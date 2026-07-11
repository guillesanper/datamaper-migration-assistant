-- ============================================================================
-- MIGRATION 005: Sistema de Mappings Híbrido (Import + Connector)
-- ============================================================================
-- Descripción: Agrega soporte para modo híbrido con Import y Connector
-- Autor: DataMap Development Team
-- Fecha: 2025-01-31
-- Nivel: Nivel 2 - Modo híbrido con hashing SHA-256 y cifrado AES-256
--
-- Este script agrega:
-- 1. Columnas para diferenciar modos (import vs connector) por lado
-- 2. Columnas de hashing SHA-256 para modo connector
-- 3. Referencias a sesiones Redis y tablas importadas
-- 4. Constraints de integridad según el modo
-- 5. Índices para búsquedas eficientes
-- ============================================================================

-- ============================================================================
-- 1. AGREGAR COLUMNAS DE DIFERENCIACIÓN POR MODO - ORIGEN
-- ============================================================================

-- Tipo de fuente de datos para el origen
ALTER TABLE mappings ADD COLUMN IF NOT EXISTS
    origin_source_type VARCHAR(20) DEFAULT 'import';

-- Hashing SHA-256 para modo connector (one-way, irreversible)
ALTER TABLE mappings ADD COLUMN IF NOT EXISTS
    origin_table_hash VARCHAR(64);

ALTER TABLE mappings ADD COLUMN IF NOT EXISTS
    origin_column_hash VARCHAR(64);

-- Referencia a sesión Redis para modo connector
ALTER TABLE mappings ADD COLUMN IF NOT EXISTS
    origin_session_id UUID;

-- Referencia a tabla importada para modo import
ALTER TABLE mappings ADD COLUMN IF NOT EXISTS
    origin_table_id INTEGER REFERENCES tables(id) ON DELETE CASCADE;

COMMENT ON COLUMN mappings.origin_source_type IS
    'Tipo de fuente de datos origen: ''import'' (esquema importado cifrado) o ''connector'' (conexión dinámica con hash)';
COMMENT ON COLUMN mappings.origin_table_hash IS
    'Hash SHA-256 del nombre de tabla origen (modo connector, one-way, irreversible)';
COMMENT ON COLUMN mappings.origin_column_hash IS
    'Hash SHA-256 del nombre de columna origen (modo connector, one-way, irreversible)';
COMMENT ON COLUMN mappings.origin_session_id IS
    'ID de sesión Redis para resolver hashes (modo connector, TTL 3-24h)';
COMMENT ON COLUMN mappings.origin_table_id IS
    'FK a tabla importada en BD (modo import, permite cifrado reversible)';

-- ============================================================================
-- 2. AGREGAR COLUMNAS DE DIFERENCIACIÓN POR MODO - DESTINO
-- ============================================================================

-- Tipo de fuente de datos para el destino
ALTER TABLE mappings ADD COLUMN IF NOT EXISTS
    destination_source_type VARCHAR(20) DEFAULT 'import';

-- Hashing SHA-256 para modo connector (one-way, irreversible)
ALTER TABLE mappings ADD COLUMN IF NOT EXISTS
    destination_table_hash VARCHAR(64);

ALTER TABLE mappings ADD COLUMN IF NOT EXISTS
    destination_column_hash VARCHAR(64);

-- Referencia a sesión Redis para modo connector
ALTER TABLE mappings ADD COLUMN IF NOT EXISTS
    destination_session_id UUID;

-- Referencia a tabla importada para modo import
ALTER TABLE mappings ADD COLUMN IF NOT EXISTS
    destination_table_id INTEGER REFERENCES tables(id) ON DELETE CASCADE;

COMMENT ON COLUMN mappings.destination_source_type IS
    'Tipo de fuente de datos destino: ''import'' (esquema importado cifrado) o ''connector'' (conexión dinámica con hash)';
COMMENT ON COLUMN mappings.destination_table_hash IS
    'Hash SHA-256 del nombre de tabla destino (modo connector, one-way, irreversible)';
COMMENT ON COLUMN mappings.destination_column_hash IS
    'Hash SHA-256 del nombre de columna destino (modo connector, one-way, irreversible)';
COMMENT ON COLUMN mappings.destination_session_id IS
    'ID de sesión Redis para resolver hashes (modo connector, TTL 3-24h)';
