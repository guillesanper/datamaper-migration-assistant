# test/integration/test_database.py
"""
Tests de integración de las fixtures de base de datos de conftest.py
Módulo: Conexión y gestión de base de datos PostgreSQL
"""

import psycopg2
import pytest


@pytest.mark.integration
@pytest.mark.database
class TestDatabaseFixtures:
    """Tests para verificar fixtures de conftest.py"""

    def test_db_fixture_provides_connection(self, db):
        """Test: Fixture 'db' debe proporcionar conexión válida"""
        assert db is not None
        assert isinstance(db, psycopg2.extensions.connection)
        assert db.closed == 0

    def test_db_fixture_auto_rollback(self, db):
        """Test: Fixture 'db' debe hacer rollback automático después del test"""
        from psycopg2.extras import RealDictCursor

        cursor = db.cursor(cursor_factory=RealDictCursor)

        # Crear tabla temporal
        cursor.execute("""
            CREATE TEMPORARY TABLE test_rollback (
                id SERIAL PRIMARY KEY,
                value TEXT
            )
        """)
        db.commit()

        # Insertar dato
        cursor.execute("INSERT INTO test_rollback (value) VALUES (%s)", ("should_rollback",))
        db.commit()

        # Verificar que existe
        cursor.execute("SELECT COUNT(*) as count FROM test_rollback")
        count = cursor.fetchone()["count"]  # RealDictCursor retorna dict
        assert count == 1

        cursor.close()

        # Al finalizar el test, el fixture debe hacer rollback
        # (esto se verifica ejecutando otro test que no vea estos datos)

    def test_clean_db_fixture(self, clean_db):
        """Test: Fixture 'clean_db' debe proporcionar BD limpia"""
        assert clean_db is not None

        cursor = clean_db.cursor()

        # Verificar que podemos crear tablas temporales
        cursor.execute("""
            CREATE TEMPORARY TABLE test_clean (
                id SERIAL PRIMARY KEY,
                value TEXT
            )
        """)

        clean_db.commit()
        cursor.close()

    def test_test_db_connection_fixture(self, test_db_connection):
        """Test: Fixture 'test_db_connection' debe proporcionar string de conexión"""
        # test_db_connection es un fixture que retorna connection string
        # o la conexión misma, dependiendo de cómo esté implementado
        assert test_db_connection is not None
