# app/services/auth_service.py
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from passlib.context import CryptContext
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud import email_otp_crud
from app.utils.email_verification import (
    create_welcome_notification,
    deliver_account_exists_email,
    send_verification_code,
)
from app.utils.security import SecurityUtils

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class DatabaseError(Exception):
    """Error personalizado para problemas de base de datos"""

    pass


class AuthenticationError(Exception):
    """Error personalizado para problemas de autenticación"""

    pass


class UsernameTakenError(AuthenticationError):
    """El username pertenece a otra cuenta (viva o borrada): único 409 explícito de register"""

    pass


# Qué hizo create_user (`RegistrationResult.outcome`); solo va al log de seguridad. Los motivos
# de las ramas «existente» coinciden con los de resend_code_ignored
REGISTRATION_CREATED = "account_created"
REGISTRATION_EXISTING_VERIFIED = "account_already_verified"
REGISTRATION_EXISTING_UNVERIFIED = "account_unverified_reissued"
REGISTRATION_EXISTING_DELETED = "account_deleted"


class RegistrationResult(dict):
    """
    Datos del 201 de register (user_id, username, email) y qué se hizo de verdad.

    Es un dict para que llegue a la respuesta tal cual y los llamadores de siempre no cambien.
    `outcome` y `account_id` (la cuenta real, que en las ramas «existente» no es `user_id`) son
    atributos, fuera de la respuesta: solo sirven para el log de seguridad.
    """

    outcome: str = REGISTRATION_CREATED
    account_id: Optional[str] = None


