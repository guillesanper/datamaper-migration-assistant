# Línea base de tests (Fase 0)

Resultado de la suite sobre el código original (tag `pre-alembic-baseline`, commit `de5a54b`),
cuyo esquema de test se crea con `Base.metadata.create_all`. Sirve como referencia para el
criterio A7 del plan: ningún test que pasaba aquí puede fallar tras el cambio a Alembic.

| Fichero | Contenido |
|---|---|
| `baseline_before.xml` | JUnit XML completo |
| `baseline_before_summary.txt` | Totales y lista de fallados/errores/saltados con su causa |
| `baseline_before_passed.txt` | Los 1495 tests que pasan (para comparar con `baseline_after`) |

## Cómo se generó

```bash
git worktree add --detach <dir>/wt-baseline pre-alembic-baseline
backend/scripts/run_tests_in_container.sh <dir>/wt-baseline/backend <dir_salida> baseline_before
```

Ejecuta `pytest test/unit test/integration -m "not slow" --maxfail=0 -p no:cacheprovider` en la
imagen del backend (Python 3.11), con un Redis en el puerto 6380 y el Postgres de docker-compose.

## Resultado

`19 failed, 1495 passed, 1 skipped, 31 errors` (1546 tests). Dos pasadas seguidas dieron el mismo
conjunto de tests pasados y de fallados (solo cambia el sufijo aleatorio del username en un mensaje).

Los 50 fallos/errores ya existían antes de tocar nada y no tienen que ver con el esquema:

| Grupo | Nº | Causa |
|---|---|---|
| `test_db_connection_flow` (13 fallos + 17 errores) | 30 | Necesitan un Postgres en `localhost:5433` y un MySQL en `localhost` (según los errores de conexión; ver `docker-compose.test.yml`), que el arnés no levanta |
| `test_migration_api` (14 errores) | 14 | `from conftest import ...` falla con `--import-mode=importlib` (que fija `pytest.ini`) |
| `test_schema_service` | 2 | El test espera un texto en español y el servicio devuelve `{'code': 'schema.…'}` (refactor i18n) |
| `test_csrf_protection_middleware` | 1 | Igual: espera texto y recibe `{'code': 'security.csrf_token_invalid'}` |
| `test_tags_crud_integration` | 2 | `creator_username` no coincide con el usuario del fixture |
| `test_project_service` | 1 | `delete_project` no lanza `HTTPException` con miembros |

## Después del cambio (Fase 4)

Misma suite y mismo arnés sobre el código con la cadena Alembic nueva (`0001_baseline` + `0002_db_functions`),
con el esquema de test creado por `alembic upgrade head`.

| Fichero | Contenido |
|---|---|
| `baseline_after.xml` | JUnit XML completo |
| `baseline_after_summary.txt` | Totales y lista de fallados/errores/saltados con su causa |
| `baseline_after_passed.txt` | Los 1510 tests que pasan |

```bash
backend/scripts/run_tests_in_container.sh <dir>/backend <dir_salida> baseline_after
diff baseline_before_passed.txt baseline_after_passed.txt   # solo líneas ">" (nuevos)
```

Resultado: `19 failed, 1510 passed, 1 skipped, 31 errors` (1561 tests). Frente a la línea base:

- **0 tests que pasaban antes y fallan ahora** (`comm -23` de las listas de pasados: vacío).
- **+15 pasados**, todos de `test_alembic_migrations.py` (no existían antes).
- Los mismos 50 fallos/errores, uno a uno (`test_tags_crud_integration` incluido: sus 2 tests pasan si el
  fichero se ejecuta solo, 12/12, pero fallan dentro de la suite completa igual que en la línea base).

## Después de retirar los CRUD psycopg2 (Fase B de la retirada de psycopg2)

`baseline_after.xml`, `baseline_after_passed.txt` y `baseline_after_summary.txt` se regeneraron con la
misma suite y arnés sobre el código sin las variantes psycopg2 de `app/crud/*`, sin `get_db` ni
`data_retention_service`, y con `mappings.py`, `stripe_service`, `execution_service` y
`BackupManager` migrados a sesiones SQLAlchemy.

Resultado: `17 failed, 1532 passed, 1 skipped, 31 errors` (1581 tests). Frente a la línea base anterior (1510 pasados):

- **0 tests que pasaban y fallan ahora**, salvo los **18 retirados** porque su único sujeto era código retirado:
  - `test_tags_crud_integration` (10 pasados): probaba `tags_crud` crudo; el equivalente `_orm` lo cubre `test_tags_crud_orm`.
  - `test_database.TestGetDb` (8): probaba `app.database.database.get_db`.
- **+40 pasados** nuevos: `test_mappings_router_endpoints.py` (34, endpoints `export`, `tables`, `validate`,
  `import_structure`, `generate-migration-script` y permisos de `save`/`delete`, que no tenían tests) y
  `test_execution_service_db.py` (6, SQL real de `ExecutionService`, `BackupManager` y `MigrationValidator`).
- Los mismos 48 fallos/errores ajenos; desaparecen los 2 de `test_tags_crud_integration` junto con el fichero.
- `test_t3_extractor_reads_every_raw_insert`: el umbral pasó de `>= 19` a `>= 1`, porque los 18 INSERT crudos
  restantes pertenecían a los CRUD retirados; solo queda el de `ExecutionService`.

Fuera de esta suite (la línea base solo ejecuta `test/unit` y `test/integration`), `test/e2e` y
`test/test_worker_isolation.py` dan 36 pasados antes y después de la retirada (y los mismos 44 fallos de
conexión a BD de usuario).

Los ficheros se generan desde el JUnit XML: pasados como `classname::name` ordenado con LF, y el resumen con
los totales y la lista de fallados/errores/saltados (primera línea del mensaje).
