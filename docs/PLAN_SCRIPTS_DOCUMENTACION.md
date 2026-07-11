# Plan: Scripts y Documentación para Maximizar Valor del Producto

**Fecha de creación**: 2025-01-16
**Estado**: Análisis completado - Pendiente decisión final
**Contexto**: Plan original previo a la definición de MVP

---

## 📋 Resumen Ejecutivo

Este documento representa el análisis inicial sobre qué scripts y documentación debería generar DataMap para aportar máximo valor. **Nota**: Este plan fue refinado posteriormente en `PLAN_MIGRACION_ENTERPRISE.md` enfocándose en el MVP crítico para demos.

---

## 🎯 Objetivo Original

Determinar qué scripts de migración y documentación debería generar automáticamente DataMap para consultoras que realizan migraciones de bases de datos.

---

## 📊 Análisis de Situación

### Capacidades Existentes
✅ Generación básica INSERT INTO ... SELECT
✅ Soporte multi-BD (PostgreSQL, MySQL, SQL Server, Oracle)
✅ Validación de tipos con matriz de compatibilidad
✅ Encriptación AES-256-GCM
✅ Modo híbrido (import + connector)
✅ Rollback manual
✅ Logs de auditoría
✅ Exportación JSON/CSV/Excel

### Gaps Identificados
❌ Sin transacciones (BEGIN/COMMIT/ROLLBACK)
❌ Sin batching para datasets grandes
❌ Sin transformaciones (CAST, CONCAT, etc.)
❌ Sin validación pre/post migración
❌ Sin optimizaciones por dialecto (COPY, BULK INSERT)
❌ Sin manejo de constraints (FK disable/enable)
❌ Sin estimación de tiempos
❌ Sin integración Liquibase/Flyway/dbt
❌ Sin modo dry-run
❌ Sin paralelización

---

## 🔍 Análisis de Necesidades de Consultoras

### Tipos de Migraciones
1. **Migraciones one-time masivas** (Oracle legacy → PostgreSQL moderno)
2. **Migraciones incrementales** (sincronización continua)
3. **Migraciones con transformación** (cambios de estructura, normalización)
4. **Migraciones con validación** (integridad referencial)

### Complejidad de Transformaciones
- Mapeos 1:1 simples
- Transformaciones complejas: CONCAT, CAST, CASE WHEN
- Conversión de tipos incompatibles
- Lookups a tablas de referencia

### Tamaños de Dataset
- **Pequeñas** (<100K filas): Script monolítico OK
- **Medianas** (100K-10M): Batching necesario
- **Grandes** (>10M): Paralelización + streaming

### Escenarios de Error
- Transacciones atómicas (todo o nada)
- Checkpointing (reanudar desde fallo)
- Logs detallados de filas fallidas

---

## 💡 PARTE 1: Scripts de Migración Propuestos

### 1.1 Script Enterprise Completo

**Componentes**:

#### A. Wrapper de Transacciones
```python
class TransactionWrapper:
    def generate(dialect: str, isolation_level: str):
        # PostgreSQL: BEGIN; ... COMMIT;
        # SQL Server: BEGIN TRANSACTION ... COMMIT TRANSACTION
        # MySQL: START TRANSACTION ... COMMIT
        # Oracle: SET TRANSACTION ... COMMIT
```

#### B. Batching Configurable
```python
class BatchGenerator:
    def generate_batched_inserts(
        mappings: List,
        batch_size: int = 1000,
        use_bulk_optimization: bool = True
    ):
        # Genera INSERTs con LIMIT/OFFSET
        # O usa COPY/BULK INSERT/LOAD DATA
```

#### C. Manejo de Constraints
```python
class ConstraintManager:
    def generate_disable_constraints():
        # PostgreSQL: ALTER TABLE ... DISABLE TRIGGER ALL
        # SQL Server: ALTER TABLE ... NOCHECK CONSTRAINT ALL
        # MySQL: SET FOREIGN_KEY_CHECKS=0

    def generate_enable_constraints():
        # Re-habilita con validación
```