COMMENT ON COLUMN mappings.destination_table_id IS
    'FK a tabla importada en BD (modo import, permite cifrado reversible)';

-- ============================================================================
-- 3. CONSTRAINTS DE INTEGRIDAD SEGÚN MODO
-- ============================================================================

-- Constraint para origen: si es 'connector', debe tener session_id y hashes
ALTER TABLE mappings DROP CONSTRAINT IF EXISTS chk_origin_connector_requirements;
ALTER TABLE mappings ADD CONSTRAINT chk_origin_connector_requirements
    CHECK (
        origin_source_type != 'connector' OR (
            origin_session_id IS NOT NULL AND
            origin_table_hash IS NOT NULL
        )
    );

-- Constraint para origen: si es 'import', debe tener table_id o nombre (plaintext/encrypted)
ALTER TABLE mappings DROP CONSTRAINT IF EXISTS chk_origin_import_requirements;
ALTER TABLE mappings ADD CONSTRAINT chk_origin_import_requirements
    CHECK (
        origin_source_type != 'import' OR (
            origin_table_id IS NOT NULL OR
            origin_table IS NOT NULL OR
            origin_table_encrypted IS NOT NULL
        )
    );

-- Constraint para destino: si es 'connector', debe tener session_id y hashes
ALTER TABLE mappings DROP CONSTRAINT IF EXISTS chk_destination_connector_requirements;
ALTER TABLE mappings ADD CONSTRAINT chk_destination_connector_requirements
    CHECK (
        destination_source_type != 'connector' OR (
            destination_session_id IS NOT NULL AND
            destination_table_hash IS NOT NULL
        )
    );

-- Constraint para destino: si es 'import', debe tener table_id o nombre (plaintext/encrypted)
ALTER TABLE mappings DROP CONSTRAINT IF EXISTS chk_destination_import_requirements;
ALTER TABLE mappings ADD CONSTRAINT chk_destination_import_requirements
    CHECK (
        destination_source_type != 'import' OR (
            destination_table_id IS NOT NULL OR
            destination_table IS NOT NULL OR
            destination_table_encrypted IS NOT NULL
        )
    );

-- Constraint para validar valores de source_type
ALTER TABLE mappings DROP CONSTRAINT IF EXISTS chk_origin_source_type_values;
ALTER TABLE mappings ADD CONSTRAINT chk_origin_source_type_values
    CHECK (origin_source_type IN ('import', 'connector'));

ALTER TABLE mappings DROP CONSTRAINT IF EXISTS chk_destination_source_type_values;
ALTER TABLE mappings ADD CONSTRAINT chk_destination_source_type_values
    CHECK (destination_source_type IN ('import', 'connector'));

COMMENT ON CONSTRAINT chk_origin_connector_requirements ON mappings IS
    'Si origin_source_type=''connector'', debe tener origin_session_id y origin_table_hash';
COMMENT ON CONSTRAINT chk_origin_import_requirements ON mappings IS
    'Si origin_source_type=''import'', debe tener origin_table_id o origin_table o origin_table_encrypted';
COMMENT ON CONSTRAINT chk_destination_connector_requirements ON mappings IS
    'Si destination_source_type=''connector'', debe tener destination_session_id y destination_table_hash';
COMMENT ON CONSTRAINT chk_destination_import_requirements ON mappings IS
    'Si destination_source_type=''import'', debe tener destination_table_id o destination_table o destination_table_encrypted';

-- ============================================================================
-- 4. ÍNDICES PARA BÚSQUEDAS EFICIENTES
-- ============================================================================

-- Índices para filtrar por tipo de fuente
CREATE INDEX IF NOT EXISTS idx_mappings_origin_source_type
    ON mappings(origin_source_type);

CREATE INDEX IF NOT EXISTS idx_mappings_destination_source_type
    ON mappings(destination_source_type);

-- Índices para sesiones (solo donde sean NOT NULL)
CREATE INDEX IF NOT EXISTS idx_mappings_origin_session_id
    ON mappings(origin_session_id)
    WHERE origin_session_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_mappings_destination_session_id
    ON mappings(destination_session_id)
    WHERE destination_session_id IS NOT NULL;

-- Índices para FKs de tablas importadas (solo donde sean NOT NULL)
CREATE INDEX IF NOT EXISTS idx_mappings_origin_table_id
    ON mappings(origin_table_id)
    WHERE origin_table_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_mappings_destination_table_id
    ON mappings(destination_table_id)
    WHERE destination_table_id IS NOT NULL;

