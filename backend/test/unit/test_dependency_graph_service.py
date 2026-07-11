"""
Unit tests for DependencyGraphService

Tests para el servicio de análisis de dependencias entre tablas.
Cobertura de:
- Construcción del grafo
- Detección de dependencias
- Topological sort (algoritmo de Kahn)
- Detección de ciclos
- Auto-referencias
- Paralelización
- Casos edge
"""

from typing import List

import pytest

from app.models.db_metadata.constraint import ForeignKeyMetadata
from app.models.db_metadata.schema import SchemaMetadata
from app.models.db_metadata.table import TableMetadata
from app.services.dependency_graph_service import CircularDependencyError, DependencyGraphService

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def empty_schema():
    """Schema vacío sin tablas"""
    return SchemaMetadata(name="test_schema", tables=[], foreign_keys=[])


@pytest.fixture
def simple_schema():
    """
    Schema simple sin dependencias:
    - Countries (independiente)
    - Categories (independiente)
    """
    return SchemaMetadata(
        name="test_schema",
        tables=[TableMetadata(name="Countries"), TableMetadata(name="Categories")],
        foreign_keys=[],
    )


@pytest.fixture
def linear_schema():
    """
    Schema con dependencias lineales:
    Countries <- Regions <- Customers <- Orders <- OrderDetails

    Orden esperado: Countries, Regions, Customers, Orders, OrderDetails
    """
    tables = [
        TableMetadata(name="Countries"),
        TableMetadata(name="Regions"),
        TableMetadata(name="Customers"),
        TableMetadata(name="Orders"),
        TableMetadata(name="OrderDetails"),
    ]

    foreign_keys = [
        ForeignKeyMetadata(
            constraint_name="fk_regions_country",
            table_name="Regions",
            column_names=["country_id"],
            referenced_table="Countries",
            referenced_columns=["id"],
        ),
        ForeignKeyMetadata(
            constraint_name="fk_customers_region",
            table_name="Customers",
            column_names=["region_id"],
            referenced_table="Regions",
            referenced_columns=["id"],
        ),
        ForeignKeyMetadata(
            constraint_name="fk_orders_customer",
            table_name="Orders",
            column_names=["customer_id"],
            referenced_table="Customers",
            referenced_columns=["id"],
        ),
        ForeignKeyMetadata(
            constraint_name="fk_orderdetails_order",
            table_name="OrderDetails",
            column_names=["order_id"],
            referenced_table="Orders",
            referenced_columns=["id"],
        ),
    ]

    return SchemaMetadata(name="test_schema", tables=tables, foreign_keys=foreign_keys)


@pytest.fixture
def complex_schema():
    """
    Schema complejo con múltiples dependencias:

    Countries <- Regions
    Categories (independiente)
    Suppliers (independiente)

    Products <- Categories
    Products <- Suppliers

    Customers <- Regions

    Orders <- Customers
    Orders <- Employees

    OrderDetails <- Orders
    OrderDetails <- Products
    """
    tables = [
        TableMetadata(name="Countries"),
        TableMetadata(name="Regions"),
        TableMetadata(name="Categories"),
        TableMetadata(name="Suppliers"),
        TableMetadata(name="Products"),
        TableMetadata(name="Customers"),
        TableMetadata(name="Employees"),
        TableMetadata(name="Orders"),
        TableMetadata(name="OrderDetails"),
    ]

    foreign_keys = [
        ForeignKeyMetadata(
            constraint_name="fk_regions_country",
            table_name="Regions",
            column_names=["country_id"],
            referenced_table="Countries",
            referenced_columns=["id"],
        ),
        ForeignKeyMetadata(
            constraint_name="fk_products_category",
            table_name="Products",
            column_names=["category_id"],
            referenced_table="Categories",
            referenced_columns=["id"],
        ),
        ForeignKeyMetadata(
            constraint_name="fk_products_supplier",
            table_name="Products",
            column_names=["supplier_id"],
            referenced_table="Suppliers",
            referenced_columns=["id"],
        ),
        ForeignKeyMetadata(
            constraint_name="fk_customers_region",
            table_name="Customers",
            column_names=["region_id"],
            referenced_table="Regions",
            referenced_columns=["id"],
        ),
        ForeignKeyMetadata(
            constraint_name="fk_orders_customer",
            table_name="Orders",
            column_names=["customer_id"],
            referenced_table="Customers",
            referenced_columns=["id"],
        ),
        ForeignKeyMetadata(
            constraint_name="fk_orders_employee",
            table_name="Orders",
            column_names=["employee_id"],
            referenced_table="Employees",
            referenced_columns=["id"],
        ),
        ForeignKeyMetadata(
            constraint_name="fk_orderdetails_order",
            table_name="OrderDetails",
            column_names=["order_id"],
            referenced_table="Orders",
            referenced_columns=["id"],
        ),
        ForeignKeyMetadata(
            constraint_name="fk_orderdetails_product",
            table_name="OrderDetails",
            column_names=["product_id"],
            referenced_table="Products",
            referenced_columns=["id"],
        ),
    ]

    return SchemaMetadata(name="test_schema", tables=tables, foreign_keys=foreign_keys)


