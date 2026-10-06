"""
Las migraciones de Alembic deben construir el esquema completo desde una BD vacía
y mantenerse sincronizadas con los modelos ORM (sin dumps ni SQL previos).

Además del esquema, la app depende de objetos de BD que los modelos no crean
(ver docs/ALEMBIC_BASELINE_AUDIT.md): funciones, triggers y defaults que solo existían en
Python. Estos tests lo comprueban:

- T1  BD vacía + upgrade head + check sin diferencias + tablas == Base.metadata
- T2  upgrade -> downgrade base -> upgrade, sin objetos huérfanos
- T3  (estático) los INSERT crudos de app/ no omiten columnas NOT NULL sin server_default
- T4  funciones de BD que la app invoca existen tras upgrade head y funcionan
- T5  esquema de Alembic equivalente al de Base.metadata.create_all
- T6  efecto de los triggers de actividad (versiones y comentarios)
"""

import ast
import os
import re
import uuid
from collections import namedtuple
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote_plus

import psycopg2
import pytest
from sqlalchemy import Integer, create_engine, func, text
from sqlalchemy.orm import Session

from alembic import command

BACKEND_DIR = Path(__file__).resolve().parents[2]

EmptyDb = namedtuple("EmptyDb", "name url config")


# ============================================================================
# FIXTURES Y UTILIDADES
# ============================================================================


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


def _db_url(dbname: str) -> str:
    return (
        f"postgresql://{quote_plus(os.environ['DB_USER'])}:{quote_plus(os.environ['DB_PASSWORD'])}"
        f"@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{dbname}"
    )


@contextmanager
def _fresh_database(name: str):
    """Crea una BD vacía (sin tablas, sin extensiones) y la elimina al salir."""
    admin = _connect("postgres")
    cur = admin.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
    cur.execute(f"CREATE DATABASE {name} ENCODING 'UTF8' TEMPLATE template0")
    try:
        yield
    finally:
        cur.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
        admin.close()


@pytest.fixture
def empty_db(worker_id, alembic_config_factory):
    # El nombre lleva el worker para que xdist no haga chocar a dos procesos
    name = f"datamap_migration_check_{worker_id}"
    with _fresh_database(name):
        url = _db_url(name)
        yield EmptyDb(name, url, alembic_config_factory(url))


@pytest.fixture
def create_all_db(worker_id):
    """BD vacía para T5, sobre la que se aplicará Base.metadata.create_all."""
    name = f"datamap_migration_createall_{worker_id}"
    with _fresh_database(name):
        yield EmptyDb(name, _db_url(name), None)


@pytest.fixture(scope="module")
def migrated_db(worker_id, alembic_config_factory):
    """BD con `alembic upgrade head` aplicado, compartida por los tests de T4 y T6.

    Cada test crea sus propios datos con ids únicos, así que no se pisan entre sí.
    """
    name = f"datamap_migration_head_{worker_id}"
    with _fresh_database(name):
        url = _db_url(name)
        command.upgrade(alembic_config_factory(url), "head")
        yield EmptyDb(name, url, None)


@pytest.fixture
def session(migrated_db):
    engine = create_engine(migrated_db.url)
    with Session(engine) as s:
        yield s
    engine.dispose()


def _public_tables(dbname: str) -> set:
    conn = _connect(dbname)
    cur = conn.cursor()
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
    )
    tables = {row[0] for row in cur.fetchall()}
    conn.close()
    return tables


# ============================================================================
# T1 / T2: la cadena construye el esquema y es reversible
# ============================================================================


def test_upgrade_from_empty_db_matches_models(empty_db):
    from app.database.base import Base
    from app.models import orm  # noqa: F401  (registra todos los modelos)

    command.upgrade(empty_db.config, "head")

    # Sin diferencias entre las migraciones y los modelos ORM
    command.check(empty_db.config)

    assert _public_tables(empty_db.name) == set(Base.metadata.tables)


def _orphans(dbname: str) -> dict:
    """Objetos que no deberían sobrevivir a un downgrade a base (excluye lo de las extensiones)."""
    queries = {
        "tablas": (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
        ),
        "tipos enum": (
            "SELECT t.typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = 'public' AND t.typtype = 'e'"
        ),
        # Las funciones de pgcrypto/uuid-ossp viven en public pero son de la extensión
        "funciones propias": (
            "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND NOT EXISTS ("
            "  SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_proc'::regclass "
            "  AND d.objid = p.oid AND d.deptype = 'e')"
        ),
        "vistas": "SELECT viewname FROM pg_views WHERE schemaname = 'public'",
        "secuencias": (
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'S'"
        ),
    }
    conn = _connect(dbname)
    cur = conn.cursor()
    found = {}
    for label, sql in queries.items():
        cur.execute(sql)
        found[label] = sorted(row[0] for row in cur.fetchall())
    conn.close()
    return found


