"""Add transformation_logic column to mappings

Revision ID: 4bdb85e9bcd8
Revises: a7f3e55ded94
Create Date: 2026-02-19 02:51:06.315996

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4bdb85e9bcd8"
down_revision: Union[str, None] = "a7f3e55ded94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mappings", sa.Column("transformation_logic", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("mappings", "transformation_logic")
