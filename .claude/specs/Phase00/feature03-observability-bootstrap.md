# Feature Spec — Phase 00.03: Observability Bootstrap

## Status
`Complete`

## Parent Phase
Phase 00 — see `.claude/specs/Phase00/master.md`

## Overview
Wires LangSmith tracing before any agent code exists, per blueprint §4.3 and
blueprint §1 principle 5 ("observability is a day-1 dependency, not a day-90
feature"). The env-var plumbing (`LANGSMITH_TRACING`, `LANGSMITH_API_KEY`,
`LANGSMITH_PROJECT` — renamed from the initial `LANGCHAIN_*` names to match current
LangSmith conventions, per the installed `langsmith-trace` skill; see the "Env var
correction" note below) already exists in `app/config.py` from feature `00-01`; this
feature adds the one-off verification call that proves the wiring actually works —
a single `haiku.invoke(...)` call that must show up as a trace in the
`audience-match-dev` LangSmith project. This is what the master spec's Definition of
Done item "a manual LangSmith trace appears for a test LLM call" refers to.

**Env var correction (post-installation of the `langsmith-trace` skill):** the
skill's guidance for LangChain/LangGraph apps is `LANGSMITH_TRACING` /
`LANGSMITH_API_KEY` / `LANGSMITH_PROJECT`, not the legacy `LANGCHAIN_TRACING_V2` /
`LANGCHAIN_API_KEY` / `LANGCHAIN_PROJECT` names originally used. `app/config.py` was
updated accordingly (fields renamed, plus a new optional `langsmith_workspace_id`).
This also surfaced a real gap: `pydantic-settings` reading `.env` into the `Settings`
object does **not** populate `os.environ`, but LangChain's tracer reads
`os.environ` directly — so `app/config.py` now explicitly does
`os.environ.setdefault(...)` for each LangSmith var after constructing `settings`,
using `setdefault` so a real env var (e.g. set by a container) is never overridden.

## Depends On
- `00-01-environment-config` — supplies `settings.langsmith_tracing`,
  `settings.langsmith_api_key`, `settings.langsmith_project`
- `00-02-llm-clients` (superseded by `00-06-llm-provider-pivot`) — supplies
  `haiku` (the client this feature's verification call uses), now from
  `app/llm/llm_clients.py` (Groq-backed) rather than the original
  `bedrock_clients.py`

## Agent I/O Contract
No external contract — internal infra, not an agent boundary. Introduces one script
entry point:

```python
# scripts/verify_langsmith_trace.py
def main() -> None:
    """Invoke haiku once and print the result, to be manually confirmed as a
    trace in the LangSmith project named by settings.langsmith_project."""
```

## LLM Call Sites
None registered in `ROUTING_TABLE`. This feature's single LLM call (in
`scripts/verify_langsmith_trace.py`) is a one-off manual verification invocation, not
a production call site — consistent with how feature `00-02`'s spec already carved
out this same exception. No task name is registered for it.

## Data & Storage Changes
None.

## Guardrails Checklist
Not applicable — this is a local verification script, not a user-facing endpoint or
agent output.

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
- `scripts/verify_langsmith_trace.py` — imports `haiku` from
  `app.llm.llm_clients` (updated by `00-06-llm-provider-pivot`; originally
  `app.llm.bedrock_clients`), makes one `.invoke()` call with a fixed test prompt
  (e.g. `"Say 'observability check' and nothing else."`), prints the response. This
  is the first real content in `scripts/` (blueprint §3 describes it as holding
  "one-off and scheduled jobs" — this qualifies).

## Files to Modify
- `app/config.py` — renamed `langchain_tracing_v2`/`langchain_api_key`/
  `langchain_project` to `langsmith_tracing`/`langsmith_api_key`/
  `langsmith_project`, added optional `langsmith_workspace_id`, and added explicit
  `os.environ.setdefault(...)` calls so LangChain's tracer (which reads the process
  environment, not the Settings object) actually sees these values
