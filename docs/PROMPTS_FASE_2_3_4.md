# Prompts Tareas Individuales - Fases 2, 3 y 4

> Documento histórico: el SQL citado está archivado en `backend/docs/legacy_sql/`; el esquema sale de Alembic.

**Continuación de**: `PROMPTS_TAREAS_INDIVIDUALES.md`

---

## FASE 2 - VALIDACIÓN Y ROBUSTEZ

### Tarea 2.1: Validation Service

```
Contexto:
Soy desarrollador de DataMap. Necesito un servicio que valide migraciones antes (pre-flight) y después (post-migration), detectando problemas de integridad referencial, tipos incompatibles y calidad de datos.

Archivo a crear:
`backend/app/services/validation_service.py`

Infraestructura existente a aprovechar:
- `backend/utilities/migrations/validators.py` - Tiene TYPE_COMPATIBILITY_MATRIX con 60+ reglas
- `backend/app/services/type_compatibility_service.py` - Wrapper de servicio existente

Responsabilidades:

1. **Pre-Migration Validation**
```python
def pre_migration_validation(
    self,
    db: Session,
    project_id: str,
    origin_adapter: Optional[BaseDBAdapter] = None
) -> ValidationReport:
    """
    Ejecuta 4 categorías de validaciones:

    1. Referential Integrity
       - Todos los FK apuntan a registros existentes en origen
       - No hay registros huérfanos
       - Sugerencia de orden de migración si hay problemas

    2. Type Compatibility
       - Usar TYPE_COMPATIBILITY_MATRIX de validators.py
       - Identificar conversiones 'danger' (ej: TEXT → INTEGER)
       - Marcar conversiones 'warning' (ej: VARCHAR(255) → VARCHAR(100))

    3. Data Quality
       - Detectar NULLs en campos que mapean a NOT NULL destino
       - Detectar overflow numérico (BIGINT → INTEGER con valores >2.1B)
       - Detectar truncado de strings (VARCHAR(255) → VARCHAR(100) con datos >100)
       - Detectar duplicados en campos que mapean a UNIQUE destino

    4. Schema Consistency
       - Todas las columnas requeridas (NOT NULL) en destino tienen mapping
       - No hay mappings a columnas inexistentes
       - Tipos de datos compatibles

    Returns: ValidationReport con estructura:
    {
        'report_id': uuid,
        'status': 'pass' | 'warning' | 'fail',
        'checks_passed': 15,
        'checks_warning': 3,
        'checks_failed': 0,
        'can_proceed': True,  # False si hay errores críticos
        'issues': [
            {
                'type': 'data_quality',
                'severity': 'warning',  # warning | error
                'table': 'users',
                'column': 'description',
                'message': '5 rows exceed VARCHAR(100) limit',
                'affected_rows': [1, 2, 3, 4, 5],
                'recommendation': 'Increase dest column to VARCHAR(255) or truncate data'
            },
            {
                'type': 'referential_integrity',
                'severity': 'error',
                'table': 'orders',
                'message': '12 orders reference non-existent customer_id',
                'affected_rows': [101, 102, ...],
                'recommendation': 'Migrate customers table first or clean orphaned records'
            }
        ],
        'recommendations': [
            'Migrate customers before orders to avoid FK violations',
            'Consider increasing destination.users.description to VARCHAR(255)'
        ]
    }
    """
```

2. **Post-Migration Validation**
```python
def post_migration_validation(
    self,
    db: Session,
    execution_id: str,
    origin_adapter: BaseDBAdapter,
    dest_adapter: BaseDBAdapter
) -> ValidationReport:
    """
    Verifica que la migración fue exitosa:

    1. Row Count Match
       - SELECT COUNT(*) de cada tabla en origen vs destino
       - Marcar discrepancias como error

    2. Sample Data Comparison
       - Seleccionar 100 filas aleatorias de cada tabla
       - Comparar valores columna por columna
       - Reportar % de coincidencia

    3. Constraint Verification
       - Verificar que todos los PKs están activos
       - Verificar que todos los FKs están activos y sin violaciones
       - Verificar UNIQUE constraints sin duplicados
       - Verificar CHECK constraints válidos

    4. Data Integrity Checks
       - No hay PKs duplicados en destino
       - No hay FKs huérfanos
       - SUM/AVG de columnas numéricas coincide entre origen y destino
       - No hay NULLs inesperados

    Returns: ValidationReport similar a pre-migration
    """
```

Estructura del servicio:
```python
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from sqlalchemy.orm import Session

from app.utils.db_adapters.base_adapter import BaseDBAdapter
from backend.utilities.migrations.validators import TYPE_COMPATIBILITY_MATRIX

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    type: str  # referential_integrity, type_compatibility, data_quality, schema_consistency
    severity: str  # warning, error
    table: str
    column: Optional[str] = None
    message: str = ""
    affected_rows: List[int] = None
    recommendation: str = ""


@dataclass
class ValidationReport:
    report_id: str
    status: str  # pass, warning, fail
    checks_passed: int
    checks_warning: int
    checks_failed: int
    can_proceed: bool
    issues: List[ValidationIssue]
    recommendations: List[str]


class ValidationService:
    def __init__(self):
        self.type_matrix = TYPE_COMPATIBILITY_MATRIX

    def pre_migration_validation(
        self,
        db: Session,
        project_id: str,
        origin_adapter: Optional[BaseDBAdapter] = None
    ) -> ValidationReport:
        """Implementar según spec arriba"""
        pass

    def post_migration_validation(
        self,
        db: Session,
        execution_id: str,
        origin_adapter: BaseDBAdapter,
        dest_adapter: BaseDBAdapter
    ) -> ValidationReport:
        """Implementar según spec arriba"""
        pass

    def _check_referential_integrity(
        self,
        db: Session,
        project_id: str,
        origin_adapter: Optional[BaseDBAdapter]
    ) -> List[ValidationIssue]:
        """
        Verifica que todos los FK apuntan a registros existentes
        """
        pass

    def _check_type_compatibility(
        self,
        db: Session,
        project_id: str
    ) -> List[ValidationIssue]:
        """
        Usa TYPE_COMPATIBILITY_MATRIX para verificar conversiones
        """
        pass

    def _check_data_quality(
        self,
        db: Session,
        project_id: str,
        origin_adapter: Optional[BaseDBAdapter]
    ) -> List[ValidationIssue]:
        """
        Escanea datos reales en origen para detectar problemas
        """
        pass

    def _check_schema_consistency(
        self,
        db: Session,
        project_id: str
    ) -> List[ValidationIssue]:
        """
        Verifica que mappings son completos y consistentes
        """
        pass

    def _compare_row_counts(
        self,
        origin_adapter: BaseDBAdapter,
        dest_adapter: BaseDBAdapter,
        tables: List[str]
    ) -> List[ValidationIssue]:
        """
        Compara COUNT(*) entre origen y destino
        """
        pass

    def _compare_sample_data(
        self,
        origin_adapter: BaseDBAdapter,
        dest_adapter: BaseDBAdapter,
        table: str,
        sample_size: int = 100
    ) -> Dict[str, Any]:
        """
        Compara sample de filas entre origen y destino
        Returns: {match_percentage: 98.5, mismatches: [...]}
        """
        pass

    def _verify_constraints(
        self,
        dest_adapter: BaseDBAdapter,
        tables: List[str]
    ) -> List[ValidationIssue]:
        """
        Verifica que constraints están activos y sin violaciones
        """
        pass

    def _save_validation_report(
        self,
        db: Session,
        project_id: str,
        execution_id: Optional[str],
        report: ValidationReport,
        report_type: str  # pre_flight o post_migration
    ):
        """
        Guarda reporte en tabla validation_reports
        """
        pass
```

Nueva tabla DB:
`backend/utilities/migrations/007_validation_reports.sql`
```sql
CREATE TABLE validation_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    execution_id UUID REFERENCES migration_executions(id),
    report_type VARCHAR(20) NOT NULL CHECK (report_type IN ('pre_flight', 'post_migration')),
    status VARCHAR(20) NOT NULL CHECK (status IN ('pass', 'warning', 'fail')),
    checks_passed INTEGER DEFAULT 0,
    checks_warning INTEGER DEFAULT 0,
    checks_failed INTEGER DEFAULT 0,
    can_proceed BOOLEAN DEFAULT FALSE,
    issues JSONB,  -- Array de ValidationIssue serializado
    recommendations JSONB,  -- Array de strings
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_validation_reports_project ON validation_reports(project_id);
CREATE INDEX idx_validation_reports_execution ON validation_reports(execution_id);
CREATE INDEX idx_validation_reports_type ON validation_reports(report_type);
```

Test file a crear:
`backend/test/unit/services/test_validation_service.py`

Tests requeridos:
1. test_pre_migration_validation_all_pass
2. test_pre_migration_validation_with_warnings
3. test_pre_migration_validation_with_errors
4. test_referential_integrity_check
5. test_type_compatibility_check
6. test_data_quality_check
7. test_post_migration_row_count_match
8. test_post_migration_sample_comparison

Por favor implementa este servicio con validaciones robustas y mensajes de error útiles para el usuario.
```

---

### Tarea 2.2: Transformation Service

```
Contexto:
Soy desarrollador de DataMap. Los mappings tienen un campo `transformation_logic_encrypted` que almacena expresiones SQL (ej: "UPPER(TRIM({column}))") pero no se aplican al generar scripts. Necesito un servicio que parsee y aplique estas transformaciones.

Archivo a crear:
`backend/app/services/transformation_service.py`

Funciones SQL a soportar:

**String Functions:**
- UPPER, LOWER, TRIM, LTRIM, RTRIM
- CONCAT (varios argumentos)
- SUBSTRING(column, start, length)
- REPLACE(column, old, new)
- LENGTH

**Numeric Functions:**
- CAST(column AS type)
- ROUND(column, decimals)
- CEIL, FLOOR
- ABS

**Date/Time Functions:**
- TO_TIMESTAMP(column)
- DATE(column)
- EXTRACT(field FROM column)

**Conditional:**
- CASE WHEN ... THEN ... ELSE ... END
- COALESCE(column, default)
- NULLIF(column, value)

**Aggregate (para validación, no en SELECT):**
- SUM, AVG, COUNT, MAX, MIN

Estructura del servicio:
```python
import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class TransformationType(Enum):
    STRING = "string"
    NUMERIC = "numeric"
    DATE = "date"
    CONDITIONAL = "conditional"
    AGGREGATE = "aggregate"


