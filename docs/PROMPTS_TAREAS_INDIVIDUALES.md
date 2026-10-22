# Prompts de Tareas Individuales - Sistema Enterprise de Migración

> Documento histórico: el SQL citado está archivado en `backend/docs/legacy_sql/`; el esquema sale de Alembic.

**Fecha**: 2025-01-16
**Propósito**: Prompts copy-paste para ejecutar cada tarea de forma independiente
**Uso**: Copiar el prompt completo y pegarlo en un nuevo chat de Claude

---

## 📋 Índice de Tareas

### FASE 1 - CRÍTICO PARA DEMOS
- [1.1 Dependency Graph Service](#tarea-11-dependency-graph-service)
- [1.2 Enhanced Migration Script Service](#tarea-12-enhanced-migration-script-service)
- [1.3 Execution Service](#tarea-13-execution-service)
- [1.4 Migration API Endpoints](#tarea-14-migration-api-endpoints)
- [1.5 Connector Polish](#tarea-15-connector-polish)
- [1.6 Database Migration Schema](#tarea-16-database-migration-schema)

### FASE 2 - VALIDACIÓN Y ROBUSTEZ
- [2.1 Validation Service](#tarea-21-validation-service)
- [2.2 Transformation Service](#tarea-22-transformation-service)
- [2.3 Error Recovery & Retry](#tarea-23-error-recovery--retry)
- [2.4 Validation API Endpoints](#tarea-24-validation-api-endpoints)

### FASE 3 - ENTERPRISE FEATURES
- [3.1 Documentation Service](#tarea-31-documentation-service)
- [3.2 Preview Service](#tarea-32-preview-service)
- [3.3 Pause/Resume Functionality](#tarea-33-pauseresume-functionality)

### FASE 4 - OPTIMIZACIONES
- [4.1 Parallel Execution Service](#tarea-41-parallel-execution-service)
- [4.2 Bulk Operations Enhancement](#tarea-42-bulk-operations-enhancement)
- [4.3 Performance Monitoring](#tarea-43-performance-monitoring)

---

## FASE 1 - CRÍTICO PARA DEMOS

### Tarea 1.1: Dependency Graph Service

```
Contexto:
Soy desarrollador de DataMap, una herramienta B2B de migraciones de bases de datos. Necesito implementar un servicio que analice dependencias de Foreign Keys entre tablas para determinar el orden correcto de migración.

Objetivo:
Crear `backend/app/services/dependency_graph_service.py` que construya un grafo de dependencias y determine el orden óptimo de ejecución usando topological sort.

Requisitos técnicos:
1. Construir grafo dirigido de dependencias FK entre tablas
2. Implementar algoritmo de Kahn para topological sort
3. Detectar dependencias circulares (ej: A → B → C → A)
4. Identificar tablas independientes que pueden ejecutarse en paralelo
5. Manejar auto-referencias (ej: Users.manager_id → Users.id)

Input esperado:
- project_id: UUID del proyecto
- origin_adapter: BaseDBAdapter opcional (para obtener metadata de BD conectada)
- Alternativamente: lista de tablas con sus FK desde base de datos local

Output esperado:
```python
{
    'execution_order': ['customers', 'products', 'orders', 'order_items'],
    'circular_dependencies': [('table_a', 'table_b', 'table_c')],  # Si hay ciclos
    'independent_tables': [['customers', 'products'], ['categories']],  # Paralelizables
    'dependency_levels': {
        1: ['customers', 'products'],
        2: ['orders'],
        3: ['order_items']
    },
    'graph_visualization': {
        'nodes': [...],
        'edges': [('parent', 'child'), ...]
    }
}
```

Casos de prueba requeridos:
1. Cadena simple: A → B → C
2. Patrón diamante: A → B/C → D
3. Dependencia circular: A → B → C → A
4. Auto-referencia: Users(manager_id) → Users(id)
5. Sin dependencias: Todas las tablas independientes
6. Grafo complejo con 10+ tablas y múltiples niveles

Estructura del código:
```python
class DependencyGraphService:
    def __init__(self):
        pass

    def build_dependency_graph(
        self,
        db,
        project_id: str,
        origin_adapter: Optional[BaseDBAdapter] = None
    ) -> Dict[str, Any]:
        """
        Construye grafo de dependencias y determina orden de ejecución
        """
        pass

    def _get_foreign_keys(self, db, project_id, origin_adapter) -> List[Tuple]:
        """Obtiene lista de (tabla_hijo, tabla_padre) de FKs"""
        pass

    def _topological_sort(self, graph: Dict) -> List[str]:
        """Algoritmo de Kahn para ordenamiento topológico"""
        pass

    def _detect_circular_dependencies(self, graph: Dict) -> List[Tuple]:
        """Detecta ciclos usando DFS"""
        pass

    def _identify_independent_tables(self, graph: Dict) -> List[List[str]]:
        """Identifica tablas sin dependencias entre sí"""
        pass
```

Dependencias necesarias:
- networkx==3.2.1 (para manipulación de grafos)

Archivos relacionados:
- Lectura: `backend/app/utils/db_adapters/base_adapter.py` (para entender interface)
- Lectura: `backend/docs/legacy_sql/schema.sql` (ver estructura de tablas/constraints)

Test file a crear:
`backend/test/unit/services/test_dependency_graph_service.py`

Por favor implementa este servicio siguiendo las mejores prácticas de Python, con:
- Type hints completos
- Docstrings detallados
- Manejo de errores apropiado
- Logging para debugging
- Tests unitarios completos
```

---

### Tarea 1.2: Enhanced Migration Script Service

```
Contexto:
Soy desarrollador de DataMap. Tengo un servicio existente que genera scripts SQL básicos (INSERT INTO ... SELECT). Necesito mejorarlo para soportar transacciones, manejo de constraints, transformaciones y batching.

Archivo a modificar:
`backend/app/services/migration_script_service.py`

Estado actual:
- Genera INSERT INTO ... SELECT básicos
- Resuelve hashes SHA-256 de modo connector
- No tiene transacciones
- No maneja constraints
- No aplica transformaciones
- No hace batching

Mejoras requeridas:

1. **Transacciones por dialecto**
Agregar método:
```python
def _generate_transaction_wrapper(self, dialect: str) -> Tuple[str, str]:
    """
    Retorna (begin_statement, commit_statement)

    PostgreSQL: ('BEGIN;', 'COMMIT;')
    MySQL: ('START TRANSACTION;', 'COMMIT;')
    SQL Server: ('BEGIN TRANSACTION;', 'COMMIT TRANSACTION;')
    Oracle: ('BEGIN', 'COMMIT;')
    """
```

2. **Manejo de constraints**
Agregar métodos:
```python
def _generate_constraint_disabling(self, tables: List[str], dialect: str) -> str:
    """
    PostgreSQL: ALTER TABLE {table} DISABLE TRIGGER ALL;
    MySQL: SET FOREIGN_KEY_CHECKS=0;
    SQL Server: ALTER TABLE {table} NOCHECK CONSTRAINT ALL;
    Oracle: ALTER TABLE {table} DISABLE ALL TRIGGERS;
    """

def _generate_constraint_enabling(self, tables: List[str], dialect: str) -> str:
    """Inverso del anterior"""
```

3. **Aplicar transformaciones**
Agregar método:
```python
def _apply_transformation(
    self,
    column_name: str,
    transformation_logic: Optional[str],
    origin_type: str,
    dest_type: str,
    dialect: str
) -> str:
    """
    Si transformation_logic existe (campo transformation_logic_encrypted del mapping):
        Reemplazar {column} por column_name en la expresión
        Ej: "UPPER(TRIM({column}))" → "UPPER(TRIM(email))"

    Si no existe pero los tipos son incompatibles:
        Generar conversión automática
        VARCHAR → INTEGER: CAST(column_name AS INTEGER)
        DATE → TIMESTAMP: column_name::TIMESTAMP (PostgreSQL)

    Retornar: expresión SQL aplicable en SELECT
    """
```

4. **Batch processing**
Agregar método:
```python
def _generate_batched_insert(
    self,
    table_name: str,
    columns: List[str],
    select_clause: str,
    total_rows: int,
    batch_size: int,
    dialect: str
) -> str:
    """
    Para PostgreSQL/MySQL/SQL Server, genera:

    DO $$
    DECLARE
        batch_size INT := {batch_size};
        offset_val INT := 0;
        total_rows INT := {total_rows};
    BEGIN
        WHILE offset_val < total_rows LOOP
            INSERT INTO {table_name} ({columns})
            SELECT {select_clause}
            LIMIT batch_size OFFSET offset_val;

            offset_val := offset_val + batch_size;
            RAISE NOTICE 'Progress: % / %', offset_val, total_rows;
        END LOOP;
    END $$;
    """
```

5. **Integrar con Dependency Graph**
Modificar método principal `generate_insert_script()` para:
- Aceptar parámetro opcional `dependency_order: List[str]`
- Si se proporciona, generar INSERTs en ese orden
- Si no, usar orden actual

Estructura del script generado (ejemplo):
```sql
-- ========================================
-- MIGRATION SCRIPT
-- Generated: 2025-01-16 14:30:00 UTC
-- Project: Customer DB Migration
-- Total mappings: 15
-- Estimated rows: 35,000
-- Estimated time: 5 minutes
-- ========================================

-- SECTION 1: Transaction Start
BEGIN;

-- SECTION 2: Disable Constraints
SET FOREIGN_KEY_CHECKS=0;
ALTER TABLE orders DISABLE TRIGGER ALL;

-- SECTION 3: Data Migration (in dependency order)
-- Table 1/5: customers (no dependencies)
INSERT INTO customers_new (id, name, email)
SELECT
    id,
    UPPER(TRIM(name)),  -- transformation applied
    LOWER(email)        -- transformation applied
FROM customers;
-- Rows: 10,000

-- Table 2/5: products (no dependencies)
INSERT INTO products_new (id, product_name, price)
SELECT id, product_name, price FROM products;
-- Rows: 5,000

-- Table 3/5: orders (depends on customers)
-- Large table - using batching
DO $$
DECLARE
    batch_size INT := 10000;
    offset_val INT := 0;
    total_rows INT := 20000;
BEGIN
    WHILE offset_val < total_rows LOOP
        INSERT INTO orders_new (id, customer_id, amount)
        SELECT id, customer_id, amount FROM orders
        LIMIT batch_size OFFSET offset_val;
        offset_val := offset_val + batch_size;
    END LOOP;
END $$;

-- SECTION 4: Enable Constraints
SET FOREIGN_KEY_CHECKS=1;
ALTER TABLE orders ENABLE TRIGGER ALL;

-- SECTION 5: Validation
SELECT 'customers_new', COUNT(*) FROM customers_new;  -- Expected: 10000
SELECT 'products_new', COUNT(*) FROM products_new;    -- Expected: 5000
SELECT 'orders_new', COUNT(*) FROM orders_new;        -- Expected: 20000

-- SECTION 6: Transaction Commit
COMMIT;

-- ========================================
-- MIGRATION COMPLETE
-- Total rows migrated: 35,000
-- ========================================
```

Parámetros adicionales al método principal:
```python
def generate_insert_script(
    self,
    mappings: List[Dict],
    origin_adapter: Optional[BaseDBAdapter] = None,
    destination_adapter: Optional[BaseDBAdapter] = None,
    dependency_order: Optional[List[str]] = None,  # NUEVO
    batch_size: int = 10000,  # NUEVO
    include_constraints: bool = True,  # NUEVO
    include_validation: bool = True,  # NUEVO
    dialect: str = 'postgresql'  # NUEVO
) -> str:
```

Archivos a leer antes de empezar:
- `backend/app/services/migration_script_service.py` (código actual completo)
- `backend/app/crud/mappings_crud.py` (ver campo transformation_logic_encrypted líneas 234, 350)
- `backend/utilities/migrations/validators.py` (matriz de compatibilidad de tipos)

Tests a actualizar:
- `backend/test/unit/services/test_migration_script_service.py`
- Agregar tests para transacciones, constraints, transformaciones, batching

Por favor implementa estas mejoras manteniendo compatibilidad con el código existente.
```

---

### Tarea 1.3: Execution Service

```
Contexto:
Soy desarrollador de DataMap. Los scripts SQL se generan pero nunca se ejecutan. Necesito un servicio que ejecute los scripts contra la base de datos destino con manejo de transacciones, rollback automático y tracking de progreso.

Archivo a crear:
`backend/app/services/execution_service.py`

Responsabilidades:
1. Ejecutar scripts SQL contra base de datos destino
2. Manejar transacciones (COMMIT en éxito, ROLLBACK en error)
3. Crear backups automáticos antes de ejecutar
4. Tracking de progreso en tiempo real
5. Modo dry-run (ejecuta pero hace ROLLBACK al final)
6. Logging detallado de cada paso

Estructura del servicio:
```python
import logging
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.utils.db_adapters.base_adapter import BaseDBAdapter
from backend.utilities.migrations.validators import BackupManager

logger = logging.getLogger(__name__)


class ExecutionServiceError(Exception):
    """Base exception for ExecutionService"""
    pass


class ExecutionService:
    def __init__(self):
        self.backup_manager = BackupManager()

    def execute_migration(
        self,
        db: Session,
        project_id: str,
        script: str,
        dest_adapter: BaseDBAdapter,
        dry_run: bool = False,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta script de migración contra BD destino

        Flujo:
        1. Crear registro en migration_executions (status='running')
        2. Crear backup automático usando BackupManager
        3. Ejecutar script línea por línea con dest_adapter
        4. Si dry_run=True: ROLLBACK al final
        5. Si error durante ejecución: ROLLBACK + marcar status='failed'
        6. Si éxito: COMMIT + marcar status='success'
        7. Actualizar execution_log con cada paso

        Returns:
        {
            'execution_id': uuid,
            'status': 'success' | 'failed' | 'dry_run_complete',
            'rows_affected': 35000,
            'duration_seconds': 42.5,
            'backup_id': 'backup_20250116_143000',
            'errors': [],
            'execution_log': [
                {'step': 1, 'table': 'customers', 'rows': 10000, 'duration': 2.5},
                {'step': 2, 'table': 'orders', 'rows': 25000, 'duration': 5.2}
            ]
        }
        """
        execution_id = self._create_execution_record(db, project_id, script, user_id)

        try:
            # Crear backup
            backup_id = self._create_backup(db, project_id)

            # Ejecutar script
            result = self._execute_script(
                dest_adapter,
                script,
                dry_run=dry_run
            )

            # Actualizar registro
            self._update_execution_record(
                db,
                execution_id,
                status='dry_run_complete' if dry_run else 'success',
                rows_migrated=result['rows_affected'],
                backup_id=backup_id,
                execution_log=result['log']
            )

            return {
                'execution_id': execution_id,
                'status': 'dry_run_complete' if dry_run else 'success',
                'rows_affected': result['rows_affected'],
                'duration_seconds': result['duration'],
                'backup_id': backup_id,
                'errors': [],
                'execution_log': result['log']
            }

        except Exception as e:
            logger.error(f"Migration execution failed: {str(e)}", exc_info=True)

            # Rollback + marcar como failed
            self._update_execution_record(
                db,
                execution_id,
                status='failed',
                error_message=str(e)
            )

            return {
                'execution_id': execution_id,
                'status': 'failed',
                'errors': [str(e)],
                'duration_seconds': 0
            }

    def _create_execution_record(
        self,
        db: Session,
        project_id: str,
        script: str,
        user_id: Optional[str]
    ) -> str:
        """
        Crea registro en tabla migration_executions
        Retorna execution_id (UUID)
        """
        pass

    def _create_backup(self, db: Session, project_id: str) -> str:
        """
        Usa BackupManager existente para crear backup
        Retorna backup_id
        """
        pass

    def _execute_script(
        self,
        adapter: BaseDBAdapter,
        script: str,
        dry_run: bool
    ) -> Dict[str, Any]:
        """
        Ejecuta script SQL contra BD usando adapter

        Parsea el script para identificar:
        - BEGIN/COMMIT statements
        - INSERT statements (contar filas afectadas)
        - Comentarios con información de tablas

        Retorna:
        {
            'rows_affected': 35000,
            'duration': 42.5,
            'log': [
                {'step': 1, 'sql': 'INSERT ...', 'rows': 10000, 'duration': 2.5},
                ...
            ]
        }
        """
        pass

    def _update_execution_record(
        self,
        db: Session,
        execution_id: str,
        status: str,
        rows_migrated: int = 0,
        backup_id: Optional[str] = None,
        execution_log: Optional[list] = None,
        error_message: Optional[str] = None
    ):
        """
        Actualiza registro en migration_executions
        """
        pass

    def get_execution_status(
        self,
        db: Session,
        execution_id: str
    ) -> Dict[str, Any]:
        """
        Consulta estado de una ejecución

        Returns:
        {
            'execution_id': uuid,
            'status': 'running' | 'success' | 'failed',
            'progress_percent': 60,
            'rows_migrated': 21000,
            'started_at': '2025-01-16T14:30:00Z',
            'completed_at': None,
            'current_step': 'Migrating table: orders'
        }
        """
        pass
```

Dependencias:
- `backend.utilities.migrations.validators.BackupManager` (ya existe)
- Tabla `migration_executions` (debe existir, ver tarea 1.6)

Archivos relacionados:
- Lectura: `backend/utilities/migrations/validators.py` (BackupManager)
- Lectura: `backend/app/utils/db_adapters/base_adapter.py` (para ejecutar SQL)

Test file a crear:
`backend/test/unit/services/test_execution_service.py`

Tests requeridos:
1. test_execute_migration_success
2. test_execute_migration_with_error_rollback
3. test_dry_run_mode
4. test_backup_creation
5. test_execution_status_tracking

Por favor implementa este servicio con manejo robusto de errores y logging detallado.
```

---

### Tarea 1.4: Migration API Endpoints

```
Contexto:
Soy desarrollador de DataMap. Necesito crear endpoints REST para generación y ejecución de scripts de migración.

Archivo a crear:
`backend/app/routers/migration.py`

Endpoints requeridos:

1. **Generar Script Mejorado**
```python
@router.post("/api/projects/{project_id}/migration/generate-script")
async def generate_migration_script(
    project_id: str,
    options: MigrationScriptOptions,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Request body (MigrationScriptOptions):
    {
        "batch_size": 10000,
        "include_constraints": true,
        "include_validation": true,
        "dialect": "postgresql"
    }

    Response:
    {
        "script_id": "uuid",
        "script": "BEGIN; ...",
        "estimated_duration_seconds": 2700,
        "estimated_rows": 35000,
        "dependency_order": ["customers", "orders", "order_items"],
        "created_at": "2025-01-16T14:30:00Z"
    }

    Lógica:
    1. Validar project ownership
    2. Obtener mappings del proyecto
    3. Llamar DependencyGraphService para orden de ejecución
    4. Llamar MigrationScriptService (enhanced) para generar script
    5. Guardar script en tabla migration_scripts con versioning
    6. Retornar script + metadata
    """
```

2. **Ejecutar Migración**
```python
@router.post("/api/projects/{project_id}/migration/execute")
async def execute_migration(
    project_id: str,
    request: ExecutionRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Request body (ExecutionRequest):
    {
        "script_id": "uuid",  # Opcional, si no se proporciona genera nuevo
        "dry_run": false,
        "dest_connection_session_id": "uuid"  # Session de conexión destino
    }

    Response:
    {
        "execution_id": "uuid",
        "status": "running",
        "message": "Migration started successfully"
    }

    Lógica:
    1. Validar project ownership
    2. Si script_id proporcionado: cargar de migration_scripts
       Si no: generar nuevo script
    3. Obtener dest_adapter de session
    4. Llamar ExecutionService.execute_migration()
    5. Retornar execution_id para polling
    """
```

3. **Consultar Estado de Ejecución**
```python
@router.get("/api/projects/{project_id}/migration/executions/{execution_id}")
async def get_execution_status(
    project_id: str,
    execution_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Response:
    {
        "execution_id": "uuid",
        "status": "running" | "success" | "failed" | "dry_run_complete",
        "progress_percent": 60,
        "rows_migrated": 21000,
        "estimated_remaining_seconds": 30,
        "started_at": "2025-01-16T14:30:00Z",
        "completed_at": null,
        "current_step": "Migrating table: orders (batch 2/3)",
        "execution_log": [
            {"step": 1, "table": "customers", "rows": 10000, "status": "completed"},
            {"step": 2, "table": "orders", "rows": 15000, "status": "in_progress"}
        ],
        "errors": []
    }

    Lógica:
    1. Validar ownership
    2. Llamar ExecutionService.get_execution_status()
    3. Calcular progress_percent basado en execution_log
    4. Estimar tiempo restante
    """
```

4. **Listar Ejecuciones**
```python
@router.get("/api/projects/{project_id}/migration/executions")
async def list_executions(
    project_id: str,
    status: Optional[str] = None,  # Filter por status
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Response:
    {
        "executions": [
            {
                "id": "uuid",
                "started_at": "2025-01-16T14:30:00Z",
                "completed_at": "2025-01-16T14:35:00Z",
                "status": "success",
                "rows_migrated": 35000,
                "duration_seconds": 300
            },
            ...
        ],
        "total": 25,
        "limit": 10,
        "offset": 0
    }
    """
```

5. **Obtener Grafo de Dependencias**
```python
@router.get("/api/projects/{project_id}/migration/dependency-graph")
async def get_dependency_graph(
    project_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Response:
    {
        "execution_order": ["customers", "products", "orders"],
        "circular_dependencies": [],
        "independent_tables": [["customers", "products"]],
        "graph_visualization": {
            "nodes": [...],
            "edges": [...]
        }
    }

    Útil para UI: mostrar grafo visual antes de ejecutar
    """
```

Modelos Pydantic a crear:
```python
from pydantic import BaseModel
from typing import Optional, List

class MigrationScriptOptions(BaseModel):
    batch_size: int = 10000
    include_constraints: bool = True
    include_validation: bool = True
    dialect: str = 'postgresql'

class ExecutionRequest(BaseModel):
    script_id: Optional[str] = None
    dry_run: bool = False
    dest_connection_session_id: str
```

Imports necesarios:
```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any

from app.database.database import get_db
from app.routers.dependencies import get_current_user
from app.services.dependency_graph_service import DependencyGraphService
from app.services.migration_script_service import MigrationScriptService
from app.services.execution_service import ExecutionService
from app.services.db_connection_service import DBConnectionService
```

Archivos relacionados:
- Lectura: `backend/app/routers/mappings.py` (para ver patrón de endpoints existentes)
- Lectura: `backend/app/routers/db_connections.py` (para ver manejo de sesiones)

Test file a crear:
`backend/test/integration/test_migration_api.py`

Tests requeridos:
1. test_generate_script_success
2. test_generate_script_unauthorized
3. test_execute_migration_dry_run
4. test_execute_migration_real
5. test_get_execution_status
6. test_list_executions
7. test_dependency_graph

Por favor implementa estos endpoints con validación apropiada y manejo de errores.
```

---

### Tarea 1.5: Connector Polish

```
Contexto:
Soy desarrollador de DataMap. Los conectores de base de datos funcionan pero tienen problemas de UX: errores genéricos (todos devuelven 500), falta manejo de timeouts, y algunos métodos faltantes.

Archivos a modificar:

1. **Backend Router - Error Handling**
Archivo: `backend/app/routers/db_connections.py`

Líneas a modificar: 348-352, 385-389, 423-427, 468-472

Cambio requerido:
```python
# ANTES (genérico):
except Exception as e:
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Error: {str(e)}"
    )

# DESPUÉS (específico):
except DBAuthenticationError as e:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid database credentials. Please check username and password."
    )
except DBTimeoutError as e:
    raise HTTPException(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        detail=f"Connection timeout after {e.timeout}s. Database server may be unreachable."
    )
except DBPermissionError as e:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Permission denied: {e.message}. Grant required permissions to database user."
    )
except DBConnectionError as e:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Cannot connect to database: {e.message}. Check host and port."
    )
except Exception as e:
    logger.error(f"Unexpected database error: {str(e)}", exc_info=True)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An unexpected error occurred. Please contact support."
    )
```

Agregar imports:
```python
from app.utils.db_adapters.exceptions import (
    DBAuthenticationError,
    DBTimeoutError,
    DBPermissionError,
    DBConnectionError
)
```

2. **Database Adapters - Specific Error Handling**
Archivos:
- `backend/app/utils/db_adapters/postgres_adapter.py`
- `backend/app/utils/db_adapters/mysql_adapter.py`
- `backend/app/utils/db_adapters/oracle_adapter.py`
- `backend/app/utils/db_adapters/sqlserver_adapter.py`

En cada adaptador, modificar método `connect()`:

PostgreSQL ejemplo:
```python
def connect(self):
    try:
        self.connection = psycopg2.connect(**self.connection_config)
        logger.info("PostgreSQL connection established")
    except psycopg2.errors.InsufficientPrivilege as e:
        raise DBPermissionError(
            f"User lacks required permissions. Grant with: "
            f"GRANT SELECT ON ALL TABLES IN SCHEMA information_schema TO {self.user}",
            original_error=e
        )
    except psycopg2.OperationalError as e:
        error_msg = str(e).lower()
        if 'timeout' in error_msg:
            raise DBTimeoutError(
                f"Connection timeout after {self.timeout}s",
                timeout=self.timeout,
                original_error=e
            )
        elif 'authentication' in error_msg or 'password' in error_msg:
            raise DBAuthenticationError(
                "Invalid username or password",
                original_error=e
            )
        elif 'could not connect' in error_msg or 'refused' in error_msg:
            raise DBConnectionError(
                f"Cannot reach database server at {self.host}:{self.port}",
                original_error=e
            )
        else:
            raise DBConnectionError(str(e), original_error=e)
    except Exception as e:
        logger.error(f"Unexpected PostgreSQL connection error: {str(e)}")
        raise DBConnectionError(f"Unexpected error: {str(e)}", original_error=e)
```

Crear archivo de excepciones si no existe:
`backend/app/utils/db_adapters/exceptions.py`
```python
class DBAdapterError(Exception):
    """Base exception for database adapters"""
    def __init__(self, message: str, original_error: Exception = None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)

class DBAuthenticationError(DBAdapterError):
    """Authentication failed (invalid credentials)"""
    pass

class DBTimeoutError(DBAdapterError):
    """Connection or query timeout"""
    def __init__(self, message: str, timeout: int = None, original_error: Exception = None):
        self.timeout = timeout
        super().__init__(message, original_error)

class DBPermissionError(DBAdapterError):
    """Insufficient permissions"""
    pass

class DBConnectionError(DBAdapterError):
    """Cannot connect to database server"""
    pass
```

3. **Frontend - Timeout Handling**
Archivo: `frontend/src/services/db_connection.service.ts`

Modificar método `testConnection` (líneas 22-43):
```typescript
async testConnection(config: DBConnectionConfig): Promise<DBConnectionTestResult> {
    try {
        const response = await api.post('/db-connections/test', config, {
            timeout: 30000  // 30 seconds timeout
        });

        return {
            success: true,
            dialect: config.dialect,
            message: 'Connection successful'
        };
    } catch (error: any) {
        // Network timeout
        if (error.code === 'ECONNABORTED') {
            return {
                success: false,
                dialect: config.dialect,
                error_type: 'timeout',
                error_message: 'Connection timeout - database server not responding after 30 seconds'
            };
        }

        // HTTP status codes
        if (error.response) {
            const status = error.response.status;
            const detail = error.response.data?.detail || 'Unknown error';

            return {
                success: false,
                dialect: config.dialect,
                error_type: this._mapStatusToErrorType(status),
                error_message: detail
            };
        }

        // Network error (server unreachable)
        return {
            success: false,
            dialect: config.dialect,
            error_type: 'connection_error',
            error_message: 'Cannot reach DataMap server. Check your network connection.'
        };
    }
}

private _mapStatusToErrorType(status: number): string {
    switch (status) {
        case 401: return 'authentication_error';
        case 403: return 'permission_error';
        case 504: return 'timeout';
        case 503: return 'connection_error';
        default: return 'unknown_error';
    }
}
```

Agregar retry logic con exponential backoff:
```typescript
async testConnectionWithRetry(
    config: DBConnectionConfig,
    maxRetries: number = 3
): Promise<DBConnectionTestResult> {
    let lastError: any;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
            return await this.testConnection(config);
        } catch (error: any) {
            lastError = error;

            // No retry on authentication errors
            if (error.response?.status === 401 || error.response?.status === 403) {
                throw error;
            }

            // Exponential backoff: 1s, 2s, 4s
            if (attempt < maxRetries) {
                const delay = Math.pow(2, attempt - 1) * 1000;
                await new Promise(resolve => setTimeout(resolve, delay));
            }
        }
    }

    throw lastError;
}
```

4. **Verificar get_full_schema_metadata()**
Revisar que todos los adaptadores implementen correctamente este método.
Si falta, puede estar en la clase base `BaseDBAdapter`.

Archivos relacionados:
- Lectura: `backend/app/utils/db_adapters/base_adapter.py` (líneas 277-329)

Checklist de verificación:
- [ ] PostgreSQLAdapter tiene get_full_schema_metadata()
- [ ] MySQLAdapter tiene get_full_schema_metadata()
- [ ] SQLServerAdapter tiene get_full_schema_metadata()
- [ ] OracleAdapter tiene get_full_schema_metadata()

Si falta en alguno, heredar de base o implementar específicamente.

Por favor implementa estos cambios para mejorar significativamente la experiencia de usuario al conectar bases de datos.
```

---

### Tarea 1.6: Database Migration Schema

```
Contexto:
Soy desarrollador de DataMap. Necesito crear las nuevas tablas de base de datos para soportar ejecución de migraciones, con tracking de progreso y logs detallados.

Archivo a crear:
`backend/docs/legacy_sql/migrations/006_migration_execution_tables.sql`

Tablas a crear:

1. **migration_executions**
```sql
-- Tabla principal de ejecuciones de migración
CREATE TABLE migration_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    status VARCHAR(20) NOT NULL CHECK (status IN (
        'pending',
        'running',
        'success',
        'failed',
        'rolled_back',
        'dry_run_complete'
    )),
    rows_migrated INTEGER DEFAULT 0,
    script_hash VARCHAR(64),  -- SHA-256 del script ejecutado (para idempotencia)
    backup_id VARCHAR(255),   -- Referencia al backup creado antes de ejecutar
    error_message TEXT,
    execution_log JSONB,      -- Log detallado: [{step, table, rows, duration, status}, ...]
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Índices para performance
CREATE INDEX idx_migration_executions_project ON migration_executions(project_id);
CREATE INDEX idx_migration_executions_status ON migration_executions(status);
CREATE INDEX idx_migration_executions_created_by ON migration_executions(created_by);
CREATE INDEX idx_migration_executions_created_at ON migration_executions(created_at DESC);

-- Comentarios
COMMENT ON TABLE migration_executions IS 'Registro de ejecuciones de scripts de migración';
COMMENT ON COLUMN migration_executions.script_hash IS 'SHA-256 del script ejecutado para detectar duplicados';
COMMENT ON COLUMN migration_executions.execution_log IS 'Array JSON con log detallado de cada paso: [{"step": 1, "table": "customers", "rows": 10000, "duration": 2.5, "status": "completed"}]';
```

2. **migration_scripts**
```sql
-- Tabla de scripts generados con versionado
CREATE TABLE migration_scripts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,  -- Auto-incrementa por proyecto
    script_content TEXT NOT NULL,
    script_hash VARCHAR(64) NOT NULL UNIQUE,  -- SHA-256 para detectar duplicados
    generation_options JSONB,  -- {batch_size, include_constraints, dialect, ...}
    dependency_graph JSONB,    -- Grafo generado para documentación
    estimated_duration_seconds FLOAT,
    estimated_rows INTEGER,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(project_id, version)  -- Versionado único por proyecto
);

-- Índices
CREATE INDEX idx_migration_scripts_project ON migration_scripts(project_id);
CREATE INDEX idx_migration_scripts_hash ON migration_scripts(script_hash);
CREATE INDEX idx_migration_scripts_version ON migration_scripts(project_id, version DESC);

-- Comentarios
COMMENT ON TABLE migration_scripts IS 'Scripts de migración generados con versionado automático';
COMMENT ON COLUMN migration_scripts.version IS 'Versión auto-incremental por proyecto (1, 2, 3, ...)';
COMMENT ON COLUMN migration_scripts.generation_options IS 'Opciones usadas al generar: {"batch_size": 10000, "include_constraints": true, "dialect": "postgresql"}';
```

3. **Trigger para auto-incrementar version**
```sql
-- Función para auto-incrementar version
CREATE OR REPLACE FUNCTION increment_migration_script_version()
RETURNS TRIGGER AS $$
BEGIN
    -- Si no se proporciona version, calcular la siguiente
    IF NEW.version IS NULL THEN
        SELECT COALESCE(MAX(version), 0) + 1 INTO NEW.version
        FROM migration_scripts
        WHERE project_id = NEW.project_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger
CREATE TRIGGER trigger_increment_migration_script_version
BEFORE INSERT ON migration_scripts
FOR EACH ROW
EXECUTE FUNCTION increment_migration_script_version();

COMMENT ON FUNCTION increment_migration_script_version() IS 'Auto-incrementa version de scripts por proyecto';
```

4. **Trigger para updated_at**
```sql
-- Función para actualizar updated_at
CREATE OR REPLACE FUNCTION update_migration_execution_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger
CREATE TRIGGER trigger_update_migration_execution_timestamp
BEFORE UPDATE ON migration_executions
FOR EACH ROW
EXECUTE FUNCTION update_migration_execution_timestamp();
```

5. **Relación con proyectos**
```sql
-- Agregar columnas a tabla projects para tracking
ALTER TABLE projects
ADD COLUMN IF NOT EXISTS last_migration_execution_id UUID REFERENCES migration_executions(id),
ADD COLUMN IF NOT EXISTS last_migration_status VARCHAR(20),
ADD COLUMN IF NOT EXISTS last_migration_at TIMESTAMP;

CREATE INDEX idx_projects_last_migration ON projects(last_migration_execution_id);

COMMENT ON COLUMN projects.last_migration_execution_id IS 'Última ejecución de migración para este proyecto';
COMMENT ON COLUMN projects.last_migration_status IS 'Estado de la última migración (success, failed, etc)';
COMMENT ON COLUMN projects.last_migration_at IS 'Timestamp de la última migración';
```

Script de Python para ejecutar la migración:
`backend/utilities/migrations/run_migration_006.py`
```python
#!/usr/bin/env python3
"""
Migración 006: Agregar tablas migration_executions y migration_scripts

Fecha: 2025-01-16
Descripción: Tablas para tracking de ejecuciones de migración con logging detallado
"""

import os
import sys
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

# Agregar backend al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

load_dotenv()


def run_migration():
    """Ejecuta la migración 006"""

    # Conexión a BD
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'datamap'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD')
    )

    try:
        cursor = conn.cursor()

        # Leer archivo SQL
        sql_file = Path(__file__).parent / '006_migration_execution_tables.sql'
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql = f.read()

        print("Ejecutando migración 006...")
        cursor.execute(sql)
        conn.commit()
        print("✓ Migración 006 completada exitosamente")

        # Verificar tablas creadas
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('migration_executions', 'migration_scripts')
            ORDER BY table_name;
        """)

        tables = cursor.fetchall()
        print(f"\nTablas creadas: {[t[0] for t in tables]}")

        cursor.close()

    except Exception as e:
        print(f"✗ Error ejecutando migración: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == '__main__':
    run_migration()
```

Hacer ejecutable:
```bash
chmod +x backend/utilities/migrations/run_migration_006.py
```

Documentación:
`backend/utilities/migrations/README_MIGRATION_006.md`
```markdown
# Migración 006: Tablas de Ejecución de Migración

## Propósito
Agregar infraestructura para ejecutar y trackear migraciones de bases de datos.

## Tablas Creadas
1. **migration_executions**: Registro de ejecuciones
2. **migration_scripts**: Scripts generados con versionado

## Cómo Ejecutar
```bash
python backend/utilities/migrations/run_migration_006.py
```

## Cómo Revertir (Rollback)
```sql
DROP TABLE IF EXISTS migration_executions CASCADE;
DROP TABLE IF EXISTS migration_scripts CASCADE;
DROP FUNCTION IF EXISTS increment_migration_script_version() CASCADE;
DROP FUNCTION IF EXISTS update_migration_execution_timestamp() CASCADE;

ALTER TABLE projects
DROP COLUMN IF EXISTS last_migration_execution_id,
DROP COLUMN IF EXISTS last_migration_status,
DROP COLUMN IF EXISTS last_migration_at;
```

## Verificación
```sql
-- Verificar tablas
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name LIKE 'migration_%';

-- Verificar triggers
SELECT trigger_name, event_object_table
FROM information_schema.triggers
WHERE trigger_schema = 'public'
AND trigger_name LIKE '%migration%';
```
```

Por favor crea estos archivos con las mejores prácticas de PostgreSQL.
```

---

## FASE 2 - VALIDACIÓN Y ROBUSTEZ

### Tarea 2.1: Validation Service

```
Contexto:
Soy desarrollador de DataMap. Necesito un servicio que valide migraciones antes (pre-flight) y después (post-migration) de ejecutarlas, detectando problemas de integridad, tipos incompatibles y calidad de datos.

Archivo a crear:
`backend/app/services/validation_service.py`

[CONTINÚA EN SIGUIENTE MENSAJE PARA NO EXCEDER LÍMITE...]
```

---

Por favor confirma si quieres que continúe con las tareas de Fase 2, 3 y 4, o si prefieres que primero revises las tareas de Fase 1.
