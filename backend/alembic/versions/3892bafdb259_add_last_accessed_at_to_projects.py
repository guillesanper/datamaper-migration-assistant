"""add_last_accessed_at_to_projects

Revision ID: 3892bafdb259
Revises: ebaf7a9054eb
Create Date: 2026-04-15 13:43:55.845576

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3892bafdb259"
down_revision: Union[str, None] = "ebaf7a9054eb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_projects_last_accessed_at"),
        "projects",
        ["last_accessed_at"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_projects_last_accessed_at"), table_name="projects")
    op.drop_column("projects", "last_accessed_at")