-- Índices compuestos para búsqueda por hashes (modo connector)
CREATE INDEX IF NOT EXISTS idx_mappings_origin_hashes
    ON mappings(origin_table_hash, origin_column_hash)
    WHERE origin_source_type = 'connector';

CREATE INDEX IF NOT EXISTS idx_mappings_destination_hashes
    ON mappings(destination_table_hash, destination_column_hash)
    WHERE destination_source_type = 'connector';

-- Índice compuesto para proyectos con ambos modos
CREATE INDEX IF NOT EXISTS idx_mappings_project_modes
    ON mappings(project_id, origin_source_type, destination_source_type);

COMMENT ON INDEX idx_mappings_origin_source_type IS
    'Índice para filtrar mappings por tipo de fuente origen';
COMMENT ON INDEX idx_mappings_origin_session_id IS
    'Índice para buscar mappings por sesión Redis origen (solo modo connector)';
COMMENT ON INDEX idx_mappings_origin_hashes IS
    'Índice compuesto para búsqueda eficiente por hashes SHA-256 origen';
COMMENT ON INDEX idx_mappings_project_modes IS
    'Índice para consultas que filtran por proyecto y combinación de modos';

-- ============================================================================
-- 5. MIGRACIÓN DE DATOS EXISTENTES
-- ============================================================================

-- Migrar mappings existentes a modo 'import' (retrocompatibilidad)
UPDATE mappings
SET
    origin_source_type = 'import',
    destination_source_type = 'import'
WHERE
    origin_source_type IS NULL
    OR destination_source_type IS NULL;

-- ============================================================================
-- 6. FUNCIONES AUXILIARES
-- ============================================================================

-- Función para obtener estadísticas de uso de modos por proyecto
CREATE OR REPLACE FUNCTION get_project_mapping_mode_stats(p_project_id UUID)
RETURNS TABLE (
    total_mappings INTEGER,
    import_import INTEGER,
    import_connector INTEGER,
    connector_import INTEGER,
    connector_connector INTEGER,
    hybrid_percentage NUMERIC
) AS $$
DECLARE
    v_total INTEGER;
    v_ii INTEGER;
    v_ic INTEGER;
    v_ci INTEGER;
    v_cc INTEGER;
    v_hybrid INTEGER;
BEGIN
    -- Contar por combinación de modos
    SELECT
        COUNT(*),
        COUNT(*) FILTER (WHERE origin_source_type = 'import' AND destination_source_type = 'import'),
        COUNT(*) FILTER (WHERE origin_source_type = 'import' AND destination_source_type = 'connector'),
        COUNT(*) FILTER (WHERE origin_source_type = 'connector' AND destination_source_type = 'import'),
        COUNT(*) FILTER (WHERE origin_source_type = 'connector' AND destination_source_type = 'connector')
    INTO v_total, v_ii, v_ic, v_ci, v_cc
    FROM mappings
    WHERE project_id = p_project_id;

    -- Calcular porcentaje de mappings híbridos
    v_hybrid := v_ic + v_ci;

    RETURN QUERY SELECT
        v_total,
        v_ii,
        v_ic,
        v_ci,
        v_cc,
        CASE
            WHEN v_total > 0 THEN ROUND((v_hybrid::NUMERIC / v_total::NUMERIC) * 100, 2)
            ELSE 0
        END;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_project_mapping_mode_stats IS
    'Obtiene estadísticas de uso de modos (import/connector) en mappings de un proyecto';

-- Función para verificar si un mapping tiene sesiones expiradas
CREATE OR REPLACE FUNCTION check_mapping_sessions_valid(p_mapping_id UUID)
RETURNS TABLE (
    origin_session_valid BOOLEAN,
    destination_session_valid BOOLEAN,
    both_valid BOOLEAN
) AS $$
DECLARE
    v_origin_type VARCHAR(20);
    v_dest_type VARCHAR(20);
    v_origin_session UUID;
    v_dest_session UUID;
    v_origin_valid BOOLEAN := TRUE;
    v_dest_valid BOOLEAN := TRUE;
