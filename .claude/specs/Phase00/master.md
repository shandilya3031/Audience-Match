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
  `app.llm.bedrock_clients`, use `app.config`, or run against a deployable API until
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
  (`LANGCHAIN_TRACING_V2`, `LANGCHAIN_PROJECT`) verified with one manual test trace
  before any agent code exists
- **4.4 Storage Bootstrap** — Pinecone index/namespace config, PostgreSQL table DDL +
  `app_readonly` read-only role, DynamoDB table definitions, S3 bucket definitions.
  Code/config definitions are in scope now; **actual cloud resource provisioning is
  deferred** — no AWS/Pinecone/PostgreSQL/DynamoDB credentials are confirmed
  available yet (see note under Data & Storage Touched)
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
- `app/llm/bedrock_clients.py`, `app/llm/model_router.py` — shared infrastructure
  imported by all future agents, not itself an agent

## Data & Storage Touched
- **Pinecone:** index config defined (serverless, cosine similarity, dimension to
  match the embedding model chosen in Phase 2); namespaces planned:
  `knowledge_base`, `cluster_profiles`, `schema_metadata`. **Not provisioned yet** —
  config/connection code only, pending credentials.
- **PostgreSQL:** DDL defined for `cluster_profiles`, `campaigns`,
  `channel_performance`, `customer_transactions`; a dedicated read-only role
  (`app_readonly`) defined now per CLAUDE.md — not retrofitted later. **Not
  provisioned yet** — pending credentials.
- **DynamoDB:** table definitions for `ChatHistory` (PK: `session_key`),
  `SchemaMetadata`, `PromptRegistry`. **Not provisioned yet** — pending credentials.
- **S3:** bucket definitions for `raw-documents/`, `raw-customer-data/`. **Not
  provisioned yet** — pending credentials.

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
- LangSmith project created; `LANGCHAIN_TRACING_V2=true` and
  `LANGCHAIN_PROJECT=audience-match-dev` set via `.env` / `app/config.py`
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
| 01 | Environment Config | feature01-environment-config.md | Not Started |

## Definition of Done (Phase Gate)
Per blueprint §4 / §21 ("0 — Foundations: Deploy pipeline works end-to-end, all
storage reachable"):

- [ ] All features in Scope above have specs and are implemented
- [ ] `docker build` succeeds
- [ ] Container runs locally
- [ ] `/health` returns 200
- [ ] A manual LangSmith trace appears for a test LLM call
- [ ] Pinecone/PostgreSQL/DynamoDB are reachable from the container — **or**, if
      credentials remain unavailable when this phase would otherwise close, this
      item is explicitly logged here as a deferred follow-up rather than silently
      dropped, and Phase 0 is not marked `Complete` until it is resolved one way or
      the other
- [ ] No unresolved items in Risk Register (blueprint §22) attributable to this phase