#### D. Error Handling por Dialecto
```python
class ErrorHandler:
    def wrap_with_error_handling(sql: str, dialect: str):
        # PostgreSQL: BEGIN; ... EXCEPTION WHEN ... END;
        # SQL Server: BEGIN TRY ... END TRY BEGIN CATCH ... END CATCH
```

#### E. Logging y Monitoreo
```python
class MigrationLogger:
    def generate_logging_statements():
        # Tabla de log temporal
        # Timestamps por paso
        # Cuenta filas procesadas/fallidas
        # Reporte final
```

**Estructura del Script Generado**:
```sql
-- ========================================
-- MIGRATION SCRIPT
-- Generated: 2025-01-16 14:30:00 UTC
-- Project: Customer DB Migration
-- Estimated time: 45 minutes
-- Estimated rows: 2.5M
-- ========================================

-- SECTION 1: Pre-Migration Validation
-- [Validación de constraints, NULLs, tipos]

-- SECTION 2: Backup Creation
CREATE TABLE customers_backup AS SELECT * FROM customers;

-- SECTION 3: Environment Setup
SET FOREIGN_KEY_CHECKS=0;
ALTER TABLE orders DISABLE TRIGGER ALL;

-- SECTION 4: Transaction Start
BEGIN TRANSACTION;

-- SECTION 5: Data Migration (Batched)
-- Batch 1/10 (rows 1-1000)
INSERT INTO customers_new SELECT * FROM customers LIMIT 1000 OFFSET 0;

-- SECTION 6: Post-Migration Validation
SELECT COUNT(*) FROM customers_new; -- Expected: 10000

-- SECTION 7: Environment Restore
SET FOREIGN_KEY_CHECKS=1;

-- SECTION 8: Transaction Commit
COMMIT;

-- SECTION 9: Cleanup (Optional)
-- DROP TABLE customers_backup;
```

---

### 1.2 Script de Transformaciones Complejas

**Motor de Transformaciones**:
```python
class TransformationEngine:
    SUPPORTED_FUNCTIONS = {
        'string': ['UPPER', 'LOWER', 'TRIM', 'CONCAT', 'SUBSTRING', 'REPLACE'],
        'numeric': ['ROUND', 'CEIL', 'FLOOR', 'ABS', 'CAST'],
        'date': ['DATE', 'TIMESTAMP', 'DATE_ADD', 'EXTRACT'],
        'conditional': ['CASE WHEN', 'COALESCE', 'NULLIF'],
        'aggregate': ['SUM', 'AVG', 'COUNT']
    }

    def parse_transformation(expression: str):
        # "UPPER(CONCAT(first_name, ' ', last_name))"
        # Valida sintaxis
        # Genera SQL por dialecto
```

**Ejemplo**:
```sql
INSERT INTO users_new (full_name)
SELECT CONCAT(first_name, ' ', last_name) FROM users;
```

---

### 1.3 Script de Validación Pre-Migración

**Validaciones**:

#### A. Integridad Referencial
```python
class ReferentialIntegrityValidator:
    def validate_foreign_keys():
        # Verifica FK targets existan
        # Genera reporte de FK huérfanos
        # Sugiere orden de migración
```

#### B. Calidad de Datos
```python
class DataQualityValidator:
    def check_nullability():
        # Campos NOT NULL sin NULLs

    def check_data_truncation():
        # VARCHAR(255) → VARCHAR(100) con datos >100

    def check_numeric_overflow():
        # INTEGER → SMALLINT fuera de rango

    def check_unique_constraints():
        # Campos UNIQUE sin duplicados
```

**Salida**:
```json
{
    "validation_report": {
        "passed": 120,
        "warnings": 8,
        "errors": 2,
        "checks": [
            {
                "type": "data_truncation",
                "severity": "warning",
                "mapping": "users.description → users_new.description",
                "issue": "5 rows exceed VARCHAR(100) limit",
                "affected_rows": [1234, 5678],
                "suggestion": "Increase to VARCHAR(255) or truncate"
            }
        ]
    }
}
```

