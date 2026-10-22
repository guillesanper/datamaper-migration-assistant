"""
Database Connections Router

API endpoints para gestión de conexiones a bases de datos externas:
- Test de credenciales
- Creación y gestión de sesiones
- Introspección de schemas
- Listado de tablas y columnas

SEGURIDAD:
- Los endpoints son síncronos (def): los drivers de BD son bloqueantes y FastAPI
  los ejecuta en el threadpool, de modo que una BD lenta no congela el event loop
- Requiere autenticación (CurrentUser)
- Credenciales cifradas con AES-256-GCM
- Sesiones con TTL en Redis
- Validación de ownership (user_id)
"""

import hashlib
import logging
import os
from typing import List, NoReturn, Optional, cast

import redis  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, HTTPException, status

from app.middleware.rate_limiting import simple_limiter
from app.models.db_connection import (
    DBConnectionConfig,
    DBConnectionRequest,
    DBConnectionSession,
    DBConnectionSessionResponse,
    DBConnectionTestResult,
)
from app.models.db_metadata import ColumnMetadata, SchemaMetadata, TableMetadata
from app.models.db_metadata.connector_tables import (
    ConnectorColumnResponse,
    ConnectorTableResponse,
    ConnectorTablesResponse,
)
from app.routers.dependencies import CurrentUser
from app.services.db_connection_service import (
    DBConnectionService,
    DBConnectionServiceError,
    SessionExpiredError,
    SessionNotFoundError,
)
from app.utils.db_adapters import DBHostNotAllowedError, DBMetadataNotFoundError, DBValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/db-connections", tags=["Database Connections"])

# Límite de intentos de conexión por usuario (test + crear sesión). Por usuario y no por
# IP: la IP del cliente se puede falsear con X-Forwarded-For.
CONNECT_RATE_LIMIT = int(os.getenv("DB_CONNECTOR_RATE_LIMIT", "10"))
CONNECT_RATE_WINDOW_SECONDS = int(os.getenv("DB_CONNECTOR_RATE_WINDOW_SECONDS", "60"))


def enforce_connect_rate_limit(user_id: str) -> None:
    """Evita usar el servidor para fuerza bruta de credenciales o barrido de hosts."""
    if not simple_limiter.is_allowed(
        f"db-connect:{user_id}", CONNECT_RATE_LIMIT, CONNECT_RATE_WINDOW_SECONDS
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many connection attempts, please wait before retrying",
        )


def raise_db_error(action: str, error: Exception) -> NoReturn:
    """
    Convierte un error de la BD externa en HTTPException sin filtrar detalles del driver.

    Los errores de validación (identificador inválido, host no permitido) y de
    metadata inexistente se devuelven tal cual; el resto solo se loguea.
    """
    if isinstance(error, HTTPException):
        raise error
    if isinstance(error, DBHostNotAllowedError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error))
    if isinstance(error, DBValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    if isinstance(error, DBMetadataNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))

    logger.error(f"Error {action}: {type(error).__name__}: {error}")
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Error {action} on the external database",
    )


# =============================================================================
# DEPENDENCIES
# =============================================================================


def get_redis_client() -> redis.Redis:
    """Dependency para obtener cliente Redis"""
    redis_client = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        db=int(os.getenv("REDIS_DB", 0)),
        decode_responses=False,  # Mantenemos bytes para hashes
    )
    return redis_client


def get_db_connection_service(
    redis_client: redis.Redis = Depends(get_redis_client),
) -> DBConnectionService:
    """Dependency para obtener DBConnectionService"""
    encryption_key = os.getenv("ENCRYPTION_MASTER_KEY")
    if not encryption_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Encryption master key not configured",
        )

    return DBConnectionService(redis_client, encryption_key)