class TransformationService:
    # Funciones soportadas por categoría
    SUPPORTED_FUNCTIONS = {
        TransformationType.STRING: [
            'UPPER', 'LOWER', 'TRIM', 'LTRIM', 'RTRIM',
            'CONCAT', 'SUBSTRING', 'REPLACE', 'LENGTH'
        ],
        TransformationType.NUMERIC: [
            'CAST', 'ROUND', 'CEIL', 'FLOOR', 'ABS'
        ],
        TransformationType.DATE: [
            'TO_TIMESTAMP', 'DATE', 'TIMESTAMP', 'EXTRACT'
        ],
        TransformationType.CONDITIONAL: [
            'CASE', 'COALESCE', 'NULLIF'
        ],
        TransformationType.AGGREGATE: [
            'SUM', 'AVG', 'COUNT', 'MAX', 'MIN'
        ]
    }

    def parse_transformation(
        self,
        transformation_logic: str
    ) -> Dict[str, Any]:
        """
        Parsea expresión de transformación

        Input: "UPPER(TRIM({column}))"
        Output:
        {
            'is_valid': True,
            'type': 'nested',
            'functions': ['TRIM', 'UPPER'],
            'column_placeholder': '{column}',
            'original_expression': 'UPPER(TRIM({column}))'
        }

        Input: "CAST({column} AS INTEGER)"
        Output:
        {
            'is_valid': True,
            'type': 'cast',
            'function': 'CAST',
            'target_type': 'INTEGER',
            'original_expression': 'CAST({column} AS INTEGER)'
        }

        Validaciones:
        - Verificar paréntesis balanceados
        - Verificar que las funciones existan en SUPPORTED_FUNCTIONS
        - Verificar que contiene {column} placeholder
        """
        pass

    def generate_transformation_sql(
        self,
        column_name: str,
        transformation: Dict[str, Any],
        origin_dialect: str,
        dest_dialect: str
    ) -> str:
        """
        Genera SQL específico por dialecto

        Ejemplo:
        column_name = "email"
        transformation = {
            'functions': ['TRIM', 'UPPER'],
            'original_expression': 'UPPER(TRIM({column}))'
        }
        origin_dialect = "postgresql"
        dest_dialect = "postgresql"

        Return: "UPPER(TRIM(email))"

        Conversiones por dialecto:
        CAST a INTEGER:
          - PostgreSQL: column::INTEGER
          - MySQL: CAST(column AS SIGNED)
          - SQL Server: CAST(column AS INT)
          - Oracle: TO_NUMBER(column)

        CONCAT:
          - PostgreSQL: CONCAT(a, b) o a || b
          - MySQL: CONCAT(a, b)
          - SQL Server: CONCAT(a, b) o a + b
          - Oracle: a || b

        TO_TIMESTAMP:
          - PostgreSQL: TO_TIMESTAMP(column, format)
          - MySQL: STR_TO_DATE(column, format)
          - SQL Server: CONVERT(DATETIME, column)
          - Oracle: TO_TIMESTAMP(column, format)
        """
        pass

    def validate_transformation(
        self,
        transformation_logic: str,
        origin_type: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Valida que la transformación es aplicable al tipo de dato

        Ejemplo:
        transformation_logic = "UPPER({column})"
        origin_type = "VARCHAR"
        Return: (True, None)

        transformation_logic = "UPPER({column})"
        origin_type = "INTEGER"
        Return: (False, "UPPER function cannot be applied to INTEGER type")

        Reglas:
        - String functions solo en tipos string (VARCHAR, TEXT, CHAR)
        - Numeric functions solo en tipos numéricos
        - Date functions solo en tipos fecha/hora
        - CAST permite cualquier tipo origen
        """
        pass

    def apply_transformation_to_mapping(
        self,
        column_name: str,
        transformation_logic: Optional[str],
        origin_type: str,
        dest_type: str,
        dialect: str
    ) -> str:
        """
        Método de alto nivel que aplica transformación o genera conversión automática

        Si transformation_logic existe:
          1. Parsear transformación
          2. Validar contra origin_type
          3. Generar SQL por dialecto
          4. Reemplazar {column} por column_name

        Si transformation_logic es None pero tipos incompatibles:
          Generar conversión automática:
          - VARCHAR → INTEGER: CAST(column AS INTEGER)
          - DATE → TIMESTAMP: column::TIMESTAMP
          - etc.

        Returns: SQL string para usar en SELECT
        """
        pass

    def _generate_auto_conversion(
        self,
        column_name: str,
        origin_type: str,
        dest_type: str,
        dialect: str
    ) -> str:
        """
        Genera conversión automática cuando no hay transformation_logic
        pero los tipos son incompatibles
        """
        pass

    def _replace_column_placeholder(
        self,
        expression: str,
        column_name: str
    ) -> str:
        """
        Reemplaza {column} por column_name en la expresión

        Maneja casos edge:
        - Múltiples {column} en la expresión
        - Column names con caracteres especiales (escapar)
        """
        return expression.replace('{column}', column_name)

    def _validate_syntax(self, expression: str) -> Tuple[bool, Optional[str]]:
        """
        Valida sintaxis SQL básica:
        - Paréntesis balanceados
        - Funciones conocidas
        - No SQL injection patterns
        """
        pass

    def get_supported_functions(self) -> Dict[str, List[str]]:
        """
        Retorna diccionario de funciones soportadas por categoría
        Útil para UI
        """
        return {cat.value: funcs for cat, funcs in self.SUPPORTED_FUNCTIONS.items()}
```

Ejemplo de uso (integración con migration_script_service.py):
```python
# En MigrationScriptService
from app.services.transformation_service import TransformationService

transformation_service = TransformationService()

# Al generar SELECT clause
for mapping in mappings:
    origin_column = mapping['origin_column']
    transformation_logic = mapping.get('transformation_logic')  # Puede ser None

    # Aplicar transformación
    select_expression = transformation_service.apply_transformation_to_mapping(
        column_name=origin_column,
        transformation_logic=transformation_logic,
        origin_type=mapping['origin_type'],
        dest_type=mapping['dest_type'],
        dialect='postgresql'
    )

    # Usar en SELECT
    select_clause += f"    {select_expression} AS {mapping['dest_column']},\n"
```

Test file a crear:
`backend/test/unit/services/test_transformation_service.py`

Tests requeridos:
1. test_parse_simple_function
2. test_parse_nested_functions
3. test_parse_cast_expression
4. test_parse_case_when
5. test_generate_sql_upper_trim
6. test_generate_sql_cast_by_dialect
7. test_generate_sql_concat_by_dialect
8. test_validate_transformation_correct_type
9. test_validate_transformation_wrong_type
10. test_auto_conversion_varchar_to_int

Por favor implementa este servicio con parsing robusto y soporte multi-dialecto.
```

---

### Tarea 2.3: Error Recovery & Retry

```
Contexto:
Soy desarrollador de DataMap. Necesito agregar lógica de retry con exponential backoff para errores transitorios (deadlocks, timeouts) y clasificación inteligente de errores para sugerir soluciones.

Archivo a modificar:
`backend/app/services/execution_service.py` (ya debería existir de Tarea 1.3)

Agregar métodos:

1. **Execute with Retry**
```python
def execute_with_retry(
    self,
    db: Session,
    step_sql: str,
    dest_adapter: BaseDBAdapter,
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    Ejecuta SQL con retry automático para errores transitorios

    Errores retryables:
    - Deadlocks (PostgreSQL error code 40P01, MySQL 1213)
    - Lock timeout (PostgreSQL 55P03)
    - Connection drops (recuperables)

    Errores NO retryables:
    - Syntax errors
    - Constraint violations
    - Permission denied
    - Data type errors

    Estrategia:
    - Retry 1: 1 segundo delay
    - Retry 2: 2 segundos delay
    - Retry 3: 4 segundos delay
    (exponential backoff)

    Returns:
    {
        'success': True,
        'rows_affected': 10000,
        'retries': 1,  # Número de reintentos necesarios
        'final_error': None
    }

    Si falla después de max_retries:
    {
        'success': False,
        'rows_affected': 0,
        'retries': 3,
        'final_error': 'Deadlock detected after 3 retries'
    }
    """
    import time

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            result = dest_adapter.execute(step_sql)
            rows = result.rowcount if hasattr(result, 'rowcount') else 0

            logger.info(
                f"SQL executed successfully on attempt {attempt + 1}/{max_retries + 1}"
            )

            return {
                'success': True,
                'rows_affected': rows,
                'retries': attempt,
                'final_error': None
            }

        except Exception as e:
            last_error = e
            error_type = self._classify_error(e)

            # No retry si no es error transitorio
            if not error_type['is_retryable']:
                logger.warning(f"Non-retryable error: {error_type['category']}")
                raise

            # Si quedan reintentos, esperar y continuar
            if attempt < max_retries:
                delay = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(
                    f"Retryable error on attempt {attempt + 1}: {str(e)}. "
                    f"Retrying in {delay}s..."
                )
                time.sleep(delay)
            else:
                logger.error(f"Max retries ({max_retries}) exceeded")
                raise

    # No debería llegar aquí, pero por si acaso
    return {
        'success': False,
        'rows_affected': 0,
        'retries': max_retries,
        'final_error': str(last_error)
    }
```

2. **Classify Error**
```python
def _classify_error(self, error: Exception) -> Dict[str, Any]:
    """
    Clasifica el error en categorías para decidir si es retryable

    Returns:
    {
        'category': 'deadlock' | 'timeout' | 'connection' | 'syntax' | 'constraint' | 'data' | 'permission' | 'unknown',
        'is_retryable': True | False,
        'severity': 'low' | 'medium' | 'high',
        'user_message': 'Mensaje amigable para el usuario',
        'suggestion': 'Sugerencia para resolver'
    }
    """
    import psycopg2

    error_str = str(error).lower()

    # Deadlock
    if (
        isinstance(error, psycopg2.errors.DeadlockDetected) or
        'deadlock' in error_str or
        '40P01' in error_str or  # PostgreSQL code
        '1213' in error_str  # MySQL code
    ):
        return {
            'category': 'deadlock',
            'is_retryable': True,
            'severity': 'medium',
            'user_message': 'Database deadlock detected',
            'suggestion': 'Will retry automatically. If persists, reduce concurrent operations.'
        }

    # Lock timeout
    if (
        isinstance(error, psycopg2.errors.LockNotAvailable) or
        'lock timeout' in error_str or
        '55P03' in error_str
    ):
        return {
            'category': 'timeout',
            'is_retryable': True,
            'severity': 'medium',
            'user_message': 'Lock timeout waiting for table',
            'suggestion': 'Will retry. Consider migrating during low-traffic period.'
        }

    # Connection error
    if (
        'connection' in error_str or
        'could not connect' in error_str or
        'connection refused' in error_str
    ):
        return {
            'category': 'connection',
            'is_retryable': True,
            'severity': 'high',
            'user_message': 'Lost connection to database',
            'suggestion': 'Will retry. Check network and database server status.'
        }

    # Syntax error
    if (
        isinstance(error, psycopg2.errors.SyntaxError) or
        'syntax error' in error_str
    ):
        return {
            'category': 'syntax',
            'is_retryable': False,
            'severity': 'high',
            'user_message': 'SQL syntax error in migration script',
            'suggestion': 'Check generated script for syntax errors. Report to support if script was auto-generated.'
        }

    # Constraint violation
    if (
        'constraint' in error_str or
        'foreign key' in error_str or
        'unique' in error_str or
        'duplicate key' in error_str
    ):
        return {
            'category': 'constraint',
            'is_retryable': False,
            'severity': 'high',
            'user_message': 'Database constraint violation',
            'suggestion': 'Run pre-migration validation to identify issues. Check table migration order.'
        }

    # Data error (overflow, type mismatch, etc.)
    if (
        'numeric value' in error_str or
        'invalid input' in error_str or
        'out of range' in error_str
    ):
        return {
            'category': 'data',
            'is_retryable': False,
            'severity': 'high',
            'user_message': 'Data conversion error',
            'suggestion': 'Check data type compatibility. Run pre-migration validation.'
        }

    # Permission denied
    if (
        'permission denied' in error_str or
        'access denied' in error_str or
        'insufficient privilege' in error_str
    ):
        return {
            'category': 'permission',
            'is_retryable': False,
            'severity': 'high',
            'user_message': 'Insufficient database permissions',
            'suggestion': 'Grant INSERT permission on destination tables to database user.'
        }

    # Unknown error
    return {
        'category': 'unknown',
        'is_retryable': False,
        'severity': 'high',
        'user_message': f'Unexpected error: {str(error)[:100]}',
        'suggestion': 'Contact support with error details.'
    }
```

3. **Handle Execution Error** (método de alto nivel)
```python
def handle_execution_error(
    self,
    db: Session,
    execution_id: str,
    error: Exception,
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Maneja errores de ejecución de forma inteligente

    Args:
        execution_id: ID de la ejecución fallida
        error: Excepción capturada
        context: {step, table, sql, ...}

    Returns:
    {
        'error_classification': {...},
        'should_retry': True | False,
        'should_rollback': True | False,
        'user_action_required': True | False,
        'suggested_fix': 'Specific suggestion based on error'
    }
    """
    classification = self._classify_error(error)

    # Determinar acciones
    should_retry = classification['is_retryable']
    should_rollback = not should_retry  # Si no es retryable, rollback
    user_action_required = not should_retry

    # Generar sugerencia específica
    suggested_fix = self._generate_fix_suggestion(
        classification,
        context
    )

    # Actualizar execution_log con error detallado
    self._update_execution_record(
        db,
        execution_id,
        status='failed',
        error_message=f"{classification['user_message']}: {str(error)}",
        execution_log=context.get('execution_log', [])
    )

    return {
        'error_classification': classification,
        'should_retry': should_retry,
        'should_rollback': should_rollback,
        'user_action_required': user_action_required,
        'suggested_fix': suggested_fix
    }
```

4. **Generate Fix Suggestion**
```python
def _generate_fix_suggestion(
    self,
    classification: Dict,
    context: Dict
) -> str:
    """
    Genera sugerencia específica basada en el tipo de error y contexto

    Ejemplos:
    - Constraint violation en tabla orders:
      "Table 'orders' has FK to 'customers'. Migrate 'customers' first."

    - Data truncation en columna description:
      "Column 'users.description' has values exceeding VARCHAR(100).
       Increase destination column size or truncate data."

    - Deadlock:
      "Reduce concurrent operations or migrate during low-traffic period."
    """
    category = classification['category']
    table = context.get('table', 'unknown')

    if category == 'constraint':
        return (
            f"Check foreign key dependencies for table '{table}'. "
            f"Run GET /api/projects/{{id}}/migration/dependency-graph to see correct order."
        )

    elif category == 'data':
        column = context.get('column', 'unknown')
        return (
            f"Data conversion failed for column '{table}.{column}'. "
            f"Run pre-migration validation to identify problematic rows."
        )

    elif category == 'permission':
        return (
            f"Grant INSERT, UPDATE, DELETE permissions on table '{table}' to database user. "
            f"SQL: GRANT ALL ON TABLE {table} TO migration_user;"
        )

    elif category == 'deadlock':
        return (
            "Deadlock detected. Will retry automatically. "
            "If persists, consider: 1) Reduce batch size, 2) Migrate one table at a time, "
            "3) Schedule migration during low-traffic period."
        )

    else:
        return classification.get('suggestion', 'Contact support for assistance.')
```

Actualizar método `execute_migration` para usar retry:
```python
# En execute_migration, reemplazar llamada directa a execute por:
result = self.execute_with_retry(
    db,
    step_sql,
    dest_adapter,
    max_retries=3
)
```

Tests adicionales a agregar:
`backend/test/unit/services/test_execution_service.py`
1. test_execute_with_retry_success_first_attempt
2. test_execute_with_retry_success_after_retries
3. test_execute_with_retry_max_retries_exceeded
4. test_classify_error_deadlock
5. test_classify_error_constraint_violation
6. test_classify_error_permission_denied
7. test_handle_execution_error_retryable
8. test_handle_execution_error_non_retryable

Por favor implementa esta lógica de retry y error handling robusto.
```

---

### Tarea 2.4: Validation API Endpoints

```
Contexto:
Soy desarrollador de DataMap. Tengo ValidationService implementado (Tarea 2.1) y necesito exponerlo via REST API.

Archivo a modificar:
`backend/app/routers/migration.py` (ya creado en Tarea 1.4)

Endpoints a agregar:

1. **Pre-Flight Validation**
```python
@router.post("/api/projects/{project_id}/migration/validate")
async def validate_pre_migration(
    project_id: str,
    options: Optional[PreMigrationValidationOptions] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Ejecuta validaciones pre-migración

    Request body (opcional):
    {
        "origin_session_id": "uuid",  # Si se conectó a BD origen
        "checks": ["referential_integrity", "type_compatibility", "data_quality", "schema_consistency"]
    }

    Si no se proporciona, ejecuta todos los checks disponibles.

    Response:
    {
        "report_id": "uuid",
        "status": "pass" | "warning" | "fail",
        "checks_passed": 12,
        "checks_warning": 3,
        "checks_failed": 0,
        "can_proceed": true,
        "issues": [
            {
                "type": "data_quality",
                "severity": "warning",
                "table": "users",
                "column": "description",
                "message": "5 rows exceed VARCHAR(100) limit",
                "affected_rows": [1, 2, 3, 4, 5],
                "recommendation": "Increase column size or truncate data"
            }
        ],
        "recommendations": [
            "Consider migrating customers before orders",
            "Increase users.description to VARCHAR(255)"
        ],
        "created_at": "2025-01-16T14:30:00Z"
    }

    Lógica:
    1. Validar project ownership
    2. Si origin_session_id proporcionado: obtener adapter
    3. Llamar ValidationService.pre_migration_validation()
    4. Guardar reporte en tabla validation_reports
    5. Retornar reporte
    """
```

Modelo Pydantic:
```python
class PreMigrationValidationOptions(BaseModel):
    origin_session_id: Optional[str] = None
    checks: Optional[List[str]] = None  # Si None, ejecuta todos
```

2. **Post-Migration Validation**
```python
@router.post("/api/projects/{project_id}/migration/executions/{execution_id}/validate")
async def validate_post_migration(
    project_id: str,
    execution_id: str,
    options: PostMigrationValidationOptions,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Ejecuta validaciones post-migración

    Request body:
    {
        "origin_session_id": "uuid",  # Requerido
        "dest_session_id": "uuid",    # Requerido
        "sample_size": 100  # Opcional, default 100
    }

    Response:
    {
        "report_id": "uuid",
        "status": "pass" | "warning" | "fail",
        "checks_passed": 15,
        "checks_warning": 0,
        "checks_failed": 0,
        "row_count_match": true,
        "sample_verification": {
            "customers": {"match_percent": 100.0, "mismatches": []},
            "orders": {"match_percent": 98.5, "mismatches": [...]},
        },
        "constraints_valid": true,
        "issues": [],
        "created_at": "2025-01-16T14:35:00Z"
    }

    Lógica:
    1. Validar ownership y que execution existe
    2. Obtener origin y dest adapters de sessions
    3. Llamar ValidationService.post_migration_validation()
    4. Guardar reporte
    5. Retornar reporte
    """
```

Modelo Pydantic:
```python
class PostMigrationValidationOptions(BaseModel):
    origin_session_id: str
    dest_session_id: str
    sample_size: int = 100
```

3. **Get Validation Report**
```python
@router.get("/api/projects/{project_id}/migration/validation-reports/{report_id}")
async def get_validation_report(
    project_id: str,
    report_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Obtiene un reporte de validación existente

    Response: Same as validate endpoints
    """
```

4. **List Validation Reports**
```python
@router.get("/api/projects/{project_id}/migration/validation-reports")
async def list_validation_reports(
    project_id: str,
    report_type: Optional[str] = None,  # pre_flight o post_migration
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Lista reportes de validación del proyecto

    Response:
    {
        "reports": [
            {
                "id": "uuid",
                "report_type": "pre_flight",
                "status": "warning",
                "checks_passed": 12,
                "checks_warning": 3,
                "created_at": "2025-01-16T14:30:00Z"
            },
            ...
        ],
        "total": 25,
        "limit": 10,
        "offset": 0
    }
    """
```

Imports adicionales:
```python
from app.services.validation_service import ValidationService
from app.services.db_connection_service import DBConnectionService
```

Tests a agregar:
`backend/test/integration/test_migration_api.py`
1. test_validate_pre_migration_all_pass
2. test_validate_pre_migration_with_warnings
3. test_validate_post_migration_success
4. test_get_validation_report
5. test_list_validation_reports

Por favor implementa estos endpoints con validación apropiada.
```

---

## FASE 3 - ENTERPRISE FEATURES

### Tarea 3.1: Documentation Service

```
Contexto:
Soy desarrollador de DataMap. Las consultoras necesitan documentación automática de sus migraciones (execution plans, validation reports en PDF, risk assessments).

Archivo a crear:
`backend/app/services/documentation_service.py`

Dependencias nuevas:
```txt
reportlab==4.0.7  # PDF generation
weasyprint==60.1  # HTML to PDF alternative
```

Funcionalidad:

1. **Generate Execution Plan (Markdown)**
```python
def generate_execution_plan(
    self,
    db: Session,
    project_id: str,
    dependency_graph: Dict
) -> str:
    """
    Genera documento Markdown con plan de ejecución

    Incluye:
    1. Migration Overview
       - Project name
       - Source/destination DBs
       - Total tables/columns/mappings
       - Estimated duration
       - Estimated rows

    2. Dependency Graph (Mermaid diagram)
       ```mermaid
       graph TD
           A[customers] --> B[orders]
           A --> C[invoices]
           B --> D[order_items]
       ```

    3. Step-by-Step Execution Plan
       - Table 1: customers (0 dependencies)
         - Rows: 10,000
         - Estimated time: 30 seconds
       - Table 2: orders (depends on customers)
         - Rows: 25,000
         - Estimated time: 1.5 minutes

    4. Risk Assessment
       - High: 2 type conversions may lose precision
       - Medium: 1 table has circular FK dependency
       - Low: All other mappings are safe

    5. Rollback Procedures
       - Automatic backup created before execution
       - Rollback script: rollback_{execution_id}.sql
       - Estimated rollback time: 2 minutes

    Returns: Markdown string
    """
```

2. **Generate Validation Report PDF**
```python
def generate_validation_report_pdf(
    self,
    validation_report: ValidationReport
) -> bytes:
    """
    Genera PDF profesional de validation report

    Estructura:
    [Cover Page]
    - DataMap logo
    - Report title
    - Generated date
    - Project name

    [Executive Summary]
    - Status: PASS / WARNING / FAIL
    - Can proceed: YES / NO
    - Checks passed: X
    - Checks warning: Y
    - Checks failed: Z

    [Detailed Findings]
    - Issue 1: [type] [severity]
      Table: users
      Column: description
      Message: 5 rows exceed VARCHAR(100)
      Recommendation: Increase to VARCHAR(255)

    [Recommendations]
    - List of actionable recommendations

    [Sign-off Section]
    - Reviewed by: ______________
    - Approved by: ______________
    - Date: ______________

    Returns: PDF bytes
    """
```

3. **Generate Risk Assessment**
```python
def generate_risk_assessment(
    self,
    db: Session,
    project_id: str,
    validation_report: Optional[ValidationReport] = None
) -> Dict[str, Any]:
    """
    Analiza riesgos de la migración

    Categorías de riesgo:
    - Data Loss (transformations, type conversions)
    - Constraint Violations (FK, UNIQUE)
    - Performance (large tables, indexes)
    - Compatibility (unsupported features)

    Returns:
    {
        "overall_risk": "low" | "medium" | "high",
        "risk_factors": [
            {
                "category": "data_loss",
                "severity": "high",
                "description": "BIGINT → INTEGER may overflow",
                "affected_tables": ["orders"],
                "mitigation": "Verify all values fit in INTEGER range"
            }
        ],
        "mitigation_steps": [
            "Run pre-migration validation",
            "Create backup before execution",
            "Execute dry-run first"
        ]
    }
    """
```

4. **Generate Rollback Procedure**
```python
def generate_rollback_procedure(
    self,
    db: Session,
    execution_id: str
) -> str:
    """
    Genera procedimiento de rollback en Markdown

    Incluye:
    1. Rollback Overview
       - Execution to rollback: {execution_id}
       - Backup location: {backup_path}
       - Tables affected: {table_list}

    2. Pre-Rollback Checklist
       - [ ] Stop application traffic to database
       - [ ] Verify backup integrity
       - [ ] Estimate rollback duration

    3. Rollback Steps
       Step 1: Drop migrated tables
       ```sql
       DROP TABLE customers_new;
       ```

       Step 2: Restore from backup
       ```sql
       ALTER TABLE customers_backup RENAME TO customers;
       ```

    4. Post-Rollback Verification
       - [ ] Verify row counts
       - [ ] Verify constraints
       - [ ] Restart application

    Returns: Markdown string
    """
```

Estructura del servicio:
```python
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

# PDF generation
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT

logger = logging.getLogger(__name__)


class DocumentationService:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Crea estilos personalizados para PDFs"""
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=30,
            alignment=TA_CENTER
        ))
        # Más estilos...

    def generate_execution_plan(self, db, project_id, dependency_graph) -> str:
        # Implementación...

    def generate_validation_report_pdf(self, validation_report) -> bytes:
        # Implementación...

    def generate_risk_assessment(self, db, project_id, validation_report) -> Dict:
        # Implementación...

    def generate_rollback_procedure(self, db, execution_id) -> str:
        # Implementación...

    def _generate_mermaid_diagram(self, dependency_graph: Dict) -> str:
        """
        Genera diagrama Mermaid de dependencias

        Returns:
        ```mermaid
        graph TD
            A[customers] --> B[orders]
        ```
        """
        pass
```

Endpoint API:
```python
# En migration.py
@router.get("/api/projects/{project_id}/migration/documentation/execution-plan")
async def get_execution_plan(...):
    # Retorna Markdown

@router.get("/api/projects/{project_id}/migration/validation-reports/{report_id}/pdf")
async def download_validation_report_pdf(...):
    # Retorna PDF bytes con Content-Type: application/pdf

@router.get("/api/projects/{project_id}/migration/documentation/risk-assessment")
async def get_risk_assessment(...):
    # Retorna JSON
```

Tests:
`backend/test/unit/services/test_documentation_service.py`
1. test_generate_execution_plan
2. test_generate_validation_report_pdf
3. test_generate_risk_assessment
4. test_mermaid_diagram_generation

Por favor implementa este servicio con PDFs profesionales.
```

---

[CONTINUARÁ EN EL SIGUIENTE MENSAJE CON FASE 3 RESTANTE Y FASE 4]

¿Te parece bien la estructura hasta ahora? ¿Quieres que continúe con las tareas restantes (3.2, 3.3, y Fase 4)?
```

---

### Tarea 3.2: Preview Service

```
Contexto:
Soy desarrollador de DataMap. Las consultoras quieren ver un preview de los datos que se migrarán antes de ejecutar, para detectar problemas y ganar confianza. Necesito un servicio que muestre muestras de datos con transformaciones aplicadas.

Archivo a crear:
`backend/app/services/preview_service.py`

Funcionalidad:

1. **Generate Preview**
```python
def generate_preview(
    self,
    db: Session,
    project_id: str,
    origin_adapter: BaseDBAdapter,
    sample_size: int = 10
) -> Dict[str, Any]:
    """
    Genera preview de datos que se migrarán

    Para cada tabla con mappings:
    1. Selecciona {sample_size} filas aleatorias de origen
    2. Aplica transformaciones definidas en mappings
    3. Detecta warnings (truncado, overflow, etc.)
    4. Muestra lado a lado: origen vs transformado

    Returns:
    {
        "project_id": "uuid",
        "total_tables": 5,
        "tables": [
            {
                "table_name": "users",
                "origin_table": "tbl_users",
                "dest_table": "users",
                "total_rows_estimate": 10000,
                "sample_size": 10,
                "sample_rows": [
                    {
                        "row_number": 1,
                        "origin_data": {
                            "name": "john doe",
                            "email": "JOHN@EXAMPLE.COM",
                            "description": "Very long text that exceeds 100 characters..."
                        },
                        "transformed_data": {
                            "name": "JOHN DOE",  # UPPER applied
                            "email": "john@example.com",  # LOWER applied
                            "description": "Very long text that exceeds 100 characters..."
                        },
                        "warnings": [
                            {
                                "column": "description",
                                "type": "truncation",
                                "message": "Value length (150) exceeds destination VARCHAR(100)",
                                "severity": "warning",
                                "will_be_truncated": true
                            }
                        ]
                    },
                    # ... 9 more rows
                ],
                "column_mappings": [
                    {
                        "origin_column": "name",
                        "dest_column": "name",
                        "origin_type": "VARCHAR(255)",
                        "dest_type": "VARCHAR(255)",
                        "transformation": "UPPER({column})",
                        "compatibility": "safe"
                    },
                    {
                        "origin_column": "email",
                        "dest_column": "email",
                        "origin_type": "VARCHAR(255)",
                        "dest_type": "VARCHAR(255)",
                        "transformation": "LOWER({column})",
                        "compatibility": "safe"
                    },
                    {
                        "origin_column": "description",
                        "dest_column": "description",
                        "origin_type": "TEXT",
                        "dest_type": "VARCHAR(100)",
                        "transformation": null,
                        "compatibility": "warning"
                    }
                ],
                "warnings_summary": {
                    "truncation": 3,
                    "overflow": 0,
                    "null_conversion": 0
                }
            },
            # ... more tables
        ],
        "overall_warnings": {
            "total": 5,
            "by_severity": {
                "warning": 5,
                "error": 0
            },
            "by_type": {
                "truncation": 3,
                "overflow": 0,
                "null_conversion": 2
            }
        },
        "generated_at": "2025-01-16T14:30:00Z"
    }
    """
```

2. **Check Value Issues**
```python
def _check_value_issues(
    self,
    value: Any,
    origin_type: str,
    dest_type: str,
    transformation: Optional[str]
) -> List[Dict[str, Any]]:
    """
    Detecta problemas potenciales con un valor

    Chequeos:
    1. Truncation
       - String length > dest length
       - Ejemplo: "Long text" → VARCHAR(5)

    2. Overflow
       - Numeric value > dest range
       - Ejemplo: 3000000000 → INTEGER (max 2147483647)

    3. Null conversion
       - NULL en origen, NOT NULL en destino sin default

    4. Precision loss
       - NUMERIC(10,5) → NUMERIC(10,2)
       - Ejemplo: 12345.67890 → 12345.68

    Returns: Lista de warnings encontrados
    """
```

3. **Apply Transformation Preview**
```python
def _apply_transformation_preview(
    self,
    value: Any,
    transformation_logic: Optional[str],
    origin_type: str
) -> Any:
    """
    Simula aplicación de transformación para preview

    NO ejecuta SQL, simula el resultado en Python:
    - UPPER({column}) → value.upper()
    - LOWER({column}) → value.lower()
    - TRIM({column}) → value.strip()
    - CAST({column} AS INTEGER) → int(value)
    - Etc.

    Returns: Valor transformado
    """
```

4. **Get Random Sample**
```python
def _get_random_sample(
    self,
    origin_adapter: BaseDBAdapter,
    table_name: str,
    columns: List[str],
    sample_size: int
) -> List[Dict[str, Any]]:
    """
    Obtiene muestra aleatoria de filas

    SQL generado:
    PostgreSQL: SELECT ... ORDER BY RANDOM() LIMIT 10
    MySQL: SELECT ... ORDER BY RAND() LIMIT 10
    SQL Server: SELECT TOP 10 ... ORDER BY NEWID()
    Oracle: SELECT ... ORDER BY DBMS_RANDOM.VALUE FETCH FIRST 10 ROWS ONLY

    Returns: Lista de filas como dicts
    """
```

Estructura del servicio:
```python
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.utils.db_adapters.base_adapter import BaseDBAdapter
from app.services.transformation_service import TransformationService
from backend.utilities.migrations.validators import TYPE_COMPATIBILITY_MATRIX

logger = logging.getLogger(__name__)


class PreviewService:
    def __init__(self):
        self.transformation_service = TransformationService()
        self.type_matrix = TYPE_COMPATIBILITY_MATRIX

    def generate_preview(
        self,
        db: Session,
        project_id: str,
        origin_adapter: BaseDBAdapter,
        sample_size: int = 10
    ) -> Dict[str, Any]:
        """Implementar según spec arriba"""
        pass

    def _check_value_issues(
        self,
        value: Any,
        origin_type: str,
        dest_type: str,
        transformation: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Implementar según spec arriba"""
        pass

    def _apply_transformation_preview(
        self,
        value: Any,
        transformation_logic: Optional[str],
        origin_type: str
    ) -> Any:
        """Implementar según spec arriba"""
        pass

    def _get_random_sample(
        self,
        origin_adapter: BaseDBAdapter,
        table_name: str,
        columns: List[str],
        sample_size: int
    ) -> List[Dict[str, Any]]:
        """Implementar según spec arriba"""
        pass

    def _simulate_transformation_in_python(
        self,
        value: Any,
        function: str
    ) -> Any:
        """
        Simula funciones SQL comunes en Python

        UPPER → str.upper()
        LOWER → str.lower()
        TRIM → str.strip()
        CAST AS INTEGER → int()
        ROUND(x, 2) → round(x, 2)
        Etc.
        """
        pass

    def _get_type_length(self, type_str: str) -> Optional[int]:
        """
        Extrae length de tipo
        VARCHAR(100) → 100
        CHAR(50) → 50
        INTEGER → None
        """
        import re
        match = re.search(r'\((\d+)\)', type_str)
        return int(match.group(1)) if match else None

    def _estimate_table_rows(
        self,
        origin_adapter: BaseDBAdapter,
        table_name: str
    ) -> int:
        """
        Estima total de filas en tabla

        PostgreSQL: SELECT reltuples FROM pg_class WHERE relname = 'table'
        MySQL: SELECT table_rows FROM information_schema.tables
        SQL Server: SELECT rows FROM sys.partitions
        Oracle: SELECT num_rows FROM all_tables

        Fallback: SELECT COUNT(*) (lento pero preciso)
        """
        pass
```

API Endpoint:
```python
# En migration.py
@router.post("/api/projects/{project_id}/migration/preview")
async def generate_migration_preview(
    project_id: str,
    options: PreviewOptions,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Request body:
    {
        "origin_session_id": "uuid",
        "sample_size": 10  # Optional, default 10
    }

    Response: Preview dict según spec arriba
    """
```

Modelo Pydantic:
```python
class PreviewOptions(BaseModel):
    origin_session_id: str
    sample_size: int = 10
```

Tests:
`backend/test/unit/services/test_preview_service.py`
1. test_generate_preview_basic
2. test_detect_truncation_warning
3. test_detect_overflow_warning
4. test_apply_transformation_preview_upper
5. test_apply_transformation_preview_cast
6. test_get_random_sample
7. test_estimate_table_rows

Por favor implementa este servicio para dar confianza a usuarios antes de migrar.
```

---

### Tarea 3.3: Pause/Resume Functionality

```
Contexto:
Soy desarrollador de DataMap. Migraciones largas (horas) necesitan poder pausarse y reanudarse sin perder progreso. Necesito agregar checkpointing al execution service.

Archivo a modificar:
`backend/app/services/execution_service.py` (ya existe de Tarea 1.3)

Cambios en DB:
`backend/utilities/migrations/008_execution_checkpoint.sql`
```sql
ALTER TABLE migration_executions
ADD COLUMN checkpoint_data JSONB;

COMMENT ON COLUMN migration_executions.checkpoint_data IS
'Stores checkpoint for pause/resume: {current_table, current_offset, completed_tables, pending_tables}';

-- Agregar nuevo status
ALTER TABLE migration_executions
DROP CONSTRAINT IF EXISTS migration_executions_status_check;

ALTER TABLE migration_executions
ADD CONSTRAINT migration_executions_status_check
CHECK (status IN (
    'pending', 'running', 'success', 'failed', 'rolled_back', 'dry_run_complete', 'paused', 'resuming'
));
```

Métodos a agregar:

1. **Pause Execution**
```python
def pause_execution(
    self,
    db: Session,
    execution_id: str
) -> Dict[str, Any]:
    """
    Pausa ejecución en curso

    Proceso:
    1. Verificar que execution está 'running'
    2. Completar batch/tabla actual (no interrumpir mid-transaction)
    3. COMMIT transaction actual
    4. Guardar checkpoint:
       {
           "paused_at": "2025-01-16T14:30:00Z",
           "current_table": "orders",
           "current_offset": 5000,  # Filas ya migradas de tabla actual
           "completed_tables": ["customers", "products"],
           "pending_tables": ["order_items", "invoices"],
           "total_rows_migrated": 15000,
           "execution_log": [...]
       }
    5. Actualizar status a 'paused'

    Returns:
    {
        "execution_id": "uuid",
        "status": "paused",
        "paused_at": "2025-01-16T14:30:00Z",
        "progress": {
            "completed_tables": 2,
            "total_tables": 5,
            "rows_migrated": 15000
        },
        "can_resume": true
    }

    Errores:
    - Si execution no existe o no está 'running': HTTPException 400
    - Si no se puede pausar safely: HTTPException 500
    """
```

2. **Resume Execution**
```python
def resume_execution(
    self,
    db: Session,
    execution_id: str,
    dest_adapter: BaseDBAdapter
) -> Dict[str, Any]:
    """
    Reanuda ejecución pausada

    Proceso:
    1. Verificar que execution está 'paused'
    2. Cargar checkpoint_data
    3. Validar que destino sigue accesible
    4. Actualizar status a 'resuming'
    5. Continuar desde checkpoint:
       - Saltar completed_tables
       - Si current_table parcial: continuar desde current_offset
       - Ejecutar pending_tables
    6. Actualizar status a 'running'
    7. Continuar ejecución normal

    Returns:
    {
        "execution_id": "uuid",
        "status": "running",
        "resumed_at": "2025-01-16T14:35:00Z",
        "progress": {
            "completed_tables": 2,
            "total_tables": 5,
            "resuming_from_offset": 5000
        }
    }

    Errores:
    - Si execution no 'paused': HTTPException 400
    - Si checkpoint inválido: HTTPException 500
    - Si destino inaccesible: HTTPException 503
    """
```

3. **Create Checkpoint**
```python
def _create_checkpoint(
    self,
    db: Session,
    execution_id: str,
    current_table: str,
    current_offset: int,
    completed_tables: List[str],
    pending_tables: List[str],
    total_rows_migrated: int,
    execution_log: List[Dict]
) -> None:
    """
    Crea checkpoint en DB

    Guarda estado actual en checkpoint_data JSONB
    """
    checkpoint = {
        "paused_at": datetime.utcnow().isoformat(),
        "current_table": current_table,
        "current_offset": current_offset,
        "completed_tables": completed_tables,
        "pending_tables": pending_tables,
        "total_rows_migrated": total_rows_migrated,
        "execution_log": execution_log
    }

    db.execute(
        """
        UPDATE migration_executions
        SET checkpoint_data = :checkpoint,
            status = 'paused'
        WHERE id = :execution_id
        """,
        {"checkpoint": checkpoint, "execution_id": execution_id}
    )
    db.commit()
```

4. **Load Checkpoint**
```python
def _load_checkpoint(
    self,
    db: Session,
    execution_id: str
) -> Optional[Dict[str, Any]]:
    """
    Carga checkpoint de DB

    Returns: checkpoint_data dict o None si no existe
    """
    result = db.execute(
        """
        SELECT checkpoint_data
        FROM migration_executions
        WHERE id = :execution_id
        """,
        {"execution_id": execution_id}
    ).fetchone()

    if result and result[0]:
        return result[0]  # JSONB automáticamente deserializa a dict
    return None
```

5. **Validate Checkpoint**
```python
def _validate_checkpoint(
    self,
    checkpoint: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Valida que checkpoint es válido y no corrupto

    Checks:
    - Tiene campos requeridos (current_table, completed_tables, etc.)
    - paused_at no muy antiguo (< 7 días)
    - Lists no vacías

    Returns: (is_valid, error_message)
    """
```

Modificar método `execute_migration`:
```python
def execute_migration(
    self,
    db: Session,
    project_id: str,
    script: str,
    dest_adapter: BaseDBAdapter,
    dry_run: bool = False,
    resume_from_checkpoint: bool = False
) -> Dict[str, Any]:
    """
    Agregar lógica de checkpointing

    Pseudocódigo:

    if resume_from_checkpoint:
        checkpoint = load_checkpoint(execution_id)
        completed_tables = checkpoint['completed_tables']
        current_table = checkpoint['current_table']
        current_offset = checkpoint['current_offset']
    else:
        completed_tables = []
        current_table = None
        current_offset = 0

    for table in dependency_order:
        if table in completed_tables:
            continue  # Skip

        if table == current_table:
            # Resume from offset
            migrate_table(table, offset=current_offset)
        else:
            # Migrate from beginning
            migrate_table(table, offset=0)

        # Guardar progreso cada N filas (ej: cada 10K)
        if should_checkpoint():
            create_checkpoint(...)

        completed_tables.append(table)
    """
```

API Endpoints:
```python
# En migration.py
@router.post("/api/projects/{project_id}/migration/executions/{execution_id}/pause")
async def pause_migration(
    project_id: str,
    execution_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Pausa migración en curso
    """

@router.post("/api/projects/{project_id}/migration/executions/{execution_id}/resume")
async def resume_migration(
    project_id: str,
    execution_id: str,
    options: ResumeOptions,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Reanuda migración pausada

    Request body:
    {
        "dest_session_id": "uuid"  # Puede ser diferente de la original
    }
    """
```

Modelo Pydantic:
```python
class ResumeOptions(BaseModel):
    dest_session_id: str
```

Tests adicionales:
`backend/test/unit/services/test_execution_service.py`
1. test_pause_execution_success
2. test_pause_execution_not_running
3. test_resume_execution_success
4. test_resume_execution_from_partial_table
5. test_resume_execution_invalid_checkpoint
6. test_checkpoint_validation

Por favor implementa esta funcionalidad de pause/resume robusta.
```

---

## FASE 4 - OPTIMIZACIONES

### Tarea 4.1: Parallel Execution Service

```
Contexto:
Soy desarrollador de DataMap. Migraciones grandes con muchas tablas independientes tardan mucho ejecutándose secuencialmente. Necesito paralelizar ejecución de tablas sin dependencias entre sí.

Archivo a crear:
`backend/app/services/parallel_execution_service.py`

Dependencia:
```txt
asyncio (built-in Python 3.7+)
aiohttp==3.9.1  # Async HTTP client
aiomysql==0.2.0  # Async MySQL adapter
asyncpg==0.29.0  # Async PostgreSQL adapter
```

Funcionalidad:

1. **Execute Parallel Batch**
```python
import asyncio
import logging
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor

from app.utils.db_adapters.base_adapter import BaseDBAdapter

logger = logging.getLogger(__name__)


class ParallelExecutionService:
    def __init__(self, max_workers: int = 4):
        """
        Args:
            max_workers: Número máximo de tablas a migrar concurrentemente
                        Default: 4 (balance entre speedup y carga en BD)
        """
        self.max_workers = max_workers

    async def execute_parallel_batch(
        self,
        db,
        execution_id: str,
        independent_tables: List[str],
        table_scripts: Dict[str, str],  # {table_name: sql_script}
        dest_adapter: BaseDBAdapter
    ) -> List[Dict[str, Any]]:
        """
        Ejecuta migración de tablas independientes en paralelo

        Args:
            independent_tables: Lista de tablas sin dependencias entre sí
            table_scripts: Scripts SQL individuales por tabla
            dest_adapter: Adapter de BD destino

        Proceso:
        1. Crear pool de workers (max_workers conexiones)
        2. Para cada tabla en independent_tables:
           - Asignar a worker disponible
           - Ejecutar script en conexión separada
           - Trackear progreso
        3. Esperar que todos completen
        4. Agregar resultados

        Returns: Lista de resultados por tabla
        [
            {
                "table_name": "customers",
                "status": "success",
                "rows_migrated": 10000,
                "duration_seconds": 45.2,
                "worker_id": 0
            },
            {
                "table_name": "products",
                "status": "success",
                "rows_migrated": 5000,
                "duration_seconds": 30.1,
                "worker_id": 1
            }
        ]

        Manejo de errores:
        - Si 1 tabla falla: continuar con otras, reportar error al final
        - Si error crítico (conexión): cancelar todas y rollback
        """
        tasks = []

        # Crear conexiones separadas para cada worker
        connections = [
            await self._create_connection(dest_adapter)
            for _ in range(min(self.max_workers, len(independent_tables)))
        ]

        # Crear task por tabla
        for idx, table_name in enumerate(independent_tables):
            worker_id = idx % len(connections)
            connection = connections[worker_id]

            task = asyncio.create_task(
                self._execute_table_migration(
                    table_name=table_name,
                    script=table_scripts[table_name],
                    connection=connection,
                    worker_id=worker_id,
                    execution_id=execution_id
                )
            )
            tasks.append(task)

        # Esperar todos los tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Cerrar conexiones
        for conn in connections:
            await self._close_connection(conn)

        # Procesar resultados
        processed_results = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "table_name": independent_tables[idx],
                    "status": "failed",
                    "error": str(result),
                    "rows_migrated": 0
                })
            else:
                processed_results.append(result)

        return processed_results

    async def _execute_table_migration(
        self,
        table_name: str,
        script: str,
        connection,
        worker_id: int,
        execution_id: str
    ) -> Dict[str, Any]:
        """
        Ejecuta migración de una tabla individual

        Returns:
        {
            "table_name": "customers",
            "status": "success",
            "rows_migrated": 10000,
            "duration_seconds": 45.2,
            "worker_id": 0
        }
        """
        import time

        start_time = time.time()
        logger.info(f"Worker {worker_id} starting migration of table {table_name}")

        try:
            # Ejecutar script
            async with connection.cursor() as cursor:
                await cursor.execute(script)
                rows_affected = cursor.rowcount
                await connection.commit()

            duration = time.time() - start_time
            logger.info(
                f"Worker {worker_id} completed {table_name} - "
                f"{rows_affected} rows in {duration:.2f}s"
            )

            return {
                "table_name": table_name,
                "status": "success",
                "rows_migrated": rows_affected,
                "duration_seconds": round(duration, 2),
                "worker_id": worker_id
            }

        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"Worker {worker_id} failed on {table_name}: {str(e)}"
            )

            # Rollback this connection
            await connection.rollback()

            return {
                "table_name": table_name,
                "status": "failed",
                "error": str(e),
                "rows_migrated": 0,
                "duration_seconds": round(duration, 2),
                "worker_id": worker_id
            }

    async def _create_connection(self, dest_adapter: BaseDBAdapter):
        """
        Crea conexión asíncrona a BD destino

        Adaptadores por dialecto:
        - PostgreSQL: asyncpg.connect()
        - MySQL: aiomysql.connect()
        - SQL Server: aioodbc (no usado comúnmente, fallback a sync)
        - Oracle: cx_Oracle async (complejo, fallback a sync)
        """
        dialect = dest_adapter.dialect.lower()

        if dialect == 'postgresql':
            import asyncpg
            return await asyncpg.connect(
                host=dest_adapter.host,
                port=dest_adapter.port,
                user=dest_adapter.username,
                password=dest_adapter.password,
                database=dest_adapter.database
            )

        elif dialect == 'mysql':
            import aiomysql
            return await aiomysql.connect(
                host=dest_adapter.host,
                port=dest_adapter.port,
                user=dest_adapter.username,
                password=dest_adapter.password,
                db=dest_adapter.database
            )

        else:
            # Fallback: usar ThreadPoolExecutor para dialectos sin async
            raise NotImplementedError(
                f"Async adapter not implemented for {dialect}. "
                f"Use sequential execution for this database."
            )

    async def _close_connection(self, connection):
        """Cierra conexión asíncrona"""
        await connection.close()

    def calculate_optimal_workers(
        self,
        num_independent_tables: int,
        dest_db_max_connections: int = 100
    ) -> int:
        """
        Calcula número óptimo de workers

        Factores:
        - Número de tablas independientes
        - Max connections de BD destino
        - CPU cores disponibles

        Heurística:
        - Min: 1
        - Max: min(num_tables, max_connections / 2, cpu_cores)
        - Default: 4
        """
        import multiprocessing

        cpu_cores = multiprocessing.cpu_count()
        safe_max_connections = max(1, dest_db_max_connections // 2)

        optimal = min(
            num_independent_tables,
            safe_max_connections,
            cpu_cores,
            self.max_workers  # No exceder configurado
        )

        return max(1, optimal)
```

2. **Integration with Execution Service**

Modificar `backend/app/services/execution_service.py`:
```python
from app.services.parallel_execution_service import ParallelExecutionService

class ExecutionService:
    def __init__(self):
        self.parallel_service = ParallelExecutionService(max_workers=4)

    def execute_migration(
        self,
        db,
        project_id: str,
        script: str,
        dest_adapter: BaseDBAdapter,
        dry_run: bool = False,
        enable_parallel: bool = True  # NUEVO
    ) -> Dict[str, Any]:
        """
        Si enable_parallel=True y hay tablas independientes:
        - Ejecutar en paralelo
        Sino:
        - Ejecutar secuencialmente
        """

        # Obtener dependency graph
        from app.services.dependency_graph_service import DependencyGraphService
        dep_service = DependencyGraphService()
        dep_graph = dep_service.build_dependency_graph(db, project_id)

        # Identificar batches paralelos
        independent_batches = dep_graph.get('independent_tables', [])

        if enable_parallel and independent_batches:
            # Ejecutar batches en paralelo
            for batch in independent_batches:
                results = asyncio.run(
                    self.parallel_service.execute_parallel_batch(
                        db,
                        execution_id,
                        batch,
                        table_scripts,
                        dest_adapter
                    )
                )
                # Procesar resultados...
        else:
            # Ejecutar secuencialmente
            # ... código existente
```

API Endpoint:
```python
# En migration.py
@router.post("/api/projects/{project_id}/migration/execute")
async def execute_migration(
    project_id: str,
    options: ExecutionOptions,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Request body:
    {
        "script_id": "uuid",
        "dry_run": false,
        "dest_session_id": "uuid",
        "enable_parallel": true,  # NUEVO
        "max_workers": 4  # NUEVO, opcional
    }
    """
```

Actualizar modelo:
```python
class ExecutionOptions(BaseModel):
    script_id: str
    dry_run: bool = False
    dest_session_id: str
    enable_parallel: bool = True
    max_workers: int = 4
```

Tests:
`backend/test/unit/services/test_parallel_execution_service.py`
1. test_execute_parallel_batch_success
2. test_execute_parallel_batch_partial_failure
3. test_calculate_optimal_workers
4. test_async_connection_creation_postgres
5. test_async_connection_creation_mysql

Warnings para documentar:
1. Parallel execution aumenta carga en BD
2. Riesgo de deadlocks si tablas comparten recursos
3. No todos los dialectos soportan async (SQL Server, Oracle)
4. Recomendado solo para tablas verdaderamente independientes

Por favor implementa este servicio con cuidado en manejo de errores async.
```

---

### Tarea 4.2: Bulk Operations Enhancement

```
Contexto:
Soy desarrollador de DataMap. INSERT INTO...SELECT row-by-row es lento para tablas grandes (millones de filas). Necesito usar operaciones bulk específicas de cada dialecto para 10x+ speedup.

Archivo a modificar:
`backend/app/services/migration_script_service.py` (ya existe)

Métodos a agregar:

1. **Generate Bulk Insert**
```python
def _generate_bulk_insert(
    self,
    dialect: str,
    table_name: str,
    columns: List[str],
    select_clause: str,
    origin_connection_string: str
) -> str:
    """
    Genera SQL de bulk insert optimizado por dialecto

    PostgreSQL: COPY
    -----------
    Fastest method (5-10x faster than INSERT)

    ```sql
    -- Opción 1: COPY FROM stdin (requiere datos en memoria)
    COPY dest_table (col1, col2, col3)
    FROM stdin
    WITH (FORMAT csv, DELIMITER ',', NULL '\\N');

    -- Opción 2: COPY FROM program (ejecuta query origen)
    COPY dest_table (col1, col2, col3)
    FROM PROGRAM 'psql origin_db -c "SELECT col1, col2, col3 FROM origin_table" -t -A -F","'
    WITH (FORMAT csv);
    ```

    MySQL: LOAD DATA INFILE
    -----------------------
    10x faster than INSERT

    ```sql
    -- Requiere exportar primero a CSV
    SELECT col1, col2, col3
    INTO OUTFILE '/tmp/export.csv'
    FIELDS TERMINATED BY ','
    LINES TERMINATED BY '\\n'
    FROM origin_table;

    -- Luego cargar
    LOAD DATA INFILE '/tmp/export.csv'
    INTO TABLE dest_table
    FIELDS TERMINATED BY ','
    LINES TERMINATED BY '\\n'
    (col1, col2, col3);
    ```

    SQL Server: BULK INSERT
    -----------------------
    15x faster than INSERT

    ```sql
    -- Requiere BCP export primero
    bcp origin_db.dbo.origin_table out /tmp/export.dat -c -t, -T

    -- Luego bulk insert
    BULK INSERT dest_table
    FROM '/tmp/export.dat'
    WITH (
        FIELDTERMINATOR = ',',
        ROWTERMINATOR = '\\n',
        FIRSTROW = 1
    );
    ```

    Oracle: SQL*Loader hints
    ------------------------
    Append hint + PARALLEL

    ```sql
    INSERT /*+ APPEND PARALLEL(4) */ INTO dest_table
    SELECT /*+ PARALLEL(4) */ col1, col2, col3
    FROM origin_table@dblink;
    ```

    Fallback: Batched INSERT
    ------------------------
    Si bulk no disponible, usar batches grandes

    ```sql
    INSERT INTO dest_table (col1, col2, col3)
    SELECT col1, col2, col3
    FROM origin_table
    LIMIT 10000 OFFSET 0;

    INSERT INTO dest_table (col1, col2, col3)
    SELECT col1, col2, col3
    FROM origin_table
    LIMIT 10000 OFFSET 10000;
    -- etc.
    ```
    """

    if dialect == 'postgresql':
        return self._generate_postgres_copy(
            table_name, columns, select_clause, origin_connection_string
        )

    elif dialect == 'mysql':
        return self._generate_mysql_load_data(
            table_name, columns, select_clause
        )

    elif dialect == 'sqlserver':
        return self._generate_sqlserver_bulk_insert(
            table_name, columns, select_clause
        )

    elif dialect == 'oracle':
        return self._generate_oracle_append_hint(
            table_name, columns, select_clause
        )

    else:
        # Fallback: batched insert
        return self._generate_batched_insert(
            table_name, columns, select_clause, batch_size=10000
        )
```

2. **PostgreSQL COPY**
```python
def _generate_postgres_copy(
    self,
    table_name: str,
    columns: List[str],
    select_clause: str,
    origin_connection_string: str
) -> str:
    """
    Genera script usando PostgreSQL COPY

    Estrategia 1: Foreign Data Wrapper (FDW) - Best
    ------------------------------------------------
    Si origen también es PostgreSQL:

    ```sql
    -- Setup (one-time)
    CREATE EXTENSION IF NOT EXISTS postgres_fdw;

    CREATE SERVER origin_server
    FOREIGN DATA WRAPPER postgres_fdw
    OPTIONS (host 'origin_host', dbname 'origin_db', port '5432');

    CREATE USER MAPPING FOR CURRENT_USER
    SERVER origin_server
    OPTIONS (user 'origin_user', password 'origin_pass');

    -- Migration
    COPY dest_table (col1, col2, col3)
    FROM (SELECT col1, col2, col3 FROM origin_schema.origin_table)
    WITH (FORMAT binary);
    ```

    Estrategia 2: CSV intermediario
    --------------------------------
    ```sql
    -- En origen: exportar a CSV
    \\COPY (SELECT col1, col2, col3 FROM origin_table) TO '/tmp/export.csv' WITH CSV;

    -- En destino: importar
    \\COPY dest_table (col1, col2, col3) FROM '/tmp/export.csv' WITH CSV;
    ```
    """
```

3. **MySQL LOAD DATA**
```python
def _generate_mysql_load_data(
    self,
    table_name: str,
    columns: List[str],
    select_clause: str
) -> str:
    """
    Genera script usando MySQL LOAD DATA INFILE

    ```sql
    -- Step 1: Export from origin
    SELECT {select_clause}
    INTO OUTFILE '/var/lib/mysql-files/migration_temp.csv'
    FIELDS TERMINATED BY ','
    ENCLOSED BY '\"'
    LINES TERMINATED BY '\\n'
    FROM {origin_table};

    -- Step 2: Load to destination
    LOAD DATA INFILE '/var/lib/mysql-files/migration_temp.csv'
    INTO TABLE {dest_table}
    FIELDS TERMINATED BY ','
    ENCLOSED BY '\"'
    LINES TERMINATED BY '\\n'
    ({column_list});

    -- Step 3: Cleanup
    -- (file deleted by mysql automatically or manually)
    ```

    Nota: Requiere FILE privilege
    GRANT FILE ON *.* TO migration_user;
    """
```

4. **Detect Bulk Availability**
```python
def can_use_bulk_operations(
    self,
    origin_adapter: BaseDBAdapter,
    dest_adapter: BaseDBAdapter
) -> Dict[str, Any]:
    """
    Detecta si bulk operations están disponibles

    Checks:
    1. Dialect soporta bulk? (PostgreSQL COPY, MySQL LOAD DATA, etc.)
    2. Usuario tiene permisos? (FILE privilege, etc.)
    3. Filesystem compartido? (para CSV intermediario)
    4. Same-host migration? (puede usar pipes)

    Returns:
    {
        "can_use_bulk": True,
        "method": "postgresql_copy",  # o "mysql_load_data", "batched_insert"
        "estimated_speedup": "5-10x",
        "requirements": [
            "postgres_fdw extension must be enabled",
            "User needs USAGE privilege on foreign server"
        ],
        "fallback_available": True
    }
    """
```

Modificar `generate_migration_script`:
```python
def generate_migration_script(
    self,
    db: Session,
    project_id: str,
    options: Dict[str, Any]
) -> str:
    """
    Agregar opción use_bulk_operations

    if options.get('use_bulk_operations', False):
        # Usar bulk
        script = self._generate_bulk_insert(...)
    else:
        # Usar INSERT...SELECT normal
        script = self._generate_insert_select(...)
    """
```

API Changes:
```python
# En migration.py
@router.post("/api/projects/{project_id}/migration/generate-script")
async def generate_migration_script(
    project_id: str,
    options: ScriptGenerationOptions,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Request body:
    {
        "batch_size": 10000,
        "include_constraints": true,
        "use_bulk_operations": true,  # NUEVO
        "bulk_temp_directory": "/tmp"  # NUEVO, opcional
    }
    """

@router.get("/api/projects/{project_id}/migration/bulk-availability")
async def check_bulk_availability(
    project_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Verifica si bulk operations están disponibles

    Response: can_use_bulk_operations() result
    """
```

Tests:
`backend/test/unit/services/test_migration_script_service.py`
1. test_generate_postgres_copy
2. test_generate_mysql_load_data
3. test_generate_sqlserver_bulk_insert
4. test_generate_oracle_append_hint
5. test_can_use_bulk_operations_postgres
6. test_fallback_to_batched_insert

Warnings:
1. Bulk operations requieren permisos especiales
2. CSV intermediario requiere espacio en disco
3. LOAD DATA INFILE puede ser deshabilitado por seguridad
4. Testing exhaustivo requerido (más complejo que INSERT)

Por favor implementa con fallbacks robustos si bulk no disponible.
```

---

### Tarea 4.3: Performance Monitoring Service

```
Contexto:
Soy desarrollador de DataMap. Necesito medir performance de migraciones (rows/sec, memory, CPU) para identificar bottlenecks y optimizar.

Archivo a crear:
`backend/app/services/performance_monitor_service.py`

Dependencia ya agregada en Fase 1:
```txt
psutil==5.9.6  # CPU, memory, disk monitoring
```

Nueva tabla DB:
`backend/utilities/migrations/009_performance_metrics.sql`
```sql
CREATE TABLE migration_performance_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    execution_id UUID NOT NULL REFERENCES migration_executions(id) ON DELETE CASCADE,
    table_name VARCHAR(255),
    metric_type VARCHAR(50) NOT NULL,  -- throughput, cpu, memory, disk_io
    value NUMERIC(20, 5) NOT NULL,
    unit VARCHAR(20) NOT NULL,  -- rows/sec, MB, percent, MB/s
    recorded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    metadata JSONB  -- Contexto adicional
);

CREATE INDEX idx_perf_metrics_execution ON migration_performance_metrics(execution_id);
CREATE INDEX idx_perf_metrics_table ON migration_performance_metrics(table_name);
CREATE INDEX idx_perf_metrics_type ON migration_performance_metrics(metric_type);
CREATE INDEX idx_perf_metrics_time ON migration_performance_metrics(recorded_at);
```

Funcionalidad:

1. **Record Metrics**
```python
import psutil
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class PerformanceMonitorService:
    def __init__(self):
        self.process = psutil.Process()
        self.start_metrics = None

    def start_monitoring(self) -> None:
        """
        Captura métricas iniciales

        Baseline:
        - CPU percent
        - Memory usage (RSS)
        - Disk I/O counters
        - Network I/O counters
        - Timestamp
        """
        self.start_metrics = {
            'cpu_percent': self.process.cpu_percent(interval=0.1),
            'memory_mb': self.process.memory_info().rss / 1024 / 1024,
            'disk_io': psutil.disk_io_counters(),
            'net_io': psutil.net_io_counters(),
            'timestamp': datetime.utcnow()
        }

    def record_table_metrics(
        self,
        db: Session,
        execution_id: str,
        table_name: str,
        rows_migrated: int,
        duration_seconds: float
    ) -> None:
        """
        Registra métricas de una tabla migrada

        Métricas:
        1. Throughput: rows/second
        2. Duration: seconds
        3. CPU usage: percent
        4. Memory usage: MB
        5. Disk I/O: MB read + written
        """

        # Throughput
        throughput = rows_migrated / duration_seconds if duration_seconds > 0 else 0
        self._save_metric(
            db, execution_id, table_name,
            metric_type='throughput',
            value=throughput,
            unit='rows/sec'
        )

        # Duration
        self._save_metric(
            db, execution_id, table_name,
            metric_type='duration',
            value=duration_seconds,
            unit='seconds'
        )

        # CPU usage
        cpu_percent = self.process.cpu_percent(interval=0.1)
        self._save_metric(
            db, execution_id, table_name,
            metric_type='cpu',
            value=cpu_percent,
            unit='percent'
        )

        # Memory usage
        memory_mb = self.process.memory_info().rss / 1024 / 1024
        self._save_metric(
            db, execution_id, table_name,
            metric_type='memory',
            value=memory_mb,
            unit='MB'
        )

    def analyze_performance(
        self,
        db: Session,
        execution_id: str
    ) -> Dict[str, Any]:
        """
        Analiza métricas de ejecución completa

        Returns:
        {
            "execution_id": "uuid",
            "total_duration_seconds": 180.5,
            "total_rows_migrated": 1000000,
            "avg_throughput_rows_per_sec": 5540.17,
            "peak_memory_mb": 512.3,
            "avg_cpu_percent": 65.2,
            "slowest_tables": [
                {
                    "table_name": "huge_logs",
                    "rows": 500000,
                    "duration_seconds": 120.0,
                    "throughput": 4166.67
                },
                ...
            ],
            "fastest_tables": [
                {
                    "table_name": "small_config",
                    "rows": 100,
                    "duration_seconds": 0.5,
                    "throughput": 200.0
                },
                ...
            ],
            "bottlenecks": [
                {
                    "type": "slow_throughput",
                    "table": "huge_logs",
                    "description": "Throughput 50% below average",
                    "suggestion": "Consider indexing or parallel execution"
                },
                {
                    "type": "high_memory",
                    "description": "Peak memory usage 512 MB",
                    "suggestion": "Reduce batch size or enable streaming"
                }
            ],
            "recommendations": [
                "Enable parallel execution for independent tables",
                "Use bulk operations (COPY/LOAD DATA) for large tables",
                "Increase batch size from 10K to 50K rows"
            ]
        }
        """

        # Query all metrics for execution
        metrics = self._get_execution_metrics(db, execution_id)

        # Calculate aggregates
        total_duration = sum(m['duration'] for m in metrics if m['metric_type'] == 'duration')
        total_rows = sum(m['rows'] for m in metrics if 'rows' in m)
        avg_throughput = total_rows / total_duration if total_duration > 0 else 0

        peak_memory = max(
            m['value'] for m in metrics if m['metric_type'] == 'memory'
        ) if metrics else 0

        avg_cpu = sum(
            m['value'] for m in metrics if m['metric_type'] == 'cpu'
        ) / len([m for m in metrics if m['metric_type'] == 'cpu']) if metrics else 0

        # Identify slowest/fastest tables
        table_performances = self._calculate_table_performances(metrics)
        slowest = sorted(table_performances, key=lambda x: x['throughput'])[:5]
        fastest = sorted(table_performances, key=lambda x: x['throughput'], reverse=True)[:5]

        # Detect bottlenecks
        bottlenecks = self._detect_bottlenecks(
            table_performances, avg_throughput, peak_memory, avg_cpu
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(bottlenecks, table_performances)

        return {
            "execution_id": execution_id,
            "total_duration_seconds": round(total_duration, 2),
            "total_rows_migrated": total_rows,
            "avg_throughput_rows_per_sec": round(avg_throughput, 2),
            "peak_memory_mb": round(peak_memory, 2),
            "avg_cpu_percent": round(avg_cpu, 2),
            "slowest_tables": slowest,
            "fastest_tables": fastest,
            "bottlenecks": bottlenecks,
            "recommendations": recommendations
        }

    def _detect_bottlenecks(
        self,
        table_performances: List[Dict],
        avg_throughput: float,
        peak_memory: float,
        avg_cpu: float
    ) -> List[Dict[str, Any]]:
        """
        Detecta bottlenecks automáticamente

        Reglas:
        1. Tabla con throughput < 50% del avg → slow_throughput
        2. Peak memory > 1GB → high_memory
        3. Avg CPU > 80% → cpu_bound
        4. Avg CPU < 20% → io_bound
        5. Tabla con >1M rows y sin bulk → should_use_bulk
        """
        bottlenecks = []

        # Slow throughput tables
        for perf in table_performances:
            if perf['throughput'] < avg_throughput * 0.5:
                bottlenecks.append({
                    "type": "slow_throughput",
                    "table": perf['table_name'],
                    "description": f"Throughput {perf['throughput']:.2f} is 50% below average {avg_throughput:.2f}",
                    "suggestion": "Consider indexing, parallel execution, or bulk operations"
                })

        # High memory
        if peak_memory > 1024:  # > 1GB
            bottlenecks.append({
                "type": "high_memory",
                "description": f"Peak memory usage {peak_memory:.2f} MB",
                "suggestion": "Reduce batch size or enable streaming mode"
            })

        # CPU bound
        if avg_cpu > 80:
            bottlenecks.append({
                "type": "cpu_bound",
                "description": f"Average CPU {avg_cpu:.2f}% indicates CPU bottleneck",
                "suggestion": "Reduce parallel workers or optimize transformations"
            })

        # I/O bound
        if avg_cpu < 20:
            bottlenecks.append({
                "type": "io_bound",
                "description": f"Average CPU {avg_cpu:.2f}% indicates I/O bottleneck",
                "suggestion": "Enable parallel execution or use faster storage"
            })

        return bottlenecks

    def _generate_recommendations(
        self,
        bottlenecks: List[Dict],
        table_performances: List[Dict]
    ) -> List[str]:
        """
        Genera recomendaciones basadas en bottlenecks
        """
        recommendations = []

        # Si hay tablas lentas
        slow_tables = [b for b in bottlenecks if b['type'] == 'slow_throughput']
        if slow_tables:
            recommendations.append(
                "Enable bulk operations (PostgreSQL COPY, MySQL LOAD DATA) for large tables"
            )

        # Si hay alta memoria
        if any(b['type'] == 'high_memory' for b in bottlenecks):
            recommendations.append(
                "Reduce batch size from current setting to limit memory usage"
            )

        # Si es CPU bound
        if any(b['type'] == 'cpu_bound' for b in bottlenecks):
            recommendations.append(
                "Reduce parallel workers to decrease CPU load"
            )

        # Si es I/O bound
        if any(b['type'] == 'io_bound' for b in bottlenecks):
            recommendations.append(
                "Enable parallel execution for independent tables to maximize I/O throughput"
            )

        # Si hay muchas tablas independientes
        if len(table_performances) > 5:
            recommendations.append(
                "Consider migrating independent tables in parallel batches"
            )

        return recommendations

    def _save_metric(
        self,
        db: Session,
        execution_id: str,
        table_name: Optional[str],
        metric_type: str,
        value: float,
        unit: str,
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Guarda métrica en DB
        """
        db.execute(
            """
            INSERT INTO migration_performance_metrics
            (execution_id, table_name, metric_type, value, unit, metadata)
            VALUES (:execution_id, :table_name, :metric_type, :value, :unit, :metadata)
            """,
            {
                "execution_id": execution_id,
                "table_name": table_name,
                "metric_type": metric_type,
                "value": value,
                "unit": unit,
                "metadata": metadata
            }
        )
        db.commit()

    def _get_execution_metrics(
        self,
        db: Session,
        execution_id: str
    ) -> List[Dict[str, Any]]:
        """
        Obtiene todas las métricas de una ejecución
        """
        result = db.execute(
            """
            SELECT table_name, metric_type, value, unit, recorded_at, metadata
            FROM migration_performance_metrics
            WHERE execution_id = :execution_id
            ORDER BY recorded_at
            """,
            {"execution_id": execution_id}
        ).fetchall()

        return [
            {
                "table_name": row[0],
                "metric_type": row[1],
                "value": row[2],
                "unit": row[3],
                "recorded_at": row[4],
                "metadata": row[5]
            }
            for row in result
        ]

    def _calculate_table_performances(
        self,
        metrics: List[Dict]
    ) -> List[Dict[str, Any]]:
        """
        Calcula performance por tabla
        """
        # Group by table
        by_table = {}
        for m in metrics:
            table = m['table_name']
            if table not in by_table:
                by_table[table] = {}
            by_table[table][m['metric_type']] = m['value']

        # Calculate throughput
        performances = []
        for table, metrics_dict in by_table.items():
            if 'throughput' in metrics_dict and 'duration' in metrics_dict:
                performances.append({
                    "table_name": table,
                    "throughput": metrics_dict['throughput'],
                    "duration_seconds": metrics_dict['duration'],
                    "rows": int(metrics_dict['throughput'] * metrics_dict['duration'])
                })

        return performances
```

API Endpoints:
```python
# En migration.py
@router.get("/api/projects/{project_id}/migration/executions/{execution_id}/performance")
async def get_performance_analysis(
    project_id: str,
    execution_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Retorna análisis de performance de una ejecución

    Response: analyze_performance() result
    """

@router.get("/api/projects/{project_id}/migration/executions/{execution_id}/metrics")
async def get_raw_metrics(
    project_id: str,
    execution_id: str,
    metric_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Retorna métricas raw para gráficos

    Query params:
    - metric_type: throughput, cpu, memory, disk_io (optional filter)

    Response:
    {
        "metrics": [
            {
                "table_name": "customers",
                "metric_type": "throughput",
                "value": 5540.17,
                "unit": "rows/sec",
                "recorded_at": "2025-01-16T14:30:00Z"
            },
            ...
        ]
    }
    """
```

Tests:
`backend/test/unit/services/test_performance_monitor_service.py`
1. test_record_table_metrics
2. test_analyze_performance
3. test_detect_bottlenecks_slow_throughput
4. test_detect_bottlenecks_high_memory
5. test_generate_recommendations

Integration:
Modificar `execution_service.py` para usar monitor:
```python
from app.services.performance_monitor_service import PerformanceMonitorService

class ExecutionService:
    def __init__(self):
        self.perf_monitor = PerformanceMonitorService()

    def execute_migration(self, ...):
        # Start monitoring
        self.perf_monitor.start_monitoring()

        # Execute tables
        for table in tables:
            start = time.time()
            rows = migrate_table(table)
            duration = time.time() - start

            # Record metrics
            self.perf_monitor.record_table_metrics(
                db, execution_id, table, rows, duration
            )
```

Por favor implementa este servicio de monitoring completo.
```

---

## 🎉 DOCUMENTACIÓN COMPLETA

**Todos los prompts han sido generados**:
- ✅ Fase 1: 6 tareas (PROMPTS_TAREAS_INDIVIDUALES.md)
- ✅ Fase 2: 4 tareas (PROMPTS_FASE_2_3_4.md)
- ✅ Fase 3: 3 tareas (PROMPTS_FASE_2_3_4.md)
- ✅ Fase 4: 3 tareas (PROMPTS_FASE_2_3_4.md)

**Total**: 16 prompts copy-paste listos para implementación

**Próximos pasos**:
1. Revisar README_PLANES.md para workflow de implementación
2. Empezar con Tarea 1.1 (Dependency Graph Service)
3. Seguir orden secuencial: 1.1 → 1.2 → ... → 4.3
4. Marcar checkboxes en PLAN_MIGRACION_ENTERPRISE.md al completar

¡Buena suerte con la implementación! 🚀
