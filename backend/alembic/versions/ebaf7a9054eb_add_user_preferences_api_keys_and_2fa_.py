"""add_user_preferences_api_keys_and_2fa_fields

Revision ID: ebaf7a9054eb
Revises: c9f1d2e3b4a5
Create Date: 2026-03-19 21:21:57.540402

Cambios incluidos:
- ALTER TABLE users: ADD COLUMN avatar_url, totp_secret, totp_enabled
- CREATE TABLE user_preferences (PK = user_id, FK a users, 1:1)
- CREATE TABLE user_api_keys (PK = id, FK a users, índice en user_id)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ebaf7a9054eb"
down_revision: Union[str, None] = "c9f1d2e3b4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Nuevas columnas en users
    # ------------------------------------------------------------------
    op.add_column("users", sa.Column("avatar_url", sa.String(length=500), nullable=True))
    op.add_column("users", sa.Column("totp_secret", sa.String(length=64), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "totp_enabled",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )

    # ------------------------------------------------------------------
    # Nueva tabla: user_preferences (relación 1:1 con users)
    # ------------------------------------------------------------------
    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("language", sa.String(length=10), server_default="es", nullable=False),
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
        sa.Column("default_db_type", sa.String(length=50), nullable=True),
        sa.Column(
            "default_export_format",
            sa.String(length=20),
            server_default="xlsx",
            nullable=False,
        ),
        sa.Column(
            "email_notifications",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "in_app_notifications",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_preferences_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_preferences")),
    )

    # ------------------------------------------------------------------
    # Nueva tabla: user_api_keys (relación 1:N con users)
    # ------------------------------------------------------------------
    op.create_table(
        "user_api_keys",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("key_prefix", sa.String(length=8), nullable=False),
        sa.Column("key_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_api_keys_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_api_keys")),
        sa.UniqueConstraint("key_hash", name=op.f("uq_user_api_keys_key_hash")),
    )
    op.create_index(op.f("ix_user_api_keys_user_id"), "user_api_keys", ["user_id"], unique=False)
    op.create_index(
        "idx_api_keys_user_active", "user_api_keys", ["user_id", "is_active"], unique=False
    )
    op.create_index(
        "idx_api_keys_expires",
        "user_api_keys",
        ["expires_at"],
        unique=False,
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # Eliminar tabla user_api_keys
    # ------------------------------------------------------------------
    op.drop_index("idx_api_keys_expires", table_name="user_api_keys")
    op.drop_index("idx_api_keys_user_active", table_name="user_api_keys")
    op.drop_index(op.f("ix_user_api_keys_user_id"), table_name="user_api_keys")
    op.drop_table("user_api_keys")

    # ------------------------------------------------------------------
    # Eliminar tabla user_preferences
    # ------------------------------------------------------------------
    op.drop_table("user_preferences")

    # ------------------------------------------------------------------
    # Revertir columnas en users
    # ------------------------------------------------------------------
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret")
    op.drop_column("users", "avatar_url")