class AuthService:
    """Servicio de autenticación - Contiene toda la lógica de negocio"""

    def __init__(self, db: Session):
        self.db = db

    def validate_password_strength(self, password: str) -> None:
        """Valida la fortaleza de la contraseña"""
        validation = SecurityUtils.validate_password_strength(password)
        if not validation["is_valid"]:
            raise ValueError("; ".join(validation["errors"]))

    def _find_existing_account(self, username: str, email: str):
        """
        Cuenta que ya ocupa el email o el username (incluidas las borradas) o None.

        Las restricciones únicas de users cubren las filas borradas: sin mirarlas, un email o un
        username de una cuenta borrada pasaría la consulta y saltaría en el INSERT. Si el
        username es de OTRA cuenta que la del email (o el email no existe), UsernameTakenError:
        con independencia de que el email exista, para que elegir un username ocupado no sirva
        para enumerar emails.
        """
        from app.models.orm import User

        rows = self.db.query(User).filter(or_(User.email == email, User.username == username)).all()
        by_email = next((u for u in rows if u.email == email), None)
        by_username = next((u for u in rows if u.username == username), None)

        if by_username is not None and (by_email is None or by_email.id != by_username.id):
            raise UsernameTakenError("El nombre de usuario ya está en uso")
        return by_email

    def _answer_for_existing_account(
        self,
        account,
        username: str,
        email: str,
        deliver: Optional[Callable[[str, str], None]],
        notify_existing: Optional[Callable[[str], None]],
    ) -> RegistrationResult:
        """
        Resultado de register cuando el email ya tiene cuenta: igual que un alta nueva.

        No se crea nada ni se toca la contraseña ni el username guardados. Verificada: aviso
        «ya tienes una cuenta» (sin código) y bcrypt simulado en lugar del del OTP. Sin
        verificar: código nuevo (invalida el anterior y repara una cuenta que se quedó sin
        código). Borrada: no se envía nada. Los datos devueltos son los de la petición, con un
        user_id aleatorio: ninguno revela la cuenta real.
        """
        result = RegistrationResult(user_id=str(uuid.uuid4()), username=username, email=email)
        result.account_id = str(account.id)

        if account.is_deleted:
            email_otp_crud.simulate_otp_check()
            result.outcome = REGISTRATION_EXISTING_DELETED
        elif account.is_verified:
            email_otp_crud.simulate_otp_check()
            (notify_existing or deliver_account_exists_email)(email)
            result.outcome = REGISTRATION_EXISTING_VERIFIED
        else:
            send_verification_code(self.db, email, str(account.id), deliver=deliver)
            result.outcome = REGISTRATION_EXISTING_UNVERIFIED
        return result

    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        deliver: Optional[Callable[[str, str], None]] = None,
        notify_existing: Optional[Callable[[str], None]] = None,
    ) -> RegistrationResult:
        """
        Crea un nuevo usuario en la base de datos, o responde como si lo creara si el email ya
        tiene cuenta (ver `_answer_for_existing_account`).

        El OTP se crea aquí y se entrega con `deliver(email, código)`; sin `deliver` se envía por
        correo en el acto. El aviso «ya tienes una cuenta» se entrega con `notify_existing(email)`
        con la misma regla. Un endpoint async inyecta funciones que lo encolan en segundo plano
        (el servicio no depende de FastAPI). El resultado nunca incluye el código.

        Raises:
            UsernameTakenError: el username es de otra cuenta (409 explícito).
        """
        from app.models.orm import User

        # Validar contraseña
        self.validate_password_strength(password)

        # Sanitizar inputs
        username = SecurityUtils.sanitize_input(username)
        email = SecurityUtils.sanitize_email(email)

        # Hash de contraseña (antes de consultar: todas las ramas pagan un bcrypt de contraseña)
        hashed_password = pwd_context.hash(password)
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        try:
            existing = self._find_existing_account(username, email)

            if existing is None:
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
                except IntegrityError:
                    # Carrera: otra petición dio de alta el email o el username entre la
                    # consulta previa y el INSERT. Se resuelve con lo que hay ahora, igual que
                    # en el camino lento (no depende del nombre de la restricción)
                    self.db.rollback()
                    existing = self._find_existing_account(username, email)
                    if existing is None:
                        raise AuthenticationError("El usuario o email ya existe")

            if existing is not None:
                return self._answer_for_existing_account(
                    existing, username, email, deliver, notify_existing
                )

            # Enviar código de verificación (usa CRUD ORM internamente)
            send_verification_code(self.db, email, user_id, deliver=deliver)

            result = RegistrationResult(
                user_id=str(new_user.id), username=new_user.username, email=new_user.email
            )
            result.account_id = str(new_user.id)
            return result

        except AuthenticationError:
            self.db.rollback()
            raise
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
                raise AuthenticationError("Credenciales inválidas")

            # Verificar bloqueo (locked_until es timestamptz: llega aware; se normaliza por si no)
            now = datetime.now(timezone.utc)
            locked_until = user.locked_until
            if locked_until is not None and locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=timezone.utc)
            if locked_until and now < locked_until:
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
            lockout_until = datetime.now(timezone.utc) + timedelta(
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
        """
        Verifica el código de email.

        El texto de cada AuthenticationError es el motivo real, para el log de seguridad: el
        endpoint responde siempre lo mismo (no revela si la cuenta existe o ya está verificada).
        """
        from app.crud import email_otp_crud
        from app.models.orm import User

        email = SecurityUtils.sanitize_email(email)
        code = SecurityUtils.sanitize_input(code)

        try:
            # Obtener usuario
            user = self.db.query(User).filter(User.email == email, User.is_deleted == False).first()

            # Sin cuenta o ya verificada no hay OTP que comprobar: se gasta el mismo bcrypt
            if not user:
                email_otp_crud.simulate_otp_check()
                raise AuthenticationError("Usuario no encontrado")

            if user.is_verified:
                email_otp_crud.simulate_otp_check()
                raise AuthenticationError("Email ya verificado")

            # Verificar OTP usando CRUD ORM (usa bcrypt internamente)
            if not email_otp_crud.verify_otp_orm(self.db, str(user.id), code):
                raise AuthenticationError("Código inválido o expirado")

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
        """
        Resetea la contraseña usando un código OTP y revoca las sesiones abiertas del usuario.

        Igual que verify_email_code, el texto de AuthenticationError es el motivo real (para el
        log de seguridad); el endpoint no lo expone.
        """
        from app.crud import email_otp_crud, session_crud
        from app.models.orm import User

        # Validar nueva contraseña
        self.validate_password_strength(new_password)

        email = SecurityUtils.sanitize_email(email)
        code = SecurityUtils.sanitize_input(code)

        try:
            # Verificar usuario
            user = self.db.query(User).filter(User.email == email, User.is_deleted == False).first()

            if not user:
                email_otp_crud.simulate_otp_check()
                raise AuthenticationError("Usuario no encontrado")

            # Verificar código OTP usando CRUD ORM
            if not email_otp_crud.verify_otp_orm(self.db, str(user.id), code):
                raise AuthenticationError("Código inválido o expirado")

            # Actualizar contraseña
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            user.password_hash = pwd_context.hash(new_password)
            user.password_changed_at = now  # type: ignore[assignment]
            user.updated_at = now  # type: ignore[assignment]
            user.failed_login_attempts = 0  # type: ignore[assignment]
            user.locked_until = None  # type: ignore[assignment]

            self.db.commit()

            # Una contraseña nueva invalida las sesiones anteriores (cierra a quien la conociera)
            session_crud.revoke_all_user_sessions_orm(
                self.db, user_id=str(user.id), reason="password_reset"
            )

        except AuthenticationError:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Error al resetear contraseña: {str(e)}")
