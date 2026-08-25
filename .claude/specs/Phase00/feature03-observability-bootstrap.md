# Feature Spec — Phase 00.03: Observability Bootstrap

## Status
`Not Started`

## Parent Phase
Phase 00 — see `.claude/specs/Phase00/master.md`

## Overview
Wires LangSmith tracing before any agent code exists, per blueprint §4.3 and
blueprint §1 principle 5 ("observability is a day-1 dependency, not a day-90
feature"). The env-var plumbing (`LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`,
`LANGCHAIN_PROJECT`) already exists in `app/config.py` from feature `00-01`; this
feature adds the one-off verification call that proves the wiring actually works —
a single `haiku.invoke(...)` call that must show up as a trace in the
`audience-match-dev` LangSmith project. This is what the master spec's Definition of
Done item "a manual LangSmith trace appears for a test LLM call" refers to.

## Depends On
- `00-01-environment-config` — supplies `settings.langchain_tracing_v2`,
  `settings.langchain_api_key`, `settings.langchain_project`
- `00-02-llm-clients` — supplies `haiku` (the client this feature's verification
  call uses)

## Agent I/O Contract
No external contract — internal infra, not an agent boundary. Introduces one script
entry point:

```python
# scripts/verify_langsmith_trace.py
def main() -> None:
    """Invoke haiku once and print the result, to be manually confirmed as a
    trace in the LangSmith project named by settings.langchain_project."""
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
  `app.llm.bedrock_clients`, makes one `.invoke()` call with a fixed test prompt
  (e.g. `"Say 'observability check' and nothing else."`), prints the response. This
  is the first real content in `scripts/` (blueprint §3 describes it as holding
  "one-off and scheduled jobs" — this qualifies).

## Files to Modify
None. LangSmith env vars are already defined in `app/config.py` and `.env.example`
from feature `00-01`.

## New Dependencies
- `langsmith` — explicit dependency on the tracing SDK, rather than relying on it
  being pulled in transitively by `langchain-core`

## Rules for Implementation
- **CLAUDE.md §4 rule 1**: the verification script must import `haiku` from
  `app.llm.bedrock_clients` — it must not instantiate any `ChatBedrock` itself.
- **CLAUDE.md §4 rule 2**: does not apply here — this is the same manual-verification
  exception already established in feature `00-02`'s spec (no `ROUTING_TABLE` entry
  for a one-off check call).
- **CLAUDE.md §4 rule 10**: LangSmith credentials come from `app.config.settings`,
  never hardcoded in the script.
- No free-text agent-to-agent handoffs — not applicable, no agents exist yet.

## Definition of Done
- [ ] `scripts/verify_langsmith_trace.py` exists, imports `haiku` from
      `app.llm.bedrock_clients`, and makes exactly one `.invoke()` call
- [ ] `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, and `LANGCHAIN_PROJECT` are read
      via `app.config.settings` inside the script's execution path (i.e. by virtue
      of importing `app.llm.bedrock_clients`, which imports `app.config`) — no
      hardcoded values
- [ ] ⚠️ **Requires real credentials, cannot be verified by the assistant in this
      environment:** running the script against real AWS Bedrock and LangSmith
      credentials produces a visible trace in the `audience-match-dev` LangSmith
      project. Per the master spec's stated assumption (no cloud credentials
      confirmed available), this item is completed by the user running the script
      themselves once credentials are in `.env`, and confirming the trace appears —
      it is logged here as a deferred follow-up rather than silently dropped, per
      the master spec's Definition of Done gate
- [ ] No `CLAUDE.md` §4 or §9 rule violations (self-check)

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
