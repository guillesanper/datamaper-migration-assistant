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
