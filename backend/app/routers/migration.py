"""
Migration Router

API endpoints para generación y ejecución de scripts de migración:
- Generación de scripts SQL optimizados con análisis de dependencias
- Ejecución de migraciones con tracking en tiempo real
- Consulta de estado y progreso de ejecuciones
- Análisis de grafos de dependencias entre tablas

SEGURIDAD:
- Requiere autenticación (CurrentUser)
- Validación de ownership de proyecto
- Backups automáticos antes de ejecutar

CREATED: 2025-01-17
"""

import hashlib
import logging
import os
from contextlib import ExitStack
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.crud import activity_crud, mappings_crud, migration_script_crud, notification_crud

# CRUDs ORM
from app.crud.project_crud import ProjectCRUD
from app.database.session import get_db_session
from app.models.db_connection import DBConnectionConfig
from app.models.db_metadata.constraint import ForeignKeyMetadata
from app.models.db_metadata.schema import SchemaMetadata
from app.models.db_metadata.table import TableMetadata
from app.routers.dependencies import get_current_user, validate_encryption_session
from app.services.data_copy_service import COPY_PLAN_MARKER, DataCopyService
from app.services.db_connection_service import (
    DBConnectionService,
    SessionExpiredError,
    SessionNotFoundError,
)
from app.services.dependency_graph_service import DependencyGraphService
from app.services.execution_service import ExecutionService, execution_progress
from app.services.migration_script_service import (
    MigrationScriptService,
    MigrationScriptServiceError,
)
from app.utils.db_adapters.base_adapter import BaseDBAdapter
from app.utils.exception_sanitizer import internal_server_error
from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["Migration"])
global_router = APIRouter(prefix="/api/migrations", tags=["Migration"])


# =============================================================================
# PYDANTIC MODELS
# =============================================================================


class MigrationScriptOptions(BaseModel):
    """Opciones para generación de script de migración"""

    batch_size: int = Field(default=10000, ge=1, le=1000000)
    include_constraints: bool = Field(default=True)
    include_validation: bool = Field(default=True)
    dialect: str = Field(default="postgresql", pattern="^(postgresql|mysql|sqlserver|oracle)$")
    origin_connection_session_id: Optional[str] = Field(
        default=None,
        description="Sesión de conexión origen (resuelve mappings connector del origen)",
    )
    dest_connection_session_id: Optional[str] = Field(
        default=None,
        description=(
            "Sesión de conexión destino (resuelve mappings connector del destino y fija "
            "el dialecto)"
        ),
    )


class ExecutionRequest(BaseModel):
    """Request para ejecutar una migración"""

    script_id: Optional[str] = Field(
        default=None, description="UUID del script guardado (opcional)"
    )
    dry_run: bool = Field(default=False, description="Si True, ejecuta ROLLBACK al final")
    dest_connection_session_id: str = Field(
        ..., description="UUID de la sesión de conexión destino"
    )
    origin_connection_session_id: Optional[str] = Field(
        default=None,
        description=(
            "UUID de la sesión de conexión origen. Si es otra BD distinta del destino, "
            "DataMap copia los datos por lotes en lugar de ejecutar el script SQL"
        ),
    )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


# Roles que pueden generar y ejecutar migraciones (escriben en la BD destino)
MIGRATION_WRITE_ROLES = {"owner", "editor"}


def validate_project_access(
    db, project_id: str, current_user: dict, require_write: bool = False
) -> dict:
    """
    Valida que el usuario tenga acceso al proyecto usando CRUD ORM.

    Args:
        db: Database session
        project_id: UUID del proyecto
        current_user: Usuario autenticado
        require_write: Si True, exige ser owner o editor (los viewers solo leen)

    Returns:
        dict con información del proyecto

    Raises:
        HTTPException: Si el proyecto no existe o el usuario no tiene acceso
    """
    # Obtener proyecto usando CRUD ORM
    project = ProjectCRUD.get_project_by_id_orm(db, project_id)

    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Verificar acceso usando CRUD ORM
    has_access = ProjectCRUD.check_user_access_orm(db, project_id, str(current_user["id"]))

    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this project"
        )

    if require_write and not (
        has_access.get("is_owner") or has_access.get("role") in MIGRATION_WRITE_ROLES
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only project owners and editors can generate or execute migrations",
        )

    return project


