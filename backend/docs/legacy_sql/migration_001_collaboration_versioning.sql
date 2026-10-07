-- ============================================================================
-- MIGRATION 001: Sistema de Colaboración y Control de Versiones
-- ============================================================================
-- Autor: Sistema de Colaboración
-- Fecha: 2025-01-22
-- Descripción: Agrega tablas para notificaciones, versiones, locks,
--              comentarios y actividad del proyecto
-- ============================================================================

-- ============================================================================
-- 1. TABLA DE NOTIFICACIONES
-- ============================================================================
-- Referenciada en notifications.py pero NO estaba en schema.sql

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    notification_kind VARCHAR(50) NOT NULL, -- 'system', 'invitation', 'mention', 'comment', 'version'
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    invitation_id UUID,
    title VARCHAR(160) NOT NULL,
    body TEXT NOT NULL,
    link_url VARCHAR(500),
    data JSONB,
    actions JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
    read_at TIMESTAMP,
    expires_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_notifications_recipient ON notifications(recipient_id);
CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(recipient_id, read_at) WHERE read_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_notifications_project ON notifications(project_id);
CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at DESC);

COMMENT ON TABLE notifications IS 'Sistema de notificaciones para invitaciones, menciones y eventos';
COMMENT ON COLUMN notifications.notification_kind IS 'Tipo: system, invitation, mention, comment, version';
COMMENT ON COLUMN notifications.data IS 'Datos adicionales en formato JSON';
COMMENT ON COLUMN notifications.actions IS 'Acciones disponibles (aceptar, rechazar, etc.)';

-- ============================================================================
-- 2. TABLA DE VERSIONES (VERSION CONTROL)
-- ============================================================================

CREATE TABLE IF NOT EXISTS entity_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hash VARCHAR(64) NOT NULL UNIQUE, -- SHA-256 del snapshot para deduplicación
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    entity_id UUID NOT NULL, -- ID de la entidad versionada (mapping, table, etc)
    entity_type VARCHAR(50) NOT NULL, -- 'mapping', 'table', 'column', 'transformation'
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE SET NULL,
    version_number INTEGER NOT NULL, -- Autoincremental por entidad
    change_type VARCHAR(20) NOT NULL, -- 'create', 'update', 'delete'
    message TEXT, -- Commit message opcional
    snapshot JSONB NOT NULL, -- Estado completo de la entidad
    diff JSONB, -- Diferencias respecto a versión anterior
    parent_version_id UUID REFERENCES entity_versions(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),

    -- Constraint: version_number debe ser único por entidad
    UNIQUE(entity_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_versions_project ON entity_versions(project_id);
CREATE INDEX IF NOT EXISTS idx_versions_entity ON entity_versions(entity_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_versions_user ON entity_versions(user_id);
CREATE INDEX IF NOT EXISTS idx_versions_hash ON entity_versions(hash);
CREATE INDEX IF NOT EXISTS idx_versions_created ON entity_versions(created_at DESC);

COMMENT ON TABLE entity_versions IS 'Historial de versiones de todas las entidades del sistema';
COMMENT ON COLUMN entity_versions.hash IS 'SHA-256 del snapshot para detectar duplicados';
COMMENT ON COLUMN entity_versions.snapshot IS 'Estado completo de la entidad en JSON';
COMMENT ON COLUMN entity_versions.diff IS 'Diferencias con la versión anterior';

-- ============================================================================
-- 3. TABLA DE TAGS DE VERSIONES
-- ============================================================================

CREATE TABLE IF NOT EXISTS version_tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id UUID NOT NULL REFERENCES entity_versions(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    color VARCHAR(7), -- Hex color: #FF5733
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),

    -- Tag name debe ser único por proyecto
    UNIQUE(project_id, name)
);

CREATE INDEX IF NOT EXISTS idx_version_tags_version ON version_tags(version_id);
CREATE INDEX IF NOT EXISTS idx_version_tags_project ON version_tags(project_id);

COMMENT ON TABLE version_tags IS 'Tags/etiquetas para marcar versiones importantes';

-- ============================================================================
-- 4. TABLA DE LOCKS (BLOQUEOS DE EDICIÓN)
-- ============================================================================

CREATE TABLE IF NOT EXISTS entity_locks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    entity_type VARCHAR(50) NOT NULL, -- 'mapping', 'table', 'column'
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    acquired_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
    expires_at TIMESTAMP NOT NULL,
    last_heartbeat TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),

    -- Solo un lock por entidad
    UNIQUE(entity_id, entity_type)
);