@pytest.fixture
def circular_schema():
    """
    Schema con dependencia circular:
    A -> B -> C -> A
    """
    tables = [TableMetadata(name="A"), TableMetadata(name="B"), TableMetadata(name="C")]

    foreign_keys = [
        ForeignKeyMetadata(
            constraint_name="fk_a_b",
            table_name="A",
            column_names=["b_id"],
            referenced_table="B",
            referenced_columns=["id"],
        ),
        ForeignKeyMetadata(
            constraint_name="fk_b_c",
            table_name="B",
            column_names=["c_id"],
            referenced_table="C",
            referenced_columns=["id"],
        ),
        ForeignKeyMetadata(
            constraint_name="fk_c_a",
            table_name="C",
            column_names=["a_id"],
            referenced_table="A",
            referenced_columns=["id"],
        ),
    ]

    return SchemaMetadata(name="test_schema", tables=tables, foreign_keys=foreign_keys)


@pytest.fixture
def self_referencing_schema():
    """
    Schema con auto-referencia:
    Employee -> Employee (manager_id)
    Categories (independiente)
    """
    tables = [TableMetadata(name="Employee"), TableMetadata(name="Categories")]

    foreign_keys = [
        ForeignKeyMetadata(
            constraint_name="fk_employee_manager",
            table_name="Employee",
            column_names=["manager_id"],
            referenced_table="Employee",
            referenced_columns=["id"],
        )
    ]

    return SchemaMetadata(name="test_schema", tables=tables, foreign_keys=foreign_keys)


# ============================================================================
# TESTS: Construcción del grafo
# ============================================================================


class TestGraphConstruction:
    """Tests para construcción del grafo"""

    def test_empty_schema(self, empty_schema):
        """Test con schema vacío"""
        service = DependencyGraphService(empty_schema)

        assert service.graph.number_of_nodes() == 0
        assert service.graph.number_of_edges() == 0

    def test_simple_schema_nodes(self, simple_schema):
        """Test que se creen nodos para todas las tablas"""
        service = DependencyGraphService(simple_schema)

        assert service.graph.number_of_nodes() == 2
        assert "Countries" in service.graph
        assert "Categories" in service.graph

    def test_simple_schema_no_edges(self, simple_schema):
        """Test que no haya aristas si no hay FKs"""
        service = DependencyGraphService(simple_schema)

        assert service.graph.number_of_edges() == 0

    def test_linear_schema_edges(self, linear_schema):
        """Test que se creen aristas correctamente"""
        service = DependencyGraphService(linear_schema)

        assert service.graph.number_of_nodes() == 5
        assert service.graph.number_of_edges() == 4

        # Verificar aristas (A -> B significa A debe crearse antes que B)
        # Regions tiene FK a Countries, entonces Countries -> Regions
        assert service.graph.has_edge("Countries", "Regions")
        assert service.graph.has_edge("Regions", "Customers")
        assert service.graph.has_edge("Customers", "Orders")
        assert service.graph.has_edge("Orders", "OrderDetails")

    def test_self_referencing_no_self_loop(self, self_referencing_schema):
        """Test que auto-referencias no creen self-loops en el grafo"""
        service = DependencyGraphService(self_referencing_schema)

        # El grafo NO debe tener self-loops (aristas Employee -> Employee)
        assert not service.graph.has_edge("Employee", "Employee")
        assert service.graph.number_of_edges() == 0


# ============================================================================
# TESTS: Obtener dependencias
# ============================================================================