def get_project_mappings(
    db, project_id: str, encryption_key: Optional[bytes] = None
) -> List[Dict[str, Any]]:
    """
    Obtiene todos los mappings de un proyecto usando CRUD ORM, descifrados.

    Args:
        db: Database session
        project_id: UUID del proyecto
        encryption_key: Clave de la sesión de cifrado del usuario (proyectos cifrados)

    Returns:
        Lista de mappings

    Raises:
        HTTPException 423: Si hay campos cifrados que no se pudieron descifrar. Sin esto la
            migración usaba nombres vacíos o, peor, se ejecutaba sin las transformaciones.
    """
    mappings = mappings_crud.get_mappings_by_project_orm(
        db, project_id, encryption_key=encryption_key
    )
    ensure_mappings_decrypted(mappings)

    # Ordenar por destination_table y destination_column
    return sorted(
        mappings,
        key=lambda m: (m.get("destination_table") or "", m.get("destination_column") or ""),
    )


# (campo cifrado, campo descifrado que debe quedar disponible)
_ENCRYPTED_MAPPING_FIELDS = [
    ("origin_table_encrypted", "origin_table"),
    ("origin_column_encrypted", "origin_column"),
    ("destination_table_encrypted", "destination_table"),
    ("destination_column_encrypted", "destination_column"),
    ("transformation_logic_encrypted", "transformation_logic"),
]


def ensure_mappings_decrypted(mappings: List[Dict[str, Any]]) -> None:
    """Falla si algún mapping tiene campos cifrados sin su valor en claro."""
    for mapping in mappings:
        for encrypted_key, plain_key in _ENCRYPTED_MAPPING_FIELDS:
            side = plain_key.split("_", 1)[0]
            if side in ("origin", "destination") and (
                mapping.get(f"{side}_source_type") == "connector"
            ):
                continue  # modo connector: no usa nombres cifrados
            if mapping.get(encrypted_key) and not mapping.get(plain_key):
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail=(
                        "This project's mappings are encrypted: unlock the project's "
                        "encryption session before generating or executing a migration"
                    ),
                )


def open_session_adapter(
    db_service: DBConnectionService,
    user_id: str,
    project_id: str,
    session_id: str,
    side: str,
    stack: ExitStack,
    long_running: bool = False,
) -> Tuple[DBConnectionConfig, BaseDBAdapter]:
    """
    Conecta a la BD de una sesión del usuario; el ExitStack la desconecta al salir.

    Raises:
        HTTPException 404/410: Sesión inexistente (de otro usuario o atada a otro
            proyecto) o expirada
    """
    try:
        session = db_service.get_session(user_id, session_id, project_id=project_id)
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{side.capitalize()} connection session not found",
        )
    except SessionExpiredError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"{side.capitalize()} connection session expired",
        )

    config = db_service.get_decrypted_config(session)
    adapter = db_service._get_adapter(config, long_running=long_running)
    adapter.connect()
    stack.callback(adapter.disconnect)
    return config, adapter


def connector_session_id(
    mappings: List[Dict[str, Any]], side: str, explicit: Optional[str]
) -> Optional[str]:
    """
    Sesión con la que resolver los mappings connector de un lado.

    La de la petición si se indica; si no, la que se usó al crear los mappings (si
    sigue activa y es del usuario, open_session_adapter lo comprueba).
    """
    if explicit:
        return explicit
    for mapping in mappings:
        if mapping.get(f"{side}_source_type") == "connector" and mapping.get(f"{side}_session_id"):
            return str(mapping[f"{side}_session_id"])
    return None


def require_connector_session(
    mappings: List[Dict[str, Any]], side: str, session_id: Optional[str]
) -> None:
    """Error claro si hay mappings connector de un lado y no hay sesión con la que resolverlos."""
    has_connector = any(m.get(f"{side}_source_type") == "connector" for m in mappings)
    if has_connector and not session_id:
        param = "origin" if side == "origin" else "dest"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Mappings use a live connection on the {side} side: an active {side} "
                f"connection session is required ({param}_connection_session_id)"
            ),
        )


