# Plan de Implementación: Sistema Enterprise de Generación y Ejecución de Scripts de Migración

**Fecha de creación**: 2025-01-16
**Estado**: Pendiente de implementación
**Prioridad**: Alta - Crítico para demos y lanzamiento

---

## 📋 Resumen Ejecutivo

### Objetivo
Convertir DataMap en una plataforma production-ready de migraciones de bases de datos que impresione a consultoras en demos, generando scripts SQL que funcionen correctamente en producción real.

### Contexto del Producto
- **Tipo**: B2B para consultoras de migración de bases de datos
- **Diferenciación clave**: Solo trabaja con metadatos (no datos sensibles) → Compliance y seguridad
- **Estado**: Pre-lanzamiento con demos programadas
- **Escenario crítico de demo**: Oracle → PostgreSQL end-to-end
- **Timeline**: 5 meses hasta lanzamiento

### Valor Único
1. ✅ Solo metadatos (no acceso a datos reales)
2. ✅ Encriptación AES-256-GCM de esquemas guardados
3. ✅ Modo híbrido: Import (guardado) + Connector (solo hashes, no guarda)
4. ✅ Interfaz visual de mapeo (React Flow)
5. ✅ Scripts SQL que realmente funcionan en producción

---

## 🔴 Gaps Críticos Identificados

### 1. NO HAY EJECUCIÓN DE SCRIPTS ❌ BLOCKER
**Problema**: Scripts generados pero nunca ejecutados
- No existe endpoint para ejecutar contra BD destino
- Sin manejo de transacciones (BEGIN/COMMIT/ROLLBACK)
- Sin rollback automático en errores
- Sin tracking de progreso

**Impacto**: Demo Oracle → PostgreSQL fallará en el paso final

---

### 2. NO HAY MANEJO DE CONSTRAINTS ❌ CRÍTICO
**Problema**: Scripts violan FK/PK constraints
- No deshabilita/habilita foreign keys antes/después
- No deshabilita triggers
- No ordena tablas por dependencias
- INSERT en orden incorrecto → violaciones FK

**Impacto**: Migración real fallará con errores de integridad

---

### 3. TRANSFORMACIONES NO SE APLICAN ❌ BLOCKER
**Problema**: Campo `transformation_logic_encrypted` existe en DB pero se ignora
- No genera CAST/CONCAT/CASE WHEN en SQL
- Sin conversión automática de tipos incompatibles
- Oracle VARCHAR2 → PostgreSQL TEXT sin conversión

**Impacto**: Datos migrados con tipos incorrectos

---

### 4. CONECTORES NECESITAN PULIDO ⚠️ IMPORTANTE
**Problema**:
- Falta `get_full_schema_metadata()` en algunos adaptadores
- Errores genéricos (todos → HTTP 500)
- Frontend sin manejo de timeouts de red

**Impacto**: UX pobre, errores confusos para usuarios

---

### 5. SIN WORKFLOW DE VALIDACIÓN ❌ CRÍTICO
**Problema**:
- No valida pre-migración (calidad de datos, integridad)
- No verifica post-migración (row counts, constraints)
- No hay modo dry-run (prueba sin commit)

**Impacto**: Errores descubiertos en producción, datos perdidos

---

## 🏗️ Arquitectura Propuesta

```
┌──────────────────────────────────────────────────────────┐
│         MIGRATION ORCHESTRATOR SERVICE                    │
│  (Coordina todo el ciclo de vida de la migración)        │
└────────────┬─────────────────────────────────────────────┘
             │
   ┌─────────┴──────────┐
   │                    │
   ▼                    ▼
┌──────────────┐   ┌──────────────────────┐
│ PRE-FLIGHT   │   │  SCRIPT GENERATOR    │
│ VALIDATOR    │   │  (Enhanced)          │
│              │   │                      │
│ • FK check   │   │ • Dependency graph   │
│ • Type check │   │ • Constraints ON/OFF │
│ • Data qual. │   │ • Transformations    │
└──────┬───────┘   │ • Batch processing   │
       │           └─────────┬────────────┘
       │                     │
       │           ┌─────────┴──────────┐
       │           │                    │
       ▼           ▼                    ▼
┌──────────────────────┐      ┌───────────────────┐
│  EXECUTION ENGINE    │      │  ROLLBACK SERVICE │
│  (NEW)               │      │  (Enhance)        │
│                      │      │                   │
│ • Transactions       │      │ • Auto snapshots  │
│ • Progress tracking  │      │ • Point-in-time   │
│ • Error recovery     │      │   recovery        │
│ • Dry-run mode       │      └───────────────────┘
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ POST-MIGRATION       │
│ VALIDATOR            │
│                      │
│ • Row count compare  │
│ • Sample verify      │
│ • Constraint check   │
└──────────────────────┘
```

