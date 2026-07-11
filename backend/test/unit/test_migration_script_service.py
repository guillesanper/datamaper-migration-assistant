"""
Unit tests for Enhanced Migration Script Service

Tests all enterprise features:
- Transaction wrappers por dialecto
- Constraint management
- Type transformations
- Batch processing
- Dependency graph integration
"""

from unittest.mock import MagicMock, Mock

import pytest

from app.services.migration_script_service import (
    HashNotFoundError,
    MigrationScriptService,
    MigrationScriptServiceError,
)


class TestTransactionWrappers:
    """Tests for _generate_transaction_wrapper()"""

    def test_postgresql_transaction(self):
        begin, commit = MigrationScriptService._generate_transaction_wrapper("postgresql")
        assert begin == "BEGIN;"
        assert commit == "COMMIT;"

    def test_mysql_transaction(self):
        begin, commit = MigrationScriptService._generate_transaction_wrapper("mysql")
        assert begin == "START TRANSACTION;"
        assert commit == "COMMIT;"

    def test_sqlserver_transaction(self):
        begin, commit = MigrationScriptService._generate_transaction_wrapper("sqlserver")
        assert begin == "BEGIN TRANSACTION;"
        assert commit == "COMMIT TRANSACTION;"

    def test_oracle_transaction(self):
        begin, commit = MigrationScriptService._generate_transaction_wrapper("oracle")
        assert begin == "BEGIN"
        assert commit == "COMMIT;"

    def test_unknown_dialect_defaults_to_postgresql(self):
        begin, commit = MigrationScriptService._generate_transaction_wrapper("unknown")
        assert begin == "BEGIN;"
        assert commit == "COMMIT;"


class TestConstraintManagement:
    """Tests for _generate_constraint_disabling/enabling()"""

    def test_postgresql_disable_constraints(self):
        tables = ["users", "orders"]
        sql = MigrationScriptService._generate_constraint_disabling(tables, "postgresql")

        assert "ALTER TABLE users DISABLE TRIGGER ALL;" in sql
        assert "ALTER TABLE orders DISABLE TRIGGER ALL;" in sql

    def test_postgresql_enable_constraints(self):
        tables = ["users", "orders"]
        sql = MigrationScriptService._generate_constraint_enabling(tables, "postgresql")

        assert "ALTER TABLE users ENABLE TRIGGER ALL;" in sql
        assert "ALTER TABLE orders ENABLE TRIGGER ALL;" in sql

    def test_mysql_disable_constraints(self):
        tables = ["users"]
        sql = MigrationScriptService._generate_constraint_disabling(tables, "mysql")

        assert "SET FOREIGN_KEY_CHECKS=0;" in sql
        assert "SET AUTOCOMMIT=0;" in sql

    def test_mysql_enable_constraints(self):
        tables = ["users"]
        sql = MigrationScriptService._generate_constraint_enabling(tables, "mysql")

        assert "SET FOREIGN_KEY_CHECKS=1;" in sql

    def test_sqlserver_disable_constraints(self):
        tables = ["users", "products"]
        sql = MigrationScriptService._generate_constraint_disabling(tables, "sqlserver")

        assert "ALTER TABLE users NOCHECK CONSTRAINT ALL;" in sql
        assert "ALTER TABLE products NOCHECK CONSTRAINT ALL;" in sql

    def test_sqlserver_enable_constraints(self):
        tables = ["users", "products"]
        sql = MigrationScriptService._generate_constraint_enabling(tables, "sqlserver")

        assert "ALTER TABLE users CHECK CONSTRAINT ALL;" in sql
        assert "ALTER TABLE products CHECK CONSTRAINT ALL;" in sql

    def test_oracle_disable_constraints(self):
        tables = ["employees"]
        sql = MigrationScriptService._generate_constraint_disabling(tables, "oracle")

        assert "ALTER TABLE employees DISABLE ALL TRIGGERS;" in sql

    def test_oracle_enable_constraints(self):
        tables = ["employees"]
        sql = MigrationScriptService._generate_constraint_enabling(tables, "oracle")

        assert "ALTER TABLE employees ENABLE ALL TRIGGERS;" in sql