def is_cross_database(
    origin_session_id: Optional[str],
    dest_session_id: Optional[str],
    origin_config: Optional[DBConnectionConfig],
    dest_config: Optional[DBConnectionConfig],
) -> bool:
    """True si origen y destino son BDs distintas (el script SQL no puede leer el origen)."""
    if origin_config is None or dest_config is None or origin_session_id == dest_session_id:
        return False

    def identity(config: DBConnectionConfig) -> tuple:
        return (
            config.dialect,
            str(config.host).lower(),
            config.port,
            config.database,
            getattr(config, "service_name", None),
            getattr(config, "sid", None),
        )

    return identity(origin_config) != identity(dest_config)


def build_copy_plans(mappings, origin_adapter, dest_adapter, dependency_order=None):
    """Planes para la copia entre BDs; cualquier nombre sin resolver es un error."""
    try:
        plans, errors = MigrationScriptService.build_table_plans(
            [dict(m) for m in mappings], origin_adapter, dest_adapter, dependency_order
        )
    except (MigrationScriptServiceError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid mappings for migration: {str(e)}",
        )
    if errors:
        # Copiar el resto omitiendo tablas dejaría una migración parcial "con éxito"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Some mappings could not be resolved: {'; '.join(errors)}",
        )
    return plans


def build_schema_metadata_from_mappings(mappings: List[Dict]) -> SchemaMetadata:
    """
    Construye SchemaMetadata a partir de mappings para análisis de dependencias.

    Nota: Esta es una versión simplificada que extrae tablas de los mappings.
    En un caso real, deberíamos obtener el schema completo con FKs del adapter.

    Args:
        mappings: Lista de mappings

    Returns:
        SchemaMetadata con tablas y foreign keys
    """
    # Extraer tablas únicas
    tables_set = set()
    for m in mappings:
        tables_set.add(m["destination_table"])

    # Crear TableMetadata para cada tabla
    tables = [TableMetadata(name=table_name, schema=None) for table_name in sorted(tables_set)]

    # Para obtener FKs reales, necesitaríamos consultar el schema de la BD destino
    # Por ahora, retornamos schema sin FKs (las dependencias se calculan después)
    foreign_keys: List[ForeignKeyMetadata] = []

    return SchemaMetadata(name="public", tables=tables, foreign_keys=foreign_keys)


def generate_script_for_sessions(
    mappings: List[Dict[str, Any]],
    options: MigrationScriptOptions,
    project: dict,
    project_id: str,
    user_id: str,
    dependency_order: Optional[List[str]],
) -> Tuple[str, str]:
    """
    Genera el script conectando a las sesiones que hagan falta.

    Returns:
        (script, dialecto destino). Si origen y destino son BDs distintas el script es
        el plan de copia por lotes (COPY_PLAN_MARKER) que ejecuta /execute.
    """
    origin_session_id = connector_session_id(
        mappings, "origin", options.origin_connection_session_id
    )
    dest_session_id = connector_session_id(
        mappings, "destination", options.dest_connection_session_id
    )
    require_connector_session(mappings, "origin", origin_session_id)
    require_connector_session(mappings, "destination", dest_session_id)
    dialect = options.dialect

    with ExitStack() as stack:
        origin_config = dest_config = None
        origin_adapter = dest_adapter = None
        if origin_session_id or dest_session_id:
            db_service = get_db_connection_service()
            if origin_session_id:
                origin_config, origin_adapter = open_session_adapter(
                    db_service, user_id, project_id, origin_session_id, "origin", stack
                )
            if dest_session_id:
                dest_config, dest_adapter = open_session_adapter(
                    db_service, user_id, project_id, dest_session_id, "destination", stack
                )
                # El script se ejecuta en el destino: su dialecto manda
                dialect = dest_config.dialect

        # is_cross_database ya exige ambos configs; cada adaptador se abre junto a su config
        if (
            origin_adapter is not None
            and dest_adapter is not None
            and is_cross_database(origin_session_id, dest_session_id, origin_config, dest_config)
        ):
            # Entre BDs distintas un INSERT ... SELECT no puede leer el origen
            plans = build_copy_plans(mappings, origin_adapter, dest_adapter, dependency_order)
            script = DataCopyService(
                origin_adapter, dest_adapter, batch_size=options.batch_size
            ).describe(
                plans,
                project_name=project["name"],
                include_constraints=options.include_constraints,
                include_validation=options.include_validation,
            )
            return script, dialect

        script = MigrationScriptService.generate_insert_script(
            mappings=[dict(m) for m in mappings],
            origin_adapter=origin_adapter,
            dest_adapter=dest_adapter,
            project_name=project["name"],
            dependency_order=dependency_order if dependency_order else None,
            batch_size=options.batch_size,
            include_constraints=options.include_constraints,
            include_validation=options.include_validation,
            dialect=dialect,
        )
        return script, dialect