---

## 🎯 Infraestructura Existente (Aprovechar)

✅ **TYPE_COMPATIBILITY_MATRIX** (`validators.py`) - 60+ reglas de compatibilidad listas
✅ **BackupManager** (`rollback.py`) - Sistema de backup production-ready
✅ **TypeCompatibilityService** - Capa de servicio completa
✅ **4 Database Adapters** - PostgreSQL, MySQL, SQL Server, Oracle funcionando
✅ **Encriptación AES-256-GCM** - Sistema completo de encriptación
✅ **Test Framework** - pytest con 50+ archivos de tests
✅ **Modo Híbrido** - import/connector ya implementado

---

## 📅 FASE 1: CRÍTICO PARA DEMOS (Semanas 1-3) 🔴

**Objetivo**: Oracle → PostgreSQL funciona end-to-end en demo

### Componente 1.1: Dependency Graph Service ✅ COMPLETADO

**Archivo**: `backend/app/services/dependency_graph_service.py`

**Estado**: ✅ Implementado y testeado (67 tests pasando, coverage >95%)

**Funcionalidad**:
- ✅ Construir grafo de dependencias FK entre tablas
- ✅ Topological sort (algoritmo de Kahn)
- ✅ Detectar dependencias circulares
- ✅ Identificar tablas independientes
- ✅ Niveles de paralelización
- ✅ Ruta crítica y análisis completo

**Test cases**:
- ✅ Cadena simple: A → B → C
- ✅ Patrón diamante: A → B/C → D
- ✅ Circular: A → B → C → A
- ✅ Auto-referencia: Users.manager_id → Users.id
- ✅ Casos edge: grafos desconectados, cadenas largas, FKs compuestas

**Test file**: `backend/test/unit/test_dependency_graph_service.py` (67 tests)

**Fecha completado**: 2025-01-16

---

### Componente 1.2: Enhanced Migration Script Service ✅ COMPLETADO

**Archivo**: `backend/app/services/migration_script_service.py`

**Estado**: ✅ Implementado y testeado (38 tests pasando, coverage >95%)

**Funcionalidad implementada**:

1. ✅ **Transacciones por dialecto**
   - PostgreSQL: `BEGIN;` ... `COMMIT;`
   - MySQL: `START TRANSACTION;` ... `COMMIT;`
   - SQL Server: `BEGIN TRANSACTION;` ... `COMMIT TRANSACTION;`
   - Oracle: `BEGIN` ... `COMMIT;`

2. ✅ **Manejo de constraints**
   - PostgreSQL: `ALTER TABLE ... DISABLE/ENABLE TRIGGER ALL;`
   - MySQL: `SET FOREIGN_KEY_CHECKS=0/1;`
   - SQL Server: `ALTER TABLE ... NOCHECK/CHECK CONSTRAINT ALL;`
   - Oracle: `ALTER TABLE ... DISABLE/ENABLE ALL TRIGGERS;`

3. ✅ **Transformaciones customizadas**
   - Placeholder `{column}` para lógica custom
   - Conversiones automáticas de tipos incompatibles
   - PostgreSQL: sintaxis `::` para casts
   - Soporte para 10+ conversiones comunes

4. ✅ **Batch processing**
   - PostgreSQL: `DO $$ ... END $$;` con LIMIT/OFFSET
   - MySQL: CREATE PROCEDURE temporal
   - SQL Server: WHILE loop con OFFSET...FETCH
   - Oracle: WHILE loop con OFFSET...FETCH
   - Progress tracking integrado

5. ✅ **Integración con Dependency Graph**
   - Parámetro `dependency_order` para orden topológico
   - Scripts respetan orden de FK
   - Agrupación por tabla automática

**Nuevos parámetros API**:
```python
def generate_insert_script(
    mappings,
    origin_adapter=None,
    dest_adapter=None,
    project_name=None,
    dependency_order=None,  # ✅ NUEVO
    batch_size=10000,       # ✅ NUEVO
    include_constraints=True,  # ✅ NUEVO
    include_validation=True,   # ✅ NUEVO
    dialect='postgresql'    # ✅ NUEVO
)
```

