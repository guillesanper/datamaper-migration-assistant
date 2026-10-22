"""
Modelo ORM para Email OTPs

Este módulo contiene el modelo para códigos OTP de email.

Características:
- Códigos de un solo uso para verificación de email
- Asociados a usuarios
- Expiración automática
- PK es user_id (un OTP activo por usuario)
"""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


class EmailOTP(Base):
    """
    Código OTP para verificación de email.

    Un usuario solo puede tener un OTP activo a la vez.
    Los códigos expiran automáticamente.

    Campos:
    - user_id: Usuario al que pertenece el OTP (PK y FK)
    - otp_code: Código OTP hasheado
    - expires_at: Timestamp de expiración
    - failed_attempts: Comprobaciones erróneas del código (se invalida al llegar a OTP_MAX_ATTEMPTS)
    """

    __tablename__ = "email_otps"

    # user_id es la PK (solo un OTP activo por usuario)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    # Código OTP (hasheado)
    otp_code = Column(Text, nullable=False)

    # Expiración
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

    # Intentos fallidos de este código (lo incrementa verify_otp_orm; create_otp_orm lo reinicia)
    failed_attempts = Column(Integer, nullable=False, server_default=text("0"))

    # Relationship
    user = relationship("User", backref="email_otp")

    def __repr__(self):
        return f"<EmailOTP(user_id={self.user_id}, expires_at={self.expires_at})>"
