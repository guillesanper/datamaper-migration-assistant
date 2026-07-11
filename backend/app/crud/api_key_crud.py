"""
Operaciones CRUD para la tabla de API keys de usuario.
Maneja generación segura de keys, verificación por hash y revocación.
"""

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.orm.api_key import UserApiKey
from app.models.orm.user import User
from app.utils.orm_helpers import model_to_dict, models_to_dict_list

logger = logging.getLogger(__name__)


# ============================================================================
# FUNCIONES ORM (SQLAlchemy)
# ============================================================================


def create_api_key_orm(
    db: Session,
    user_id: UUID,
    name: str,
    expires_at: Optional[datetime],
) -> Tuple[Dict[str, Any], str]:
    """
    Crea una nueva API key para el usuario (ORM version).

    Genera una key con formato "rlk_" + secrets.token_hex(32) (68 chars).
    Solo guarda el prefijo visible y el hash SHA-256; la raw_key se retorna
    una única vez y nunca se vuelve a almacenar.

    Args:
        db: SQLAlchemy Session
        user_id: UUID del usuario propietario
        name: Nombre descriptivo para identificar la key (ej: "Mi integración")
        expires_at: Fecha de expiración opcional (None = sin expiración)

    Returns:
        Tupla (dict del objeto creado, raw_key) — raw_key solo disponible aquí

    Raises:
        Exception: Si hay un error de DB no recuperable
    """
    try:
        # Generar key segura: "rlk_" + 64 hex chars = 68 chars totales
        raw_key = "rlk_" + secrets.token_hex(32)
        key_prefix = raw_key[4:12]  # 8 chars después del prefijo "rlk_"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        api_key = UserApiKey(
            id=uuid.uuid4(),
            user_id=user_id,
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            expires_at=expires_at,
        )

        db.add(api_key)
        db.commit()
        db.refresh(api_key)

        logger.info(f"API key '{name}' creada para usuario {user_id}")

        return model_to_dict(api_key) or {}, raw_key

    except Exception as e:
        db.rollback()
        logger.error(f"Error al crear API key para usuario {user_id}: {str(e)}")
        raise


def get_user_api_keys_orm(db: Session, user_id: UUID) -> List[Dict[str, Any]]:
    """
    Obtiene todas las API keys del usuario ordenadas por fecha de creación (ORM version).

    El dict resultante NO incluye key_hash para evitar exposición del secreto.

    Args:
        db: SQLAlchemy Session
        user_id: UUID del usuario propietario

    Returns:
        Lista de dicts con los datos de las keys (sin key_hash), ordenada por created_at DESC
    """
    try:
        keys = (
            db.query(UserApiKey)
            .filter(UserApiKey.user_id == user_id)
            .order_by(UserApiKey.created_at.desc())
            .all()
        )

        return models_to_dict_list(keys, exclude=["key_hash"])

    except Exception as e:
        logger.error(f"Error al obtener API keys de usuario {user_id}: {str(e)}")
        return []


def revoke_api_key_orm(db: Session, user_id: UUID, key_id: UUID) -> bool:
    """
    Revoca una API key poniéndola inactiva (soft disable) (ORM version).

    Verifica que la key pertenezca al usuario antes de revocarla.

    Args:
        db: SQLAlchemy Session
        user_id: UUID del usuario propietario (para verificar ownership)
        key_id: UUID de la API key a revocar

    Returns:
        True si se encontró y revocó, False si no existe o no pertenece al usuario
    """
    try:
        key = (
            db.query(UserApiKey)
            .filter(UserApiKey.id == key_id, UserApiKey.user_id == user_id)
            .first()
        )

        if key is None:
            logger.warning(f"API key {key_id} no encontrada para usuario {user_id}")
            return False

        key.is_active = False  # type: ignore[assignment]
        db.commit()

        logger.info(f"API key {key_id} revocada para usuario {user_id}")
        return True

    except Exception as e:
        db.rollback()
        logger.error(f"Error al revocar API key {key_id}: {str(e)}")
        return False


def verify_api_key_orm(db: Session, raw_key: str) -> Optional[Dict[str, Any]]:
    """
    Verifica una API key raw y retorna los datos del usuario asociado (ORM version).

    Pasos de verificación:
    1. Hashea raw_key con SHA-256 y busca en DB por key_hash
    2. Verifica que is_active == True
    3. Verifica que expires_at sea None o una fecha futura
    4. Si válida: actualiza last_used_at y retorna dict del usuario (sin password_hash)

    Args:
        db: SQLAlchemy Session
        raw_key: API key en texto plano (formato "rlk_...")

    Returns:
        Dict del usuario asociado (sin password_hash) si la key es válida, None si no
    """
    try:
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        key = (
            db.query(UserApiKey)
            .filter(
                UserApiKey.key_hash == key_hash,
                UserApiKey.is_active == True,  # noqa: E712
            )
            .first()
        )

        if key is None:
            return None

        # Verificar expiración (expires_at es DateTime(timezone=True) → tz-aware)
        if key.expires_at is not None:
            now = datetime.now(timezone.utc)
            # Normalizar expires_at a tz-aware si la DB devolviera naive
            expires = key.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < now:
                return None

        # Actualizar timestamp de último uso
        key.last_used_at = datetime.now(timezone.utc)  # type: ignore[assignment]
        db.commit()

        # Retornar dict del usuario asociado (no de la key)
        user = (
            db.query(User).filter(User.id == key.user_id, User.is_deleted == False).first()
        )  # noqa: E712
        if user is None:
            return None

        return model_to_dict(user, exclude=["password_hash"])

    except Exception as e:
        db.rollback()
        logger.error(f"Error al verificar API key: {str(e)}")
        return None
