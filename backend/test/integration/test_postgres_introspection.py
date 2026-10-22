"""
Integration tests de introspección contra un PostgreSQL real.

Cubre fallos que los tests con mocks no detectaban:
- get_full_schema_metadata devolvía 0 PKs/FKs/índices (orden de argumentos invertido)
- FKs compuestas con columnas duplicadas (producto cartesiano)
- Tablas con nombres no ASCII, con guiones o palabras reservadas tumbaban el schema
- pg_total_relation_size fallaba con nombres en mayúsculas
- test_connection no desconectaba si fallaba la query

Usa la BD de docker-compose.test.yml (puerto 5433); se omite si no está disponible.
"""

import psycopg2
import pytest

from app.utils.db_adapters import PostgreSQLAdapter
from app.utils.db_adapters.exceptions import DBConnectionError

PG_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "database": "test_database",
    "user": "test_user",
    "password": "test_password",
    "ssl_mode": "disable",
}
SCHEMA = "introspection_it"

DDL = f"""
    DROP SCHEMA IF EXISTS {SCHEMA} CASCADE;
    CREATE SCHEMA {SCHEMA};
    CREATE TABLE {SCHEMA}.parent (a int, b int, label text UNIQUE, PRIMARY KEY (a, b));
    CREATE TABLE {SCHEMA}.child (
        id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        pa int,
        pb int,
        CONSTRAINT child_parent_fk FOREIGN KEY (pa, pb) REFERENCES {SCHEMA}.parent (b, a)
            ON DELETE CASCADE
    );
    CREATE INDEX child_pb_pa_idx ON {SCHEMA}.child (pb, pa);
    CREATE TABLE {SCHEMA}."Año" (id serial PRIMARY KEY);
    CREATE TABLE {SCHEMA}."order-items" (id int PRIMARY KEY);
    CREATE TABLE {SCHEMA}."view" (id int PRIMARY KEY);
    CREATE TABLE {SCHEMA}."MixedCase" (id int PRIMARY KEY);
"""


class _CountingConnection:
    """Proxy de conexión psycopg2 que registra cada query ejecutada."""

    def __init__(self, connection, executed):
        self._connection = connection
        self._executed = executed

    def cursor(self, *args, **kwargs):
        executed = self._executed
        cursor = self._connection.cursor(*args, **kwargs)

        class _Cursor:
            def __enter__(self):
                cursor.__enter__()
                return self

            def __exit__(self, *exc):
                return cursor.__exit__(*exc)

            def execute(self, query, params=None):
                executed.append(query)
                return cursor.execute(query, params)

            def __getattr__(self, name):
                return getattr(cursor, name)

        return _Cursor()

    def __getattr__(self, name):
        return getattr(self._connection, name)


class _FailingConnection:
    """Proxy de conexión cuyo cursor falla siempre."""

    def __init__(self, connection):
        self._connection = connection

    def cursor(self, *args, **kwargs):
        raise psycopg2.InterfaceError("boom")

    def __getattr__(self, name):
        return getattr(self._connection, name)


@pytest.fixture(scope="module")
def pg_schema():
    try:
        conn = psycopg2.connect(
            connect_timeout=3, **{k: v for k, v in PG_CONFIG.items() if k != "ssl_mode"}
        )
    except psycopg2.OperationalError:
        pytest.skip("PostgreSQL test instance not available on port 5433")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(DDL)
    yield
    with conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
    conn.close()


@pytest.fixture
def adapter(pg_schema):
    with PostgreSQLAdapter(dict(PG_CONFIG)) as adapter:
        yield adapter