class TestGetDependencies:
    """Tests para get_dependencies()"""

    def test_no_dependencies(self, linear_schema):
        """Test tabla sin dependencias"""
        service = DependencyGraphService(linear_schema)

        deps = service.get_dependencies("Countries")
        assert deps == []

    def test_single_dependency(self, linear_schema):
        """Test tabla con una dependencia"""
        service = DependencyGraphService(linear_schema)

        deps = service.get_dependencies("Regions")
        assert deps == ["Countries"]

    def test_multiple_dependencies(self, complex_schema):
        """Test tabla con múltiples dependencias"""
        service = DependencyGraphService(complex_schema)

        deps = service.get_dependencies("Products")
        assert set(deps) == {"Categories", "Suppliers"}

    def test_nonexistent_table(self, simple_schema):
        """Test tabla inexistente"""
        service = DependencyGraphService(simple_schema)

        deps = service.get_dependencies("NonExistent")
        assert deps == []


# ============================================================================
# TESTS: Obtener dependientes
# ============================================================================


class TestGetDependents:
    """Tests para get_dependents()"""

    def test_no_dependents(self, linear_schema):
        """Test tabla sin dependientes"""
        service = DependencyGraphService(linear_schema)

        dependents = service.get_dependents("OrderDetails")
        assert dependents == []

    def test_single_dependent(self, linear_schema):
        """Test tabla con un dependiente"""
        service = DependencyGraphService(linear_schema)

        dependents = service.get_dependents("Countries")
        assert dependents == ["Regions"]

    def test_multiple_dependents(self, complex_schema):
        """Test tabla con múltiples dependientes"""
        service = DependencyGraphService(complex_schema)

        dependents = service.get_dependents("Orders")
        assert dependents == ["OrderDetails"]

        dependents = service.get_dependents("Regions")
        assert set(dependents) == {"Customers"}


# ============================================================================
# TESTS: Detección de ciclos
# ============================================================================


class TestCircularDependencies:
    """Tests para detección de dependencias circulares"""

    def test_no_cycles_empty(self, empty_schema):
        """Test schema vacío no tiene ciclos"""
        service = DependencyGraphService(empty_schema)

        assert not service.has_circular_dependencies()

    def test_no_cycles_simple(self, simple_schema):
        """Test schema simple no tiene ciclos"""
        service = DependencyGraphService(simple_schema)

        assert not service.has_circular_dependencies()

    def test_no_cycles_linear(self, linear_schema):
        """Test schema lineal no tiene ciclos"""
        service = DependencyGraphService(linear_schema)

        assert not service.has_circular_dependencies()

    def test_no_cycles_complex(self, complex_schema):
        """Test schema complejo sin ciclos"""
        service = DependencyGraphService(complex_schema)

        assert not service.has_circular_dependencies()

    def test_has_cycle(self, circular_schema):
        """Test detección de ciclo"""
        service = DependencyGraphService(circular_schema)

        assert service.has_circular_dependencies()

    def test_find_cycles(self, circular_schema):
        """Test encontrar ciclos específicos"""
        service = DependencyGraphService(circular_schema)

        cycles = service.find_circular_dependencies()

        assert len(cycles) > 0
        # Verificar que el ciclo encontrado contiene A, B, C
        cycle = cycles[0]
        assert set(cycle[:-1]) == {"A", "B", "C"}
        # Verificar que el ciclo está cerrado (primer y último elemento iguales)
        assert cycle[0] == cycle[-1]

    def test_no_cycles_self_referencing(self, self_referencing_schema):
        """Test que auto-referencias no se consideren ciclos"""
        service = DependencyGraphService(self_referencing_schema)

        # Auto-referencias no crean aristas, por lo tanto no hay ciclos
        assert not service.has_circular_dependencies()


# ============================================================================
# TESTS: Auto-referencias
# ============================================================================


