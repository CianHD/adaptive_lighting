"""Baseline revision to anchor Alembic migrations.

Revision ID: 20251118_0001
Revises: 
Create Date: 2025-11-18 00:00:00
""" # pylint: disable=invalid-name

from alembic import op  # pylint: disable=unused-import
import sqlalchemy as sa  # pylint: disable=unused-import

revision = "20251118_0001"  # pylint: disable=invalid-name
down_revision = None  # pylint: disable=invalid-name
branch_labels = None  # pylint: disable=invalid-name
depends_on = None  # pylint: disable=invalid-name


def upgrade() -> None:
    """Baseline upgrade is a no-op because the DB already matches the models."""


def downgrade() -> None:
    """Baseline downgrade also does nothing; it exists for completeness."""
