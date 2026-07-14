"""Add embedding vector column to document_chunks.

Revision ID: 004_document_chunk_embedding
Revises: 003_reconcile_orm_schema
Create Date: 2026-07-14 00:00:04.000000

Milestone 3 vector storage: ``DocumentChunk.embedding`` stores a dense float
vector (Postgres ``double precision[]``) produced by the embedding provider.
Python computes cosine similarity at retrieval time. Production should migrate
this to pgvector for ANN indexing (see ADR-003).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004_document_chunk_embedding'
down_revision = '003_reconcile_orm_schema'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'document_chunks',
        sa.Column('embedding', postgresql.ARRAY(sa.Float()), nullable=True),
    )


def downgrade():
    op.drop_column('document_chunks', 'embedding')