**Test cases**:
- ✅ Transaction wrappers (5 tests)
- ✅ Constraint management (8 tests)
- ✅ Transformations (8 tests)
- ✅ Batch processing (6 tests)
- ✅ Script generation (9 tests)
- ✅ Hash resolution (2 tests)

**Test file**: `backend/test/unit/test_migration_script_service.py` (38 tests)

**Documentación**: `docs/TAREA_1.2_ENHANCED_MIGRATION_SCRIPT.md`

**Fecha completado**: 2025-01-17

---

### Componente 1.3: Execution Service ⭐ NUEVO

**Archivo**: `backend/app/services/execution_service.py`

**Método principal**:
```python
def execute_migration(
    db, project_id, script, dest_adapter, dry_run=False
) -> Dict:
    # 1. Crear registro migration_executions
    # 2. Crear backup automático
    # 3. Ejecutar script
    # 4. Si dry_run: ROLLBACK
    # 5. Si error: ROLLBACK + status='failed'
    # 6. Si éxito: COMMIT + status='success'
```

**Nueva tabla DB**:
```sql
CREATE TABLE migration_executions (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    status VARCHAR(20),  -- pending, running, success, failed, rolled_back, dry_run_complete
    rows_migrated INTEGER,
    script_hash VARCHAR(64),
    backup_id VARCHAR(255),
    error_message TEXT,
    execution_log JSONB,
    created_by UUID,
    created_at TIMESTAMP
);
```

**Migration file**: `backend/utilities/migrations/006_migration_execution_tables.sql`

**Test file**: `backend/test/unit/services/test_execution_service.py`

---

### Componente 1.4: API Endpoints ⭐ NUEVO

**Archivo**: `backend/app/routers/migration.py`

**Endpoints**:

```python
POST /api/projects/{project_id}/migration/generate-script
# Request: {batch_size, include_constraints, include_validation}
# Response: {script_id, script, estimated_duration, dependency_order}

POST /api/projects/{project_id}/migration/execute
# Request: {script_id, dry_run, dest_connection_session_id}
# Response: {execution_id, status}

GET /api/projects/{project_id}/migration/executions/{execution_id}
# Response: {execution_id, status, progress_percent, rows_migrated, current_step}

GET /api/projects/{project_id}/migration/executions
# Response: {executions: [...]}
```

**Test file**: `backend/test/integration/test_migration_api.py`

---

### Componente 1.5: Connector Polish 🔧 MODIFICAR

**Archivos**:
- `backend/app/routers/db_connections.py` - Error handling específico
- `backend/app/utils/db_adapters/*.py` - Error handling
- `frontend/src/services/db_connection.service.ts` - Timeout handling

**Cambios**:
1. Reemplazar `except Exception` por errores específicos (401, 403, 504)
2. Verificar `get_full_schema_metadata()` en todos los adaptadores
3. Frontend: timeout 30s + retry logic

---

## 📅 FASE 2: VALIDACIÓN (Semanas 4-6) 🟡

### Componente 2.1: Validation Service ⭐ NUEVO

**Archivo**: `backend/app/services/validation_service.py`

**Pre-migration**:
- Referential Integrity check
- Type compatibility check
- Data quality scan (NULLs, overflow, truncado)
- Schema consistency

**Post-migration**:
- Row count match
- Sample data comparison
- Constraint verification
- Data integrity checksums

**Nueva tabla**:
```sql
CREATE TABLE validation_reports (
    id UUID PRIMARY KEY,
    project_id UUID,
    execution_id UUID,
    report_type VARCHAR(20),  -- pre_flight, post_migration
    status VARCHAR(20),
    checks_passed INTEGER,
    checks_warning INTEGER,
    checks_failed INTEGER,
    can_proceed BOOLEAN,
    issues JSONB,
    recommendations JSONB,
    created_at TIMESTAMP
);
```

**Test file**: `backend/test/unit/services/test_validation_service.py`

---

### Componente 2.2: Transformation Service ⭐ NUEVO

**Archivo**: `backend/app/services/transformation_service.py`

**Funciones soportadas**:
CAST, UPPER, LOWER, TRIM, CONCAT, COALESCE, SUBSTRING, CASE, REPLACE, TO_TIMESTAMP

**Métodos**:
```python
def parse_transformation(transformation_logic: str) -> Dict
def generate_transformation_sql(column, transformation, dialect) -> str
def validate_transformation(transformation_logic, origin_type) -> Tuple[bool, str]
```

