# Auditoría de dependencias de BD fuera del ORM (Fase 1)

Inventario de todo lo que la aplicación necesita de la base de datos y que **no** crean los modelos ORM (`Base.metadata`), para decidir qué debe llevar la cadena Alembic además del baseline. Es la entrada de las Fases 2 y 3 del plan de baseline de Alembic.

- Fecha: 2026-10-05. Rama `fix/alembic-baseline`, partiendo de `bdeae48`.
- Alcance: solo lectura. No se ha tocado código de la app, modelos ni migraciones.
- Estado del baseline de partida: `alembic.gen.ini` + `alembic/_gen/0001_baseline.py` sobre una BD vacía crea **30 tablas** (+ `alembic_version`), **0 funciones propias y 0 triggers** (comprobado con `pg_proc` / `pg_trigger`).

## Resumen

| Concepto | Cifra |
|---|---|
| Funciones propias de BD invocadas desde `app/` | **4** (el plan sospechaba 3; falta `calculate_and_save_user_metrics`) |
| …de ellas definidas en algún SQL legado | 3 (`calculate_and_save_user_metrics` **no está definida en ningún sitio**) |
| …de ellas alcanzables desde un router o el arranque | **0** |
| `INSERT INTO` crudos en `app/crud` y `app/services` | **19** |
| …que omiten alguna columna `NOT NULL` sin `server_default` | **7 INSERT / 9 columnas** (el plan sospechaba 3 INSERT) |
| …de ellos alcanzables desde un router | 1 (`POST /api/projects/{id}/migration/execute`, omite `rows_migrated`) |
| Triggers en el legado | **6** (4 en SQL de texto + 2 solo en el dump `backup_schema.sql`) |
| Vistas en el legado | 4 (ninguna usada por `app/`, tests ni frontend) |
| Triggers con dependencia real del código | 2 (`log_version_activity`, `log_comment_activity`) |

## Método y reproducibilidad

- **Funciones SQL**: extracción con `ast` de todos los literales SQL de `app/` y nombres de función que invocan, descontando las nativas de PostgreSQL (`array_position`, `pg_get_constraintdef`, `pg_total_relation_size`, `pg_advisory_xact_lock`, `hashtext`…). Contraste con `grep` de `SELECT fn(` y de cada nombre en todo el repo.
- **INSERT**: extracción con `ast` de los literales con `INSERT INTO t (cols)` en `app/crud` y `app/services` (excluido `migration_script_service.py`, que *genera* SQL para BD ajenas). Las columnas `NOT NULL` sin `server_default` se derivan de `Base.metadata` ejecutando en el contenedor del backend (3.11), no de leer los modelos. Se contrastó contra una BD real creada con el baseline (`information_schema.columns`: `is_nullable='NO' AND column_default IS NULL`): **0 discrepancias en los 19 INSERT**. Los `id` enteros PK (serial) no cuentan como omisión.
- **Alcanzabilidad**: grafo de llamadas con `ast` desde cada función decorada con `@router.*`/`@app.*` (y desde `main.py`), resolviendo `módulo.función`, `Clase.método` y `self.método`; para receptores desconocidos (instancias) hay un fallback conservador por nombre de método (sobreaproxima: lo que sale «no alcanzable» lo es). Se validó a mano con `grep` (sección 1). Todos los routers están incluidos en `main.py` (líneas 127–157).
- **Dump `backup_schema.sql`**: no es SQL de texto sino un `pg_dump` en formato custom (`PGDMP`, v17.6). Se inspeccionó con `pg_restore -l` y `pg_restore -s` en un contenedor `postgres:17` temporal sin red.
- Limitación: el análisis de alcanzabilidad es estático; no ve despacho dinámico (`getattr`, registro por nombre). No se ha auditado el resto del código muerto, solo el que cuelga de lo inventariado.

## 1. Funciones SQL invocadas desde `app/`

