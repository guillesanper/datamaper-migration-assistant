"""
Unit Tests for ExecutionService

Tests para el servicio de ejecución de scripts de migración.

Created: 2025-01-17
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, Mock, call, patch
from uuid import uuid4

import pytest

from app.services.execution_service import ExecutionService, ExecutionServiceError
from utilities.migrations.validators import BackupManager

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_db_connection():
    """Mock de psycopg2 connection"""
    connection = Mock()
    mock_cursor = Mock()
    mock_cursor.execute = Mock()
    mock_cursor.close = Mock()
    mock_cursor.fetchone = Mock()

    connection.cursor = Mock(return_value=mock_cursor)
    connection.commit = Mock()
    connection.rollback = Mock()

    return connection


@pytest.fixture
def mock_dest_adapter():
    """Mock de BaseDBAdapter conectado"""
    adapter = Mock()
    adapter.is_connected = True
    adapter.dialect = "postgresql"

    # Mock de conexión y cursor
    mock_cursor = Mock()
    mock_cursor.execute = Mock()
    mock_cursor.rowcount = 100
    mock_cursor.close = Mock()

    mock_connection = Mock()
    mock_connection.cursor = Mock(return_value=mock_cursor)
    mock_connection.commit = Mock()
    mock_connection.rollback = Mock()

    adapter.connection = mock_connection

    return adapter


@pytest.fixture
def sample_script():
    """Script SQL de ejemplo"""
    return """
    -- SECTION 1: Transaction Start
    BEGIN;

    -- SECTION 2: Disable Constraints
    ALTER TABLE customers DISABLE TRIGGER ALL;

    -- SECTION 3: Data Migration
    INSERT INTO customers (id, name, email)
    SELECT id, name, email FROM source_customers;

    INSERT INTO orders (id, customer_id, total)
    SELECT id, customer_id, total FROM source_orders;

    -- SECTION 4: Enable Constraints
    ALTER TABLE customers ENABLE TRIGGER ALL;

    -- SECTION 5: Validation
    SELECT 'customers' AS table_name, COUNT(*) AS row_count FROM customers;

    -- SECTION 6: Transaction Commit
    COMMIT;
    """


@pytest.fixture
def execution_service():
    """Instancia de ExecutionService"""
    return ExecutionService()


# =============================================================================
# TEST 1: EXECUTE MIGRATION SUCCESS
# =============================================================================


def test_execute_migration_success(
    execution_service, mock_db_connection, mock_dest_adapter, sample_script
):
    """Test de ejecución exitosa de migración"""

    project_id = str(uuid4())
    user_id = str(uuid4())

    # Mock de BackupManager
    with patch.object(BackupManager, "create_backup") as mock_create_backup:
        mock_create_backup.return_value = {
            "backup_id": "backup_20250117_143000",
            "timestamp": datetime.now().isoformat(),
            "tables": [{"table": "projects", "row_count": 10}],
        }

        # Ejecutar migración
        result = execution_service.execute_migration(
            db_connection=mock_db_connection,
            project_id=project_id,
            script=sample_script,
            dest_adapter=mock_dest_adapter,
            dry_run=False,
            user_id=user_id,
        )

    # Verificar resultado
    assert result["status"] == "success"
    assert result["rows_affected"] > 0
    assert result["backup_id"] == "backup_20250117_143000"
    assert len(result["errors"]) == 0
    assert result["execution_id"] is not None
    assert result["duration_seconds"] >= 0

    # Verificar que se hizo COMMIT en la BD destino
    mock_dest_adapter.connection.commit.assert_called_once()


# =============================================================================
# TEST 2: EXECUTE MIGRATION WITH ERROR AND ROLLBACK
# =============================================================================


def test_execute_migration_with_error_rollback(
    execution_service, mock_db_connection, mock_dest_adapter, sample_script
):
    """Test de manejo de error con ROLLBACK automático"""

    project_id = str(uuid4())

    # Configurar cursor para fallar en el segundo statement
    mock_cursor = mock_dest_adapter.connection.cursor.return_value
    call_count = [0]

    def execute_with_error(sql):
        call_count[0] += 1
        if call_count[0] == 3:  # Falla en el tercer statement
            raise Exception("Simulated SQL error: constraint violation")

    mock_cursor.execute.side_effect = execute_with_error

    # Mock de BackupManager
    with patch.object(BackupManager, "create_backup") as mock_create_backup:
        mock_create_backup.return_value = {
            "backup_id": "backup_20250117_143000",
            "timestamp": datetime.now().isoformat(),
            "tables": [],
        }

        # Ejecutar migración (debería fallar)
        result = execution_service.execute_migration(
            db_connection=mock_db_connection,
            project_id=project_id,
            script=sample_script,
            dest_adapter=mock_dest_adapter,
            dry_run=False,
        )

    # Verificar resultado de error
    assert result["status"] == "failed"
    assert result["rows_affected"] == 0
    assert len(result["errors"]) > 0
    assert "constraint violation" in result["errors"][0]

    # Verificar que se hizo ROLLBACK en la BD destino
    mock_dest_adapter.connection.rollback.assert_called()

    # Verificar que no se hizo COMMIT
    mock_dest_adapter.connection.commit.assert_not_called()


# =============================================================================
# TEST 3: DRY-RUN MODE
# =============================================================================


def test_dry_run_mode(execution_service, mock_db_connection, mock_dest_adapter, sample_script):
    """Test de modo dry-run (ejecuta pero hace ROLLBACK)"""

    project_id = str(uuid4())

    # Mock de BackupManager
    with patch.object(BackupManager, "create_backup") as mock_create_backup:
        mock_create_backup.return_value = {
            "backup_id": "backup_20250117_143000",
            "timestamp": datetime.now().isoformat(),
            "tables": [],
        }

        # Ejecutar en modo dry-run
        result = execution_service.execute_migration(
            db_connection=mock_db_connection,
            project_id=project_id,
            script=sample_script,
            dest_adapter=mock_dest_adapter,
            dry_run=True,  # <-- DRY-RUN MODE
        )

    # Verificar resultado
    assert result["status"] == "dry_run_complete"
    assert result["rows_affected"] > 0  # Se ejecutaron los statements
    assert len(result["errors"]) == 0

    # Verificar que se hizo ROLLBACK en vez de COMMIT
    mock_dest_adapter.connection.rollback.assert_called_once()
    mock_dest_adapter.connection.commit.assert_not_called()


# =============================================================================
# TEST 4: SCRIPT PARSING
# =============================================================================


def test_script_parsing(execution_service):
    """Test de parsing de script SQL en statements individuales"""

    script = """
    -- Comment line
    BEGIN;

    INSERT INTO customers (id, name) VALUES (1, 'John');
    INSERT INTO orders (id, customer_id) VALUES (1, 1);

    -- Another comment
    COMMIT;
    """

    statements = execution_service._parse_sql_script(script)

    # Verificar que se parsearon correctamente
    assert len(statements) > 0

    # Filtrar statements vacíos
    non_empty = [s for s in statements if s.strip()]

    # Debe haber al menos BEGIN, 2 INSERTs, y COMMIT
    assert len(non_empty) >= 4

    # Verificar que se removieron comentarios
    for stmt in statements:
        assert not stmt.strip().startswith("--")


# =============================================================================
# TEST 5: TABLE NAME EXTRACTION
# =============================================================================


def test_extract_table_name(execution_service):
    """Test de extracción de nombre de tabla de statements INSERT"""

    # Caso 1: INSERT simple
    stmt1 = "INSERT INTO customers (id, name) VALUES (1, 'John');"
    assert execution_service._extract_table_name(stmt1) == "customers"

    # Caso 2: INSERT con schema
    stmt2 = "INSERT INTO public.orders (id) VALUES (1);"
    assert execution_service._extract_table_name(stmt2) == "orders"

    # Caso 3: INSERT con minúsculas
    stmt3 = "insert into products (id) values (1);"
    assert execution_service._extract_table_name(stmt3) == "products"

    # Caso 4: Statement que no es INSERT
    stmt4 = "SELECT * FROM customers;"
    assert execution_service._extract_table_name(stmt4) is None


# =============================================================================
# TEST 6: ADAPTER NOT CONNECTED
# =============================================================================


def test_execute_script_adapter_not_connected(execution_service, sample_script):
    """Test de error cuando adapter no está conectado"""

    # Mock de adapter desconectado
    mock_adapter = Mock()
    mock_adapter.is_connected = False

    # Debe lanzar ExecutionServiceError
    with pytest.raises(ExecutionServiceError) as exc_info:
        execution_service._execute_script(adapter=mock_adapter, script=sample_script, dry_run=False)

    assert "not connected" in str(exc_info.value).lower()


# =============================================================================
# SUMMARY
# =============================================================================

"""
Tests implementados:

1. ✅ test_execute_migration_success - Ejecución exitosa completa
2. ✅ test_execute_migration_with_error_rollback - Manejo de errores con ROLLBACK
3. ✅ test_dry_run_mode - Modo dry-run (ROLLBACK al final)
4. ✅ test_script_parsing - Parsing de script SQL
5. ✅ test_extract_table_name - Extracción de nombres de tablas
6. ✅ test_execute_script_adapter_not_connected - Validación de conexión

Total: 6 tests core (simplified)
Coverage esperado: >80%
"""
