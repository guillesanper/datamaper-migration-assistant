"""
Operaciones CRUD para la tabla de preferencias de usuario.
Maneja creación lazy (get-or-create) y actualización parcial con merge de JSONB.
"""

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ============================================================================
# FUNCIONES ORM (SQLAlchemy)
# ============================================================================


def get_or_create_preferences_orm(db: Session, user_id: UUID) -> Dict[str, Any]:
    """
    Obtiene las preferencias de un usuario, creándolas si no existen (ORM version).

    Crea una fila con todos los valores por defecto del modelo si es la primera
    vez que se accede a las preferencias del usuario.

    Args:
        db: SQLAlchemy Session
        user_id: UUID del usuario propietario

    Returns:
        Dict con todos los campos de UserPreferences (user_id como str)

    Raises:
        Exception: Si hay un error de DB no recuperable
    """
    from app.models.orm.user_preferences import UserPreferences
    from app.utils.orm_helpers import model_to_dict

    try:
        prefs = db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()

        if prefs is None:
            prefs = UserPreferences(user_id=user_id)
            db.add(prefs)
            db.commit()
            db.refresh(prefs)
            logger.info(f"Preferencias creadas para usuario {user_id}")
        else:
            logger.debug(f"Preferencias encontradas para usuario {user_id}")

        return model_to_dict(prefs) or {}

    except Exception as e:
        db.rollback()
        logger.error(f"Error al obtener/crear preferencias para usuario {user_id}: {str(e)}")
        raise


def update_preferences_orm(
    db: Session, user_id: UUID, update_data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Actualiza los campos especificados en las preferencias del usuario (ORM version).

    Para los campos JSONB (email_notifications, in_app_notifications) realiza un
    merge del dict existente con el nuevo, sin reemplazar claves no mencionadas.
    Para el resto de campos, asigna directamente.

    Args:
        db: SQLAlchemy Session
        user_id: UUID del usuario propietario
        update_data: Diccionario con los campos a actualizar

    Returns:
        Dict actualizado con todos los campos, o None si el usuario no tiene preferencias
    """
    from app.models.orm.user_preferences import UserPreferences
    from app.utils.orm_helpers import model_to_dict

    try:
        prefs = db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()

        if prefs is None:
            logger.warning(f"Preferencias no encontradas para usuario {user_id}")
            return None

        for key, value in update_data.items():
            # Proteger la PK
            if key == "user_id":
                continue

            if key in ("email_notifications", "in_app_notifications"):
                # Merge del dict existente con el nuevo (preserva claves no mencionadas)
                existing: Dict[str, Any] = getattr(prefs, key) or {}
                merged = {**existing, **value}
                setattr(prefs, key, merged)  # type: ignore[assignment]
            elif hasattr(prefs, key):
                setattr(prefs, key, value)  # type: ignore[assignment]

        db.commit()
        db.refresh(prefs)

        logger.info(f"Preferencias actualizadas para usuario {user_id}")
        return model_to_dict(prefs)

    except Exception as e:
        db.rollback()
        logger.error(f"Error al actualizar preferencias para usuario {user_id}: {str(e)}")
        return None