| Función | Llamada en `app/` | Definición en el legado | ¿Alcanzable desde router/servicio? |
|---|---|---|---|
| `cleanup_expired_locks()` | `app/crud/locks_crud.py:245`, dentro de `cleanup_expired_locks` (psycopg2), llamada por `acquire_lock` (:31), `get_lock_status` (:122) y `get_active_locks` (:198), todas crudas | `utilities/migration_001_collaboration_versioning.sql:235-246` (`RETURNS INTEGER`, borra `entity_locks` con `expires_at < NOW()`) | **No.** `locking_service.py` solo usa las variantes `*_orm` (`cleanup_expired_locks_orm`, `acquire_lock_orm`…). Ningún test llama a las crudas. Solo la documenta `docs/COLLABORATION_SYSTEM_README.md:639` como comando manual |
| `get_next_version_number(uuid)` | `app/crud/versions_crud.py:208`, dentro de `get_next_version_number` (psycopg2) | `utilities/migration_001_collaboration_versioning.sql:251-263` (`COALESCE(MAX(version_number),0)+1` sobre `entity_versions`) | **No.** `version_control_service.create_version` usa `get_next_version_number_orm` (`version_control_service.py:94`). Nadie llama a la cruda |
| `purge_old_encrypted_data(uuid, int)` | `app/services/data_retention_service.py:59` (`SELECT * FROM purge_old_encrypted_data(%s, %s)`), en `DataRetentionService.purge_old_encrypted_data`; la usan `schedule_automatic_purge` (:407) y `run_daily_purge` (:479-486, APScheduler `cron`) | `utilities/migrations/003_encryption_infrastructure.sql:313-368` (`RETURNS TABLE(versions_deleted, comments_deleted, activity_deleted)`) | **No.** Ningún fichero importa `data_retention_service` (`grep -rn data_retention_service . --include=*.py` no devuelve ninguna importación) y `main.py` no arranca ningún scheduler |
| `calculate_and_save_user_metrics(uuid)` | `app/crud/project_crud.py:884` y `:973` (`ProjectCRUD.get_user_metrics_comparison_orm`, `force_recalculate_user_metrics_orm`, vía `text()`); `:1105` y `:1223` (versiones psycopg2 `get_user_metrics_comparison`, `force_recalculate_user_metrics`) | **No definida en ningún sitio**: ni en los `.sql` de texto, ni en el dump `backup_schema.sql`, ni en las 6 revisiones Alembic antiguas, ni en `scripts/` | **No.** Su único camino es `ProjectService.get_user_stats` (`project_service.py:511`), que ningún router llama: `GET /api/projects/stats` (`routers/projects.py:52`) calcula inline con `SELECT … FROM projects`. Solo lo ejercitan tests unitarios con mocks (`test_project_service.py:707,736`) |

Funciones nativas de PostgreSQL usadas en SQL crudo de `app/` (no requieren portado): `pg_advisory_xact_lock(hashtext(...))` (`project_service.py:122`), `array_position` (`pk_crud.py:78`), `pg_get_constraintdef`, `pg_total_relation_size` (`db_adapters/postgres_adapter.py`; consultan BD de usuario, no la de la app). `gen_random_uuid()` solo aparece como `server_default` de un modelo (`subscription.py:103`); `uuid_generate_v4()` solo en `test/test_worker_isolation.py:58,94` (requiere la extensión `uuid-ossp`, que ya instala el baseline).

**Efecto lateral relevante:** `GET /api/projects/metrics/history` **sí** es alcanzable (`routers/projects.py:148` → `ProjectService.get_metrics_history` → `get_user_metrics_history_orm`) y lee `project_metrics_history`, pero **nada escribe nunca en esa tabla** (la función que la rellenaría no existe). Hoy ya devuelve siempre una lista vacía.

## 2. `INSERT INTO` crudos (19) y columnas `NOT NULL` sin `server_default` que omiten

Solo cuentan las columnas `NOT NULL`, sin `server_default` y no serial. Las que fallan en una BD de Alembic aparecen en negrita. En todas existe un `default` de Python (`False`, `0`, `uuid.uuid4`) que un INSERT crudo no aplica, y **el SQL legado sí tenía un `DEFAULT` en BD** (`is_edited BOOLEAN DEFAULT FALSE`, `rows_migrated INTEGER DEFAULT 0`, etc.), de modo que el modelo ORM perdió ese default al sustituir al dump.

