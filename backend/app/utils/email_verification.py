import logging
import os
import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.config.security import security_settings

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool) -> bool:
    """
    Lee una variable de entorno booleana sin distinguir mayúsculas ni espacios.

    1/true/yes/on -> True; 0/false/no/off -> False. Si la variable no existe, está vacía
    o tiene un valor no reconocido se devuelve `default`.
    """
    value = os.getenv(name, "").strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    return default


# Variables de entorno
EMAIL_FROM = os.getenv("EMAIL_FROM")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
# STARTTLS activo salvo que se desactive explícitamente (un valor erróneo no lo desactiva)
SMTP_USE_STARTTLS = _env_flag("SMTP_USE_STARTTLS", default=True)
# Tiempo máximo (s) de las operaciones SMTP: evita que una conexión colgada bloquee el registro
SMTP_TIMEOUT_SECONDS = 10


def generate_numeric_code():
    """Genera un código OTP seguro de 8 caracteres alfanuméricos"""
    from app.utils.security import SecurityUtils

    return SecurityUtils.generate_secure_otp()


def _smtp_is_configured() -> bool:
    """
    Indica si hay configuración SMTP suficiente para intentar el envío.

    Requiere servidor y remitente. Las credenciales son opcionales (servidores de desarrollo
    como Mailpit), pero nunca a medias: usuario y contraseña deben estar ambos o ninguno.
    """
    return bool(SMTP_SERVER and EMAIL_FROM) and bool(SMTP_USER) == bool(SMTP_PASS)


def _log_code_fallback_allowed() -> bool:
    """
    Indica si, cuando el envío falla o se simula, el código puede imprimirse en la salida.

    Solo en desarrollo (permite probar el registro sin SMTP). Se lee en cada llamada, no al
    importar, para que los tests y el entorno puedan cambiarlo.
    """
    return bool(security_settings.DEVELOPMENT_MODE)


def _mask_email(email: str) -> str:
    """Enmascara el usuario de un email para el log conservando el dominio (u***@dominio)"""
    local, separator, domain = email.partition("@")
    if not separator:
        return "***"
    return f"{local[:1]}***@{domain}"


def _redact_delivery_error(error: Exception, to_email: str, code: str) -> str:
    """Texto del error de envío sin el código ni el destinatario (un servidor puede devolverlos)"""
    detail = str(error)
    if code:
        detail = detail.replace(code, "***")
    if to_email:
        detail = detail.replace(to_email, _mask_email(to_email))
    return detail


def _build_verification_message(to_email: str, code: str) -> EmailMessage:
    """Construye el correo con el código de verificación (válido 10 minutos)"""
    message = EmailMessage()
    message["Subject"] = "Tu código de verificación"
    message["From"] = EMAIL_FROM
    message["To"] = to_email
    message.set_content(
        f"Tu código de verificación es: {code}\n" f"Este código expirará en 10 minutos."
    )
    return message


def _send_message(message: EmailMessage) -> None:
    """
    Envía el mensaje por SMTP según la configuración del módulo.

    STARTTLS solo si SMTP_USE_STARTTLS y login solo si hay usuario y contraseña.
    """
    if not SMTP_SERVER:
        raise RuntimeError("SMTP_SERVER no configurado")

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as server:
        server.ehlo()  # Identificarse con el servidor
        if SMTP_USE_STARTTLS:
            server.starttls()  # Iniciar TLS
            server.ehlo()  # Identificarse nuevamente después de TLS
        if SMTP_USER and SMTP_PASS:
            server.login(SMTP_USER, SMTP_PASS)
        server.send_message(message)


def send_verification_code(db: Session, to_email: str, user_id: str):
    """
    Genera y guarda un OTP para el usuario y lo envía por correo.

    Compatibilidad: con usuario y contraseña el comportamiento es el de siempre (STARTTLS +
    login). Antes, con servidor y remitente pero sin usuario ni contraseña, se simulaba el
    envío; ahora se intenta enviar sin autenticar (con STARTTLS salvo que SMTP_USE_STARTTLS lo
    desactive). Con credenciales a medias o sin servidor/remitente sigue simulándose el envío.

    Si el envío falla o se simula, el código se imprime solo en desarrollo
    (`_log_code_fallback_allowed`); fuera de él el fallo se registra con logging, sin el código
    y con el email enmascarado. El OTP guardado en BD no depende de que el correo salga.
    """
    from app.crud import email_otp_crud

    code = generate_numeric_code()

    # Crear OTP usando CRUD (cifra automáticamente con bcrypt y hace UPSERT)
    email_otp_crud.create_otp_orm(db, user_id=user_id, otp_code=code, expires_in_minutes=10)

    # Enviar el código por correo
    try:
        # Verificar que las variables de entorno estén configuradas
        if not _smtp_is_configured():
            if _log_code_fallback_allowed():
                print(" Configuración SMTP incompleta, simulando envío de email")
                print(f" Código de verificación para {to_email}: {code}")
            else:
                logger.error(
                    "Configuración SMTP incompleta: no se entregó el código de verificación a %s",
                    _mask_email(to_email),
                )
            return  # Simular envío exitoso (el código solo se imprime en desarrollo)

        _send_message(_build_verification_message(to_email, code))

        print(f" Email de verificación enviado exitosamente a {to_email}")

    except Exception as e:
        if _log_code_fallback_allowed():
            print(f"❌ Error enviando email: {e}")
            print(f"📧 Código de verificación para {to_email}: {code}")
        else:
            logger.error(
                "Error enviando el email de verificación a %s: %s",
                _mask_email(to_email),
                _redact_delivery_error(e, to_email, code),
            )
        # No lanzar excepción para no interrumpir el registro
        # En producción, podrías querer manejar esto de manera diferente


def create_welcome_notification(db: Session, user_id: str, _):
    """
    Inserta una notificación de bienvenida para el usuario dado.
    Usa ORM para insertar la notificación.
    """
    from app.crud import notification_crud

    notification_crud.create_notification_orm(
        db,
        recipient_id=user_id,
        notification_kind="system",
        title="¡Bienvenido!",
        body="Gracias por registrarte en DataMap Assistant. Ahora que ya tienes tu cuenta, podrás crear tus proyectos, importar las tablas desde tus bases de datos y empezar a darles vida creando relaciones. Simplemente une las flechas entre las tablas para visualizar cómo se conectan tus datos.",
    )
