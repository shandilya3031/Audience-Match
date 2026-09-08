import numpy as np
import pytest

from app.agents.segmenter.clustering import (
    ClusteringCandidate,
    ClusteringError,
    check_stability,
    cluster,
    run_agglomerative_candidates,
    run_kmeans_candidates,
    select_best_candidate,
)


def _make_blobs(centers, points_per_cluster, jitter=1.0):
    rows = []
    for cx, cy in centers:
        for k in range(points_per_cluster):
            dx = ((k % 7) - 3) * (jitter / 3)
            dy = (((k // 7) % 7) - 3) * (jitter / 3)
            rows.append([cx + dx, cy + dy])
    return np.array(rows, dtype=float)


def _three_cluster_matrix():
    return _make_blobs([(0, 0), (20, 0), (10, 17.32)], points_per_cluster=15, jitter=1.0)


def _six_cluster_matrix():
    centers = [(0, 0), (30, 0), (60, 0), (0, 30), (30, 30), (60, 30)]
    return _make_blobs(centers, points_per_cluster=12, jitter=1.0)


def _tiny_matrix():
    return np.array([[0.0, 0.0], [1.0, 1.0]])


def _two_location_duplicated_matrix():
    # Two heavily-duplicated point locations. KMeans's Lloyd's-algorithm
    # collapses to 2 distinct labels at every k -- it has no mechanism to
    # split an exactly-duplicated point cloud into more groups than there
    # are distinct locations, so it never clears the 3-cluster floor here.
    # AgglomerativeClustering (ward), as a tree-cut, still produces exactly
    # k non-empty labels for any k <= n regardless of duplication, so it
    # succeeds where KMeans returns None -- the genuine, deterministic
    # asymmetric-partial-success case for this two-algorithm pipeline.
    return np.vstack([np.tile([0.0, 0.0], (30, 1)), np.tile([100.0, 100.0], (30, 1))])


def test_run_kmeans_candidates_recovers_three_cluster_floor():
    candidate = run_kmeans_candidates(_three_cluster_matrix())
    assert candidate is not None
    assert candidate.n_clusters == 3


def test_run_kmeans_candidates_recovers_six_clusters():
    candidate = run_kmeans_candidates(_six_cluster_matrix())
    assert candidate is not None
    assert candidate.n_clusters == 6


@pytest.mark.filterwarnings("ignore::sklearn.exceptions.ConvergenceWarning")
def test_run_kmeans_candidates_returns_none_on_duplicated_locations():
    assert run_kmeans_candidates(_two_location_duplicated_matrix()) is None


def test_run_agglomerative_candidates_recovers_three_cluster_floor():
    candidate = run_agglomerative_candidates(_three_cluster_matrix())
    assert candidate is not None
    assert candidate.n_clusters == 3


def test_run_agglomerative_candidates_recovers_six_clusters():
    candidate = run_agglomerative_candidates(_six_cluster_matrix())
    assert candidate is not None
    assert candidate.n_clusters == 6


def test_run_agglomerative_candidates_is_deterministic_across_calls():
    X = _three_cluster_matrix()
    first = run_agglomerative_candidates(X)
    second = run_agglomerative_candidates(X)
    assert np.array_equal(first.labels, second.labels)


def test_select_best_candidate_picks_outright_best_silhouette_when_no_near_tie():
    a = ClusteringCandidate("a", {}, np.array([]), 3, 0.9, 0.5)
    b = ClusteringCandidate("b", {}, np.array([]), 3, 0.5, 0.1)
    assert select_best_candidate([a, b]) is a


def test_select_best_candidate_picks_lower_davies_bouldin_within_epsilon_window():
    a = ClusteringCandidate("a", {}, np.array([]), 3, 0.90, 0.8)
    b = ClusteringCandidate("b", {}, np.array([]), 3, 0.89, 0.3)  # within 0.02, lower DB
    assert select_best_candidate([a, b], silhouette_tie_epsilon=0.02) is b


def test_select_best_candidate_excludes_candidates_outside_epsilon_window_despite_best_davies_bouldin():
    a = ClusteringCandidate("a", {}, np.array([]), 3, 0.90, 0.8)
    b = ClusteringCandidate("b", {}, np.array([]), 3, 0.60, 0.05)  # far outside window
    assert select_best_candidate([a, b], silhouette_tie_epsilon=0.02) is a


def test_select_best_candidate_breaks_residual_tie_by_input_order():
    a = ClusteringCandidate("a", {}, np.array([]), 3, 0.9, 0.5)
    b = ClusteringCandidate("b", {}, np.array([]), 3, 0.9, 0.5)
    assert select_best_candidate([a, b]) is a


def test_check_stability_returns_ten_pairwise_scores_for_five_runs():
    scores, _ = check_stability(_three_cluster_matrix(), "kmeans", {"n_clusters": 3})
    assert len(scores) == 10


def test_check_stability_flags_stable_on_well_separated_data():
    _, is_stable = check_stability(_three_cluster_matrix(), "kmeans", {"n_clusters": 3})
    assert is_stable is True


def test_cluster_end_to_end_produces_stable_multi_algorithm_result():
    result = cluster(_three_cluster_matrix())
    assert result.n_clusters >= 3
    assert result.is_stable is True
    assert len(result.all_candidates) == 2


@pytest.mark.filterwarnings("ignore::sklearn.exceptions.ConvergenceWarning")
def test_cluster_excludes_none_candidates_from_all_candidates():
    result = cluster(_two_location_duplicated_matrix())
    assert len(result.all_candidates) == 1
    assert result.all_candidates[0].algorithm == "agglomerative"


def test_cluster_raises_clustering_error_on_too_few_rows():
    with pytest.raises(ClusteringError):
        cluster(_tiny_matrix())