| # | Fichero:línea | Tabla | Función contenedora | ¿Alcanzable? | Columnas omitidas (NOT NULL, sin server_default) |
|---|---|---|---|---|---|
| 1 | `crud/activity_crud.py:29` | `project_activity` | `create_activity_log` | No (se usa `create_activity_log_orm`) | — |
| 2 | `crud/comments_crud.py:29` | `comments` | `create_comment` | No | **`is_encrypted`, `is_edited`, `is_resolved`** (BOOLEAN, py `False`) |
| 3 | `crud/comments_crud.py:216` | `comment_reads` | `mark_as_read` | No | **`id`** (UUID, py `uuid4`) |
| 4 | `crud/locks_crud.py:65` | `entity_locks` | `acquire_lock` | No | — |
| 5 | `crud/mappings_crud.py:137` | `mappings` | `create_mapping` | No | — |
| 6 | `crud/master_key_crud.py:67` | `project_encryption` | `create_project_encryption` | No | — |
| 7 | `crud/pk_crud.py:160` | `primary_key_constraints` | `create_pk_constraint` | No | **`id`** (UUID, py `uuid4`) |
| 8 | `crud/pk_crud.py:171` | `primary_key_constraints` | `create_pk_constraint` | No | — (esta variante sí pasa `id`) |
| 9 | `crud/pk_crud.py:305` | `migration_audit_log` | `insert_audit_log` | No | **`id`** (UUID, py `uuid4`) |
| 10 | `crud/project_crud.py:50` | `projects` | `create_project` | No (se usa la vía ORM) | — |
| 11 | `crud/reactions_crud.py:20` | `comment_reactions` | `add_reaction` | No | — |
| 12 | `crud/schemas_crud.py:82` | `tables` | `create_table` | No | — |
| 13 | `crud/schemas_crud.py:95` | `tables` | `create_table` | No | **`is_encrypted`** (BOOLEAN, py `False`) |
| 14 | `crud/schemas_crud.py:471` | `columns` | `create_column` | No | — |
| 15 | `crud/schemas_crud.py:500` | `columns` | `create_column` | No | **`is_encrypted`** (BOOLEAN, py `False`) |
| 16 | `crud/subscription_crud.py:159` | `subscriptions` | `create_subscription` | No | — |
| 17 | `crud/tags_crud.py:28` | `version_tags` | `create_tag` | No | — |
| 18 | `crud/versions_crud.py:42` | `entity_versions` | `create_version` | No | — |
| 19 | `services/execution_service.py:222` | `migration_executions` | `_create_execution_record` | **Sí**: `POST /api/projects/{project_id}/migration/execute` (`routers/migration.py:310`) → `ExecutionService().execute_migration` → `_create_execution_record` | **`rows_migrated`** (INTEGER, py `0`) |

Notas:
- Los INSERT 1–18 pertenecen a funciones crudas sin llamadas en `app/` (todas tienen variante `*_orm`). Los INSERT problemáticos 2, 3, 7 y 9 tampoco los llama ningún test. Los 13 y 15 (`schemas_crud.create_table`/`create_column`) solo los llama `test/e2e/test_encryption_full_flow.py`, que la línea base de la Fase 0 no ejecuta (excluye `test/e2e`). `tags_crud.create_tag` (INSERT 17, sin omisiones) sí se ejercita en `test/integration/test_tags_crud_integration.py`. No se ha verificado qué variante de INSERT ejecuta cada test.
- El 19 es el único defecto que un usuario puede provocar hoy en una BD creada solo por Alembic (y también con `create_all`: el modelo no tiene `server_default`; solo el SQL legado, `006_migration_execution_tables.sql:22`, lo tenía).
- Los defectos que el plan ya sospechaba (INSERT 2, 7 y 9) se confirman; los INSERT 3, 13, 15 y 19 son nuevos.
- Propuesta para la Fase 3 (sin aplicar aún): `server_default=sa.false()` en los BOOLEAN, `gen_random_uuid()` en los `id` UUID y `server_default='0'` en `rows_migrated`, manteniendo el `default` de Python.