class TestSelfReferencing:
    """Tests para get_self_referencing_tables()"""

    def test_no_self_references(self, linear_schema):
        """Test schema sin auto-referencias"""
        service = DependencyGraphService(linear_schema)

        self_refs = service.get_self_referencing_tables()
        assert len(self_refs) == 0

    def test_single_self_reference(self, self_referencing_schema):
        """Test una tabla con auto-referencia"""
        service = DependencyGraphService(self_referencing_schema)

        self_refs = service.get_self_referencing_tables()
        assert len(self_refs) == 1

        table_name, fks = self_refs[0]
        assert table_name == "Employee"
        assert len(fks) == 1
        assert fks[0].constraint_name == "fk_employee_manager"

    def test_multiple_self_references_same_table(self):
        """Test tabla con múltiples auto-referencias"""
        tables = [TableMetadata(name="Node")]

        foreign_keys = [
            ForeignKeyMetadata(
                constraint_name="fk_node_parent",
                table_name="Node",
                column_names=["parent_id"],
                referenced_table="Node",
                referenced_columns=["id"],
            ),
            ForeignKeyMetadata(
                constraint_name="fk_node_next",
                table_name="Node",
                column_names=["next_id"],
                referenced_table="Node",
                referenced_columns=["id"],
            ),
        ]

        schema = SchemaMetadata(name="test", tables=tables, foreign_keys=foreign_keys)
        service = DependencyGraphService(schema)

        self_refs = service.get_self_referencing_tables()
        assert len(self_refs) == 1

        table_name, fks = self_refs[0]
        assert table_name == "Node"
        assert len(fks) == 2


# ============================================================================
# TESTS: Topological Sort
# ============================================================================


class TestTopologicalSort:
    """Tests para topological_sort()"""

    def test_empty_schema_sort(self, empty_schema):
        """Test ordenamiento de schema vacío"""
        service = DependencyGraphService(empty_schema)

        sorted_tables = service.topological_sort()
        assert sorted_tables == []

    def test_simple_schema_sort(self, simple_schema):
        """Test ordenamiento de tablas independientes"""
        service = DependencyGraphService(simple_schema)

        sorted_tables = service.topological_sort()
        assert len(sorted_tables) == 2
        assert set(sorted_tables) == {"Countries", "Categories"}

    def test_linear_schema_sort(self, linear_schema):
        """Test ordenamiento lineal"""
        service = DependencyGraphService(linear_schema)

        sorted_tables = service.topological_sort()

        # Verificar que Countries está antes que Regions
        assert sorted_tables.index("Countries") < sorted_tables.index("Regions")
        assert sorted_tables.index("Regions") < sorted_tables.index("Customers")
        assert sorted_tables.index("Customers") < sorted_tables.index("Orders")
        assert sorted_tables.index("Orders") < sorted_tables.index("OrderDetails")

    def test_complex_schema_sort(self, complex_schema):
        """Test ordenamiento complejo"""
        service = DependencyGraphService(complex_schema)

        sorted_tables = service.topological_sort()

        # Verificar invariantes
        assert sorted_tables.index("Countries") < sorted_tables.index("Regions")
        assert sorted_tables.index("Regions") < sorted_tables.index("Customers")
        assert sorted_tables.index("Categories") < sorted_tables.index("Products")
        assert sorted_tables.index("Suppliers") < sorted_tables.index("Products")
        assert sorted_tables.index("Customers") < sorted_tables.index("Orders")
        assert sorted_tables.index("Employees") < sorted_tables.index("Orders")
        assert sorted_tables.index("Orders") < sorted_tables.index("OrderDetails")
        assert sorted_tables.index("Products") < sorted_tables.index("OrderDetails")

    def test_circular_raises_error(self, circular_schema):
        """Test que ciclo lance excepción"""
        service = DependencyGraphService(circular_schema)

        with pytest.raises(CircularDependencyError) as exc_info:
            service.topological_sort()

        # Verificar que la excepción contiene información del ciclo
        assert exc_info.value.cycle is not None


# ============================================================================
# TESTS: Tablas independientes
# ============================================================================


class TestIndependentTables:
    """Tests para get_independent_tables()"""

    def test_empty_schema_independent(self, empty_schema):
        """Test schema vacío"""
        service = DependencyGraphService(empty_schema)

        independent = service.get_independent_tables()
        assert independent == []

    def test_all_independent(self, simple_schema):
        """Test todas las tablas independientes"""
        service = DependencyGraphService(simple_schema)

        independent = service.get_independent_tables()
        assert set(independent) == {"Countries", "Categories"}

    def test_linear_one_independent(self, linear_schema):
        """Test una tabla independiente en cadena"""
        service = DependencyGraphService(linear_schema)

        independent = service.get_independent_tables()
        assert independent == ["Countries"]

    def test_complex_multiple_independent(self, complex_schema):
        """Test múltiples tablas independientes"""
        service = DependencyGraphService(complex_schema)

        independent = service.get_independent_tables()
        assert set(independent) == {"Countries", "Categories", "Suppliers", "Employees"}


