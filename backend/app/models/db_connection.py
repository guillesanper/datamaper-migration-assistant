"""
Database Connection Models

Modelos Pydantic para gestión de sesiones de conexión a bases de datos externas.

SEGURIDAD:
- Las credenciales se cifran con AES-256-GCM antes de almacenarse en Redis
- Las sesiones tienen TTL de 3 horas
- Los session_id son UUID v4 únicos
"""

import uuid
from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class DBConnectionConfig(BaseModel):
    """
    Configuración de conexión a base de datos externa.

    Estos datos se cifran antes de almacenarse en Redis.
    """

    dialect: Literal["postgresql", "mysql", "sqlserver", "oracle"] = Field(
        ..., description="Tipo de base de datos"
    )
    host: str = Field(
        ..., min_length=1, max_length=255, description="Hostname o IP de la base de datos"
    )
    port: int = Field(..., ge=1, le=65535, description="Puerto de la base de datos")
    database: str = Field(
        ..., min_length=1, max_length=128, description="Nombre de la base de datos/schema"
    )
    user: str = Field(..., min_length=1, max_length=128, description="Usuario de la base de datos")
    password: str = Field(..., min_length=1, description="Contraseña de la base de datos")
    timeout: int = Field(default=30, ge=5, le=600, description="Timeout de conexión en segundos")
    ssl_mode: Literal["verify", "require", "disable"] = Field(
        default="verify",
        description=(
            "TLS: 'verify' cifra y verifica certificado y hostname (por defecto), "
            "'require' cifra sin verificar el certificado, 'disable' sin TLS"
        ),
    )

    # Oracle: identificador del servicio. Si no se indica ninguno se usa `database`
    # como service name.
    service_name: Optional[str] = Field(
        default=None, max_length=128, description="Oracle: service name"
    )
    sid: Optional[str] = Field(default=None, max_length=128, description="Oracle: SID")

    @field_validator("service_name", "sid")
    @classmethod
    def validate_oracle_target(cls, v: Optional[str]) -> Optional[str]:
        """Normaliza vacíos a None y rechaza caracteres de control"""
        if v is None or not v.strip():
            return None
        if any(not char.isprintable() for char in v):
            raise ValueError("must not contain control characters")
        return v.strip()

    @property
    def username(self) -> str:
        """Alias for user - used by tests"""
        return self.user

    @field_validator("dialect")
    @classmethod
    def validate_dialect(cls, v: str) -> str:
        """Valida que el dialecto esté soportado"""
        supported = ["postgresql", "mysql", "sqlserver", "oracle"]
        if v not in supported:
            raise ValueError(f"Dialect must be one of {supported}")
        return v

    def to_adapter_config(self) -> Dict[str, Any]:
        """
        Convierte a formato dict para adapters.

        Returns:
            Dict con configuración para BaseDBAdapter
        """
        return {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "password": self.password,
            "timeout": self.timeout,
            "ssl_mode": self.ssl_mode,
            **({"service_name": self.service_name} if self.service_name else {}),
            **({"sid": self.sid} if self.sid else {}),
        }

    class Config:
        json_schema_extra = {
            "example": {
                "dialect": "postgresql",
                "host": "localhost",
                "port": 5432,
                "database": "mydb",
                "user": "datamap_readonly",
                "password": "secure_password",
                "timeout": 30,
                "ssl_mode": "verify",
            }
        }


class DBConnectionRequest(BaseModel):
    """
    Request para crear una nueva sesión de conexión.

    El usuario proporciona credenciales que se cifran y almacenan temporalmente.
    """

    connection: DBConnectionConfig = Field(..., description="Configuración de conexión")
    test_connection: bool = Field(
        default=True, description="Validar credenciales antes de crear sesión"
    )
    ttl_hours: int = Field(
        default=3, ge=1, description="Tiempo de vida de la sesión en horas (máximo 24)"
    )
    project_id: Optional[uuid.UUID] = Field(
        default=None,
        description=(
            "Proyecto al que se ata la sesión (opcional). Si se indica, solo se puede usar "
            "desde ese proyecto"
        ),
    )

    class Config:
        json_schema_extra = {
            "example": {
                "connection": {
                    "dialect": "postgresql",
                    "host": "localhost",
                    "port": 5432,
                    "database": "mydb",
                    "user": "datamap_readonly",
                    "password": "secure_password",
                },
                "test_connection": True,
                "ttl_hours": 3,
            }
        }


