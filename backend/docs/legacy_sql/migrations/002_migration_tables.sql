-- Migration: Create tables for migration script generation and execution tracking
-- Created: 2025-01-17
-- Description: Adds migration_scripts and migration_executions tables for the Migration API

-- =====================================================
-- TABLE: migration_scripts
-- =====================================================
-- Stores generated migration scripts with versioning

CREATE TABLE IF NOT EXISTS migration_scripts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    script_content TEXT NOT NULL,
    script_hash VARCHAR(64) NOT NULL,  -- SHA-256 hash for deduplication

    -- Script generation options
    batch_size INTEGER DEFAULT 10000,
    include_constraints BOOLEAN DEFAULT TRUE,
    include_validation BOOLEAN DEFAULT TRUE,
    dialect VARCHAR(50) DEFAULT 'postgresql',

    -- Dependency analysis
    dependency_order TEXT[],  -- Array of table names in execution order

    -- Metadata
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indices for migration_scripts
CREATE INDEX IF NOT EXISTS idx_migration_scripts_project_id
    ON migration_scripts(project_id);

CREATE INDEX IF NOT EXISTS idx_migration_scripts_hash
    ON migration_scripts(script_hash);

CREATE INDEX IF NOT EXISTS idx_migration_scripts_created_at
    ON migration_scripts(created_at DESC);


-- =====================================================
-- TABLE: migration_executions
-- =====================================================
-- Tracks execution status and progress of migrations

CREATE TABLE IF NOT EXISTS migration_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    script_hash VARCHAR(64),  -- Hash of the executed script

    -- Execution status
    status VARCHAR(50) NOT NULL DEFAULT 'running',  -- running, success, failed, dry_run_complete

    -- Progress tracking
    rows_migrated INTEGER DEFAULT 0,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    -- Backup information
    backup_id VARCHAR(255),  -- ID of the backup created before execution

    -- Execution log (JSON array of step details)
    execution_log JSONB,

    -- Error handling
    error_message TEXT,

    -- Metadata
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indices for migration_executions
CREATE INDEX IF NOT EXISTS idx_migration_executions_project_id
    ON migration_executions(project_id);

CREATE INDEX IF NOT EXISTS idx_migration_executions_status
    ON migration_executions(status);

CREATE INDEX IF NOT EXISTS idx_migration_executions_started_at
    ON migration_executions(started_at DESC);

CREATE INDEX IF NOT EXISTS idx_migration_executions_script_hash
    ON migration_executions(script_hash);


-- =====================================================
-- COMMENTS
-- =====================================================

COMMENT ON TABLE migration_scripts IS
    'Stores generated SQL migration scripts with versioning and options';

COMMENT ON COLUMN migration_scripts.script_hash IS
    'SHA-256 hash of script_content for deduplication and integrity checking';

COMMENT ON COLUMN migration_scripts.dependency_order IS
    'Topologically sorted order of tables based on foreign key dependencies';

COMMENT ON TABLE migration_executions IS
    'Tracks execution status, progress, and results of migration scripts';

COMMENT ON COLUMN migration_executions.status IS
    'Execution status: running, success, failed, dry_run_complete';

COMMENT ON COLUMN migration_executions.execution_log IS
    'JSON array containing step-by-step execution details: [{step, table, rows, duration, status}]';

COMMENT ON COLUMN migration_executions.backup_id IS
    'Reference to backup created before execution for rollback capability';
