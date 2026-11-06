"""Initialize PostgreSQL persistence for users, VPCs, subnets, and IPs."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001_initial_persistence"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


resource_status = postgresql.ENUM(
    "PENDING", "ACTIVE", "ERROR", "DELETED", name="resource_status", create_type=False
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    resource_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "vpcs",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("cidr_block", postgresql.CIDR(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("region", sa.String(length=32), nullable=False),
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
        sa.CheckConstraint(
            "masklen(cidr_block) BETWEEN 16 AND 28",
            name="cidr_prefix_length",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name="fk_vpcs_owner_id_users", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_vpcs"),
    )
    op.create_index(
        "uq_vpcs_owner_name_active",
        "vpcs",
        ["owner_id", "name"],
        unique=True,
        postgresql_where=sa.text("status != 'DELETED'"),
    )
    op.create_index("ix_vpcs_owner_id", "vpcs", ["owner_id"])
    op.create_index("ix_vpcs_status", "vpcs", ["status"])

    op.create_table(
        "subnets",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("vpc_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("cidr_block", postgresql.CIDR(), nullable=False),
        sa.Column("type", sa.String(length=7), nullable=False),
        sa.Column("availability_zone", sa.String(length=64), nullable=True),
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
        sa.CheckConstraint(
            "masklen(cidr_block) BETWEEN 16 AND 28",
            name="cidr_prefix_length",
        ),
        sa.ForeignKeyConstraint(
            ["vpc_id"], ["vpcs.id"], name="fk_subnets_vpc_id_vpcs", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_subnets"),
    )
    op.create_index(
        "uq_subnets_vpc_name_active",
        "subnets",
        ["vpc_id", "name"],
        unique=True,
        postgresql_where=sa.text("status != 'DELETED'"),
    )
    op.create_index("ix_subnets_vpc_id", "subnets", ["vpc_id"])
    op.create_index("ix_subnets_status", "subnets", ["status"])

    op.create_table(
        "ip_allocations",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("subnet_id", sa.Uuid(), nullable=False),
        sa.Column("ip_address", postgresql.INET(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
            name="fk_ip_allocations_subnet_id_subnets",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ip_allocations"),
    )
    op.create_index(
        "uq_ip_allocations_subnet_ip_active",
        "ip_allocations",
        ["subnet_id", "ip_address"],
        unique=True,
        postgresql_where=sa.text("status != 'DELETED'"),
    )
    op.create_index("ix_ip_allocations_subnet_id", "ip_allocations", ["subnet_id"])
    op.create_index("ix_ip_allocations_status", "ip_allocations", ["status"])

    op.execute(
        """
        CREATE FUNCTION set_updated_at() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$
        """
    )
    for table in ("vpcs", "subnets", "ip_allocations"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated_at "
            f"BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )


def downgrade() -> None:
    for table in ("ip_allocations", "subnets", "vpcs"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table}")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")

    op.drop_index("ix_ip_allocations_status", table_name="ip_allocations")
    op.drop_index("ix_ip_allocations_subnet_id", table_name="ip_allocations")
    op.drop_index("uq_ip_allocations_subnet_ip_active", table_name="ip_allocations")
    op.drop_table("ip_allocations")

    op.drop_index("ix_subnets_status", table_name="subnets")
    op.drop_index("ix_subnets_vpc_id", table_name="subnets")
    op.drop_index("uq_subnets_vpc_name_active", table_name="subnets")
    op.drop_table("subnets")

    op.drop_index("ix_vpcs_status", table_name="vpcs")
    op.drop_index("ix_vpcs_owner_id", table_name="vpcs")
    op.drop_index("uq_vpcs_owner_name_active", table_name="vpcs")
    op.drop_table("vpcs")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")

    resource_status.drop(op.get_bind(), checkfirst=True)
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
