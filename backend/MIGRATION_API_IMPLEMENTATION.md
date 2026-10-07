# Migration API Implementation

> Documento histórico: el SQL citado está archivado en `backend/docs/legacy_sql/`; el esquema sale de Alembic.

## ✅ Status: COMPLETO

Este documento describe la implementación de los endpoints de Migration API para DataMap, que permiten generación y ejecución de scripts SQL para migraciones de datos.

## Cambios Realizados

- ✅ Router creado en `backend/app/routers/migration.py` (sin SQLAlchemy, usa psycopg2)
- ✅ Tests de integración creados en `backend/test/integration/test_migration_api.py`
- ✅ Schema SQL para tablas en `backend/docs/legacy_sql/migrations/002_migration_tables.sql`
- ✅ Router registrado en `backend/main.py`
- ✅ Sintaxis validada y tests corregidos

## Files Created

### 1. Router: `backend/app/routers/migration.py`

Main API router with 5 endpoints:

- **POST** `/api/projects/{project_id}/migration/generate-script` - Generate optimized migration script
- **POST** `/api/projects/{project_id}/migration/execute` - Execute migration with tracking
- **GET** `/api/projects/{project_id}/migration/executions/{execution_id}` - Get execution status
- **GET** `/api/projects/{project_id}/migration/executions` - List all executions
- **GET** `/api/projects/{project_id}/migration/dependency-graph` - Get dependency graph

### 2. Tests: `backend/test/integration/test_migration_api.py`

Comprehensive integration tests covering:

- ✅ test_generate_script_success
- ✅ test_generate_script_unauthorized
- ✅ test_generate_script_project_not_found
- ✅ test_generate_script_invalid_dialect
- ✅ test_execute_migration_dry_run
- ✅ test_execute_migration_with_script_id
- ✅ test_execute_migration_unauthorized
- ✅ test_get_execution_status
- ✅ test_get_execution_status_not_found
- ✅ test_list_executions
- ✅ test_list_executions_with_filters
- ✅ test_list_executions_pagination
- ✅ test_get_dependency_graph
- ✅ test_get_dependency_graph_empty_project

### 3. Database Migration: `backend/docs/legacy_sql/migrations/002_migration_tables.sql`

SQL schema for two new tables:

#### `migration_scripts`
Stores generated migration scripts with:
- Script content and SHA-256 hash
- Generation options (batch_size, constraints, validation, dialect)
- Dependency order analysis
- Created by user tracking

#### `migration_executions`
Tracks execution status with:
- Status (running, success, failed, dry_run_complete)
- Progress tracking (rows migrated, duration)
- Backup ID for rollback
- Execution log (JSON array of steps)
- Error messages

### 4. Main App Integration

Updated `backend/main.py`:
- Added import for migration router
- Registered migration router in app

## Features Implemented

### 1. Script Generation

**Endpoint:** `POST /api/projects/{project_id}/migration/generate-script`

**Features:**
- Validates project ownership
- Retrieves project mappings
- Analyzes table dependencies using DependencyGraphService
- Generates optimized SQL script with MigrationScriptService
- Supports multiple SQL dialects (PostgreSQL, MySQL, SQL Server, Oracle)
- Configurable batch size, constraints, and validation
- Saves script with SHA-256 hash for versioning
- Estimates duration and row count

**Request:**
```json
{
  "batch_size": 10000,
  "include_constraints": true,
  "include_validation": true,
  "dialect": "postgresql"
}
```

**Response:**
```json
{
  "script_id": "uuid",
  "script": "BEGIN; INSERT INTO...",
  "estimated_duration_seconds": 2700,
  "estimated_rows": 35000,
  "dependency_order": ["customers", "orders", "order_items"],
  "created_at": "2025-01-16T14:30:00Z"
}
```

### 2. Migration Execution

**Endpoint:** `POST /api/projects/{project_id}/migration/execute`

**Features:**
- Supports both saved scripts and on-the-fly generation
- Dry-run mode for testing (executes ROLLBACK at end)
- Automatic backup creation before execution
- Real-time progress tracking
- Session-based database connection management
- Automatic ROLLBACK on errors
- Detailed execution logging

**Request:**
```json
{
  "script_id": "uuid",  // Optional
  "dry_run": false,
  "dest_connection_session_id": "uuid"
}
```

**Response:**
```json
{
  "execution_id": "uuid",
  "status": "running",
  "message": "Migration started successfully"
}
```

### 3. Execution Status

**Endpoint:** `GET /api/projects/{project_id}/migration/executions/{execution_id}`

**Features:**
- Real-time status updates
- Progress percentage calculation
- Rows migrated count
- Current step information
- Execution log with detailed steps
- Error messages if failed

**Response:**
```json
{
  "execution_id": "uuid",
  "status": "running",
  "progress_percent": 60,
  "rows_migrated": 21000,
  "estimated_remaining_seconds": 30,
  "started_at": "2025-01-16T14:30:00Z",
  "completed_at": null,
  "current_step": "Migrating table: orders (batch 2/3)",
  "execution_log": [...],
  "errors": []
}
```

