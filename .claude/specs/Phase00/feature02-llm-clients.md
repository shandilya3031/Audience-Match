# Feature Spec — Phase 00.02: LLM Clients

## Status
`Complete` — **provider superseded, see note below.**

**LLM provider superseded (2026-09-01):** this feature's Bedrock implementation
was replaced by `06-llm-provider-pivot` — the project moved from AWS Bedrock to
Groq (free-tier hosted API, open-weight models) to eliminate paid/approval-gated
components now that this is a solo project (see the blueprint's "Architecture
Amendment — Open-Source/Zero-Cost Pivot" section). `app/llm/bedrock_clients.py`
no longer exists; it was renamed to `app/llm/llm_clients.py` and now instantiates
`ChatGroq`. The architectural *pattern* this feature established (single choke
point, `sonnet`/`haiku`/`robust_sonnet` exports, `ROUTING_TABLE` in
`model_router.py`) is unchanged and still accurately described below — only the
provider name/model IDs are stale. See `feature06-llm-provider-pivot.md` for the
current state.

## Parent Phase
Phase 00 — see `.claude/specs/Phase00/master.md`

## Overview
Establishes `app/llm/bedrock_clients.py` — the single place in the entire codebase
allowed to instantiate `ChatBedrock` — exposing `sonnet`, `haiku`, and `robust_sonnet`
(a Sonnet-with-fallback-to-Haiku-then-Llama chain), and `app/llm/model_router.py`
holding an (initially empty) `ROUTING_TABLE` plus a lookup helper that later phases
populate by task name. This is the concrete implementation of CLAUDE.md §4 rules 1–2
and blueprint §4.2: every future agent imports models from here rather than
instantiating `ChatBedrock` itself, which is what makes a global model swap or
fallback-policy change a one-file edit.

*(Historical — describes the original Bedrock implementation. See the superseded
note above.)*

## Depends On
`00-01-environment-config` — reads model IDs and AWS region from `app.config.settings`
rather than hardcoding them, so `Settings` (with `bedrock_sonnet_model_id`,
`bedrock_haiku_model_id`, `bedrock_fallback_model_id`, `aws_region`) must already
exist.

## Agent I/O Contract
No external contract — internal infrastructure, not an agent boundary. This feature
introduces:

```python
# app/llm/bedrock_clients.py
sonnet: ChatBedrock
haiku: ChatBedrock
robust_sonnet: Runnable  # sonnet.with_fallbacks([haiku, llama_fallback])

# app/llm/model_router.py
ROUTING_TABLE: dict[str, ChatBedrock | Runnable]  # starts empty

def get_model_for_task(task_name: str) -> ChatBedrock | Runnable:
    """Look up a model by task name; raise if the task isn't registered."""
```

## LLM Call Sites
None. This feature builds the routing *infrastructure* itself — no task-name entries
are registered in `ROUTING_TABLE` yet, since no agent call sites exist. The first real
entries get added starting Phase 1 (Segmenter).

## Data & Storage Changes
None.

## Guardrails Checklist
Not applicable — no user-facing endpoint or agent output is introduced by this
feature.

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
- `app/llm/__init__.py` — empty, makes `app.llm` a package
- `app/llm/bedrock_clients.py` — `sonnet`, `haiku`, `robust_sonnet`, all constructed
  from `app.config.settings` (model IDs, region), temperature 0 for `sonnet`/`haiku`
- `app/llm/model_router.py` — empty `ROUTING_TABLE` dict + `get_model_for_task()`
  helper that raises a clear `KeyError`/`ValueError` for an unregistered task name,
  so future call sites are structurally forced to register (operationalizes CLAUDE.md
  §4 rule 2 rather than leaving it as a convention)
- `tests/unit/test_llm_clients.py` — one test asserting `ChatBedrock(` does not appear
  anywhere under `app/` outside `app/llm/bedrock_clients.py` (a mechanical check for
  CLAUDE.md §4 rule 1), plus a test that `get_model_for_task("nonexistent")` raises

## Files to Modify
- `requirements.txt` — add `langchain-core`, `langchain-aws`, `boto3`

## New Dependencies
- `langchain-core` — `Runnable`, `.with_fallbacks()`
- `langchain-aws` — `ChatBedrock`
- `boto3` — AWS SDK, required transitively by `langchain-aws`'s Bedrock client

## Rules for Implementation
- **CLAUDE.md §4 rule 1** (the rule this feature exists to satisfy): "No raw
  `ChatBedrock(...)` instantiation outside `app/llm/bedrock_clients.py`." Every other
  file imports `sonnet`, `haiku`, or `robust_sonnet` from there.
- **CLAUDE.md §4 rule 2**: "No LLM call site without a declared model tier." This
  feature creates `ROUTING_TABLE` empty by design — later features/phases add entries
  by task name, never inline model selection in agent code.
- No free-text agent-to-agent handoffs — not applicable, no agents exist yet.
- Model IDs and AWS region come from `app.config.settings`, never hardcoded strings
  in `bedrock_clients.py` (keeps CLAUDE.md §4 rule 10 — no secrets/config in code —
  consistent even though model IDs aren't secrets, the pattern of "config comes from
  `app.config`" should hold uniformly).

## Definition of Done
- [x] `from app.llm.bedrock_clients import sonnet, haiku, robust_sonnet` succeeds
      with valid dummy `.env` values (no real AWS call required at import time)
- [x] `robust_sonnet` is `sonnet.with_fallbacks([haiku, llama_fallback])` (fallback
      chain: Sonnet → Haiku → Llama, matching blueprint §4.2)
- [x] No hardcoded model ID or region string in `bedrock_clients.py` — all sourced
      from `app.config.settings`
- [x] `app/llm/model_router.py` defines `ROUTING_TABLE = {}` and
      `get_model_for_task()` raises a clear error for an unregistered task name
- [x] `tests/unit/test_llm_clients.py` passes: no `ChatBedrock(` outside
      `app/llm/bedrock_clients.py`, and `get_model_for_task()` raises correctly
- [x] No `CLAUDE.md` §4 or §9 rule violations (self-check) — specifically rules 1
      and 2

## Out of Scope
- Populating `ROUTING_TABLE` with real task entries — starts Phase 1 (Segmenter)
- Verifying a real Bedrock call succeeds end-to-end and traces to LangSmith — that
  verification belongs to `00-03-observability-bootstrap`, which will make the one
  manual test call using `sonnet` or `haiku` from this feature
- Any actual AWS credentials/account setup — assumed to exist via `app.config`
  environment variables, provisioning itself is out of scope for Phase 0 per the
  master spec's credentials assumption
