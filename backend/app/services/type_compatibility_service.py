# backend/app/services/type_compatibility_service.py
"""
Servicio de validación de compatibilidad entre tipos de datos.
Utiliza el MigrationValidator para determinar si un cambio de tipo es seguro.
"""

import sys
from pathlib import Path
from typing import Any, Dict, Tuple

from fastapi import HTTPException, status
from sqlalchemy import text

# Add migrations directory to path to import validators
migrations_dir = Path(__file__).parent.parent.parent / "migrations"
sys.path.insert(0, str(migrations_dir))

try:
    from validators import BackupManager, MigrationValidator
except ImportError:
    # Fallback if validators not available
    MigrationValidator = None
    BackupManager = None


class TypeCompatibilityService:
    """Servicio para validar cambios de tipos de datos"""

    @staticmethod
    def validate_type_change_request(
        db, table_id: str, column_id: str, new_type: str
    ) -> Dict[str, Any]:
        """
        Validar una solicitud de cambio de tipo de columna

        Args:
            db: Conexión a la base de datos
            table_id: ID de la tabla
            column_id: ID de la columna
            new_type: Nuevo tipo solicitado

        Returns:
            Dict con información de validación:
            - is_safe: bool
            - risk_level: 'safe' | 'warning' | 'danger'
            - message: descripción del riesgo
            - recommendation: qué hacer
            - old_type: tipo actual
            - new_type: tipo solicitado
            - requires_confirmation: si requiere confirmación del usuario
            - requires_backup: si requiere backup antes del cambio

        Raises:
            HTTPException: Si la columna no existe o hay error de validación
        """
        if not MigrationValidator:
            # Fallback si validators no está disponible
            return {
                "is_safe": False,
                "risk_level": "warning",
                "message": "Sistema de validación no disponible. Proceder con precaución.",
                "recommendation": "Crear backup manual antes de cambiar tipo.",
                "old_type": None,
                "new_type": new_type,
                "requires_confirmation": True,
                "requires_backup": True,
            }

        # Get current column info
        row = (
            db.execute(
                text("""
                SELECT c.id, c.name, c.data_type, c.table_id,
                       t.name as table_name, t.project_id
                FROM columns c
                JOIN tables t ON c.table_id = t.id
                WHERE c.id = :column_id
            """),
                {"column_id": column_id},
            )
            .mappings()
            .fetchone()
        )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Columna no encontrada"
            )

        column = dict(row)
        old_type = column["data_type"]

        # Check if it's the same type
        if old_type.upper() == new_type.upper():
            return {
                "is_safe": True,
                "risk_level": "safe",
                "message": "No hay cambio de tipo",
                "recommendation": "No se requiere acción.",
                "old_type": old_type,
                "new_type": new_type,
                "requires_confirmation": False,
                "requires_backup": False,
            }

        # Use MigrationValidator to check compatibility
        validator = MigrationValidator(db)
        validation_result = validator.validate_type_change(
            table_id=table_id, column_id=column_id, old_type=old_type, new_type=new_type
        )

        # Determine if confirmation and backup are required
        risk_level = validation_result["risk_level"]

        return {
            "is_safe": validation_result["is_safe"],
            "risk_level": risk_level,
            "message": validation_result["message"],
            "recommendation": validation_result["recommendation"],
            "old_type": old_type,
            "new_type": new_type,
            "requires_confirmation": risk_level in ["warning", "danger"],
            "requires_backup": risk_level in ["warning", "danger"],
            "affected_rows": validation_result.get("affected_rows", 0),
            "examples": validation_result.get("examples", []),
            "column_name": column["name"],
            "table_name": column["table_name"],
        }

    @staticmethod
    def create_backup_before_type_change(
        db, table_id: str, column_id: str, old_type: str, new_type: str
    ) -> Dict[str, Any]:
        """
        Crear backup antes de cambiar tipo de columna

        Args:
            db: Conexión a la base de datos
            table_id: ID de la tabla
            column_id: ID de la columna
            old_type: Tipo actual
            new_type: Tipo nuevo

        Returns:
            Información del backup creado
        """
        if not BackupManager:
            return {"success": False, "message": "Sistema de backup no disponible"}

        try:
            # Get table and column info
            row = (
                db.execute(
                    text("""
                    SELECT c.name as column_name, t.name as table_name
                    FROM columns c
                    JOIN tables t ON c.table_id = t.id
                    WHERE c.id = :column_id
                """),
                    {"column_id": column_id},
                )
                .mappings()
                .fetchone()
            )

            if not row:
                return {"success": False, "message": "Columna no encontrada"}

            info = dict(row)

            # Create backup of relevant tables
            manager = BackupManager(db)
            backup_info = manager.create_backup(
                tables=["columns", "mappings"],
                description=f"Antes de cambiar tipo de {info['table_name']}.{info['column_name']} de {old_type} a {new_type}",
            )

            return {
                "success": True,
                "backup_id": backup_info["backup_id"],
                "backup_info": backup_info,
                "message": "Backup creado exitosamente",
            }

        except Exception as e:
            return {"success": False, "message": f"Error creando backup: {str(e)}"}

    @staticmethod
    def get_type_suggestions(base_type: str) -> Dict[str, Any]:
        """
        Obtener sugerencias de configuración para un tipo base

        Args:
            base_type: Tipo base (VARCHAR, NUMERIC, etc.)

        Returns:
            Dict con sugerencias de parámetros comunes
        """
        suggestions: Dict[str, Any] = {
            "VARCHAR": {
                "common_lengths": [50, 100, 255, 500, 1000],
                "default_length": 255,
                "description": "Variable-length character string",
                "requires": ["length"],
            },
            "CHAR": {
                "common_lengths": [1, 10, 50, 100],
                "default_length": 50,
                "description": "Fixed-length character string (padded with spaces)",
                "requires": ["length"],
            },
            "NUMERIC": {
                "common_configs": [
                    {"precision": 10, "scale": 2, "description": "Moneda (10,2)"},
                    {"precision": 18, "scale": 4, "description": "Alta precisión (18,4)"},
                    {"precision": 5, "scale": 0, "description": "Enteros pequeños (5,0)"},
                ],
                "default": {"precision": 10, "scale": 2},
                "description": "Exact numeric with user-defined precision",
                "requires": ["precision", "scale"],
            },
            "DECIMAL": {
                "common_configs": [
                    {"precision": 10, "scale": 2, "description": "Moneda (10,2)"},
                    {"precision": 18, "scale": 4, "description": "Alta precisión (18,4)"},
                ],
                "default": {"precision": 10, "scale": 2},
                "description": "Exact numeric (equivalent to NUMERIC)",
                "requires": ["precision", "scale"],
            },
            "TEXT": {
                "description": "Variable-length character string (unlimited length)",
                "requires": [],
            },
            "INTEGER": {
                "range": "−2,147,483,648 to +2,147,483,647",
                "description": "4-byte signed integer",
                "requires": [],
            },
            "BIGINT": {
                "range": "−9,223,372,036,854,775,808 to +9,223,372,036,854,775,807",
                "description": "8-byte signed integer",
                "requires": [],
            },
            "SMALLINT": {
                "range": "−32,768 to +32,767",
                "description": "2-byte signed integer",
                "requires": [],
            },
            "BOOLEAN": {
                "values": ["true", "false", "null"],
                "description": "Boolean value (true/false)",
                "requires": [],
            },
            "DATE": {
                "format": "YYYY-MM-DD",
                "description": "Calendar date (year, month, day)",
                "requires": [],
            },
            "TIMESTAMP": {
                "format": "YYYY-MM-DD HH:MI:SS",
                "description": "Date and time (without timezone)",
                "requires": [],
            },
            "TIMESTAMPTZ": {
                "format": "YYYY-MM-DD HH:MI:SS+TZ",
                "description": "Date and time (with timezone)",
                "requires": [],
            },
            "TIME": {
                "format": "HH:MI:SS",
                "description": "Time of day (without date)",
                "requires": [],
            },
            "JSON": {"description": "JSON data (text format)", "requires": []},
            "JSONB": {"description": "JSON data (binary format, more efficient)", "requires": []},
            "UUID": {
                "format": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                "description": "Universally unique identifier",
                "requires": [],
            },
            "REAL": {
                "description": "Single precision floating-point (4 bytes)",
                "precision": "6 decimal digits",
                "requires": [],
            },
            "DOUBLE PRECISION": {
                "description": "Double precision floating-point (8 bytes)",
                "precision": "15 decimal digits",
                "requires": [],
            },
            "FLOAT": {"description": "Floating-point number (equivalent to REAL)", "requires": []},
        }

        return suggestions.get(  # type: ignore[no-any-return]
            base_type.upper(), {"description": "PostgreSQL data type", "requires": []}
        )

    @staticmethod
    def get_compatible_types(current_type: str) -> Dict[str, Any]:
        """
        Obtener lista de tipos compatibles con el tipo actual

        Args:
            current_type: Tipo de dato actual

        Returns:
            Dict con tipos compatibles organizados por nivel de seguridad
        """
        # This would use the TYPE_COMPATIBILITY_MATRIX from validators.py
        # For now, return a simplified version

        return {
            "safe_conversions": ["Conversiones seguras (sin pérdida de datos)"],
            "warning_conversions": ["Conversiones con advertencia (posible pérdida de datos)"],
            "danger_conversions": ["Conversiones peligrosas (requieren validación manual)"],
            "current_type": current_type,
        }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def validate_and_backup_type_change(
    db, table_id: str, column_id: str, new_type: str, user_confirmed: bool = False
) -> Tuple[bool, Dict[str, Any]]:
    """
    Validar cambio de tipo y crear backup si es necesario

    Args:
        db: Conexión a la base de datos
        table_id: ID de la tabla
        column_id: ID de la columna
        new_type: Nuevo tipo solicitado
        user_confirmed: Si el usuario confirmó el cambio riesgoso

    Returns:
        Tuple de (can_proceed, info_dict)
    """
    service = TypeCompatibilityService()

    # Validate type change
    validation = service.validate_type_change_request(db, table_id, column_id, new_type)

    # If it's safe, allow
    if validation["is_safe"]:
        return True, validation

    # If requires confirmation and user hasn't confirmed, block
    if validation["requires_confirmation"] and not user_confirmed:
        return False, {**validation, "blocked_reason": "Requiere confirmación del usuario"}

    # If requires backup, create it
    if validation["requires_backup"]:
        backup_result = service.create_backup_before_type_change(
            db, table_id, column_id, validation["old_type"], new_type
        )

        if not backup_result["success"]:
            return False, {
                **validation,
                "blocked_reason": f"Error creando backup: {backup_result['message']}",
            }

        validation["backup_created"] = backup_result

    return True, validation
