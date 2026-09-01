# Feature Spec — Phase 00.06: LLM Provider Pivot (Bedrock → Groq)

## Status
`In Progress` — code complete; blocked on the user obtaining a real Groq API key
and running the final verification (see Definition of Done below).

## Parent Phase
Phase 00 — see `.claude/specs/Phase00/master.md`

## Overview
Replaces AWS Bedrock with **Groq** as the LLM inference provider, and updates the
Phase 0 config scaffold to point the (not-yet-implemented) vector store at
**Chroma** instead of Pinecone. This is a solo-project cost/friction elimination
pass, not a Phase 1+ feature: AWS Bedrock model access never got approved despite
a valid AWS account, correct model IDs, and correct inference-profile syntax (see
`feature03-observability-bootstrap.md`'s error history) — and Bedrock costs money
even once approved. Groq issues a free API key instantly (no waitlist) and hosts
open-weight models, preserving the project's "open models via a managed API"
character without direct-to-provider billing. Pinecone is similarly a paid/quota-
gated cloud service; Chroma is an embedded, local, open-source vector DB that
needs no account or provisioning at all. Full rationale and the substitution table
live in the blueprint's "Architecture Amendment — Open-Source/Zero-Cost Pivot"
section.

This feature **supersedes `00-02-llm-clients`'s provider choice** (that feature's
spec is marked `Complete (provider superseded by 06)`, not rewritten) and directly
**unblocks `00-03-observability-bootstrap`**, whose final Definition of Done item
has been stuck on unavailable Bedrock credentials for several sessions.

**Scope:** LLM inference + embeddings + vector store only. PostgreSQL, DynamoDB,
S3, and AWS ECS Fargate are unchanged — those decisions are deferred to
`00-04-storage-bootstrap` and the deployment phases, where they aren't blocking
anything yet.

**Model IDs (verified via WebSearch, Sept 2026):** `llama-3.3-70b-versatile` and
`llama-3.1-8b-instant` — the models a naive port of the blueprint's original intent
would reach for — were **deprecated by Groq on 2026-06-17**. This feature uses the
current recommended replacements instead: `openai/gpt-oss-120b` (sonnet-tier),
`openai/gpt-oss-20b` (haiku-tier), `qwen/qwen3.6-27b` (fallback-tier, different
model family for real fallback diversity). Re-check
https://console.groq.com/docs/models before assuming a future invoke failure is
anything other than another stale model ID — this exact class of bug already cost
significant time with Bedrock inference-profile IDs.

## Depends On
- `00-01-environment-config` — `Settings`/`.env` plumbing this feature repoints
- `00-02-llm-clients` — the file/pattern this feature supersedes in place

## Agent I/O Contract
No external contract — internal infrastructure, not an agent boundary.

```python
# app/llm/llm_clients.py (renamed from bedrock_clients.py)
sonnet: ChatGroq
haiku: ChatGroq
robust_sonnet: Runnable  # sonnet.with_fallbacks([haiku, fallback_model])
```

## LLM Call Sites
None registered in `ROUTING_TABLE` — unchanged from `00-02`; this feature only
swaps the provider behind the existing exported names.

## Data & Storage Changes
- `app/config.py`: removed `aws_region`, `bedrock_sonnet_model_id`,
  `bedrock_haiku_model_id`, `bedrock_fallback_model_id`,
  `aws_bearer_token_bedrock`; added `groq_api_key`, `groq_sonnet_model_id`,
  `groq_haiku_model_id`, `groq_fallback_model_id`
- `app/config.py`: removed `pinecone_api_key`, `pinecone_environment`,
  `pinecone_index_name`; added `chroma_persist_directory` (default
  `./data/chroma`) and `embedding_model_name` (default
  `sentence-transformers/all-mpnet-base-v2`) — scaffolded ahead of
  `00-04-storage-bootstrap` actually consuming them, matching the precedent
  `00-01` already set (Pinecone fields existed in config before any Pinecone
  client code did)
- No vector-store client code is created yet — that's `00-04`'s job. This feature
  only updates the config fields it scaffolds ahead of time.

## Guardrails Checklist
Not applicable — internal infra, no user-facing endpoint or agent output.

- [ ] Input filtering — N/A
- [ ] SQL guard — N/A
- [ ] Output is validated Pydantic, not raw text — N/A
- [ ] Citations/sources included for factual claims — N/A
- [ ] Similarity threshold check before generation — N/A
- [ ] Synchronous faithfulness/grounding check — N/A
- [ ] Adversarial test cases to add to `tests/e2e/` — N/A

