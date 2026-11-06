"""Create Internet Gateway and NAT Gateway persistence."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0004_gateways"
down_revision: str | None = "0003_user_active"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


resource_status = postgresql.ENUM(
    "PENDING",
    "ACTIVE",
    "ERROR",
    "DELETED",
    name="resource_status",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "internet_gateways",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("vpc_id", sa.Uuid(), nullable=False),
        sa.Column("status", resource_status, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["vpc_id"],
            ["vpcs.id"],
            name="fk_internet_gateways_vpc_id_vpcs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_internet_gateways"),
    )
    op.create_index(
        "uq_internet_gateways_vpc_active",
        "internet_gateways",
        ["vpc_id"],
        unique=True,
        postgresql_where=sa.text("status != 'DELETED'"),
    )
    op.create_index("ix_internet_gateways_vpc_id", "internet_gateways", ["vpc_id"])
    op.create_index("ix_internet_gateways_status", "internet_gateways", ["status"])

    op.create_table(
        "nat_gateways",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("subnet_id", sa.Uuid(), nullable=False),
        sa.Column("status", resource_status, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["subnet_id"],
            ["subnets.id"],
            name="fk_nat_gateways_subnet_id_subnets",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_nat_gateways"),
    )
    op.create_index("ix_nat_gateways_subnet_id", "nat_gateways", ["subnet_id"])
    op.create_index("ix_nat_gateways_status", "nat_gateways", ["status"])

    for table in ("internet_gateways", "nat_gateways"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated_at "
            f"BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )


def downgrade() -> None:
    for table in ("internet_gateways", "nat_gateways"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table}")
    op.drop_index("ix_nat_gateways_status", table_name="nat_gateways")
    op.drop_index("ix_nat_gateways_subnet_id", table_name="nat_gateways")
    op.drop_table("nat_gateways")
    op.drop_index("ix_internet_gateways_status", table_name="internet_gateways")
    op.drop_index("ix_internet_gateways_vpc_id", table_name="internet_gateways")
    op.drop_index("uq_internet_gateways_vpc_active", table_name="internet_gateways")
    op.drop_table("internet_gateways")
