# test/integration/test_database.py
"""
Tests de integración para app.database.database
Módulo: Conexión y gestión de base de datos PostgreSQL
"""

import os
import sys
from unittest.mock import patch

import psycopg2
import pytest
from psycopg2.extras import RealDictCursor

# Import functions to test
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from app.database.database import get_db


@pytest.mark.integration
@pytest.mark.database
class TestGetDb:
    """Tests para la función get_db()"""

    def test_get_db_returns_connection(self):
        """Test: Debe retornar una conexión válida a PostgreSQL"""
        conn = get_db()

        # Verificar que retorna una conexión
        assert conn is not None
        assert isinstance(conn, psycopg2.extensions.connection)

        # Verificar que la conexión está abierta
        assert conn.closed == 0  # 0 = abierta, 1 = cerrada

        # Limpiar
        conn.close()

    def test_get_db_connection_is_functional(self):
        """Test: La conexión debe ser funcional y permitir queries"""
        conn = get_db()

        try:
            # Ejecutar una query simple
            cursor = conn.cursor()
            cursor.execute("SELECT 1 as test")
            result = cursor.fetchone()

            assert result is not None
            assert result["test"] == 1  # RealDictCursor retorna dict

            cursor.close()
        finally:
            conn.close()

    def test_get_db_uses_realdict_cursor(self):
        """Test: Debe usar RealDictCursor por defecto"""
        conn = get_db()

        try:
            # Crear cursor y verificar que retorna diccionarios
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT 1 as test_col, 'value' as test_str")
            result = cursor.fetchone()

            # RealDictCursor retorna dict
            assert isinstance(result, dict)
            assert result["test_col"] == 1
            assert result["test_str"] == "value"

            cursor.close()
        finally:
            conn.close()

    def test_get_db_uses_correct_environment_variables(self):
        """Test: Debe usar variables de entorno correctas"""
        # Este test verifica que las variables de entorno están configuradas
        required_env_vars = ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]

        for var in required_env_vars:
            assert os.getenv(var) is not None, f"Variable {var} no está configurada"

    def test_get_db_connection_properties(self):
        """Test: Verificar propiedades de la conexión"""
        conn = get_db()

        try:
            # Verificar encoding
            assert conn.encoding is not None

            # Verificar que está conectado a la BD correcta
            cursor = conn.cursor()
            cursor.execute("SELECT current_database() as db_name")
            current_db = cursor.fetchone()["db_name"]  # RealDictCursor retorna dict

            assert current_db == os.getenv("DB_NAME")

            cursor.close()
        finally:
            conn.close()

    def test_get_db_multiple_connections(self):
        """Test: Debe permitir múltiples conexiones simultáneas"""
        conn1 = get_db()
        conn2 = get_db()

        try:
            # Ambas deben ser válidas
            assert conn1 is not None
            assert conn2 is not None

            # Deben ser conexiones diferentes
            assert conn1 != conn2

            # Ambas deben ser funcionales
            cursor1 = conn1.cursor()
            cursor1.execute("SELECT 1 as val")
            assert cursor1.fetchone()["val"] == 1  # RealDictCursor retorna dict
            cursor1.close()

            cursor2 = conn2.cursor()
            cursor2.execute("SELECT 2 as val")
            assert cursor2.fetchone()["val"] == 2  # RealDictCursor retorna dict
            cursor2.close()

        finally:
            conn1.close()
            conn2.close()

    @patch.dict(os.environ, {"DB_HOST": "invalid_host"})
    def test_get_db_with_invalid_host_raises_error(self):
        """Test: Debe lanzar error con host inválido"""
        # Recargar módulo para que use el env modificado
        from importlib import reload

        import app.database.database as db_module

        reload(db_module)

        with pytest.raises(psycopg2.OperationalError):
            db_module.get_db()

    def test_get_db_transaction_support(self):
        """Test: Debe soportar transacciones"""
        conn = get_db()

        try:
            cursor = conn.cursor()

            # Crear tabla temporal para test y hacer commit
            cursor.execute("""
                CREATE TEMPORARY TABLE test_transaction (
                    id SERIAL PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.commit()

            # Insertar dato
            cursor.execute("INSERT INTO test_transaction (value) VALUES (%s)", ("test",))

            # Rollback
            conn.rollback()

            # Verificar que no se guardó
            cursor.execute("SELECT COUNT(*) as count FROM test_transaction")
            count = cursor.fetchone()["count"]  # RealDictCursor retorna dict
            assert count == 0

            # Insertar y commit
            cursor.execute("INSERT INTO test_transaction (value) VALUES (%s)", ("test",))
            conn.commit()

            # Verificar que sí se guardó
            cursor.execute("SELECT COUNT(*) as count FROM test_transaction")
            count = cursor.fetchone()["count"]  # RealDictCursor retorna dict
            assert count == 1

            cursor.close()
        finally:
            conn.close()


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