class TestTransformations:
    """Tests for _apply_transformation() and _generate_type_conversion()"""

    def test_apply_custom_transformation(self):
        result = MigrationScriptService._apply_transformation(
            column_name="email",
            transformation_logic="UPPER(TRIM({column}))",
            origin_type=None,
            dest_type=None,
            dialect="postgresql",
        )

        assert result == "UPPER(TRIM(email))"

    def test_apply_transformation_with_multiple_placeholders(self):
        result = MigrationScriptService._apply_transformation(
            column_name="name",
            transformation_logic="CONCAT({column}, ' - ', {column})",
            origin_type=None,
            dest_type=None,
            dialect="postgresql",
        )

        assert result == "CONCAT(name, ' - ', name)"

    def test_no_transformation_same_types(self):
        result = MigrationScriptService._apply_transformation(
            column_name="id",
            transformation_logic=None,
            origin_type="INTEGER",
            dest_type="INTEGER",
            dialect="postgresql",
        )

        assert result == "id"

    def test_auto_conversion_varchar_to_integer(self):
        result = MigrationScriptService._apply_transformation(
            column_name="age",
            transformation_logic=None,
            origin_type="VARCHAR",
            dest_type="INTEGER",
            dialect="postgresql",
        )

        assert "age" in result
        assert "INTEGER" in result
        # PostgreSQL usa sintaxis ::
        assert "::INTEGER" in result or "CAST" in result

    def test_auto_conversion_date_to_timestamp_postgresql(self):
        result = MigrationScriptService._apply_transformation(
            column_name="created_at",
            transformation_logic=None,
            origin_type="DATE",
            dest_type="TIMESTAMP",
            dialect="postgresql",
        )

        assert "created_at::TIMESTAMP" in result

    def test_auto_conversion_integer_to_varchar(self):
        result = MigrationScriptService._apply_transformation(
            column_name="quantity",
            transformation_logic=None,
            origin_type="INTEGER",
            dest_type="VARCHAR",
            dialect="mysql",
        )

        assert "CAST(quantity AS VARCHAR" in result

    def test_type_conversion_generic_cast_fallback(self):
        # Conversión no específica debe usar CAST genérico
        result = MigrationScriptService._generate_type_conversion(
            column_name="custom_field", origin_type="JSONB", dest_type="TEXT", dialect="postgresql"
        )

        assert "CAST(custom_field AS TEXT)" in result


class TestBatchProcessing:
    """Tests for _generate_batched_insert()"""

    def test_postgresql_batched_insert(self):
        result = MigrationScriptService._generate_batched_insert(
            table_name="users",
            columns=["id", "name", "email"],
            select_clause="SELECT id, name, email FROM source_users",
            total_rows=50000,
            batch_size=10000,
            dialect="postgresql",
        )

        assert "DO $$" in result
        assert "batch_size INT := 10000" in result
        assert "total_rows INT := 50000" in result
        assert "INSERT INTO users (id, name, email)" in result
        assert "LIMIT batch_size OFFSET offset_val" in result
        assert "RAISE NOTICE" in result

    def test_mysql_batched_insert(self):
        result = MigrationScriptService._generate_batched_insert(
            table_name="products",
            columns=["id", "price"],
            select_clause="SELECT id, price FROM source_products",
            total_rows=25000,
            batch_size=5000,
            dialect="mysql",
        )

        assert "CREATE PROCEDURE batch_insert_products" in result
        assert "DECLARE batch_size INT DEFAULT 5000" in result
        assert "WHILE offset_val < total_rows DO" in result
        assert "CALL batch_insert_products()" in result
        assert "DROP PROCEDURE batch_insert_products" in result

    def test_sqlserver_batched_insert(self):
        result = MigrationScriptService._generate_batched_insert(
            table_name="orders",
            columns=["order_id", "amount"],
            select_clause="SELECT order_id, amount FROM source_orders",
            total_rows=100000,
            batch_size=20000,
            dialect="sqlserver",
        )

        assert "DECLARE @batch_size INT = 20000" in result
        assert "DECLARE @total_rows INT = 100000" in result
        assert "WHILE @offset_val < @total_rows" in result
        assert "OFFSET @offset_val ROWS" in result
        assert "FETCH NEXT @batch_size ROWS ONLY" in result

    def test_oracle_batched_insert(self):
        result = MigrationScriptService._generate_batched_insert(
            table_name="employees",
            columns=["emp_id", "salary"],
            select_clause="SELECT emp_id, salary FROM source_emp",
            total_rows=15000,
            batch_size=3000,
            dialect="oracle",
        )

        assert "batch_size NUMBER := 3000" in result
        assert "total_rows NUMBER := 15000" in result
        assert "WHILE offset_val < total_rows LOOP" in result
        assert "OFFSET offset_val ROWS FETCH NEXT batch_size ROWS ONLY" in result
        assert "DBMS_OUTPUT.PUT_LINE" in result

    def test_batched_insert_with_null_total_rows(self):
        result = MigrationScriptService._generate_batched_insert(
            table_name="users",
            columns=["id"],
            select_clause="SELECT id FROM source",
            total_rows=None,
            batch_size=10000,
            dialect="postgresql",
        )

        assert "total_rows INT := NULL" in result

    def test_unknown_dialect_fallback_to_simple_insert(self):
        result = MigrationScriptService._generate_batched_insert(
            table_name="users",
            columns=["id", "name"],
            select_clause="SELECT id, name FROM source",
            total_rows=1000,
            batch_size=500,
            dialect="unknown_db",
        )

        # Debería generar INSERT simple sin batching
        assert "INSERT INTO users (id, name)" in result
        assert "SELECT id, name FROM source" in result
        assert "DO $$" not in result  # No batching code