## 3. Triggers, vistas y funciones auxiliares del legado

Fuentes: `utilities/migration_001_collaboration_versioning.sql`, `utilities/migrations/003_encryption_infrastructure.sql`, `utilities/migrations/005_mapping_source_types.sql`, `utilities/schema.sql` y el dump `utilities/backup_schema.sql`. Los demás `.sql` de `utilities/migrations/` (001, 002, 004, 006) no definen funciones, triggers ni vistas.

### 3.1 Triggers (6)

| Trigger → función | Fuente | Efecto | ¿Depende algo del código o de los tests? |
|---|---|---|---|
| `trigger_log_version_activity` → `log_version_activity()` | `migration_001…sql:268-305` | `AFTER INSERT` en `entity_versions`: inserta en `project_activity` un `version_created` con `description` = `creó/actualizó/eliminó` + tipo | **Sí (código).** `version_control_service.py:118`: `# Log activity (done by trigger in database)`; `create_version_orm` no escribe actividad. El feed del frontend (`team/ActivityFeed.tsx`, `version_control/ActivityFeed.tsx`) pinta `version_created`. **Ningún test lo comprueba** (los tests con BD real que crean versiones no miran `project_activity`). **Fallo heredado:** `CASE` sin `ELSE` → con `change_type='restore'` (lo que usa `restore_version`, `version_control_service.py:229`) la `description` sale `NULL` y `project_activity.description` es `NOT NULL`: la restauración fallaría en una BD con este trigger tal cual |
| `trigger_log_comment_activity` → `log_comment_activity()` | `migration_001…sql:308-343` | `AFTER INSERT` en `comments` (solo `parent_id IS NULL`): inserta `comment_added` | **Sí (código).** `comments_service.py:65-66`: `# Log activity (done by trigger, but only for top-level comments)`. Sin test |
| `trigger_update_project_encryption_timestamp` → `update_project_encryption_timestamp()` | `003_encryption…sql:378-389` | `BEFORE UPDATE` en `project_encryption`: `updated_at = NOW()` | **No.** Los `UPDATE` crudos ya fijan `updated_at` (`master_key_crud.py:232,596`), la vía ORM lo hace (`:845`) y el modelo tiene `onupdate=func.now()` (`encryption.py:62`) |
| `trigger_prevent_mapping_mode_change` → `prevent_mode_change()` | `005_mapping_source_types.sql:398-424` | `BEFORE UPDATE` en `mappings`: lanza excepción si cambia `origin/destination_source_type` | **No.** Ni `update_mapping` ni `update_mapping_orm` tocan `*_source_type`; ningún test espera esa excepción. Es una salvaguarda de integridad sin consumidores |
| `trigger_subscription_plans_updated_at` → `update_subscription_plans_updated_at()` | **solo** dump `backup_schema.sql` | `BEFORE UPDATE` en `subscription_plans` | **No.** El modelo tiene `onupdate=func.now()` (`subscription.py:74,147`) y `app/` no hace `UPDATE subscription_plans` crudo |
| `trigger_update_rate_limits_timestamp` → `update_rate_limits_timestamp()` | **solo** dump `backup_schema.sql` | `BEFORE UPDATE` en `security_rate_limits` | **No.** `security.py:114-118` tiene `onupdate`; sin `UPDATE` crudo en `app/` |

### 3.2 Vistas (4)

| Vista | Fuente | ¿Dependencia? |
|---|---|---|
| `v_entity_versions_with_user` | `migration_001…sql:350` | **No.** Sin referencias en `app/`, `test/`, `scripts/` ni frontend |
| `v_comments_with_details` | `migration_001…sql:362` | **No** (ídem) |
| `v_active_locks` | `migration_001…sql:377` | **No** (ídem) |
| `v_mappings_with_modes` | `005_mapping_source_types.sql:349` | **No.** Solo la menciona `utilities/migrations/run_migration_005.py:141`, un verificador del propio SQL legado |

### 3.3 Funciones auxiliares definidas en el legado y no invocadas por `app/`

