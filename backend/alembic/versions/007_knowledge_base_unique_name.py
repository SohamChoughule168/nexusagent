"""Knowledge base unique (organization_id, name) constraint.

Revision ID: 007_kb_unique_name
Revises: 006_long_term_memory
Create Date: 2026-07-19 00:00:07.000000

Ensures exactly ONE UNIQUE constraint on (organization_id, name) exists on
the ``knowledge_bases`` table, named ``uq_knowledge_bases_org_name`` to
match the ORM ``KnowledgeBase.__table_args__``.

NOTE ON HISTORY: a UNIQUE (organization_id, name) constraint has existed
since migration 001 (auto-named ``knowledge_bases_organization_id_name_key``).
The ORM model later gained ``UniqueConstraint(name="uq_knowledge_bases_org_name")``,
so the live schema had TWO identical, redundantly-named constraints. This
migration converges to the single canonical, explicitly-named constraint and
drops the legacy auto-named one so the schema matches the model.

The DB-level constraint is the source of truth; the REST API's try/except that
turns the resulting IntegrityError into a 409 is just a friendly wrapper.

Robustness notes for the upgrade path:

* Idempotent: if the canonical constraint already exists (e.g. a re-run, or a
  database built via ``Base.metadata.create_all`` which already has it), it is a
  no-op rather than erroring with "already exists".
* Self-healing: the legacy auto-named constraint, if still present, is dropped
  so we never end up with two redundant constraints again.
* Graceful on duplicates: Postgres would otherwise fail the ``ALTER TABLE ... ADD
  CONSTRAINT`` with an opaque "could not create unique index" error. Instead we
  detect duplicate (organization_id, name) groups first and raise a clear,
  actionable ``CommandError`` listing exactly which rows to resolve.
"""

from alembic import op
from alembic.util import CommandError
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '007_kb_unique_name'
down_revision = '006_long_term_memory'
branch_labels = None
depends_on = None

# Canonical name, matching KnowledgeBase.__table_args__ in app/models/all_models.
CANONICAL = "uq_knowledge_bases_org_name"
# Legacy auto-named constraint added by migration 001 (UniqueConstraint without a
# name -> Postgres names it <table>_<cols>_key).
LEGACY = "knowledge_bases_organization_id_name_key"


def _constraint_exists(bind, name: str) -> bool:
    return bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_name = 'knowledge_bases' AND constraint_name = :name"
        ).bindparams(name=name)
    ).first() is not None


def _drop_if_exists(bind, name: str) -> None:
    if _constraint_exists(bind, name):
        op.drop_constraint(name, "knowledge_bases", type_="unique")


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Detect duplicate (organization_id, name) groups BEFORE touching the
    #    constraint, and fail with a clear, actionable message instead of a raw
    #    Postgres "could not create unique index" error.
    duplicates = bind.execute(sa.text(
        "SELECT organization_id, name, count(*) "
        "FROM knowledge_bases "
        "GROUP BY organization_id, name HAVING count(*) > 1"
    )).fetchall()
    if duplicates:
        rows = "\n".join(
            f"  organization_id={org_id} name={name!r} (rows={cnt})"
            for org_id, name, cnt in duplicates
        )
        raise CommandError(
            "Cannot add UNIQUE constraint "
            f"{CANONICAL}: found {len(duplicates)} duplicate "
            "(organization_id, name) group(s):\n"
            f"{rows}\n"
            "Resolve the duplicates (keep a single row per organization + name) "
            "and re-run 'alembic upgrade head'."
        )

    # 2. If the canonical constraint already exists, just ensure the legacy
    #    stray is gone (idempotent, no-op when already clean).
    if _constraint_exists(bind, CANONICAL):
        _drop_if_exists(bind, LEGACY)
        return

    # 3. Canonical missing: drop the legacy auto-named constraint (if any)
    #    and create the canonical one.
    _drop_if_exists(bind, LEGACY)
    op.create_unique_constraint(
        CANONICAL,
        "knowledge_bases",
        ["organization_id", "name"],
    )


def downgrade() -> None:
    # Only drop if it exists, so a no-op re-run (or a database built without
    # it) does not error with "constraint does not exist". The legacy
    # auto-named constraint is intentionally left in place on downgrade (it is
    # the pre-existing 001 constraint and is not this migration's to remove).
    bind = op.get_bind()
    if not _constraint_exists(bind, CANONICAL):
        return
    op.drop_constraint(
        CANONICAL,
        "knowledge_bases",
        type_="unique",
    )