- `.env.example` and local `.env` — updated to the renamed `LANGSMITH_*` var names

## New Dependencies
- `langsmith` — explicit dependency on the tracing SDK, rather than relying on it
  being pulled in transitively by `langchain-core`

## Rules for Implementation
- **CLAUDE.md §4 rule 1**: the verification script must import `haiku` from
  `app.llm.llm_clients` — it must not instantiate any `ChatGroq` itself.
- **CLAUDE.md §4 rule 2**: does not apply here — this is the same manual-verification
  exception already established in feature `00-02`'s spec (no `ROUTING_TABLE` entry
  for a one-off check call).
- **CLAUDE.md §4 rule 10**: LangSmith credentials come from `app.config.settings`,
  never hardcoded in the script.
- No free-text agent-to-agent handoffs — not applicable, no agents exist yet.

## Definition of Done
- [x] `scripts/verify_langsmith_trace.py` exists, imports `haiku` from
      `app.llm.bedrock_clients`, and makes exactly one `.invoke()` call
- [x] `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, and `LANGSMITH_PROJECT` are read via
      `app.config.settings` and explicitly exported to `os.environ` (see "Env var
      correction" in Overview) — no hardcoded values
- [x] Running the script with placeholder `.env` values fails with a clean
      `botocore.exceptions.NoCredentialsError`, not an import or config error —
      confirms Bedrock wiring is correct up to the credentials boundary (verified
      in a clean venv: `python -m scripts.verify_langsmith_trace`)
- [x] LangSmith tracing is confirmed *actively firing*, not just configured: the
      same run also produced `langsmith.utils.LangSmithError: ... 403 Client Error:
      Forbidden for url: https://api.smith.langchain.com/runs/multipart` — proof the
      LangSmith client attempted to post a real trace and was rejected only because
      the placeholder API key is invalid, not because tracing was inert
- [x] **LangSmith side confirmed with real credentials (interim evidence, not the
      DoD item itself):** with real `LANGSMITH_API_KEY`/`LANGSMITH_PROJECT` in
      `.env`, a standalone throwaway script (not committed — lives outside the repo,
      uses OpenAI's `gpt-4o-mini` via `@traceable`/`wrap_openai` since Bedrock
      credentials weren't available, per the langsmith-trace skill's
      "trace_other_frameworks" pattern) produced a trace named `test_call` visible
      in the LangSmith UI under project `audience-match-dev`, with correct
      `LANGSMITH_PROJECT`/`LANGSMITH_TRACING` metadata and output "Observability
      check." — user-confirmed via screenshot. This proves the LangSmith ingestion
      path (API key, project routing, tracing activation) is genuinely correct end
      to end. It does **not** exercise Bedrock, so it does not satisfy the item
      below.
- [x] **Confirmed with real Groq credentials (via `00-06-llm-provider-pivot`):**
      `python -m scripts.verify_langsmith_trace` (using `haiku` from
      `app.llm.llm_clients`, Groq-backed) succeeded against a real `GROQ_API_KEY`
      and produced a visible trace in the `audience-match-dev` LangSmith
      project — confirmed via `Client().list_runs(...)`: run `ChatGroq success`,
      2026-09-01 10:49:53 UTC. This is the item the master spec's Definition of
      Done actually refers to.
- [x] No `CLAUDE.md` §4 or §9 rule violations (self-check)

## Out of Scope
- Structured `agent` / `prompt_version` LangSmith tag conventions — that's Phase 9
  (LLM Observability), which enforces those tags from each agent's first commit;
  no agents exist yet in Phase 0
- `app/observability/langsmith_setup.py` / `cost_tracker.py` module content — per
  the Phase 0 master spec's target scaffold, `app/observability/` is not created
  until Phase 9
- Cost tracking, alerting thresholds, dashboards — Phase 9/10
- Any real AWS or LangSmith account/project provisioning — assumed to be the user's
  own existing accounts; this feature only wires config and verifies connectivity
