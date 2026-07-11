-- ============================================================================
-- MIGRATION 003: Infraestructura de Cifrado Enterprise
-- ============================================================================
-- Descripción: Agrega soporte para cifrado de datos con AES-256-GCM + Argon2id
-- Autor: DataMap Security Team
-- Fecha: 2025-01-31
-- Nivel: Nivel 1 - Cifrado por defecto con master key
--
-- Este script agrega:
-- 1. Tabla project_encryption para gestión de claves por proyecto
-- 2. Columnas de cifrado para tables, columns, mappings, versiones y comentarios
-- 3. Índices para búsquedas eficientes
-- ============================================================================

-- ============================================================================
-- 1. TABLA DE CONFIGURACIÓN DE CIFRADO POR PROYECTO
-- ============================================================================

CREATE TABLE IF NOT EXISTS project_encryption (
    project_id UUID PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,

    -- Master key hash (Argon2id one-way) - NUNCA se puede revertir
    master_key_hash TEXT NOT NULL,

    -- Salts (128 bits cada uno, almacenados en base64)
    salt_verification TEXT NOT NULL,      -- Para verificar la passphrase
    salt_key_derivation TEXT NOT NULL,    -- Para derivar la AES key

    -- Estado del cifrado
    encryption_enabled BOOLEAN DEFAULT TRUE,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
    updated_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
);

CREATE INDEX IF NOT EXISTS idx_project_encryption_enabled
    ON project_encryption(encryption_enabled);

COMMENT ON TABLE project_encryption IS
    'Configuración de cifrado por proyecto (AES-256-GCM + Argon2id)';
COMMENT ON COLUMN project_encryption.master_key_hash IS
    'Hash one-way de la master key (Argon2id) - solo para verificación';
COMMENT ON COLUMN project_encryption.salt_verification IS
    'Salt para verificar la passphrase del usuario';
COMMENT ON COLUMN project_encryption.salt_key_derivation IS
    'Salt para derivar la clave de cifrado AES-256';

-- ============================================================================
-- 2. AGREGAR SOPORTE DE CIFRADO A TABLA "tables"
-- ============================================================================

-- Agregar columnas para almacenar el nombre cifrado
ALTER TABLE tables ADD COLUMN IF NOT EXISTS
    name_encrypted TEXT;

ALTER TABLE tables ADD COLUMN IF NOT EXISTS
    name_nonce TEXT;

ALTER TABLE tables ADD COLUMN IF NOT EXISTS
    is_encrypted BOOLEAN DEFAULT FALSE;

-- Índice para filtrar por estado de cifrado
CREATE INDEX IF NOT EXISTS idx_tables_encrypted
    ON tables(is_encrypted) WHERE is_encrypted = TRUE;

CREATE INDEX IF NOT EXISTS idx_tables_project_encrypted
    ON tables(project_id, is_encrypted);

COMMENT ON COLUMN tables.name_encrypted IS
    'Nombre de la tabla cifrado (AES-256-GCM, base64)';
COMMENT ON COLUMN tables.name_nonce IS
    'Nonce único usado para cifrar el nombre (96 bits, base64)';
COMMENT ON COLUMN tables.is_encrypted IS
    'Indica si los datos de esta tabla están cifrados';

-- ============================================================================
-- 3. AGREGAR SOPORTE DE CIFRADO A TABLA "columns"
-- ============================================================================

-- Nombre cifrado
ALTER TABLE columns ADD COLUMN IF NOT EXISTS
    name_encrypted TEXT;

ALTER TABLE columns ADD COLUMN IF NOT EXISTS
    name_nonce TEXT;

-- Tipo de dato cifrado
ALTER TABLE columns ADD COLUMN IF NOT EXISTS
    data_type_encrypted TEXT;

ALTER TABLE columns ADD COLUMN IF NOT EXISTS
    data_type_nonce TEXT;

-- Flag de cifrado
ALTER TABLE columns ADD COLUMN IF NOT EXISTS
    is_encrypted BOOLEAN DEFAULT FALSE;

