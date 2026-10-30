"""email_otps.failed_attempts: intentos fallidos por codigo OTP

Aditiva y reversible: la columna nace NOT NULL con DEFAULT 0, asi que las filas existentes
quedan en 0 y el codigo anterior (que no la conoce) sigue funcionando mientras dura un
despliegue. `verify_otp_orm` la incrementa de forma atomica y borra el OTP al llegar a
OTP_MAX_ATTEMPTS; `create_otp_orm` la reinicia (un reenvio da otra tanda).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-11

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "email_otps",
        sa.Column("failed_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("email_otps", "failed_attempts")
