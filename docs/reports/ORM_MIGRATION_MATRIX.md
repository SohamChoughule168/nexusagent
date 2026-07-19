# ORM ↔ Migration Audit Matrix — Phase 3C

**Date:** 2026-07-19
**Scope:** Every SQLAlchemy ORM model (`app/models/*.py`) vs the Alembic
migration chain (`backend/alembic/versions/001..008`).
**Method:** Authoritative comparison of `Base.metadata` (ORM) against the
actual schema produced by `alembic upgrade head` on a fresh database, plus
introspection of the existing `nexusagent` development database. All findings
below were **verified empirically**, not guessed.

---

## 1. Summary

| Category | Count | Status after Phase 3C |
|---|---|---|
| Missing tables (ORM has, migration lacked) | 1 | **RESOLVED** by 008 |
| Missing columns (ORM has, migration lacked) | 5 | **RESOLVED** by 008 |
| Extra columns (migration has, ORM lacks) | 5 | Intentionally left (harmless) |
| Extra tables (migration has, ORM lacks) | 2 | Intentionally left (harmless) |
| Type mismatches | 6 | Intentionally left (benign, see §4) |
| Default mismatches | many | Intentionally left (benign, see §5) |
| Constraint mismatches | 2 | Deferred (see §6 — cannot safely add) |
| Index mismatches | few | Intentionally left (benign, see §7) |

**Headline:** Before Phase 3C, 5 ORM columns and 1 ORM table were absent from a
migration-built database. These are exactly the objects that broke ORM writes
(`column "messages.updated_at" does not exist`, `column "documents.upload_member_id"
does not exist`). Migration **008_reconcile_schema_drift** adds all of them.
After 008, a fresh `alembic upgrade head` produces a schema whose tables and
columns exactly match `Base.metadata` (zero missing columns/tables).

---

## 2. Migration chain (after Phase 3C)

```
001_initial_migration → 002_rls_policies → 003_reconcile_orm_schema
  → 004_document_chunk_embedding → 005_reconcile_models
  → 006_long_term_memory → 007_kb_unique_name → 008_reconcile_schema_drift (head)
```

> **005 id fix:** the original revision id `005_reconcile_models_to_migrations`
> (34 chars) exceeds the standard `alembic_version.version_num` width of
> `VARCHAR(32)` that Alembic creates on a fresh database
> (`alembic/runtime/migration.py: Column("version_num", String(32))`). A fresh
> `alembic upgrade head` therefore failed at 005. Renamed to
> `005_reconcile_models` (21 chars). The existing dev DB is stamped at the head
> (`007_kb_unique_name`) and never records 005's id directly, so renaming is
> transparent.

---

## 3. Per-table matrix

Legend: ✅ match · ❌ was missing (now RESOLVED) · ➕ extra in DB (harmless) ·
⚠️ drift (see section)

| Table | ORM columns | Migration columns (post-008) | Missing | Extra | Notes |
|---|---|---|---|---|---|
| organizations | 12 | 12 | — | — | ➕ ix_organizations_plan index; ⚠️ type/default |
| users | 12 | 12 | — | — | ➕ ix_users_active; ⚠️ type/default |
| organization_members | 7 | 7 | — | — | ✅ (003 added updated_at) |
| knowledge_bases | 11 | 13 | — | embedding_provider, embedding_dimensions | ✅ (005 added chunk_size/overlap); ⚠️ extra cols |
| agents | 19 | 19 | — | — | ⚠️ type (temperature), ⚠️ constraint (public_id) |
| documents | 18 | 18 | — | — | ❌→✅ upload_member_id (008); ⚠️ type (file_size) |
| document_chunks | 14 | 14 | — | — | ❌→✅ updated_at (008); ✅ unique(doc,chunk) |
| conversations | 15 | 15 | — | — | ⚠️ type (cost), ⚠️ constraint (session_id) |
| messages | 14 | 15 | — | metadata | ❌→✅ updated_at (008); ➕ metadata col |
| tools | 11 | 11 | — | — | ✅ |
| leads | 13 | 13 | — | — | ✅ |
| api_keys | 11 | 11 | — | — | ❌→✅ updated_at (008) |
| usage_events | 13 | 13 | — | — | ❌→✅ updated_at (008); ⚠️ type (cost) |
| audit_logs | 11 | 13 | — | api_key_id, request_id | ❌→✅ updated_at (003); ➕ 2 cols |
| memories | 12 | 12 | — | — | ✅ (006) |
| organization_settings | 6 | 6 | — | — | ✅ (003) |
| system_settings | 7 | 7 | — | — | ✅ (003) |
| tool_configs | 7 | 7 | — (table ❌→✅) | — | ❌→✅ whole table (008) |
| agent_tools | — | 4 | — | whole table | ➕ migration-only, no ORM model |
| tool_executions | — | 11 | — | whole table | ➕ migration-only, no ORM model |

### The 6 gaps that broke ORM writes (all RESOLVED by 008)

