"""
Demo script para mostrar las nuevas capacidades del Enhanced Migration Script Service

Este script genera scripts de migración con:
- Transacciones por dialecto
- Manejo de constraints
- Transformaciones customizadas
- Batch processing
- Integración con dependency graph
"""

from migration_script_service import MigrationScriptService

# ============================================================================
# EJEMPLO 1: Script básico con todas las características enterprise
# ============================================================================


def example_1_full_featured_postgresql():
    """Script PostgreSQL completo con todas las features"""

    mappings = [
        # Tabla 1: customers (sin dependencias)
        {
            "origin_table": "old_customers",
            "origin_column": "customer_id",
            "destination_table": "customers",
            "destination_column": "id",
            "origin_source_type": "import",
            "destination_source_type": "import",
            "origin_data_type": "INTEGER",
            "destination_data_type": "BIGINT",
        },
        {
            "origin_table": "old_customers",
            "origin_column": "customer_email",
            "destination_table": "customers",
            "destination_column": "email",
            "origin_source_type": "import",
            "destination_source_type": "import",
            "transformation_logic": "LOWER(TRIM({column}))",  # Normalizar emails
        },
        # Tabla 2: orders (depende de customers)
        {
            "origin_table": "old_orders",
            "origin_column": "order_id",
            "destination_table": "orders",
            "destination_column": "id",
            "origin_source_type": "import",
            "destination_source_type": "import",
        },
        {
            "origin_table": "old_orders",
            "origin_column": "customer_id",
            "destination_table": "orders",
            "destination_column": "customer_id",
            "origin_source_type": "import",
            "destination_source_type": "import",
        },
        {
            "origin_table": "old_orders",
            "origin_column": "order_date",
            "destination_table": "orders",
            "destination_column": "created_at",
            "origin_source_type": "import",
            "destination_source_type": "import",
            "origin_data_type": "DATE",
            "destination_data_type": "TIMESTAMP",  # Auto-conversión
        },
    ]

    script = MigrationScriptService.generate_insert_script(
        mappings=mappings,
        project_name="Customer DB Migration",
        dependency_order=["customers", "orders"],  # Orden topológico
        batch_size=10000,
        include_constraints=True,
        include_validation=True,
        dialect="postgresql",
    )

    print("=" * 80)
    print("EJEMPLO 1: PostgreSQL Full-Featured Migration")
    print("=" * 80)
    print(script)
    print()


# ============================================================================
# EJEMPLO 2: Script MySQL con batching
# ============================================================================


def example_2_mysql_with_batching():
    """Script MySQL con batch processing"""

    mappings = [
        {
            "origin_table": "legacy_products",
            "origin_column": "id",
            "destination_table": "products",
            "destination_column": "product_id",
            "origin_source_type": "import",
            "destination_source_type": "import",
        },
        {
            "origin_table": "legacy_products",
            "origin_column": "name",
            "destination_table": "products",
            "destination_column": "product_name",
            "origin_source_type": "import",
            "destination_source_type": "import",
            "transformation_logic": "UPPER({column})",  # Nombres en mayúsculas
        },
        {
            "origin_table": "legacy_products",
            "origin_column": "price",
            "destination_table": "products",
            "destination_column": "price",
            "origin_source_type": "import",
            "destination_source_type": "import",
            "origin_data_type": "VARCHAR",
            "destination_data_type": "DECIMAL",  # Conversión automática
        },
    ]

    script = MigrationScriptService.generate_insert_script(
        mappings=mappings,
        project_name="Product Catalog Migration",
        batch_size=5000,  # Batches más pequeños para MySQL
        include_constraints=True,
        include_validation=True,
        dialect="mysql",
    )

    print("=" * 80)
    print("EJEMPLO 2: MySQL Migration with Batching")
    print("=" * 80)
    print(script)
    print()


# ============================================================================
# EJEMPLO 3: SQL Server con transformaciones complejas
# ============================================================================


def example_3_sqlserver_with_transformations():
    """Script SQL Server con transformaciones avanzadas"""

    mappings = [
        {
            "origin_table": "EmployeesOld",
            "origin_column": "EmployeeID",
            "destination_table": "Employees",
            "destination_column": "Id",
            "origin_source_type": "import",
            "destination_source_type": "import",
        },
        {
            "origin_table": "EmployeesOld",
            "origin_column": "FirstName",
            "destination_table": "Employees",
            "destination_column": "FullName",
            "origin_source_type": "import",
            "destination_source_type": "import",
            # Concatenar FirstName + LastName
            "transformation_logic": "CONCAT(TRIM({column}), ' ', TRIM(LastName))",
        },
        {
            "origin_table": "EmployeesOld",
            "origin_column": "Salary",
            "destination_table": "Employees",
            "destination_column": "AnnualSalary",
            "origin_source_type": "import",
            "destination_source_type": "import",
            # Multiplicar por 12 para convertir mensual a anual
            "transformation_logic": "{column} * 12",
        },
    ]

    script = MigrationScriptService.generate_insert_script(
        mappings=mappings,
        project_name="HR System Migration",
        batch_size=20000,
        include_constraints=True,
        include_validation=True,
        dialect="sqlserver",
    )

    print("=" * 80)
    print("EJEMPLO 3: SQL Server Migration with Complex Transformations")
    print("=" * 80)
    print(script)
    print()


