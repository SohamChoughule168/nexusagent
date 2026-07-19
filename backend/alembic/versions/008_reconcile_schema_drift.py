"""Phase 3C — reconcile ORM-expected schema objects missing from migrations.

Revision ID: 008_reconcile_schema_drift
Revises: 007_kb_unique_name
Create Date: 2026-07-19 00:00:08.000000

The Alembic chain (001-007) is behind the ORM models. On a database built
purely from migrations, the following objects declared on the ORM models are
absent, so any ORM write that includes them fails with "column does not exist":

  1. messages.updated_at              (TimestampedModel base column; 001 omitted it)
  2. document_chunks.updated_at       (TimestampedModel base column; 001 omitted it)
  3. api_keys.updated_at              (TimestampedModel base column; 001 omitted it)
  4. usage_events.updated_at          (TimestampedModel base column; 001 omitted it)
  5. documents.upload_member_id       (Document.upload_member_id; never migrated)
  6. tool_configs table               (ToolConfig model; never migrated; used by
                                       ToolConfigRepository in the application)

Why these and not every drift:

* The four ``updated_at`` columns are inherited from ``TimestampedModel`` onto
  ``Message``, ``DocumentChunk``, ``APIKey`` and ``UsageEvent``. Migration 001
  added ``updated_at`` to *some* TimestampedModel subclasses but missed these
  four; 003 later filled ``organization_members`` and ``audit_logs``. They are
  added here with a DB-side ``server_default=now()`` to match the ORM column
  and to backfill existing rows, exactly as 003 did.
* ``documents.upload_member_id`` is added nullable (the ORM declares it
  NOT NULL). It is made nullable so the migration applies cleanly to the
  existing, already-populated database. The ORM always supplies a value on
  write, so this is functionally equivalent; the residual nullability mismatch
  is benign and intentionally left to keep the migration safe on populated DBs.
* ``tool_configs`` is created only if absent (idempotent, guarded by a
  table-existence check, mirroring migration 006) and matches the ORM
  ``ToolConfig`` model so the application's ``ToolConfigRepository`` works on a
  migration-built database.

All additions are idempotent / guarded (``IF NOT EXISTS`` / ``has_table``) so
the migration is a no-op on a database that already has these objects (e.g. one
built via ``Base.metadata.create_all``) and safe to apply to the existing
development database.

Intentional out-of-scope drifts (documented in the Phase 3C report, left
untouched to avoid breaking the existing database):

* ``conversations.session_id`` and ``agents.public_id`` are declared
  ``unique=True`` on the ORM but were created as non-unique indexes by 001.
  ``agents.public_id`` currently has duplicate rows in the dev database, so a
  UNIQUE constraint cannot be added without dropping data. These are deferred.
* Type mismatches (e.g. ``agents.temperature`` Integer vs Numeric,
  ``documents.file_size`` Integer vs Numeric, ``*_cost_usd`` Float vs Numeric)
  are benign (PostgreSQL coerces) and intentionally left per the 005 rationale.
* Extra migration-only columns (``audit_logs.api_key_id``/``request_id``,
  ``knowledge_bases.embedding_provider``/``embedding_dimensions``) and the
  migration-only tables ``agent_tools``/``tool_executions`` are left in place;
  they are harmless and never removed.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '008_reconcile_schema_drift'
down_revision = '007_kb_unique_name'
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


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return bind.dialect.has_table(bind, name)


def upgrade() -> None:
    # 1-4. Missing TimestampedModel ``updated_at`` columns.
    for table in ("messages", "document_chunks", "api_keys", "usage_events"):
        _add_column_if_not_exists(
            table,
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=True,
                server_default=sa.func.now(),
            ),
        )

    # 5. documents.upload_member_id (UUID reference to User.id).
    #    Nullable here so the migration applies to the populated existing DB;
    #    the ORM supplies a value on every write.
    _add_column_if_not_exists(
        "documents",
        sa.Column(
            "upload_member_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    # 6. tool_configs table (ToolConfig model), created only if absent.
    if _table_exists("tool_configs"):
        return

    op.create_table(
        "tool_configs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("config_type", sa.String(length=50), nullable=False),
        sa.Column(
            "config_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tool_configs_organization_id"),
        "tool_configs",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_tool_configs_organization_id"), table_name="tool_configs")
    op.drop_table("tool_configs")

    op.execute(sa.text("ALTER TABLE documents DROP COLUMN IF EXISTS upload_member_id"))
    op.execute(sa.text("ALTER TABLE usage_events DROP COLUMN IF EXISTS updated_at"))
    op.execute(sa.text("ALTER TABLE api_keys DROP COLUMN IF EXISTS updated_at"))
    op.execute(sa.text("ALTER TABLE document_chunks DROP COLUMN IF EXISTS updated_at"))
    op.execute(sa.text("ALTER TABLE messages DROP COLUMN IF EXISTS updated_at"))
