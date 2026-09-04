# Feature Spec — Phase 01.01: Preprocessing Pipeline

## Status
`Not Started`

## Parent Phase
Phase 01 — see `.claude/specs/Phase01/master.md`

## Overview
This feature builds the deterministic, non-LLM data-preparation pipeline
that turns a raw customer CSV into a cleaned, scaled/encoded feature
matrix ready for clustering, plus a `feature_lineage.json` recording which
real customer attributes each matrix column corresponds to and which
columns were dropped along the way — needed by later stages (the
clustering pipeline in 01.02, and the LLM naming chain in 01.03) so
naming stays grounded in real column names. It is the first stage of the
Segmenter agent's pipeline (blueprint §5.1) and has no dependency on any
other Phase 1 feature — it is the natural leaf to start from.

**Note (2026-09-04):** the blueprint originally specified a PCA
dimensionality-reduction step as the last stage of this pipeline. Per the
blueprint's 2026-09-04 amendment to §5.1, PCA has been dropped — expected
customer CSVs don't have enough columns to justify it, and skipping it
keeps every feature the clustering algorithms see directly traceable to a
real column (or one-hot-encoded category) instead of an abstract
component. This spec reflects that amendment; there is no PCA step or
`n_components`/`explained_variance` concept anywhere below.

## Depends On
None — this is the first feature of Phase 1, with no internal dependency
on other Phase 1 features. It depends only on Phase 0 infrastructure
(`app.config`, `app.storage.local_files`), both already complete.

## Agent I/O Contract
No external contract — internal to the `segmenter` agent. This feature
does not cross an agent boundary (`SegmenterAgentInput`/`Output` is
feature 01.05); it introduces internal module functions and one internal
(non-agent-boundary) data structure:

```python
# app/agents/segmenter/preprocessing.py

@dataclass
class PreprocessingResult:
    feature_matrix: np.ndarray        # scaled/encoded, correlation-pruned -- clustering input,
                                       # shape (n_rows, len(feature_names))
    cleaned_df: pd.DataFrame          # post-cleaning, pre-encoding DataFrame (numeric + categorical
                                       # columns retained, rows with removed outliers dropped) --
                                       # used downstream by the naming chain (01.03) to compute real
                                       # aggregate stats (avg_income, dominant_age_group, etc.) per cluster
    feature_names: list[str]          # names of feature_matrix's columns, in order (e.g. "income",
                                       # "region_onehot_West") -- since no PCA is applied, matrix
                                       # columns already map directly to real (or one-hot-expanded)
                                       # customer attributes; this is what feature_lineage.json records
    dropped_columns: list[str]        # columns dropped for >85% missingness or |corr| > 0.9

def preprocess(csv_path: str | Path, client_id: str) -> PreprocessingResult:
    """Full pipeline entrypoint: raw CSV -> PreprocessingResult. Also writes
    feature_lineage.json to the client's segmenter artifact directory as a
    side effect (see Data & Storage Changes)."""

# Internal steps, each independently unit-testable:
def identify_column_types(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Returns (numeric_columns, categorical_columns)."""

def drop_high_missing_columns(df: pd.DataFrame, threshold: float = 0.85) -> tuple[pd.DataFrame, list[str]]:
    """Returns (df_with_columns_dropped, dropped_column_names)."""

def remove_outliers_iqr(df: pd.DataFrame, numeric_columns: list[str]) -> pd.DataFrame:
    """Drops rows where any numeric column falls outside [Q1 - 1.5*IQR, Q3 + 1.5*IQR]."""

def scale_and_encode(
    df: pd.DataFrame, numeric_columns: list[str], categorical_columns: list[str]
) -> tuple[np.ndarray, list[str]]:
    """StandardScaler on numeric_columns + OneHotEncoder on categorical_columns,
    concatenated. Returns (encoded_matrix, output_feature_names) where
    output_feature_names maps each matrix column back to its origin
    (e.g. "income" or "region_onehot_West")."""

def drop_correlated_features(
    matrix: np.ndarray, feature_names: list[str], threshold: float = 0.9
) -> tuple[np.ndarray, list[str], list[str]]:
    """Returns (reduced_matrix, kept_feature_names, dropped_feature_names).
    On each correlated pair (|corr| > threshold), drops the second column
    encountered (deterministic, order-based) to keep behavior reproducible.
    This is the final step of the pipeline -- its output becomes
    PreprocessingResult.feature_matrix / feature_names directly (no PCA
    step follows, per the blueprint's 2026-09-04 amendment)."""
```