| # | Object | ORM source | Why missing | Fix |
|---|---|---|---|---|
| 1 | `messages.updated_at` | `TimestampedModel` base column; 001 omitted it | inherited column not in 001 | 008 `ADD COLUMN` |
| 2 | `document_chunks.updated_at` | `TimestampedModel` base column; 001 omitted it | inherited column not in 001 | 008 `ADD COLUMN` |
| 3 | `api_keys.updated_at` | `TimestampedModel` base column; 001 omitted it | inherited column not in 001 | 008 `ADD COLUMN` |
| 4 | `usage_events.updated_at` | `TimestampedModel` base column; 001 omitted it | inherited column not in 001 | 008 `ADD COLUMN` |
| 5 | `documents.upload_member_id` | `Document.upload_member_id` | never migrated (001 has no such column) | 008 `ADD COLUMN` (nullable) |
| 6 | `tool_configs` (table) | `ToolConfig` model, used by `ToolConfigRepository` | never migrated at all | 008 `CREATE TABLE` |

> **Root cause:** `TimestampedModel` adds `created_at`/`updated_at` to every
> subclass. Migration 001 added `updated_at` to *some* subclasses (organizations,
> users, knowledge_bases, agents, documents, conversations, leads, tools,
> audit_logs) but missed `messages`, `document_chunks`, `api_keys`,
> `usage_events`. 003 later backfilled `organization_members` and `audit_logs`;
> 008 backfills the remaining four. `documents.upload_member_id` and the
> `tool_configs` table were simply never in any migration.

---

## 4. Type mismatches (benign — intentionally NOT altered)

PostgreSQL coerces between these types, so they do not break ORM reads/writes.
This matches the explicit rationale in migration 005 ("Type-level mismatches …
are intentionally not altered here to keep this migration low-risk").

| Column | ORM type | Migration type |
|---|---|---|
| `agents.temperature` | `Integer` | `Numeric(3,2)` |
| `documents.file_size` | `Integer` | `Numeric(20,0)` |
| `conversations.total_cost_usd` | `Float` | `Numeric(10,6)` |
| `messages.cost_usd` | `Float` | `Numeric(10,6)` |
| `usage_events.cost_usd` | `Float` | `Numeric(10,6)` |
| `users.last_login_at` / `created_at` / `updated_at` | `DateTime(timezone=True)` | `TIMESTAMP` (no tz) |

---

## 5. Default mismatches (benign — intentionally NOT altered)

The ORM declares `server_default` on timestamp/`id` columns
(`func.now()`, `gen_random_uuid()`); the migrations generally do not. Python-side
`default=` values cover every INSERT, so this causes no failures. Leaving it
avoids churning the schema. Examples: `created_at`/`updated_at` on most tables,
`id` UUID defaults on tables other than those created by 003/006/008.

---

## 6. Constraint mismatches (DEFERRED — cannot safely reconcile)

| Constraint | ORM | Migration | Verdict |
|---|---|---|---|
| `conversations.session_id` UNIQUE | `unique=True` | non-unique index `ix_convs_session` | Deferred. No duplicate `session_id` rows exist in dev DB, so it *could* be added, but left deferred for consistency with the low-risk pattern and to avoid constraining future inserts. |
| `agents.public_id` UNIQUE | `unique=True` | non-unique index `ix_agents_public_id` | **Cannot add.** The dev DB has 194 `agents` rows but only 176 distinct `public_id` values (18 duplicates), proving the application does not maintain uniqueness. Adding a UNIQUE constraint would fail the existing-DB upgrade and drop data. Left as residual drift. |

Neither of these caused test failures (ORM inserts use distinct values), so they
are out of scope for the migration-failure fix and are recorded here for
visibility.

---

## 7. Index / Extra-object mismatches (benign — intentionally left)

- **Extra columns in DB (not mapped by ORM):** `audit_logs.api_key_id`,
  `audit_logs.request_id`, `knowledge_bases.embedding_provider`,
  `knowledge_bases.embedding_dimensions`, `messages.metadata`. These are legacy
  columns from 001. The ORM never references them, so they are harmless; removing
  them would be "removing data" and is out of scope.
- **Extra tables in DB (no ORM model):** `agent_tools`, `tool_executions`.
  Migration-only legacy tables. Left in place (never remove data).
- **Extra indexes in DB (not in ORM):** `ix_users_active`, `ix_organizations_plan`,
  plus assorted index-naming differences reported by `alembic check`. These are
  benign and left as-is.

---

## 8. Validation evidence

- Fresh DB (`nexusagent_fresh`): `alembic upgrade head` succeeded through 008.
  Schema diff vs `Base.metadata` → **0 missing tables, 0 missing columns.**
- Existing dev DB (`nexusagent`): `alembic upgrade head` applied 008 only;
  `alembic_version` → `008_reconcile_schema_drift`. All reconciled objects
  present (`tool_configs`, the four `updated_at` columns, `documents.upload_member_id`).
- Backend test suite: **338 passed / 82 failed / 11 errors at 007 (before)** →
  **420 passed / 0 failed / 0 errors at 008 (after)**. Every before-failure was
  a `column "messages.updated_at" does not exist` or
  `column "documents.upload_member_id" does not exist` `ProgrammingError` — i.e.
  migration-related, now resolved.
- Seed (`seed_demo.py`) ran successfully on the migration-built DB: ingested and
  embedded 4 demo PDFs, created the agent and sample conversations.
