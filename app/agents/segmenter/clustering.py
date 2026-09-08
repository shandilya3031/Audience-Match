import itertools
from dataclasses import dataclass

import numpy as np
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.metrics import adjusted_rand_score, davies_bouldin_score, silhouette_score

# Fixed rather than randomized per run -- ClusteringCandidate.params for kmeans
# only ever stores {"n_clusters": k} (no random_state key), so check_stability
# has no way to recover a per-candidate random_state. Keeping it fixed means
# the only source of variability across check_stability's bootstrap runs is
# the subsample itself, not the algorithm's own internal randomness.
_KMEANS_RANDOM_STATE = 42


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


def _score_candidate(
    X: np.ndarray, labels: np.ndarray, algorithm: str, params: dict
) -> ClusteringCandidate | None:
    """Shared by run_kmeans_candidates/run_agglomerative_candidates:
    recounts n_clusters from the actual labels (never assumes it equals a
    requested k -- KMeans can legitimately collapse to fewer distinct
    labels on degenerate/duplicate data), and returns None if the cluster
    count doesn't clear the 3-cluster floor or if scoring itself is
    undefined (e.g. only 1 distinct label survives)."""
    n_clusters = len(set(labels.tolist()))
    if n_clusters < 3:
        return None
    try:
        silhouette = silhouette_score(X, labels)
        davies_bouldin = davies_bouldin_score(X, labels)
    except ValueError:
        # e.g. "Number of labels is 1" -- a degenerate collapse that still
        # nominally reported >=3 unique values above but isn't scorable.
        return None
    return ClusteringCandidate(
        algorithm=algorithm,
        params=params,
        labels=labels,
        n_clusters=n_clusters,
        silhouette=silhouette,
        davies_bouldin=davies_bouldin,
    )


def _fit_candidate_labels(algorithm: str, params: dict, X: np.ndarray) -> np.ndarray:
    """Reconstructs and fits the sklearn estimator matching an
    algorithm/params pair. Used by check_stability to refit the winning
    candidate on each bootstrap subsample."""
    if algorithm == "kmeans":
        model = KMeans(
            n_clusters=params["n_clusters"], n_init=10, random_state=_KMEANS_RANDOM_STATE
        )
    elif algorithm == "agglomerative":
        model = AgglomerativeClustering(n_clusters=params["n_clusters"], linkage="ward")
    else:
        raise ValueError(f"Unknown algorithm '{algorithm}'")
    return model.fit_predict(X)


def run_kmeans_candidates(
    X: np.ndarray, k_range: range = range(3, 11), random_state: int = _KMEANS_RANDOM_STATE
) -> ClusteringCandidate | None:
    """Fits KMeans(n_clusters=k, n_init=10, random_state=random_state) for
    each k in k_range, scores each by silhouette, returns the
    best-scoring k's candidate. None if no k in k_range is viable (e.g.
    every k >= len(X), or every k collapses to fewer than 3 distinct
    labels on degenerate/duplicate data) -- see the empty-all_candidates
    guard in cluster()."""
    best = None
    for k in k_range:
        if k >= len(X):
            continue
        labels = KMeans(n_clusters=k, n_init=10, random_state=random_state).fit_predict(X)
        candidate = _score_candidate(X, labels, "kmeans", {"n_clusters": k})
        if candidate is not None and (best is None or candidate.silhouette > best.silhouette):
            best = candidate
    return best


def run_agglomerative_candidates(
    X: np.ndarray, k_range: range = range(3, 11)
) -> ClusteringCandidate | None:
    """Fits AgglomerativeClustering(n_clusters=k, linkage="ward") for each
    k in k_range, scores by silhouette, returns the best-scoring k's
    candidate. Deterministic -- ward linkage has no random_state, and
    (as a tree-cut) unconditionally produces exactly k non-empty clusters
    for any k <= len(X), so this practically never returns None except
    when every k in k_range is skipped for being too large."""
    best = None
    for k in k_range:
        if k >= len(X):
            continue
        labels = AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(X)
        candidate = _score_candidate(X, labels, "agglomerative", {"n_clusters": k})
        if candidate is not None and (best is None or candidate.silhouette > best.silhouette):
            best = candidate
    return best


def select_best_candidate(
    candidates: list[ClusteringCandidate], silhouette_tie_epsilon: float = 0.02
) -> ClusteringCandidate:
    """Selects primarily by silhouette (higher is better). Among all
    candidates whose silhouette is within silhouette_tie_epsilon of the
    single best silhouette score (a near-tie window, not an exact-equality
    check), the one with the lowest davies_bouldin wins. If exactly one
    candidate has the best silhouette and no other candidate falls within
    the epsilon window, davies_bouldin plays no role and that candidate
    wins outright. Deterministic given fixed candidates/epsilon: ties
    within the near-tied group on davies_bouldin itself resolve by
    candidates' input list order (Python's min() returns the first
    occurrence on a tied key)."""
    best_silhouette = max(candidate.silhouette for candidate in candidates)
    near_tied = [
        candidate
        for candidate in candidates
        if best_silhouette - candidate.silhouette <= silhouette_tie_epsilon
    ]
    return min(near_tied, key=lambda candidate: candidate.davies_bouldin)


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
    n_rows = len(X)
    sample_size = max(2, round(sample_frac * n_rows))

    runs: list[tuple[np.ndarray, np.ndarray]] = []
    for seed in range(n_runs):
        rng = np.random.RandomState(seed)
        indices = np.sort(rng.choice(n_rows, size=sample_size, replace=False))
        labels = _fit_candidate_labels(algorithm, params, X[indices])
        runs.append((indices, labels))

    pairwise_scores: list[float] = []
    for i, j in itertools.combinations(range(n_runs), 2):
        idx_i, labels_i = runs[i]
        idx_j, labels_j = runs[j]
        common = np.intersect1d(idx_i, idx_j)
        if len(common) < 2:
            continue
        pos_i = np.searchsorted(idx_i, common)
        pos_j = np.searchsorted(idx_j, common)
        pairwise_scores.append(adjusted_rand_score(labels_i[pos_i], labels_j[pos_j]))

    is_stable = bool(pairwise_scores) and (sum(pairwise_scores) / len(pairwise_scores)) >= ari_threshold
    return pairwise_scores, is_stable


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
    candidates: list[ClusteringCandidate] = []
    for candidate in (
        run_kmeans_candidates(X, k_range=k_range),
        run_agglomerative_candidates(X, k_range=k_range),
    ):
        if candidate is not None:
            candidates.append(candidate)

    if not candidates:
        raise ClusteringError(
            f"No candidate algorithm achieved >=3 valid clusters on {len(X)} rows."
        )

    best = select_best_candidate(candidates, silhouette_tie_epsilon=silhouette_tie_epsilon)
    stability_ari_scores, is_stable = check_stability(
        X, best.algorithm, best.params, ari_threshold=stability_ari_threshold
    )

    return ClusteringResult(
        labels=best.labels,
        algorithm=best.algorithm,
        params=best.params,
        n_clusters=best.n_clusters,
        silhouette=best.silhouette,
        davies_bouldin=best.davies_bouldin,
        stability_ari_scores=stability_ari_scores,
        is_stable=is_stable,
        all_candidates=candidates,
    )