def test_downgrade_and_upgrade_again(empty_db):
    from app.database.base import Base
    from app.models import orm  # noqa: F401

    command.upgrade(empty_db.config, "head")
    command.downgrade(empty_db.config, "base")

    leftovers = {label: names for label, names in _orphans(empty_db.name).items() if names}
    assert leftovers == {}, f"Objetos huérfanos tras downgrade base: {leftovers}"

    command.upgrade(empty_db.config, "head")
    assert _public_tables(empty_db.name) == set(Base.metadata.tables)


# ============================================================================
# T3: INSERT crudos que omiten columnas NOT NULL sin server_default
# ============================================================================

# Ficheros que *generan* SQL para bases de datos ajenas (no insertan en la BD de la app)
T3_EXCLUDED_FILES = {"app/services/migration_script_service.py"}

_INSERT_RE = re.compile(r"INSERT\s+INTO\s+(?:public\.)?(\w+)\s*\(([^)]*)\)", re.IGNORECASE)
_INSERT_ANY_RE = re.compile(r"INSERT\s+INTO", re.IGNORECASE)


def _string_literals(tree: ast.AST):
    """Literales de texto del módulo (f-strings con {} como marcador), sin docstrings."""
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstrings.add(id(first.value))

    inside_fstring = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            parts = []
            for value in node.values:
                if isinstance(value, ast.Constant):
                    inside_fstring.add(id(value))
                    parts.append(str(value.value))
                else:
                    parts.append("{}")
            yield node.lineno, "".join(parts)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
            and id(node) not in inside_fstring
        ):
            yield node.lineno, node.value


def _raw_inserts():
    """(inserts, no_interpretados): INSERT INTO t (cols) de app/ y literales que no se supieron leer."""
    inserts, unparsed = [], []
    for path in sorted((BACKEND_DIR / "app").rglob("*.py")):
        rel = path.relative_to(BACKEND_DIR).as_posix()
        if rel in T3_EXCLUDED_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for lineno, literal in _string_literals(tree):
            matches = _INSERT_RE.findall(literal)
            for table, cols in matches:
                columns = tuple(c.strip().strip('"').lower() for c in cols.split(",") if c.strip())
                inserts.append((rel, lineno, table.lower(), columns))
            if len(_INSERT_ANY_RE.findall(literal)) > len(matches):
                unparsed.append((rel, lineno))
    return inserts, unparsed


def _required_columns(table) -> set:
    """Columnas que un INSERT debe indicar: NOT NULL, sin server_default y que no son serial."""
    required = set()
    for col in table.columns:
        serial = (
            col.primary_key and isinstance(col.type, Integer) and col.autoincrement in (True, "auto")
        )
        if not col.nullable and col.server_default is None and col.identity is None and not serial:
            required.add(col.name)
    return required


def test_t3_extractor_reads_every_raw_insert():
    """Cordura de T3: si el extractor dejara de ver INSERTs, T3 pasaría sin comprobar nada."""
    inserts, unparsed = _raw_inserts()
    assert unparsed == [], f"INSERT INTO que el extractor no sabe interpretar: {unparsed}"
    # La auditoría de la Fase 1 localizó 19 en app/crud y app/services
    assert len(inserts) >= 19, f"Solo se encontraron {len(inserts)} INSERT crudos"


def test_t3_raw_inserts_do_not_omit_required_columns():
    from app.database.base import Base
    from app.models import orm  # noqa: F401

    inserts, _ = _raw_inserts()
    problems = []
    for rel, lineno, table, columns in inserts:
        assert table in Base.metadata.tables, f"{rel}:{lineno} inserta en una tabla desconocida: {table}"
        missing = sorted(_required_columns(Base.metadata.tables[table]) - set(columns))
        if missing:
            problems.append(f"{rel}:{lineno} -> {table}: omite {', '.join(missing)}")

    assert not problems, (
        "INSERT crudos que omiten columnas NOT NULL sin server_default "
        "(fallarían en una BD creada solo con migraciones):\n  " + "\n  ".join(problems)
    )


# ============================================================================
# T4: funciones de BD que la app invoca
# ============================================================================


def _own_function_exists(session: Session, name: str) -> bool:
    return bool(
        session.execute(
            text(
                "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'public' AND p.proname = :name"
            ),
            {"name": name},
        ).first()
    )


@pytest.mark.parametrize(
    "function",
    ["calculate_and_save_user_metrics", "log_version_activity", "log_comment_activity"],
)
def test_t4_function_exists_after_upgrade(session, function):
    assert _own_function_exists(session, function), f"Falta la función {function}() en pg_proc"


