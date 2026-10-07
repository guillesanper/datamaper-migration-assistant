# SQL legado (archivado, no se ejecuta)

Los ficheros de este directorio son el esquema y las migraciones SQL **anteriores a Alembic**. Se conservan solo como referencia histórica: **ninguno se ejecuta ya**, ni al arrancar `docker compose`, ni desde los tests, ni desde la aplicación.

El esquema de la base de datos sale ahora únicamente de `alembic upgrade head` (cadena `0001_baseline` → `0002_db_functions` en `backend/alembic/versions/`). Ver [../how_to_export_db_pgadmin.md](../how_to_export_db_pgadmin.md) para crear la BD y añadir migraciones.

> No uses estos ficheros para crear ni actualizar una BD: no reflejan el esquema actual (ver «Qué se portó y qué no») y aplicarlos encima de Alembic dejaría la BD en un estado que `alembic check` no reconoce.

## Contenido

| Fichero | Qué era |
|---|---|
| `schema.sql` | Esquema base inicial en SQL de texto (usuarios, proyectos, miembros, esquemas…) |
| `backup_schema.sql` | **No es SQL de texto**: es un `pg_dump -Fc` (formato custom, `PGDMP`, v17.6). Se lee con `pg_restore -l` / `pg_restore -s`. Contiene además 2 triggers y 3 funciones que no están en el resto del SQL legado |
| `migration_001_collaboration_versioning.sql` | Colaboración y control de versiones: `entity_versions`, `comments`, `entity_locks`, `project_activity`, funciones, triggers y vistas |
| `migrations/001_composite_primary_keys.sql` y `…_rollback.sql` | Claves primarias compuestas y su rollback |
| `migrations/002_add_serial_to_pk_constraints.sql` | Secuencia de auto-incremento en `primary_key_constraints` |
| `migrations/002_fix_pk_constraints_id.sql` | `primary_key_constraints.id` de UUID a `SERIAL` |
| `migrations/002_migration_tables.sql` | `migration_scripts` y `migration_executions` |
| `migrations/003_encryption_infrastructure.sql` | Infraestructura de cifrado (`project_encryption`, auditoría, funciones) |
| `migrations/004_fix_encryption_nullable_fields.sql` | Campos cifrados nulables |
| `migrations/005_mapping_source_types.sql` | Mappings híbridos (import + connector), funciones, trigger y vista |
| `migrations/006_migration_execution_tables.sql` | Tablas de ejecución de migraciones |

## Qué se portó y qué no

Las **tablas, columnas, índices y constraints** de estos ficheros ya están en `0001_baseline.py`, generado desde los modelos ORM (`backend/app/models/orm/`). Los `DEFAULT` de columna que el legado tenía en BD y los modelos habían perdido se recuperaron como `server_default` (10 columnas).

Respecto a funciones, triggers y vistas, que los modelos no crean, la auditoría ([../ALEMBIC_BASELINE_AUDIT.md](../ALEMBIC_BASELINE_AUDIT.md)) decidió:

| Objeto | Destino |
|---|---|
| `log_version_activity()` + trigger en `entity_versions` | **Portado** a `0002_db_functions.py`, corrigiendo `restore` (el `CASE` no tenía `ELSE` y dejaba `description` en `NULL`) |
| `log_comment_activity()` + trigger en `comments` | **Portado** a `0002_db_functions.py` |
| `calculate_and_save_user_metrics(uuid)` | **Escrita desde cero** en `0002_db_functions.py`: no existía en ninguna fuente legada |
| `cleanup_expired_locks()`, `get_next_version_number(uuid)`, `purge_old_encrypted_data(uuid, int)` | **No portadas**: solo las llaman wrappers psycopg2 inalcanzables |
| Triggers `update_project_encryption_timestamp`, `prevent_mode_change`, `trigger_subscription_plans_updated_at`, `trigger_update_rate_limits_timestamp` y sus funciones | **No portados** (los modelos ya tienen `onupdate`; ninguna salvaguarda tiene consumidores) |
| Vistas `v_entity_versions_with_user`, `v_comments_with_details`, `v_active_locks`, `v_mappings_with_modes` | **No portadas** (ninguna se usa desde `app/`, tests ni frontend) |
| Resto de funciones auxiliares (`get_project_encryption_stats`, `get_project_mapping_mode_stats`, `check_mapping_sessions_valid`, `cleanup_orphaned_connector_mappings`, `cleanup_old_rate_limits`, `cleanup_security_data`) | **No portadas** (sin uso) |

Por tanto, estos `.sql` definen funciones, triggers y vistas que **ya no existen** en la base de datos. Si alguna hiciera falta, se añade como migración nueva de Alembic (no ejecutando el SQL de aquí).

## Notas

- De `backend/utilities/` solo queda `migrations/validators.py`, porque `app/services/execution_service.py` importa `BackupManager` de `utilities.migrations.validators`. Los scripts que dependían de este SQL (`run_migration_00X.py`, `check_migration_status.py`) se eliminaron.
- Documentos antiguos (`MIGRATION_API_IMPLEMENTATION.md`, `IMPLEMENTATION_PLAN.md`, `docs/COLLABORATION_SYSTEM_README.md`…) son históricos: llevan una nota al inicio y sus rutas apuntan aquí, a `legacy_sql/`.
- Recuperar el estado anterior a Alembic: tag `pre-alembic-baseline` (commit `de5a54b`).
