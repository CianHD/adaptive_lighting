"""Add duration to realtime commands.

Revision ID: 20251118_0200
Revises: 20251118_0100
Create Date: 2025-11-18 15:30:00
"""  # pylint: disable=invalid-name

from alembic import op
import sqlalchemy as sa


revision = "20251118_0200"  # pylint: disable=invalid-name
down_revision = "20251118_0100"  # pylint: disable=invalid-name
branch_labels = None  # pylint: disable=invalid-name
depends_on = None  # pylint: disable=invalid-name


def upgrade() -> None:
    """Add duration_minutes column and constraint."""
    op.add_column(
        "realtime_command",
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="15"),
    )
    op.create_check_constraint(
        "realtime_command_duration_minutes_check",
        "realtime_command",
        sa.text("duration_minutes BETWEEN 1 AND 1440"),
    )
    op.alter_column("realtime_command", "duration_minutes", server_default=None)


def downgrade() -> None:
    """Remove duration_minutes column and constraint."""
    op.drop_constraint("realtime_command_duration_minutes_check", "realtime_command", type_="check")
    op.drop_column("realtime_command", "duration_minutes")