# ============================================================================
# TESTS: Niveles de dependencia
# ============================================================================


class TestDependencyLevels:
    """Tests para get_dependency_levels()"""

    def test_empty_levels(self, empty_schema):
        """Test niveles de schema vacío"""
        service = DependencyGraphService(empty_schema)

        levels = service.get_dependency_levels()
        assert levels == {}

    def test_simple_levels(self, simple_schema):
        """Test niveles de tablas independientes"""
        service = DependencyGraphService(simple_schema)

        levels = service.get_dependency_levels()

        assert len(levels) == 1
        assert set(levels[0]) == {"Countries", "Categories"}

    def test_linear_levels(self, linear_schema):
        """Test niveles en cadena lineal"""
        service = DependencyGraphService(linear_schema)

        levels = service.get_dependency_levels()

        assert len(levels) == 5
        assert levels[0] == ["Countries"]
        assert levels[1] == ["Regions"]
        assert levels[2] == ["Customers"]
        assert levels[3] == ["Orders"]
        assert levels[4] == ["OrderDetails"]

    def test_complex_levels(self, complex_schema):
        """Test niveles en schema complejo"""
        service = DependencyGraphService(complex_schema)

        levels = service.get_dependency_levels()

        # Nivel 0: tablas sin dependencias
        assert set(levels[0]) == {"Countries", "Categories", "Suppliers", "Employees"}

        # Nivel 1: dependen de nivel 0
        assert set(levels[1]) == {"Regions", "Products"}

        # Nivel 2: dependen de nivel 1
        assert set(levels[2]) == {"Customers"}

        # Nivel 3: dependen de nivel 2
        assert set(levels[3]) == {"Orders"}

        # Nivel 4: dependen de nivel 3
        assert set(levels[4]) == {"OrderDetails"}

    def test_circular_raises_error(self, circular_schema):
        """Test que ciclo lance excepción"""
        service = DependencyGraphService(circular_schema)

        with pytest.raises(CircularDependencyError):
            service.get_dependency_levels()


# ============================================================================
# TESTS: Orden de migración y eliminación
# ============================================================================


class TestMigrationOrder:
    """Tests para get_migration_order() y get_deletion_order()"""

    def test_migration_order(self, linear_schema):
        """Test orden de migración"""
        service = DependencyGraphService(linear_schema)

        order = service.get_migration_order()

        # Debe ser igual al topological sort
        assert order == service.topological_sort()

    def test_deletion_order(self, linear_schema):
        """Test orden de eliminación"""
        service = DependencyGraphService(linear_schema)

        deletion_order = service.get_deletion_order()
        migration_order = service.get_migration_order()

        # Debe ser el inverso del orden de migración
        assert deletion_order == list(reversed(migration_order))

    def test_deletion_order_correctness(self, linear_schema):
        """Test que el orden de eliminación sea correcto"""
        service = DependencyGraphService(linear_schema)

        order = service.get_deletion_order()

        # OrderDetails debe eliminarse antes que Orders
        assert order.index("OrderDetails") < order.index("Orders")
        assert order.index("Orders") < order.index("Customers")
        assert order.index("Customers") < order.index("Regions")
        assert order.index("Regions") < order.index("Countries")


# ============================================================================
# TESTS: Análisis completo
# ============================================================================