-- Índices
CREATE INDEX IF NOT EXISTS idx_columns_encrypted
    ON columns(is_encrypted) WHERE is_encrypted = TRUE;

CREATE INDEX IF NOT EXISTS idx_columns_table_encrypted
    ON columns(table_id, is_encrypted);

COMMENT ON COLUMN columns.name_encrypted IS
    'Nombre de la columna cifrado (AES-256-GCM, base64)';
COMMENT ON COLUMN columns.name_nonce IS
    'Nonce único para el nombre de la columna';
COMMENT ON COLUMN columns.data_type_encrypted IS
    'Tipo de dato cifrado (ej: VARCHAR(255) cifrado)';
COMMENT ON COLUMN columns.data_type_nonce IS
    'Nonce único para el tipo de dato';
COMMENT ON COLUMN columns.is_encrypted IS
    'Indica si los datos de esta columna están cifrados';

-- ============================================================================
-- 4. AGREGAR SOPORTE DE CIFRADO A TABLA "mappings"
-- ============================================================================

-- Origin table y column
ALTER TABLE mappings ADD COLUMN IF NOT EXISTS
    origin_table_encrypted TEXT;

ALTER TABLE mappings ADD COLUMN IF NOT EXISTS
    origin_table_nonce TEXT;

ALTER TABLE mappings ADD COLUMN IF NOT EXISTS
    origin_column_encrypted TEXT;

ALTER TABLE mappings ADD COLUMN IF NOT EXISTS
    origin_column_nonce TEXT;

-- Destination table y column
ALTER TABLE mappings ADD COLUMN IF NOT EXISTS
    destination_table_encrypted TEXT;

ALTER TABLE mappings ADD COLUMN IF NOT EXISTS
    destination_table_nonce TEXT;

ALTER TABLE mappings ADD COLUMN IF NOT EXISTS
    destination_column_encrypted TEXT;

ALTER TABLE mappings ADD COLUMN IF NOT EXISTS
    destination_column_nonce TEXT;

-- Transformation logic (puede ser sensible)
ALTER TABLE mappings ADD COLUMN IF NOT EXISTS
    transformation_logic_encrypted TEXT;

ALTER TABLE mappings ADD COLUMN IF NOT EXISTS
    transformation_logic_nonce TEXT;

-- Flag de cifrado
ALTER TABLE mappings ADD COLUMN IF NOT EXISTS
    is_encrypted BOOLEAN DEFAULT FALSE;

-- Índices
CREATE INDEX IF NOT EXISTS idx_mappings_encrypted
    ON mappings(is_encrypted) WHERE is_encrypted = TRUE;

CREATE INDEX IF NOT EXISTS idx_mappings_project_encrypted
    ON mappings(project_id, is_encrypted);

COMMENT ON COLUMN mappings.origin_table_encrypted IS
    'Nombre de tabla origen cifrado';
COMMENT ON COLUMN mappings.transformation_logic_encrypted IS
    'Lógica de transformación cifrada (puede contener datos sensibles)';
COMMENT ON COLUMN mappings.is_encrypted IS
    'Indica si los datos de este mapping están cifrados';

-- ============================================================================
-- 5. AGREGAR SOPORTE DE CIFRADO A TABLA "entity_versions"
-- ============================================================================

-- Snapshot (estado completo de la entidad en JSON)
ALTER TABLE entity_versions ADD COLUMN IF NOT EXISTS
    snapshot_encrypted TEXT;

ALTER TABLE entity_versions ADD COLUMN IF NOT EXISTS
    snapshot_nonce TEXT;

-- Diff (diferencias respecto a versión anterior)
ALTER TABLE entity_versions ADD COLUMN IF NOT EXISTS
    diff_encrypted TEXT;

ALTER TABLE entity_versions ADD COLUMN IF NOT EXISTS
    diff_nonce TEXT;

-- Flag de cifrado
ALTER TABLE entity_versions ADD COLUMN IF NOT EXISTS
    is_encrypted BOOLEAN DEFAULT FALSE;