@pytest.mark.integration
class TestFullSchemaMetadata:
    def test_tables_with_special_names_are_introspected(self, adapter):
        metadata = adapter.get_full_schema_metadata(SCHEMA)

        names = {t.name for t in metadata.tables}
        assert names == {"parent", "child", "Año", "order-items", "view", "MixedCase"}
        # Ninguna tabla queda sin columnas
        assert all(t.columns for t in metadata.tables)

    def test_primary_keys_are_returned(self, adapter):
        metadata = adapter.get_full_schema_metadata(SCHEMA)

        pks = {pk.table_name: pk.columns for pk in metadata.primary_keys}
        assert pks["parent"] == ["a", "b"]
        assert pks["child"] == ["id"]
        assert pks["Año"] == ["id"]
        assert len(pks) == 6

        parent = metadata.get_table("parent")
        assert [c.name for c in parent.columns if c.is_primary_key] == ["a", "b"]

    def test_composite_foreign_key_columns_are_paired(self, adapter):
        metadata = adapter.get_full_schema_metadata(SCHEMA)

        assert len(metadata.foreign_keys) == 1
        fk = metadata.foreign_keys[0]
        assert fk.name == "child_parent_fk"
        assert fk.table_name == "child"
        # Sin duplicados y emparejadas por posición (pa -> b, pb -> a)
        assert fk.columns == ["pa", "pb"]
        assert fk.referenced_columns == ["b", "a"]
        assert fk.referenced_table == "parent"
        assert fk.referenced_schema == SCHEMA
        assert fk.on_delete == "CASCADE"

        child = metadata.get_table("child")
        assert {c.name for c in child.columns if c.is_foreign_key} == {"pa", "pb"}

    def test_indexes_and_unique_constraints(self, adapter):
        metadata = adapter.get_full_schema_metadata(SCHEMA)

        indexes = {idx.name: idx for idx in metadata.indexes}
        # Orden de columnas del índice, no el de la tabla
        assert indexes["child_pb_pa_idx"].columns == ["pb", "pa"]
        assert indexes["parent_pkey"].is_primary
        assert [u.columns for u in metadata.unique_constraints] == [["label"]]

    def test_identity_and_serial_are_auto_increment(self, adapter):
        metadata = adapter.get_full_schema_metadata(SCHEMA)

        assert metadata.get_table("child").get_column("id").is_auto_increment
        assert metadata.get_table("Año").get_column("id").is_auto_increment
        assert not metadata.get_table("parent").get_column("a").is_auto_increment

    def test_fixed_number_of_queries(self, adapter):
        """La introspección no hace N+1: el número de queries no depende de las tablas."""
        executed = []
        adapter.connection = _CountingConnection(adapter.connection, executed)

        adapter.get_full_schema_metadata(SCHEMA)

        # get_tables + columnas + PKs + UNIQUE + FKs + índices
        assert len(executed) == 6


@pytest.mark.integration
class TestPerTableMethods:
    def test_unified_signature_table_then_schema(self, adapter):
        assert adapter.get_primary_keys("parent", SCHEMA)[0].columns == ["a", "b"]
        assert adapter.get_foreign_keys("child", SCHEMA)[0].referenced_columns == ["b", "a"]
        assert {i.name for i in adapter.get_indexes("child", SCHEMA)} == {
            "child_pkey",
            "child_pb_pa_idx",
        }
        assert adapter.get_unique_constraints("parent", SCHEMA)[0].columns == ["label"]

    def test_statistics_with_mixed_case_name(self, adapter):
        stats = adapter.get_table_statistics("MixedCase", SCHEMA)
        assert stats.table_name == "MixedCase"
        assert stats.size_bytes > 0

    def test_test_connection_disconnects_when_query_fails(self, pg_schema):
        adapter = PostgreSQLAdapter(dict(PG_CONFIG))
        original_connect = adapter.connect
        opened = []

        def connect_with_failing_cursor():
            original_connect()
            opened.append(adapter.connection)
            adapter.connection = _FailingConnection(adapter.connection)

        adapter.connect = connect_with_failing_cursor
        with pytest.raises(DBConnectionError):
            adapter.test_connection()

        assert opened[0].closed
        assert not adapter.is_connected
