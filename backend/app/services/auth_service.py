# app/services/auth_service.py
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from passlib.context import CryptContext
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.utils.email_verification import create_welcome_notification, send_verification_code
from app.utils.security import SecurityUtils

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Mensaje único para usuario inexistente, ya verificado o código incorrecto: distinguirlos
# permitía saber qué emails tienen cuenta
INVALID_CODE_MESSAGE = "Código inválido o expirado"

_dummy_password_hash: Optional[str] = None


def _verify_against_dummy_hash(password: str) -> None:
    """Mismo coste bcrypt cuando el usuario no existe (evita enumerar por tiempo)."""
    global _dummy_password_hash
    if _dummy_password_hash is None:
        _dummy_password_hash = pwd_context.hash("datamap-timing-equalizer")
    pwd_context.verify(password, _dummy_password_hash)


class DatabaseError(Exception):
    """Error personalizado para problemas de base de datos"""

    pass


class AuthenticationError(Exception):
    """Error personalizado para problemas de autenticación"""

    pass


class AuthService:
    """Servicio de autenticación - Contiene toda la lógica de negocio"""

    def __init__(self, db: Session):
        self.db = db

    def validate_password_strength(self, password: str) -> None:
        """Valida la fortaleza de la contraseña"""
        validation = SecurityUtils.validate_password_strength(password)
        if not validation["is_valid"]:
            raise ValueError("; ".join(validation["errors"]))

    def create_user(self, username: str, email: str, password: str) -> Dict[str, Any]:
        """Crea un nuevo usuario en la base de datos"""
        from app.models.orm import User

        # Validar contraseña
        self.validate_password_strength(password)

        # Sanitizar inputs
        username = SecurityUtils.sanitize_input(username)
        email = SecurityUtils.sanitize_email(email)

        # Hash de contraseña
        hashed_password = pwd_context.hash(password)
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        try:
            # Crear usuario usando SQLAlchemy ORM
            new_user = User(
                id=user_id,
                username=username,
                email=email,
                password_hash=hashed_password,
                created_at=now,
                updated_at=now,
                is_verified=False,
                is_deleted=False,
                failed_login_attempts=0,
            )

            self.db.add(new_user)
            self.db.commit()
            self.db.refresh(new_user)

            # Enviar código de verificación (usa CRUD ORM internamente)
            send_verification_code(self.db, email, user_id)

            return {
                "user_id": str(new_user.id),
                "username": new_user.username,
                "email": new_user.email,
            }

        except IntegrityError:
            self.db.rollback()
            raise AuthenticationError("El usuario o email ya existe")
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Error al crear usuario: {str(e)}")

    def authenticate_user(self, identifier: str, password: str, client_ip: str) -> Dict[str, Any]:
        """Autentica un usuario y retorna sus datos"""
        from app.models.orm import User

        identifier = SecurityUtils.sanitize_input(identifier)

        try:
            # Obtener usuario usando SQLAlchemy ORM
            user = (
                self.db.query(User)
                .filter(
                    or_(User.username == identifier, User.email == identifier),
                    User.is_deleted == False,
                )
                .first()
            )

            # Verificar si existe
            if not user:
                _verify_against_dummy_hash(password)
                raise AuthenticationError("Credenciales inválidas")

            # Verificar bloqueo
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            if user.locked_until and now < user.locked_until:
                raise AuthenticationError("Cuenta bloqueada temporalmente")

            # Verificar contraseña
            if not pwd_context.verify(password, user.password_hash):
                self._handle_failed_login(user)
                raise AuthenticationError("Credenciales inválidas")

            # Verificar email verificado
            if not user.is_verified:
                raise AuthenticationError("Debes verificar tu email primero")

            # Login exitoso - actualizar información
            self._handle_successful_login(user, client_ip)

            return {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "is_verified": user.is_verified,
                "created_at": user.created_at,
            }
        except AuthenticationError:
            raise
        except Exception as e:
            raise DatabaseError(f"Error al autenticar usuario: {str(e)}")

    def _handle_failed_login(self, user) -> None:
        """Maneja intentos fallidos de login"""
        from app.config.security import security_settings

        failed_attempts = (user.failed_login_attempts or 0) + 1

        if failed_attempts >= security_settings.MAX_FAILED_LOGIN_ATTEMPTS:
            lockout_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
                seconds=security_settings.ACCOUNT_LOCKOUT_DURATION
            )
            user.locked_until = lockout_until

        user.failed_login_attempts = failed_attempts
        self.db.commit()

    def _handle_successful_login(self, user, client_ip: str) -> None:
        """Maneja login exitoso"""
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        user.updated_at = now
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        user.last_login_ip = client_ip

        self.db.commit()

    def verify_email_code(self, email: str, code: str) -> Dict[str, Any]:
        """Verifica el código de email"""
        from app.crud import email_otp_crud
        from app.models.orm import User

        email = SecurityUtils.sanitize_email(email)
        code = SecurityUtils.sanitize_input(code)

        try:
            # Obtener usuario
            user = self.db.query(User).filter(User.email == email, User.is_deleted == False).first()

            if not user or user.is_verified:
                raise AuthenticationError(INVALID_CODE_MESSAGE)

            # Verificar OTP usando CRUD ORM (usa bcrypt internamente)
            if not email_otp_crud.verify_otp_orm(self.db, str(user.id), code):
                raise AuthenticationError(INVALID_CODE_MESSAGE)

            # Marcar como verificado
            user.is_verified = True  # type: ignore[assignment]
            user.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)  # type: ignore[assignment]
            self.db.commit()

            return {"user_id": str(user.id), "username": user.username}
        except AuthenticationError:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Error al verificar código: {str(e)}")

    def reset_password(self, email: str, code: str, new_password: str) -> None:
        """Resetea la contraseña usando un código OTP"""
        from app.crud import email_otp_crud
        from app.models.orm import User

        # Validar nueva contraseña
        self.validate_password_strength(new_password)

        email = SecurityUtils.sanitize_email(email)
        code = SecurityUtils.sanitize_input(code)

        try:
            # Verificar usuario
            user = self.db.query(User).filter(User.email == email, User.is_deleted == False).first()

            if not user:
                raise AuthenticationError(INVALID_CODE_MESSAGE)

            # Verificar código OTP usando CRUD ORM
            if not email_otp_crud.verify_otp_orm(self.db, str(user.id), code):
                raise AuthenticationError(INVALID_CODE_MESSAGE)

            # Actualizar contraseña
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            user.password_hash = pwd_context.hash(new_password)
            user.updated_at = now  # type: ignore[assignment]
            user.failed_login_attempts = 0  # type: ignore[assignment]
            user.locked_until = None  # type: ignore[assignment]

            self.db.commit()

        except AuthenticationError:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Error al resetear contraseña: {str(e)}")

        # Quien tuviera una sesión abierta (p. ej. quien robó la contraseña) la pierde
        revoke_user_sessions(self.db, str(user.id), reason="password_reset")


def revoke_user_sessions(
    db: Session, user_id: str, reason: str, except_token: Optional[str] = None
) -> int:
    """
    Revoca las sesiones de login del usuario y sus sesiones de cifrado (claves en Redis).

    Raises:
        DatabaseError: Si no se pudieron revocar (la contraseña ya está cambiada: mejor
            avisar que dejar sesiones vivas en silencio)
    """
    import logging

    from app.models.orm import UserSession

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        query = db.query(UserSession).filter(
            UserSession.user_id == user_id, UserSession.is_revoked == False  # noqa: E712
        )
        if except_token:
            query = query.filter(UserSession.session_token != except_token)
        revoked = query.update(
            {"is_revoked": True, "revoked_at": now, "revoked_reason": reason},
            synchronize_session=False,
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise DatabaseError(f"Error al revocar sesiones: {str(e)}")

    if not except_token:
        try:
            from app.utils.redis_session_cache import get_encryption_session_cache

            get_encryption_session_cache().invalidate_user_sessions(user_id)
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"Could not invalidate encryption sessions for user {user_id}: {e}"
            )

    return int(revoked)
