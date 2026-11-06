"""Add user account activation state."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0003_user_active"
down_revision: str | None = "0002_network_overlap_exclusions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "is_active")