class TestGenerateInsertScript:
    """Tests for complete generate_insert_script() with all features"""

    def test_empty_mappings(self):
        script = MigrationScriptService.generate_insert_script(mappings=[], dialect="postgresql")

        assert script == "-- No mappings found for this project\n"

    def test_script_header_includes_metadata(self):
        mappings = [
            {
                "origin_table": "users",
                "origin_column": "id",
                "destination_table": "new_users",
                "destination_column": "user_id",
                "origin_source_type": "import",
                "destination_source_type": "import",
            }
        ]

        script = MigrationScriptService.generate_insert_script(
            mappings=mappings, project_name="Test Migration", batch_size=5000, dialect="mysql"
        )

        assert "-- MIGRATION SCRIPT" in script
        assert "-- Project: Test Migration" in script
        assert "-- Total mappings: 1" in script
        assert "-- Dialect: mysql" in script
        assert "-- Batch size: 5000" in script

    def test_script_includes_transaction_wrapper(self):
        mappings = [
            {
                "origin_table": "customers",
                "origin_column": "name",
                "destination_table": "clients",
                "destination_column": "client_name",
                "origin_source_type": "import",
                "destination_source_type": "import",
            }
        ]

        script = MigrationScriptService.generate_insert_script(
            mappings=mappings, dialect="postgresql"
        )

        assert "BEGIN;" in script
        assert "COMMIT;" in script

    def test_script_includes_constraints_when_enabled(self):
        mappings = [
            {
                "origin_table": "orders",
                "origin_column": "id",
                "destination_table": "new_orders",
                "destination_column": "order_id",
                "origin_source_type": "import",
                "destination_source_type": "import",
            }
        ]

        script = MigrationScriptService.generate_insert_script(
            mappings=mappings, include_constraints=True, dialect="postgresql"
        )

        assert "DISABLE TRIGGER ALL" in script
        assert "ENABLE TRIGGER ALL" in script

    def test_script_excludes_constraints_when_disabled(self):
        mappings = [
            {
                "origin_table": "products",
                "origin_column": "id",
                "destination_table": "new_products",
                "destination_column": "product_id",
                "origin_source_type": "import",
                "destination_source_type": "import",
            }
        ]

        script = MigrationScriptService.generate_insert_script(
            mappings=mappings, include_constraints=False, dialect="postgresql"
        )

        assert "DISABLE TRIGGER" not in script
        assert "ENABLE TRIGGER" not in script

    def test_script_includes_validation_when_enabled(self):
        mappings = [
            {
                "origin_table": "users",
                "origin_column": "email",
                "destination_table": "new_users",
                "destination_column": "email",
                "origin_source_type": "import",
                "destination_source_type": "import",
            }
        ]

        script = MigrationScriptService.generate_insert_script(
            mappings=mappings, include_validation=True, dialect="postgresql"
        )

        assert "SECTION 5: Validation" in script
        assert "SELECT" in script
        assert "COUNT(*)" in script

    def test_script_applies_dependency_order(self):
        mappings = [
            {
                "origin_table": "orders",
                "origin_column": "id",
                "destination_table": "orders",
                "destination_column": "id",
                "origin_source_type": "import",
                "destination_source_type": "import",
            },
            {
                "origin_table": "customers",
                "origin_column": "id",
                "destination_table": "customers",
                "destination_column": "id",
                "origin_source_type": "import",
                "destination_source_type": "import",
            },
        ]

        # customers debe ir antes que orders (dependency order)
        script = MigrationScriptService.generate_insert_script(
            mappings=mappings, dependency_order=["customers", "orders"], dialect="postgresql"
        )

        # Verificar que customers aparece antes que orders en el script
        customers_pos = script.find("INSERT INTO customers")
        orders_pos = script.find("INSERT INTO orders")

        assert customers_pos > 0
        assert orders_pos > 0
        assert customers_pos < orders_pos

    def test_script_with_transformations(self):
        mappings = [
            {
                "origin_table": "users",
                "origin_column": "email",
                "destination_table": "new_users",
                "destination_column": "email",
                "origin_source_type": "import",
                "destination_source_type": "import",
                "transformation_logic": "LOWER(TRIM({column}))",
            }
        ]

        script = MigrationScriptService.generate_insert_script(
            mappings=mappings, dialect="postgresql"
        )

        assert "LOWER(TRIM(email))" in script

    def test_script_groups_mappings_by_table(self):
        mappings = [
            {
                "origin_table": "users",
                "origin_column": "id",
                "destination_table": "new_users",
                "destination_column": "user_id",
                "origin_source_type": "import",
                "destination_source_type": "import",
            },
            {
                "origin_table": "users",
                "origin_column": "name",
                "destination_table": "new_users",
                "destination_column": "user_name",
                "origin_source_type": "import",
                "destination_source_type": "import",
            },
        ]

        script = MigrationScriptService.generate_insert_script(
            mappings=mappings, dialect="postgresql"
        )

        # Debe haber solo un INSERT INTO new_users con ambas columnas
        assert "INSERT INTO new_users (user_id, user_name)" in script
        assert script.count("INSERT INTO new_users") == 1