---

### Componente 2.3: Error Recovery 🔧 ENHANCE

**Archivo**: `backend/app/services/execution_service.py` (enhance)

**Agregar**:
```python
def execute_with_retry(step_sql, dest_adapter, max_retries=3) -> Dict
def handle_execution_error(execution_id, error) -> Dict
```

---

### Componente 2.4: Validation API ⭐ NUEVO

**Archivo**: `backend/app/routers/migration.py` (agregar endpoints)

```python
POST /api/projects/{project_id}/migration/validate
POST /api/projects/{project_id}/migration/executions/{exec_id}/validate
```

---

## 📅 FASE 3: ENTERPRISE (Semanas 7-10) 🟢

### Componente 3.1: Documentation Service ⭐ NUEVO

**Archivo**: `backend/app/services/documentation_service.py`

**Genera**:
- Execution plan (Markdown + Mermaid)
- Validation report (PDF)
- Risk assessment
- Rollback procedures

---

### Componente 3.2: Preview Service ⭐ NUEVO

**Archivo**: `backend/app/services/preview_service.py`

**Muestra**:
- Sample 10 filas por tabla
- Valores transformados
- Warnings

---

### Componente 3.3: Pause/Resume 🔧 ENHANCE

**Archivo**: `backend/app/services/execution_service.py` (enhance)

**Agregar**:
```python
def pause_execution(execution_id) -> Dict
def resume_execution(execution_id) -> Dict
```

**DB change**:
```sql
ALTER TABLE migration_executions ADD COLUMN checkpoint_data JSONB;
```

---

## 📅 FASE 4: PERFORMANCE (Semanas 11-14) ⚪

### Componente 4.1: Parallel Execution ⭐ NUEVO

**Archivo**: `backend/app/services/parallel_execution_service.py`

---

### Componente 4.2: Bulk Operations 🔧 ENHANCE

**Archivo**: `backend/app/services/migration_script_service.py` (enhance)

**Agregar**:
- PostgreSQL COPY
- MySQL LOAD DATA INFILE
- SQL Server BULK INSERT

---

### Componente 4.3: Performance Monitor ⭐ NUEVO

**Archivo**: `backend/app/services/performance_monitor_service.py`

---

## 📂 Resumen de Archivos

### ⭐ Nuevos (16 archivos)
1. `backend/app/services/dependency_graph_service.py`
2. `backend/app/services/execution_service.py`
3. `backend/app/services/validation_service.py`
4. `backend/app/services/transformation_service.py`
5. `backend/app/services/documentation_service.py`
6. `backend/app/services/preview_service.py`
7. `backend/app/services/parallel_execution_service.py`
8. `backend/app/services/performance_monitor_service.py`
9. `backend/app/routers/migration.py`
10. `backend/utilities/migrations/006_migration_execution_tables.sql`
11. `backend/utilities/migrations/007_validation_reports.sql`
12. `backend/utilities/migrations/run_migration_006.py`
13. `backend/utilities/migrations/run_migration_007.py`
14. `backend/test/unit/services/test_dependency_graph_service.py`
15. `backend/test/unit/services/test_execution_service.py`
16. `backend/test/integration/test_oracle_to_postgres_migration.py`

### 🔧 A Modificar (6 archivos)
1. `backend/app/services/migration_script_service.py`
2. `backend/app/routers/db_connections.py`
3. `backend/app/utils/db_adapters/postgres_adapter.py`
4. `backend/app/utils/db_adapters/mysql_adapter.py`
5. `backend/app/utils/db_adapters/oracle_adapter.py`
6. `frontend/src/services/db_connection.service.ts`

---

## 📦 Dependencias

```txt
networkx==3.2.1
psutil==5.9.6
reportlab==4.0.7  # Opcional Fase 3
```

---

## ✅ Checklist de Éxito

### Fase 1
- [ ] Oracle → PostgreSQL 10 tablas OK
- [ ] FK preservados
- [ ] Transformaciones aplicadas
- [ ] Dry-run funciona
- [ ] <5min para 100K rows
- [ ] Rollback automático

### Fase 2
- [ ] 4 dialectos testeados
- [ ] 90%+ coverage
- [ ] 1M+ rows load test
- [ ] Validación 95%+ detección

### Fase 3
- [ ] Docs auto-generadas
- [ ] Preview 70% reduce surprises
- [ ] Pause/resume OK

### Fase 4
- [ ] 3x speedup paralelo
- [ ] 10M+ rows OK
