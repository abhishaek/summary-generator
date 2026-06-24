"""add content_hash and per-user unique constraint for dedup

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-06-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, Sequence[str], None] = 'e6f7a8b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('content_hash', sa.String(length=64), nullable=True))
    op.create_unique_constraint(
        'uq_documents_user_content_hash', 'documents', ['user_id', 'content_hash']
    )


def downgrade() -> None:
    op.drop_constraint('uq_documents_user_content_hash', 'documents', type_='unique')
    op.drop_column('documents', 'content_hash')
