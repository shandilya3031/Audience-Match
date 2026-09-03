# Feature Spec — Phase 00.04: Storage Bootstrap

## Status
`Complete`

## Parent Phase
Phase 00 — see `.claude/specs/Phase00/master.md`

## Overview
Stands up Phase 0's storage layer: a local Chroma vector store, PostgreSQL
tables (including the memory tables originally planned for DynamoDB), and
local-filesystem directories (originally planned as S3 buckets). Per the
blueprint's "Storage follow-up" amendment (2026-09-01), DynamoDB and S3 were
folded into PostgreSQL and the local filesystem respectively at this feature's
kickoff — same rationale as the `00-06` LLM/vector-store pivot: no AWS account
should be required to develop this project solo. **Net effect: no AWS account
is needed for storage at all.** Only a local PostgreSQL instance is required
(e.g. via Docker) — confirm one is available before implementation starts, or
flag it so we can set one up first.

**Design note (resolves an ambiguity, not silently):** the blueprint names
`campaigns`, `channel_performance`, `customer_transactions` as PostgreSQL
tables but never defines their columns anywhere in the document. Per CLAUDE.md
§9 ("Don't hardcode table/column names anywhere outside the Aggregator's
schema retrieval path"), these are read as **pre-existing client marketing
data** with client-specific schema — not tables Audience Match defines. This
feature grants `app_readonly` SELECT access to whatever exists in the database
(current and future tables), rather than inventing columns for them. Only
`cluster_profiles` (Audience Match's own Segmenter output) and the three
folded-in memory tables get real DDL here.

## Depends On
- `00-01-environment-config` — `Settings`/`.env` plumbing
- `00-06-llm-provider-pivot` — supplies `chroma_persist_directory` and
  `embedding_model_name` settings this feature consumes for the first time

## Agent I/O Contract
No external contract — internal infrastructure, not an agent boundary.
Introduces these function signatures:

```python
# app/db/postgres.py
def get_connection() -> psycopg2.extensions.connection:
    """Connection using the app_user (read-write) DSN."""

def get_readonly_connection() -> psycopg2.extensions.connection:
    """Connection using the app_readonly (SELECT-only) DSN — this is the
    connection the Aggregator agent (Phase 3) will use."""

# app/vectorstore/chroma_client.py
def get_collection(name: str) -> Chroma:
    """Open (creating if needed) a local Chroma collection persisted to
    settings.chroma_persist_directory, using HuggingFaceEmbeddings built from
    settings.embedding_model_name. name must be one of KNOWLEDGE_BASE,
    CLUSTER_PROFILES, SCHEMA_METADATA."""

# app/storage/local_files.py
def raw_documents_path(filename: str) -> Path: ...
def raw_customer_data_path(filename: str) -> Path: ...
```

## LLM Call Sites
None. `HuggingFaceEmbeddings` runs the embedding model locally — it is not a
chat-completion call and does not get a `ROUTING_TABLE` entry (that table is
for LLM task routing, not embedding models).

## Data & Storage Changes

**PostgreSQL** — `infra/db/schema.sql`:
```sql
-- Read-only role for the Aggregator (Phase 3) and CLAUDE.md §4 rule 4's
-- DB-level enforcement layer (defense in depth alongside sql_guard.validate_sql()).
CREATE ROLE app_readonly WITH LOGIN PASSWORD :'app_readonly_password';
GRANT CONNECT ON DATABASE audience_match TO app_readonly;
GRANT USAGE ON SCHEMA public TO app_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO app_readonly;

-- Segmenter output (Phase 1) — Audience Match's own data, real DDL
CREATE TABLE IF NOT EXISTS cluster_profiles (
    cluster_id SERIAL PRIMARY KEY,
    client_id VARCHAR(255) NOT NULL,
    cluster_name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    summary_points JSONB NOT NULL,
    member_count INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cluster_profiles_client_id ON cluster_profiles(client_id);

-- Folded in from DynamoDB (see blueprint's "Storage follow-up" amendment)
CREATE TABLE IF NOT EXISTS chat_history (
    id BIGSERIAL PRIMARY KEY,
    session_key VARCHAR(255) NOT NULL,  -- {user_id}_{module}_{session_id}, CLAUDE.md §4 rule 7
    turn_index INT NOT NULL,
    role VARCHAR(20) NOT NULL,          -- 'human' | 'ai' | 'system'
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_history_session_key ON chat_history(session_key);

CREATE TABLE IF NOT EXISTS schema_metadata (
    table_name VARCHAR(255) PRIMARY KEY,
    enriched_description TEXT NOT NULL,
    sample_rows JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prompt_registry (
    id BIGSERIAL PRIMARY KEY,
    agent VARCHAR(100) NOT NULL,
    prompt_version VARCHAR(50) NOT NULL,
    prompt_text TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(agent, prompt_version)
);

-- campaigns / channel_performance / customer_transactions: NOT created here —
-- pre-existing client data, schema unknown to this feature. app_readonly's
-- broad SELECT grants above cover them once they exist.
```
`schema.sql` is idempotent (`CREATE ... IF NOT EXISTS`) so it can be re-run
safely; no migration tool (Alembic etc.) is introduced at this stage.

**Chroma:** three collections in one local persist directory
(`settings.chroma_persist_directory`) — `knowledge_base` (Phase 2 RAG),
`cluster_profiles` (Phase 1 Segmenter), `schema_metadata` (Phase 3
Aggregator). Cosine similarity, dimension determined by
`settings.embedding_model_name` (`sentence-transformers/all-mpnet-base-v2` →
768-dim).

**Local filesystem** (folded in from S3): `data/raw_documents/` and
`data/raw_customer_data/`, created on first use if missing. Paths come from
new `Settings` fields, not hardcoded.

## Guardrails Checklist
Not applicable — internal infra, no user-facing endpoint or agent output yet.

- [ ] Input filtering — N/A
- [ ] SQL guard — N/A this feature (creates the DB-level read-only role that
      `sql_guard.validate_sql()` will sit alongside in Phase 3, per CLAUDE.md
      §4 rule 4's "both layers must exist" requirement — this feature
      delivers the DB-level half now)
- [ ] Output is validated Pydantic, not raw text — N/A
- [ ] Citations/sources included for factual claims — N/A
- [ ] Similarity threshold check before generation — N/A (no retrieval/
      generation happens yet; that's Phase 2)
- [ ] Synchronous faithfulness/grounding check — N/A
- [ ] Adversarial test cases to add to `tests/e2e/` — N/A

## Golden Eval Cases to Add
No eval additions — non-agent-facing change.

## Files to Create
- `infra/db/schema.sql` — DDL above. **Implementation refinement:** `CREATE
  ROLE` has no native `IF NOT EXISTS` form, so role creation is wrapped in a
  `DO $$ ... IF NOT EXISTS (SELECT FROM pg_roles ...) $$` block to keep the
  file genuinely idempotent. The password is a `__APP_READONLY_PASSWORD__`
  placeholder, not the spec's original `psql`-CLI-specific `:'var'` syntax.
- `scripts/apply_schema.py` — **added during implementation, not in the
  original spec draft.** Runs `schema.sql` via `psycopg2` directly (safely
  substituting the password placeholder with `psycopg2.sql.Literal`), since
  Postgres runs in Docker and the `psql` CLI isn't assumed to be on the host.
- `app/db/__init__.py`, `app/db/postgres.py` — `get_connection()`,
  `get_readonly_connection()`, both reading DSNs from `app.config.settings`
- `app/vectorstore/__init__.py`, `app/vectorstore/chroma_client.py` —
  `get_collection(name)`, plus `KNOWLEDGE_BASE`/`CLUSTER_PROFILES`/
  `SCHEMA_METADATA` name constants
- `app/storage/__init__.py`, `app/storage/local_files.py` —
  `raw_documents_path()`, `raw_customer_data_path()`, directory
  auto-creation
- `tests/unit/test_storage_bootstrap.py` — Chroma + local filesystem tests
  (no external services needed)
- `tests/integration/__init__.py`, `tests/integration/test_postgres.py` —
  **split out from the originally-planned single `tests/unit` file**,
  matching CLAUDE.md §10's own `tests/unit` (no external deps) vs
  `tests/integration` (needs real services) distinction — Postgres
  connection + read-only-enforcement tests need the live container

## Files to Modify
- `app/config.py` — remove `dynamodb_chat_history_table`,
  `dynamodb_schema_metadata_table`, `dynamodb_prompt_registry_table`,
  `s3_raw_documents_bucket`, `s3_raw_customer_data_bucket`; add
  `raw_documents_dir: str = "./data/raw_documents"`,
  `raw_customer_data_dir: str = "./data/raw_customer_data"`,
  `postgres_readonly_password: str` (needed to actually create the
  `app_readonly` role from `schema.sql`, not just connect as it)
- `.env.example`, local `.env` — DynamoDB/S3 blocks removed; local storage
  dir vars added; `POSTGRES_READONLY_PASSWORD` added
- `requirements.txt` — add `psycopg2-binary`, `langchain-chroma`, `chromadb`,
  `langchain-huggingface`, `sentence-transformers`

## New Dependencies
- `psycopg2-binary` — PostgreSQL driver
- `langchain-chroma`, `chromadb` — local vector store
- `langchain-huggingface`, `sentence-transformers` — local embedding model
  (note: `sentence-transformers/all-mpnet-base-v2` is a ~420MB PyTorch model
  downloaded on first use — free, but a real one-time bandwidth/disk cost
  worth knowing about going in, unlike a hosted embeddings API)

## Rules for Implementation
- **CLAUDE.md §4 rule 4**: "No SQL reaches PostgreSQL without passing
  `sql_guard.validate_sql()` ... in addition to (never instead of) the
  DB-level read-only role. Both layers must exist." This feature delivers the
  DB-level half (`app_readonly`); `sql_guard.validate_sql()` itself is Phase 3
  (Aggregator).
- **CLAUDE.md §4 rule 7**: session keys follow `{user_id}_{module}_{session_id}`
  — `chat_history.session_key` is shaped for this now; the key-generation
  logic itself (`app/memory/session_keys.py`) is Phase 6.
- **CLAUDE.md §4 rule 10**: no secrets in code — `POSTGRES_READONLY_PASSWORD`
  and all DSNs come from `app.config.settings`, never hardcoded in
  `schema.sql` (parameterized via `psql -v` or equivalent) or `postgres.py`.
- **CLAUDE.md §9**: don't hardcode table/column names outside the
  Aggregator's schema retrieval path — this is why `campaigns`/
  `channel_performance`/`customer_transactions` get no invented columns here.
- No raw `ChatGroq(...)` outside `app/llm/llm_clients.py` — unaffected by
  this feature, restated as a standing rule.
- No free-text agent-to-agent handoffs — not applicable, no agents exist yet.

## Definition of Done
- [x] `infra/db/schema.sql`, run against a local PostgreSQL instance
      (`scripts/apply_schema.py`, since `psql` CLI isn't assumed to be on the
      host — see the file's own header comment), creates `cluster_profiles`,
      `chat_history`, `schema_metadata`, `prompt_registry`, the
      `app_readonly` role, and its SELECT grants without error, and is
      safely re-runnable (verified: ran twice, no errors either time)
- [x] `app/db/postgres.get_connection()` and `get_readonly_connection()`
      both connect successfully using `settings.postgres_dsn` /
      `settings.postgres_readonly_dsn` (`tests/integration/test_postgres.py`)
- [x] A write (`INSERT`) attempted via the readonly connection fails with
      `psycopg2.errors.InsufficientPrivilege` — concrete proof the read-only
      guarantee actually holds, not just that the role exists
      (`test_readonly_connection_cannot_write`)
- [x] `app/vectorstore/chroma_client.get_collection(...)` successfully
      creates/opens all three named collections, persisted under
      `settings.chroma_persist_directory`
- [x] `app/storage/local_files.py` creates `data/raw_documents/` and
      `data/raw_customer_data/` if missing, and returns correct paths
- [x] `tests/unit/test_storage_bootstrap.py` and
      `tests/integration/test_postgres.py` both pass (11/11 total across
      `tests/unit` + `tests/integration`)
- [x] No `CLAUDE.md` §4 or §9 rule violations (self-check)

## Out of Scope
- Real DDL/columns for `campaigns`, `channel_performance`,
  `customer_transactions` — pre-existing client data with unknown schema;
  Aggregator (Phase 3) introspects via the semantic schema index
- Document/CSV ingestion pipelines (chunking, embedding, upsert into these
  collections/tables) — Phase 1 (Segmenter) and Phase 2 (RAG) build the
  pipelines that populate the empty scaffolding this feature creates
- `app/memory/session_keys.py`, summarization, memory read/write logic —
  Phase 6 (Memory Architecture); this feature only creates `chat_history`'s
  storage shape
- `sql_guard.validate_sql()` itself — Phase 3 (Aggregator)
- Migration tooling (Alembic, etc.) — a single idempotent `schema.sql` is
  sufficient at this stage
- Containerized local Postgres setup (e.g. `docker-compose.yml`) — only in
  scope if the user doesn't already have a local Postgres instance available;
  confirm before implementation
