"""
Dependency Graph Service

Servicio para construir y analizar grafos de dependencias entre tablas basados en foreign keys.
Permite identificar el orden correcto de migración, detectar ciclos, y paralelizar operaciones.

Funcionalidades:
- Construir grafo dirigido de dependencias FK
- Topological sort usando algoritmo de Kahn
- Detectar dependencias circulares
- Identificar tablas independientes para paralelización
- Manejo de casos edge (auto-referencias, ciclos complejos)
"""

from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from app.models.db_metadata.constraint import ForeignKeyMetadata
from app.models.db_metadata.schema import SchemaMetadata


class CircularDependencyError(Exception):
    """Excepción lanzada cuando se detecta una dependencia circular"""

    def __init__(self, cycle: List[str]):
        self.cycle = cycle
        cycle_str = " -> ".join(cycle)
        super().__init__(f"Dependencia circular detectada: {cycle_str}")


class DependencyGraphService:
    """
    Servicio para analizar dependencias entre tablas.

    El grafo es dirigido: una arista A -> B significa que la tabla A depende de B
    (A tiene una FK que referencia a B, por lo tanto B debe crearse antes que A).
    """

    def __init__(self, schema_metadata: SchemaMetadata):
        """
        Inicializa el servicio con metadata de un schema.

        Args:
            schema_metadata: Metadata del schema que contiene tablas y foreign keys
        """
        self.schema_metadata = schema_metadata
        self.graph = nx.DiGraph()
        self._build_graph()

    def _build_graph(self) -> None:
        """
        Construye el grafo de dependencias a partir de foreign keys.

        Nodos: nombres de tablas
        Aristas: A -> B si tabla B depende de A (B tiene FK a A)

        Para migración, si hay arista A -> B, entonces A debe crearse antes que B.
        """
        # Agregar todos los nodos (tablas)
        for table in self.schema_metadata.tables:
            self.graph.add_node(table.name)

        # Agregar aristas basadas en foreign keys
        for fk in self.schema_metadata.foreign_keys:
            source_table = fk.table_name
            target_table = fk.referenced_table

            # Agregar arista: target -> source (target debe crearse antes que source)
            # Porque source tiene FK a target
            # Solo si no es auto-referencia (se manejan por separado)
            if source_table != target_table:
                self.graph.add_edge(target_table, source_table)

    def get_dependencies(self, table_name: str) -> List[str]:
        """
        Obtiene las tablas de las que depende una tabla dada.

        Args:
            table_name: Nombre de la tabla

        Returns:
            Lista de nombres de tablas de las que depende table_name

        Example:
            Si Orders tiene FK a Customers y Products:
            get_dependencies("Orders") -> ["Customers", "Products"]
        """
        if table_name not in self.graph:
            return []

        # Las dependencias son los predecesores (tablas que deben crearse antes)
        return list(self.graph.predecessors(table_name))

    def get_dependents(self, table_name: str) -> List[str]:
        """
        Obtiene las tablas que dependen de una tabla dada.

        Args:
            table_name: Nombre de la tabla

        Returns:
            Lista de nombres de tablas que dependen de table_name

        Example:
            Si Orders y OrderDetails tienen FK a Products:
            get_dependents("Products") -> ["Orders", "OrderDetails"]
        """
        if table_name not in self.graph:
            return []

        # Los dependientes son los sucesores (tablas que dependen de esta)
        return list(self.graph.successors(table_name))

    def has_circular_dependencies(self) -> bool:
        """
        Verifica si existen dependencias circulares en el grafo.

        Returns:
            True si hay ciclos, False en caso contrario
        """
        try:
            # NetworkX lanza NetworkXUnfeasible si hay ciclos
            list(nx.topological_sort(self.graph))
            return False
        except (nx.NetworkXError, nx.NetworkXUnfeasible):
            return True

    def find_circular_dependencies(self) -> List[List[str]]:
        """
        Encuentra todos los ciclos en el grafo de dependencias.

        Returns:
            Lista de ciclos, donde cada ciclo es una lista de nombres de tablas

        Example:
            [["A", "B", "C", "A"], ["X", "Y", "X"]]
        """
        try:
            cycles = list(nx.simple_cycles(self.graph))
            # Cerrar cada ciclo agregando el primer nodo al final para claridad
            return [cycle + [cycle[0]] for cycle in cycles]
        except Exception:
            return []

    def get_self_referencing_tables(self) -> List[Tuple[str, List[ForeignKeyMetadata]]]:
        """
        Identifica tablas con auto-referencias (FK a sí mismas).

        Returns:
            Lista de tuplas (nombre_tabla, lista_de_fks_auto_referentes)

        Example:
            Tabla Employee con FK manager_id -> Employee.id:
            [("Employee", [ForeignKeyMetadata(...)])]
        """
        self_refs: list[Any] = []

        for fk in self.schema_metadata.foreign_keys:
            if fk.table_name == fk.referenced_table:
                # Buscar si ya agregamos esta tabla
                found = False
                for i, (table_name, fks) in enumerate(self_refs):
                    if table_name == fk.table_name:
                        self_refs[i][1].append(fk)
                        found = True
                        break

                if not found:
                    self_refs.append((fk.table_name, [fk]))

        return self_refs

    def topological_sort(self) -> List[str]:
        """
        Ordena las tablas topológicamente usando el algoritmo de Kahn.

        El orden resultante garantiza que si tabla A depende de B, entonces B
        aparece antes que A en la lista.

        Returns:
            Lista ordenada de nombres de tablas

        Raises:
            CircularDependencyError: Si existen dependencias circulares

        Algorithm:
            1. Calcular in-degree de cada nodo
            2. Encolar nodos con in-degree 0
            3. Mientras haya nodos en la cola:
               - Desencolar nodo
               - Agregar a resultado
               - Reducir in-degree de vecinos
               - Encolar vecinos con in-degree 0
            4. Si quedan nodos sin procesar, hay ciclo
        """
        # Verificar si hay ciclos
        if self.has_circular_dependencies():
            cycles = self.find_circular_dependencies()
            if cycles:
                raise CircularDependencyError(cycles[0])
            else:
                raise CircularDependencyError(["Unknown cycle"])

        # Usar el topological sort de NetworkX (implementa Kahn)
        try:
            return list(nx.topological_sort(self.graph))
        except nx.NetworkXError as e:
            # Esto no debería ocurrir porque ya verificamos ciclos
            raise CircularDependencyError(["Unknown cycle"]) from e

    def get_independent_tables(self) -> List[str]:
        """
        Identifica tablas sin dependencias (no tienen FK a otras tablas).

        Estas tablas pueden crearse/migrarse primero y en paralelo.

        Returns:
            Lista de nombres de tablas sin dependencias

        Example:
            Tablas lookup independientes: ["Countries", "Categories", "Statuses"]
        """
        independent = []

        for node in self.graph.nodes():
            # Una tabla es independiente si no tiene aristas entrantes (in_degree = 0)
            # Es decir, ninguna otra tabla debe crearse antes que esta
            if self.graph.in_degree(node) == 0:
                independent.append(node)

        return independent

    def get_dependency_levels(self) -> Dict[int, List[str]]:
        """
        Agrupa tablas por niveles de dependencia para paralelización.

        Nivel 0: Tablas sin dependencias (pueden ejecutarse en paralelo)
        Nivel 1: Tablas que solo dependen de nivel 0
        Nivel N: Tablas que dependen de niveles 0 a N-1

        Returns:
            Diccionario {nivel: [tabla1, tabla2, ...]}

        Example:
            {
                0: ["Countries", "Categories"],
                1: ["Products", "Customers"],
                2: ["Orders"],
                3: ["OrderDetails"]
            }

        Raises:
            CircularDependencyError: Si existen dependencias circulares
        """
        # Obtener orden topológico
        sorted_tables = self.topological_sort()

        # Asignar niveles
        levels: Dict[int, List[str]] = defaultdict(list)
        table_level: Dict[str, int] = {}

        for table in sorted_tables:
            # El nivel de una tabla es el máximo nivel de sus dependencias + 1
            dependencies = self.get_dependencies(table)

            if not dependencies:
                # Sin dependencias -> nivel 0
                level = 0
            else:
                # Nivel = max(niveles de dependencias) + 1
                max_dep_level = max(table_level.get(dep, 0) for dep in dependencies)
                level = max_dep_level + 1

            table_level[table] = level
            levels[level].append(table)

        return dict(levels)

    def get_migration_order(self) -> List[str]:
        """
        Obtiene el orden recomendado para migración de tablas.

        Alias de topological_sort() con semántica más clara.

        Returns:
            Lista ordenada de nombres de tablas para migración

        Raises:
            CircularDependencyError: Si existen dependencias circulares
        """
        return self.topological_sort()

    def get_deletion_order(self) -> List[str]:
        """
        Obtiene el orden recomendado para eliminación de tablas.

        Es el inverso del orden de migración: las tablas con más dependencias
        se eliminan primero.

        Returns:
            Lista ordenada de nombres de tablas para eliminación

        Raises:
            CircularDependencyError: Si existen dependencias circulares
        """
        return list(reversed(self.topological_sort()))

    def analyze_dependencies(self) -> Dict:
        """
        Genera un análisis completo de las dependencias del schema.

        Returns:
            Diccionario con análisis completo:
            {
                "total_tables": int,
                "total_foreign_keys": int,
                "has_cycles": bool,
                "cycles": List[List[str]],
                "self_referencing_tables": List[str],
                "independent_tables": List[str],
                "dependency_levels": Dict[int, List[str]],
                "migration_order": List[str],
                "max_parallelization": int
            }
        """
        self_refs = self.get_self_referencing_tables()

        try:
            levels = self.get_dependency_levels()
            migration_order = self.get_migration_order()
            max_parallel = max(len(tables) for tables in levels.values()) if levels else 0
        except CircularDependencyError:
            levels = {}
            migration_order = []
            max_parallel = 0

        return {
            "total_tables": len(self.schema_metadata.tables),
            "total_foreign_keys": len(self.schema_metadata.foreign_keys),
            "has_cycles": self.has_circular_dependencies(),
            "cycles": self.find_circular_dependencies(),
            "self_referencing_tables": [table_name for table_name, _ in self_refs],
            "independent_tables": self.get_independent_tables(),
            "dependency_levels": levels,
            "migration_order": migration_order,
            "max_parallelization": max_parallel,
        }

    def get_table_depth(self, table_name: str) -> int:
        """
        Calcula la profundidad de dependencia de una tabla.

        Profundidad 0: tabla sin dependencias
        Profundidad N: tabla depende de tablas con profundidad máxima N-1

        Args:
            table_name: Nombre de la tabla

        Returns:
            Profundidad de la tabla (nivel en el grafo de dependencias)

        Raises:
            ValueError: Si la tabla no existe
            CircularDependencyError: Si hay ciclos
        """
        if table_name not in self.graph:
            raise ValueError(f"Tabla '{table_name}' no existe en el schema")

        levels = self.get_dependency_levels()

        for level, tables in levels.items():
            if table_name in tables:
                return level

        return 0

    def get_critical_path(self) -> List[str]:
        """
        Identifica la ruta crítica (camino más largo) en el grafo de dependencias.

        La ruta crítica determina el tiempo mínimo de migración secuencial.

        Returns:
            Lista de tablas en la ruta crítica, de menos a más dependencias

        Example:
            ["Countries", "Regions", "Customers", "Orders", "OrderDetails"]
        """
        if self.has_circular_dependencies():
            return []

        try:
            # Encontrar el camino más largo usando longest_path de NetworkX
            path = nx.dag_longest_path(self.graph)
            return list(path)
        except Exception:
            return []

    def can_parallelize(self, tables: List[str]) -> bool:
        """
        Verifica si un conjunto de tablas puede migrarse en paralelo.

        Las tablas pueden migrarse en paralelo si no tienen dependencias entre sí.

        Args:
            tables: Lista de nombres de tablas

        Returns:
            True si pueden ejecutarse en paralelo, False en caso contrario
        """
        # Crear subgrafo con solo las tablas especificadas
        subgraph = self.graph.subgraph(tables)

        # Pueden ejecutarse en paralelo si no hay aristas entre ellas
        return bool(subgraph.number_of_edges() == 0)

    def get_parallel_batches(self, max_batch_size: Optional[int] = None) -> List[List[str]]:
        """
        Genera batches de tablas que pueden migrarse en paralelo.

        Args:
            max_batch_size: Tamaño máximo de cada batch (None = sin límite)

        Returns:
            Lista de batches, donde cada batch es una lista de tablas
            que pueden ejecutarse en paralelo

        Example:
            [
                ["Countries", "Categories", "Statuses"],
                ["Products", "Customers"],
                ["Orders"],
                ["OrderDetails"]
            ]

        Raises:
            CircularDependencyError: Si existen dependencias circulares
        """
        levels = self.get_dependency_levels()
        batches = []

        for level in sorted(levels.keys()):
            tables = levels[level]

            if max_batch_size is None or len(tables) <= max_batch_size:
                batches.append(tables)
            else:
                # Dividir en batches más pequeños
                for i in range(0, len(tables), max_batch_size):
                    batch = tables[i : i + max_batch_size]
                    batches.append(batch)

        return batches