def execute_cross_database_copy(
    db,
    project_id: str,
    project: dict,
    request: ExecutionRequest,
    user_id: str,
    mappings: List[Dict[str, Any]],
    origin_adapter: BaseDBAdapter,
    dest_adapter: BaseDBAdapter,
) -> Dict[str, Any]:
    """Copia por lotes origen -> destino con las opciones del script guardado (si hay)."""
    options = MigrationScriptOptions(dialect=dest_adapter.dialect)
    dependency_order = None
    if request.script_id:
        saved = migration_script_crud.get_migration_script_by_id_orm(
            db, request.script_id, project_id
        )
        if not saved or str(saved.get("project_id")) != str(project_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Script not found")
        options = MigrationScriptOptions(
            dialect=dest_adapter.dialect,
            batch_size=saved.get("batch_size") or options.batch_size,
            include_constraints=saved.get("include_constraints", True),
            include_validation=saved.get("include_validation", True),
        )
        dependency_order = saved.get("dependency_order") or None

    plans = build_copy_plans(mappings, origin_adapter, dest_adapter, dependency_order)
    logger.info(f"Cross-database copy of {len(plans)} tables")
    return ExecutionService().execute_copy(
        db_connection=db,
        project_id=project_id,
        plans=plans,
        origin_adapter=origin_adapter,
        dest_adapter=dest_adapter,
        dry_run=request.dry_run,
        user_id=user_id,
        batch_size=options.batch_size,
        include_constraints=options.include_constraints,
        include_validation=options.include_validation,
        project_name=project["name"],
    )


def load_or_generate_script(
    db,
    project_id: str,
    project: dict,
    script_id: Optional[str],
    dialect: str,
    mappings: Optional[List[Dict[str, Any]]] = None,
    origin_adapter: Optional[BaseDBAdapter] = None,
    dest_adapter: Optional[BaseDBAdapter] = None,
) -> str:
    """
    Carga el script guardado (verificando que sea del mismo dialecto que el destino)
    o genera uno nuevo a partir de los mappings del proyecto.

    Raises:
        HTTPException: Si el script no existe, es de otro dialecto o los mappings son inválidos
    """
    if script_id:
        # Cargar script guardado usando CRUD ORM
        script_row = migration_script_crud.get_migration_script_by_id_orm(db, script_id, project_id)

        if not script_row or str(script_row.get("project_id")) != str(project_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Script not found")

        script: str = script_row["script_content"]
        script_dialect = script_row.get("dialect") or dialect
        if script_dialect != dialect:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Script was generated for '{script_dialect}' but the destination "
                    f"connection is '{dialect}'"
                ),
            )
        if script.startswith(COPY_PLAN_MARKER):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "This script describes a copy between two databases: execute it with "
                    "the origin connection session (origin_connection_session_id)"
                ),
            )
        logger.info(f"Loaded saved script: {script_id}")
    else:
        # Generar nuevo script on-the-fly
        if mappings is None:
            mappings = get_project_mappings(db, project_id)

        if not mappings:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No mappings found for this project",
            )

        try:
            script = MigrationScriptService.generate_insert_script(
                mappings=[dict(m) for m in mappings],
                origin_adapter=origin_adapter,
                dest_adapter=dest_adapter,
                project_name=project["name"],
                dialect=dialect,
            )
        except (MigrationScriptServiceError, ValueError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid mappings for migration script: {str(e)}",
            )
        logger.info("Generated new script on-the-fly")

    return script