## Golden Eval Cases to Add
No eval additions — non-agent-facing change.

## Files to Create
- `app/llm/llm_clients.py` — replaces `app/llm/bedrock_clients.py` (deleted);
  `sonnet`, `haiku`, `fallback_model`, `robust_sonnet`, all `ChatGroq` instances
  built from `app.config.settings`

## Files to Modify
- `app/config.py` — see Data & Storage Changes above
- `.env.example`, local `.env` — Bedrock/AWS block → Groq block; Pinecone block →
  Chroma block
- `requirements.txt` — remove `langchain-aws`, `boto3`; add `langchain-groq`
- `tests/unit/test_llm_clients.py` — `ALLOWED_FILE` now points at
  `app/llm/llm_clients.py`; forbidden-substring check is `"ChatGroq("` instead of
  `"ChatBedrock("`
- `scripts/verify_langsmith_trace.py` — import path updated to
  `app.llm.llm_clients`
- `CLAUDE.md` — stack line, repo-structure line, and Rule 1 updated to
  Groq/Chroma/`ChatGroq`/`llm_clients.py`
- `Audience_Match_Implementation_Blueprint.md` — new Architecture Amendment
  section; Phase 0 §4.2/§4.4/DoD snippets updated in place
- `.claude/specs/Phase00/feature02-llm-clients.md` — superseded note added
- `.claude/specs/Phase00/feature03-observability-bootstrap.md` — Bedrock/import
  references updated to Groq/`llm_clients.py`
- `.claude/specs/Phase00/master.md` — Feature Specs Index row added; Pinecone →
  Chroma references updated in Scope/Data & Storage Touched/DoD

## New Dependencies
- `langchain-groq` — `ChatGroq`

## Rules for Implementation
- **CLAUDE.md §4 rule 1**: "No raw `ChatGroq(...)` instantiation outside
  `app/llm/llm_clients.py`." Every other file imports `sonnet`, `haiku`, or
  `robust_sonnet` from there — unchanged pattern from `00-02`, just the provider
  swapped.
- **CLAUDE.md §4 rule 2**: not applicable — no new call sites, `ROUTING_TABLE`
  stays empty.
- **CLAUDE.md §4 rule 10**: Groq credentials come from `app.config.settings`,
  never hardcoded in `llm_clients.py`. Real `GROQ_API_KEY` value is never echoed
  back in chat/commits, consistent with how the Bedrock/LangSmith keys were
  handled.
- No free-text agent-to-agent handoffs — not applicable, no agents exist yet.

## Definition of Done
- [x] `app/llm/bedrock_clients.py` deleted; `app/llm/llm_clients.py` exists,
      exporting `sonnet`, `haiku`, `robust_sonnet`, all `ChatGroq`-backed
- [x] `app/config.py`, `.env.example`, local `.env`, `requirements.txt` updated
      per Files to Modify above
- [x] `tests/unit/test_llm_clients.py` updated and passing: no `ChatGroq(`
      outside `app/llm/llm_clients.py`, `get_model_for_task()` still raises
      `KeyError` for an unregistered task
- [x] `scripts/verify_langsmith_trace.py` imports from `app.llm.llm_clients`
- [x] `CLAUDE.md` and the blueprint updated (no stale Bedrock/Pinecone
      references in Phase 0's active scope)
- [ ] With a placeholder `GROQ_API_KEY`, `python -m scripts.verify_langsmith_trace`
      fails cleanly on a Groq auth error, not an import/config error
- [ ] ⚠️ **Requires a real Groq API key, not yet verified:** with a real
      `GROQ_API_KEY` in `.env`, `python -m scripts.verify_langsmith_trace`
      succeeds end-to-end and produces a visible trace in the
      `audience-match-dev` LangSmith project. **Status stays `In Progress` until
      this is confirmed** — this is also what finally unblocks
      `feature03-observability-bootstrap`'s own long-blocked DoD item.
- [x] No `CLAUDE.md` §4 or §9 rule violations (self-check)

## Out of Scope
- Any actual Chroma client code / vector-store implementation — that's
  `00-04-storage-bootstrap`, which now consumes the `chroma_persist_directory` /
  `embedding_model_name` config fields this feature scaffolds
- PostgreSQL, DynamoDB, S3, AWS ECS Fargate — unchanged, deferred per Scope above
- Re-litigating `00-02-llm-clients`'s merged history — that spec is left
  historically accurate with a superseded note, not rewritten