-- Índices
CREATE INDEX IF NOT EXISTS idx_versions_encrypted
    ON entity_versions(is_encrypted) WHERE is_encrypted = TRUE;

CREATE INDEX IF NOT EXISTS idx_versions_project_encrypted
    ON entity_versions(project_id, is_encrypted);

COMMENT ON COLUMN entity_versions.snapshot_encrypted IS
    'Snapshot de la entidad cifrado (JSON cifrado)';
COMMENT ON COLUMN entity_versions.diff_encrypted IS
    'Diferencias cifradas respecto a versión anterior';
COMMENT ON COLUMN entity_versions.is_encrypted IS
    'Indica si los snapshots de esta versión están cifrados';

-- ============================================================================
-- 6. AGREGAR SOPORTE DE CIFRADO A TABLA "comments"
-- ============================================================================

-- Contenido del comentario
ALTER TABLE comments ADD COLUMN IF NOT EXISTS
    content_encrypted TEXT;

ALTER TABLE comments ADD COLUMN IF NOT EXISTS
    content_nonce TEXT;

-- Flag de cifrado
ALTER TABLE comments ADD COLUMN IF NOT EXISTS
    is_encrypted BOOLEAN DEFAULT FALSE;

-- Índices
CREATE INDEX IF NOT EXISTS idx_comments_encrypted
    ON comments(is_encrypted) WHERE is_encrypted = TRUE;

CREATE INDEX IF NOT EXISTS idx_comments_project_encrypted
    ON comments(project_id, is_encrypted);

COMMENT ON COLUMN comments.content_encrypted IS
    'Contenido del comentario cifrado';
COMMENT ON COLUMN comments.content_nonce IS
    'Nonce único para el contenido del comentario';
COMMENT ON COLUMN comments.is_encrypted IS
    'Indica si el contenido de este comentario está cifrado';

-- ============================================================================
-- 7. FUNCIONES AUXILIARES
-- ============================================================================

-- Función para obtener estadísticas de cifrado de un proyecto
CREATE OR REPLACE FUNCTION get_project_encryption_stats(p_project_id UUID)
RETURNS TABLE (
    tables_total INTEGER,
    tables_encrypted INTEGER,
    columns_total INTEGER,
    columns_encrypted INTEGER,
    mappings_total INTEGER,
    mappings_encrypted INTEGER,
    versions_total INTEGER,
    versions_encrypted INTEGER,
    comments_total INTEGER,
    comments_encrypted INTEGER,
    encryption_percentage NUMERIC
) AS $$
DECLARE
    total_items INTEGER;
    encrypted_items INTEGER;
BEGIN
    -- Contar tablas
    SELECT COUNT(*), COUNT(*) FILTER (WHERE is_encrypted = TRUE)
    INTO tables_total, tables_encrypted
    FROM tables WHERE project_id = p_project_id;

    -- Contar columnas
    SELECT COUNT(*), COUNT(*) FILTER (WHERE c.is_encrypted = TRUE)
    INTO columns_total, columns_encrypted
    FROM columns c
    INNER JOIN tables t ON c.table_id = t.id
    WHERE t.project_id = p_project_id;

    -- Contar mappings
    SELECT COUNT(*), COUNT(*) FILTER (WHERE is_encrypted = TRUE)
    INTO mappings_total, mappings_encrypted
    FROM mappings WHERE project_id = p_project_id;

    -- Contar versiones
    SELECT COUNT(*), COUNT(*) FILTER (WHERE is_encrypted = TRUE)
    INTO versions_total, versions_encrypted
    FROM entity_versions WHERE project_id = p_project_id;

    -- Contar comentarios
    SELECT COUNT(*), COUNT(*) FILTER (WHERE is_encrypted = TRUE)
    INTO comments_total, comments_encrypted
    FROM comments WHERE project_id = p_project_id;

    -- Calcular porcentaje total
    total_items := tables_total + columns_total + mappings_total +
                   versions_total + comments_total;
    encrypted_items := tables_encrypted + columns_encrypted +
                       mappings_encrypted + versions_encrypted + comments_encrypted;

    IF total_items > 0 THEN
        encryption_percentage := (encrypted_items::NUMERIC / total_items::NUMERIC) * 100;
    ELSE
        encryption_percentage := 0;
    END IF;

    RETURN QUERY SELECT
        tables_total, tables_encrypted,
        columns_total, columns_encrypted,
        mappings_total, mappings_encrypted,
        versions_total, versions_encrypted,
        comments_total, comments_encrypted,
        ROUND(encryption_percentage, 2);
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_project_encryption_stats IS
    'Obtiene estadísticas de cifrado para un proyecto (cuántos items están cifrados)';

