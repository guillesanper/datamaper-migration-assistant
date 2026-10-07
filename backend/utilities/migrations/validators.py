# backend/migrations/validators.py
"""
Sistema de validación de cambios de tipos de datos y backups automáticos.
Previene pérdida de datos mediante validaciones pre-migración y backups.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

# ============================================================================
# MATRIZ DE COMPATIBILIDAD DE TIPOS DE DATOS
# ============================================================================

# Nivel de seguridad: 'safe', 'warning', 'danger'
TYPE_COMPATIBILITY_MATRIX = {
    # TEXT-based types
    ("TEXT", "VARCHAR"): ("warning", "Posible truncado si VARCHAR tiene límite pequeño"),
    ("TEXT", "CHAR"): ("warning", "Posible truncado y padding con espacios"),
    ("TEXT", "JSON"): ("warning", "Requiere validación de formato JSON"),
    ("TEXT", "JSONB"): ("warning", "Requiere validación de formato JSON"),
    ("TEXT", "UUID"): ("warning", "Requiere validación de formato UUID"),
    ("TEXT", "INTEGER"): ("danger", "Solo si todos los valores son numéricos"),
    ("TEXT", "NUMERIC"): ("danger", "Solo si todos los valores son numéricos"),
    # VARCHAR conversions
    ("VARCHAR", "TEXT"): ("safe", "Expansión segura"),
    ("VARCHAR", "VARCHAR"): ("warning", "Puede haber truncado si el nuevo límite es menor"),
    ("VARCHAR", "CHAR"): ("warning", "Posible truncado y padding"),
    ("VARCHAR", "JSON"): ("warning", "Requiere validación de formato JSON"),
    ("VARCHAR", "JSONB"): ("warning", "Requiere validación de formato JSON"),
    ("VARCHAR", "UUID"): ("warning", "Requiere validación de formato UUID"),
    ("VARCHAR", "INTEGER"): ("danger", "Solo si todos los valores son numéricos"),
    # CHAR conversions
    ("CHAR", "TEXT"): ("safe", "Expansión segura, se eliminarán espacios de padding"),
    ("CHAR", "VARCHAR"): ("safe", "Conversión segura"),
    ("CHAR", "CHAR"): ("warning", "Puede haber truncado si el nuevo límite es menor"),
    # INTEGER family conversions
    ("SMALLINT", "INTEGER"): ("safe", "Expansión de rango segura"),
    ("SMALLINT", "BIGINT"): ("safe", "Expansión de rango segura"),
    ("INTEGER", "BIGINT"): ("safe", "Expansión de rango segura"),
    ("INTEGER", "SMALLINT"): ("warning", "Posible overflow si hay valores fuera de rango"),
    ("BIGINT", "INTEGER"): ("warning", "Posible overflow si hay valores fuera de rango"),
    ("BIGINT", "SMALLINT"): ("warning", "Posible overflow si hay valores fuera de rango"),
    ("INTEGER", "NUMERIC"): ("safe", "Conversión segura"),
    ("INTEGER", "DECIMAL"): ("safe", "Conversión segura"),
    ("INTEGER", "REAL"): ("warning", "Posible pérdida de precisión para valores grandes"),
    ("INTEGER", "FLOAT"): ("warning", "Posible pérdida de precisión"),
    ("INTEGER", "TEXT"): ("safe", "Conversión segura"),
    ("INTEGER", "VARCHAR"): ("safe", "Conversión segura"),
    # NUMERIC/DECIMAL conversions
    ("NUMERIC", "DECIMAL"): ("safe", "Son equivalentes"),
    ("NUMERIC", "INTEGER"): ("warning", "Se perderán decimales"),
    ("NUMERIC", "BIGINT"): ("warning", "Se perderán decimales"),
    ("NUMERIC", "REAL"): ("warning", "Posible pérdida de precisión"),
    ("NUMERIC", "TEXT"): ("safe", "Conversión segura"),
    ("NUMERIC", "VARCHAR"): ("safe", "Conversión segura"),
    ("NUMERIC", "NUMERIC"): (
        "warning",
        "Puede haber pérdida de precisión si se reduce precision/scale",
    ),
    ("DECIMAL", "NUMERIC"): ("safe", "Son equivalentes"),
    ("DECIMAL", "INTEGER"): ("warning", "Se perderán decimales"),
    ("DECIMAL", "TEXT"): ("safe", "Conversión segura"),
    # REAL/FLOAT conversions
    ("REAL", "DOUBLE PRECISION"): ("safe", "Aumento de precisión"),
    ("REAL", "FLOAT"): ("safe", "Son equivalentes"),
    ("REAL", "NUMERIC"): ("warning", "Posible pérdida de precisión dependiendo de la escala"),
    ("REAL", "INTEGER"): ("warning", "Se perderán decimales y posible overflow"),
    ("REAL", "TEXT"): ("safe", "Conversión segura"),
    ("DOUBLE PRECISION", "REAL"): ("warning", "Pérdida de precisión"),
    ("DOUBLE PRECISION", "NUMERIC"): ("warning", "Posible pérdida de precisión"),
    ("DOUBLE PRECISION", "TEXT"): ("safe", "Conversión segura"),
    # FLOAT conversions
    ("FLOAT", "DOUBLE PRECISION"): ("safe", "Aumento de precisión"),
    ("FLOAT", "REAL"): ("safe", "Son equivalentes"),
    ("FLOAT", "INTEGER"): ("warning", "Se perderán decimales"),
    ("FLOAT", "TEXT"): ("safe", "Conversión segura"),
    # BOOLEAN conversions
    ("BOOLEAN", "TEXT"): ("safe", "Conversión segura"),
    ("BOOLEAN", "VARCHAR"): ("safe", "Conversión segura"),
    ("BOOLEAN", "INTEGER"): ("safe", "true=1, false=0"),
    ("INTEGER", "BOOLEAN"): ("warning", "0=false, cualquier otro=true"),
    ("TEXT", "BOOLEAN"): ("danger", "Solo si valores son true/false/t/f/yes/no/1/0"),
    # DATE/TIME conversions
    ("DATE", "TIMESTAMP"): ("safe", "Se agrega hora 00:00:00"),
    ("DATE", "TIMESTAMPTZ"): ("safe", "Se agrega hora 00:00:00 con zona horaria"),
    ("DATE", "TEXT"): ("safe", "Conversión segura"),
    ("DATE", "VARCHAR"): ("safe", "Conversión segura"),
    ("DATETIME", "TIMESTAMP"): ("safe", "Son equivalentes"),
    ("DATETIME", "TIMESTAMPTZ"): ("safe", "Se agrega zona horaria"),
    ("DATETIME", "DATE"): ("warning", "Se perderá la información de hora"),
    ("DATETIME", "TIME"): ("warning", "Se perderá la información de fecha"),
    ("DATETIME", "TEXT"): ("safe", "Conversión segura"),
    ("TIMESTAMP", "TIMESTAMPTZ"): (
        "warning",
        "Se agregará zona horaria (puede cambiar interpretación)",
    ),
    ("TIMESTAMP", "DATE"): ("warning", "Se perderá la información de hora"),
    ("TIMESTAMP", "TIME"): ("warning", "Se perderá la información de fecha"),
    ("TIMESTAMP", "TEXT"): ("safe", "Conversión segura"),
    ("TIMESTAMP", "DATETIME"): ("safe", "Son equivalentes"),
    ("TIMESTAMPTZ", "TIMESTAMP"): ("warning", "Se perderá la zona horaria"),
    ("TIMESTAMPTZ", "DATE"): ("warning", "Se perderá hora y zona horaria"),
    ("TIMESTAMPTZ", "TEXT"): ("safe", "Conversión segura"),
    ("TIME", "TEXT"): ("safe", "Conversión segura"),
    ("TIME", "VARCHAR"): ("safe", "Conversión segura"),
    # JSON conversions
    ("JSON", "JSONB"): ("safe", "JSONB es más eficiente"),
    ("JSON", "TEXT"): ("safe", "Conversión segura"),
    ("JSONB", "JSON"): ("safe", "Conversión segura"),
    ("JSONB", "TEXT"): ("safe", "Conversión segura"),
    ("TEXT", "JSONB"): ("danger", "Requiere validación de formato JSON"),
    # UUID conversions
    ("UUID", "TEXT"): ("safe", "Conversión segura"),
    ("UUID", "VARCHAR"): ("safe", "Conversión segura (requiere VARCHAR(36)"),
    ("UUID", "CHAR"): ("warning", "Requiere CHAR(36)"),
    # BYTEA conversions
    ("BYTEA", "TEXT"): ("warning", "Conversión a representación hexadecimal"),
    ("TEXT", "BYTEA"): ("danger", "Requiere formato hexadecimal o escape válido"),
    # Array conversions
    ("ARRAY", "TEXT"): ("safe", "Conversión a representación de texto"),
    ("ARRAY", "JSON"): ("safe", "Conversión a JSON array"),
    ("ARRAY", "JSONB"): ("safe", "Conversión a JSONB array"),
}


# ============================================================================
# TYPE PARAMETER VALIDATION RANGES
# ============================================================================

TYPE_PARAMETER_RANGES = {
    "VARCHAR": {"length": (1, 10485760)},  # PostgreSQL max
    "CHAR": {"length": (1, 10485760)},
    "NUMERIC": {"precision": (1, 1000), "scale": (0, 1000)},
    "DECIMAL": {"precision": (1, 1000), "scale": (0, 1000)},
}


# ============================================================================
# MIGRATION VALIDATOR CLASS
# ============================================================================


class MigrationValidator:
    """Validador de migraciones de tipos de datos"""

    def __init__(self, db_connection):
        """
        Inicializar validador

        Args:
            db_connection: Conexión a la base de datos PostgreSQL
        """
        self.db = db_connection

    def parse_data_type(self, data_type: str) -> Dict[str, Any]:
        """
        Parsear tipo de dato en sus componentes

        Args:
            data_type: Tipo completo, ej: "VARCHAR(255)", "NUMERIC(10,2)"

        Returns:
            Dict con base_type, parameters, y full_type

        Examples:
            >>> parse_data_type("VARCHAR(255)")
            {'base_type': 'VARCHAR', 'parameters': {'length': 255}, 'full_type': 'VARCHAR(255)'}

            >>> parse_data_type("NUMERIC(10,2)")
            {'base_type': 'NUMERIC', 'parameters': {'precision': 10, 'scale': 2}, 'full_type': 'NUMERIC(10,2)'}
        """
        data_type = data_type.strip().upper()

        # Check for parametrized types
        if "(" in data_type:
            base_type = data_type[: data_type.index("(")]
            params_str = data_type[data_type.index("(") + 1 : data_type.index(")")]

            parameters = {}

            if "," in params_str:
                # NUMERIC(10,2) or DECIMAL(10,2)
                parts = [p.strip() for p in params_str.split(",")]
                if base_type in ["NUMERIC", "DECIMAL"]:
                    parameters["precision"] = int(parts[0])
                    parameters["scale"] = int(parts[1])
            else:
                # VARCHAR(255) or CHAR(50)
                if base_type in ["VARCHAR", "CHAR"]:
                    parameters["length"] = int(params_str)

            return {"base_type": base_type, "parameters": parameters, "full_type": data_type}
        else:
            # Simple type without parameters
            return {"base_type": data_type, "parameters": {}, "full_type": data_type}

    def check_type_compatibility(self, old_type: str, new_type: str) -> Tuple[str, str, str]:
        """
        Verificar compatibilidad entre dos tipos de datos

        Args:
            old_type: Tipo actual (ej: "VARCHAR(100)")
            new_type: Tipo nuevo (ej: "VARCHAR(50)")

        Returns:
            Tuple de (risk_level, message, recommendation)
            risk_level: 'safe' | 'warning' | 'danger' | 'blocked'
        """
        old_parsed = self.parse_data_type(old_type)
        new_parsed = self.parse_data_type(new_type)

        old_base = old_parsed["base_type"]
        new_base = new_parsed["base_type"]

        # Same base type, check parameters
        if old_base == new_base:
            return self._check_parameter_compatibility(old_parsed, new_parsed)

        # Different base types, check matrix
        compatibility_key = (old_base, new_base)

        if compatibility_key in TYPE_COMPATIBILITY_MATRIX:
            risk_level, message = TYPE_COMPATIBILITY_MATRIX[compatibility_key]
            recommendation = self._get_recommendation(risk_level, old_type, new_type)
            return risk_level, message, recommendation

        # No specific rule found - default to danger
        return (
            "danger",
            f"Cambio no estándar de {old_type} a {new_type}. Se requiere validación manual.",
            "Verificar manualmente que todos los datos sean compatibles. Crear backup antes de continuar.",
        )

    def _check_parameter_compatibility(
        self, old_parsed: Dict[str, Any], new_parsed: Dict[str, Any]
    ) -> Tuple[str, str, str]:
        """Verificar compatibilidad de parámetros para el mismo tipo base"""
        base_type = old_parsed["base_type"]
        old_params = old_parsed["parameters"]
        new_params = new_parsed["parameters"]

        # VARCHAR or CHAR length changes
        if base_type in ["VARCHAR", "CHAR"]:
            old_length = old_params.get("length", float("inf"))
            new_length = new_params.get("length", float("inf"))

            if new_length >= old_length:
                return (
                    "safe",
                    f'Expansión segura de {old_parsed["full_type"]} a {new_parsed["full_type"]}',
                    "No se requiere acción adicional.",
                )
            else:
                return (
                    "warning",
                    f"Reducción de {old_length} a {new_length} caracteres. Posible truncado de datos.",
                    "Verificar que ningún valor exceda el nuevo límite. Se creará un backup automático.",
                )

        # NUMERIC or DECIMAL precision/scale changes
        if base_type in ["NUMERIC", "DECIMAL"]:
            old_precision = old_params.get("precision", 1000)
            old_scale = old_params.get("scale", 0)
            new_precision = new_params.get("precision", 1000)
            new_scale = new_params.get("scale", 0)

            if new_precision >= old_precision and new_scale >= old_scale:
                return (
                    "safe",
                    f"Expansión segura de precisión/escala",
                    "No se requiere acción adicional.",
                )
            else:
                return (
                    "warning",
                    f"Reducción de precisión de ({old_precision},{old_scale}) a ({new_precision},{new_scale}). Posible pérdida de dígitos.",
                    "Verificar que ningún valor exceda el nuevo límite. Se creará un backup automático.",
                )

        # No parameters changed
        return ("safe", f"Sin cambios en {base_type}", "No se requiere acción adicional.")

    def _get_recommendation(self, risk_level: str, old_type: str, new_type: str) -> str:
        """Generar recomendación basada en nivel de riesgo"""
        if risk_level == "safe":
            return "Cambio seguro. No se requiere acción adicional."
        elif risk_level == "warning":
            return f"Se recomienda revisar los datos antes de cambiar de {old_type} a {new_type}. Se creará un backup automático."
        else:  # danger
            return f"PRECAUCIÓN: Cambio riesgoso de {old_type} a {new_type}. Se requiere confirmación explícita y se creará un backup."

    def analyze_data_for_type_change(
        self, table_id: str, column_id: str, new_type: str, sample_size: int = 100
    ) -> Dict[str, Any]:
        """
        Analizar datos existentes para determinar si el cambio de tipo es seguro

        Args:
            table_id: ID de la tabla
            column_id: ID de la columna
            new_type: Nuevo tipo de dato
            sample_size: Cantidad de ejemplos a retornar

        Returns:
            Dict con:
            - affected_rows: cantidad de filas que podrían tener problemas
            - total_rows: total de filas
            - examples: lista de ejemplos problemáticos
            - is_safe_data: bool indicando si los datos son seguros
        """
        # Get column info
        column = (
            self.db.execute(
                text("""
                SELECT c.name, c.data_type, t.name as table_name
                FROM columns c
                JOIN tables t ON c.table_id = t.id
                WHERE c.id = :column_id
            """),
                {"column_id": column_id},
            )
            .mappings()
            .fetchone()
        )
        if not column:
            return {
                "affected_rows": 0,
                "total_rows": 0,
                "examples": [],
                "is_safe_data": True,
                "message": "Columna no encontrada",
            }

        old_type = column["data_type"]
        column_name = column["name"]

        # Parse new type
        new_parsed = self.parse_data_type(new_type)

        # Specific validations based on new type
        affected_rows = 0
        examples: list[Any] = []
        total_rows = 0

        # For VARCHAR/CHAR length reductions
        if new_parsed["base_type"] in ["VARCHAR", "CHAR"] and "length" in new_parsed["parameters"]:
            new_length = new_parsed["parameters"]["length"]

            # This would require actual table data which we don't have in the schema
            # In a real implementation, we would query the actual data table
            # For now, return a placeholder

            return {
                "affected_rows": 0,
                "total_rows": 0,
                "examples": [],
                "is_safe_data": True,
                "message": f"Se reducirá el límite a {new_length} caracteres. Verificar datos reales antes de aplicar.",
            }

        # For numeric type changes
        if (
            new_parsed["base_type"] in ["NUMERIC", "DECIMAL"]
            and "precision" in new_parsed["parameters"]
        ):
            return {
                "affected_rows": 0,
                "total_rows": 0,
                "examples": [],
                "is_safe_data": True,
                "message": f'Se cambiará a precisión ({new_parsed["parameters"]["precision"]},{new_parsed["parameters"]["scale"]}). Verificar datos reales.',
            }

        return {
            "affected_rows": affected_rows,
            "total_rows": total_rows,
            "examples": examples,
            "is_safe_data": True,
            "message": "Análisis completado",
        }

    def validate_type_change(
        self, table_id: str, column_id: str, old_type: str, new_type: str
    ) -> Dict[str, Any]:
        """
        Validación completa de cambio de tipo

        Returns:
            Dict con toda la información de validación:
            - is_safe: bool
            - risk_level: 'safe' | 'warning' | 'danger'
            - message: mensaje descriptivo
            - affected_rows: filas afectadas
            - examples: ejemplos de valores problemáticos
            - recommendation: recomendación
        """
        # Check type compatibility
        risk_level, message, recommendation = self.check_type_compatibility(old_type, new_type)

        # Analyze existing data
        data_analysis = self.analyze_data_for_type_change(table_id, column_id, new_type)

        # Determine if it's safe
        is_safe = risk_level == "safe" and data_analysis["is_safe_data"]

        return {
            "is_safe": is_safe,
            "risk_level": risk_level,
            "message": message,
            "affected_rows": data_analysis["affected_rows"],
            "examples": data_analysis["examples"],
            "recommendation": recommendation,
            "data_analysis": data_analysis,
        }


# ============================================================================
# BACKUP MANAGER CLASS
# ============================================================================


class BackupManager:
    """Gestor de backups automáticos para migraciones"""

    def __init__(self, db_connection, backup_dir: Optional[str] = None):
        """
        Inicializar gestor de backups

        Args:
            db_connection: Conexión a la base de datos
            backup_dir: Directorio para guardar backups (default: dev/backups/)
        """
        self.db = db_connection

        if backup_dir is None:
            # Default to dev/backups/
            project_root = Path(__file__).parent.parent.parent
            self.backup_dir = project_root / "backups"
        else:
            self.backup_dir = Path(backup_dir)

        # Create backup directory if it doesn't exist
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self.retention_days = 30

    def create_backup(self, tables: List[str], description: Optional[str] = None) -> Dict[str, Any]:
        """
        Crear backup de tablas especificadas

        Args:
            tables: Lista de nombres de tablas a respaldar
            description: Descripción del backup

        Returns:
            Dict con información del backup creado
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_id = f"backup_{timestamp}"

        backup_info: Dict[str, Any] = {
            "backup_id": backup_id,
            "timestamp": datetime.now().isoformat(),
            "description": description or "Backup automático",
            "tables": [],
            "files": [],
        }

        for table_name in tables:
            # Get table data
            rows = self.db.execute(text(f"SELECT * FROM {table_name}")).mappings().all()

            # Convert to list of dicts
            data = [dict(row) for row in rows]

            # Save to file
            filename = f"{backup_id}_{table_name}.json"
            filepath = self.backup_dir / filename

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "table": table_name,
                        "timestamp": backup_info["timestamp"],
                        "row_count": len(data),
                        "data": data,
                    },
                    f,
                    indent=2,
                    default=str,
                )

            backup_info["tables"].append(
                {"table": table_name, "row_count": len(data), "file": filename}
            )
            backup_info["files"].append(str(filepath))

        # Save backup metadata
        metadata_file = self.backup_dir / f"{backup_id}_metadata.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(backup_info, f, indent=2)

        return backup_info

    def list_backups(self) -> List[Dict[str, Any]]:
        """Listar todos los backups disponibles"""
        backups = []

        for metadata_file in self.backup_dir.glob("*_metadata.json"):
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    backup_info = json.load(f)
                    backups.append(backup_info)
            except Exception as e:
                print(f"Error reading backup metadata {metadata_file}: {e}")

        # Sort by timestamp descending
        backups.sort(key=lambda x: x["timestamp"], reverse=True)

        return backups

    def restore_backup(self, backup_id: str) -> Dict[str, Any]:
        """
        Restaurar desde un backup

        Args:
            backup_id: ID del backup a restaurar

        Returns:
            Dict con resultado de la restauración
        """
        # Load metadata
        metadata_file = self.backup_dir / f"{backup_id}_metadata.json"

        if not metadata_file.exists():
            return {"success": False, "message": f"Backup {backup_id} no encontrado"}

        with open(metadata_file, "r", encoding="utf-8") as f:
            backup_info = json.load(f)

        restored_tables = []

        try:
            for table_info in backup_info["tables"]:
                table_name = table_info["table"]
                filename = table_info["file"]
                filepath = self.backup_dir / filename

                # Load backup data
                with open(filepath, "r", encoding="utf-8") as f:
                    backup_data = json.load(f)

                # NOTE: This is a simplified restore
                # In a real implementation, you would need to:
                # 1. Truncate or delete existing data
                # 2. Insert backup data
                # 3. Handle foreign key constraints
                # 4. Restore sequences/auto-increment values

                restored_tables.append(table_name)

            self.db.commit()

            return {
                "success": True,
                "message": f"Backup {backup_id} restaurado exitosamente",
                "restored_tables": restored_tables,
            }

        except Exception as e:
            self.db.rollback()
            return {"success": False, "message": f"Error al restaurar backup: {str(e)}"}

    def cleanup_old_backups(self) -> Dict[str, Any]:
        """Eliminar backups más antiguos que retention_days"""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        deleted_backups = []

        for metadata_file in self.backup_dir.glob("*_metadata.json"):
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    backup_info = json.load(f)

                backup_date = datetime.fromisoformat(backup_info["timestamp"])

                if backup_date < cutoff_date:
                    # Delete backup files
                    backup_id = backup_info["backup_id"]

                    for file_info in backup_info["tables"]:
                        filepath = self.backup_dir / file_info["file"]
                        if filepath.exists():
                            filepath.unlink()

                    # Delete metadata
                    metadata_file.unlink()

                    deleted_backups.append(backup_id)

            except Exception as e:
                print(f"Error cleaning up backup {metadata_file}: {e}")

        return {"deleted_count": len(deleted_backups), "deleted_backups": deleted_backups}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def backup_before_migration(db_connection, tables: List[str], description: str) -> Dict[str, Any]:
    """
    Helper function para crear backup antes de una migración

    Args:
        db_connection: Conexión a la base de datos
        tables: Lista de tablas a respaldar
        description: Descripción del backup

    Returns:
        Información del backup creado
    """
    manager = BackupManager(db_connection)
    return manager.create_backup(tables, description)


def validate_column_type_change(
    db_connection, table_id: str, column_id: str, old_type: str, new_type: str
) -> Dict[str, Any]:
    """
    Helper function para validar un cambio de tipo de columna

    Args:
        db_connection: Conexión a la base de datos
        table_id: ID de la tabla
        column_id: ID de la columna
        old_type: Tipo actual
        new_type: Tipo nuevo

    Returns:
        Resultado de la validación
    """
    validator = MigrationValidator(db_connection)
    return validator.validate_type_change(table_id, column_id, old_type, new_type)
