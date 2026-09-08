import json

import numpy as np
import pandas as pd
import pytest

from app.agents.segmenter.preprocessing import (
    drop_correlated_features,
    drop_high_missing_columns,
    drop_identifier_like_columns,
    drop_near_constant_columns,
    identify_column_types,
    preprocess,
    read_customer_csv,
    remove_outliers_iqr,
    scale_and_encode,
)


def test_identify_column_types_splits_numeric_and_categorical():
    df = pd.DataFrame({"age": [20, 30, 40], "income": [1.5, 2.5, 3.5], "region": ["A", "B", "C"]})
    numeric, categorical = identify_column_types(df)
    assert numeric == ["age", "income"]
    assert categorical == ["region"]


def test_identify_column_types_treats_non_numeric_junk_as_categorical():
    df = pd.DataFrame({"maybe_numeric": ["42", "abc", "17"]})
    numeric, categorical = identify_column_types(df)
    assert numeric == []
    assert categorical == ["maybe_numeric"]


def test_drop_high_missing_columns_drops_columns_over_threshold():
    df = pd.DataFrame({"a": [1] + [None] * 9, "b": list(range(10))})
    result_df, dropped = drop_high_missing_columns(df, threshold=0.85)
    assert dropped == ["a"]
    assert list(result_df.columns) == ["b"]


def test_drop_high_missing_columns_keeps_columns_under_threshold():
    df = pd.DataFrame({"a": list(range(10)), "b": list(range(10, 20))})
    result_df, dropped = drop_high_missing_columns(df, threshold=0.85)
    assert dropped == []
    assert list(result_df.columns) == ["a", "b"]


def test_drop_high_missing_columns_drops_all_missing_column():
    df = pd.DataFrame({"a": [None] * 5, "b": list(range(5))})
    _, dropped = drop_high_missing_columns(df, threshold=0.85)
    assert dropped == ["a"]


