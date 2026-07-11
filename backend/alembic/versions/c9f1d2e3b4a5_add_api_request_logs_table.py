"""Add api_request_logs table

Revision ID: c9f1d2e3b4a5
Revises: 4bdb85e9bcd8
Create Date: 2026-03-18 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9f1d2e3b4a5"
down_revision: Union[str, None] = "4bdb85e9bcd8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_request_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("endpoint", sa.String(255), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_time_ms", sa.Integer(), nullable=False),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_api_request_logs"),
    )
    op.create_index(
        "idx_api_request_logs_endpoint_status",
        "api_request_logs",
        ["endpoint", "status_code"],
    )
    op.create_index(
        "idx_api_request_logs_created_at",
        "api_request_logs",
        ["created_at"],
        postgresql_using="brin",
    )
    op.create_index(
        "idx_api_request_logs_endpoint",
        "api_request_logs",
        ["endpoint"],
    )


def downgrade() -> None:
    op.drop_index("idx_api_request_logs_endpoint", table_name="api_request_logs")
    op.drop_index("idx_api_request_logs_created_at", table_name="api_request_logs")
    op.drop_index("idx_api_request_logs_endpoint_status", table_name="api_request_logs")
    op.drop_table("api_request_logs")