BEGIN
    -- Obtener información del mapping
    SELECT
        origin_source_type,
        destination_source_type,
        origin_session_id,
        destination_session_id
    INTO
        v_origin_type,
        v_dest_type,
        v_origin_session,
        v_dest_session
    FROM mappings
    WHERE id = p_mapping_id;

    -- Si es connector, verificar sesión (aquí solo verificamos que exista el ID)
    -- La verificación real de TTL se hace en Redis desde el backend
    IF v_origin_type = 'connector' THEN
        v_origin_valid := (v_origin_session IS NOT NULL);
    END IF;

    IF v_dest_type = 'connector' THEN
        v_dest_valid := (v_dest_session IS NOT NULL);
    END IF;

    RETURN QUERY SELECT
        v_origin_valid,
        v_dest_valid,
        (v_origin_valid AND v_dest_valid);
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION check_mapping_sessions_valid IS
    'Verifica si las sesiones de un mapping están configuradas correctamente (verificación básica de IDs)';

-- Función para limpiar mappings con sesiones huérfanas
CREATE OR REPLACE FUNCTION cleanup_orphaned_connector_mappings(
    p_valid_session_ids UUID[]
)
RETURNS TABLE (
    mappings_affected INTEGER
) AS $$
DECLARE
    v_deleted INTEGER := 0;
BEGIN
    -- Marcar o eliminar mappings cuyas sesiones ya no existen
    -- (Esta es una operación de mantenimiento que el backend puede llamar periódicamente)

    -- Por seguridad, solo reportamos, no eliminamos automáticamente
    SELECT COUNT(*)
    INTO v_deleted
    FROM mappings
    WHERE (
        (origin_source_type = 'connector' AND NOT (origin_session_id = ANY(p_valid_session_ids)))
        OR
        (destination_source_type = 'connector' AND NOT (destination_session_id = ANY(p_valid_session_ids)))
    );

    RETURN QUERY SELECT v_deleted;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_orphaned_connector_mappings IS
    'Identifica mappings con sesiones que ya no existen en Redis (para mantenimiento)';

-- ============================================================================
-- 7. VISTAS ÚTILES
-- ============================================================================

-- Vista para ver mappings con información de modo
CREATE OR REPLACE VIEW v_mappings_with_modes AS
SELECT
    m.id,
    m.project_id,
    m.origin_source_type,
    m.destination_source_type,
    -- Campos de origen según modo
    CASE
        WHEN m.origin_source_type = 'import' THEN COALESCE(m.origin_table, '[ENCRYPTED]')
        WHEN m.origin_source_type = 'connector' THEN LEFT(m.origin_table_hash, 8) || '...'
        ELSE NULL
    END AS origin_table_display,
    CASE
        WHEN m.origin_source_type = 'import' THEN COALESCE(m.origin_column, '[ENCRYPTED]')
        WHEN m.origin_source_type = 'connector' THEN LEFT(m.origin_column_hash, 8) || '...'
        ELSE NULL
    END AS origin_column_display,
    -- Campos de destino según modo
    CASE
        WHEN m.destination_source_type = 'import' THEN COALESCE(m.destination_table, '[ENCRYPTED]')
        WHEN m.destination_source_type = 'connector' THEN LEFT(m.destination_table_hash, 8) || '...'
        ELSE NULL
    END AS destination_table_display,
    CASE
        WHEN m.destination_source_type = 'import' THEN COALESCE(m.destination_column, '[ENCRYPTED]')
        WHEN m.destination_source_type = 'connector' THEN LEFT(m.destination_column_hash, 8) || '...'
        ELSE NULL
    END AS destination_column_display,
    -- Indicadores de modo
    CASE
        WHEN m.origin_source_type = 'import' AND m.destination_source_type = 'import' THEN 'IMPORT→IMPORT'
        WHEN m.origin_source_type = 'import' AND m.destination_source_type = 'connector' THEN 'IMPORT→CONNECTOR'
        WHEN m.origin_source_type = 'connector' AND m.destination_source_type = 'import' THEN 'CONNECTOR→IMPORT'
        WHEN m.origin_source_type = 'connector' AND m.destination_source_type = 'connector' THEN 'CONNECTOR→CONNECTOR'
        ELSE 'UNKNOWN'
    END AS mapping_mode,
    m.is_encrypted,
    m.created_at,
    m.updated_at
FROM mappings m;

COMMENT ON VIEW v_mappings_with_modes IS
    'Vista simplificada de mappings mostrando modo y valores truncados para visualización';

-- ============================================================================
-- 8. TRIGGERS PARA VALIDACIÓN ADICIONAL
-- ============================================================================