---

### 1.4 Script de Validación Post-Migración

**Verificaciones**:

#### A. Row Count Verification
```python
class RowCountValidator:
    def compare_counts(origin, dest, mappings):
        # SELECT COUNT(*) FROM origin
        # SELECT COUNT(*) FROM dest
        # Reporte discrepancias
```

#### B. Data Integrity Checks
```python
class DataIntegrityValidator:
    def verify_primary_keys():
        # No PKs duplicados

    def verify_foreign_keys():
        # Todas FK válidas

    def verify_constraints():
        # UNIQUE, CHECK constraints
```

**Salida**:
```sql
-- POST-MIGRATION VALIDATION REPORT

-- Row Count Validation
SELECT 'customers (origin)', COUNT(*) FROM customers;  -- 10000
SELECT 'customers_new (dest)', COUNT(*) FROM customers_new;  -- 10000
-- ✓ PASS

-- Primary Key Validation
SELECT COUNT(*) FROM (
    SELECT customer_id, COUNT(*) FROM customers_new
    GROUP BY customer_id HAVING COUNT(*) > 1
);
-- Expected: 0, Actual: 0
-- ✓ PASS

-- VALIDATION SUMMARY
-- Checks: 15
-- Passed: 14
-- Failed: 1 (Warning)
```

---

### 1.5 Script de Rollback Automático

```python
class RollbackGenerator:
    def generate_rollback_script(migration_script, backup_tables):
        """
        1. DROP tablas nuevas
        2. RENAME backups a originales
        3. Restaurar constraints
        """
```

**Ejemplo**:
```sql
-- ROLLBACK SCRIPT
BEGIN TRANSACTION;

DROP TABLE IF EXISTS customers_new;
ALTER TABLE customers_backup RENAME TO customers;
ALTER TABLE orders ADD CONSTRAINT fk_customer ...;

COMMIT;
```

---

### 1.6 Script de Estimación de Tiempos

```python
class MigrationEstimator:
    def estimate_execution_time(
        row_count: int,
        column_count: int,
        has_indexes: bool,
        batch_size: int,
        dialect: str
    ) -> Dict:
        """
        Benchmarks por dialecto:
        - PostgreSQL: ~1000 rows/sec
        - MySQL: ~800 rows/sec
        - SQL Server: ~900 rows/sec

        Returns:
        {
            "estimated_time_seconds": 2700,
            "estimated_time_formatted": "45 minutes",
            "breakdown": {
                "data_copy": "35 min",
                "constraint_validation": "8 min",
                "index_rebuild": "2 min"
            },
            "confidence": "medium"
        }
        """
```

---

### 1.7 Generadores por Herramienta

#### A. Liquibase Exporter
```python
class LiquibaseExporter:
    def export_to_xml(mappings) -> str:
        """
        <changeSet id="1" author="datamap">
            <createTable tableName="customers_new">
                <column name="id" type="INT"/>
            </createTable>
            <insert tableName="customers_new">
                <column name="id" valueComputed="(SELECT id FROM customers)"/>
            </insert>
        </changeSet>
        """
```

#### B. Flyway Exporter
```python
class FlywayExporter:
    def export_to_sql(mappings) -> str:
        """
        -- V1__migrate_customers.sql
        [SQL con convenciones Flyway]
        """
```

#### C. dbt Exporter
```python
class DbtExporter:
    def export_to_yml(mappings) -> str:
        """
        models:
          - name: customers_new
            columns:
              - name: id
                tests:
                  - unique
                  - not_null
        """
```

---

## 📚 PARTE 2: Documentación Enterprise

### 2.1 Plan de Ejecución de Migración

**Template**: `EXECUTION_PLAN_TEMPLATE.md`

