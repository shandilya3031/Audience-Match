# Master Spec — Phase 1: Segmenter Agent

## Status
`Not Started`

## Overview
Phase 1 builds the Segmenter Agent: a standalone pipeline that clusters
customers from historical CSV data and uses an LLM to name/describe each
resulting segment with structured, grounded output. Per CLAUDE.md §2 and
blueprint §5's build order rationale, Segmenter is built first among the
four worker agents because it has no dependency on any other agent and
produces the cluster data that both the RAG agent (Phase 2, indirectly,
via later Campaign Briefing context) and the Campaign Briefing agent
(Phase 5) will eventually consume — building it first means downstream
phases get real cluster data to test against instead of mocks.

## Position in Build Order
- **Depends on (must be complete):** Phase 0 (Foundations) — needs
  `app.config`, `app.llm.llm_clients` / `model_router`, the provisioned
  `cluster_profiles` PostgreSQL table + `app_readonly` role, and the
  provisioned `cluster_profiles` Chroma collection, all of which Phase 0
  created. Phase 0 is `Gate Met` (`.claude/specs/Phase00/master.md`),
  DoD fully checked off.
- **Blocks (cannot start until this is done):**
  - Phase 2 (RAG) — per CLAUDE.md §2's strict sequential build order
    (Segmenter → RAG → Aggregator), even though RAG has no direct data
    dependency on Segmenter's output.
  - Phase 4 (Supervisor) — its `dispatch_node` calls the Segmenter agent
    directly via `SegmenterAgentInput`/`Output` (blueprint §8.4); cannot be
    wired against a schema that doesn't exist and pass eval yet.
  - Phase 5 (Campaign Briefing) — its context builder reads real Segmenter
    conversation history and references real `cluster_id`s (blueprint §9.1,
    §9.2); needs Phase 1's real output, not mocks, per CLAUDE.md §2.

## Scope
- **Preprocessing pipeline** (`app/agents/segmenter/preprocessing.py`) —
  raw CSV → pandas DataFrame → numeric/categorical split → drop >85%
  missing columns → IQR outlier removal → `StandardScaler` /
  `OneHotEncoder` → correlation-based feature drop (|corr| > 0.9) →
  `feature_lineage.json` recording final feature-matrix column names
  and any dropped columns (blueprint §5.1; PCA step dropped per
  blueprint's 2026-09-04 amendment — expected column counts don't
  justify dimensionality reduction, so clustering operates on real,
  directly-interpretable features throughout)
- **Clustering pipeline** (`app/agents/segmenter/clustering.py`) —
  multi-algorithm candidate run (KMeans, Agglomerative/ward, DBSCAN,
  HDBSCAN), best-model selection by silhouette + Davies-Bouldin (tie-break
  on stability), minimum 4 unique clusters to qualify, 5-reseed stability
  check via Adjusted Rand Index with a documented warning path when
  ARI < 0.75 (blueprint §5.2)
- **LLM naming chain** (`app/agents/segmenter/naming_chain.py`) —
  structured-output `ClusterSummary` (cluster_id, cluster_name,
  segment_size_pct, exactly 5 summary_points, dominant_age_group,
  top_channels, spending_level) grounded in real aggregate statistics +
  `feature_lineage.json`, via `sonnet.with_structured_output` routed
  through `ROUTING_TABLE["cluster_naming"]` (blueprint §5.3, CLAUDE.md §4
  rule 2)
- **Dual persistence** — structured metrics to PostgreSQL `cluster_profiles`
  table, embedded `summary_points` to the Chroma `cluster_profiles`
  collection with `{cluster_id, type}` metadata (blueprint §5.4)
- **Agent interface / schemas.py** (`app/agents/segmenter/schemas.py`) —
  `SegmenterAgentInput` / `SegmenterAgentOutput` per CLAUDE.md §5's agent
  contract pattern (blueprint §5.5)