### 4. List Executions

**Endpoint:** `GET /api/projects/{project_id}/migration/executions`

**Features:**
- Pagination support (limit/offset)
- Filter by status
- Ordered by start time (DESC)
- Total count for pagination

**Query Parameters:**
- `status`: Filter by execution status
- `limit`: Number of results (default: 10)
- `offset`: Pagination offset (default: 0)

**Response:**
```json
{
  "executions": [
    {
      "id": "uuid",
      "started_at": "2025-01-16T14:30:00Z",
      "completed_at": "2025-01-16T14:35:00Z",
      "status": "success",
      "rows_migrated": 35000,
      "duration_seconds": 300
    }
  ],
  "total": 25,
  "limit": 10,
  "offset": 0
}
```

### 5. Dependency Graph

**Endpoint:** `GET /api/projects/{project_id}/migration/dependency-graph`

**Features:**
- Analyzes table dependencies based on foreign keys
- Returns execution order
- Detects circular dependencies
- Identifies independent tables (can run in parallel)
- Provides graph visualization data for UI

**Response:**
```json
{
  "execution_order": ["customers", "products", "orders"],
  "circular_dependencies": [],
  "independent_tables": ["customers", "products"],
  "graph_visualization": {
    "nodes": [
      {"id": "customers", "label": "Customers"},
      {"id": "orders", "label": "Orders"}
    ],
    "edges": [
      {"from": "customers", "to": "orders"}
    ]
  }
}
```

## Security Features

1. **Authentication Required**: All endpoints require valid JWT token
2. **Project Ownership Validation**: Verifies user has access to project
3. **Encrypted Credentials**: Database credentials stored encrypted in Redis
4. **Session Management**: Connection sessions with TTL
5. **Automatic Backups**: Created before each execution
6. **SQL Injection Prevention**: Uses parameterized queries

## Services Used

### DependencyGraphService
- Analyzes table dependencies from foreign keys
- Performs topological sorting
- Detects circular dependencies
- Identifies parallelization opportunities

### MigrationScriptService
- Generates SQL scripts from mappings
- Supports multiple dialects
- Includes transaction wrappers
- Handles constraints and validation

### ExecutionService
- Executes SQL scripts with transaction management
- Tracks progress in real-time
- Creates automatic backups
- Handles dry-run mode
- Logs execution steps

### DBConnectionService
- Manages encrypted database sessions
- Provides database adapters
- Handles session expiration

## Usage Example

### 1. Generate Migration Script

```bash
curl -X POST "http://localhost:8000/api/projects/{project_id}/migration/generate-script" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "batch_size": 10000,
    "include_constraints": true,
    "include_validation": true,
    "dialect": "postgresql"
  }'
```

### 2. Execute Migration (Dry Run)

```bash
curl -X POST "http://localhost:8000/api/projects/{project_id}/migration/execute" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "script_id": "{script_id}",
    "dry_run": true,
    "dest_connection_session_id": "{session_id}"
  }'
```

### 3. Check Execution Status

```bash
curl -X GET "http://localhost:8000/api/projects/{project_id}/migration/executions/{execution_id}" \
  -H "Authorization: Bearer {token}"
```

### 4. List All Executions

```bash
curl -X GET "http://localhost:8000/api/projects/{project_id}/migration/executions?status=success&limit=10" \
  -H "Authorization: Bearer {token}"
```

### 5. Get Dependency Graph

```bash
curl -X GET "http://localhost:8000/api/projects/{project_id}/migration/dependency-graph" \
  -H "Authorization: Bearer {token}"
```

## Database Setup

The required tables (`migration_scripts`, `migration_executions`) are part of the Alembic schema. Create them with:

```bash
cd backend
alembic upgrade head
```

With Docker Compose the `backend` service already runs this on startup.

## Testing

Run integration tests:

```bash
cd backend
pytest test/integration/test_migration_api.py -v
```

Run all migration-related tests:

```bash
pytest test/ -k migration -v
```

## Future Enhancements

1. **Progress WebSocket**: Real-time progress updates via WebSocket
2. **Parallel Execution**: Execute independent tables in parallel
3. **Rollback Support**: Automatic rollback using backup_id
4. **Scheduling**: Schedule migrations for specific times
5. **Retry Logic**: Automatic retry on transient failures
6. **Email Notifications**: Notify on completion/failure
7. **Performance Metrics**: Track execution performance over time
8. **Script Diff**: Compare different script versions

## Notes

- The current implementation assumes mappings store table/column names directly (not hashes)
- Foreign key analysis requires schema metadata from destination database
- Backup creation uses BackupManager from utilities.migrations.validators
- Session TTL is configurable (default: 3 hours, max: 24 hours)

## Related Files

- Services: `backend/app/services/dependency_graph_service.py`
- Services: `backend/app/services/execution_service.py`
- Services: `backend/app/services/migration_script_service.py`
- Router: `backend/app/routers/db_connections.py`
- Models: `backend/app/models/db_metadata/`
