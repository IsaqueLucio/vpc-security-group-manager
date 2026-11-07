"""Create security groups and security group rules."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0007_security_groups"
down_revision: str | None = "0006_vpc_peerings"
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
rule_direction = postgresql.ENUM(
    "INBOUND",
    "OUTBOUND",
    name="security_group_rule_direction",
    create_type=False,
)
rule_protocol = postgresql.ENUM(
    "TCP",
    "UDP",
    "ICMP",
    "ALL",
    name="security_group_rule_protocol",
    create_type=False,
)


def upgrade() -> None:
    rule_direction.create(op.get_bind(), checkfirst=True)
    rule_protocol.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "security_groups",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("vpc_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
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
            ["vpc_id"],
            ["vpcs.id"],
            name="fk_security_groups_vpc_id_vpcs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_security_groups"),
    )
    op.create_index("ix_security_groups_vpc_id", "security_groups", ["vpc_id"])
    op.create_index("ix_security_groups_status", "security_groups", ["status"])

    op.create_table(
        "security_group_rules",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("security_group_id", sa.Uuid(), nullable=False),
        sa.Column("direction", rule_direction, nullable=False),
        sa.Column("protocol", rule_protocol, nullable=False),
        sa.Column("port_range_from", sa.Integer(), nullable=True),
        sa.Column("port_range_to", sa.Integer(), nullable=True),
        sa.Column("cidr_block", postgresql.CIDR(), nullable=False),
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
            ["security_group_id"],
            ["security_groups.id"],
            name="fk_security_group_rules_security_group_id_security_groups",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_security_group_rules"),
    )
    op.create_index(
        "ix_security_group_rules_security_group_id",
        "security_group_rules",
        ["security_group_id"],
    )
    op.create_index("ix_security_group_rules_status", "security_group_rules", ["status"])

    for table in ("security_groups", "security_group_rules"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated_at "
            f"BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )


def downgrade() -> None:
    for table in ("security_group_rules", "security_groups"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table}")
    op.drop_index("ix_security_group_rules_status", table_name="security_group_rules")
    op.drop_index(
        "ix_security_group_rules_security_group_id",
        table_name="security_group_rules",
    )
    op.drop_table("security_group_rules")
    op.drop_index("ix_security_groups_status", table_name="security_groups")
    op.drop_index("ix_security_groups_vpc_id", table_name="security_groups")
    op.drop_table("security_groups")
    rule_protocol.drop(op.get_bind(), checkfirst=True)
    rule_direction.drop(op.get_bind(), checkfirst=True)
