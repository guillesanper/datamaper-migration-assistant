"""
Operaciones CRUD para la tabla de usuarios.
Maneja autenticación, gestión de usuarios y permisos.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from passlib.context import CryptContext
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

# Contexto de hash de passwords (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ============================================================================
# FUNCIONES ORM (SQLAlchemy)
# ============================================================================


def create_user_orm(db, username: str, email: str, password: str) -> Dict[str, Any]:
    """
    Crea un nuevo usuario con password hasheado (ORM version).

    Args:
        db: SQLAlchemy Session
        username: Nombre de usuario único
        email: Email único
        password: Contraseña en texto plano (se hasheará aquí)

    Returns:
        Dict con los datos del usuario creado (sin password_hash)

    Raises:
        IntegrityError: Si username o email ya existen
    """
    from app.models.orm import User

    try:
        # Hashear password
        password_hash = pwd_context.hash(password)

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        new_user = User(
            id=uuid.uuid4(),
            username=username,
            email=email,
            password_hash=password_hash,
            is_verified=False,
            is_deleted=False,
            failed_login_attempts=0,
            created_at=now,
            updated_at=now,
            password_changed_at=now,
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        logger.info(f"Usuario creado: {username} ({email})")

        # NO retornar password_hash
        return {
            "id": str(new_user.id),
            "username": new_user.username,
            "email": new_user.email,
            "is_verified": new_user.is_verified,
            "is_deleted": new_user.is_deleted,
            "created_at": new_user.created_at,
            "updated_at": new_user.updated_at,
        }

    except IntegrityError as e:
        db.rollback()
        logger.error(f"Error de integridad al crear usuario: {str(e)}")
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error al crear usuario: {str(e)}")
        raise


def get_user_by_id_orm(db, user_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene un usuario por su ID (ORM version).

    Args:
        db: SQLAlchemy Session
        user_id: ID del usuario (UUID string)

    Returns:
        Dict con los datos del usuario o None si no existe
    """
    from app.models.orm import User
    from app.utils.orm_helpers import model_to_dict

    try:
        user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()

        if not user:
            return None

        # Excluir password_hash del resultado
        return model_to_dict(user, exclude=["password_hash"])

    except Exception as e:
        logger.error(f"Error al obtener usuario {user_id}: {str(e)}")
        return None


