"""
Servicio para gestión de Primary Keys (simples y compuestas)
Contiene lógica de negocio y validaciones
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from app.crud.pk_crud import PrimaryKeyCRUD
from app.services.schema_service import SchemaService


class PrimaryKeyService:
    """Servicio para gestión de Primary Keys compuestas"""

    @staticmethod
    def get_primary_key(db, table_id: int) -> Optional[Dict[str, Any]]:
        """
        Obtiene la definición de Primary Key para una tabla

        Args:
            db: SQLAlchemy Session
            table_id: ID de la tabla (integer)

        Returns:
            {
                'id': int,
                'table_id': int,
                'column_ids': List[str],
                'columns': List[Dict],
                'constraint_name': str,
                'is_composite': bool
            }
            o None si no tiene PK
        """
        str_table_id = str(table_id)

        pk_constraint = PrimaryKeyCRUD.get_pk_constraint_by_table_id_orm(db, str_table_id)

        if not pk_constraint:
            # Fallback: buscar columnas con is_primary=true (legacy)
            legacy_pk_columns = PrimaryKeyCRUD.get_legacy_pk_columns_orm(db, str_table_id)

            if not legacy_pk_columns:
                return None

            return {
                "id": None,
                "table_id": table_id,
                "column_ids": [col["id"] for col in legacy_pk_columns],
                "columns": legacy_pk_columns,
                "constraint_name": None,
                "is_composite": len(legacy_pk_columns) > 1,
                "is_legacy": True,
            }

        # PK encontrada en tabla nueva
        column_ids = pk_constraint["column_ids"]
        columns = PrimaryKeyCRUD.get_columns_by_ids_orm(db, column_ids)

        return {
            "id": pk_constraint["id"],
            "table_id": pk_constraint["table_id"],
            "column_ids": column_ids,
            "columns": columns,
            "constraint_name": pk_constraint.get("constraint_name"),
            "is_composite": len(column_ids) > 1,
            "is_legacy": False,
            "created_at": pk_constraint.get("created_at"),
            "updated_at": pk_constraint.get("updated_at"),
        }

    @staticmethod
    def set_primary_key(
        db,
        table_id: int,
        column_ids: List[int],
        user_id: str,
        constraint_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Establece o actualiza la Primary Key de una tabla

        Args:
            db: SQLAlchemy Session
            table_id: ID de la tabla (integer)
            column_ids: Lista de IDs de columnas que componen la PK (integers)
            user_id: UUID del usuario que ejecuta la acción
            constraint_name: Nombre opcional del constraint

        Returns:
            Información de la PK creada/actualizada

        Raises:
            HTTPException: Si validación falla
        """
        PrimaryKeyService._validate_column_ids(column_ids)

        str_table_id = str(table_id)
        str_column_ids = [str(cid) for cid in column_ids]

        try:
            # 1. Verificar tabla y permisos
            table = PrimaryKeyCRUD.get_table_by_id_orm(db, str_table_id)
            if not table:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Tabla no encontrada"
                )

            project_id = table["project_id"]
            SchemaService.can_user_modify_schema(db, project_id, user_id)

            # 2. Validar columnas
            columns = PrimaryKeyCRUD.get_columns_for_validation_orm(db, str_column_ids)
            PrimaryKeyService._validate_columns(columns, column_ids, table_id)

            # 3. Crear o actualizar PK
            existing_pk = PrimaryKeyCRUD.get_pk_constraint_by_table_id_orm(db, str_table_id)
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            if existing_pk:
                PrimaryKeyCRUD.update_pk_constraint_orm(
                    db, str_table_id, str_column_ids, constraint_name, now
                )
            else:
                PrimaryKeyCRUD.create_pk_constraint_orm(
                    db, str_table_id, str_column_ids, constraint_name, now
                )

            # 4. Actualizar is_primary en columnas
            PrimaryKeyCRUD.update_columns_primary_flag_orm(db, str_table_id, str_column_ids, now)

            # 5. Retornar información completa
            return PrimaryKeyService.get_primary_key(db, table_id)

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error configurando Primary Key: {str(e)}",
            )

    @staticmethod
    def _validate_column_ids(column_ids: List[int]) -> None:
        """Valida que la lista de column_ids sea correcta"""
        if not column_ids or len(column_ids) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debe especificar al menos una columna para la Primary Key",
            )

        if len(column_ids) > 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Primary Key compuesta no puede tener más de 5 columnas",
            )

    @staticmethod
    def _validate_columns(columns: List[Any], column_ids: List[int], table_id: int) -> None:
        """Valida que las columnas existan y pertenezcan a la tabla"""
        if len(columns) != len(column_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Una o más columnas no existen"
            )

        str_table_id = str(table_id)
        for col in columns:
            if str(col["table_id"]) != str_table_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"La columna '{col['name']}' no pertenece a esta tabla",
                )

    @staticmethod
    def remove_primary_key(db, table_id: int, user_id: str) -> Dict[str, Any]:
        """
        Elimina la Primary Key de una tabla

        Args:
            db: SQLAlchemy Session
            table_id: ID de la tabla (integer)
            user_id: UUID del usuario que ejecuta la acción

        Returns:
            {'success': bool, 'message': str, 'removed_pk': Dict}

        Raises:
            HTTPException: Si validación falla
        """
        str_table_id = str(table_id)

        try:
            # 1. Verificar tabla y permisos
            table = PrimaryKeyCRUD.get_table_by_id_orm(db, str_table_id)
            if not table:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Tabla no encontrada"
                )

            SchemaService.can_user_modify_schema(db, table["project_id"], user_id)

            # 2. Obtener PK actual antes de eliminar
            pk_info = PrimaryKeyService.get_primary_key(db, table_id)
            if not pk_info:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Esta tabla no tiene Primary Key definida",
                )

            # 3. Eliminar PK constraint
            PrimaryKeyCRUD.delete_pk_constraint_orm(db, str_table_id)

            # 4. Actualizar is_primary a false en todas las columnas
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            PrimaryKeyCRUD.clear_all_primary_flags_orm(db, str_table_id, now)

            return {
                "success": True,
                "message": "Primary Key eliminada exitosamente",
                "removed_pk": pk_info,
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error eliminando Primary Key: {str(e)}",
            )

    @staticmethod
    def validate_pk_mapping_completeness(db, project_id: str) -> Dict[str, Any]:
        """
        Valida que todas las columnas de Primary Keys compuestas
        estén mapeadas en tablas destino

        Args:
            db: SQLAlchemy Session
            project_id: UUID del proyecto

        Returns:
            {
                'is_valid': bool,
                'missing_mappings': List[Dict],
                'warnings': List[str]
            }
        """
        origin_tables_with_pks = PrimaryKeyCRUD.get_origin_tables_with_pks_orm(db, project_id)

        missing_mappings = []
        warnings = []

        for table in origin_tables_with_pks:
            table_name = table["table_name"]
            column_ids = table["column_ids"]

            # Obtener nombres de columnas
            pk_columns_data = PrimaryKeyCRUD.get_columns_by_ids_orm(db, column_ids)
            pk_columns = {col["id"]: col["name"] for col in pk_columns_data}

            # Verificar que cada columna de PK tenga mapping
            for col_id, col_name in pk_columns.items():
                count = PrimaryKeyCRUD.count_column_mappings_orm(
                    db, project_id, table_name, col_name
                )

                if count == 0:
                    missing_mappings.append(
                        {"table": table_name, "column": col_name, "is_pk_column": True}
                    )
                    warnings.append(f"⚠️ Columna PK sin mapear: {table_name}.{col_name}")

        is_valid = len(missing_mappings) == 0

        return {
            "is_valid": is_valid,
            "missing_mappings": missing_mappings,
            "warnings": warnings,
            "checked_tables": len(origin_tables_with_pks),
            "total_missing": len(missing_mappings),
        }
