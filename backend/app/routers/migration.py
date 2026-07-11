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
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field

from app.crud import activity_crud, mappings_crud, migration_script_crud, notification_crud

# CRUDs ORM
from app.crud.project_crud import ProjectCRUD
from app.database.session import get_db_session
from app.models.db_metadata.constraint import ForeignKeyMetadata
from app.models.db_metadata.schema import SchemaMetadata
from app.models.db_metadata.table import TableMetadata
from app.routers.dependencies import get_current_user
from app.services.db_connection_service import (
    DBConnectionService,
    SessionExpiredError,
    SessionNotFoundError,
)
from app.services.dependency_graph_service import DependencyGraphService
from app.services.execution_service import ExecutionService
from app.services.migration_script_service import MigrationScriptService
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


class ExecutionRequest(BaseModel):
    """Request para ejecutar una migración"""

    script_id: Optional[str] = Field(
        default=None, description="UUID del script guardado (opcional)"
    )
    dry_run: bool = Field(default=False, description="Si True, ejecuta ROLLBACK al final")
    dest_connection_session_id: str = Field(
        ..., description="UUID de la sesión de conexión destino"
    )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def validate_project_access(db, project_id: str, current_user: dict) -> dict:
    """
    Valida que el usuario tenga acceso al proyecto usando CRUD ORM.

    Args:
        db: Database session
        project_id: UUID del proyecto
        current_user: Usuario autenticado

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

    return project


def get_project_mappings(db, project_id: str) -> List[Dict[str, Any]]:
    """
    Obtiene todos los mappings de un proyecto usando CRUD ORM.

    Args:
        db: Database session
        project_id: UUID del proyecto

    Returns:
        Lista de mappings
    """
    # Obtener mappings usando CRUD ORM
    mappings = mappings_crud.get_mappings_by_project_orm(db, project_id, encryption_key=None)

    # Ordenar por destination_table y destination_column
    return sorted(
        mappings, key=lambda m: (m.get("destination_table", ""), m.get("destination_column", ""))
    )


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
async def generate_migration_script(
    project_id: str,
    options: MigrationScriptOptions,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
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
        # PASO 1: Validar acceso al proyecto
        project = validate_project_access(db, project_id, current_user)
        logger.info(f"Generating migration script for project {project_id} ({project['name']})")

        # PASO 2: Obtener mappings del proyecto
        mappings = get_project_mappings(db, project_id)

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

        # PASO 5: Generar script usando MigrationScriptService
        # Nota: origin_adapter y dest_adapter son None porque los mappings
        # no usan hashes en este caso (son nombres directos)
        script = MigrationScriptService.generate_insert_script(
            mappings=[dict(m) for m in mappings],
            origin_adapter=None,
            dest_adapter=None,
            project_name=project["name"],
            dependency_order=dependency_order if dependency_order else None,
            batch_size=options.batch_size,
            include_constraints=options.include_constraints,
            include_validation=options.include_validation,
            dialect=options.dialect,
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
            dialect=options.dialect,
            dependency_order=dependency_order if dependency_order else [],
            created_by=str(current_user["id"]),
        )

        script_id = saved_script["id"]
        logger.info(f"Script saved with ID: {script_id}")

        # PASO 8: Log activity
        tables_count = len(dependency_order) if dependency_order else len(set(m["destination_table"] for m in mappings))
        activity_crud.create_activity_log_orm(
            db=db,
            project_id=project_id,
            user_id=str(current_user["id"]),
            activity_type="migration:script_generated",
            description=f"Migration script generated: {tables_count} tables, dialect={options.dialect}",
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
    except Exception as e:
        logger.error(f"Error generating migration script: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating migration script: {str(e)}",
        )


@router.post(
    "/{project_id}/migration/execute",
    summary="Execute migration",
    description="Ejecuta script de migración contra la base de datos destino",
)
async def execute_migration(
    project_id: str,
    request: ExecutionRequest,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
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
        # PASO 1: Validar acceso al proyecto
        project = validate_project_access(db, project_id, current_user)
        logger.info(f"Executing migration for project {project_id}")

        # PASO 2: Obtener o generar script
        if request.script_id:
            # Cargar script guardado usando CRUD ORM
            script_row = migration_script_crud.get_migration_script_by_id_orm(
                db, request.script_id, project_id
            )

            if not script_row or str(script_row.get("project_id")) != str(project_id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Script not found"
                )

            script = script_row["script_content"]
            logger.info(f"Loaded saved script: {request.script_id}")
        else:
            # Generar nuevo script on-the-fly
            mappings = get_project_mappings(db, project_id)

            if not mappings:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No mappings found for this project",
                )

            script = MigrationScriptService.generate_insert_script(
                mappings=[dict(m) for m in mappings],
                origin_adapter=None,
                dest_adapter=None,
                project_name=project["name"],
            )
            logger.info("Generated new script on-the-fly")

        # PASO 3: Obtener adapter de conexión destino
        db_service = get_db_connection_service()

        try:
            session = db_service.get_session(current_user["id"], request.dest_connection_session_id)
        except SessionNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Destination connection session not found",
            )
        except SessionExpiredError:
            raise HTTPException(
                status_code=status.HTTP_410_GONE, detail="Destination connection session expired"
            )

        # Descifrar config y obtener adapter
        config = db_service.get_decrypted_config(session)
        dest_adapter = db_service._get_adapter(config)

        # Conectar adapter
        dest_adapter.connect()
        logger.info(f"Connected to destination database: {config.dialect}")

        # PASO 4: Ejecutar migración usando ExecutionService
        execution_service = ExecutionService()

        result = execution_service.execute_migration(
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
            notif_body = f"Project '{project['name']}': {result.get('rows_affected', 0)} rows migrated."
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
        logger.error(f"Error executing migration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error executing migration: {str(e)}",
        )


@router.get(
    "/{project_id}/migration/executions/{execution_id}",
    summary="Get execution status",
    description="Consulta el estado y progreso de una ejecución de migración",
)
async def get_execution_status(
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

        # PASO 3: Calcular progreso desde el execution_log
        import json

        exec_status = execution.get("status", "pending")
        execution_log = execution.get("execution_log", [])
        log = json.loads(execution_log) if isinstance(execution_log, str) else (execution_log or [])

        if exec_status in ("success", "failed", "dry_run_complete"):
            progress_percent = 100
        else:
            total_statements = None
            for entry in log:
                if entry.get("type") == "metadata":
                    total_statements = entry.get("total_statements")
                    break
            completed = len(
                [e for e in log if e.get("step", 0) > 0 and e.get("status") == "success"]
            )
            if total_statements and total_statements > 0:
                progress_percent = min(int((completed / total_statements) * 100), 99)
            else:
                progress_percent = 0

        # PASO 4: Determinar step actual del execution_log
        current_step = "Initializing..."
        step_entries = [e for e in log if e.get("step", 0) > 0]
        if step_entries:
            last_step = step_entries[-1]
            current_step = f"Step {last_step.get('step', 0)}: {last_step.get('table', 'Unknown')}"

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
        logger.error(f"Error getting execution status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting execution status: {str(e)}",
        )


@router.get(
    "/{project_id}/migration/executions",
    summary="List executions",
    description="Lista todas las ejecuciones de migración del proyecto",
)
async def list_executions(
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
        logger.error(f"Error listing executions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing executions: {str(e)}",
        )


@router.get(
    "/{project_id}/migration/dependency-graph",
    summary="Get dependency graph",
    description="Obtiene el grafo de dependencias entre tablas para visualización",
)
async def get_dependency_graph(
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
                session = db_service.get_session(current_user["id"], dest_connection_session_id)
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
        logger.error(f"Error getting dependency graph: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting dependency graph: {str(e)}",
        )


@global_router.get(
    "/recent",
    summary="Recent migrations",
    description="Returns the latest migration executions across all accessible projects",
)
async def get_recent_migrations(
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
        logger.error(f"Error fetching recent migrations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching recent migrations: {str(e)}",
        )
