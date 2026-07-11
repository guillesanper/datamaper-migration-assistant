-- Migración 001: Soporte para Primary Keys Compuestas
-- Fecha: 2025-01-24
-- Descripción: Crea tabla para gestionar PKs compuestas (múltiples columnas)
--              y migra los datos existentes de columnas con is_primary=true

-- ========================================
-- PARTE 1: Crear nueva tabla
-- ========================================

CREATE TABLE IF NOT EXISTS primary_key_constraints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_id UUID NOT NULL REFERENCES tables(id) ON DELETE CASCADE,
    column_ids UUID[] NOT NULL,  -- Array de column IDs que componen la PK
    constraint_name VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT pk_at_least_one_column CHECK (array_length(column_ids, 1) >= 1),
    CONSTRAINT pk_unique_per_table UNIQUE (table_id)
);

-- Índices para optimizar consultas
CREATE INDEX idx_pk_constraints_table_id ON primary_key_constraints(table_id);
CREATE INDEX idx_pk_constraints_column_ids ON primary_key_constraints USING GIN(column_ids);

-- Comentarios para documentación
COMMENT ON TABLE primary_key_constraints IS 'Almacena definiciones de Primary Keys, incluyendo PKs compuestas (múltiples columnas)';
COMMENT ON COLUMN primary_key_constraints.column_ids IS 'Array de UUIDs de columnas que componen la Primary Key';
COMMENT ON COLUMN primary_key_constraints.constraint_name IS 'Nombre opcional del constraint, ej: "pk_users_id_tenant"';

-- ========================================
-- PARTE 2: Migrar datos existentes
-- ========================================
-- Por cada tabla que tenga columnas con is_primary=true,
-- crear un registro en primary_key_constraints

INSERT INTO primary_key_constraints (table_id, column_ids, constraint_name, created_at, updated_at)
SELECT
    t.id as table_id,
    ARRAY_AGG(c.id ORDER BY c.id) as column_ids,
    CONCAT('pk_', t.name, '_migrated') as constraint_name,
    NOW() as created_at,
    NOW() as updated_at
FROM tables t
JOIN columns c ON c.table_id = t.id
WHERE c.is_primary = true
GROUP BY t.id, t.name
HAVING COUNT(c.id) > 0;

-- Verificación: Mostrar cuántos registros se migraron
DO $$
DECLARE
    migrated_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO migrated_count FROM primary_key_constraints;
    RAISE NOTICE 'Primary Keys migradas: % tablas', migrated_count;
END $$;

-- ========================================
-- PARTE 3: Tabla de auditoría para cambios
-- ========================================
CREATE TABLE IF NOT EXISTS migration_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    migration_number VARCHAR(20) NOT NULL,
    action VARCHAR(50) NOT NULL,  -- 'TYPE_CHANGE', 'PK_ADDED', 'FK_CREATED', 'TABLE_BACKUP'
    table_id UUID,
    column_id UUID,
    old_value JSONB,
    new_value JSONB,
    validation_result JSONB,
    backup_reference VARCHAR(255),
    user_id UUID,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Metadata adicional
    ip_address VARCHAR(50),
    user_agent TEXT
);

CREATE INDEX idx_audit_migration ON migration_audit_log(migration_number);
CREATE INDEX idx_audit_timestamp ON migration_audit_log(timestamp DESC);
CREATE INDEX idx_audit_table_id ON migration_audit_log(table_id);
CREATE INDEX idx_audit_user_id ON migration_audit_log(user_id);

COMMENT ON TABLE migration_audit_log IS 'Registro de auditoría de todas las migraciones y cambios de esquema';

-- ========================================
-- PARTE 4: Registrar esta migración
-- ========================================
INSERT INTO migration_audit_log (
    migration_number,
    action,
    old_value,
    new_value,
    timestamp
) VALUES (
    '001',
    'MIGRATION_EXECUTED',
    jsonb_build_object('description', 'Estado inicial sin PKs compuestas'),
    jsonb_build_object(
        'description', 'Sistema de PKs compuestas implementado',
        'table_created', 'primary_key_constraints',
        'audit_table_created', 'migration_audit_log'
    ),
    NOW()
);

-- ========================================
-- NOTAS IMPORTANTES
-- ========================================
-- 1. La columna "is_primary" en "columns" se mantiene por compatibilidad
--    pero el sistema ahora usa "primary_key_constraints" como fuente de verdad
--
-- 2. Para agregar una PK compuesta:
--    INSERT INTO primary_key_constraints (table_id, column_ids, constraint_name)
--    VALUES ('tabla_uuid', ARRAY['col1_uuid', 'col2_uuid'], 'pk_nombre');
--
-- 3. Para obtener las columnas de una PK:
--    SELECT c.* FROM columns c
--    JOIN primary_key_constraints pk ON pk.table_id = c.table_id
--    WHERE c.id = ANY(pk.column_ids);
--
-- 4. Esta migración NO elimina datos, solo agrega nueva funcionalidad
--
-- 5. En caso de rollback, ejecutar: 001_composite_primary_keys_rollback.sql