- **Evaluation harness** — `eval/golden_datasets/segmenter_eval.jsonl`
  (15–20 hand-labeled synthetic clustering runs with known ground-truth
  segment count/boundaries) and `eval/run_segmenter_eval.py` computing ARI
  against ground truth + the stability ARI check, plus a 100%-spot-check
  naming-quality checklist (blueprint §5.6)

## Out of Scope
- Any Supervisor wiring or LangGraph node calling this agent (Phase 4) —
  this phase only builds the agent so it is independently
  `ainvoke`-able per CLAUDE.md §5's invocation pattern
- RAG, Aggregator, and Campaign Briefing agent logic (Phases 2, 3, 5)
- Cross-session memory / DynamoDB-style history persistence for Segmenter
  conversations beyond what a single `SegmenterAgentInput`/`Output` call
  needs — full memory architecture is Phase 6
- Guardrail hardening beyond the basic input-length/PII/injection filter
  already scoped generically in CLAUDE.md §6 — adversarial suite
  consolidation is Phase 7
- Caching of naming-chain or preprocessing results — Phase 10
- CI wiring of `eval/run_segmenter_eval.py` as a blocking GitHub Actions
  gate — that automation is Phase 12; this phase only requires the script
  to exist and pass when run locally/manually (CLAUDE.md §4 rule 9, §7)
- Nightly/scheduled re-clustering jobs — not called for anywhere in
  blueprint §5; only on-demand clustering via the agent interface is in
  scope

## Agent / Module Contracts Touched
- **`segmenter`** — **new agent**. Needs the full `AgentInput`/`AgentOutput`
  pair per CLAUDE.md §5:
  - `SegmenterAgentInput(query: str, client_id: str)`
  - `SegmenterAgentOutput(answer: str, referenced_clusters: List[int], confidence: Literal["high","medium","low"])`
  - Internal (not cross-agent, but still schema-first per CLAUDE.md §5):
    `ClusterSummary` — structured LLM naming-chain output, with
    `segment_size_pct: float = Field(ge=0, le=100)` and
    `summary_points: List[str] = Field(min_items=5, max_items=5)`
    constraints preserved exactly as specified (CLAUDE.md §9: never
    silently widen these to make a test pass)

## Data & Storage Touched
- **Chroma:** uses the `cluster_profiles` collection already provisioned
  in Phase 0 (`app/vectorstore/chroma_client.py`, feature `00-04`) — no
  new collection needed. Embeds `summary_points` text with metadata
  `{cluster_id, type}`.
- **PostgreSQL:** `cluster_profiles` table already exists (`infra/db/schema.sql`)
  but currently only has `cluster_id, client_id, cluster_name, description,
  summary_points, member_count, created_at` — it does **not** yet have
  columns for the structured metrics blueprint §5.4 calls for (e.g.
  `avg_income`, `avg_spend`, `dominant_age_group`, `top_channels`,
  `spending_level`, `segment_size_pct`). A migration adding these columns
  is in scope for a feature spec in this phase. No `app_readonly` grant
  change is needed — `ALTER DEFAULT PRIVILEGES ... GRANT SELECT` in
  `infra/db/schema.sql` already covers new/altered tables in `public`.
- **DynamoDB:** N/A (folded into PostgreSQL per blueprint amendment).
- **S3:** raw CSVs read from `data/raw_customer_data/` (local filesystem,
  folded in from S3 per blueprint amendment) via `app/storage/local_files.py`
  (Phase 0) — no new storage location needed.

## LLM Usage in This Phase

| Task | Model tier | Notes |
|---|---|---|
| `cluster_naming` | `robust_sonnet` | Structured `ClusterSummary` output; matches blueprint §14.1's `ROUTING_TABLE` entry exactly — register in `app/llm/model_router.py` |

No other LLM call sites in this phase — preprocessing and clustering are
pure pandas/scikit-learn, no LLM involved.

