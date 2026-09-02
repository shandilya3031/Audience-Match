# Master Spec — Phase 00: Foundations

## Status
`In Progress`

## Overview
Phase 0 stands up the skeleton every later phase depends on: environment/config
plumbing, the single choke point for LLM instantiation, observability wiring, storage
scaffolding, and a deployable skeleton FastAPI app. Per CLAUDE.md §2 and blueprint §1
principle 5 ("observability is a day-1 dependency, not a day-90 feature"), this phase
exists so that no later phase is ever blocked on infra that should have existed from
the start, and so every chain built from Phase 1 onward is traced automatically with
zero extra work later.

## Position in Build Order
- **Depends on (must be complete):** None — this is the root phase.
- **Blocks (cannot start until this is done):** All of Phase 1 (Segmenter), Phase 2
  (RAG), Phase 3 (Aggregator), and every phase after them — none of them can import
  `app.llm.llm_clients`, use `app.config`, or run against a deployable API until
  this phase's skeleton exists (CLAUDE.md §2, §4 rule 1).

## Scope
- **4.1 Environment & Config** — `pydantic-settings`-based `Config` class reading from
  environment variables (12-factor); `.env.example` committed, `.env` gitignored;
  separate config handling for `dev` / `staging` / `prod`
- **4.2 LLM Clients** — `app/llm/bedrock_clients.py` exposing `sonnet`, `haiku`, and
  `robust_sonnet` (with fallback chain to `haiku` then a Llama fallback model);
  `app/llm/model_router.py` with an (initially empty) `ROUTING_TABLE` that later
  phases populate by task name (CLAUDE.md §4 rules 1–2)
- **4.3 Observability Bootstrap** — LangSmith project wiring
  (`LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`) verified with one
  manual test trace before any agent code exists
- **4.4 Storage Bootstrap** — Chroma (local vector store) collection/namespace
  config; PostgreSQL table DDL (`cluster_profiles`, `campaigns`,
  `channel_performance`, `customer_transactions`, plus `chat_history`,
  `schema_metadata`, `prompt_registry` folded in from the original DynamoDB
  plan) + `app_readonly` read-only role; local filesystem directories
  (`data/raw_documents/`, `data/raw_customer_data/`) folded in from the
  original S3 plan. Per the blueprint's "Storage follow-up" amendment
  (2026-09-01), no AWS account is needed for storage at all — Chroma is
  local/embedded, DynamoDB was folded into PostgreSQL, and S3 was folded into
  the local filesystem. Only a local PostgreSQL instance is required, and
  actual provisioning (running the DDL against it) is in scope for this
  feature, not deferred.
- **4.5 Skeleton FastAPI App** — `app/main.py`, `/health` endpoint, an empty `/chat`
  endpoint that echoes input (no LLM call) — proves the deployment pipeline
  end-to-end before any AI logic exists
- **Docker & dependencies** — `requirements.txt`, multi-stage non-root
  `infra/docker/Dockerfile` (blueprint §16.2 pattern) — required because this phase's
  Definition of Done includes `docker build` succeeding locally

## Out of Scope
- Any agent implementation (Segmenter, RAG, Aggregator, Supervisor, Campaign
  Briefing) — Phase 1 onward, per CLAUDE.md §2 build order
- Populating `ROUTING_TABLE` with real task entries — later phases add their own as
  they introduce call sites
- Memory architecture implementation (Phase 6), guardrails implementation beyond
  what's structurally needed for `/chat` to exist (Phase 7), caching (Phase 10)
- CI/CD pipeline (Phase 12) and cloud deployment (Phase 13) — Phase 0 only needs
  `docker build` to succeed locally, not a working pipeline
- Golden datasets and eval scripts (Phase 8) — `eval/`, `tests/`, `scripts/`
  directories are scaffolded empty for structure, no content
- Actual cloud resource provisioning (real Pinecone index, RDS instance, DynamoDB
  tables, S3 buckets) — deferred until credentials are confirmed available

## Agent / Module Contracts Touched
None. Phase 0 creates no agents and no `AgentInput`/`AgentOutput` Pydantic contracts —
those begin in Phase 1. It creates two new non-agent modules:
- `app/config.py` — not agent-facing, no Pydantic I/O contract
- `app/llm/llm_clients.py`, `app/llm/model_router.py` — shared infrastructure
  imported by all future agents, not itself an agent