## LLM Call Sites
None. This feature is pure pandas/scikit-learn/numpy — no LLM involvement
(blueprint §5.1 has no LLM step; the naming chain that uses this feature's
output is 01.03).

## Data & Storage Changes
- **PostgreSQL:** None — this feature doesn't read or write PostgreSQL.
- **Chroma:** None.
- **DynamoDB:** N/A (folded into PostgreSQL per blueprint amendment); not touched.
- **S3 / local filesystem:**
  - **Reads:** raw CSV via `app.storage.local_files.raw_customer_data_path(filename)`
    (existing Phase 0 helper, `data/raw_customer_data/`) — no changes to
    that module.
  - **Writes (new):** `feature_lineage.json` per client, written by
    `preprocess()` as a side effect. This needs a new storage location not
    yet in `app.storage.local_files` — add:
    ```python
    # app/storage/local_files.py -- new function
    def segmenter_artifact_path(client_id: str, filename: str) -> Path:
        directory = Path(settings.segmenter_artifacts_dir) / client_id
        directory.mkdir(parents=True, exist_ok=True)
        return directory / filename
    ```
    and a new `app.config.Settings` field:
    ```python
    segmenter_artifacts_dir: str = "./data/segmenter_artifacts"
    ```
    `feature_lineage.json` is written to
    `segmenter_artifact_path(client_id, "feature_lineage.json")` — a JSON
    object with `feature_names` (list, matching `feature_matrix`'s column
    order) and `dropped_columns` (list).

## Guardrails Checklist
- [ ] Input filtering — **not applicable here.** `guardrails/input_filters.py`
      (length/injection/PII on a user `query` string) applies to
      `SegmenterAgentInput.query` (feature 01.05), not to CSV file
      ingestion. No text-based prompt-injection surface exists in this
      feature.
- [ ] SQL guard — not applicable (Aggregator-only).
- [ ] Output is validated Pydantic, not raw text — **not applicable in the
      cross-agent sense** (no agent boundary crossed here); `PreprocessingResult`
      is an internal `@dataclass`, not a Pydantic model, which is
      consistent with CLAUDE.md §5 (Pydantic is required at agent I/O
      boundaries, not for every internal data structure).
- [ ] Citations/sources for factual claims — not applicable (no
      generated/retrieved content here).
- [ ] Similarity threshold check — not applicable (RAG-only).
- [ ] Synchronous faithfulness/grounding check — not applicable (RAG-adjacent
      only); however, `cleaned_df` is exactly what feature 01.03's naming
      chain will use to ground its `ClusterSummary` claims in real
      aggregate values, so correctness here is a precondition for that
      phase's grounding guarantee.
- [ ] Adversarial test cases — add one `tests/unit/test_segmenter_preprocessing.py`
      case feeding a CSV with an adversarial/malformed column (e.g. a
      column that is 100% missing, or contains non-numeric junk in a
      column that looks numeric) and asserting `preprocess()` degrades
      gracefully (drops the column / raises a clear, typed error) rather
      than crashing uninformatively or silently corrupting the matrix.

## Golden Eval Cases to Add
No eval additions — this feature is non-agent-facing preprocessing
infrastructure with no LLM call and no clustering decision of its own; its
correctness is verified via deterministic unit tests (see Definition of
Done below), not RAGAS/ARI-style golden cases. The `segmenter_eval.jsonl`
golden dataset (blueprint §5.6, master spec §Evaluation Requirements)
exercises this pipeline indirectly, end-to-end, once feature 01.02
(Clustering Pipeline) wires it into the full agent flow — golden cases
belong to that feature, not this one.

## Files to Create
- `app/agents/segmenter/__init__.py` — empty, makes `segmenter` an importable package
- `app/agents/segmenter/preprocessing.py` — the pipeline described above
- `tests/unit/test_segmenter_preprocessing.py` — unit tests for every
  function in `preprocessing.py`, including the adversarial case above

## Files to Modify
- `app/config.py` — add `segmenter_artifacts_dir: str = "./data/segmenter_artifacts"` field
- `app/storage/local_files.py` — add `segmenter_artifact_path(client_id, filename)` helper
- `requirements.txt` — add `pandas`, `scikit-learn`, `numpy` (see New Dependencies)