## Guardrails Required
From CLAUDE.md §6 checklist, applicable to this phase:
- [ ] Input passes through `guardrails/input_filters.py` (length, injection
      pattern, PII flag) — applies to the `query` field of
      `SegmenterAgentInput`
- [ ] Output is a validated Pydantic model, not raw LLM text — enforced via
      `sonnet.with_structured_output(ClusterSummary)`
- [ ] Output includes citations/sources if it makes factual claims from
      retrieved context — N/A in the RAG-citation sense (no retrieval
      here), but naming-chain claims must trace to real aggregate stats
      passed in the prompt (this phase's equivalent of grounding, verified
      by the 100%-spot-check naming-quality review in §5.6)
- Not applicable this phase: SQL guard (Aggregator-only), retrieval
  similarity threshold (RAG-only), faithfulness/grounding sync check
  (RAG-adjacent only — Segmenter's grounding check is the manual
  naming-quality review instead, per blueprint §5.6)
- Adversarial test cases: defer full adversarial suite to Phase 7, but a
  minimal prompt-injection-in-`query` test belongs in this phase's own
  `tests/e2e/` per the general CLAUDE.md §6 guidance to default to adding
  a guardrail/test when unsure

## Evaluation Requirements
- Golden dataset: `eval/golden_datasets/segmenter_eval.jsonl` — 15–20
  hand-labeled clustering runs on synthetic datasets with known
  ground-truth segment count and rough boundaries (blueprint §5.6, §12.1)
- Metrics and gating thresholds (CLAUDE.md §7 table):
  - Segmenter cluster stability (ARI across reseeded runs) **≥ 0.75**
  - Ground-truth ARI on golden dataset (no CLAUDE.md §7 numeric floor
    given beyond stability; blueprint §5's Definition of Done requires
    "reliably produces ≥4 stable clusters" — treat ≥4 valid clusters per
    golden case as a pass/fail gate alongside the ARI stability number)
  - Naming quality: zero fabricated statistics in 100% manual review of
    golden-dataset naming outputs (blueprint §5 DoD)

## Observability Requirements
- LangSmith tags on the naming-chain call: `agent: "segmenter"`,
  `prompt_version`, per blueprint §13.1's tagging convention (enforced
  from this agent's first commit, per CLAUDE.md §9)
- No new cost-tracking/alerting infra in this phase — `cost_tracker.py`
  wiring is Phase 9; this phase just needs to emit the tags Phase 9 will
  later consume

## Feature Specs Index
_Populated automatically by `/create-feature-spec` as features are created.
Do not edit manually._

| # | Feature | Spec file | Status |
|---|---|---|---|
| 01 | Preprocessing Pipeline | feature01-preprocessing-pipeline.md | Not Started |

## Definition of Done (Phase Gate)
Per blueprint §5 / §21 ("1 — Segmenter: ARI stability ≥0.75, zero
fabricated stats in naming review"):

- [ ] All features in Scope above have specs and are implemented
- [ ] Given a test CSV, pipeline reliably produces ≥4 stable clusters
- [ ] Clustering stability ARI ≥ 0.75 across 5 reseeded runs
- [ ] Names are grounded in real aggregate values — zero fabricated numbers
      in 100% manual review of golden dataset naming outputs
- [ ] Data lands correctly in both PostgreSQL (`cluster_profiles` table,
      including the new structured-metrics columns) and Chroma
      (`cluster_profiles` collection)
- [ ] `eval/run_segmenter_eval.py` passes locally (ARI-vs-ground-truth +
      stability check) — CI gating of this script is out of scope for this
      phase (Phase 12) but a passing local run is required before this
      phase is considered done, per CLAUDE.md §4 rule 9
- [ ] No unresolved items in Risk Register (blueprint §22) attributable to
      this phase (the "Clustering instability across runs undermines
      trust" row — mitigated by the mandatory stability check being
      non-optional, not deferred)