class TestAnalyzeDependencies:
    """Tests para analyze_dependencies()"""

    def test_analyze_empty(self, empty_schema):
        """Test análisis de schema vacío"""
        service = DependencyGraphService(empty_schema)

        analysis = service.analyze_dependencies()

        assert analysis["total_tables"] == 0
        assert analysis["total_foreign_keys"] == 0
        assert not analysis["has_cycles"]
        assert analysis["cycles"] == []
        assert analysis["self_referencing_tables"] == []
        assert analysis["independent_tables"] == []
        assert analysis["migration_order"] == []
        assert analysis["max_parallelization"] == 0

    def test_analyze_simple(self, simple_schema):
        """Test análisis de schema simple"""
        service = DependencyGraphService(simple_schema)

        analysis = service.analyze_dependencies()

        assert analysis["total_tables"] == 2
        assert analysis["total_foreign_keys"] == 0
        assert not analysis["has_cycles"]
        assert set(analysis["independent_tables"]) == {"Countries", "Categories"}
        assert analysis["max_parallelization"] == 2

    def test_analyze_linear(self, linear_schema):
        """Test análisis de schema lineal"""
        service = DependencyGraphService(linear_schema)

        analysis = service.analyze_dependencies()

        assert analysis["total_tables"] == 5
        assert analysis["total_foreign_keys"] == 4
        assert not analysis["has_cycles"]
        assert analysis["independent_tables"] == ["Countries"]
        assert len(analysis["migration_order"]) == 5
        assert analysis["max_parallelization"] == 1

    def test_analyze_complex(self, complex_schema):
        """Test análisis de schema complejo"""
        service = DependencyGraphService(complex_schema)

        analysis = service.analyze_dependencies()

        assert analysis["total_tables"] == 9
        assert analysis["total_foreign_keys"] == 8
        assert not analysis["has_cycles"]
        assert set(analysis["independent_tables"]) == {
            "Countries",
            "Categories",
            "Suppliers",
            "Employees",
        }
        assert analysis["max_parallelization"] == 4

    def test_analyze_circular(self, circular_schema):
        """Test análisis de schema con ciclos"""
        service = DependencyGraphService(circular_schema)

        analysis = service.analyze_dependencies()

        assert analysis["has_cycles"]
        assert len(analysis["cycles"]) > 0
        assert analysis["migration_order"] == []  # No se puede ordenar con ciclos

    def test_analyze_self_referencing(self, self_referencing_schema):
        """Test análisis con auto-referencias"""
        service = DependencyGraphService(self_referencing_schema)

        analysis = service.analyze_dependencies()

        assert "Employee" in analysis["self_referencing_tables"]
        assert not analysis["has_cycles"]  # Auto-referencias no son ciclos


# ============================================================================
# TESTS: Profundidad de tabla
# ============================================================================


class TestTableDepth:
    """Tests para get_table_depth()"""

    def test_depth_independent_table(self, linear_schema):
        """Test profundidad de tabla independiente"""
        service = DependencyGraphService(linear_schema)

        depth = service.get_table_depth("Countries")
        assert depth == 0

    def test_depth_dependent_table(self, linear_schema):
        """Test profundidad de tabla dependiente"""
        service = DependencyGraphService(linear_schema)

        assert service.get_table_depth("Regions") == 1
        assert service.get_table_depth("Customers") == 2
        assert service.get_table_depth("Orders") == 3
        assert service.get_table_depth("OrderDetails") == 4

    def test_depth_nonexistent_table(self, linear_schema):
        """Test profundidad de tabla inexistente"""
        service = DependencyGraphService(linear_schema)

        with pytest.raises(ValueError, match="no existe"):
            service.get_table_depth("NonExistent")

    def test_depth_complex_schema(self, complex_schema):
        """Test profundidad en schema complejo"""
        service = DependencyGraphService(complex_schema)

        # Nivel 0
        assert service.get_table_depth("Countries") == 0
        assert service.get_table_depth("Categories") == 0

        # Nivel 1
        assert service.get_table_depth("Regions") == 1
        assert service.get_table_depth("Products") == 1

        # Nivel 2
        assert service.get_table_depth("Customers") == 2

        # Nivel 3
        assert service.get_table_depth("Orders") == 3

        # Nivel 4
        assert service.get_table_depth("OrderDetails") == 4


# ============================================================================
# TESTS: Ruta crítica
# ============================================================================


class TestCriticalPath:
    """Tests para get_critical_path()"""

    def test_critical_path_empty(self, empty_schema):
        """Test ruta crítica en schema vacío"""
        service = DependencyGraphService(empty_schema)

        path = service.get_critical_path()
        assert path == []

    def test_critical_path_simple(self, simple_schema):
        """Test ruta crítica en tablas independientes"""
        service = DependencyGraphService(simple_schema)

        path = service.get_critical_path()
        # Puede ser cualquier tabla (todas tienen longitud 0)
        assert len(path) <= 1

    def test_critical_path_linear(self, linear_schema):
        """Test ruta crítica en cadena lineal"""
        service = DependencyGraphService(linear_schema)

        path = service.get_critical_path()

        # La ruta crítica debe ser toda la cadena
        assert len(path) == 5
        assert "Countries" in path
        assert "OrderDetails" in path

    def test_critical_path_circular(self, circular_schema):
        """Test ruta crítica con ciclos"""
        service = DependencyGraphService(circular_schema)

        path = service.get_critical_path()
        # No se puede calcular con ciclos
        assert path == []