def get_user_session(
    session_id: str,
    service: DBConnectionService = Depends(get_db_connection_service),
    current_user: dict = Depends(CurrentUser()),
) -> DBConnectionSession:
    """
    Dependency para obtener sesión de conexión y validar ownership.

    Args:
        session_id: ID de la sesión
        service: DBConnectionService
        current_user: Usuario autenticado

    Returns:
        DBConnectionSession validada

    Raises:
        HTTPException 404: Si la sesión no existe
        HTTPException 403: Si el usuario no es el propietario
        HTTPException 410: Si la sesión expiró
    """
    try:
        session = service.get_session(current_user["id"], session_id)

        # Validar ownership
        if session.user_id != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this session",
            )

        return session

    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Session not found: {session_id}"
        )
    except SessionExpiredError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail=f"Session expired: {session_id}"
        )


# =============================================================================
# ENDPOINTS - Test Connection
# =============================================================================


@router.post(
    "/test",
    response_model=DBConnectionTestResult,
    summary="Test database connection",
    description="Validates database credentials without creating a session",
)
def test_connection(
    config: DBConnectionConfig,
    service: DBConnectionService = Depends(get_db_connection_service),
    current_user: dict = Depends(CurrentUser()),
) -> DBConnectionTestResult:
    """
    Test de conexión a base de datos.

    Valida credenciales sin crear sesión. Útil para verificar antes de guardar.

    **Dialectos soportados**: postgresql, mysql

    **Permisos requeridos**: Usuario autenticado
    """
    enforce_connect_rate_limit(current_user["id"])

    try:
        result = service.test_connection(config)
        return result

    except Exception as e:
        raise_db_error("testing connection", e)


# =============================================================================
# ENDPOINTS - Session Management
# =============================================================================


@router.post(
    "/sessions",
    response_model=DBConnectionSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create connection session",
    description="Creates a new session with encrypted credentials stored in Redis",
)
def create_session(
    request: DBConnectionRequest,
    service: DBConnectionService = Depends(get_db_connection_service),
    current_user: dict = Depends(CurrentUser()),
) -> DBConnectionSessionResponse:
    """
    Crea sesión de conexión con credenciales cifradas.

    Las credenciales se cifran con AES-256-GCM y se almacenan en Redis con TTL.

    **TTL**: Por defecto 3 horas, máximo 24 horas

    **Test opcional**: Si test_connection=true, valida credenciales antes de crear sesión
    """
    enforce_connect_rate_limit(current_user["id"])

    # Validación adicional de ttl_hours para devolver 400 en vez de 422
    if request.ttl_hours > 24:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="TTL cannot exceed 24 hours"
        )

    try:
        response = service.create_session(
            user_id=current_user["id"],
            config=request.connection,
            ttl_hours=request.ttl_hours,
            test_connection=request.test_connection,
        )
        return response

    except DBConnectionServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/sessions",
    response_model=List[DBConnectionSessionResponse],
    summary="List user sessions",
    description="Lists all active sessions for the current user",
)
def list_sessions(
    service: DBConnectionService = Depends(get_db_connection_service),
    current_user: dict = Depends(CurrentUser()),
) -> List[DBConnectionSessionResponse]:
    """
    Lista todas las sesiones activas del usuario.

    Excluye sesiones expiradas (se eliminan automáticamente).
    """
    sessions = service.list_user_sessions(current_user["id"])

    # Convertir a response model
    return [
        DBConnectionSessionResponse(
            session_id=session.session_id,
            dialect=session.dialect,
            host=session.host,
            database=session.database,
            expires_at=session.expires_at,
        )
        for session in sessions
    ]


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete session",
    description="Deletes a connection session and removes credentials from Redis",
)
def delete_session(
    session_id: str,
    service: DBConnectionService = Depends(get_db_connection_service),
    current_user: dict = Depends(CurrentUser()),
):
    """
    Elimina sesión de conexión.

    Las credenciales cifradas se eliminan de Redis inmediatamente.
    """
    deleted = service.delete_session(current_user["id"], session_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Session not found: {session_id}"
        )

    return None