## Data & Storage Touched
- **Chroma:** local collection config defined (cosine similarity, dimension to
  match the embedding model chosen in Phase 2); namespaces/collections planned:
  `knowledge_base`, `cluster_profiles`, `schema_metadata`. Local/embedded — no
  cloud credentials needed; not yet provisioned since feature `00.04` hasn't been
  implemented.
- **PostgreSQL:** DDL defined for `cluster_profiles`, `campaigns`,
  `channel_performance`, `customer_transactions`, plus `chat_history` (keyed on
  `session_key`, per CLAUDE.md §4 rule 7's `{user_id}_{module}_{session_id}`
  convention), `schema_metadata`, `prompt_registry` (folded in from the
  original DynamoDB plan — see blueprint's "Storage follow-up" amendment); a
  dedicated read-only role (`app_readonly`) defined now per CLAUDE.md — not
  retrofitted later. Provisioning against a local PostgreSQL instance is in
  scope for feature `00.04`.
- **DynamoDB:** no longer used — folded into PostgreSQL (see above).
- **S3:** no longer used — folded into local filesystem directories
  (`data/raw_documents/`, `data/raw_customer_data/`), see blueprint amendment.

## LLM Usage in This Phase
None yet. This phase only builds the routing *infrastructure* — `ROUTING_TABLE` in
`app/llm/model_router.py` starts empty; later phases register their own call sites by
task name (CLAUDE.md §4 rule 2). The one exception is a manual, one-off
`sonnet.invoke(...)` or `haiku.invoke(...)` call used purely to verify the LangSmith
trace appears (Observability Requirements below) — this is a verification step, not a
production call site, and does not get a `ROUTING_TABLE` entry.

## Guardrails Required
None apply yet. The skeleton `/chat` endpoint is a pure echo with no LLM call and no
user-facing generated content, so none of the CLAUDE.md §6 checklist items
(input filtering, SQL guard, output validation, citations, retrieval threshold,
faithfulness check, adversarial tests) are applicable until an agent exists behind
it. Revisit this checklist starting with the first agent that gives `/chat` real
behavior (Phase 1+).

## Evaluation Requirements
None. Golden datasets and `eval/run_*_eval.py` gating scripts begin with Phase 1
(Segmenter). This phase only creates the empty `eval/golden_datasets/` directory for
structure.

## Observability Requirements
- LangSmith project created; `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, and
  `LANGSMITH_PROJECT=audience-match-dev` set via `.env` / `app/config.py` (current
  LangSmith env var naming, per the installed `langsmith-trace` skill — `app.config`
  also explicitly exports these to `os.environ`, since LangChain's tracer reads the
  process environment directly rather than any Settings object)
- Verified with one manual test trace (a single `sonnet.invoke(...)` or
  `haiku.invoke(...)` call) showing up in the LangSmith project — this is what proves
  wiring is correct before any agent code depends on it
- No `agent` / `prompt_version` tag convention to enforce yet (no chains exist) —
  that convention starts being enforced from each agent's first commit, Phase 1
  onward

## Feature Specs Index
_Populated automatically by `/create-feature-spec` as features are created.
Do not edit manually._

| # | Feature | Spec file | Status |
|---|---|---|---|
| 01 | Environment Config | feature01-environment-config.md | Complete |
| 02 | LLM Clients | feature02-llm-clients.md | Complete (provider superseded by 06) |
| 03 | Observability Bootstrap | feature03-observability-bootstrap.md | Complete |
| 06 | LLM Provider Pivot | feature06-llm-provider-pivot.md | Complete |
| 04 | Storage Bootstrap | feature04-storage-bootstrap.md | Complete |
| 05 | Skeleton FastAPI App | feature05-skeleton-fastapi-app.md | Complete |

## Definition of Done (Phase Gate)
Per blueprint §4 / §21 ("0 — Foundations: Deploy pipeline works end-to-end, all
storage reachable"):

- [ ] All features in Scope above have specs and are implemented
- [ ] `docker build` succeeds
- [ ] Container runs locally
- [ ] `/health` returns 200
- [x] A manual LangSmith trace appears for a test LLM call (`ChatGroq success`,
      `audience-match-dev`, 2026-09-01 10:49:53 UTC — feature `00-03`/`00-06`)
- [ ] Chroma/PostgreSQL are reachable from the container — both are local/no-AWS-
      account-needed per the storage follow-up amendment (DynamoDB folded into
      PostgreSQL, S3 folded into local filesystem); if a local PostgreSQL instance
      isn't available when this phase would otherwise close, this item is
      explicitly logged here as a deferred follow-up rather than silently dropped
- [ ] No unresolved items in Risk Register (blueprint §22) attributable to this phase
