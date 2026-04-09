"""add project status column

Revision ID: 7c2a1f9b3e10
Revises: 26b0492540d7
Create Date: 2026-04-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c2a1f9b3e10"
down_revision: Union[str, None] = "26b0492540d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "status",
            sa.String(length=64),
            nullable=False,
            server_default="queued",
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "status")