-- Trigger para evitar cambios de modo en mappings existentes (protección)
CREATE OR REPLACE FUNCTION prevent_mode_change()
RETURNS TRIGGER AS $$
BEGIN
    -- Permitir cambios si es INSERT
    IF TG_OP = 'INSERT' THEN
        RETURN NEW;
    END IF;

    -- En UPDATE, prevenir cambio de source_type
    IF OLD.origin_source_type != NEW.origin_source_type THEN
        RAISE EXCEPTION 'No se puede cambiar origin_source_type de un mapping existente (de % a %)',
            OLD.origin_source_type, NEW.origin_source_type;
    END IF;

    IF OLD.destination_source_type != NEW.destination_source_type THEN
        RAISE EXCEPTION 'No se puede cambiar destination_source_type de un mapping existente (de % a %)',
            OLD.destination_source_type, NEW.destination_source_type;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_prevent_mapping_mode_change
    BEFORE UPDATE ON mappings
    FOR EACH ROW
    EXECUTE FUNCTION prevent_mode_change();

COMMENT ON TRIGGER trigger_prevent_mapping_mode_change ON mappings IS
    'Previene cambios de source_type en mappings existentes (protección de integridad)';

-- ============================================================================
-- 9. PERMISOS Y SEGURIDAD
-- ============================================================================

-- Los hashes SHA-256 son one-way, por lo que no hay riesgo de exposición
-- Las sesiones Redis ya tienen su propia capa de seguridad
-- Los datos cifrados con AES-256-GCM siguen las políticas de la migración 003

-- ============================================================================
-- FIN DE LA MIGRACIÓN
-- ============================================================================

-- Verificar que la migración se ejecutó correctamente
DO $$
DECLARE
    v_column_count INTEGER;
    v_constraint_count INTEGER;
    v_index_count INTEGER;
BEGIN
    -- Contar columnas nuevas
    SELECT COUNT(*)
    INTO v_column_count
    FROM information_schema.columns
    WHERE table_name = 'mappings'
        AND column_name IN (
            'origin_source_type', 'origin_table_hash', 'origin_column_hash',
            'origin_session_id', 'origin_table_id',
            'destination_source_type', 'destination_table_hash', 'destination_column_hash',
            'destination_session_id', 'destination_table_id'
        );

    -- Contar constraints nuevos
    SELECT COUNT(*)
    INTO v_constraint_count
    FROM information_schema.table_constraints
    WHERE table_name = 'mappings'
        AND constraint_name LIKE 'chk_%_requirements'
           OR constraint_name LIKE 'chk_%_source_type_values';

    -- Contar índices nuevos
    SELECT COUNT(*)
    INTO v_index_count
    FROM pg_indexes
    WHERE tablename = 'mappings'
        AND indexname LIKE 'idx_mappings_%'
        AND indexname IN (
            'idx_mappings_origin_source_type',
            'idx_mappings_destination_source_type',
            'idx_mappings_origin_session_id',
            'idx_mappings_destination_session_id',
            'idx_mappings_origin_table_id',
            'idx_mappings_destination_table_id',
            'idx_mappings_origin_hashes',
            'idx_mappings_destination_hashes',
            'idx_mappings_project_modes'
        );

    RAISE NOTICE '✅ Migración 005_mapping_source_types completada exitosamente';
    RAISE NOTICE '📊 Columnas agregadas: % de 10 esperadas', v_column_count;
    RAISE NOTICE '🔒 Constraints de integridad creados: %', v_constraint_count;
    RAISE NOTICE '⚡ Índices creados: % de 9 esperados', v_index_count;
    RAISE NOTICE '🔐 Modos soportados: IMPORT↔IMPORT, IMPORT↔CONNECTOR, CONNECTOR↔CONNECTOR';
    RAISE NOTICE '🔗 Referencias: tables(id), sesiones Redis (UUID)';
    RAISE NOTICE '🛡️ Hashing: SHA-256 (one-way, irreversible)';
    RAISE NOTICE '📈 Funciones creadas: get_project_mapping_mode_stats, check_mapping_sessions_valid, cleanup_orphaned_connector_mappings';
    RAISE NOTICE '👁️ Vista creada: v_mappings_with_modes';

    -- Validar que todo se creó correctamente
    IF v_column_count < 10 THEN
        RAISE WARNING '⚠️ No se crearon todas las columnas esperadas. Revisar logs.';
    END IF;
END $$;