## New Dependencies
- `pandas` — DataFrame handling, IQR outlier removal, correlation matrix
- `scikit-learn` — `StandardScaler`, `OneHotEncoder`
- `numpy` — array operations (also a transitive dependency of the above,
  pinned explicitly since `preprocessing.py` imports it directly)

## Rules for Implementation
From CLAUDE.md §4, relevant to this feature:
- **Rule 1** (no raw `ChatGroq(...)` outside `app/llm/llm_clients.py`) —
  N/A, this feature makes no LLM calls, but any future call site added
  here must still go through that file.
- **Rule 2** (no LLM call site without a declared `ROUTING_TABLE` tier) —
  N/A for the same reason.
- **Rule 3** (no free-text agent-to-agent handoffs) — N/A, no agent
  boundary is crossed by this feature; internal functions may use plain
  dataclasses per CLAUDE.md §5's scoping of Pydantic to agent I/O.
- **Rule 9** (no agent/prompt change ships without its eval passing) —
  this feature has no eval script of its own (see Golden Eval Cases
  above); its unit tests are the applicable gate instead.
- **Rule 10** (no secrets in code) — N/A, no secrets involved.
- CLAUDE.md §9: don't silently widen a Pydantic schema's validation to
  make a failing test pass — N/A here (no Pydantic model in this
  feature), but the equivalent discipline applies to the `threshold=0.9`
  correlation cutoff and `threshold=0.85` missingness cutoff: if a test
  fails because real data doesn't behave as expected at these values, do
  not silently loosen them to make the test pass — surface it.
- Repository structure (CLAUDE.md §3): this module lives under
  `app/agents/segmenter/` and must import and run standalone — no
  reaching into `app/supervisor/` (trivially true here; no such import
  exists in this feature).

## Definition of Done
- [ ] `identify_column_types` correctly splits a mixed-type test
      DataFrame into numeric vs. categorical column lists
- [ ] `drop_high_missing_columns` drops exactly the columns with >85%
      missing values on a constructed test DataFrame and returns their
      names
- [ ] `remove_outliers_iqr` removes rows with values outside the IQR
      fences on a constructed test DataFrame with known outliers, and
      leaves in-range rows untouched
- [ ] `scale_and_encode` produces a matrix with correctly standardized
      numeric columns (mean ≈0, std ≈1) and correctly one-hot-encoded
      categorical columns, with `output_feature_names` matching the
      matrix's column order exactly
- [ ] `drop_correlated_features` removes one column from every pair with
      `|corr| > 0.9` on a constructed test matrix with a known correlated
      pair, deterministically (same input → same output across repeated
      runs), and its output `feature_names` length matches the reduced
      matrix's column count exactly
- [ ] `preprocess()` run end-to-end on a synthetic test CSV (with at
      least one >85%-missing column, one pair of correlated numeric
      columns, and injected outliers) produces a `PreprocessingResult`
      whose `feature_matrix` has no NaNs/infs and whose `feature_names`
      traces every remaining column back to a real input column (numeric
      as-is, categorical as its one-hot-encoded form), and writes a valid
      `feature_lineage.json` to `segmenter_artifact_path(client_id,
      "feature_lineage.json")` that round-trips (JSON-decodes back to the
      same `feature_names`/`dropped_columns` data)
- [ ] Adversarial case (malformed/all-missing column) handled gracefully
      per the Guardrails Checklist item above
- [ ] Unit tests in `tests/unit/test_segmenter_preprocessing.py` added
      and passing (`pytest tests/unit/test_segmenter_preprocessing.py`)
- [ ] No CLAUDE.md §4 or §9 rule violations (self-check before marking complete)

## Out of Scope
- Clustering itself (KMeans/Agglomerative/DBSCAN/HDBSCAN, stability ARI
  check) — feature 01.02
- The LLM naming chain and `ClusterSummary` schema — feature 01.03
- Dual persistence to PostgreSQL `cluster_profiles` / Chroma — feature 01.04
- `SegmenterAgentInput`/`Output` and the public agent entrypoint — feature 01.05
- Golden dataset construction and `eval/run_segmenter_eval.py` — the
  evaluation-harness feature within this phase (not yet numbered)
- Any guardrail beyond the minimal adversarial-input unit test above —
  full guardrail consolidation is Phase 7