@router.post(
    "/sessions/{session_id}/refresh",
    response_model=DBConnectionSessionResponse,
    summary="Refresh session TTL",
    description="Extends the TTL of an active session",
)
def refresh_session(
    session_id: str,
    ttl_hours: int = 3,
    service: DBConnectionService = Depends(get_db_connection_service),
    current_user: dict = Depends(CurrentUser()),
) -> DBConnectionSessionResponse:
    """
    Extiende el TTL de una sesión.

    **Máximo TTL**: 24 horas
    """
    try:
        # Validar ownership
        get_user_session(session_id, service, current_user)

        # Refresh
        new_expires_at = service.refresh_session(current_user["id"], session_id, ttl_hours)

        # Obtener sesión actualizada
        session = service.get_session(current_user["id"], session_id)

        return DBConnectionSessionResponse(
            session_id=session.session_id,
            dialect=session.dialect,
            host=session.host,
            database=session.database,
            expires_at=new_expires_at,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# =============================================================================
# ENDPOINTS - Schema Introspection
# =============================================================================


@router.get(
    "/sessions/{session_id}/schemas",
    response_model=List[str],
    summary="List schemas/databases",
    description="Lists all schemas (PostgreSQL) or databases (MySQL)",
)
def list_schemas(
    session_id: str,
    session: DBConnectionSession = Depends(get_user_session),
    service: DBConnectionService = Depends(get_db_connection_service),
) -> List[str]:
    """
    Lista schemas/databases de la conexión.

    **PostgreSQL**: Retorna schemas (public, app_schema, etc.)
    **MySQL**: Retorna databases
    """
    try:
        # Descifrar config
        config = service.get_decrypted_config(session)

        # Obtener adapter
        adapter = service._get_adapter(config)

        # Listar schemas
        with adapter:
            schemas = adapter.get_schemas()

        return cast(List[str], schemas)

    except Exception as e:
        raise_db_error("listing schemas", e)


@router.get(
    "/sessions/{session_id}/schemas/{schema_name}/tables",
    response_model=List[TableMetadata],
    summary="List tables in schema",
    description="Lists all tables and views in a schema",
)
def list_tables(
    session_id: str,
    schema_name: str,
    session: DBConnectionSession = Depends(get_user_session),
    service: DBConnectionService = Depends(get_db_connection_service),
) -> List[TableMetadata]:
    """
    Lista tablas de un schema.

    Incluye BASE TABLEs y VIEWs.
    """
    try:
        # Descifrar config
        config = service.get_decrypted_config(session)

        # Obtener adapter
        adapter = service._get_adapter(config)

        # Listar tablas
        with adapter:
            tables = adapter.get_tables(schema=schema_name)

        return cast(List[TableMetadata], tables)

    except Exception as e:
        raise_db_error("listing tables", e)


@router.get(
    "/sessions/{session_id}/schemas/{schema_name}/tables/{table_name}/columns",
    response_model=List[ColumnMetadata],
    summary="List table columns",
    description="Lists all columns with metadata (type, nullable, PK, FK, etc.)",
)
def list_columns(
    session_id: str,
    schema_name: str,
    table_name: str,
    session: DBConnectionSession = Depends(get_user_session),
    service: DBConnectionService = Depends(get_db_connection_service),
) -> List[ColumnMetadata]:
    """
    Lista columnas de una tabla.

    Incluye metadata completa: tipos, PKs, FKs, defaults, etc.
    """
    try:
        # Descifrar config
        config = service.get_decrypted_config(session)

        # Obtener adapter
        adapter = service._get_adapter(config)

        # Listar columnas
        with adapter:
            columns = adapter.get_columns(table_name=table_name, schema=schema_name)

        return cast(List[ColumnMetadata], columns)

    except Exception as e:
        raise_db_error("listing columns", e)


@router.get(
    "/sessions/{session_id}/schemas/{schema_name}/metadata",
    response_model=SchemaMetadata,
    summary="Get full schema metadata",
    description="Gets complete metadata for a schema (tables, columns, constraints, indexes)",
)
def get_schema_metadata(
    session_id: str,
    schema_name: str,
    session: DBConnectionSession = Depends(get_user_session),
    service: DBConnectionService = Depends(get_db_connection_service),
) -> SchemaMetadata:
    """
    Obtiene metadata completa de un schema.

    Incluye:
    - Todas las tablas
    - Todas las columnas
    - Primary keys
    - Foreign keys
    - Índices
    - Estadísticas (row count aproximado)

    **Nota**: Este endpoint puede tardar en schemas grandes.
    """
    try:
        # Descifrar config
        config = service.get_decrypted_config(session)

        # Obtener adapter
        adapter = service._get_adapter(config)

        # Obtener metadata completa
        with adapter:
            schema_metadata = adapter.get_full_schema_metadata(schema=schema_name)

        return cast(SchemaMetadata, schema_metadata)

    except Exception as e:
        raise_db_error("getting schema metadata", e)


@router.get(
    "/sessions/{session_id}/connector-tables",
    response_model=ConnectorTablesResponse,
    summary="Get connector tables with hashes",
    description=(
        "Reads all tables from the external DB and returns them with pre-computed SHA-256 hashes. "
        "The structure is NOT saved locally. Hashes are used to identify tables/columns in mappings."
    ),
)
def get_connector_tables(
    session_id: str,
    schema: Optional[str] = None,
    session: DBConnectionSession = Depends(get_user_session),
    service: DBConnectionService = Depends(get_db_connection_service),
) -> ConnectorTablesResponse:
    """
    Obtiene tablas de la BD externa con hashes SHA-256 pre-computados.

    La estructura NO se guarda en la BD local. Los hashes identifican tablas y columnas
    en los mappings almacenados (origin_table_hash, origin_column_hash).

    El frontend muestra los nombres reales. Los hashes son transparentes al usuario.

    **Parámetros**:
    - schema: Filtrar por schema específico. Si se omite, devuelve todos los schemas.
    """
    try:
        config = service.get_decrypted_config(session)
        adapter = service._get_adapter(config)

        connector_tables: List[ConnectorTableResponse] = []

        with adapter:
            schemas_to_fetch: List[str] = [schema] if schema else adapter.get_schemas()

            for schema_name in schemas_to_fetch:
                try:
                    schema_metadata = adapter.get_full_schema_metadata(schema=schema_name)
                except Exception:
                    continue

                for table in schema_metadata.tables:
                    table_hash = hashlib.sha256(table.name.encode()).hexdigest()

                    connector_columns: List[ConnectorColumnResponse] = []
                    for col in table.columns:
                        col_hash = hashlib.sha256(col.name.encode()).hexdigest()
                        connector_columns.append(
                            ConnectorColumnResponse(
                                name=col.name,
                                column_hash=col_hash,
                                data_type=(
                                    str(col.data_type.value)
                                    if hasattr(col.data_type, "value")
                                    else str(col.data_type)
                                ),
                                native_type=col.native_type,
                                is_nullable=col.is_nullable,
                                is_primary_key=col.is_primary_key,
                                is_auto_increment=col.is_auto_increment,
                                default_value=col.default_value,
                                max_length=col.max_length,
                                ordinal_position=col.ordinal_position,
                            )
                        )

                    connector_tables.append(
                        ConnectorTableResponse(
                            name=table.name,
                            table_hash=table_hash,
                            schema=schema_name,
                            table_type=(
                                str(table.table_type.value)
                                if hasattr(table.table_type, "value")
                                else str(table.table_type)
                            ),
                            columns=connector_columns,
                        )
                    )

        return ConnectorTablesResponse(
            session_id=session_id,
            tables=connector_tables,
        )

    except Exception as e:
        raise_db_error("getting connector tables", e)
