import os
import random
import smtplib
import uuid
from datetime import datetime, timedelta
from email.message import EmailMessage

from sqlalchemy.orm import Session

# Variables de entorno
EMAIL_FROM = os.getenv("EMAIL_FROM")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")


def generate_numeric_code():
    """Genera un código OTP seguro de 8 caracteres alfanuméricos"""
    from app.utils.security import SecurityUtils

    return SecurityUtils.generate_secure_otp()


def send_verification_code(db: Session, to_email: str, user_id: str):
    from app.crud import email_otp_crud

    code = generate_numeric_code()

    # Crear OTP usando CRUD (cifra automáticamente con bcrypt y hace UPSERT)
    email_otp_crud.create_otp_orm(db, user_id=user_id, otp_code=code, expires_in_minutes=10)

    # Enviar el código por correo
    try:
        message = EmailMessage()
        message["Subject"] = "Tu código de verificación"
        message["From"] = EMAIL_FROM
        message["To"] = to_email
        message.set_content(
            f"Tu código de verificación es: {code}\n" f"Este código expirará en 10 minutos."
        )

        # Verificar que las variables de entorno estén configuradas
        if not all([SMTP_SERVER, SMTP_USER, SMTP_PASS, EMAIL_FROM]):
            print(" Configuración SMTP incompleta, simulando envío de email")
            print(f" Código de verificación para {to_email}: {code}")
            return  # Simular envío exitoso en desarrollo

        assert SMTP_SERVER is not None
        assert SMTP_USER is not None
        assert SMTP_PASS is not None

        # Usar SMTP con STARTTLS para ProtonMail
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()  # Identificarse con el servidor
            server.starttls()  # Iniciar TLS
            server.ehlo()  # Identificarse nuevamente después de TLS
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(message)

        print(f" Email de verificación enviado exitosamente a {to_email}")

    except Exception as e:
        print(f"❌ Error enviando email: {e}")
        print(f"📧 Código de verificación para {to_email}: {code}")
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