-- Función para limpiar datos cifrados antiguos (data retention)
CREATE OR REPLACE FUNCTION purge_old_encrypted_data(
    p_project_id UUID,
    p_retention_days INTEGER DEFAULT 90
)
RETURNS TABLE (
    versions_deleted INTEGER,
    comments_deleted INTEGER,
    activity_deleted INTEGER
) AS $$
DECLARE
    v_deleted INTEGER := 0;
    c_deleted INTEGER := 0;
    a_deleted INTEGER := 0;
    cutoff_date TIMESTAMP;
BEGIN
    cutoff_date := NOW() - (p_retention_days || ' days')::INTERVAL;

    -- Eliminar snapshots de versiones antiguas (mantener última versión siempre)
    WITH to_delete AS (
        SELECT ev.id
        FROM entity_versions ev
        WHERE ev.project_id = p_project_id
          AND ev.is_encrypted = TRUE
          AND ev.created_at < cutoff_date
          AND ev.id NOT IN (
              -- Mantener última versión de cada entidad
              SELECT DISTINCT ON (entity_id) id
              FROM entity_versions
              WHERE project_id = p_project_id
              ORDER BY entity_id, created_at DESC
          )
    )
    DELETE FROM entity_versions
    WHERE id IN (SELECT id FROM to_delete);

    GET DIAGNOSTICS v_deleted = ROW_COUNT;

    -- Eliminar comentarios cifrados antiguos (opcionales)
    DELETE FROM comments
    WHERE project_id = p_project_id
      AND is_encrypted = TRUE
      AND created_at < cutoff_date
      AND is_resolved = TRUE;  -- Solo eliminar comentarios resueltos

    GET DIAGNOSTICS c_deleted = ROW_COUNT;

    -- Eliminar actividad antigua
    DELETE FROM project_activity
    WHERE project_id = p_project_id
      AND created_at < cutoff_date;

    GET DIAGNOSTICS a_deleted = ROW_COUNT;

    RETURN QUERY SELECT v_deleted, c_deleted, a_deleted;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION purge_old_encrypted_data IS
    'Elimina datos cifrados antiguos según política de retención (por defecto 90 días)';

-- ============================================================================
-- 8. TRIGGERS PARA ACTUALIZAR updated_at
-- ============================================================================

-- Trigger para project_encryption
CREATE OR REPLACE FUNCTION update_project_encryption_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW() AT TIME ZONE 'UTC';
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_project_encryption_timestamp
    BEFORE UPDATE ON project_encryption
    FOR EACH ROW
    EXECUTE FUNCTION update_project_encryption_timestamp();

-- ============================================================================
-- 9. PERMISOS Y SEGURIDAD
-- ============================================================================

-- Asegurar que los datos de cifrado solo sean accesibles por el backend
-- (Si usas roles específicos de PostgreSQL, configúralos aquí)

-- ============================================================================
-- FIN DE LA MIGRACIÓN
-- ============================================================================

-- Verificar que la migración se ejecutó correctamente
DO $$
BEGIN
    RAISE NOTICE '✅ Migración 003_encryption_infrastructure completada exitosamente';
    RAISE NOTICE '📊 Nueva tabla: project_encryption';
    RAISE NOTICE '🔐 Columnas de cifrado agregadas a: tables, columns, mappings, entity_versions, comments';
    RAISE NOTICE '⚡ Funciones auxiliares creadas: get_project_encryption_stats, purge_old_encrypted_data';
END $$;
