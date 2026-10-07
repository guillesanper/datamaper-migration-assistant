"""Funciones y triggers de BD que usa la app

Crea lo que ningun modelo ORM define pero que la app necesita:

- `log_version_activity` + trigger en `entity_versions`: registra `version_created` en
  `project_activity`. Portada de `utilities/migration_001_collaboration_versioning.sql`
  corrigiendo `restore`: el `CASE` no tenia `ELSE`, la descripcion quedaba NULL y
  `project_activity.description` es NOT NULL.
- `log_comment_activity` + trigger en `comments`: registra `comment_added` para comentarios
  raiz (los replies no generan actividad). Portada tal cual.
- `calculate_and_save_user_metrics(uuid)`: escrita desde cero (no existe en ninguna fuente);
  la llama `project_crud.py` con `SELECT calculate_and_save_user_metrics(:user_id)`.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-06

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Actividad al crear una version. `project_activity.id` lo genera el server_default del modelo.
    op.execute("""
    CREATE FUNCTION log_version_activity()
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
                WHEN NEW.change_type = 'restore' THEN 'restauró'
                ELSE 'modificó'
            END || ' ' || NEW.entity_type,
            jsonb_build_object(
                'version_id', NEW.id,
                'version_number', NEW.version_number,
                'message', NEW.message
            )
        );
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """)
    op.execute("""
    CREATE TRIGGER trigger_log_version_activity
        AFTER INSERT ON entity_versions
        FOR EACH ROW
        EXECUTE FUNCTION log_version_activity()
    """)

    # Actividad al crear un comentario: solo comentarios principales, no replies.
    op.execute("""
    CREATE FUNCTION log_comment_activity()
    RETURNS TRIGGER AS $$
    BEGIN
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
    $$ LANGUAGE plpgsql
    """)
    op.execute("""
    CREATE TRIGGER trigger_log_comment_activity
        AFTER INSERT ON comments
        FOR EACH ROW
        EXECUTE FUNCTION log_comment_activity()
    """)

    # Snapshot diario de metricas de proyectos de un usuario. Idempotente: si ya hay fila de
    # hoy la sobrescribe. Un usuario sin proyectos deja una fila de ceros. El INSERT lista todas
    # las columnas contadoras porque en el modelo solo tienen `default` de Python.
    op.execute("""
    CREATE FUNCTION calculate_and_save_user_metrics(p_user_id uuid)
    RETURNS VOID AS $$
    BEGIN
        INSERT INTO project_metrics_history (
            user_id,
            date,
            total_projects,
            active_projects,
            paused_projects,
            completed_projects,
            total_budget,
            avg_progress
        )
        SELECT
            p_user_id,
            CURRENT_DATE,
            COUNT(*),
            COUNT(*) FILTER (WHERE status = 'active'),
            COUNT(*) FILTER (WHERE status = 'paused'),
            COUNT(*) FILTER (WHERE status = 'completed'),
            COALESCE(SUM(budget), 0),
            COALESCE(AVG(progress), 0)
        FROM projects
        WHERE owner_id = p_user_id
          AND is_deleted = FALSE
        ON CONFLICT (user_id, date) DO UPDATE SET
            total_projects = EXCLUDED.total_projects,
            active_projects = EXCLUDED.active_projects,
            paused_projects = EXCLUDED.paused_projects,
            completed_projects = EXCLUDED.completed_projects,
            total_budget = EXCLUDED.total_budget,
            avg_progress = EXCLUDED.avg_progress;
    END;
    $$ LANGUAGE plpgsql
    """)


def downgrade() -> None:
    op.execute('DROP FUNCTION IF EXISTS calculate_and_save_user_metrics(uuid)')
    op.execute('DROP TRIGGER IF EXISTS trigger_log_comment_activity ON comments')
    op.execute('DROP FUNCTION IF EXISTS log_comment_activity()')
    op.execute('DROP TRIGGER IF EXISTS trigger_log_version_activity ON entity_versions')
    op.execute('DROP FUNCTION IF EXISTS log_version_activity()')