class DBConnectionSession(BaseModel):
    """
    Sesión de conexión activa.

    Contiene metadatos de la sesión y credenciales cifradas.
    """

    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Identificador único de la sesión"
    )
    user_id: str = Field(..., description="ID del usuario propietario de la sesión (UUID)")
    project_id: Optional[str] = Field(
        default=None, description="ID del proyecto asociado (opcional, UUID)"
    )
    dialect: str = Field(..., description="Tipo de base de datos")
    host: str = Field(..., description="Hostname de la base de datos (metadata no cifrada)")
    database: str = Field(..., description="Nombre de la base de datos (metadata no cifrada)")
    encrypted_credentials: str = Field(
        ..., description="Credenciales cifradas con AES-256-GCM (base64)"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Fecha de creación de la sesión"
    )
    expires_at: datetime = Field(..., description="Fecha de expiración de la sesión")
    last_used_at: datetime = Field(
        default_factory=datetime.utcnow, description="Última vez que se usó la sesión"
    )

    def is_expired(self) -> bool:
        """Verifica si la sesión ha expirado"""
        return datetime.utcnow() > self.expires_at

    def to_redis_dict(self) -> Dict[str, Any]:
        """
        Serializa para almacenamiento en Redis.

        Returns:
            Dict con campos serializados (exclude None values)
        """
        data = {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "dialect": self.dialect,
            "host": self.host,
            "database": self.database,
            "encrypted_credentials": self.encrypted_credentials,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat(),
        }
        # Only add project_id if it's not None (Redis can't serialize None)
        if self.project_id is not None:
            data["project_id"] = self.project_id
        return data

    @classmethod
    def from_redis_dict(cls, data: Dict[str, Any]) -> "DBConnectionSession":
        """
        Deserializa desde Redis.

        Args:
            data: Dict con datos de Redis

        Returns:
            DBConnectionSession instanciada
        """
        return cls(
            session_id=data["session_id"],
            user_id=data["user_id"],
            project_id=data.get("project_id"),
            dialect=data["dialect"],
            host=data["host"],
            database=data["database"],
            encrypted_credentials=data["encrypted_credentials"],
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            last_used_at=datetime.fromisoformat(data["last_used_at"]),
        )

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "project_id": "223e4567-e89b-12d3-a456-426614174001",
                "dialect": "postgresql",
                "host": "localhost",
                "database": "mydb",
                "encrypted_credentials": "base64_encrypted_data...",
                "created_at": "2025-01-29T10:00:00",
                "expires_at": "2025-01-29T13:00:00",
                "last_used_at": "2025-01-29T10:00:00",
            }
        }


class DBConnectionTestResult(BaseModel):
    """
    Resultado de un test de conexión.

    Indica si las credenciales son válidas sin crear sesión.
    """

    success: bool = Field(..., description="True si la conexión fue exitosa")
    dialect: str = Field(..., description="Tipo de base de datos")
    host: str = Field(..., description="Hostname de la base de datos")
    database: str = Field(..., description="Nombre de la base de datos")
    error_message: Optional[str] = Field(
        default=None, description="Mensaje de error si la conexión falló"
    )
    error_type: Optional[str] = Field(
        default=None, description="Tipo de error (authentication, connection, timeout, etc.)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "dialect": "postgresql",
                "host": "localhost",
                "database": "mydb",
                "error_message": None,
                "error_type": None,
            }
        }


class DBConnectionSessionResponse(BaseModel):
    """
    Response al crear una sesión de conexión.

    Devuelve el session_id y metadatos básicos.
    """

    session_id: str = Field(..., description="Identificador único de la sesión")
    dialect: str = Field(..., description="Tipo de base de datos")
    host: str = Field(..., description="Hostname de la base de datos")
    database: str = Field(..., description="Nombre de la base de datos")
    expires_at: datetime = Field(..., description="Fecha de expiración de la sesión")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "dialect": "postgresql",
                "host": "localhost",
                "database": "mydb",
                "expires_at": "2025-01-29T13:00:00",
            }
        }
