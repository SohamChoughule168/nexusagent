"""Long-Term Memory Store (Milestone 5, Phase 2.2).

Revision ID: 006_long_term_memory
Revises: 005_reconcile_models_to_migrations
Create Date: 2026-07-16 00:00:06.000000

Adds the ``memories`` table: a tenant-scoped (``organization_id``) long-term
memory store that persists important facts/preferences/instructions
independently of conversation history. Columns mirror the ORM ``Memory`` model
in ``app.models.all_models``:

  * ``content`` (text, NOT NULL) -- the memory text
  * ``category`` / ``key`` -- non-semantic lookup/grouping hints
  * ``importance`` -- reserved for later ranking (Phase 2.3)
  * ``agent_id`` / ``user_id`` -- optional scoping hints
  * ``embedding`` (float[]) -- reuses the vector-storage architecture; populated
    by the deterministic local embedder, queried by Phase 2.3 semantic retrieval
  * ``metadata`` (jsonb) -- reserved for later consolidation

The create is guarded by an existence check so it is a no-op on a database that
was already built via ``Base.metadata.create_all`` (which already has this
table), and creates it cleanly on a fresh database built purely from migrations.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '006_long_term_memory'
down_revision = '005_reconcile_models'
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return bind.dialect.has_table(bind, name)


def upgrade():
    if _table_exists('memories'):
        return

    op.create_table(
        'memories',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=255), nullable=True),
        sa.Column('key', sa.String(length=255), nullable=True),
        sa.Column('importance', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('embedding', postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_memories_organization_id'), 'memories', ['organization_id'], unique=False)
    op.create_index(op.f('ix_memories_agent_id'), 'memories', ['agent_id'], unique=False)
    op.create_index(op.f('ix_memories_user_id'), 'memories', ['user_id'], unique=False)
    op.create_index(op.f('ix_memories_category'), 'memories', ['category'], unique=False)
    op.create_index(op.f('ix_memories_key'), 'memories', ['key'], unique=False)


def downgrade():
    if not _table_exists('memories'):
        return
    op.drop_index(op.f('ix_memories_key'), table_name='memories')
    op.drop_index(op.f('ix_memories_category'), table_name='memories')
    op.drop_index(op.f('ix_memories_user_id'), table_name='memories')
    op.drop_index(op.f('ix_memories_agent_id'), table_name='memories')
    op.drop_index(op.f('ix_memories_organization_id'), table_name='memories')
    op.drop_table('memories')
