# CLAUDE.md

Guidance for Claude Code (and any AI coding agent) working in this repository. Read this before making changes. When this file and a specific request conflict, ask — don't silently pick one.

Companion doc: `Audience_Match_Implementation_Blueprint.md` — the full phase-by-phase plan. This file is the condensed, enforceable ruleset derived from it. If a decision here seems to contradict the blueprint, the blueprint is the source of truth; flag the discrepancy rather than resolving it silently.

---

## 1. What This Project Is

Audience Match is a multi-agent marketing intelligence platform: one **Supervisor Agent** (LangGraph) orchestrating four independent worker agents:

- **Segmenter** — clusters customers from historical CSV data, LLM names/describes segments
- **RAG (Knowledge Base)** — answers questions from company documents via retrieval
- **Aggregator** — converts natural language to SQL against PostgreSQL marketing data
- **Campaign Briefing** — synthesizes all other agents' conversation history into a campaign roadmap

Stack: Python, LangChain + LangGraph, FastAPI, Chroma (local vector store), PostgreSQL, DynamoDB, S3, Groq (hosted free-tier inference — open-weight models), Docker, AWS ECS Fargate, GitHub Actions, LangSmith, RAGAS. See the blueprint's "Architecture Amendment — Open-Source/Zero-Cost Pivot" for why Bedrock/Pinecone were replaced.

---

## 2. The One Rule That Shapes Everything Else

**Build order is not negotiable: Segmenter → RAG → Aggregator (each independently eval-passing) → Supervisor → Campaign Briefing.**

Do not write Supervisor/LangGraph orchestration code that depends on an agent that hasn't passed its own golden-dataset evaluation yet. Do not build Campaign Briefing logic against mocked agent outputs when real agents already exist — use real outputs. If asked to work on the Supervisor before the three worker agents it depends on exist and pass eval, say so and ask whether to proceed anyway.

---

## 3. Repository Structure — Where Things Go

```
app/
  api/                  FastAPI routes only — no business logic here
  supervisor/           LangGraph graph, state, router, synthesizer
  agents/<name>/         Each agent is self-contained and independently importable
    schemas.py           Pydantic I/O contracts — the ONLY way agents talk to each other
  memory/                DynamoDB history, summarization, session key logic
  guardrails/             Input/output validation, SQL guard, PII
  caching/                Exact/semantic/embedding cache layers
  observability/          LangSmith setup, cost tracking
  llm/                    llm_clients.py, model_router.py — the ONLY place ChatGroq is instantiated
eval/
  golden_datasets/        One file per agent, JSONL, shared schema (see §7)
  run_*_eval.py           CI-gating scripts
tests/
  unit/ integration/ e2e/
infra/
  docker/ terraform/ github_actions/
scripts/                 One-off and scheduled jobs (schema extraction, cache warming)
```

**Hard rule:** every module under `app/agents/<agent>/` must import and run standalone — no reaching into `app/supervisor/` from an agent. Agents don't know the Supervisor exists.

---

## 4. Non-Negotiable Engineering Rules

These are enforced, not suggested. If a change would violate one, stop and flag it rather than proceeding.

1. **No raw `ChatGroq(...)` instantiation outside `app/llm/llm_clients.py`.** Every other file imports `sonnet`, `haiku`, or `robust_sonnet` from there. This is what makes model swaps and fallback policy a one-file change.

2. **No LLM call site without a declared model tier.** Add new call sites to `ROUTING_TABLE` in `app/llm/model_router.py` by task name (e.g. `"filter_extraction": haiku`). Don't inline model selection in agent code.

3. **No free-text agent-to-agent handoffs.** Every agent's output is a Pydantic model (see each agent's `schemas.py`). If the Supervisor needs a new field from an agent, add it to the schema — don't parse free text.

4. **No SQL reaches PostgreSQL without passing `sql_guard.validate_sql()`.** This runs in-process before execution, in addition to (never instead of) the DB-level read-only role. Both layers must exist; neither is sufficient alone.