class TestHashResolution:
    """Tests for hash resolution (connector mode)"""

    def test_resolve_hash_not_found_raises_error(self):
        mock_adapter = Mock()
        mock_adapter.get_tables.return_value = []

        with pytest.raises(HashNotFoundError) as exc_info:
            MigrationScriptService._resolve_hash_from_adapter(
                adapter=mock_adapter, hash_value="abc123", is_column=False, side="origin"
            )

        assert "abc123" in str(exc_info.value)
        assert "origin" in str(exc_info.value)

    def test_resolve_table_hash_success(self):
        # Mock table with matching hash
        import hashlib

        mock_table = Mock()
        mock_table.name = "users"

        mock_adapter = Mock()
        mock_adapter.get_tables.return_value = [mock_table]

        # Generate correct hash
        expected_hash = hashlib.sha256("users".encode()).hexdigest()

        result = MigrationScriptService._resolve_hash_from_adapter(
            adapter=mock_adapter, hash_value=expected_hash, is_column=False, side="origin"
        )

        assert result == "users"

    def test_resolve_column_hash_success(self):
        import hashlib

        # Mock column with matching hash
        mock_column = Mock()
        mock_column.name = "email"

        mock_table = Mock()
        mock_table.name = "users"

        mock_adapter = Mock()
        mock_adapter.get_tables.return_value = [mock_table]
        mock_adapter.get_columns.return_value = [mock_column]

        expected_hash = hashlib.sha256("email".encode()).hexdigest()

        result = MigrationScriptService._resolve_hash_from_adapter(
            adapter=mock_adapter, hash_value=expected_hash, is_column=True, side="destination"
        )

        assert result == "email"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
