# Feature Spec — Phase 01.02: Clustering Pipeline

## Status
`Complete`

## Parent Phase
Phase 01 — see `.claude/specs/Phase01/master.md`

## Overview
This feature builds the clustering stage of the Segmenter agent
(blueprint §5.2): given the feature matrix produced by feature 01.01's
`preprocess()`, it runs two candidate clustering algorithms (KMeans,
Agglomerative/ward), each internally searched over a small hyperparameter
grid since no target cluster count is known ahead of time, selects the
best-scoring candidate by silhouette/Davies-Bouldin, and runs a 5-run
bootstrap stability check (Adjusted Rand Index) on the winner before
returning a result. This is the second stage of the Segmenter pipeline
and the direct input to feature 01.03's LLM naming chain (which needs
final cluster labels) and feature 01.04's persistence (which needs
per-cluster membership).

**Amendment (2026-09-08) — dropped DBSCAN/HDBSCAN:** manual testing
against the real Kaggle "Sample Superstore" dataset (7,143 rows, 84
columns after feature 01.01's preprocessing) found a structural bias in
the original four-algorithm design: DBSCAN and HDBSCAN score themselves
(silhouette, Davies-Bouldin) only on non-noise points, while KMeans/
Agglomerative must classify every row (no reject option). This lets a
density-based algorithm "win" the silhouette comparison purely by
discarding hard-to-cluster rows as noise and scoring well on the easier
remainder — not a fair comparison for a segmentation use case where every
customer should land in an actionable cluster. Verified on the real
dataset: HDBSCAN (the original winner) produced 3 clusters at
silhouette=0.2482 but labeled **72.9% of rows (5,207/7,143) as noise**;
DBSCAN produced 3 clusters at silhouette=0.1885 (lower — scored against a
larger, harder subset) and still labeled **41.2% (2,945/7,143) as
noise**. Neither achieves the actual objective of maximum-coverage
segmentation, and keeping DBSCAN alone doesn't fix the underlying bias,
only shrinks its effect. Decision: drop both DBSCAN and HDBSCAN, keep
only KMeans and Agglomerative/ward, which structurally guarantee 100% row
coverage (confirmed: both always produce exactly `k` non-empty clusters
for any `k <= n`; ward linkage is a tree-cut, unconditionally guaranteed,
while KMeans can collapse below `k` on degenerate/duplicate data — a
separate, already-handled case via `_score_candidate`'s recount-from-
actual-labels logic). This is a deliberate deviation from the blueprint's
original four-algorithm `candidates` dict — see the blueprint's own
matching 2026-09-08 amendment to §5.2.

**Interpretation note:** the blueprint's inline code comment for
`select_best` says "tie-broken by stability," but its following paragraph
describes the stability check as validating only "the winning algorithm"
after selection. This spec follows the paragraph (the more detailed,
authoritative elaboration): selection is by silhouette first, with
Davies-Bouldin breaking near-ties (see `select_best_candidate` below),
and stability is computed once, after selection, for the winner only —
not as a per-candidate selection criterion. Running the 5x bootstrap
stability check for every candidate in the hyperparameter grid would be
expensive for no clearly-specified benefit.

**Design note on combining silhouette and Davies-Bouldin:** both indices
measure compactness-vs-separation and are correlated (not independent
signals) — they don't fully diversify against each other's blind spots.
Silhouette is the primary criterion since it is the finer-grained
(point-wise) measure. Davies-Bouldin's role is scoped to breaking
near-ties within `silhouette_tie_epsilon` (default `0.02`) of the best
silhouette score — not a strict lexicographic secondary sort key (which
would make it fire only on an effectively-impossible exact float tie),
and not a full combined/weighted score (which would let a much worse
silhouette outrank a genuinely better-separated candidate). This is a
deliberate middle ground: Davies-Bouldin gets real influence exactly when
silhouette alone can't confidently distinguish the top candidates. (An
earlier version of this note also warned that both indices could
systematically favor KMeans/Agglomerative's cluster shape over DBSCAN/
HDBSCAN's — moot now that this feature only ever compares those two
algorithms against each other, per the amendment above.)