CREATE INDEX IF NOT EXISTS idx_locks_entity ON entity_locks(entity_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_locks_user ON entity_locks(user_id);
CREATE INDEX IF NOT EXISTS idx_locks_project ON entity_locks(project_id);
CREATE INDEX IF NOT EXISTS idx_locks_expires ON entity_locks(expires_at);

COMMENT ON TABLE entity_locks IS 'Bloqueos de edición para prevenir conflictos concurrentes';
COMMENT ON COLUMN entity_locks.last_heartbeat IS 'Último ping del cliente para mantener el lock activo';

-- ============================================================================
-- 5. TABLA DE COMENTARIOS
-- ============================================================================

CREATE TABLE IF NOT EXISTS comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL,
    entity_type VARCHAR(50) NOT NULL, -- 'mapping', 'table', 'column', 'project'
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE SET NULL,
    parent_id UUID REFERENCES comments(id) ON DELETE CASCADE, -- Para replies
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
    updated_at TIMESTAMP,
    is_edited BOOLEAN DEFAULT FALSE,
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_by UUID REFERENCES users(id) ON DELETE SET NULL,
    resolved_at TIMESTAMP,
    mentions JSONB, -- Array de user_ids mencionados: ["uuid1", "uuid2"]

    -- Validación: content no puede estar vacío
    CONSTRAINT check_comment_not_empty CHECK (LENGTH(TRIM(content)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_comments_entity ON comments(entity_id, entity_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_comments_project ON comments(project_id);
CREATE INDEX IF NOT EXISTS idx_comments_user ON comments(user_id);
CREATE INDEX IF NOT EXISTS idx_comments_parent ON comments(parent_id);
CREATE INDEX IF NOT EXISTS idx_comments_resolved ON comments(is_resolved);

COMMENT ON TABLE comments IS 'Comentarios y discusiones sobre entidades del proyecto';
COMMENT ON COLUMN comments.mentions IS 'Array JSON de user_ids mencionados con @';

-- ============================================================================
-- 6. TABLA DE REACCIONES A COMENTARIOS
-- ============================================================================

CREATE TABLE IF NOT EXISTS comment_reactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    comment_id UUID NOT NULL REFERENCES comments(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    emoji VARCHAR(10) NOT NULL, -- Emoji unicode
    created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),

    -- Un usuario solo puede reaccionar una vez con el mismo emoji
    UNIQUE(comment_id, user_id, emoji)
);

CREATE INDEX IF NOT EXISTS idx_reactions_comment ON comment_reactions(comment_id);
CREATE INDEX IF NOT EXISTS idx_reactions_user ON comment_reactions(user_id);

COMMENT ON TABLE comment_reactions IS 'Reacciones emoji a comentarios';

-- ============================================================================
-- 7. TABLA DE LECTURAS DE COMENTARIOS
-- ============================================================================

CREATE TABLE IF NOT EXISTS comment_reads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    comment_id UUID NOT NULL REFERENCES comments(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    read_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),

    -- Un usuario solo puede marcar un comentario como leído una vez
    UNIQUE(comment_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_comment_reads_user ON comment_reads(user_id, read_at DESC);
CREATE INDEX IF NOT EXISTS idx_comment_reads_comment ON comment_reads(comment_id);

COMMENT ON TABLE comment_reads IS 'Tracking de comentarios leídos por usuario';

-- ============================================================================
-- 8. TABLA DE ACTIVIDAD DEL PROYECTO
-- ============================================================================

CREATE TABLE IF NOT EXISTS project_activity (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    activity_type VARCHAR(50) NOT NULL, -- 'version_created', 'comment_added', 'member_added', etc
    entity_id UUID,
    entity_type VARCHAR(50),
    description TEXT NOT NULL,
    metadata JSONB, -- Datos adicionales del evento
    created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
);

CREATE INDEX IF NOT EXISTS idx_activity_project ON project_activity(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_user ON project_activity(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_type ON project_activity(activity_type);
CREATE INDEX IF NOT EXISTS idx_activity_entity ON project_activity(entity_id, entity_type);

COMMENT ON TABLE project_activity IS 'Feed de actividad del proyecto para auditoría y timeline';
COMMENT ON COLUMN project_activity.metadata IS 'Datos adicionales del evento en JSON';

-- ============================================================================
-- 9. EXTENDER TABLA project_members CON CAMPOS FALTANTES
-- ============================================================================

-- Agregar campo 'added_by' que se usa en notifications.py pero no existe
ALTER TABLE project_members
ADD COLUMN IF NOT EXISTS added_by UUID REFERENCES users(id) ON DELETE SET NULL;

COMMENT ON COLUMN project_members.added_by IS 'Usuario que añadió a este miembro al proyecto';

-- ============================================================================
-- 10. FUNCIONES AUXILIARES
-- ============================================================================

-- Función para limpiar locks expirados
CREATE OR REPLACE FUNCTION cleanup_expired_locks()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM entity_locks
    WHERE expires_at < NOW();

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_expired_locks IS 'Limpia locks que han expirado';

-- Función para obtener el siguiente número de versión
CREATE OR REPLACE FUNCTION get_next_version_number(p_entity_id UUID)
RETURNS INTEGER AS $$
DECLARE
    next_version INTEGER;
BEGIN
    SELECT COALESCE(MAX(version_number), 0) + 1
    INTO next_version
    FROM entity_versions
    WHERE entity_id = p_entity_id;

    RETURN next_version;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_next_version_number IS 'Obtiene el siguiente número de versión para una entidad';

-- Función para crear actividad automáticamente al crear versión
CREATE OR REPLACE FUNCTION log_version_activity()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO project_activity (
        project_id,
        user_id,
        activity_type,
        entity_id,
        entity_type,
        description,
        metadata
    ) VALUES (
        NEW.project_id,
        NEW.user_id,
        'version_created',
        NEW.entity_id,
        NEW.entity_type,
        CASE
            WHEN NEW.change_type = 'create' THEN 'creó'
            WHEN NEW.change_type = 'update' THEN 'actualizó'
            WHEN NEW.change_type = 'delete' THEN 'eliminó'
        END || ' ' || NEW.entity_type,
        jsonb_build_object(
            'version_id', NEW.id,
            'version_number', NEW.version_number,
            'message', NEW.message
        )
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger para log automático de versiones
DROP TRIGGER IF EXISTS trigger_log_version_activity ON entity_versions;
CREATE TRIGGER trigger_log_version_activity
    AFTER INSERT ON entity_versions
    FOR EACH ROW
    EXECUTE FUNCTION log_version_activity();

-- Función para crear actividad automáticamente al crear comentario
CREATE OR REPLACE FUNCTION log_comment_activity()
RETURNS TRIGGER AS $$
BEGIN
    -- Solo loguear comentarios principales, no replies
    IF NEW.parent_id IS NULL THEN
        INSERT INTO project_activity (
            project_id,
            user_id,
            activity_type,
            entity_id,
            entity_type,
            description,
            metadata
        ) VALUES (
            NEW.project_id,
            NEW.user_id,
            'comment_added',
            NEW.entity_id,
            NEW.entity_type,
            'comentó en ' || NEW.entity_type,
            jsonb_build_object(
                'comment_id', NEW.id,
                'content_preview', LEFT(NEW.content, 100)
            )
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger para log automático de comentarios
DROP TRIGGER IF EXISTS trigger_log_comment_activity ON comments;
CREATE TRIGGER trigger_log_comment_activity
    AFTER INSERT ON comments
    FOR EACH ROW
    EXECUTE FUNCTION log_comment_activity();

-- ============================================================================
-- 11. VISTAS ÚTILES
-- ============================================================================

-- Vista de versiones con información de usuario
CREATE OR REPLACE VIEW v_entity_versions_with_user AS
SELECT
    ev.*,
    u.username,
    u.email as user_email,
    (SELECT COUNT(*) FROM version_tags WHERE version_id = ev.id) as tags_count
FROM entity_versions ev
LEFT JOIN users u ON ev.user_id = u.id;

COMMENT ON VIEW v_entity_versions_with_user IS 'Versiones con datos del usuario que las creó';

-- Vista de comentarios con información completa
CREATE OR REPLACE VIEW v_comments_with_details AS
SELECT
    c.*,
    u.username,
    u.email as user_email,
    resolver.username as resolved_by_username,
    (SELECT COUNT(*) FROM comment_reactions WHERE comment_id = c.id) as reactions_count,
    (SELECT COUNT(*) FROM comments WHERE parent_id = c.id) as replies_count
FROM comments c
LEFT JOIN users u ON c.user_id = u.id
LEFT JOIN users resolver ON c.resolved_by = resolver.id;

COMMENT ON VIEW v_comments_with_details IS 'Comentarios con datos de usuario y estadísticas';

-- Vista de locks activos con información de usuario
CREATE OR REPLACE VIEW v_active_locks AS
SELECT
    el.*,
    u.username,
    u.email as user_email,
    EXTRACT(EPOCH FROM (el.expires_at - NOW())) as seconds_remaining
FROM entity_locks el
LEFT JOIN users u ON el.user_id = u.id
WHERE el.expires_at > NOW();

COMMENT ON VIEW v_active_locks IS 'Locks activos (no expirados) con información del usuario';

-- ============================================================================
-- 12. DATOS INICIALES
-- ============================================================================

-- Insertar tipos de actividad comunes (opcional, para referencia)
-- Estos son solo los tipos más comunes que se usarán
-- Los valores reales son strings libres en la columna activity_type

-- ============================================================================
-- FIN DE MIGRACIÓN
-- ============================================================================

-- Verificación de integridad
DO $$
BEGIN
    RAISE NOTICE 'Migración 001 completada exitosamente';
    RAISE NOTICE 'Tablas creadas: notifications, entity_versions, version_tags, entity_locks, comments, comment_reactions, comment_reads, project_activity';
    RAISE NOTICE 'Funciones creadas: cleanup_expired_locks, get_next_version_number, log_version_activity, log_comment_activity';
    RAISE NOTICE 'Vistas creadas: v_entity_versions_with_user, v_comments_with_details, v_active_locks';
END $$;
