"""Reconcile ORM-expected schema objects missing from the migration chain.

Revision ID: 003_reconcile_orm_schema
Revises: 002_rls_policies
Create Date: 2026-07-12 00:00:02.000000

The Alembic chain (001 + 002) is behind the ORM. The following objects are
expected by the ORM models but are not produced on a fresh database by the
migration chain:

  1. organization_members.updated_at        (TimestampedModel base column)
  2. audit_logs.updated_at                  (TimestampedModel base column)
  3. agents.max_tokens                      (Agent.max_tokens)
  4. organization_settings table            (KeyValueSettings model)
  5. system_settings table                  (SystemSettings model)

002 only adds RLS policies and does not touch these objects, so the delta
below is the complete reconciliation. This migration is forward-only and does
not modify 001/002 or the ORM.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003_reconcile_orm_schema'
down_revision = '002_rls_policies'
branch_labels = None
depends_on = None


def upgrade():
    # 1. organization_members.updated_at (inherited from TimestampedModel)
    op.add_column(
        'organization_members',
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
    )

    # 2. audit_logs.updated_at (inherited from TimestampedModel)
    op.add_column(
        'audit_logs',
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
    )

    # 3. agents.max_tokens (Agent.max_tokens: Optional[int])
    op.add_column(
        'agents',
        sa.Column('max_tokens', sa.Integer(), nullable=True),
    )

    # 4. organization_settings table (KeyValueSettings model)
    # Matches Base.metadata.tables['organization_settings']:
    #   inherited TimestampedModel columns (id, created_at, updated_at) are
    #   part of the ORM schema; id is a PK column with gen_random_uuid()
    #   server default, so the primary key is composite (organization_id, id).
    op.create_table(
        'organization_settings',
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text('gen_random_uuid()'),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('organization_id', 'id'),
        sa.UniqueConstraint('organization_id', 'key', name='unique_key_per_org'),
    )

    # 5. system_settings table (SystemSettings model)
    # Matches Base.metadata.tables['system_settings']:
    #   inherited TimestampedModel columns (id, created_at, updated_at) are
    #   part of the ORM schema; id is a PK column with gen_random_uuid()
    #   server default, so the primary key is composite (organization_id, id).
    #   organization_id carries NO foreign key in the ORM model.
    op.create_table(
        'system_settings',
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('theme', sa.String(length=20), nullable=False),
        sa.Column('language', sa.String(length=10), nullable=False),
        sa.Column('timezone', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text('gen_random_uuid()'),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint('organization_id', 'id'),
    )


def downgrade():
    # Reverse ONLY the objects introduced by 003, in reverse order.
    op.drop_table('system_settings')

    op.drop_table('organization_settings')

    op.drop_column('agents', 'max_tokens')

    op.drop_column('audit_logs', 'updated_at')

    op.drop_column('organization_members', 'updated_at')
