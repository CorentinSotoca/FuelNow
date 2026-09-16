"""add enseigne column to stations

Revision ID: 003
Revises: 002
Create Date: 2026-09-16
"""
import sqlalchemy as sa

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stations", sa.Column("enseigne", sa.Text))


def downgrade() -> None:
    op.drop_column("stations", "enseigne")