```markdown
# Plan de Ejecución de Migración

## 1. Información del Proyecto
- Nombre: [...]
- Cliente: [...]
- Fecha: [...]

## 2. Resumen Ejecutivo
- Objetivo: Migrar de [origen] a [destino]
- Tablas: [N]
- Filas: [N millones]
- Tiempo estimado: [X horas]

## 3. Análisis de Dependencias
### Orden de Migración
1. customers (sin FK)
2. orders (FK a customers)
3. order_items (FK a orders)

### Grafo de Dependencias
[Diagrama Mermaid]

## 4. Recursos Requeridos
- CPU: [...]
- Memoria: [...]
- Storage: [...]

## 5. Checklist Pre-Migración
- [ ] Backup completo
- [ ] Validación integridad
- [ ] Dry-run exitoso
- [ ] Equipo notificado

## 6. Checklist Post-Migración
- [ ] Row counts coinciden
- [ ] Primary keys validados
- [ ] Foreign keys validados
```

---

### 2.2 Matriz de Compatibilidad de Tipos

**Template**: `TYPE_COMPATIBILITY_MATRIX.md`

```markdown
# Matriz de Compatibilidad de Tipos

## PostgreSQL → MySQL

| Origen | Destino | Seguridad | Notas |
|--------|---------|-----------|-------|
| VARCHAR(255) | VARCHAR(255) | ✅ SAFE | Conversión directa |
| VARCHAR(255) | VARCHAR(100) | ⚠️ WARNING | Truncación si >100 |
| TEXT | LONGTEXT | ✅ SAFE | MySQL hasta 4GB |
| INTEGER | BIGINT | ✅ SAFE | Ampliación |
| BIGINT | INTEGER | ❌ DANGER | Overflow >2.1B |

## Transformaciones Recomendadas

### VARCHAR → INTEGER
```sql
-- ❌ Peligroso
CAST(varchar_col AS INTEGER)

-- ✅ Seguro
CASE
    WHEN varchar_col ~ '^[0-9]+$' THEN CAST(varchar_col AS INTEGER)
    ELSE NULL
END
```
```

---

### 2.3 Guía de Troubleshooting

**Template**: `TROUBLESHOOTING_GUIDE.md`

```markdown
# Guía de Troubleshooting

## Error: FK Constraint Violation

**Síntoma**:
```
ERROR: FK constraint "fk_customer" violated
Key (customer_id)=(12345) not found in table "customers"
```

**Causa**: Orden incorrecto de migración

**Solución**:
1. Verificar grafo de dependencias
2. Migrar tablas padre primero
3. O deshabilitar FK temporalmente

---

## Error: Data Truncation

**Síntoma**:
```
WARNING: Data truncated for column 'description' at row 1234
```

**Causa**: Campo destino más pequeño

**Solución**:
```sql
SELECT id, LENGTH(description)
FROM source_table
WHERE LENGTH(description) > 100;
```

Opciones:
- Aumentar tamaño columna
- Truncar: SUBSTRING(description, 1, 100)
```

---

### 2.4 Guía de Optimización

**Template**: `PERFORMANCE_OPTIMIZATION.md`

```markdown
# Optimización de Performance

## Por Tamaño de Dataset

### Pequeños (<100K)
- ✅ INSERT estándar
- ✅ Single transaction

### Medianos (100K-10M)
- ✅ Batching 10K-50K
- ✅ Deshabilitar índices temp
- ⚠️ COPY/BULK INSERT

### Grandes (>10M)
- ✅ COPY/BULK obligatorio
- ✅ Paralelización
- ✅ Deshabilitar constraints temp

## Por Dialecto

### PostgreSQL
```sql
-- COPY (10-50x faster)
COPY customers_new FROM STDIN;

-- Deshabilitar autovacuum
ALTER TABLE customers_new SET (autovacuum_enabled = false);
```

### MySQL
```sql
-- LOAD DATA INFILE (20x faster)
LOAD DATA INFILE '/tmp/customers.csv'
INTO TABLE customers_new;

-- Deshabilitar índices
ALTER TABLE customers_new DISABLE KEYS;
```
```

---

### 2.5 Manual de API

**Template**: `API_INTEGRATION_GUIDE.md`