## Depends On
Feature 01.01 (Preprocessing Pipeline) — `Complete`. This feature consumes
`PreprocessingResult.feature_matrix` as its `X` input; it does not read
CSVs or call `preprocess()` itself.

## Agent I/O Contract
No external contract — internal to the `segmenter` agent. This feature
does not cross an agent boundary (`SegmenterAgentInput`/`Output` is
feature 01.05); it introduces internal module functions and data
structures:

```python
# app/agents/segmenter/clustering.py

class ClusteringError(Exception):
    """Raised when no candidate algorithm achieves >=3 valid clusters --
    there is nothing sensible to return."""

@dataclass
class ClusteringCandidate:
    algorithm: str                 # "kmeans" | "agglomerative"
    params: dict                   # hyperparameters used, e.g. {"n_clusters": 6}
    labels: np.ndarray             # cluster assignment per row
    n_clusters: int                # unique cluster count
    silhouette: float
    davies_bouldin: float

@dataclass
class ClusteringResult:
    labels: np.ndarray             # winning algorithm's final per-row cluster assignment
    algorithm: str
    params: dict
    n_clusters: int
    silhouette: float
    davies_bouldin: float
    stability_ari_scores: list[float]  # pairwise ARI across the 5-run bootstrap check
    is_stable: bool                    # mean(stability_ari_scores) >= stability_ari_threshold
    all_candidates: list[ClusteringCandidate]  # every algorithm family's best
                                                # result (that reached >=3 clusters) --
                                                # up to 2 entries (kmeans, agglomerative)

def run_kmeans_candidates(
    X: np.ndarray, k_range: range = range(3, 11), random_state: int = 42
) -> ClusteringCandidate | None:
    """Fits KMeans(n_clusters=k, n_init=10, random_state=random_state) for
    each k in k_range, scores each by silhouette, returns the
    best-scoring k's candidate. None if no k in k_range is viable (e.g.
    every k >= len(X)) -- see the empty-all_candidates guard in
    cluster()."""

def run_agglomerative_candidates(
    X: np.ndarray, k_range: range = range(3, 11)
) -> ClusteringCandidate | None:
    """Fits AgglomerativeClustering(n_clusters=k, linkage="ward") for each
    k in k_range, scores by silhouette, returns the best-scoring k's
    candidate. Deterministic -- ward linkage has no random_state."""

def select_best_candidate(
    candidates: list[ClusteringCandidate], silhouette_tie_epsilon: float = 0.02
) -> ClusteringCandidate:
    """Selects primarily by silhouette (higher is better). Among all
    candidates whose silhouette is within silhouette_tie_epsilon of the
    single best silhouette score (a near-tie window, not an exact-equality
    check -- exact float ties are effectively impossible in practice),
    the one with the lowest davies_bouldin wins. If exactly one candidate
    has the best silhouette and no other candidate falls within the
    epsilon window, davies_bouldin plays no role and that candidate wins
    outright. Deterministic given fixed candidates/epsilon (ties within
    the near-tied group on davies_bouldin itself resolve by candidates'
    input list order). See the Overview interpretation note: stability is
    NOT a selection criterion here."""

def check_stability(
    X: np.ndarray,
    algorithm: str,
    params: dict,
    n_runs: int = 5,
    sample_frac: float = 0.9,
    ari_threshold: float = 0.75,
) -> tuple[list[float], bool]:
    """Refits the given algorithm+params on n_runs random sample_frac
    subsamples of X (seeds 0..n_runs-1), then computes pairwise Adjusted
    Rand Index between every pair of runs, restricted to the row indices
    common to both (their random subsamples overlap substantially at
    sample_frac=0.9). Returns (pairwise_ari_scores, is_stable) where
    is_stable = mean(pairwise_ari_scores) >= ari_threshold. Uniform across
    both algorithm families -- bootstrap subsampling works consistently
    whether or not the algorithm exposes a random_state, rather than
    branching per algorithm."""

def cluster(
    X: np.ndarray,
    k_range: range = range(3, 11),
    silhouette_tie_epsilon: float = 0.02,
    stability_ari_threshold: float = 0.75,
) -> ClusteringResult:
    """Main entrypoint. Runs both run_*_candidates functions, collects
    every non-None result into all_candidates, raises ClusteringError if
    all_candidates is empty (neither algorithm family reached >=3
    clusters), otherwise selects the best via select_best_candidate
    (passing through silhouette_tie_epsilon), runs check_stability on it,
    and returns the assembled ClusteringResult."""
```