# ============================================================================
# EJEMPLO 4: Oracle con dependency graph complejo
# ============================================================================


def example_4_oracle_with_complex_dependencies():
    """Script Oracle con múltiples niveles de dependencias"""

    mappings = [
        # Nivel 0: Tablas independientes
        {
            "origin_table": "countries_old",
            "origin_column": "id",
            "destination_table": "countries",
            "destination_column": "country_id",
            "origin_source_type": "import",
            "destination_source_type": "import",
        },
        {
            "origin_table": "categories_old",
            "origin_column": "id",
            "destination_table": "categories",
            "destination_column": "category_id",
            "origin_source_type": "import",
            "destination_source_type": "import",
        },
        # Nivel 1: Depende de countries
        {
            "origin_table": "customers_old",
            "origin_column": "id",
            "destination_table": "customers",
            "destination_column": "customer_id",
            "origin_source_type": "import",
            "destination_source_type": "import",
        },
        # Nivel 1: Depende de categories
        {
            "origin_table": "products_old",
            "origin_column": "id",
            "destination_table": "products",
            "destination_column": "product_id",
            "origin_source_type": "import",
            "destination_source_type": "import",
        },
        # Nivel 2: Depende de customers y products
        {
            "origin_table": "orders_old",
            "origin_column": "id",
            "destination_table": "orders",
            "destination_column": "order_id",
            "origin_source_type": "import",
            "destination_source_type": "import",
        },
    ]

    # Orden topológico correcto
    dependency_order = ["countries", "categories", "customers", "products", "orders"]

    script = MigrationScriptService.generate_insert_script(
        mappings=mappings,
        project_name="E-commerce Migration",
        dependency_order=dependency_order,
        batch_size=15000,
        include_constraints=True,
        include_validation=True,
        dialect="oracle",
    )

    print("=" * 80)
    print("EJEMPLO 4: Oracle Migration with Complex Dependency Graph")
    print("=" * 80)
    print(script)
    print()


# ============================================================================
# EJEMPLO 5: Script simple sin features enterprise (backward compatible)
# ============================================================================


def example_5_simple_backward_compatible():
    """Script simple sin transacciones ni constraints (backward compatible)"""

    mappings = [
        {
            "origin_table": "users",
            "origin_column": "name",
            "destination_table": "users_new",
            "destination_column": "username",
            "origin_source_type": "import",
            "destination_source_type": "import",
        }
    ]

    script = MigrationScriptService.generate_insert_script(
        mappings=mappings,
        include_constraints=False,  # Sin manejo de constraints
        include_validation=False,  # Sin validación
        dialect="postgresql",
    )

    print("=" * 80)
    print("EJEMPLO 5: Simple Migration (Backward Compatible)")
    print("=" * 80)
    print(script)
    print()


# ============================================================================
# MAIN - Ejecutar todos los ejemplos
# ============================================================================

if __name__ == "__main__":
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 15 + "ENHANCED MIGRATION SCRIPT SERVICE - DEMO" + " " * 22 + "║")
    print("║" + " " * 20 + "Tarea 1.2 - Production Ready" + " " * 29 + "║")
    print("╚" + "=" * 78 + "╝")
    print("\n")

    example_1_full_featured_postgresql()
    example_2_mysql_with_batching()
    example_3_sqlserver_with_transformations()
    example_4_oracle_with_complex_dependencies()
    example_5_simple_backward_compatible()

    print("\n" + "=" * 80)
    print("RESUMEN DE FEATURES IMPLEMENTADAS:")
    print("=" * 80)
    print()
    print("✓ Transacciones por dialecto (PostgreSQL, MySQL, SQL Server, Oracle)")
    print("✓ Manejo automático de constraints y triggers")
    print("✓ Transformaciones customizadas con placeholders {column}")
    print("✓ Conversiones automáticas de tipos incompatibles")
    print("✓ Batch processing para tablas grandes")
    print("✓ Integración con dependency graph para orden correcto")
    print("✓ Queries de validación automática")
    print("✓ Headers mejorados con metadata completa")
    print("✓ Backward compatible con código existente")
    print()
    print("=" * 80)