```markdown
# Guía de Integración API

## Workflow Completo

### Paso 1: Crear Proyecto
```bash
POST /api/projects
{
  "name": "Customer DB Migration",
  "description": "Oracle to PostgreSQL"
}
```

### Paso 2: Conectar BD Origen
```bash
POST /api/db-connections/sessions
{
  "dialect": "oracle",
  "host": "oracle.example.com",
  "database": "PROD"
}
```

### Paso 3: Crear Mappings
```bash
POST /api/mappings/projects/{id}/save
{
  "origin_table": "EMPLOYEES",
  "destination_table": "employees"
}
```

### Paso 4: Validar
```bash
POST /api/mappings/projects/{id}/validate-pre-migration
```

### Paso 5: Generar Script
```bash
POST /api/mappings/projects/{id}/generate-migration-script
```

## Webhook Integration
```bash
POST /api/webhooks
{
  "url": "https://jenkins.example.com/job/migration/build",
  "events": ["migration_completed"]
}
```
```

---

## 🔧 PARTE 3: Scripts de Utilidad

### 3.1 CLI para Generación

```bash
# Generar script
python migration_cli.py generate --project-id=abc123 --output=script.sql

# Validar
python migration_cli.py validate --project-id=abc123 --type=pre

# Estimar
python migration_cli.py estimate --project-id=abc123
```

---

### 3.2 Análisis de Dependencias

```python
class DependencyAnalyzer:
    def analyze_table_dependencies(project_id) -> Dict:
        # 1. Construir grafo FK
        # 2. Detectar ciclos
        # 3. Topological sort
        # 4. Identificar paralelizables

        return {
            "migration_order": [
                {"level": 1, "tables": ["customers", "products"]},
                {"level": 2, "tables": ["orders"]}
            ],
            "circular_references": [],
            "parallelizable_groups": [["customers", "products"]]
        }
```

---

### 3.3 Dry-Run Executor

```python
class DryRunExecutor:
    def execute_dry_run(project_id, sample_size=1000):
        # 1. Crear tablas temp
        # 2. Migrar sample_size filas
        # 3. Ejecutar validaciones
        # 4. Limpiar
        # 5. Retornar proyecciones

        return {
            "success": True,
            "sample_rows": 1000,
            "errors": 0,
            "projections": {
                "estimated_full_time": "45 min",
                "risk_level": "low"
            }
        }
```

---

## 🎯 Priorización Original

### Fase 1: Crítico
1. EnterpriseM igrationGenerator (transacciones + batching)
2. PreMigrationValidator
3. PostMigrationValidator
4. EXECUTION_PLAN_TEMPLATE
5. API_INTEGRATION_GUIDE

### Fase 2: Alto Valor
6. TransformationEngine
7. RollbackGenerator
8. DependencyAnalyzer
9. MigrationEstimator
10. TROUBLESHOOTING_GUIDE

### Fase 3: Integraciones
12. LiquibaseExporter
13. FlywayExporter
14. DbtExporter
15. WebhookSystem
16. MigrationCLI

### Fase 4: Optimizaciones
17. Dialect optimizations (COPY, BULK)
18. ParallelExecutor
19. DryRunExecutor
20. StreamingMigrator (>100M)

---

## 📝 Conclusión

**Este plan inicial fue refinado** en `PLAN_MIGRACION_ENTERPRISE.md` para enfocarse en el MVP crítico: hacer que las migraciones funcionen end-to-end en demos.

**Elementos que pasaron al MVP**:
- ✅ Transacciones
- ✅ Manejo de constraints
- ✅ Validación pre/post
- ✅ Transformaciones básicas
- ✅ Dry-run
- ✅ Dependency graph

**Elementos postponed (Fases 3-4)**:
- ⏸️ Liquibase/Flyway/dbt exporters
- ⏸️ CLI tool
- ⏸️ Webhooks
- ⏸️ Documentación PDF auto-generada
- ⏸️ Parallel execution
- ⏸️ Streaming para >100M rows

**Razón del refinamiento**: Enfoque en conseguir demos exitosas y primeros clientes antes que features enterprise avanzadas.
