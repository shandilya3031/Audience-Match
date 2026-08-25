# Feature Spec — Phase 00.01: Environment Config

## Status
`Complete`

## Parent Phase
Phase 00 — see `.claude/specs/Phase00/master.md`

## Overview
Establishes `app/config.py`, a single `pydantic-settings`-based `Config`/`settings`
object that every later module reads typed configuration from — AWS/Bedrock
credentials, Pinecone/PostgreSQL/DynamoDB/S3 connection info, LangSmith keys, and an
`environment` field distinguishing dev/staging/prod. This is the concrete
implementation of CLAUDE.md §4 rule 10 ("Config comes from environment variables via
`app/config.py`. If you find yourself typing an API key... into a file, stop.") and is
a leaf dependency for every other Phase 0 feature (LLM clients, observability,
storage, the skeleton API all read settings from here).

## Depends On
None — this is the first feature in Phase 0 and has no internal dependencies.

## Agent I/O Contract
No external contract — internal infrastructure, not an agent boundary. This feature
introduces one class and one function signature:

```python
# app/config.py
class Settings(BaseSettings):
    app_env: Literal["dev", "staging", "prod"] = "dev"

    # Bedrock / AWS
    aws_region: str
    bedrock_sonnet_model_id: str
    bedrock_haiku_model_id: str
    bedrock_fallback_model_id: str

    # Pinecone
    pinecone_api_key: str
    pinecone_environment: str
    pinecone_index_name: str

    # PostgreSQL
    postgres_dsn: str
    postgres_readonly_dsn: str

    # DynamoDB
    dynamodb_chat_history_table: str = "ChatHistory"
    dynamodb_schema_metadata_table: str = "SchemaMetadata"
    dynamodb_prompt_registry_table: str = "PromptRegistry"

    # S3
    s3_raw_documents_bucket: str
    s3_raw_customer_data_bucket: str

    # LangSmith
    langchain_tracing_v2: bool = True
    langchain_api_key: str
    langchain_project: str = "audience-match-dev"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
```

## LLM Call Sites
None.

## Data & Storage Changes
None. This feature defines the *names and connection strings* for Pinecone,
PostgreSQL, DynamoDB, and S3 as typed settings fields, but does not connect to,
create, or query any of them — that belongs to feature `00-04-storage-bootstrap` and
to each resource's consuming phase.

## Guardrails Checklist
Not applicable — no user-facing endpoint or LLM call is introduced by this feature.

- [ ] Input filtering — N/A
- [ ] SQL guard — N/A
- [ ] Output is validated Pydantic, not raw text — N/A (no output produced)
- [ ] Citations/sources included for factual claims — N/A
- [ ] Similarity threshold check before generation — N/A
- [ ] Synchronous faithfulness/grounding check — N/A
- [ ] Adversarial test cases to add to `tests/e2e/` — N/A

## Golden Eval Cases to Add
No eval additions — non-agent-facing change.

## Files to Create
- `app/__init__.py` — empty, makes `app` a package
- `app/config.py` — `Settings` class + module-level `settings` instance, as above
- `.env.example` — every field above listed with a placeholder value (no real
  secrets), e.g. `PINECONE_API_KEY=your-pinecone-api-key-here`
- `requirements.txt` — created here with the two dependencies this feature needs
  (`pydantic-settings`, `python-dotenv`); later features append to it rather than
  recreating it

## Files to Modify
None (no pre-existing files touch this feature).

## New Dependencies
- `pydantic-settings` — typed settings management from environment variables
- `python-dotenv` — required by `pydantic-settings` for `.env` file loading

## Rules for Implementation
- **CLAUDE.md §4 rule 10** (the rule this feature exists to satisfy): "No secrets in
  code, ever. Config comes from environment variables via `app/config.py`." Every
  field in `Settings` must come from an environment variable with no hardcoded
  default for anything secret (API keys, DSNs) — only non-secret fields (table names,
  `app_env`, `langchain_project`) may have defaults.
- No raw `ChatBedrock()` outside `app/llm/bedrock_clients.py` — not applicable here
  (no LLM instantiation in this feature), but `Settings` is what feature `00-02` will
  read `bedrock_*_model_id` from, so field names must be stable once set.
- No LLM call without a `ROUTING_TABLE` entry — not applicable, no LLM calls here.
- No free-text agent-to-agent handoffs — not applicable, no agents exist yet.

## Definition of Done
- [x] `app/config.py` loads settings from environment variables via
      `pydantic-settings`, with typed fields for AWS/Bedrock, Pinecone, PostgreSQL
      (including the read-only DSN), DynamoDB, S3, and LangSmith, plus `app_env`
- [x] `.env.example` is committed with a placeholder for every `Settings` field and
      contains zero real secrets
- [x] `from app.config import settings` succeeds in a fresh Python process after
      copying `.env.example` to `.env` and filling in placeholder (non-real) values
- [x] `Settings` also loads correctly from real environment variables with no `.env`
      file present (verifies container/CI compatibility, where `.env` won't exist)
- [x] Missing a required field (e.g. no `PINECONE_API_KEY` set) raises a clear
      `pydantic` validation error rather than silently defaulting
- [x] No `CLAUDE.md` §4 or §9 rule violations (self-check) — specifically no
      hardcoded secret values anywhere in `app/config.py` or committed to git

## Out of Scope
- Actually instantiating Bedrock clients (`app/llm/bedrock_clients.py`) — feature
  `00-02-llm-clients`
- Verifying LangSmith tracing works end-to-end — feature `00-03-observability-bootstrap`
- Provisioning or connecting to Pinecone/PostgreSQL/DynamoDB/S3 — feature
  `00-04-storage-bootstrap`
- The FastAPI app that will import `settings` — feature `00-05-skeleton-api`
- Docker packaging / final `requirements.txt` contents (FastAPI, uvicorn, etc.) —
  feature `00-06-docker-and-deps`
