"""add_keycloak_id_nullable_password

Revision ID: 3c7b52c3f5fb
Revises: 7c2a1f9b3e10
Create Date: 2026-04-07 17:19:15.654510

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3c7b52c3f5fb'
down_revision: Union[str, None] = '7c2a1f9b3e10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('keycloak_id', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_users_keycloak_id'), 'users', ['keycloak_id'], unique=True)
    op.alter_column('users', 'hashed_password',
                    existing_type=sa.VARCHAR(length=255),
                    nullable=True)


def downgrade() -> None:
    op.alter_column('users', 'hashed_password',
                    existing_type=sa.VARCHAR(length=255),
                    nullable=False)
    op.drop_index(op.f('ix_users_keycloak_id'), table_name='users')
    op.drop_column('users', 'keycloak_id')
