"""add active_snapshot_version to projects

Revision ID: a9f3e1b2c4d5
Revises: f8e21d3c9a04
Create Date: 2026-04-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9f3e1b2c4d5"
down_revision: Union[str, None] = "f8e21d3c9a04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("active_snapshot_version", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "active_snapshot_version")