def get_user_by_email_orm(db, email: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene un usuario por su email (ORM version).

    Args:
        db: SQLAlchemy Session
        email: Email del usuario

    Returns:
        Dict con los datos del usuario o None si no existe
    """
    from app.models.orm import User
    from app.utils.orm_helpers import model_to_dict

    try:
        user = db.query(User).filter(User.email == email, User.is_deleted == False).first()

        if not user:
            return None

        # Excluir password_hash del resultado
        return model_to_dict(user, exclude=["password_hash"])

    except Exception as e:
        logger.error(f"Error al obtener usuario por email {email}: {str(e)}")
        return None


def get_user_by_username_orm(db, username: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene un usuario por su username (ORM version).

    Args:
        db: SQLAlchemy Session
        username: Username del usuario

    Returns:
        Dict con los datos del usuario o None si no existe
    """
    from app.models.orm import User
    from app.utils.orm_helpers import model_to_dict

    try:
        user = db.query(User).filter(User.username == username, User.is_deleted == False).first()

        if not user:
            return None

        # Excluir password_hash del resultado
        return model_to_dict(user, exclude=["password_hash"])

    except Exception as e:
        logger.error(f"Error al obtener usuario por username {username}: {str(e)}")
        return None


def update_user_orm(db, user_id: str, update_data: Dict[str, Any]) -> bool:
    """
    Actualiza datos de un usuario (ORM version).

    Args:
        db: SQLAlchemy Session
        user_id: ID del usuario
        update_data: Diccionario con campos a actualizar (username, email, etc.)
                     NO incluir password_hash directamente, usar update_user_password_orm

    Returns:
        True si se actualizó exitosamente, False en caso contrario
    """
    from app.models.orm import User

    try:
        # No permitir actualización de password_hash directamente
        update_data = {k: v for k, v in update_data.items() if k != "password_hash"}

        # Agregar updated_at
        update_data["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None)

        result = (
            db.query(User)
            .filter(User.id == user_id, User.is_deleted == False)
            .update(update_data, synchronize_session=False)
        )

        db.commit()

        if result > 0:
            logger.info(f"Usuario actualizado: {user_id}")
            return True
        else:
            logger.warning(f"Usuario no encontrado para actualizar: {user_id}")
            return False

    except IntegrityError as e:
        db.rollback()
        logger.error(f"Error de integridad al actualizar usuario {user_id}: {str(e)}")
        return False
    except Exception as e:
        db.rollback()
        logger.error(f"Error al actualizar usuario {user_id}: {str(e)}")
        return False


def verify_user_password_orm(db, user_id: str, password: str) -> bool:
    """
    Verifica si un password es correcto para un usuario (ORM version).

    Args:
        db: SQLAlchemy Session
        user_id: ID del usuario
        password: Contraseña en texto plano a verificar

    Returns:
        True si el password es correcto, False en caso contrario
    """
    from app.models.orm import User

    try:
        user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()

        if not user:
            return False

        # Verificar password con bcrypt
        return bool(pwd_context.verify(password, user.password_hash))

    except Exception as e:
        logger.error(f"Error al verificar password de usuario {user_id}: {str(e)}")
        return False


def update_user_password_orm(
    db, user_id: str, new_password: str, old_password: Optional[str] = None
) -> bool:
    """
    Actualiza el password de un usuario (ORM version).

    Args:
        db: SQLAlchemy Session
        user_id: ID del usuario
        new_password: Nueva contraseña en texto plano (se hasheará)
        old_password: Contraseña anterior para validación (opcional)

    Returns:
        True si se actualizó exitosamente, False en caso contrario
    """
    from app.models.orm import User

    try:
        user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()

        if not user:
            logger.warning(f"Usuario no encontrado: {user_id}")
            return False

        # Verificar old_password si se proporciona
        if old_password is not None:
            if not pwd_context.verify(old_password, user.password_hash):
                logger.warning(f"Password anterior incorrecto para usuario {user_id}")
                return False

        # Hashear nueva contraseña
        new_password_hash = pwd_context.hash(new_password)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        user.password_hash = new_password_hash
        user.password_changed_at = now
        user.updated_at = now

        db.commit()

        logger.info(f"Password actualizado para usuario {user_id}")
        return True

    except Exception as e:
        db.rollback()
        logger.error(f"Error al actualizar password de usuario {user_id}: {str(e)}")
        return False


def authenticate_user_orm(db, identifier: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Autentica un usuario con email/username y password (ORM version).

    Args:
        db: SQLAlchemy Session
        identifier: Email o username del usuario
        password: Contraseña en texto plano

    Returns:
        Dict con datos del usuario si la autenticación es exitosa, None en caso contrario
    """
    from app.models.orm import User
    from app.utils.orm_helpers import model_to_dict

    try:
        # Buscar por email o username
        user = (
            db.query(User)
            .filter(
                or_(User.email == identifier, User.username == identifier), User.is_deleted == False
            )
            .first()
        )

        if not user:
            logger.warning(f"Usuario no encontrado: {identifier}")
            return None

        # Verificar si está bloqueado
        if (
            user.locked_until
            and datetime.now(timezone.utc).replace(tzinfo=None) < user.locked_until
        ):
            logger.warning(f"Usuario bloqueado: {identifier}")
            return None

        # Verificar password
        if not pwd_context.verify(password, user.password_hash):
            # Incrementar intentos fallidos
            _handle_failed_login_orm(db, user)
            logger.warning(f"Password incorrecto para usuario: {identifier}")
            return None

        # Verificar si email está verificado
        if not user.is_verified:
            logger.warning(f"Email no verificado para usuario: {identifier}")
            return None

        # Login exitoso - resetear intentos fallidos
        _handle_successful_login_orm(db, user)

        # Excluir password_hash del resultado
        return model_to_dict(user, exclude=["password_hash"])

    except Exception as e:
        logger.error(f"Error al autenticar usuario {identifier}: {str(e)}")
        return None


def _handle_failed_login_orm(db, user):
    """
    Maneja intentos fallidos de login (función auxiliar ORM).
    Incrementa contador y bloquea cuenta si es necesario.
    """
    from app.config.security import security_settings

    try:
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1

        # Bloquear cuenta si supera el límite
        if user.failed_login_attempts >= security_settings.MAX_FAILED_LOGIN_ATTEMPTS:
            user.locked_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
                seconds=security_settings.ACCOUNT_LOCKOUT_DURATION
            )
            logger.warning(f"Cuenta bloqueada por intentos fallidos: {user.username}")

        db.commit()

    except Exception as e:
        db.rollback()
        logger.error(f"Error al manejar login fallido: {str(e)}")


def _handle_successful_login_orm(db, user):
    """
    Maneja login exitoso (función auxiliar ORM).
    Resetea intentos fallidos y actualiza última actividad.
    """
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        user.updated_at = now

        db.commit()

        logger.info(f"Login exitoso: {user.username}")

    except Exception as e:
        db.rollback()
        logger.error(f"Error al manejar login exitoso: {str(e)}")


def verify_user_email_orm(db, user_id: str) -> bool:
    """
    Marca el email de un usuario como verificado (ORM version).

    Args:
        db: SQLAlchemy Session
        user_id: ID del usuario

    Returns:
        True si se verificó exitosamente, False en caso contrario
    """
    from app.models.orm import User

    try:
        result = (
            db.query(User)
            .filter(User.id == user_id, User.is_deleted == False)
            .update(
                {
                    "is_verified": True,
                    "updated_at": datetime.now(timezone.utc).replace(tzinfo=None),
                },
                synchronize_session=False,
            )
        )

        db.commit()

        if result > 0:
            logger.info(f"Email verificado para usuario {user_id}")
            return True
        else:
            logger.warning(f"Usuario no encontrado para verificar: {user_id}")
            return False

    except Exception as e:
        db.rollback()
        logger.error(f"Error al verificar email de usuario {user_id}: {str(e)}")
        return False


def request_email_verification_orm(db, user_id: str) -> bool:
    """
    Solicita verificación de email para un usuario (ORM version).
    Nota: Esta función solo verifica que el usuario existe.
    El envío del email debe manejarse en una capa superior.

    Args:
        db: SQLAlchemy Session
        user_id: ID del usuario

    Returns:
        True si el usuario existe y puede recibir verificación, False en caso contrario
    """
    from app.models.orm import User

    try:
        user = (
            db.query(User)
            .filter(User.id == user_id, User.is_deleted == False, User.is_verified == False)
            .first()
        )

        if user:
            logger.info(f"Solicitud de verificación de email para usuario {user_id}")
            return True
        else:
            logger.warning(f"Usuario no válido para verificación: {user_id}")
            return False

    except Exception as e:
        logger.error(f"Error al solicitar verificación de email: {str(e)}")
        return False


def deactivate_user_orm(db, user_id: str) -> bool:
    """
    Desactiva una cuenta de usuario (soft delete) (ORM version).

    Args:
        db: SQLAlchemy Session
        user_id: ID del usuario

    Returns:
        True si se desactivó exitosamente, False en caso contrario
    """
    from app.models.orm import User

    try:
        result = (
            db.query(User)
            .filter(User.id == user_id, User.is_deleted == False)
            .update(
                {"is_deleted": True, "updated_at": datetime.now(timezone.utc).replace(tzinfo=None)},
                synchronize_session=False,
            )
        )

        db.commit()

        if result > 0:
            logger.info(f"Usuario desactivado: {user_id}")
            return True
        else:
            logger.warning(f"Usuario no encontrado para desactivar: {user_id}")
            return False

    except Exception as e:
        db.rollback()
        logger.error(f"Error al desactivar usuario {user_id}: {str(e)}")
        return False


def activate_user_orm(db, user_id: str) -> bool:
    """
    Reactiva una cuenta de usuario desactivada (ORM version).

    Args:
        db: SQLAlchemy Session
        user_id: ID del usuario

    Returns:
        True si se reactivó exitosamente, False en caso contrario
    """
    from app.models.orm import User

    try:
        result = (
            db.query(User)
            .filter(User.id == user_id, User.is_deleted == True)
            .update(
                {
                    "is_deleted": False,
                    "updated_at": datetime.now(timezone.utc).replace(tzinfo=None),
                },
                synchronize_session=False,
            )
        )

        db.commit()

        if result > 0:
            logger.info(f"Usuario reactivado: {user_id}")
            return True
        else:
            logger.warning(f"Usuario no encontrado para reactivar: {user_id}")
            return False

    except Exception as e:
        db.rollback()
        logger.error(f"Error al reactivar usuario {user_id}: {str(e)}")
        return False


def search_users_orm(
    db, search_term: str, limit: int = 50, offset: int = 0, include_deleted: bool = False
) -> List[Dict[str, Any]]:
    """
    Busca usuarios por username o email (ORM version).

    Args:
        db: SQLAlchemy Session
        search_term: Término de búsqueda (parcial, case-insensitive)
        limit: Número máximo de resultados
        offset: Número de resultados a saltar (paginación)
        include_deleted: Si True, incluye usuarios desactivados

    Returns:
        Lista de diccionarios con datos de usuarios encontrados
    """
    from app.models.orm import User
    from app.utils.orm_helpers import models_to_dict_list

    try:
        query = db.query(User)

        # Filtrar por término de búsqueda
        search_filter = or_(
            User.username.ilike(f"%{search_term}%"), User.email.ilike(f"%{search_term}%")
        )
        query = query.filter(search_filter)

        # Filtrar usuarios eliminados si es necesario
        if not include_deleted:
            query = query.filter(User.is_deleted == False)

        # Ordenar y paginar
        users = query.order_by(User.created_at.desc()).limit(limit).offset(offset).all()

        # Convertir a diccionarios excluyendo password_hash
        return [
            {k: v for k, v in user_dict.items() if k != "password_hash"}
            for user_dict in models_to_dict_list(users)
        ]

    except Exception as e:
        logger.error(f"Error al buscar usuarios: {str(e)}")
        return []


def get_all_users_paginated_orm(
    db, limit: int = 50, offset: int = 0, include_deleted: bool = False
) -> Dict[str, Any]:
    """
    Obtiene todos los usuarios con paginación (ORM version).

    Args:
        db: SQLAlchemy Session
        limit: Número máximo de resultados por página
        offset: Número de resultados a saltar
        include_deleted: Si True, incluye usuarios desactivados

    Returns:
        Dict con 'users' (lista de usuarios) y 'total' (total de usuarios)
    """
    from app.models.orm import User
    from app.utils.orm_helpers import models_to_dict_list

    try:
        query = db.query(User)

        # Filtrar usuarios eliminados si es necesario
        if not include_deleted:
            query = query.filter(User.is_deleted == False)

        # Contar total
        total = query.count()

        # Obtener usuarios paginados
        users = query.order_by(User.created_at.desc()).limit(limit).offset(offset).all()

        # Convertir a diccionarios excluyendo password_hash
        users_list = [
            {k: v for k, v in user_dict.items() if k != "password_hash"}
            for user_dict in models_to_dict_list(users)
        ]

        return {"users": users_list, "total": total, "limit": limit, "offset": offset}

    except Exception as e:
        logger.error(f"Error al obtener usuarios paginados: {str(e)}")
        return {"users": [], "total": 0, "limit": limit, "offset": offset}


def get_user_stats_orm(db, user_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene estadísticas de un usuario (ORM version).

    Args:
        db: SQLAlchemy Session
        user_id: ID del usuario

    Returns:
        Dict con estadísticas del usuario o None si no existe
    """
    from app.models.orm import Project, Subscription, User

    try:
        user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()

        if not user:
            return None

        # Contar proyectos del usuario
        projects_count = db.query(Project).filter(Project.owner_id == user_id).count()

        # Contar suscripciones activas
        active_subscriptions = (
            db.query(Subscription)
            .filter(
                Subscription.user_id == user_id, Subscription.status.in_(["active", "trialing"])
            )
            .count()
        )

        return {
            "user_id": str(user.id),
            "username": user.username,
            "email": user.email,
            "is_verified": user.is_verified,
            "created_at": user.created_at,
            "last_login_at": user.last_login_at,
            "projects_count": projects_count,
            "active_subscriptions": active_subscriptions,
            "failed_login_attempts": user.failed_login_attempts,
            "is_locked": user.locked_until is not None
            and user.locked_until > datetime.now(timezone.utc).replace(tzinfo=None),
        }

    except Exception as e:
        logger.error(f"Error al obtener estadísticas de usuario {user_id}: {str(e)}")
        return None
