"""Reconcile Alembic schema with the ORM models (Milestone 3 drift).

Revision ID: 005_reconcile_models
Revises: 004_document_chunk_embedding
Create Date: 2026-07-14 00:00:05.000000

NOTE ON REVISION ID: the original id ``005_reconcile_models_to_migrations``
was 34 characters, which exceeds the standard ``alembic_version.version_num``
width of ``VARCHAR(32)`` that Alembic creates on a fresh database
(alembic/runtime/migration.py: ``Column("version_num", String(32)``). A fresh
``alembic upgrade head`` therefore failed at this revision with
"value too long for type character varying(32)". The id was shortened to
``005_reconcile_models`` (21 chars). The existing development database is
already stamped at the head (``007_kb_unique_name``) and never records this
revision id directly, so renaming is transparent and does not break its
migration history.

The Alembic chain (001-004) is behind the ORM models. The following columns
are declared on the ORM models but are missing from the migration chain, so a
fresh ``alembic upgrade head`` would produce tables without them and any INSERT
through the ORM (which always writes every mapped column) would fail:

  1. knowledge_bases.chunk_size        (KnowledgeBase.chunk_size, default 1000)
  2. knowledge_bases.chunk_overlap     (KnowledgeBase.chunk_overlap, default 200)
  3. agents.top_p                      (Agent.top_p)
  4. agents.presence_penalty           (Agent.presence_penalty)
  5. agents.frequency_penalty          (Agent.frequency_penalty)
  6. documents.title                   (Document.title)

All additions are nullable so they are safe to apply to an existing database
that was created via ``Base.metadata.create_all`` (which already has these
columns) -- the ``IF NOT EXISTS`` guard makes each a no-op there -- and to a
fresh database built purely from migrations.

Note: ``knowledge_bases.embedding_provider`` / ``embedding_dimensions`` exist in
001 but are intentionally not mapped by the ORM; they are left in place (extra,
unmapped columns are harmless). Type-level mismatches (e.g. agents.temperature
Integer vs Numeric, documents.file_size Integer vs Numeric) are benign because
PostgreSQL coerces numeric types and are intentionally not altered here to keep
this migration low-risk.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '005_reconcile_models'
down_revision = '004_document_chunk_embedding'
branch_labels = None
depends_on = None


def _add_column_if_not_exists(table: str, column: sa.Column) -> None:
    """Add ``column`` to ``table`` only if it does not already exist."""
    op.execute(
        sa.text(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
            f"{column.name} {column.type.compile(dialect=op.get_bind().dialect)}"
        )
    )


def upgrade():
    _add_column_if_not_exists(
        'knowledge_bases', sa.Column('chunk_size', sa.Integer(), nullable=True)
    )
    _add_column_if_not_exists(
        'knowledge_bases', sa.Column('chunk_overlap', sa.Integer(), nullable=True)
    )
    _add_column_if_not_exists(
        'agents', sa.Column('top_p', sa.Float(), nullable=True)
    )
    _add_column_if_not_exists(
        'agents', sa.Column('presence_penalty', sa.Float(), nullable=True)
    )
    _add_column_if_not_exists(
        'agents', sa.Column('frequency_penalty', sa.Float(), nullable=True)
    )
    _add_column_if_not_exists(
        'documents', sa.Column('title', sa.String(length=255), nullable=True)
    )


def downgrade():
    # Drop only the columns introduced by this migration.
    op.execute(sa.text("ALTER TABLE documents DROP COLUMN IF EXISTS title"))
    op.execute(sa.text("ALTER TABLE agents DROP COLUMN IF EXISTS frequency_penalty"))
    op.execute(sa.text("ALTER TABLE agents DROP COLUMN IF EXISTS presence_penalty"))
    op.execute(sa.text("ALTER TABLE agents DROP COLUMN IF EXISTS top_p"))
    op.execute(sa.text("ALTER TABLE knowledge_bases DROP COLUMN IF EXISTS chunk_overlap"))
    op.execute(sa.text("ALTER TABLE knowledge_bases DROP COLUMN IF EXISTS chunk_size"))
