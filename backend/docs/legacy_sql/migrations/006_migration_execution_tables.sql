-- Migration 006: Migration Execution Tables
-- Created: 2025-01-17
-- Purpose: Add execution tracking for migration scripts

-- =============================================================================
-- MIGRATION EXECUTIONS TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS migration_executions (
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
    script_hash VARCHAR(64),  -- SHA-256 of the executed script
    backup_id VARCHAR(255),
    error_message TEXT,
    execution_log JSONB,  -- [{step, table, rows, duration, status}, ...]
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_migration_executions_project ON migration_executions(project_id);
CREATE INDEX IF NOT EXISTS idx_migration_executions_status ON migration_executions(status);
CREATE INDEX IF NOT EXISTS idx_migration_executions_created_at ON migration_executions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_migration_executions_script_hash ON migration_executions(script_hash);

-- =============================================================================
-- COMMENTS
-- =============================================================================

COMMENT ON TABLE migration_executions IS 'Tracks execution of migration scripts against destination databases';
COMMENT ON COLUMN migration_executions.status IS 'Execution status: pending, running, success, failed, rolled_back, dry_run_complete';
COMMENT ON COLUMN migration_executions.rows_migrated IS 'Total number of rows migrated';
COMMENT ON COLUMN migration_executions.script_hash IS 'SHA-256 hash of the executed SQL script for deduplication';
COMMENT ON COLUMN migration_executions.backup_id IS 'ID of the backup created before execution';
COMMENT ON COLUMN migration_executions.execution_log IS 'Detailed log of each step: [{step, table, rows, duration, status}]';