5. **No LLM-generated SQL statement type other than SELECT, ever.** Not even in test fixtures that "won't actually run." The guard code and its test suite are the same code path used in production.

6. **No cache key without `client_id`.** Exact cache, semantic cache, and any future cache layer must include client_id in the key. A cache hit across clients is a data leak, not a bug.

7. **No conversation memory shared across modules.** Session keys follow `{user_id}_{module}_{session_id}` exactly (see `app/memory/session_keys.py`). Never let the Aggregator's history bleed into the RAG agent's context or vice versa.

8. **No summarization without entity verification.** Any code path that compresses conversation history must extract critical entities pre-summary and verify they appear post-summary (see `app/memory/summarizer.py`). Never summarize the last 10 exchanges — those stay verbatim.

9. **No agent or prompt change ships without its eval passing.** `eval/run_*_eval.py` scripts are CI gates, not optional local scripts. If you're touching a prompt template or retrieval logic in `app/agents/rag/` or `app/agents/aggregator/`, the corresponding eval script must be run and pass before the change is considered complete.

10. **No secrets in code, ever.** Config comes from environment variables via `app/config.py`. If you find yourself typing an API key, an AWS credential, or a DB password into a file, stop.

---

## 5. Agent Contract Pattern

Every agent exposes exactly this shape. Follow it for any new agent or when modifying an existing one.

```python
# app/agents/<name>/schemas.py
class <Name>AgentInput(BaseModel):
    query: str
    client_id: str
    # + agent-specific fields (e.g. cluster_filter for RAG)

class <Name>AgentOutput(BaseModel):
    # structured, typed — never a bare string
    ...
```

```python
# invocation pattern used everywhere
result: <Name>AgentOutput = await agent.ainvoke(<Name>AgentInput(...))
```

When adding a new field to an agent's output that the Supervisor or Campaign Briefing needs, add it to the Pydantic schema first, regenerate/update any dependent code, then implement. Schema-first, not implementation-first.

---

## 6. Guardrail Checklist — Apply to Any New Agent or Endpoint

Before considering a new agent, tool, or user-facing endpoint complete, verify:

- [ ] Input passes through `guardrails/input_filters.py` (length, injection pattern, PII flag)
- [ ] Any SQL touches `sql_guard.validate_sql()` before execution
- [ ] Output is a validated Pydantic model, not raw LLM text
- [ ] Output includes citations/sources if it makes factual claims from retrieved context
- [ ] Retrieval-based agents check similarity threshold (< 0.75 → "insufficient information", do not generate)
- [ ] Faithfulness/grounding check runs before returning to user (sync, Haiku-based) for anything RAG-adjacent
- [ ] Adversarial test cases added to the relevant suite in `tests/e2e/` (prompt injection, SQL injection as applicable)

If you're unsure whether a change needs a new guardrail, default to adding one and flag it for review rather than skipping it.

---

## 7. Evaluation — How to Add or Extend

Golden dataset format is shared across agents for tooling reuse:

```json
{
  "id": "rag_042",
  "query": "...",
  "expected_answer_contains": ["..."],
  "expected_sources": ["..."],
  "category": "...",
  "difficulty": "simple|medium|complex",
  "module": "rag|aggregator|segmenter|campaign_briefing|supervisor"
}
```

When adding new functionality to an agent:
1. Add 3-5 new golden cases covering the new behavior to the relevant `eval/golden_datasets/*.jsonl`
2. Run the corresponding `eval/run_*_eval.py` and confirm it passes
3. Only then consider the feature complete

Minimum thresholds that gate CI (do not lower these without explicit sign-off):

| Metric | Threshold |
|---|---|
| RAG faithfulness | ≥ 0.85 |
| RAG context precision | ≥ 0.75 |
| Aggregator SQL accuracy | ≥ 85% |
| Supervisor routing accuracy | ≥ 90% |
| Adversarial guardrail block rate | 100% |
| Segmenter cluster stability (ARI across reseeded runs) | ≥ 0.75 |

