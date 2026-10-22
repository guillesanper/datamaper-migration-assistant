-- Rollback de Migración 001: Soporte para Primary Keys Compuestas
-- Fecha: 2025-01-24
-- Descripción: Revierte los cambios de la migración 001, eliminando tablas creadas
--              Los datos en "columns" con is_primary se mantienen intactos

-- ========================================
-- ADVERTENCIA
-- ========================================
-- Este script eliminará:
-- - Tabla primary_key_constraints (y todos sus datos)
-- - Tabla migration_audit_log (y todos sus registros)
--
-- NO se perderán datos de:
-- - Tabla columns (is_primary se mantiene)
-- - Tabla tables
-- - Tabla mappings
--
-- Ejecutar solo si es necesario revertir la migración 001
-- ========================================

BEGIN;

-- Verificación de seguridad
DO $$
DECLARE
    pk_count INTEGER;
    audit_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO pk_count FROM primary_key_constraints;
    SELECT COUNT(*) INTO audit_count FROM migration_audit_log;

    RAISE NOTICE '============================================';
    RAISE NOTICE 'ROLLBACK MIGRACIÓN 001';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Primary Keys registradas: %', pk_count;
    RAISE NOTICE 'Registros de auditoría: %', audit_count;
    RAISE NOTICE '';
    RAISE NOTICE 'Estas tablas serán ELIMINADAS:';
    RAISE NOTICE '  - primary_key_constraints';
    RAISE NOTICE '  - migration_audit_log';
    RAISE NOTICE '';
    RAISE NOTICE 'Los datos en "columns" (is_primary) se mantienen.';
    RAISE NOTICE '============================================';
END $$;

-- ========================================
-- PARTE 1: Eliminar índices
-- ========================================
DROP INDEX IF EXISTS idx_pk_constraints_table_id;
DROP INDEX IF EXISTS idx_pk_constraints_column_ids;
DROP INDEX IF EXISTS idx_audit_migration;
DROP INDEX IF EXISTS idx_audit_timestamp;
DROP INDEX IF EXISTS idx_audit_table_id;
DROP INDEX IF EXISTS idx_audit_user_id;

-- ========================================
-- PARTE 2: Eliminar tablas
-- ========================================
DROP TABLE IF EXISTS primary_key_constraints CASCADE;
DROP TABLE IF EXISTS migration_audit_log CASCADE;

-- ========================================
-- PARTE 3: Verificación post-rollback
-- ========================================
DO $$
DECLARE
    tables_count INTEGER;
    columns_count INTEGER;
    columns_with_pk INTEGER;
BEGIN
    SELECT COUNT(*) INTO tables_count FROM tables;
    SELECT COUNT(*) INTO columns_count FROM columns;
    SELECT COUNT(*) INTO columns_with_pk FROM columns WHERE is_primary = true;

    RAISE NOTICE '';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'ROLLBACK COMPLETADO';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Estado de las tablas principales:';
    RAISE NOTICE '  - Tablas: % registros', tables_count;
    RAISE NOTICE '  - Columnas: % registros', columns_count;
    RAISE NOTICE '  - Columnas con PK: % registros', columns_with_pk;
    RAISE NOTICE '';
    RAISE NOTICE '✅ Datos principales intactos';
    RAISE NOTICE '✅ Rollback completado exitosamente';
    RAISE NOTICE '============================================';
END $$;

COMMIT;

-- ========================================
-- NOTAS IMPORTANTES
-- ========================================
-- 1. Después de este rollback, el sistema vuelve a usar solo
--    la columna "is_primary" en "columns" para PKs simples
--
-- 2. No hay pérdida de datos en tablas principales
--
-- 3. Se pierde el historial de auditoría de migraciones
--
-- 4. Para re-aplicar la migración 001, ejecutar:
--    001_composite_primary_keys.sql