# ============================================================================
# TESTS: Paralelización
# ============================================================================


class TestParallelization:
    """Tests para can_parallelize() y get_parallel_batches()"""

    def test_can_parallelize_independent(self, simple_schema):
        """Test que tablas independientes pueden paralelizarse"""
        service = DependencyGraphService(simple_schema)

        assert service.can_parallelize(["Countries", "Categories"])

    def test_can_parallelize_dependent(self, linear_schema):
        """Test que tablas dependientes NO pueden paralelizarse"""
        service = DependencyGraphService(linear_schema)

        assert not service.can_parallelize(["Countries", "Regions"])
        assert not service.can_parallelize(["Regions", "Customers"])

    def test_can_parallelize_mixed(self, complex_schema):
        """Test paralelización en schema complejo"""
        service = DependencyGraphService(complex_schema)

        # Tablas independientes pueden paralelizarse
        assert service.can_parallelize(["Countries", "Categories", "Suppliers"])

        # Tablas con dependencias no pueden paralelizarse
        assert not service.can_parallelize(["Countries", "Regions"])

    def test_parallel_batches_simple(self, simple_schema):
        """Test batches en schema simple"""
        service = DependencyGraphService(simple_schema)

        batches = service.get_parallel_batches()

        assert len(batches) == 1
        assert set(batches[0]) == {"Countries", "Categories"}

    def test_parallel_batches_linear(self, linear_schema):
        """Test batches en schema lineal"""
        service = DependencyGraphService(linear_schema)

        batches = service.get_parallel_batches()

        # Cada tabla en su propio batch (no hay paralelización)
        assert len(batches) == 5
        assert batches[0] == ["Countries"]
        assert batches[1] == ["Regions"]
        assert batches[2] == ["Customers"]
        assert batches[3] == ["Orders"]
        assert batches[4] == ["OrderDetails"]

    def test_parallel_batches_complex(self, complex_schema):
        """Test batches en schema complejo"""
        service = DependencyGraphService(complex_schema)

        batches = service.get_parallel_batches()

        # Nivel 0: 4 tablas en paralelo
        assert len(batches[0]) == 4
        assert set(batches[0]) == {"Countries", "Categories", "Suppliers", "Employees"}

        # Nivel 1: 2 tablas en paralelo
        assert len(batches[1]) == 2
        assert set(batches[1]) == {"Regions", "Products"}

    def test_parallel_batches_with_max_size(self, complex_schema):
        """Test batches con tamaño máximo"""
        service = DependencyGraphService(complex_schema)

        batches = service.get_parallel_batches(max_batch_size=2)

        # El nivel 0 tiene 4 tablas, debe dividirse en 2 batches de 2
        level_0_batches = [
            b
            for b in batches
            if any(t in b for t in ["Countries", "Categories", "Suppliers", "Employees"])
        ]
        assert len(level_0_batches) == 2

    def test_parallel_batches_circular_raises(self, circular_schema):
        """Test batches con ciclos"""
        service = DependencyGraphService(circular_schema)

        with pytest.raises(CircularDependencyError):
            service.get_parallel_batches()


# ============================================================================
# TESTS: Casos Edge
# ============================================================================