---

## 8. Common Task Playbooks

**"Add a new query type the Supervisor should route somewhere new"**
1. Add golden examples to `eval/golden_datasets/supervisor_routing_eval.jsonl` with expected `required_agents`
2. Update `IntentClassification` enum/logic in `app/supervisor/router.py`
3. Update `graph.py` conditional edges if a new node path is needed
4. Run routing eval, confirm ≥90% still holds

**"Change a prompt template"**
1. Identify which agent's `*_chain.py` owns it
2. Make the change
3. Run that agent's eval script locally
4. If faithfulness/accuracy drops below threshold, do not proceed — iterate on the prompt, not the threshold
5. Bump `prompt_version` in the tag/metadata if this is a production agent (needed for Prompt Registry rollback later)

**"Add a new data source to an agent"**
1. Update ingestion pipeline (chunking/embedding/schema-extraction as applicable)
2. Update the agent's retrieval filter logic if new metadata fields are introduced
3. Add golden cases exercising the new source
4. Verify namespace/table isolation — don't let new data bleed into unrelated clients or clusters

**"Debug a hallucination report"**
1. Pull the LangSmith trace by request ID — check `agent` and `prompt_version` tags
2. Check retrieved context in the trace — was retrieval precision the problem, or generation?
3. Reproduce with the same query against the golden dataset harness, not ad hoc
4. Fix at the layer where it actually originated (retrieval threshold, prompt grounding rules, or output validation) — don't paper over a retrieval bug with a stricter generation prompt

**"Add caching to a new call path"**
1. Confirm the cache key includes `client_id`
2. Pick TTL based on data volatility (see blueprint §14.2 table — embeddings 7d, SQL results 1h, etc.)
3. Confirm cache invalidation hook exists if the underlying data can change (tag-based purge)

---

## 9. What NOT to Do

- Don't build the Supervisor's orchestration logic against agents that haven't passed their own eval yet
- Don't let an agent call another agent directly — all cross-agent coordination goes through the Supervisor
- Don't pass LangChain memory *objects* between modules — Campaign Briefing reads serialized DynamoDB history, not live memory instances from other agents
- Don't hardcode table/column names anywhere outside the Aggregator's schema retrieval path — it must always go through the semantic schema index, even if there are currently only a handful of tables
- Don't silently widen a Pydantic schema's validation (e.g., removing a `Field(ge=0, le=100)` constraint) to make a failing test pass — that's usually masking a real upstream bug
- Don't add a new LLM call without adding it to the cost/observability tagging convention (`agent`, `prompt_version` metadata)
- Don't treat eval script failures as "flaky" without investigating — golden datasets are small and deterministic by design; a failure usually means a real regression

---

## 10. Local Dev Commands

```bash
# Setup
pip install -r requirements.txt
cp .env.example .env   # fill in Bedrock/Pinecone/DB creds

# Run locally
uvicorn app.main:app --reload

# Tests
pytest tests/unit                          # fast, no external deps
pytest tests/integration                   # needs staging Pinecone/PostgreSQL/DynamoDB
pytest tests/e2e                           # needs full staging stack

# Eval (run before considering an agent change complete)
python eval/run_ragas_eval.py --agent rag --gate
python eval/run_sql_eval.py --gate
python eval/run_agentic_eval.py --gate     # supervisor routing accuracy

# Lint / format / security
black .
flake8 .
bandit -r app/
```

---

## 11. When In Doubt

- **Architecture question not covered here** → check `Audience_Match_Implementation_Blueprint.md`, the relevant phase section
- **Threshold seems wrong for the current stage of the project** → flag it, don't silently change it
- **A request conflicts with build order (§2) or the non-negotiable rules (§4)** → say so explicitly before proceeding
- **Unsure whether something needs an eval case or a guardrail** → add it; asking forgiveness on over-testing is cheaper than a silent regression