def test_drop_identifier_like_columns_drops_near_unique_categorical_by_ratio():
    n = 40
    df = pd.DataFrame(
        {
            "near_unique": [f"v{i}" for i in range(35)] + ["v0"] * 5,  # 35/40 = 0.875 ratio
            "segment": ["A", "B"] * (n // 2),
        }
    )
    _, kept_numeric, kept_categorical, dropped = drop_identifier_like_columns(
        df, [], ["near_unique", "segment"]
    )
    assert dropped == ["near_unique"]
    assert kept_categorical == ["segment"]


def test_drop_identifier_like_columns_drops_high_cardinality_categorical_by_cap():
    n = 200
    df = pd.DataFrame(
        {
            "wide_category": [f"cat{i % 60}" for i in range(n)],  # 60 unique, ratio 0.3
            "segment": (["A", "B", "C"] * 67)[:n],
        }
    )
    _, _, kept_categorical, dropped = drop_identifier_like_columns(
        df, [], ["wide_category", "segment"], max_categorical_cardinality=50
    )
    assert dropped == ["wide_category"]
    assert kept_categorical == ["segment"]


def test_drop_identifier_like_columns_drops_numeric_perfect_sequence():
    df = pd.DataFrame(
        {"row_id": list(range(1, 51)), "income": [1000.0 + i * 3.7 for i in range(50)]}
    )
    _, kept_numeric, _, dropped = drop_identifier_like_columns(df, ["row_id", "income"], [])
    assert "row_id" in dropped
    assert kept_numeric == ["income"]


def test_drop_identifier_like_columns_drops_numeric_unique_sequence_with_gaps():
    values = list(range(1, 21)) + list(range(31, 51))  # 40 distinct integers, gap 21-30
    df = pd.DataFrame({"sparse_id": values})
    _, kept_numeric, _, dropped = drop_identifier_like_columns(df, ["sparse_id"], [])
    assert dropped == ["sparse_id"]
    assert kept_numeric == []


def test_drop_identifier_like_columns_keeps_high_cardinality_continuous_numeric():
    df = pd.DataFrame({"income": [i + 0.5 for i in range(50)]})
    _, kept_numeric, _, dropped = drop_identifier_like_columns(df, ["income"], [])
    assert dropped == []
    assert kept_numeric == ["income"]


def test_drop_identifier_like_columns_keeps_low_cardinality_columns():
    n = 40
    df = pd.DataFrame({"age": [20 + (i % 5) for i in range(n)], "region": ["N", "S"] * (n // 2)})
    _, kept_numeric, kept_categorical, dropped = drop_identifier_like_columns(
        df, ["age"], ["region"]
    )
    assert dropped == []
    assert kept_numeric == ["age"]
    assert kept_categorical == ["region"]


def test_drop_identifier_like_columns_skips_check_below_min_rows():
    df = pd.DataFrame({"unique_col": [f"v{i}" for i in range(10)]})
    _, _, kept_categorical, dropped = drop_identifier_like_columns(
        df, [], ["unique_col"], min_rows_for_identifier_check=30
    )
    assert dropped == []
    assert kept_categorical == ["unique_col"]


def test_drop_near_constant_columns_drops_constant_numeric():
    df = pd.DataFrame({"constant": [5.0] * 10, "varying": list(range(10))})
    _, kept_numeric, _, dropped = drop_near_constant_columns(df, ["constant", "varying"], [])
    assert dropped == ["constant"]
    assert kept_numeric == ["varying"]


def test_drop_near_constant_columns_drops_single_value_categorical():
    df = pd.DataFrame({"country": ["US"] * 10, "segment": ["A", "B"] * 5})
    _, _, kept_categorical, dropped = drop_near_constant_columns(df, [], ["country", "segment"])
    assert dropped == ["country"]
    assert kept_categorical == ["segment"]


def test_drop_near_constant_columns_keeps_normal_variance_columns():
    df = pd.DataFrame({"income": list(range(10)), "segment": ["A", "B"] * 5})
    _, kept_numeric, kept_categorical, dropped = drop_near_constant_columns(
        df, ["income"], ["segment"]
    )
    assert dropped == []
    assert kept_numeric == ["income"]
    assert kept_categorical == ["segment"]


def test_remove_outliers_iqr_removes_out_of_fence_rows():
    df = pd.DataFrame({"x": [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 10000]})
    result = remove_outliers_iqr(df, ["x"])
    assert 10000 not in result["x"].values
    assert len(result) == 10


def test_remove_outliers_iqr_keeps_in_range_rows_untouched():
    df = pd.DataFrame({"x": [10, 11, 12, 13, 14, 15]})
    result = remove_outliers_iqr(df, ["x"])
    assert list(result["x"]) == list(df["x"])


def test_remove_outliers_iqr_returns_df_unchanged_when_no_numeric_columns():
    df = pd.DataFrame({"x": ["a", "b", "c"]})
    result = remove_outliers_iqr(df, [])
    pd.testing.assert_frame_equal(result, df)


def test_scale_and_encode_standardizes_numeric_columns():
    df = pd.DataFrame({"income": [10.0, 20.0, 30.0, 40.0]})
    matrix, feature_names = scale_and_encode(df, ["income"], [])
    assert feature_names == ["income"]
    assert np.isclose(matrix[:, 0].mean(), 0.0, atol=1e-8)
    assert np.isclose(matrix[:, 0].std(), 1.0, atol=1e-8)


def test_scale_and_encode_one_hot_encodes_with_expected_naming():
    df = pd.DataFrame({"region": ["West", "East", "West"]})
    _, feature_names = scale_and_encode(df, [], ["region"])
    assert "region_onehot_West" in feature_names
    assert "region_onehot_East" in feature_names


def test_scale_and_encode_feature_names_match_matrix_columns():
    df = pd.DataFrame({"income": [1.0, 2.0, 3.0], "region": ["A", "B", "A"]})
    matrix, feature_names = scale_and_encode(df, ["income"], ["region"])
    assert len(feature_names) == matrix.shape[1]


def test_scale_and_encode_handles_no_categorical_columns():
    df = pd.DataFrame({"income": [1.0, 2.0, 3.0], "age": [20.0, 30.0, 40.0]})
    matrix, feature_names = scale_and_encode(df, ["income", "age"], [])
    assert matrix.shape[1] == 2
    assert feature_names == ["income", "age"]


def test_scale_and_encode_handles_no_numeric_columns():
    df = pd.DataFrame({"region": ["A", "B", "A"]})
    matrix, feature_names = scale_and_encode(df, [], ["region"])
    assert matrix.shape[1] == 2
    assert feature_names == ["region_onehot_A", "region_onehot_B"]


def test_drop_correlated_features_drops_second_column_of_pair():
    matrix = np.array([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0], [4.0, 4.0]])
    reduced, kept, dropped = drop_correlated_features(matrix, ["a", "b"], threshold=0.9)
    assert dropped == ["b"]
    assert kept == ["a"]
    assert reduced.shape[1] == 1


def test_drop_correlated_features_is_deterministic():
    matrix = np.array([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0], [4.0, 4.0]])
    result_1 = drop_correlated_features(matrix, ["a", "b"], threshold=0.9)
    result_2 = drop_correlated_features(matrix, ["a", "b"], threshold=0.9)
    assert result_1[1] == result_2[1]
    assert result_1[2] == result_2[2]


def test_drop_correlated_features_feature_names_length_matches_matrix():
    matrix = np.array([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0], [4.0, 4.0]])
    reduced, kept, _ = drop_correlated_features(matrix, ["a", "b"], threshold=0.9)
    assert len(kept) == reduced.shape[1]


def test_drop_correlated_features_keeps_uncorrelated_columns():
    matrix = np.array([[1.0, 1.0], [2.0, -1.0], [3.0, 1.0], [4.0, -1.0]])
    reduced, kept, dropped = drop_correlated_features(matrix, ["a", "b"], threshold=0.9)
    assert dropped == []
    assert kept == ["a", "b"]
    assert reduced.shape[1] == 2


def test_drop_correlated_features_handles_single_feature_matrix():
    matrix = np.array([[1.0], [2.0], [3.0], [4.0]])
    reduced, kept, dropped = drop_correlated_features(matrix, ["a"], threshold=0.9)
    assert dropped == []
    assert kept == ["a"]
    assert reduced.shape == (4, 1)


def test_read_customer_csv_falls_back_to_latin1_on_decode_error(tmp_path):
    csv_path = tmp_path / "customers.csv"
    content = "name,city\nJos\xe9,Madrid\n"  # \xe9 ("é") is invalid as UTF-8 standalone
    csv_path.write_bytes(content.encode("latin-1"))
    df = read_customer_csv(csv_path)
    assert df.loc[0, "name"] == "Jos\xe9"


def _build_sample_customer_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "high_missing": [None] * 18 + [1, 2],
            "income": list(range(100, 120)),
            "income_copy": list(range(100, 120)),
            "age": [25, 31, 22, 29, 35, 20, 33, 27, 24, 30, 26, 32, 23, 28, 34, 21, 36, 25, 29, 9999],
            "region": ["North", "South"] * 10,
            "junk_looking": (["1", "2", "abc"] * 7)[:20],
        }
    )


