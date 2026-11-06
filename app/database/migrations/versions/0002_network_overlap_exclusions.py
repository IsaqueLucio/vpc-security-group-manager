"""Protect active VPC and subnet CIDRs against overlap."""

from typing import Sequence

from alembic import op


revision: str = "0002_network_overlap_exclusions"
down_revision: str | None = "0001_initial_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE vpcs
        ADD CONSTRAINT ex_vpcs_owner_cidr_active
        EXCLUDE USING gist (
            owner_id WITH =,
            cidr_block inet_ops WITH &&
        )
        WHERE (status != 'DELETED')
        """
    )
    op.execute(
        """
        ALTER TABLE subnets
        ADD CONSTRAINT ex_subnets_vpc_cidr_active
        EXCLUDE USING gist (
            vpc_id WITH =,
            cidr_block inet_ops WITH &&
        )
        WHERE (status != 'DELETED')
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE subnets DROP CONSTRAINT ex_subnets_vpc_cidr_active")
    op.execute("ALTER TABLE vpcs DROP CONSTRAINT ex_vpcs_owner_cidr_active")
