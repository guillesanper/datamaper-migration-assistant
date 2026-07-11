"""
Modelos ORM de SQLAlchemy

Este paquete contiene todos los modelos ORM de la aplicación.
Los modelos se importan aquí para que Alembic pueda descubrirlos
automáticamente durante la auto-generación de migraciones.

Estructura:
- security.py: Modelos de seguridad (SecurityLog, SecurityRateLimit)
- user.py: Modelo de usuarios
- user_preferences.py: Preferencias de usuario (UserPreferences)
- api_key.py: API keys de usuario (UserApiKey)
- subscription.py: Modelos de suscripciones (SubscriptionPlan, Subscription)
- project.py: Modelos de proyectos (Project, ProjectMember)
- encryption.py: Modelo de configuración de encriptación
- table.py: Modelo de tablas de metadata
- column.py: Modelo de columnas de metadata
- primary_key.py: Modelo de primary keys compuestas
- mapping.py: Modelo de mappings (modo híbrido import/connector)
- version.py: Modelos de versionado (EntityVersion, VersionTag)
- comment.py: Modelos de comentarios (Comment, CommentReaction, CommentRead)
- activity.py: Modelo de actividad del proyecto
- lock.py: Modelo de locks de edición
- notification.py: Modelo de notificaciones
- migration.py: Modelos de migración (MigrationScript, MigrationExecution, MigrationAuditLog)

Usage en Alembic (alembic/env.py):
    from app.models.orm import Base
    target_metadata = Base.metadata

Usage en código:
    from app.models.orm import User, UserPreferences, UserApiKey, Project, Table, Mapping
    from sqlalchemy.orm import Session

    def get_user(db: Session, user_id: str):
        return db.query(User).filter(User.id == user_id).first()
"""

from app.database.base import Base

from .activity import ProjectActivity
from .api_key import UserApiKey
from .column import TableColumn
from .comment import Comment, CommentReaction, CommentRead
from .csrf import CSRFToken
from .email_otp import EmailOTP
from .encryption import ProjectEncryption
from .lock import EntityLock
from .mapping import Mapping
from .metrics import ProjectMetricsHistory
from .migration import MigrationAuditLog, MigrationExecution, MigrationScript
from .notification import Notification
from .primary_key import PrimaryKeyConstraint
from .project import MemberRole, Project, ProjectMember
from .request_log import ApiRequestLog

# Importar todos los modelos
from .security import SecurityLog, SecurityRateLimit
from .session import UserSession
from .subscription import Subscription, SubscriptionPlan
from .table import Table
from .user import User
from .user_preferences import UserPreferences
from .version import EntityVersion, VersionTag

__all__ = [
    # Base
    "Base",
    # Security
    "SecurityLog",
    "SecurityRateLimit",
    "CSRFToken",
    # Authentication & Sessions
    "EmailOTP",
    "UserSession",
    # User
    "User",
    "UserPreferences",
    "UserApiKey",
    # Metrics
    "ProjectMetricsHistory",
    # Subscriptions
    "SubscriptionPlan",
    "Subscription",
    # Projects
    "Project",
    "ProjectMember",
    "MemberRole",
    # Encryption
    "ProjectEncryption",
    # Metadata
    "Table",
    "TableColumn",
    "PrimaryKeyConstraint",
    # Mappings
    "Mapping",
    # Version Control
    "EntityVersion",
    "VersionTag",
    # Comments
    "Comment",
    "CommentReaction",
    "CommentRead",
    # Activity & Locks
    "ProjectActivity",
    "EntityLock",
    # Notifications
    "Notification",
    # Migrations
    "MigrationScript",
    "MigrationExecution",
    "MigrationAuditLog",
    # Request Logs
    "ApiRequestLog",
]
