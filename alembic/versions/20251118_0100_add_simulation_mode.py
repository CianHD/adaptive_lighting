"""Add project simulation mode and simulated flags to schedules/commands.

Revision ID: 20251118_0100
Revises: 20251118_0001
Create Date: 2025-11-18 12:00:00
"""  # pylint: disable=invalid-name

from alembic import op
import sqlalchemy as sa


revision = "20251118_0100"  # pylint: disable=invalid-name
down_revision = "20251118_0001"  # pylint: disable=invalid-name
branch_labels = None  # pylint: disable=invalid-name
depends_on = None  # pylint: disable=invalid-name


PROJECT_MODES = ("live", "simulation")


def upgrade() -> None:
    """Add project mode and is_simulated columns."""
    op.add_column(
        "project",
        sa.Column("mode", sa.String(length=20), nullable=False, server_default="live"),
    )
    op.create_check_constraint(
        "project_mode_check",
        "project",
        sa.text("mode in ('live','simulation')"),
    )
    op.alter_column("project", "mode", server_default=None)

    op.add_column(
        "schedule",
        sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("schedule", "is_simulated", server_default=None)

    op.add_column(
        "realtime_command",
        sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("realtime_command", "is_simulated", server_default=None)


def downgrade() -> None:
    """Remove project mode and is_simulated columns."""
    op.drop_column("realtime_command", "is_simulated")
    op.drop_column("schedule", "is_simulated")

    op.drop_constraint("project_mode_check", "project", type_="check")
    op.drop_column("project", "mode")
