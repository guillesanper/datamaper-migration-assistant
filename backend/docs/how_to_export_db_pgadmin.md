# Base de datos: creación con Alembic y cambios de esquema

El esquema de la base de datos sale **únicamente de `alembic upgrade head`**. Ya no hay dump SQL ni carpeta `backend/init-db/`: una BD vacía llega al esquema completo aplicando la cadena de `backend/alembic/versions/`.

> Este fichero se llamaba «cómo exportar la BD desde pgAdmin» y explicaba cómo cargar un dump en `init-db/`. Ese flujo ya no existe. El nombre se mantiene para no romper enlaces.

## Crear la base de datos desde cero

Con Docker Compose, desde la raíz del repo:

```bash
docker compose up -d
```

El comando del servicio `backend` es `alembic upgrade head && uvicorn main:app …`, así que el contenedor crea el esquema al arrancar. Si la BD ya está en el último `head`, `upgrade head` no hace nada.

Para partir de una BD vacía (no hay datos que conservar ni datos semilla):

```bash
docker compose down -v      # elimina también el volumen de PostgreSQL
docker compose up -d
```

Comprobaciones útiles (dentro del contenedor del backend):

```bash
docker exec datamap-backend alembic current   # revisión aplicada (hoy: 0002 (head))
docker exec datamap-backend alembic heads     # debe haber un único head
docker exec datamap-backend alembic check     # "No new upgrade operations detected."
```

Sin Docker, desde `backend/` y con las variables `DB_*` del `.env` apuntando a una BD vacía: `alembic upgrade head`.

## Qué contiene la cadena

| Revisión | Contenido |
|---|---|
| `0001_baseline` | Extensiones (`pgcrypto`, `uuid-ossp`), las 30 tablas, índices, constraints, el tipo enum `member_role` y los `server_default` generados desde los modelos ORM |
| `0002_db_functions` | Funciones y triggers que ningún modelo define: `log_version_activity` + trigger en `entity_versions`, `log_comment_activity` + trigger en `comments` y `calculate_and_save_user_metrics(uuid)` |

El SQL anterior a Alembic está archivado en [legacy_sql/](legacy_sql/README.md) y no se ejecuta.

## Cómo crear una migración nueva

1. **Modifica los modelos ORM** en `backend/app/models/orm/`. Si añades una columna `NOT NULL` que algún `INSERT` crudo de `app/` pueda omitir, dale también `server_default` (un `default` de Python no se aplica en SQL crudo; el test T3 lo comprueba).
2. **Genera la migración** desde `backend/` (en el contenedor: `docker exec datamap-backend …`):
   ```bash
   alembic revision --autogenerate -m "descripcion corta" --rev-id 0003
   ```
   `--rev-id` sigue la numeración de la cadena (`0003`, `0004`…); el `down_revision` lo rellena Alembic con el head actual. Si el fichero se genera en el contenedor y el código está montado en `/app`, aparece en `backend/alembic/versions/`.
3. **Revisa el fichero generado** antes de aplicarlo. La autogeneración no ve funciones, triggers ni vistas (créalos a mano con `op.execute`, como hace `0002`) y puede confundir un renombrado con un borrado más un alta.
4. **Escribe el `downgrade()`** para que deshaga todo lo que crea `upgrade()`; el test T2 exige que `upgrade → downgrade base → upgrade` funcione sin dejar objetos huérfanos.
5. **Aplícala y comprueba**:
   ```bash
   alembic upgrade head
   alembic check          # "No new upgrade operations detected."
   ```
6. **Ejecuta los tests de migraciones**: `backend/test/integration/test_alembic_migrations.py` (T1–T6). Si añades una función o trigger propios, añade su caso a T4/T6.

No hay que actualizar ningún esquema estático de testing: `backend/test/conftest.py` crea la BD de cada worker con `alembic upgrade head`, igual que `backend/scripts/setup_test_db.py`.

## Exportar un volcado de la BD (opcional)

Un volcado sirve para copias de seguridad o para inspeccionar el esquema, **no** para inicializar el entorno. Con pgAdmin: clic derecho sobre la BD → **Backup…** → formato **Plain**. Por línea de comandos:

```bash
docker exec datamap-postgres pg_dump -U datamaper_user_local -d datamap_dev --schema-only > schema_dump.sql
```

No lo coloques en el repo como script de arranque: la fuente de verdad del esquema son las migraciones de Alembic.