| Función | Fuente | ¿Dependencia? |
|---|---|---|
| `get_project_encryption_stats(uuid)` | `003_encryption…sql:242` | No (solo `docs/ENCRYPTION_SETUP.md:89`) |
| `get_project_mapping_mode_stats(uuid)`, `check_mapping_sessions_valid(uuid)`, `cleanup_orphaned_connector_mappings(uuid[])` | `005_mapping…sql:218,266,315` | No (solo las lista `run_migration_005.py:124-126`) |
| `cleanup_old_rate_limits()` | `schema.sql:242` | No |
| `cleanup_security_data()` | **solo** dump `backup_schema.sql` | No |

## 4. Hallazgos que amplían o corrigen lo sospechado en el plan

1. **Falta una función en la lista**: `calculate_and_save_user_metrics(uuid)` (4 llamadas) y no existe definición en ninguna fuente. No es «portar», es un hueco de diseño.
2. **`backup_schema.sql` no es SQL de texto** sino un dump `pg_dump -Fc`, y contiene 2 triggers y 3 funciones que no están en el resto del legado.
3. **Más INSERT problemáticos** de los 3 esperados: 7 INSERT omiten alguna columna (9 columnas en total), y uno de ellos (`migration_executions`) es alcanzable desde un endpoint.
4. **Las 3 funciones que el plan daba por «llamadas por la app» solo las llaman wrappers psycopg2 sin uso**; los servicios ya migraron a las variantes `*_orm`. Esto afecta a la lista de T4.
5. **Los triggers de actividad sí tienen dependencia funcional**, pero solo indicada en comentarios y en la UI; ningún test la cubre, por lo que la suite actual no detectaría su ausencia.
6. **Bug heredado** en `log_version_activity` con `change_type='restore'` (ver 3.1).

## 5. Decisiones de la Puerta 1 (usuario, 2026-10-05)

| Objeto | Decisión |
|---|---|
| Triggers `log_version_activity` y `log_comment_activity` (con sus funciones) | **Portar ambos** a la revisión `0002`, **corrigiendo `restore`**: `log_version_activity` con un `ELSE` para cualquier `change_type` no previsto, de modo que `description` nunca sea `NULL`. Añadir en la Fase 2 un test (T6) que cree una versión (también `restore`) y un comentario raíz y compruebe la fila en `project_activity` |
| `calculate_and_save_user_metrics(uuid)` | **Escribirla desde cero** (no hay legado que portar). Diseño a deducir de `project_metrics_history` (upsert del snapshot del día por `user_id`: contadores por `status`, `SUM(budget)`, `AVG(progress)` sobre `projects` del usuario con `is_deleted = FALSE`) y a validar con el usuario antes de darla por buena |
| `cleanup_expired_locks()`, `get_next_version_number(uuid)`, `purge_old_encrypted_data(uuid,int)` | **No portar** («elimina lo que no se llame nunca»). Pendiente de confirmar si además se retiran los wrappers muertos de `app/` (cambio de código fuera de este plan) |
| Triggers `update_project_encryption_timestamp`, `prevent_mode_change` y los 2 solo-dump; 4 vistas; funciones auxiliares sin uso | **No portar** (sin dependencia; decisión por defecto del plan) |

## 6. Código muerto detectado (informativo, no se ha tocado)

Cuelgan de lo inventariado y no se llaman desde ningún router, servicio ni arranque:

- `app/crud/locks_crud.py`: `cleanup_expired_locks`, y las crudas `acquire_lock`, `get_lock_status`, `get_active_locks` que la usan.
- `app/crud/versions_crud.py`: `get_next_version_number`.
- `app/services/data_retention_service.py` completo (nadie lo importa).
- `app/crud/project_crud.py`: `get_user_metrics_comparison`, `force_recalculate_user_metrics` (psycopg2) y las variantes `_orm` que usan `calculate_and_save_user_metrics`; y `ProjectService.get_user_stats`.
- Las 15 funciones contenedoras distintas de los INSERT 1–18 de la sección 2 (variantes crudas con equivalente `*_orm`), aunque varias las usan tests con BD real.

No se ha auditado el resto del código muerto del repositorio.
