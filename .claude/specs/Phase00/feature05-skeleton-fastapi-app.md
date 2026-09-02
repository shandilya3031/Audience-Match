# Feature Spec — Phase 00.05: Skeleton FastAPI App

## Status
`Complete`

## Parent Phase
Phase 00 — see `.claude/specs/Phase00/master.md`

## Overview
Stands up the deployable FastAPI skeleton: `app/main.py` as the entrypoint, a
`/health` endpoint, and an empty `/chat` endpoint that echoes input with no
LLM call. Per blueprint §4.5 and master spec §4.5, this proves the
deployment pipeline (app boots, routes respond) end-to-end **before** any
agent/AI logic exists, so later phases wire real behavior into an
already-working scaffold instead of debugging plumbing and agent logic at
the same time. This feature does **not** include Docker — `infra/docker/
Dockerfile` is a separate, not-yet-created scope item in the master spec
(needed for the phase's `docker build` Definition of Done gate, but tracked
as its own feature).

## Depends On
- `00-01-environment-config` — `app.config.settings` (not consumed directly by
  this feature yet, but `app/main.py` importing `app.config` is what proves
  config loads correctly at app startup)

## Agent I/O Contract
No external contract — no agent exists yet. This feature introduces the
`/chat` endpoint's request/response shape, which is intentionally already
Pydantic-validated (per CLAUDE.md §5's "structured, typed — never a bare
string" philosophy, applied one phase early since it's the exact shape later
phases will build on top of rather than change):

```python
# app/api/routes_chat.py
class ChatRequest(BaseModel):
    message: str
    client_id: str  # no isolation logic yet -- just establishing the field
                     # every later cache/session/guardrail rule depends on
                     # (CLAUDE.md §4 rules 6/7), so the request shape doesn't
                     # break when Phase 1+ wires real behavior behind it

class ChatResponse(BaseModel):
    message: str
```

## LLM Call Sites
None. `/chat` echoes `request.message` back verbatim — no model is invoked.

## Data & Storage Changes
None. No new `Settings` fields — `uvicorn app.main:app --reload` (per
CLAUDE.md §10) takes host/port as CLI flags, not app config.

## Guardrails Checklist
CLAUDE.md §6 technically applies to any new user-facing endpoint, but per the
master spec's own Out of Scope ("guardrails implementation beyond what's
structurally needed for `/chat` to exist (Phase 7)"), full guardrails don't
exist yet — `app/guardrails/` isn't created until Phase 7. This is a
deliberate, already-documented Phase 0 exception, not an oversight:

- [ ] Input filtering — N/A (`guardrails/input_filters.py` doesn't exist
      until Phase 7); `ChatRequest`'s Pydantic validation is the only
      current input check (type/presence, not content)
- [ ] SQL guard — N/A, no SQL involved
- [x] Output is validated Pydantic, not raw text — `ChatResponse`, from day
      one
- [ ] Citations/sources included for factual claims — N/A, no generation
- [ ] Similarity threshold check before generation — N/A, no retrieval
- [ ] Synchronous faithfulness/grounding check — N/A, no generation
- [ ] Adversarial test cases to add to `tests/e2e/` — N/A yet; revisit once
      `/chat` has real agent behavior behind it (Phase 1+)

## Golden Eval Cases to Add
No eval additions — non-agent-facing change.

## Files to Create
- `app/main.py` — FastAPI entrypoint; creates the `FastAPI` app, includes the
  health and chat routers
- `app/api/__init__.py` — empty, makes `app.api` a package
- `app/api/routes_health.py` — `GET /health` returning `{"status": "ok"}`,
  200. Shallow check only (no DB/Chroma connectivity probe) — deeper health
  checks are an observability concern, out of scope here (see Out of Scope)
- `app/api/routes_chat.py` — `POST /chat`, `ChatRequest`/`ChatResponse` per
  Agent I/O Contract above, handler returns `ChatResponse(message=request.message)`
- `tests/unit/test_api.py` — `fastapi.testclient.TestClient` tests for both
  routes (see Definition of Done)

## Files to Modify
- `requirements.txt` — add `fastapi`, `uvicorn[standard]` (note: `uvicorn`
  and `httpx` are already present transitively via `chromadb`'s own bundled
  server, but weren't explicit top-level dependencies; `fastapi` itself is
  not yet installed anywhere)

## New Dependencies
- `fastapi` — the web framework this entire feature stands up
- `uvicorn[standard]` — ASGI server; already present transitively but made
  an explicit dependency since CLAUDE.md §10's `uvicorn app.main:app --reload`
  command relies on it directly

## Rules for Implementation
- **CLAUDE.md §3**: "`app/api/` — FastAPI routes only — no business logic
  here." `routes_chat.py`/`routes_health.py` contain only request/response
  handling; there is no business logic to misplace yet since `/chat` is a
  pure echo.
- **CLAUDE.md §5 pattern** (agent I/O contracts are Pydantic, never bare
  strings) — applied to `/chat`'s request/response now even though no agent
  exists yet, so the shape doesn't have to change when one is wired in.
- No raw `ChatGroq(...)` outside `app/llm/llm_clients.py` — unaffected,
  restated as a standing rule; this feature makes no LLM calls at all.
- No free-text agent-to-agent handoffs — not applicable, no agents exist yet.

## Definition of Done
- [x] `uvicorn app.main:app` boots without error — verified by actually
      running it (`--port 8123`) and hitting both endpoints with `curl`,
      not just via `TestClient`
- [x] `GET /health` returns `200` with `{"status": "ok"}` — confirmed both
      via `TestClient` and a real running server
- [x] `POST /chat` with `{"message": "hi", "client_id": "test"}` returns
      `200` with `{"message": "hi"}` (exact echo) — confirmed both ways
- [x] `POST /chat` with a missing `message` or `client_id` field returns a
      `422` validation error (proves `ChatRequest` is actually enforced, not
      just declared)
- [x] `tests/unit/test_api.py` passes, using `TestClient` (no running server
      process required) — 4/4 new tests, 12/12 total in `tests/unit`
- [x] No `CLAUDE.md` §4 or §9 rule violations (self-check)

## Out of Scope
- `infra/docker/Dockerfile`, `docker build` — separate master-spec scope
  item ("Docker & dependencies"), not this feature
- `routes_upload.py` (blueprint's planned upload endpoint) — no phase needs
  file upload yet; introduced whenever Phase 1 (Segmenter CSV) or Phase 2
  (RAG documents) actually needs it
- Real `/chat` behavior (routing to agents, Supervisor wiring) — Phase 4+
  once the Supervisor and worker agents exist, per CLAUDE.md §2 build order
- Deep health checks (DB/Chroma/Groq connectivity probes) — an observability
  concern; revisit in Phase 9 (LLM Observability) or Phase 13 (Deployment) if
  actually needed, not assumed now
- Guardrails (input filtering, PII, injection detection) — Phase 7, per the
  master spec's own Out of Scope for this phase
- Auth / rate limiting / CORS — not mentioned anywhere in Phase 0 scope;
  deferred to whichever later phase actually needs it
