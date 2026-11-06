"""Create VPC peering requests."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0006_vpc_peerings"
down_revision: str | None = "0005_route_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


peering_status = postgresql.ENUM(
    "PENDING_ACCEPTANCE",
    "ACTIVE",
    "REJECTED",
    "DELETED",
    name="vpc_peering_status",
    create_type=False,
)


def upgrade() -> None:
    peering_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "vpc_peerings",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("requester_vpc_id", sa.Uuid(), nullable=False),
        sa.Column("accepter_vpc_id", sa.Uuid(), nullable=False),
        sa.Column("status", peering_status, nullable=False),
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
            ["requester_vpc_id"],
            ["vpcs.id"],
            name="fk_vpc_peerings_requester_vpc_id_vpcs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["accepter_vpc_id"],
            ["vpcs.id"],
            name="fk_vpc_peerings_accepter_vpc_id_vpcs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_vpc_peerings"),
        sa.CheckConstraint(
            "requester_vpc_id <> accepter_vpc_id",
            name="ck_vpc_peerings_distinct_vpcs",
        ),
    )
    op.create_index(
        "uq_vpc_peerings_pair_active",
        "vpc_peerings",
        [
            sa.text("LEAST(requester_vpc_id, accepter_vpc_id)"),
            sa.text("GREATEST(requester_vpc_id, accepter_vpc_id)"),
        ],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('DELETED', 'REJECTED')"),
    )
    op.create_index(
        "ix_vpc_peerings_requester_vpc_id",
        "vpc_peerings",
        ["requester_vpc_id"],
    )
    op.create_index(
        "ix_vpc_peerings_accepter_vpc_id",
        "vpc_peerings",
        ["accepter_vpc_id"],
    )
    op.create_index("ix_vpc_peerings_status", "vpc_peerings", ["status"])
    op.execute(
        "CREATE TRIGGER trg_vpc_peerings_updated_at "
        "BEFORE UPDATE ON vpc_peerings "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_vpc_peerings_updated_at ON vpc_peerings")
    op.drop_index("ix_vpc_peerings_status", table_name="vpc_peerings")
    op.drop_index("ix_vpc_peerings_accepter_vpc_id", table_name="vpc_peerings")
    op.drop_index("ix_vpc_peerings_requester_vpc_id", table_name="vpc_peerings")
    op.drop_index("uq_vpc_peerings_pair_active", table_name="vpc_peerings")
    op.drop_table("vpc_peerings")
    peering_status.drop(op.get_bind(), checkfirst=True)