## LLM Call Sites
None. This feature is pure scikit-learn/numpy — no LLM involvement
(blueprint §5.2 has no LLM step; the naming chain that consumes this
feature's output is 01.03).

## Data & Storage Changes
None. This feature is pure in-memory computation — it takes a feature
matrix (from feature 01.01) and returns cluster labels/metrics; it reads
no files and writes nothing to PostgreSQL/Chroma. Persistence is feature
01.04's scope.

## Guardrails Checklist
- [ ] Input filtering — not applicable (no user-facing text input; `X` is
      a numeric feature matrix produced by feature 01.01).
- [ ] SQL guard — not applicable (Aggregator-only).
- [ ] Output is validated Pydantic, not raw text — not applicable in the
      cross-agent sense (no agent boundary crossed here);
      `ClusteringCandidate`/`ClusteringResult` are internal `@dataclass`es,
      consistent with CLAUDE.md §5 (Pydantic required at agent I/O
      boundaries only).
- [ ] Citations/sources for factual claims — not applicable (no
      generated/retrieved content here).
- [ ] Similarity threshold check — not applicable (RAG-only).
- [ ] Synchronous faithfulness/grounding check — not applicable
      (RAG-adjacent only).
- [x] Adversarial test cases — `tests/unit/test_segmenter_clustering.py`
      covers a feature matrix with too few rows for any candidate
      algorithm to reach the 3-cluster floor (e.g. 2 rows) and asserts
      `cluster()` raises `ClusteringError` with a clear message rather
      than crashing uninformatively or returning a degenerate/misleading
      result. Note: "homogeneous/near-identical data" is deliberately
      NOT used as the adversarial case here — verified that
      `AgglomerativeClustering` (ward linkage, a tree-cut) structurally
      guarantees exactly `k` non-empty groups for any `k <= n` regardless
      of whether the data has real structure, so it would never actually
      return `None` on homogeneous data and `ClusteringError` would never
      fire. Too-few-rows is the only content-independent, deterministic
      trigger.

## Golden Eval Cases to Add
No eval additions in this feature — golden dataset construction
(`eval/golden_datasets/segmenter_eval.jsonl`) and the gating script
(`eval/run_segmenter_eval.py`) are explicitly out of scope for Phase 1's
individual pipeline-stage features (per feature 01.01's precedent and the
master spec's "not yet numbered" evaluation-harness feature). This
feature's correctness is verified via deterministic unit tests on
synthetic, known-structure datasets (see Definition of Done below). The
master spec's cluster-stability-ARI (≥0.75) and ground-truth-ARI gates
will ultimately be exercised end-to-end once that separate
evaluation-harness feature exists and wires in this module.

## Files to Create
- `app/agents/segmenter/clustering.py` — the pipeline described above
- `tests/unit/test_segmenter_clustering.py` — unit tests for every
  function, including the adversarial no-viable-clusters case

## Files to Modify
None. `scikit-learn` (already a dependency from feature 01.01, version
1.9.0 installed) provides `KMeans`, `AgglomerativeClustering`,
`silhouette_score`, `davies_bouldin_score`, and `adjusted_rand_score`.
`numpy` (already a dependency) covers the rest.

## New Dependencies
None.

## Rules for Implementation
From CLAUDE.md §4, relevant to this feature:
- **Rule 1** (no raw `ChatGroq(...)` outside `app/llm/llm_clients.py`) —
  N/A, this feature makes no LLM calls.
- **Rule 2** (no LLM call site without a declared `ROUTING_TABLE` tier) —
  N/A for the same reason.
- **Rule 3** (no free-text agent-to-agent handoffs) — N/A, no agent
  boundary is crossed by this feature; internal functions use plain
  dataclasses per CLAUDE.md §5's scoping of Pydantic to agent I/O.
- **Rule 9** (no agent/prompt change ships without its eval passing) —
  this feature has no eval script of its own (see Golden Eval Cases
  above); its unit tests are the applicable gate instead.
- **Rule 10** (no secrets in code) — N/A, no secrets involved.
- CLAUDE.md §9: don't silently widen validation to make a failing test
  pass — applies directly to `stability_ari_threshold` (default `0.75`,
  matching CLAUDE.md §7's "Segmenter cluster stability (ARI across
  reseeded runs) ≥ 0.75" gate exactly), the `>=3 clusters` qualification
  floor (lowered from the blueprint's original 4 per its 2026-09-08
  amendment — this is now the floor, not a value to lower further), and
  `silhouette_tie_epsilon` (default `0.02`): if a test fails because a
  dataset can't clear a bar, or because the epsilon window is picking a
  candidate that "feels wrong" for that specific test, do not loosen the
  threshold to make the test pass — surface it. These gates exist
  specifically to catch unreliable/unstable segmentation before it ships
  (blueprint §5.2, master spec Risk Register: "Clustering instability
  across runs undermines trust").
- Repository structure (CLAUDE.md §3): this module lives under
  `app/agents/segmenter/` and must import and run standalone — no
  reaching into `app/supervisor/` (trivially true here).

## Definition of Done
- [x] `run_kmeans_candidates` and `run_agglomerative_candidates` each
      correctly identify the true cluster count and produce a valid
      `ClusteringCandidate` (correct `n_clusters`, finite
      `silhouette`/`davies_bouldin`) on a synthetic, deterministically
      constructed dataset with a known number of well-separated clusters
      (e.g. 3-6 distinct point groups placed at fixed, non-random
      coordinates), including a dedicated case with exactly 3 groups to
      exercise the lowered floor
- [x] `select_best_candidate` deterministically picks the outright-best
      silhouette candidate when no other candidate falls within
      `silhouette_tie_epsilon`; and, on a constructed list with two
      candidates whose silhouette scores are within the epsilon window
      but whose Davies-Bouldin scores differ, picks the lower-Davies-
      Bouldin one even though it does not have the single highest
      silhouette — proving the epsilon window actually changes the
      outcome, not just a same-result sanity check
- [x] `check_stability` returns 10 pairwise ARI scores (5 runs → C(5,2)
      pairs) and correctly flags `is_stable=True` on a well-separated,
      easily-reproducible synthetic dataset
- [x] `cluster()` run end-to-end on a synthetic separable dataset (45
      rows, 3 well-separated groups) produces a `ClusteringResult` with
      `n_clusters >= 3`, `is_stable=True`, and `all_candidates` containing
      one entry per algorithm family that reached the 3-cluster floor (up
      to 2: kmeans, agglomerative)
- [x] `cluster()` correctly handles the asymmetric case where one
      algorithm family returns `None` and the other succeeds: on a
      constructed two-location, heavily-duplicated-point dataset, KMeans
      collapses to fewer than 3 distinct labels at every `k` (a genuine
      Lloyd's-algorithm degeneracy, not a density-based noise rejection)
      while Agglomerative-ward's tree-cut still produces exactly `k`
      non-empty clusters — `all_candidates` ends up with exactly 1 entry
      (`"agglomerative"`), not 2, and `cluster()` does not crash on the
      `None` from `run_kmeans_candidates`
- [x] Real-world verification: re-ran against actual feature 01.01
      `preprocess()` output on the Kaggle Sample Superstore dataset
      (7,143 rows, 84 columns) that originally exposed the DBSCAN/HDBSCAN
      noise-fraction bias — confirmed `kmeans` won (`n_clusters=3`,
      `is_stable=True`, `all_candidates=["kmeans", "agglomerative"]`)
      with **zero noise rows**: cluster sizes 3,033 + 2,914 + 1,196 =
      7,143, every row accounted for. Directly closes the gap the
      amendment above describes. Note: runtime was ~48s, essentially
      unchanged from the original ~46s — confirms the slowness was never
      really about DBSCAN/HDBSCAN; it's `run_agglomerative_candidates`
      refitting a full ward-linkage tree from scratch 8 times (once per
      `k` in `range(3,11)`) on 7,143 rows. A separate, still-open
      performance concern, not something this redesign fixes or was
      meant to — tracked as a follow-up, not blocking this feature.
- [x] `cluster()` raises `ClusteringError` on a too-few-rows input (e.g.
      2 rows) where no algorithm family can even attempt to reach 3
      clusters (adversarial case, per the Guardrails Checklist item above
      — not a "homogeneous data" case, which would not actually trigger
      this)
- [x] Unit tests in `tests/unit/test_segmenter_clustering.py` added and
      passing (`pytest tests/unit/test_segmenter_clustering.py` — 15/15;
      full `tests/unit` suite 61/61, no regressions)
- [x] No CLAUDE.md §4 or §9 rule violations (self-check before marking complete)

## Out of Scope
- Preprocessing (feature matrix construction, feature selection) —
  feature 01.01, already `Complete`
- The LLM naming chain and `ClusterSummary` schema — feature 01.03
- Dual persistence to PostgreSQL `cluster_profiles` / Chroma — feature 01.04
- `SegmenterAgentInput`/`Output` and the public agent entrypoint — feature 01.05
- Golden dataset construction and `eval/run_segmenter_eval.py` — the
  evaluation-harness feature within this phase (not yet numbered)
- Any guardrail beyond the minimal adversarial-input unit test above —
  full guardrail consolidation is Phase 7
- Re-running the full candidate grid search with stability as a
  per-candidate selection criterion — deliberately out of scope per the
  Overview interpretation note; revisit only if the blueprint is amended
  to require it explicitly
- **Known follow-up, not fixed here:** `run_agglomerative_candidates`
  refits a full ward-linkage tree from scratch for every `k` in
  `k_range` (8 separate fits by default). Profiled on the real
  Superstore dataset (7,143 rows × 84 columns): this function alone took
  34.98s of `cluster()`'s ~48s total runtime (`run_kmeans_candidates`:
  10.71s, `check_stability`: 0.92s). Ward-linkage clustering computes one
  dendrogram and different `k` values only require cutting it at
  different heights — that cut is nearly free, so refitting per-`k` is
  pure waste. Fix: build the tree once via
  `scipy.cluster.hierarchy.linkage(X, method="ward")`, then cut it per
  `k` via `scipy.cluster.hierarchy.fcluster(tree, k, criterion="maxclust")`
  instead of calling `sklearn.cluster.AgglomerativeClustering` 8 times.
  Expected to bring `cluster()`'s total runtime on datasets this size
  from ~48s down to roughly 10-15s. Deliberately deferred: this feature
  has already gone through two redesigns in one session, the current
  implementation is correct (no accuracy/behavior issue, purely a
  performance one), and whether this actually needs fixing depends on
  how `cluster()` gets invoked once feature 01.05 (the agent interface)
  exists — tolerable if segmentation runs as a background job, not if it
  ever needs to run synchronously in a user-facing request. Revisit then.
