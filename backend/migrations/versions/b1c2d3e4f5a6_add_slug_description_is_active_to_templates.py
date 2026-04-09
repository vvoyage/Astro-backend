"""add slug, description, is_active to templates

Revision ID: b1c2d3e4f5a6
Revises: a9f3e1b2c4d5
Create Date: 2026-04-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a9f3e1b2c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("templates", sa.Column("slug", sa.String(100), nullable=False, server_default=""))
    op.add_column("templates", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("templates", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.create_unique_constraint("uq_templates_slug", "templates", ["slug"])
    # Remove server defaults after backfill so future inserts must supply explicit values
    op.alter_column("templates", "slug", server_default=None)
    op.alter_column("templates", "is_active", server_default=None)


def downgrade() -> None:
    op.drop_constraint("uq_templates_slug", "templates", type_="unique")
    op.drop_column("templates", "is_active")
    op.drop_column("templates", "description")
    op.drop_column("templates", "slug")
