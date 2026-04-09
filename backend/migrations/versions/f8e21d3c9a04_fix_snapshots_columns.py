"""fix snapshots columns: version_id→version(int), s3_path→minio_path, add description

Revision ID: f8e21d3c9a04
Revises: 3c7b52c3f5fb
Create Date: 2026-04-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f8e21d3c9a04"
down_revision: Union[str, None] = "3c7b52c3f5fb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # version_id String → version Integer
    op.alter_column(
        "snapshots",
        "version_id",
        new_column_name="version",
        existing_type=sa.String(length=50),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using="version_id::integer",
    )
    # s3_path → minio_path (переименование, тип тот же)
    op.alter_column(
        "snapshots",
        "s3_path",
        new_column_name="minio_path",
        existing_type=sa.String(length=255),
        existing_nullable=False,
    )
    # добавляем description
    op.add_column(
        "snapshots",
        sa.Column("description", sa.String(length=500), nullable=True, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("snapshots", "description")
    op.alter_column(
        "snapshots",
        "minio_path",
        new_column_name="s3_path",
        existing_type=sa.String(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        "snapshots",
        "version",
        new_column_name="version_id",
        existing_type=sa.Integer(),
        type_=sa.String(length=50),
        existing_nullable=False,
    )
