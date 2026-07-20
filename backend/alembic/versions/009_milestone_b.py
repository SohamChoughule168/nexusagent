"""Milestone B — schema additions for product-expansion steps.

Revision ID: 009_milestone_b
Revises: 008_reconcile_schema_drift
Create Date: 2026-07-19

Adds the schema that Steps 2-6 of Milestone B depend on:

* ``documents`` — indexing progress (integer percent + chunk counters),
  ``last_indexed_at``, and ``tags`` (for metadata filtering at retrieval time).
* ``tools`` — per-tool ``timeout_seconds``, an ``allowed_roles`` execution
  allow-list, ``documentation``, and health-probe columns (``health_status``,
  ``last_checked_at``); plus a uniqueness constraint on (organization_id, name).
* ``usage_events`` — ``latency_ms`` / ``status`` / ``error`` for analytics.
* New tables: ``notifications`` (in-app), ``webhook_subscriptions`` /
  ``webhook_deliveries`` (webhook events), and ``background_tasks`` (job status
  polling).

All additions are idempotent (``IF NOT EXISTS`` / existence guards) so the
migration is a no-op on a database already built from the ORM via
``Base.metadata.create_all`` and safe to apply to a populated database.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '009_milestone_b'
down_revision = '008_reconcile_schema_drift'
branch_labels = None
depends_on = None


def _add_column_if_not_exists(table: str, column: sa.Column) -> None:
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
    # --- documents: indexing progress + metadata tags ----------------------
    _add_column_if_not_exists(
        "documents", sa.Column("indexing_progress", sa.Integer(), nullable=False, server_default="0")
    )
    _add_column_if_not_exists(
        "documents", sa.Column("total_chunks", sa.Integer(), nullable=False, server_default="0")
    )
    _add_column_if_not_exists(
        "documents", sa.Column("indexed_chunks", sa.Integer(), nullable=False, server_default="0")
    )
    _add_column_if_not_exists(
        "documents", sa.Column("last_indexed_at", sa.DateTime(timezone=True), nullable=True)
    )
    _add_column_if_not_exists(
        "documents",
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.String),
            nullable=True,
            server_default=sa.text("'{}'::character varying[]"),
        ),
    )

    # --- tools: per-tool timeout / permissions / docs / health ------------
    _add_column_if_not_exists("tools", sa.Column("timeout_seconds", sa.Integer(), nullable=True))
    _add_column_if_not_exists(
        "tools",
        sa.Column(
            "allowed_roles",
            postgresql.ARRAY(sa.String),
            nullable=True,
            server_default=sa.text("'{}'::character varying[]"),
        ),
    )
    _add_column_if_not_exists("tools", sa.Column("documentation", sa.Text(), nullable=True))
    _add_column_if_not_exists("tools", sa.Column("health_status", sa.String(length=20), nullable=True))
    _add_column_if_not_exists(
        "tools", sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Unique (organization_id, name) so duplicate tool names 409 instead of crash.
    # ``ADD CONSTRAINT IF NOT EXISTS`` is not portable across PostgreSQL versions,
    # so guard the DDL with an existence check inside a DO block (transactional,
    # idempotent, and safe to re-run).
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "IF NOT EXISTS ("
            "SELECT 1 FROM pg_constraint WHERE conname = 'uq_tools_org_name'"
            ") THEN "
            "ALTER TABLE tools ADD CONSTRAINT uq_tools_org_name "
            "UNIQUE (organization_id, name); "
            "END IF; END $$;"
        )
    )

    # --- usage_events: analytics fields ------------------------------------
    _add_column_if_not_exists("usage_events", sa.Column("latency_ms", sa.Integer(), nullable=True))
    _add_column_if_not_exists("usage_events", sa.Column("status", sa.String(length=20), nullable=True))
    _add_column_if_not_exists("usage_events", sa.Column("error", sa.Text(), nullable=True))

    # --- new tables --------------------------------------------------------
    if not _table_exists("notifications"):
        op.create_table(
            "notifications",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("type", sa.String(length=50), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True,
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True,
                      server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_notifications_organization_id", "notifications", ["organization_id"])
        op.create_index("ix_notifications_user_id", "notifications", ["user_id"])

    if not _table_exists("webhook_subscriptions"):
        op.create_table(
            "webhook_subscriptions",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("event_type", sa.String(length=50), nullable=False),
            sa.Column("url", sa.String(length=500), nullable=False),
            sa.Column("secret", sa.String(length=255), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True,
                      server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_webhook_subscriptions_organization_id",
                        "webhook_subscriptions", ["organization_id"])

    if not _table_exists("webhook_deliveries"):
        op.create_table(
            "webhook_deliveries",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("event_type", sa.String(length=50), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("response_status", sa.Integer(), nullable=True),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True,
                      server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["subscription_id"], ["webhook_subscriptions.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_webhook_deliveries_organization_id",
                        "webhook_deliveries", ["organization_id"])
        op.create_index("ix_webhook_deliveries_subscription_id",
                        "webhook_deliveries", ["subscription_id"])

    if not _table_exists("background_tasks"):
        op.create_table(
            "background_tasks",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("task_type", sa.String(length=50), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True,
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True,
                      server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_background_tasks_organization_id",
                        "background_tasks", ["organization_id"])


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE tools DROP CONSTRAINT IF EXISTS uq_tools_org_name"))
    op.execute(sa.text("ALTER TABLE documents DROP COLUMN IF EXISTS tags"))
    op.execute(sa.text("ALTER TABLE documents DROP COLUMN IF EXISTS last_indexed_at"))
    op.execute(sa.text("ALTER TABLE documents DROP COLUMN IF EXISTS indexed_chunks"))
    op.execute(sa.text("ALTER TABLE documents DROP COLUMN IF EXISTS total_chunks"))
    op.execute(sa.text("ALTER TABLE documents DROP COLUMN IF EXISTS indexing_progress"))
    op.execute(sa.text("ALTER TABLE tools DROP COLUMN IF EXISTS last_checked_at"))
    op.execute(sa.text("ALTER TABLE tools DROP COLUMN IF EXISTS health_status"))
    op.execute(sa.text("ALTER TABLE tools DROP COLUMN IF EXISTS documentation"))
    op.execute(sa.text("ALTER TABLE tools DROP COLUMN IF EXISTS allowed_roles"))
    op.execute(sa.text("ALTER TABLE tools DROP COLUMN IF EXISTS timeout_seconds"))
    op.execute(sa.text("ALTER TABLE usage_events DROP COLUMN IF EXISTS error"))
    op.execute(sa.text("ALTER TABLE usage_events DROP COLUMN IF EXISTS status"))
    op.execute(sa.text("ALTER TABLE usage_events DROP COLUMN IF EXISTS latency_ms"))

    if _table_exists("background_tasks"):
        op.drop_table("background_tasks")
    if _table_exists("webhook_deliveries"):
        op.drop_table("webhook_deliveries")
    if _table_exists("webhook_subscriptions"):
        op.drop_table("webhook_subscriptions")
    if _table_exists("notifications"):
        op.drop_table("notifications")
