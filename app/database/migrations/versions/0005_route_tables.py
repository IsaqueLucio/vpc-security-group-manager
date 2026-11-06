"""Create route tables, routes, and subnet associations."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0005_route_tables"
down_revision: str | None = "0004_gateways"
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
route_target_type = postgresql.ENUM(
    "LOCAL",
    "INTERNET_GATEWAY",
    "NAT_GATEWAY",
    name="route_target_type",
    create_type=False,
)


def upgrade() -> None:
    route_target_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "route_tables",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("vpc_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
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
            name="fk_route_tables_vpc_id_vpcs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_route_tables"),
    )
    op.create_index("ix_route_tables_vpc_id", "route_tables", ["vpc_id"])
    op.create_index("ix_route_tables_status", "route_tables", ["status"])

    op.create_table(
        "routes",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("route_table_id", sa.Uuid(), nullable=False),
        sa.Column("destination_cidr", postgresql.CIDR(), nullable=False),
        sa.Column("target_type", route_target_type, nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=True),
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
            ["route_table_id"],
            ["route_tables.id"],
            name="fk_routes_route_table_id_route_tables",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_routes"),
    )
    op.create_index("ix_routes_route_table_id", "routes", ["route_table_id"])
    op.create_index("ix_routes_status", "routes", ["status"])

    op.create_table(
        "route_table_associations",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("subnet_id", sa.Uuid(), nullable=False),
        sa.Column("route_table_id", sa.Uuid(), nullable=False),
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
            name="fk_route_table_associations_subnet_id_subnets",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["route_table_id"],
            ["route_tables.id"],
            name="fk_route_table_associations_route_table_id_route_tables",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_route_table_associations"),
    )
    op.create_index(
        "uq_route_table_associations_subnet_active",
        "route_table_associations",
        ["subnet_id"],
        unique=True,
        postgresql_where=sa.text("status != 'DELETED'"),
    )
    op.create_index(
        "ix_route_table_associations_route_table_id",
        "route_table_associations",
        ["route_table_id"],
    )
    op.create_index(
        "ix_route_table_associations_status",
        "route_table_associations",
        ["status"],
    )

    for table in ("route_tables", "routes", "route_table_associations"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated_at "
            f"BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )


def downgrade() -> None:
    for table in ("route_table_associations", "routes", "route_tables"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table}")

    op.drop_index(
        "ix_route_table_associations_status",
        table_name="route_table_associations",
    )
    op.drop_index(
        "ix_route_table_associations_route_table_id",
        table_name="route_table_associations",
    )
    op.drop_index(
        "uq_route_table_associations_subnet_active",
        table_name="route_table_associations",
    )
    op.drop_table("route_table_associations")

    op.drop_index("ix_routes_status", table_name="routes")
    op.drop_index("ix_routes_route_table_id", table_name="routes")
    op.drop_table("routes")

    op.drop_index("ix_route_tables_status", table_name="route_tables")
    op.drop_index("ix_route_tables_vpc_id", table_name="route_tables")
    op.drop_table("route_tables")
    route_target_type.drop(op.get_bind(), checkfirst=True)