def test_preprocess_end_to_end_produces_clean_feature_matrix(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "segmenter_artifacts_dir", str(tmp_path / "artifacts"))
    csv_path = tmp_path / "customers.csv"
    _build_sample_customer_df().to_csv(csv_path, index=False)

    result = preprocess(csv_path, client_id="test_client")

    assert np.isfinite(result.feature_matrix).all()
    assert result.feature_matrix.shape[0] == 19  # one outlier row removed
    assert result.cleaned_df.shape[0] == 19

    # dropped for >85% missingness (this fixture is 20 rows -- below the
    # identifier-check floor, so income/income_copy/junk_looking are never
    # touched by drop_identifier_like_columns despite being fully unique)
    assert result.dropped_columns["high_missing"] == "high_missing"
    # dropped for |corr| > 0.9 -- income_copy is the second-encountered column of the pair
    assert result.dropped_columns["income_copy"] == "high_correlation"

    assert "income" in result.feature_names
    assert "age" in result.feature_names
    assert any(name.startswith("region_onehot_") for name in result.feature_names)
    assert any(name.startswith("junk_looking_onehot_") for name in result.feature_names)


def test_preprocess_writes_feature_lineage_json_roundtrip(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "segmenter_artifacts_dir", str(tmp_path / "artifacts"))
    csv_path = tmp_path / "customers.csv"
    _build_sample_customer_df().to_csv(csv_path, index=False)

    result = preprocess(csv_path, client_id="test_client")

    lineage_path = tmp_path / "artifacts" / "test_client" / "feature_lineage.json"
    with open(lineage_path) as f:
        lineage = json.load(f)

    assert isinstance(lineage["dropped_columns"], dict)
    assert lineage == {
        "feature_names": result.feature_names,
        "dropped_columns": result.dropped_columns,
    }


def test_preprocess_handles_adversarial_columns_gracefully(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "segmenter_artifacts_dir", str(tmp_path / "artifacts"))
    df = pd.DataFrame(
        {
            "all_missing": [None] * 10,
            "junk_numeric": ["1", "2", "x", "4", "5", "6", "7", "8", "9", "10"],
            "value": list(range(10)),
        }
    )
    csv_path = tmp_path / "adversarial.csv"
    df.to_csv(csv_path, index=False)

    result = preprocess(csv_path, client_id="adv_client")

    assert result.dropped_columns["all_missing"] == "high_missing"
    assert any(name.startswith("junk_numeric_onehot_") for name in result.feature_names)
    assert np.isfinite(result.feature_matrix).all()


def _build_high_cardinality_df(n: int = 600) -> pd.DataFrame:
    # Deterministic (no np.random), synthetic reproduction of the real-world
    # shape that broke the original implementation: a Row-ID-style perfect
    # sequence, an order-id-style unique-per-row categorical column, a
    # handful of genuine low-cardinality categoricals, and genuine
    # continuous numerics -- without committing the actual dataset.
    return pd.DataFrame(
        {
            "row_id": list(range(1, n + 1)),
            "order_id": [f"ORD-{i}" for i in range(n)],
            "customer_name": [f"Customer {i}" for i in range(n)],
            "segment": ["Consumer", "Corporate", "Home Office"] * (n // 3),
            "region": ["East", "West", "North", "South"] * (n // 4),
            "sales": [50.0 + (i % 97) * 3.7 for i in range(n)],
            "discount": [round((i % 11) * 0.05, 2) for i in range(n)],
        }
    )


def test_preprocess_drops_identifier_like_columns_on_high_cardinality_dataset(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "segmenter_artifacts_dir", str(tmp_path / "artifacts"))
    csv_path = tmp_path / "high_cardinality.csv"
    _build_high_cardinality_df().to_csv(csv_path, index=False)

    result = preprocess(csv_path, client_id="hc_client")

    assert result.dropped_columns["row_id"] == "identifier_like"
    assert result.dropped_columns["order_id"] == "identifier_like"
    assert result.dropped_columns["customer_name"] == "identifier_like"
    # bounded, not exploded into hundreds/thousands of one-hot columns
    assert result.feature_matrix.shape[1] < 30
