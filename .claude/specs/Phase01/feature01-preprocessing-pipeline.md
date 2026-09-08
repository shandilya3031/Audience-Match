# Feature Spec — Phase 01.01: Preprocessing Pipeline

## Status
`Complete`

## Parent Phase
Phase 01 — see `.claude/specs/Phase01/master.md`

## Overview
This feature builds the deterministic, non-LLM data-preparation pipeline
that turns a raw customer CSV into a cleaned, scaled/encoded feature
matrix ready for clustering, plus a `feature_lineage.json` recording which
real customer attributes each matrix column corresponds to, and *why*
every dropped column was dropped — needed by later stages (the
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

**Amendment (2026-09-08) — smart feature selection redesign:** manual
testing against a real dataset (Kaggle's "Sample Superstore" CSV, 9,994
rows, 21 columns) found the first implementation of this feature broke in
two ways: (1) `pd.read_csv` had no encoding fallback and failed
immediately on the file's Windows-1252/Latin-1 encoding; (2) high-
cardinality, ID-like categorical columns (`Order ID`: 5,009 unique,
`Product ID`/`Name`: ~1,850 each, `Customer ID`/`Name`: 793 each,
`Order Date`/`Ship Date`: ~1,300 each, `City`: 531) one-hot encoded into a
**12,178-column** matrix, and `drop_correlated_features`'s pairwise
`pandas.DataFrame.corr()` call never finished in 4.5+ minutes at that
width. This amendment adds two new pipeline steps
(`drop_identifier_like_columns`, `drop_near_constant_columns`) that
statistically detect and exclude non-informative columns *before*
encoding — no column-name matching, so it generalizes across arbitrary,
unknown client schemas — plus a `read_customer_csv` encoding fallback and
a `numpy`-vectorized reimplementation of `drop_correlated_features` for
defense-in-depth at scale. Verified against the real dataset post-fix:
0.11s (down from never finishing), 84 output columns (down from 12,178),
with `Row ID`/`Order ID`/`Customer ID`/`Customer Name`/`Product ID`/
`Product Name`/`Order Date`/`Ship Date`/`City` correctly excluded as
`identifier_like` and `Country` as `near_constant`. This is a contract
change (`PreprocessingResult.dropped_columns` goes from `list[str]` to
`dict[str, str]`, column name → drop reason) made before this feature
ever shipped — no downstream code depends on the old shape.

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
    feature_matrix: np.ndarray        # scaled/encoded, feature-selected + correlation-pruned --
                                       # clustering input, shape (n_rows, len(feature_names))
    cleaned_df: pd.DataFrame          # post-cleaning, pre-encoding DataFrame (numeric + categorical
                                       # columns retained, rows with removed outliers/NaNs dropped) --
                                       # used downstream by the naming chain (01.03) to compute real
                                       # aggregate stats (avg_income, dominant_age_group, etc.) per cluster
    feature_names: list[str]          # names of feature_matrix's columns, in order (e.g. "income",
                                       # "region_onehot_West") -- since no PCA is applied, matrix
                                       # columns already map directly to real (or one-hot-expanded)
                                       # customer attributes; this is what feature_lineage.json records
    dropped_columns: dict[str, str]   # column_name -> reason: "high_missing" | "identifier_like" |
                                       # "near_constant" | "high_correlation"

def read_customer_csv(csv_path: str | Path) -> pd.DataFrame:
    """Reads a raw client CSV. Tries UTF-8 first (pandas default); falls
    back to latin-1 (which never raises a decode error) on
    UnicodeDecodeError -- the standard safe fallback for legacy/Excel-
    exported CSVs using Windows-1252/Latin-1 encoding."""

def preprocess(
    csv_path: str | Path,
    client_id: str,
    missing_threshold: float = 0.85,
    identifier_cardinality_ratio: float = 0.5,
    max_categorical_cardinality: int = 50,
    min_rows_for_identifier_check: int = 30,
    near_constant_std_threshold: float = 1e-8,
    correlation_threshold: float = 0.9,
) -> PreprocessingResult:
    """Full pipeline entrypoint: raw CSV -> PreprocessingResult. Also
    writes feature_lineage.json to the client's segmenter artifact
    directory as a side effect. Thresholds are keyword-configurable so
    different clients' data can be tuned without code changes."""

# Internal steps, each independently unit-testable:
def identify_column_types(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Returns (numeric_columns, categorical_columns)."""

def drop_high_missing_columns(df: pd.DataFrame, threshold: float = 0.85) -> tuple[pd.DataFrame, list[str]]:
    """Returns (df_with_columns_dropped, dropped_column_names)."""

def drop_identifier_like_columns(
    df: pd.DataFrame,
    numeric_columns: list[str],
    categorical_columns: list[str],
    identifier_cardinality_ratio: float = 0.5,
    max_categorical_cardinality: int = 50,
    min_rows_for_identifier_check: int = 30,
) -> tuple[pd.DataFrame, list[str], list[str], list[str]]:
    """Returns (df, kept_numeric_columns, kept_categorical_columns,
    dropped_column_names). Drops columns that behave like row identifiers
    rather than clustering features, using purely statistical signals --
    no column-name matching, so this generalizes across arbitrary client
    schemas ("for different clients, different kind of data will come").

    Categorical columns are dropped if nunique/n_rows > identifier_cardinality_ratio
    (default 0.5) OR nunique > max_categorical_cardinality (default 50) --
    the absolute cap is what catches columns like customer/product IDs or
    free-text names, whose ratio is well under 0.5 but whose raw
    cardinality is still far too high to one-hot encode sensibly.

    Numeric columns use a much stricter rule: only a fully-unique,
    integer-valued column (every row distinct, no NaNs -- no gapless
    requirement, since an ID with gaps from deleted rows is still an ID)
    is dropped as an identifier. Genuine continuous features (income,
    sales) are *expected* to have high cardinality, so high cardinality
    alone must never exclude a numeric column.

    No-ops entirely below min_rows_for_identifier_check rows (default 30):
    on small samples, a genuine feature can accidentally look fully
    unique by chance, so cardinality-based pruning isn't statistically
    meaningful there -- and a small dataset can't produce the one-hot
    blowup this guards against anyway.

    Known limitation: a numeric column that is semantically categorical
    but not unique per row (e.g. a postal/ZIP code) is NOT caught by any
    rule here or elsewhere -- there is no generic statistical signal that
    safely distinguishes it from a genuine bounded-range continuous
    feature without domain knowledge. Documented and accepted, not hacked
    around with a fragile heuristic."""

def drop_near_constant_columns(
    df: pd.DataFrame,
    numeric_columns: list[str],
    categorical_columns: list[str],
    near_constant_std_threshold: float = 1e-8,
) -> tuple[pd.DataFrame, list[str], list[str], list[str]]:
    """Returns (df, kept_numeric_columns, kept_categorical_columns,
    dropped_column_names). Drops columns with (near-)zero variance -- no
    signal for clustering distance regardless of dataset size, so unlike
    drop_identifier_like_columns this applies at any row count."""

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
    step follows, per the blueprint's 2026-09-04 amendment).

    Uses vectorized numpy.corrcoef rather than pandas' pairwise .corr() --
    numerically equivalent on NaN-free data (matrix is guaranteed NaN-free
    by this point) but scales to far more columns; pandas' NaN-safe
    pairwise Cython loop doesn't scale past a few thousand columns. This
    is defense-in-depth even after drop_identifier_like_columns /
    drop_near_constant_columns shrink the space, in case a client's data
    still has a few hundred legitimate categorical columns. Guards
    n <= 1 explicitly: np.corrcoef returns a 0-d scalar (not a 2D array)
    for a single column, a failure mode pandas.DataFrame.corr() didn't
    have."""
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
  - **Reads:** raw CSV via `read_customer_csv` (this feature's own helper,
    with the UTF-8 → latin-1 fallback described above) — sourced from
    `data/raw_customer_data/` via the existing Phase 0
    `app.storage.local_files.raw_customer_data_path(filename)` helper, no
    changes to that module.
  - **Writes:** `feature_lineage.json` per client, written by
    `preprocess()` as a side effect to
    `segmenter_artifact_path(client_id, "feature_lineage.json")`
    (existing Phase 0 helper, no changes needed) — a JSON object with
    `feature_names` (list, matching `feature_matrix`'s column order) and
    `dropped_columns` (**object**, column name → reason string):
    ```json
    {
      "feature_names": ["income", "region_onehot_West"],
      "dropped_columns": {
        "order_id": "identifier_like",
        "notes": "high_missing",
        "country": "near_constant",
        "income_copy": "high_correlation"
      }
    }
    ```

## Guardrails Checklist
- [ ] Input filtering — **not applicable here.** `guardrails/input_filters.py`
      (length/injection/PII on a user `query` string) applies to
      `SegmenterAgentInput.query` (feature 01.05), not to CSV file
      ingestion. No text-based prompt-injection surface exists in this
      feature. Worth noting as a side benefit (not a designed guardrail):
      `drop_identifier_like_columns` tends to exclude PII-heavy columns
      (customer names, IDs) automatically, since they're statistically
      high-cardinality — full PII handling remains Phase 7 scope.
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
- [x] Adversarial test cases — `tests/unit/test_segmenter_preprocessing.py`
      covers: a CSV with a 100%-missing column and a numeric-looking
      column containing non-numeric junk (`preprocess()` degrades
      gracefully, no crash); and a synthetic high-cardinality
      reproduction of the real-world failure mode (Row-ID-style perfect
      sequence, order-id-style unique-per-row categorical column) proving
      `feature_matrix` stays bounded instead of exploding.

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
  function in `preprocessing.py`, including the adversarial and
  high-cardinality cases above

## Files to Modify
- `app/config.py` — add `segmenter_artifacts_dir: str = "./data/segmenter_artifacts"` field
- `app/storage/local_files.py` — add `segmenter_artifact_path(client_id, filename)` helper
- `requirements.txt` — add `pandas`, `scikit-learn`, `numpy` (see New Dependencies)

## New Dependencies
- `pandas` — DataFrame handling, IQR outlier removal, cardinality/variance checks
- `scikit-learn` — `StandardScaler`, `OneHotEncoder`
- `numpy` — array operations, and the vectorized `corrcoef` used in
  `drop_correlated_features`

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
  feature), but the equivalent discipline applies to every threshold in
  this feature (`missing_threshold`, `identifier_cardinality_ratio`,
  `max_categorical_cardinality`, `min_rows_for_identifier_check`,
  `near_constant_std_threshold`, `correlation_threshold`): if a test
  fails because real data doesn't behave as expected at these values, do
  not silently loosen them to make the test pass — surface it. This
  applies with extra force to `min_rows_for_identifier_check`, which
  exists specifically to prevent false positives on small datasets —
  lowering it to make an unrelated test pass would reintroduce that risk.
- Repository structure (CLAUDE.md §3): this module lives under
  `app/agents/segmenter/` and must import and run standalone — no
  reaching into `app/supervisor/` (trivially true here; no such import
  exists in this feature).

## Definition of Done
- [x] `identify_column_types` correctly splits a mixed-type test
      DataFrame into numeric vs. categorical column lists
- [x] `drop_high_missing_columns` drops exactly the columns with >85%
      missing values on a constructed test DataFrame and returns their
      names
- [x] `drop_identifier_like_columns` drops near-unique categoricals (by
      ratio), high-absolute-cardinality categoricals (by the cap alone,
      isolated from the ratio condition), and fully-unique integer
      numeric sequences (with and without gaps); correctly **keeps** a
      high-cardinality but non-integer continuous numeric column
      (proving no false positive on genuine continuous features); and
      no-ops entirely below `min_rows_for_identifier_check` rows
- [x] `drop_near_constant_columns` drops zero-variance numeric columns
      and single-value categorical columns; keeps normal-variance columns
      of both types
- [x] `remove_outliers_iqr` removes rows with values outside the IQR
      fences on a constructed test DataFrame with known outliers, and
      leaves in-range rows untouched
- [x] `scale_and_encode` produces a matrix with correctly standardized
      numeric columns (mean ≈0, std ≈1) and correctly one-hot-encoded
      categorical columns, with `output_feature_names` matching the
      matrix's column order exactly
- [x] `drop_correlated_features` removes one column from every pair with
      `|corr| > 0.9` on a constructed test matrix with a known correlated
      pair, deterministically (same input → same output across repeated
      runs); handles the single-feature-matrix edge case (`n <= 1`)
      without crashing, a new failure mode introduced by the
      `numpy.corrcoef` reimplementation
- [x] `read_customer_csv` falls back to `latin-1` and reads successfully
      on a CSV that would fail UTF-8 decoding
- [x] `preprocess()` run end-to-end on a synthetic test CSV (with a
      >85%-missing column, a correlated numeric pair, injected outliers)
      produces a `PreprocessingResult` whose `feature_matrix` has no
      NaNs/infs, whose `feature_names` traces every remaining column back
      to a real input column, and whose `dropped_columns` dict correctly
      tags each drop reason; writes a valid `feature_lineage.json` that
      round-trips with the new dict-shaped `dropped_columns`
- [x] Adversarial case (malformed/all-missing column) handled gracefully
      per the Guardrails Checklist item above
- [x] **Real-world verification**: run against the actual Kaggle "Sample
      Superstore" CSV (9,994 rows, 21 columns, Windows-1252 encoded) that
      broke the first implementation — confirmed 0.11s runtime (down from
      never finishing in 4.5+ minutes), 84 output feature columns (down
      from 12,178), and every expected high-cardinality/near-constant
      column correctly excluded with the right reason
      (`Row ID`/`Order ID`/`Customer ID`/`Customer Name`/`Product ID`/
      `Product Name`/`Order Date`/`Ship Date`/`City` → `identifier_like`;
      `Country` → `near_constant`)
- [x] Unit tests in `tests/unit/test_segmenter_preprocessing.py` added
      and passing (`pytest tests/unit/test_segmenter_preprocessing.py`)
- [x] No CLAUDE.md §4 or §9 rule violations (self-check before marking complete)

## Known Limitations
- **Numeric ID-like-but-not-fully-unique columns** (e.g. postal/ZIP
  codes): not caught by `drop_identifier_like_columns` or any other rule
  in this feature. There's no generic statistical signal that safely
  distinguishes a semantically-categorical numeric code from a genuine
  bounded-range continuous feature without domain knowledge. Such columns
  survive as numeric, go through `StandardScaler`, and are also subject
  to `remove_outliers_iqr`'s fence-based row removal — meaning legitimate
  rows could be dropped if their code's raw numeric value falls outside
  the IQR fence (e.g. very low vs. very high ZIP codes). Documented and
  accepted; not hacked around with a fragile heuristic. Revisit if a real
  client dataset makes this a practical problem.

## Out of Scope
- Clustering itself (KMeans/Agglomerative/DBSCAN/HDBSCAN, stability ARI
  check) — feature 01.02
- The LLM naming chain and `ClusterSummary` schema — feature 01.03
- Dual persistence to PostgreSQL `cluster_profiles` / Chroma — feature 01.04
- `SegmenterAgentInput`/`Output` and the public agent entrypoint — feature 01.05
- Golden dataset construction and `eval/run_segmenter_eval.py` — the
  evaluation-harness feature within this phase (not yet numbered)
- Any guardrail beyond the minimal adversarial-input unit tests above —
  full guardrail consolidation is Phase 7
- More sophisticated unsupervised feature-importance scoring (e.g.
  Laplacian score, mutual-information-based ranking) — the statistical
  heuristics in this feature (identifier detection, near-constant
  removal, correlation redundancy) are the scoped-in mechanism for now;
  a documented future enhancement, not needed to satisfy this feature's
  Definition of Done
