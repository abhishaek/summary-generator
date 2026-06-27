"""add chunk embedding hnsw index

Revision ID: 612164b36863
Revises: 7c58e1e79732
Create Date: 2026-06-26 15:37:19.761813

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '612164b36863'
down_revision: Union[str, Sequence[str], None] = '7c58e1e79732'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Add an HNSW index on document_chunks.embedding for approximate nearest-
    neighbour search. The operator class is vector_cosine_ops because stored
    vectors are L2-normalized and the retrieval query orders by cosine_distance
    (<=>); the index opclass MUST match that operator or Postgres won't use it.
    """
    # HNSW builds the graph in memory; bump maintenance_work_mem for this build
    # so a large existing table doesn't fail with an out-of-memory error. SET
    # LOCAL scopes it to this migration's transaction only.
    op.execute("SET LOCAL maintenance_work_mem = '256MB'")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
