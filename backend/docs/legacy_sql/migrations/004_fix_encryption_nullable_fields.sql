-- ============================================================================
-- MIGRATION 004: Fix Nullable Fields for Encryption
-- ============================================================================
-- Descripción: Permite que los campos originales sean NULL cuando están cifrados
-- Autor: DataMap Security Team
-- Fecha: 2025-02-01
--
-- Este script permite que name, data_type, etc sean NULL cuando is_encrypted = TRUE
-- ============================================================================

-- ============================================================================
-- 1. MODIFICAR RESTRICCIONES EN TABLA "tables"
-- ============================================================================

-- Permitir que 'name' sea NULL cuando is_encrypted = TRUE
ALTER TABLE tables ALTER COLUMN name DROP NOT NULL;

-- Agregar constraint CHECK para asegurar que name existe O está cifrado
ALTER TABLE tables ADD CONSTRAINT check_table_name_or_encrypted
    CHECK (
        (name IS NOT NULL AND (is_encrypted IS NULL OR is_encrypted = FALSE))
        OR
        (name_encrypted IS NOT NULL AND name_nonce IS NOT NULL AND is_encrypted = TRUE)
    );

COMMENT ON CONSTRAINT check_table_name_or_encrypted ON tables IS
    'Asegura que la tabla tenga nombre en texto plano O cifrado, no ambos ni ninguno';

-- ============================================================================
-- 2. MODIFICAR RESTRICCIONES EN TABLA "columns"
-- ============================================================================

-- Permitir que 'name' y 'data_type' sean NULL cuando is_encrypted = TRUE
ALTER TABLE columns ALTER COLUMN name DROP NOT NULL;
ALTER TABLE columns ALTER COLUMN data_type DROP NOT NULL;

-- Agregar constraint CHECK para asegurar que name existe O está cifrado
ALTER TABLE columns ADD CONSTRAINT check_column_name_or_encrypted
    CHECK (
        (name IS NOT NULL AND (is_encrypted IS NULL OR is_encrypted = FALSE))
        OR
        (name_encrypted IS NOT NULL AND name_nonce IS NOT NULL AND is_encrypted = TRUE)
    );

-- Agregar constraint CHECK para asegurar que data_type existe O está cifrado
ALTER TABLE columns ADD CONSTRAINT check_column_datatype_or_encrypted
    CHECK (
        (data_type IS NOT NULL AND (is_encrypted IS NULL OR is_encrypted = FALSE))
        OR
        (data_type_encrypted IS NOT NULL AND data_type_nonce IS NOT NULL AND is_encrypted = TRUE)
    );

COMMENT ON CONSTRAINT check_column_name_or_encrypted ON columns IS
    'Asegura que la columna tenga nombre en texto plano O cifrado';
COMMENT ON CONSTRAINT check_column_datatype_or_encrypted ON columns IS
    'Asegura que la columna tenga data_type en texto plano O cifrado';

-- ============================================================================
-- 3. MODIFICAR RESTRICCIONES EN TABLA "mappings"
-- ============================================================================

-- Los mappings ya no tienen NOT NULL en los campos que se cifran
-- pero agregar constraints CHECK por consistencia
ALTER TABLE mappings ADD CONSTRAINT check_mapping_origin_table_or_encrypted
    CHECK (
        (origin_table IS NOT NULL AND (is_encrypted IS NULL OR is_encrypted = FALSE))
        OR
        (origin_table_encrypted IS NOT NULL AND origin_table_nonce IS NOT NULL AND is_encrypted = TRUE)
    );

ALTER TABLE mappings ADD CONSTRAINT check_mapping_origin_column_or_encrypted
    CHECK (
        (origin_column IS NOT NULL AND (is_encrypted IS NULL OR is_encrypted = FALSE))
        OR
        (origin_column_encrypted IS NOT NULL AND origin_column_nonce IS NOT NULL AND is_encrypted = TRUE)
    );

ALTER TABLE mappings ADD CONSTRAINT check_mapping_dest_table_or_encrypted
    CHECK (
        (destination_table IS NOT NULL AND (is_encrypted IS NULL OR is_encrypted = FALSE))
        OR
        (destination_table_encrypted IS NOT NULL AND destination_table_nonce IS NOT NULL AND is_encrypted = TRUE)
    );

ALTER TABLE mappings ADD CONSTRAINT check_mapping_dest_column_or_encrypted
    CHECK (
        (destination_column IS NOT NULL AND (is_encrypted IS NULL OR is_encrypted = FALSE))
        OR
        (destination_column_encrypted IS NOT NULL AND destination_column_nonce IS NOT NULL AND is_encrypted = TRUE)
    );

-- ============================================================================
-- FIN DE LA MIGRACIÓN
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '✅ Migración 004_fix_encryption_nullable_fields completada exitosamente';
    RAISE NOTICE '🔐 Campos name, data_type ahora pueden ser NULL cuando están cifrados';
    RAISE NOTICE '✅ Constraints CHECK agregados para garantizar integridad de datos';
END $$;
