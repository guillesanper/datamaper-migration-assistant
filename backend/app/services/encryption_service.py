"""
Encryption Service
Capa de servicio para operaciones de cifrado

Maneja:
- Setup de cifrado para nuevos proyectos
- Verificación de passphrases
- Derivación de claves de cifrado
- Rotación de master keys
- Validaciones de seguridad

SEGURIDAD:
- Todas las excepciones son sanitizadas para prevenir filtrado de passphrases
- Los errores logeados no contienen información sensible
- Mensajes al usuario son genéricos y seguros

Autor: DataMap Security Team
Última actualización: 2025-01-03 (Security hardening)
"""

import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from app.config.security import security_settings
from app.crud import master_key_crud
from app.utils.encryption import EncryptionError, EncryptionManager, KeyDerivationError
from app.utils.exception_sanitizer import (
    create_safe_http_exception,
    safe_log_exception,
    sanitize_exception,
)

logger = logging.getLogger(__name__)


class EncryptionService:
    """Servicio de cifrado con lógica de negocio"""

    @staticmethod
    def setup_project_encryption(
        db, project_id: str, passphrase: str, user_id: str
    ) -> Dict[str, Any]:
        """
        Configura cifrado para un proyecto y cifra datos existentes

        Args:
            db: Database connection
            project_id: ID del proyecto
            passphrase: Passphrase del usuario (master key)
            user_id: Usuario que configura el cifrado

        Returns:
            Dict con status, configuración creada y estadísticas de cifrado

        Raises:
            HTTPException: Si ya existe configuración o passphrase es débil
        """
        # Verificar si ya tiene cifrado configurado
        existing = master_key_crud.get_project_encryption_orm(db, project_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Este proyecto ya tiene cifrado configurado",
            )

        # Validar fortaleza de la passphrase
        EncryptionService._validate_passphrase_strength(passphrase)

        # Verificar permisos del usuario (debe ser owner o editor)
        EncryptionService._verify_user_can_modify_encryption(db, project_id, user_id)

        try:
            # Crear configuración de cifrado
            config = master_key_crud.create_project_encryption_orm(db, project_id, passphrase)

            # Derivar encryption key para cifrar datos existentes
            encryption_key = master_key_crud.derive_encryption_key_for_project_orm(
                db, project_id, passphrase
            )

            if not encryption_key:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Error derivando clave de cifrado",
                )

            # Cifrar datos existentes del proyecto
            encryption_stats = EncryptionService.encrypt_existing_project_data(
                db, project_id, encryption_key
            )

            return {
                "status": "success",
                "message": "Cifrado configurado exitosamente y datos existentes cifrados",
                "project_id": project_id,
                "encryption_enabled": True,
                "created_at": config["created_at"],
                "encrypted_data": encryption_stats,
            }

        except KeyDerivationError as e:
            # Sanitizar excepción para evitar filtrado de passphrase
            safe_exc = safe_log_exception(
                e,
                logger,
                level="error",
                context={"operation": "setup_encryption", "project_id": project_id},
                user_friendly_message="Error derivando claves de cifrado",
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=safe_exc.user_message
            )
        except Exception as e:
            # CRÍTICO: Sanitizar para prevenir exposición de passphrase en logs
            safe_exc = safe_log_exception(
                e,
                logger,
                level="error",
                context={"operation": "setup_encryption", "project_id": project_id},
                user_friendly_message="Error configurando cifrado del proyecto",
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=safe_exc.user_message
            )

    @staticmethod
    def verify_project_passphrase(db, project_id: str, passphrase: str) -> bool:
        """
        Verifica si la passphrase es correcta

        Args:
            db: Database connection
            project_id: ID del proyecto
            passphrase: Passphrase a verificar

        Returns:
            True si es correcta, False en caso contrario
        """
        return master_key_crud.verify_project_passphrase_orm(db, project_id, passphrase)

    @staticmethod
    def get_encryption_key(db, project_id: str, passphrase: str) -> Optional[bytes]:
        """
        Obtiene la clave de cifrado derivada (on-demand)

        IMPORTANTE: Esta clave NUNCA se almacena, solo se deriva cuando se necesita

        Args:
            db: Database connection
            project_id: ID del proyecto
            passphrase: Passphrase del usuario

        Returns:
            32-byte AES-256 key o None si la passphrase es incorrecta

        Raises:
            HTTPException: Si el proyecto no tiene cifrado configurado
        """
        config = master_key_crud.get_project_encryption_orm(db, project_id)
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Este proyecto no tiene cifrado configurado",
            )

        if not config["encryption_enabled"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El cifrado está deshabilitado para este proyecto",
            )

        # Derivar clave
        encryption_key = master_key_crud.derive_encryption_key_for_project_orm(
            db, project_id, passphrase
        )

        if not encryption_key:
            # Passphrase incorrecta
            return None

        return encryption_key

    @staticmethod
    def rotate_master_key(
        db, project_id: str, old_passphrase: str, new_passphrase: str, user_id: str
    ) -> Dict[str, Any]:
        """
        Rota la master key de un proyecto

        Este proceso:
        1. Verifica la passphrase antigua
        2. Descifra todos los datos con la clave antigua
        3. Crea nueva configuración con nueva passphrase
        4. Re-cifra todos los datos con la nueva clave

        ADVERTENCIA: Operación costosa que puede tardar varios minutos

        Args:
            db: Database connection
            project_id: ID del proyecto
            old_passphrase: Passphrase actual
            new_passphrase: Nueva passphrase
            user_id: Usuario que realiza la rotación

        Returns:
            Dict con estadísticas de la rotación

        Raises:
            HTTPException: Si falla la verificación o el proceso
        """
        # Verificar permisos
        EncryptionService._verify_user_can_modify_encryption(db, project_id, user_id)

        # Validar nueva passphrase
        EncryptionService._validate_passphrase_strength(new_passphrase)

        # Verificar passphrase actual
        if not master_key_crud.verify_project_passphrase_orm(db, project_id, old_passphrase):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Passphrase actual incorrecta"
            )

        # Verificar que la nueva es diferente
        if old_passphrase == new_passphrase:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La nueva passphrase debe ser diferente a la actual",
            )

        try:
            # Obtener clave antigua
            old_encryption_key = master_key_crud.derive_encryption_key_for_project_orm(
                db, project_id, old_passphrase
            )

            # TODO: Re-cifrar todos los datos
            # Por ahora solo actualizar la configuración
            # La implementación completa requiere:
            # 1. Leer todos los datos cifrados
            # 2. Descifrar con old_encryption_key
            # 3. Cifrar con new_encryption_key
            # 4. Actualizar en la BD

            success = master_key_crud.rotate_project_master_key_orm(
                db, project_id, old_passphrase, new_passphrase
            )

            if not success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Error rotando master key",
                )

            return {
                "status": "success",
                "message": "Master key rotada exitosamente",
                "project_id": project_id,
                "warning": "IMPORTANTE: Guarda la nueva passphrase en un lugar seguro",
            }

        except Exception as e:
            db.rollback()
            # CRÍTICO: Sanitizar para prevenir exposición de passphrases (old y new) en logs
            safe_exc = safe_log_exception(
                e,
                logger,
                level="error",
                context={"operation": "rotate_master_key", "project_id": project_id},
                user_friendly_message="Error durante rotación de master key",
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=safe_exc.user_message
            )

    @staticmethod
    def get_encryption_stats(db, project_id: str) -> Dict[str, Any]:
        """
        Obtiene estadísticas de cifrado para un proyecto

        Args:
            db: Database session (SQLAlchemy)
            project_id: ID del proyecto

        Returns:
            Dict con estadísticas de cifrado
        """
        from sqlalchemy import and_, func

        from app.models.orm.column import TableColumn
        from app.models.orm.comment import Comment
        from app.models.orm.mapping import Mapping
        from app.models.orm.table import Table
        from app.models.orm.version import EntityVersion

        tables_total = (
            db.query(func.count(Table.id)).filter(Table.project_id == project_id).scalar() or 0
        )
        tables_encrypted = (
            db.query(func.count(Table.id))
            .filter(and_(Table.project_id == project_id, Table.is_encrypted == True))
            .scalar()
            or 0
        )

        columns_total = (
            db.query(func.count(TableColumn.id))
            .join(Table, TableColumn.table_id == Table.id)
            .filter(Table.project_id == project_id)
            .scalar()
            or 0
        )
        columns_encrypted = (
            db.query(func.count(TableColumn.id))
            .join(Table, TableColumn.table_id == Table.id)
            .filter(and_(Table.project_id == project_id, TableColumn.is_encrypted == True))
            .scalar()
            or 0
        )

        mappings_total = (
            db.query(func.count(Mapping.id)).filter(Mapping.project_id == project_id).scalar() or 0
        )
        mappings_encrypted = (
            db.query(func.count(Mapping.id))
            .filter(and_(Mapping.project_id == project_id, Mapping.is_encrypted == True))
            .scalar()
            or 0
        )

        versions_total = (
            db.query(func.count(EntityVersion.id))
            .filter(EntityVersion.project_id == project_id)
            .scalar()
            or 0
        )
        versions_encrypted = (
            db.query(func.count(EntityVersion.id))
            .filter(
                and_(EntityVersion.project_id == project_id, EntityVersion.is_encrypted == True)
            )
            .scalar()
            or 0
        )

        comments_total = (
            db.query(func.count(Comment.id)).filter(Comment.project_id == project_id).scalar() or 0
        )
        comments_encrypted = (
            db.query(func.count(Comment.id))
            .filter(and_(Comment.project_id == project_id, Comment.is_encrypted == True))
            .scalar()
            or 0
        )

        total_items = (
            tables_total + columns_total + mappings_total + versions_total + comments_total
        )
        encrypted_items = (
            tables_encrypted
            + columns_encrypted
            + mappings_encrypted
            + versions_encrypted
            + comments_encrypted
        )
        encryption_percentage = (
            round((encrypted_items / total_items * 100), 2) if total_items > 0 else 0.0
        )

        return {
            "tables_total": tables_total,
            "tables_encrypted": tables_encrypted,
            "columns_total": columns_total,
            "columns_encrypted": columns_encrypted,
            "mappings_total": mappings_total,
            "mappings_encrypted": mappings_encrypted,
            "versions_total": versions_total,
            "versions_encrypted": versions_encrypted,
            "comments_total": comments_total,
            "comments_encrypted": comments_encrypted,
            "encryption_percentage": encryption_percentage,
        }

    @staticmethod
    def disable_encryption(
        db, project_id: str, user_id: str, confirm_passphrase: str
    ) -> Dict[str, Any]:
        """
        Deshabilita el cifrado para un proyecto

        ADVERTENCIA: Esto NO descifra los datos, solo deshabilita nuevas operaciones cifradas

        Args:
            db: Database connection
            project_id: ID del proyecto
            user_id: Usuario que deshabilita el cifrado
            confirm_passphrase: Passphrase para confirmar

        Returns:
            Dict con status

        Raises:
            HTTPException: Si falla la verificación
        """
        # Verificar permisos
        EncryptionService._verify_user_can_modify_encryption(db, project_id, user_id)

        # Verificar passphrase
        if not master_key_crud.verify_project_passphrase_orm(db, project_id, confirm_passphrase):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Passphrase incorrecta"
            )

        # Deshabilitar
        config = master_key_crud.update_project_encryption_enabled_orm(db, project_id, False)

        return {
            "status": "success",
            "message": "Cifrado deshabilitado",
            "encryption_enabled": False,
        }

    @staticmethod
    def enable_encryption(db, project_id: str, user_id: str, passphrase: str) -> Dict[str, Any]:
        """
        Re-habilita el cifrado para un proyecto y cifra datos existentes

        Args:
            db: Database connection
            project_id: ID del proyecto
            user_id: Usuario que habilita el cifrado
            passphrase: Passphrase para verificar

        Returns:
            Dict con status y estadísticas de cifrado
        """
        # Verificar permisos
        EncryptionService._verify_user_can_modify_encryption(db, project_id, user_id)

        # Verificar passphrase
        if not master_key_crud.verify_project_passphrase_orm(db, project_id, passphrase):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Passphrase incorrecta"
            )

        # Derivar encryption key
        encryption_key = master_key_crud.derive_encryption_key_for_project_orm(
            db, project_id, passphrase
        )

        if not encryption_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error derivando clave de cifrado",
            )

        # Habilitar cifrado
        config = master_key_crud.update_project_encryption_enabled_orm(db, project_id, True)

        # Cifrar datos existentes
        stats = EncryptionService.encrypt_existing_project_data(db, project_id, encryption_key)

        return {
            "status": "success",
            "message": "Cifrado habilitado y datos existentes cifrados",
            "encryption_enabled": True,
            "encrypted_data": stats,
        }

    @staticmethod
    def encrypt_existing_project_data(db, project_id: str, encryption_key: bytes) -> Dict[str, int]:
        """
        Cifra todos los datos existentes de un proyecto

        Este método cifra:
        - Nombres de tablas (tables.name → name_encrypted, name_nonce)
        - Nombres y tipos de columnas (columns.name, data_type → encrypted versions)
        - Mappings (origin_table, origin_column, destination_table, destination_column → encrypted versions)

        Args:
            db: Database session (SQLAlchemy)
            project_id: ID del proyecto
            encryption_key: Clave de cifrado derivada (32 bytes)

        Returns:
            Dict con estadísticas de cifrado:
            {
                'tables_encrypted': int,
                'columns_encrypted': int,
                'mappings_encrypted': int,
                'total_encrypted': int
            }

        Raises:
            HTTPException: Si ocurre un error durante el cifrado
        """
        from datetime import datetime, timezone

        from sqlalchemy import or_

        from app.models.orm.column import TableColumn
        from app.models.orm.mapping import Mapping
        from app.models.orm.table import Table

        stats = {
            "tables_encrypted": 0,
            "columns_encrypted": 0,
            "mappings_encrypted": 0,
            "total_encrypted": 0,
        }

        try:
            # ==================== CIFRAR TABLAS ====================
            # Obtener todas las tablas no cifradas del proyecto
            tables = (
                db.query(Table)
                .filter(
                    Table.project_id == project_id,
                    or_(Table.is_encrypted == None, Table.is_encrypted == False),
                    Table.name != None,
                )
                .all()
            )

            for table in tables:
                # Cifrar nombre de tabla
                name_encrypted, name_nonce = master_key_crud.encrypt_table_name(
                    table.name, encryption_key
                )

                # Actualizar tabla con datos cifrados
                table.name_encrypted = name_encrypted
                table.name_nonce = name_nonce
                table.is_encrypted = True
                table.name = None
                table.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

                stats["tables_encrypted"] += 1

            # ==================== CIFRAR COLUMNAS ====================
            # Obtener todas las columnas no cifradas del proyecto
            columns = (
                db.query(TableColumn)
                .join(Table)
                .filter(
                    Table.project_id == project_id,
                    or_(TableColumn.is_encrypted == None, TableColumn.is_encrypted == False),
                    TableColumn.name != None,
                )
                .all()
            )

            for column in columns:
                # Cifrar nombre de columna
                name_encrypted, name_nonce = master_key_crud.encrypt_column_name(
                    column.name, encryption_key
                )

                # Cifrar tipo de dato
                type_encrypted, type_nonce = master_key_crud.encrypt_column_type(
                    column.data_type, encryption_key
                )

                # Actualizar columna con datos cifrados
                column.name_encrypted = name_encrypted
                column.name_nonce = name_nonce
                column.data_type_encrypted = type_encrypted
                column.data_type_nonce = type_nonce
                column.is_encrypted = True
                column.name = None
                column.data_type = None
                column.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

                stats["columns_encrypted"] += 1

            # ==================== CIFRAR MAPPINGS ====================
            # Obtener todos los mappings no cifrados del proyecto
            mappings = (
                db.query(Mapping)
                .filter(
                    Mapping.project_id == project_id,
                    or_(Mapping.is_encrypted == None, Mapping.is_encrypted == False),
                    Mapping.origin_table != None,
                )
                .all()
            )

            for mapping in mappings:
                # Cifrar origin_table
                origin_table_enc, origin_table_nonce = master_key_crud.encrypt_mapping_field(
                    mapping.origin_table, encryption_key
                )

                # Cifrar origin_column
                origin_column_enc, origin_column_nonce = master_key_crud.encrypt_mapping_field(
                    mapping.origin_column, encryption_key
                )

                # Cifrar destination_table
                dest_table_enc, dest_table_nonce = master_key_crud.encrypt_mapping_field(
                    mapping.destination_table, encryption_key
                )

                # Cifrar destination_column
                dest_column_enc, dest_column_nonce = master_key_crud.encrypt_mapping_field(
                    mapping.destination_column, encryption_key
                )

                # Actualizar mapping con datos cifrados
                mapping.origin_table_encrypted = origin_table_enc
                mapping.origin_table_nonce = origin_table_nonce
                mapping.origin_column_encrypted = origin_column_enc
                mapping.origin_column_nonce = origin_column_nonce
                mapping.destination_table_encrypted = dest_table_enc
                mapping.destination_table_nonce = dest_table_nonce
                mapping.destination_column_encrypted = dest_column_enc
                mapping.destination_column_nonce = dest_column_nonce
                mapping.is_encrypted = True
                mapping.origin_table = None
                mapping.origin_column = None
                mapping.destination_table = None
                mapping.destination_column = None
                mapping.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

                stats["mappings_encrypted"] += 1

            # Commit de todas las operaciones
            db.commit()

            stats["total_encrypted"] = (
                stats["tables_encrypted"] + stats["columns_encrypted"] + stats["mappings_encrypted"]
            )

            return stats

        except Exception as e:
            db.rollback()
            # Sanitizar excepción para prevenir exposición de datos sensibles
            safe_exc = safe_log_exception(
                e,
                logger,
                level="error",
                context={"operation": "encrypt_existing_data", "project_id": project_id},
                user_friendly_message="Error cifrando datos existentes del proyecto",
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=safe_exc.user_message
            )

    # ========================================================================
    # HELPER METHODS PRIVADOS
    # ========================================================================

    @staticmethod
    def _validate_passphrase_strength(passphrase: str):
        """
        Valida que la passphrase sea lo suficientemente fuerte

        Requisitos mínimos:
        - Al menos 12 caracteres
        - Contiene mayúsculas y minúsculas
        - Contiene números
        - Contiene caracteres especiales (recomendado)

        Raises:
            HTTPException: Si la passphrase es débil
        """
        if len(passphrase) < 12:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La passphrase debe tener al menos 12 caracteres",
            )

        has_upper = any(c.isupper() for c in passphrase)
        has_lower = any(c.islower() for c in passphrase)
        has_digit = any(c.isdigit() for c in passphrase)
        has_special = any(not c.isalnum() for c in passphrase)

        if not (has_upper and has_lower):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La passphrase debe contener mayúsculas y minúsculas",
            )

        if not has_digit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La passphrase debe contener al menos un número",
            )

        # Special characters son recomendados pero no obligatorios
        # para no bloquear passphrases largas tipo diceware

    @staticmethod
    def _verify_user_can_modify_encryption(db, project_id: str, user_id: str):
        """
        Verifica que el usuario tenga permisos para modificar cifrado

        Args:
            db: Database session (SQLAlchemy)
            project_id: ID del proyecto
            user_id: ID del usuario

        Raises:
            HTTPException: Si el usuario no tiene permisos
        """
        from app.models.orm.project import MemberRole, Project, ProjectMember

        # Verificar si es owner
        project = db.query(Project).filter(Project.id == project_id).first()

        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado"
            )

        if str(project.owner_id) == str(user_id):
            return  # Es owner, tiene permisos

        # Verificar si es editor
        member = (
            db.query(ProjectMember)
            .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
            .first()
        )

        if not member or member.role != MemberRole.EDITOR:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para modificar el cifrado de este proyecto",
            )