class TestEdgeCases:
    """Tests para casos especiales y límites"""

    def test_single_table_no_fks(self):
        """Test una sola tabla sin FKs"""
        schema = SchemaMetadata(
            name="test", tables=[TableMetadata(name="OnlyTable")], foreign_keys=[]
        )
        service = DependencyGraphService(schema)

        assert service.get_independent_tables() == ["OnlyTable"]
        assert service.topological_sort() == ["OnlyTable"]
        assert not service.has_circular_dependencies()

    def test_two_way_cycle(self):
        """Test ciclo bidireccional A <-> B"""
        tables = [TableMetadata(name="A"), TableMetadata(name="B")]

        foreign_keys = [
            ForeignKeyMetadata(
                constraint_name="fk_a_b",
                table_name="A",
                column_names=["b_id"],
                referenced_table="B",
                referenced_columns=["id"],
            ),
            ForeignKeyMetadata(
                constraint_name="fk_b_a",
                table_name="B",
                column_names=["a_id"],
                referenced_table="A",
                referenced_columns=["id"],
            ),
        ]

        schema = SchemaMetadata(name="test", tables=tables, foreign_keys=foreign_keys)
        service = DependencyGraphService(schema)

        assert service.has_circular_dependencies()
        cycles = service.find_circular_dependencies()
        assert len(cycles) > 0

    def test_composite_foreign_keys(self):
        """Test FKs compuestas (múltiples columnas)"""
        tables = [TableMetadata(name="Parent"), TableMetadata(name="Child")]

        foreign_keys = [
            ForeignKeyMetadata(
                constraint_name="fk_child_parent",
                table_name="Child",
                column_names=["parent_id1", "parent_id2"],
                referenced_table="Parent",
                referenced_columns=["id1", "id2"],
            )
        ]

        schema = SchemaMetadata(name="test", tables=tables, foreign_keys=foreign_keys)
        service = DependencyGraphService(schema)

        deps = service.get_dependencies("Child")
        assert deps == ["Parent"]

    def test_multiple_fks_same_tables(self):
        """Test múltiples FKs entre las mismas tablas"""
        tables = [TableMetadata(name="Orders"), TableMetadata(name="Users")]

        foreign_keys = [
            ForeignKeyMetadata(
                constraint_name="fk_orders_customer",
                table_name="Orders",
                column_names=["customer_id"],
                referenced_table="Users",
                referenced_columns=["id"],
            ),
            ForeignKeyMetadata(
                constraint_name="fk_orders_seller",
                table_name="Orders",
                column_names=["seller_id"],
                referenced_table="Users",
                referenced_columns=["id"],
            ),
        ]

        schema = SchemaMetadata(name="test", tables=tables, foreign_keys=foreign_keys)
        service = DependencyGraphService(schema)

        # Debe haber solo una arista (networkx no permite múltiples aristas)
        deps = service.get_dependencies("Orders")
        assert deps == ["Users"]

    def test_disconnected_components(self):
        """Test grafos con componentes desconectados"""
        tables = [
            TableMetadata(name="A"),
            TableMetadata(name="B"),
            TableMetadata(name="X"),
            TableMetadata(name="Y"),
        ]

        foreign_keys = [
            ForeignKeyMetadata(
                constraint_name="fk_b_a",
                table_name="B",
                column_names=["a_id"],
                referenced_table="A",
                referenced_columns=["id"],
            ),
            ForeignKeyMetadata(
                constraint_name="fk_y_x",
                table_name="Y",
                column_names=["x_id"],
                referenced_table="X",
                referenced_columns=["id"],
            ),
        ]

        schema = SchemaMetadata(name="test", tables=tables, foreign_keys=foreign_keys)
        service = DependencyGraphService(schema)

        # Debe poder ordenar sin problemas
        sorted_tables = service.topological_sort()
        assert len(sorted_tables) == 4

        # A y X deben estar antes que B y Y respectivamente
        assert sorted_tables.index("A") < sorted_tables.index("B")
        assert sorted_tables.index("X") < sorted_tables.index("Y")

    def test_large_dependency_chain(self):
        """Test cadena larga de dependencias"""
        n = 20
        tables = [TableMetadata(name=f"Table{i}") for i in range(n)]

        foreign_keys = [
            ForeignKeyMetadata(
                constraint_name=f"fk_{i}_{i-1}",
                table_name=f"Table{i}",
                column_names=["prev_id"],
                referenced_table=f"Table{i-1}",
                referenced_columns=["id"],
            )
            for i in range(1, n)
        ]

        schema = SchemaMetadata(name="test", tables=tables, foreign_keys=foreign_keys)
        service = DependencyGraphService(schema)

        sorted_tables = service.topological_sort()
        assert len(sorted_tables) == n

        # Verificar orden correcto
        for i in range(n):
            assert sorted_tables[i] == f"Table{i}"

        # Profundidad de la última tabla debe ser n-1
        assert service.get_table_depth(f"Table{n-1}") == n - 1
