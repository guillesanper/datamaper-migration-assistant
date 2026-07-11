"""
Modelo ORM para el log de requests HTTP de la API.

Captura método, endpoint, status code, tiempo de respuesta, usuario y errores
para visibilidad de rendimiento en el admin panel.
"""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database.base import Base


class ApiRequestLog(Base):
    """
    Log de cada request HTTP procesado por la API.

    Insertado de forma asíncrona (fire-and-forget) por el middleware de
    request_logging para no bloquear las respuestas.
    """

    __tablename__ = "api_request_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    method = Column(String(10), nullable=False)
    endpoint = Column(String(255), nullable=False, index=True)
    status_code = Column(Integer, nullable=False)
    response_time_ms = Column(Integer, nullable=False)

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    error_message = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    __table_args__ = (Index("idx_api_request_logs_endpoint_status", "endpoint", "status_code"),)

    def __repr__(self) -> str:
        return (
            f"<ApiRequestLog(id={self.id}, method='{self.method}', "
            f"endpoint='{self.endpoint}', status={self.status_code}, "
            f"time={self.response_time_ms}ms)>"
        )