def _make_user(session: Session):
    from app.models.orm import User

    suffix = uuid.uuid4().hex[:12]
    user = User(
        username=f"user_{suffix}", email=f"user_{suffix}@example.com", password_hash="x" * 60
    )
    session.add(user)
    session.commit()
    return user


def _make_project(session: Session, owner_id, **fields):
    from app.models.orm import Project

    project = Project(name=f"proyecto_{uuid.uuid4().hex[:8]}", owner_id=owner_id, **fields)
    session.add(project)
    session.commit()
    return project


def _calculate_metrics(session: Session, user_id) -> None:
    # Misma llamada que project_crud.force_recalculate_user_metrics_orm
    session.execute(text("SELECT calculate_and_save_user_metrics(:user_id)"), {"user_id": str(user_id)})
    session.commit()


def _metrics_rows(session: Session, user_id) -> list:
    from app.models.orm import ProjectMetricsHistory

    session.expire_all()
    return (
        session.query(ProjectMetricsHistory)
        .filter(
            ProjectMetricsHistory.user_id == user_id,
            ProjectMetricsHistory.date == func.current_date(),
        )
        .all()
    )


def test_t4_metrics_on_database_with_user_without_projects(session):
    """Sobre una BD recién creada, con un usuario y sin proyectos: fila del día con ceros."""
    user = _make_user(session)

    _calculate_metrics(session, user.id)

    rows = _metrics_rows(session, user.id)
    assert len(rows) == 1
    row = rows[0]
    assert (row.total_projects, row.active_projects, row.paused_projects, row.completed_projects) == (
        0,
        0,
        0,
        0,
    )
    assert row.total_budget == Decimal("0") and row.avg_progress == Decimal("0")


