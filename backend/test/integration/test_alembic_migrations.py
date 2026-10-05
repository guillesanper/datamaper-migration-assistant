"""
Las migraciones de Alembic deben construir el esquema completo desde una BD vacía
y mantenerse sincronizadas con los modelos ORM (sin dumps ni SQL previos).
"""

import os
from pathlib import Path
from urllib.parse import quote_plus

import psycopg2
import pytest

from alembic import command
from alembic.config import Config

BACKEND_DIR = Path(__file__).resolve().parents[2]
CHECK_DB = "datamap_migration_check"


def _connect(dbname: str):
    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        dbname=dbname,
    )
    conn.autocommit = True
    return conn


@pytest.fixture
def empty_db_config():
    admin = _connect("postgres")
    cur = admin.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {CHECK_DB} WITH (FORCE)")
    cur.execute(f"CREATE DATABASE {CHECK_DB} ENCODING 'UTF8' TEMPLATE template0")

    url = (
        f"postgresql://{quote_plus(os.environ['DB_USER'])}:{quote_plus(os.environ['DB_PASSWORD'])}"
        f"@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{CHECK_DB}"
    )
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))

    yield cfg

    cur.execute(f"DROP DATABASE IF EXISTS {CHECK_DB} WITH (FORCE)")
    admin.close()


def test_upgrade_from_empty_db_matches_models(empty_db_config):
    from app.database.base import Base
    from app.models import orm  # noqa: F401  (registra todos los modelos)

    command.upgrade(empty_db_config, "head")

    # Sin diferencias entre las migraciones y los modelos ORM
    command.check(empty_db_config)

    conn = _connect(CHECK_DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
    )
    created = {row[0] for row in cur.fetchall()}
    conn.close()
    assert created == set(Base.metadata.tables)


def test_downgrade_and_upgrade_again(empty_db_config):
    command.upgrade(empty_db_config, "head")
    command.downgrade(empty_db_config, "base")
    command.upgrade(empty_db_config, "head")