def get_db_connection_service() -> DBConnectionService:
    """Dependency para obtener DBConnectionService"""
    redis_client = get_redis_client()
    encryption_key = os.getenv("ENCRYPTION_MASTER_KEY")

    if not encryption_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Encryption master key not configured",
        )

    return DBConnectionService(redis_client, encryption_key)


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.post(
    "/{project_id}/migration/generate-script",
    summary="Generate migration script",
    description="Genera script SQL de migración optimizado con análisis de dependencias",
)
def generate_migration_script(
    project_id: str,
    options: MigrationScriptOptions,
    http_request: Request,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
    _=Depends(validate_encryption_session),
) -> Dict[str, Any]:
    """
    Genera script de migración SQL con:
    - Análisis de dependencias entre tablas
    - Orden topológico de ejecución
    - Batching para tablas grandes
    - Manejo de constraints y validación

    Returns:
        {
            "script_id": "uuid",
            "script": "BEGIN; ...",
            "estimated_duration_seconds": 2700,
            "estimated_rows": 35000,
            "dependency_order": ["customers", "orders", "order_items"],
            "created_at": "2025-01-16T14:30:00Z"
        }
    """
    try:
        # PASO 1: Validar acceso al proyecto (owner/editor)
        project = validate_project_access(db, project_id, current_user, require_write=True)
        logger.info(f"Generating migration script for project {project_id} ({project['name']})")

        # PASO 2: Obtener mappings del proyecto (descifrados con la sesión de cifrado)
        encryption_key = getattr(http_request.state, "encryption_key", None)
        mappings = get_project_mappings(db, project_id, encryption_key)

        if not mappings:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No mappings found for this project"
            )

        logger.info(f"Found {len(mappings)} mappings")

        # PASO 3: Construir metadata del schema para análisis de dependencias
        # Nota: En producción, deberíamos obtener el schema completo con FKs del adapter
        schema_metadata = build_schema_metadata_from_mappings(mappings)

        # PASO 4: Analizar dependencias (si hay FKs disponibles)
        dependency_order = []
        if schema_metadata.foreign_keys:
            try:
                dependency_service = DependencyGraphService(schema_metadata)
                dependency_order = dependency_service.get_migration_order()
                logger.info(f"Dependency order: {dependency_order}")
            except Exception as e:
                logger.warning(f"Could not analyze dependencies: {str(e)}")
                # Continuar sin orden de dependencias

        # PASO 5: Generar script. Los mappings connector se resuelven con las sesiones
        # de conexión (de la petición o las usadas al crear los mappings)
        script, dialect = generate_script_for_sessions(
            mappings, options, project, project_id, current_user["id"], dependency_order
        )

        # PASO 6: Calcular estimaciones
        estimated_rows = len(mappings) * 1000  # Estimación simplificada
        estimated_duration = (estimated_rows / options.batch_size) * 0.5  # 0.5s por batch

        # PASO 7: Guardar script usando CRUD ORM
        saved_script = migration_script_crud.create_migration_script_orm(
            db=db,
            project_id=project_id,
            script_content=script,
            batch_size=options.batch_size,
            include_constraints=options.include_constraints,
            include_validation=options.include_validation,
            dialect=dialect,
            dependency_order=dependency_order if dependency_order else [],
            created_by=str(current_user["id"]),
        )

        script_id = saved_script["id"]
        logger.info(f"Script saved with ID: {script_id}")

        # PASO 8: Log activity
        tables_count = (
            len(dependency_order)
            if dependency_order
            else len(set(m["destination_table"] for m in mappings))
        )
        activity_crud.create_activity_log_orm(
            db=db,
            project_id=project_id,
            user_id=str(current_user["id"]),
            activity_type="migration:script_generated",
            description=f"Migration script generated: {tables_count} tables, dialect={dialect}",
            entity_id=script_id,
            entity_type="migration_script",
        )

        # PASO 9: Retornar respuesta
        return {
            "script_id": script_id,
            "script": script,
            "estimated_duration_seconds": int(estimated_duration),
            "estimated_rows": estimated_rows,
            "dependency_order": dependency_order if dependency_order else [],
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

    except HTTPException:
        raise
    except (MigrationScriptServiceError, ValueError) as e:
        # Mappings inválidos o inseguros (p.ej. transformación con ';', tipo inválido)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid mappings for migration script: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Error generating migration script: {str(e)}")
        db.rollback()
        raise internal_server_error(e, logger, "Error generating migration script") from e


@router.post(
    "/{project_id}/migration/execute",
    summary="Execute migration",
    description="Ejecuta script de migración contra la base de datos destino",
)
def execute_migration(
    project_id: str,
    request: ExecutionRequest,
    http_request: Request,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
    _=Depends(validate_encryption_session),
) -> Dict[str, Any]:
    """
    Ejecuta migración con:
    - Backup automático antes de ejecutar
    - Tracking de progreso en tiempo real
    - Modo dry-run para testing
    - ROLLBACK automático en caso de error

    Returns:
        {
            "execution_id": "uuid",
            "status": "running",
            "message": "Migration started successfully"
        }
    """
    try:
        # PASO 1: Validar acceso al proyecto (owner/editor: escribe en la BD destino)
        project = validate_project_access(db, project_id, current_user, require_write=True)
        logger.info(f"Executing migration for project {project_id}")

        # PASO 2: Mappings (descifrados) y sesión origen. Con un script guardado y sin
        # sesión origen no hacen falta los mappings: se ejecuta el script tal cual
        encryption_key = getattr(http_request.state, "encryption_key", None)
        mappings: Optional[List[Dict[str, Any]]] = None
        origin_session_id = request.origin_connection_session_id
        if not request.script_id:
            mappings = get_project_mappings(db, project_id, encryption_key)
            origin_session_id = connector_session_id(mappings, "origin", origin_session_id)
            require_connector_session(mappings, "origin", origin_session_id)

        db_service = get_db_connection_service()

        with ExitStack() as stack:
            # PASO 3: Conectar al destino (sin límite de lectura: los INSERT pueden tardar)
            config, dest_adapter = open_session_adapter(
                db_service,
                current_user["id"],
                project_id,
                request.dest_connection_session_id,
                "destination",
                stack,
                long_running=True,
            )
            logger.info(f"Connected to destination database: {config.dialect}")

            origin_config, origin_adapter = None, None
            if origin_session_id:
                origin_config, origin_adapter = open_session_adapter(
                    db_service,
                    current_user["id"],
                    project_id,
                    origin_session_id,
                    "origin",
                    stack,
                    long_running=True,
                )

            # is_cross_database ya exige el config de origen, que se abre junto a su adaptador
            if origin_adapter is not None and is_cross_database(
                origin_session_id, request.dest_connection_session_id, origin_config, config
            ):
                # PASO 4a: BDs distintas: copia por lotes origen -> destino
                if mappings is None:
                    mappings = get_project_mappings(db, project_id, encryption_key)
                result = execute_cross_database_copy(
                    db,
                    project_id,
                    project,
                    request,
                    current_user["id"],
                    mappings,
                    origin_adapter,
                    dest_adapter,
                )
            else:
                # PASO 4b: misma BD: script INSERT ... SELECT en el destino
                script = load_or_generate_script(
                    db,
                    project_id,
                    project,
                    request.script_id,
                    config.dialect,
                    mappings=mappings,
                    origin_adapter=origin_adapter,
                    dest_adapter=dest_adapter,
                )
                result = ExecutionService().execute_migration(
                    db_connection=db,
                    project_id=project_id,
                    script=script,
                    dest_adapter=dest_adapter,
                    dry_run=request.dry_run,
                    user_id=current_user["id"],
                )

        logger.info(f"Migration execution completed: {result['status']}")

        # PASO 5: Log activity
        activity_crud.create_activity_log_orm(
            db=db,
            project_id=project_id,
            user_id=str(current_user["id"]),
            activity_type="migration:execution_started",
            description=f"Migration execution completed (ID: {result['execution_id']}, status={result['status']}, dry_run={request.dry_run})",
            entity_id=result["execution_id"],
            entity_type="migration_execution",
        )

        # PASO 6: Notify user on completion
        final_status = result["status"]
        if final_status == "success":
            notif_title = "Migration completed successfully"
            notif_body = (
                f"Project '{project['name']}': {result.get('rows_affected', 0)} rows migrated."
            )
        elif final_status == "dry_run_complete":
            notif_title = "Dry-run migration completed"
            notif_body = f"Project '{project['name']}': dry-run finished — no data was modified."
        else:
            notif_title = "Migration failed"
            notif_body = f"Project '{project['name']}': migration failed. Check the execution log for details."

        notification_crud.create_notification_orm(
            db=db,
            recipient_id=str(current_user["id"]),
            notification_kind="migration_complete",
            title=notif_title,
            body=notif_body,
            project_id=project_id,
            data={"execution_id": result["execution_id"], "status": final_status},
        )

        # PASO 7: Retornar resultado
        return {
            "execution_id": result["execution_id"],
            "status": result["status"],
            "message": f"Migration {'dry-run' if request.dry_run else 'execution'} completed",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise internal_server_error(e, logger, "Error executing migration") from e


@router.get(
    "/{project_id}/migration/executions/{execution_id}",
    summary="Get execution status",
    description="Consulta el estado y progreso de una ejecución de migración",
)
def get_execution_status(
    project_id: str,
    execution_id: str,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Retorna estado detallado de ejecución con:
    - Progreso actual (%)
    - Filas migradas
    - Tiempo restante estimado
    - Log de pasos ejecutados
    - Errores (si aplica)

    Returns:
        {
            "execution_id": "uuid",
            "status": "running" | "success" | "failed" | "dry_run_complete",
            "progress_percent": 60,
            "rows_migrated": 21000,
            "estimated_remaining_seconds": 30,
            "started_at": "2025-01-16T14:30:00Z",
            "completed_at": null,
            "current_step": "Migrating table: orders (batch 2/3)",
            "execution_log": [...],
            "errors": []
        }
    """
    try:
        # PASO 1: Validar acceso al proyecto
        validate_project_access(db, project_id, current_user)

        # PASO 2: Obtener ejecución usando CRUD ORM
        execution = migration_script_crud.get_execution_by_project_orm(db, execution_id, project_id)
        if not execution:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found for this project"
            )

        # PASO 3: Progreso y step actual desde el execution_log
        exec_status = execution.get("status", "pending")
        execution_log = execution.get("execution_log", [])
        progress = execution_progress(execution)
        progress_percent = progress["progress_percent"]
        current_step = progress["current_step"]

        # PASO 5: Calcular tiempo restante estimado
        estimated_remaining = 0
        if exec_status == "running":
            if progress_percent > 0:
                estimated_remaining = int((100 - progress_percent) * 0.5)

        # PASO 6: Preparar respuesta
        started_at = execution.get("started_at")
        completed_at = execution.get("completed_at")
        error_message = execution.get("error_message")

        return {
            "execution_id": str(execution.get("id")),
            "status": exec_status,
            "progress_percent": progress_percent,
            "rows_migrated": execution.get("rows_migrated", 0) or 0,
            "estimated_remaining_seconds": estimated_remaining,
            "started_at": started_at.isoformat() if started_at else None,
            "completed_at": completed_at.isoformat() if completed_at else None,
            "current_step": current_step,
            "execution_log": execution_log if execution_log else [],
            "errors": [error_message] if error_message else [],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise internal_server_error(e, logger, "Error getting execution status") from e


@router.get(
    "/{project_id}/migration/executions",
    summary="List executions",
    description="Lista todas las ejecuciones de migración del proyecto",
)
def list_executions(
    project_id: str,
    status_filter: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Lista ejecuciones con filtros y paginación.

    Query params:
        - status: Filtrar por status (running, success, failed, dry_run_complete)
        - limit: Número de resultados (default: 10)
        - offset: Offset para paginación (default: 0)

    Returns:
        {
            "executions": [...],
            "total": 25,
            "limit": 10,
            "offset": 0
        }
    """
    try:
        # PASO 1: Validar acceso al proyecto
        validate_project_access(db, project_id, current_user)

        # PASO 2: Contar total usando CRUD ORM
        total = migration_script_crud.count_executions_orm(
            db, project_id, status_filter=status_filter
        )

        # PASO 3: Obtener ejecuciones paginadas usando CRUD ORM
        executions = migration_script_crud.get_executions_paginated_orm(
            db=db, project_id=project_id, status_filter=status_filter, limit=limit, offset=offset
        )

        # PASO 4: Formatear respuesta (el CRUD ya retorna los datos en el formato correcto)
        formatted_executions = []
        for e in executions:
            started_at = e.get("started_at")
            completed_at = e.get("completed_at")
            formatted_executions.append(
                {
                    "id": e.get("id"),
                    "started_at": started_at.isoformat() if started_at else None,
                    "completed_at": completed_at.isoformat() if completed_at else None,
                    "status": e.get("status"),
                    "rows_migrated": e.get("rows_migrated", 0),
                    "duration_seconds": e.get("duration_seconds", 0),
                }
            )

        return {
            "executions": formatted_executions,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise internal_server_error(e, logger, "Error listing executions") from e


@router.get(
    "/{project_id}/migration/dependency-graph",
    summary="Get dependency graph",
    description="Obtiene el grafo de dependencias entre tablas para visualización",
)
def get_dependency_graph(
    project_id: str,
    dest_connection_session_id: Optional[str] = None,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Analiza dependencias entre tablas basándose en foreign keys.
    Útil para visualizar en UI antes de ejecutar migración.

    Returns:
        {
            "execution_order": ["customers", "products", "orders"],
            "circular_dependencies": [],
            "independent_tables": ["customers", "products"],
            "graph_visualization": {
                "nodes": [
                    {"id": "customers", "label": "Customers"},
                    {"id": "orders", "label": "Orders"}
                ],
                "edges": [
                    {"from": "customers", "to": "orders"}
                ]
            }
        }
    """
    try:
        # PASO 1: Validar acceso al proyecto
        validate_project_access(db, project_id, current_user)

        # PASO 2: Obtener mappings usando CRUD ORM
        mappings = get_project_mappings(db, project_id)

        if not mappings:
            return {
                "execution_order": [],
                "circular_dependencies": [],
                "independent_tables": [],
                "graph_visualization": {"nodes": [], "edges": []},
            }

        # PASO 3: Construir schema metadata con FKs reales si hay conexión destino disponible
        if dest_connection_session_id:
            try:
                db_service = get_db_connection_service()
                session = db_service.get_session(
                    current_user["id"], dest_connection_session_id, project_id=project_id
                )
                config = db_service.get_decrypted_config(session)
                dest_adapter = db_service._get_adapter(config)
                dest_adapter.connect()
                try:
                    schema_metadata = dest_adapter.get_full_schema_metadata()
                    logger.info(
                        f"Retrieved schema metadata with {len(schema_metadata.foreign_keys)} FKs"
                        f" from destination DB"
                    )
                finally:
                    dest_adapter.disconnect()
            except (SessionNotFoundError, SessionExpiredError) as e:
                logger.warning(f"Dest connection not available for FK analysis: {e}")
                schema_metadata = build_schema_metadata_from_mappings(mappings)
            except Exception as e:
                logger.warning(f"Could not fetch schema from dest DB: {e}")
                schema_metadata = build_schema_metadata_from_mappings(mappings)
        else:
            schema_metadata = build_schema_metadata_from_mappings(mappings)

        # PASO 4: Analizar dependencias con DependencyGraphService
        tables = [t.name for t in schema_metadata.tables]
        circular_dependencies: List[Any] = []
        execution_order = sorted(tables)
        independent_tables = sorted(tables)

        if schema_metadata.foreign_keys:
            try:
                dependency_service = DependencyGraphService(schema_metadata)
                analysis = dependency_service.analyze_dependencies()
                execution_order = analysis.get("migration_order") or sorted(tables)
                circular_dependencies = [list(cycle) for cycle in analysis.get("cycles", [])]
                independent_tables = analysis.get("independent_tables", sorted(tables))
                logger.info(f"Dependency analysis: {len(execution_order)} tables in order")
            except Exception as e:
                logger.warning(f"Could not analyze dependencies: {e}")

        # PASO 5: Generar graph visualization
        nodes = [{"id": table, "label": table.replace("_", " ").title()} for table in tables]

        edges = [
            {"from": fk.table_name, "to": fk.referenced_table}
            for fk in schema_metadata.foreign_keys
        ]

        return {
            "execution_order": execution_order,
            "circular_dependencies": circular_dependencies,
            "independent_tables": independent_tables,
            "graph_visualization": {"nodes": nodes, "edges": edges},
        }

    except HTTPException:
        raise
    except Exception as e:
        raise internal_server_error(e, logger, "Error getting dependency graph") from e


@global_router.get(
    "/recent",
    summary="Recent migrations",
    description="Returns the latest migration executions across all accessible projects",
)
def get_recent_migrations(
    limit: int = 5,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    Returns up to `limit` recent migration executions for all projects
    the authenticated user can access (owned or member of).
    """
    try:
        return migration_script_crud.get_recent_executions_for_user(
            db=db,
            user_id=str(current_user["id"]),
            limit=limit,
        )
    except Exception as e:
        raise internal_server_error(e, logger, "Error fetching recent migrations") from e