def test_t4_metrics_aggregate_owned_projects_and_upsert(session):
    """Contrato validado por el usuario en la Puerta 1 (ver docs/ALEMBIC_BASELINE_AUDIT.md)."""
    user = _make_user(session)
    other = _make_user(session)

    _make_project(session, user.id, status="active", progress=10, budget=Decimal("100.50"))
    _make_project(session, user.id, status="active", progress=30, budget=Decimal("200.25"))
    _make_project(session, user.id, status="paused", progress=50, budget=Decimal("0"))
    _make_project(session, user.id, status="completed", progress=100, budget=Decimal("50"))
    # No cuentan: proyecto borrado del usuario y proyecto de otro usuario
    _make_project(session, user.id, status="active", progress=99, budget=Decimal("999"), is_deleted=True)
    _make_project(session, other.id, status="active", progress=99, budget=Decimal("999"))

    _calculate_metrics(session, user.id)

    rows = _metrics_rows(session, user.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.total_projects == 4
    assert row.active_projects == 2
    assert row.paused_projects == 1
    assert row.completed_projects == 1
    assert row.total_budget == Decimal("350.75")
    assert row.avg_progress == Decimal("47.50")

    # Idempotente: una segunda llamada el mismo día actualiza la fila, no crea otra
    _make_project(session, user.id, status="paused", progress=0, budget=Decimal("10"))
    _calculate_metrics(session, user.id)

    rows = _metrics_rows(session, user.id)
    assert len(rows) == 1
    assert rows[0].total_projects == 5 and rows[0].paused_projects == 2
    assert rows[0].total_budget == Decimal("360.75")
    # Las métricas de otro usuario no se tocan
    assert _metrics_rows(session, other.id) == []


# ============================================================================
# T5: equivalencia con Base.metadata.create_all
# ============================================================================


def _schema_snapshot(dbname: str) -> dict:
    """Tablas, columnas, índices y constraints de public (sin alembic_version, funciones ni triggers)."""
    queries = {
        "columnas": (
            "SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull, "
            "       pg_get_expr(d.adbin, d.adrelid), a.attidentity, a.attgenerated "
            "FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' AND a.attnum > 0 "
            "  AND NOT a.attisdropped AND c.relname <> 'alembic_version' "
            "ORDER BY 1, 2"
        ),
        "indices": (
            "SELECT tablename, indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename <> 'alembic_version' ORDER BY 1, 2"
        ),
        "constraints": (
            "SELECT c.relname, co.conname, co.contype, pg_get_constraintdef(co.oid) "
            "FROM pg_constraint co "
            "JOIN pg_class c ON c.oid = co.conrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname <> 'alembic_version' ORDER BY 1, 2"
        ),
        "tipos enum": (
            "SELECT t.typname, array_agg(e.enumlabel ORDER BY e.enumsortorder) "
            "FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid "
            "JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = 'public' GROUP BY t.typname ORDER BY 1"
        ),
    }
    conn = _connect(dbname)
    cur = conn.cursor()
    snapshot = {}
    for label, sql in queries.items():
        cur.execute(sql)
        snapshot[label] = {
            tuple(tuple(v) if isinstance(v, list) else v for v in row) for row in cur.fetchall()
        }
    conn.close()
    return snapshot


def test_alembic_schema_equals_create_all(empty_db, create_all_db):
    """pg_dump no está en la imagen del backend: se comparan los catálogos que habría volcado."""
    from app.database.base import Base
    from app.models import orm  # noqa: F401

    engine = create_engine(create_all_db.url)
    Base.metadata.create_all(engine)
    engine.dispose()

    command.upgrade(empty_db.config, "head")

    from_create_all = _schema_snapshot(create_all_db.name)
    from_alembic = _schema_snapshot(empty_db.name)

    differences = []
    for label in from_create_all:
        only_create_all = sorted(from_create_all[label] - from_alembic[label], key=str)
        only_alembic = sorted(from_alembic[label] - from_create_all[label], key=str)
        for item in only_create_all:
            differences.append(f"[{label}] solo en create_all: {item}")
        for item in only_alembic:
            differences.append(f"[{label}] solo en Alembic: {item}")
    assert not differences, "Esquemas distintos:\n  " + "\n  ".join(differences)


# ============================================================================
# T6: efecto de los triggers de actividad
# ============================================================================


def _make_version(session: Session, user, project, change_type: str, **fields):
    from app.models.orm import EntityVersion

    version = EntityVersion(
        hash=uuid.uuid4().hex + uuid.uuid4().hex,
        project_id=project.id,
        entity_id=uuid.uuid4(),
        entity_type="mapping",
        user_id=user.id,
        version_number=1,
        change_type=change_type,
        message="mensaje de prueba",
        **fields,
    )
    session.add(version)
    session.commit()
    return version


def _activity(session: Session, project_id, activity_type: str) -> list:
    from app.models.orm import ProjectActivity

    session.expire_all()
    return (
        session.query(ProjectActivity)
        .filter(
            ProjectActivity.project_id == project_id, ProjectActivity.activity_type == activity_type
        )
        .all()
    )


@pytest.mark.parametrize(
    "change_type, verb",
    [("create", "creó"), ("update", "actualizó"), ("delete", "eliminó"), ("restore", None)],
)
def test_t6_version_insert_logs_activity(session, change_type, verb):
    user = _make_user(session)
    project = _make_project(session, user.id)

    version = _make_version(session, user, project, change_type)

    rows = _activity(session, project.id, "version_created")
    assert len(rows) == 1, f"Se esperaba 1 fila version_created y hay {len(rows)}"
    activity = rows[0]
    assert activity.description, "description no puede ser NULL ni vacía"
    assert "mapping" in activity.description
    if verb:
        assert activity.description == f"{verb} mapping"
    assert activity.user_id == user.id
    assert activity.entity_id == version.entity_id and activity.entity_type == "mapping"
    assert activity.activity_metadata["version_id"] == str(version.id)
    assert activity.activity_metadata["version_number"] == 1
    assert activity.activity_metadata["message"] == "mensaje de prueba"


def _make_comment(session: Session, user, project, content: str, parent_id=None, entity_id=None):
    from app.models.orm import Comment

    comment = Comment(
        entity_id=entity_id or uuid.uuid4(),
        entity_type="mapping",
        project_id=project.id,
        user_id=user.id,
        parent_id=parent_id,
        content=content,
    )
    session.add(comment)
    session.commit()
    return comment


def test_t6_root_comment_logs_activity_and_reply_does_not(session):
    user = _make_user(session)
    project = _make_project(session, user.id)

    root = _make_comment(session, user, project, "x" * 150)

    rows = _activity(session, project.id, "comment_added")
    assert len(rows) == 1, f"Se esperaba 1 fila comment_added y hay {len(rows)}"
    activity = rows[0]
    assert activity.description == "comentó en mapping"
    assert activity.user_id == user.id
    assert activity.entity_id == root.entity_id and activity.entity_type == "mapping"
    assert activity.activity_metadata["comment_id"] == str(root.id)
    assert activity.activity_metadata["content_preview"] == "x" * 100

    # Una respuesta (parent_id) no deja fila nueva
    _make_comment(session, user, project, "respuesta", parent_id=root.id, entity_id=root.entity_id)

    rows = _activity(session, project.id, "comment_added")
    assert len(rows) == 1, "Una respuesta no debe registrar actividad"
    assert rows[0].activity_metadata["comment_id"] == str(root.id)
