import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.storage.local_files import segmenter_artifact_path


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
    """Reads a raw client CSV. Tries UTF-8 first (pandas default); falls back
    to latin-1 (which never raises a decode error) on UnicodeDecodeError --
    the standard safe fallback for legacy/Excel-exported CSVs using
    Windows-1252/Latin-1 encoding."""
    try:
        return pd.read_csv(csv_path)
    except UnicodeDecodeError:
        return pd.read_csv(csv_path, encoding="latin-1")


def identify_column_types(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Returns (numeric_columns, categorical_columns). Exhaustive and mutually
    exclusive: a column pandas infers as non-numeric (e.g. a numeric-looking
    column containing stray non-numeric values) lands in categorical, not
    numeric -- no crash, no special-casing."""
    numeric_columns = df.select_dtypes(include="number").columns.tolist()
    categorical_columns = df.select_dtypes(exclude="number").columns.tolist()
    return numeric_columns, categorical_columns


def drop_high_missing_columns(
    df: pd.DataFrame, threshold: float = 0.85
) -> tuple[pd.DataFrame, list[str]]:
    """Returns (df_with_columns_dropped, dropped_column_names). A column that
    is entirely missing trivially qualifies for dropping."""
    missing_fraction = df.isna().mean()
    dropped = missing_fraction[missing_fraction > threshold].index.tolist()
    return df.drop(columns=dropped), dropped


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
    rather than clustering features, using purely statistical signals -- no
    column-name matching, so this generalizes across arbitrary client
    schemas.

    Categorical columns are dropped if they're near-unique (cardinality
    ratio above identifier_cardinality_ratio) OR simply have too many
    distinct values to encode sensibly (above max_categorical_cardinality),
    whichever catches it -- the absolute cap is what catches columns like
    customer/product IDs or free-text names, whose ratio is well under 0.5
    but whose raw cardinality is still far too high to one-hot encode.

    Numeric columns use a much stricter rule: only a fully-unique,
    integer-valued column (every row distinct, no NaNs) is dropped as an
    identifier -- genuine continuous features (income, sales) are *expected*
    to have high cardinality, so high cardinality alone must never exclude
    a numeric column.

    No-ops entirely below min_rows_for_identifier_check rows: on small
    samples, a genuine feature can accidentally look fully unique by
    chance, so cardinality-based pruning isn't statistically meaningful
    there -- and a small dataset can't produce the one-hot blowup this
    guards against anyway.

    Known limitation: a numeric column that is semantically categorical but
    not unique per row (e.g. a postal/ZIP code) is not caught by any rule
    here -- there's no generic statistical signal that safely distinguishes
    it from a genuine bounded-range continuous feature without domain
    knowledge."""
    n_rows = len(df)
    if n_rows < min_rows_for_identifier_check:
        return df, list(numeric_columns), list(categorical_columns), []

    dropped: list[str] = []

    kept_categorical = []
    for column in categorical_columns:
        nunique = df[column].nunique(dropna=True)
        ratio = nunique / n_rows
        if ratio > identifier_cardinality_ratio or nunique > max_categorical_cardinality:
            dropped.append(column)
        else:
            kept_categorical.append(column)

    kept_numeric = []
    for column in numeric_columns:
        values = df[column].dropna()
        is_fully_unique = len(values) == n_rows and values.nunique() == n_rows
        is_whole_number = not values.empty and (values % 1 == 0).all()
        if is_fully_unique and is_whole_number:
            dropped.append(column)
        else:
            kept_numeric.append(column)

    return df.drop(columns=dropped), kept_numeric, kept_categorical, dropped


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
    dropped: list[str] = []

    kept_numeric = []
    for column in numeric_columns:
        std = df[column].std()
        if pd.isna(std) or std <= near_constant_std_threshold:
            dropped.append(column)
        else:
            kept_numeric.append(column)

    kept_categorical = []
    for column in categorical_columns:
        if df[column].nunique(dropna=True) <= 1:
            dropped.append(column)
        else:
            kept_categorical.append(column)

    return df.drop(columns=dropped), kept_numeric, kept_categorical, dropped


def remove_outliers_iqr(df: pd.DataFrame, numeric_columns: list[str]) -> pd.DataFrame:
    """Drops rows where any numeric column falls outside
    [Q1 - 1.5*IQR, Q3 + 1.5*IQR]. A missing value is treated as not-an-outlier
    here -- NaN-row removal is a separate, explicit step in preprocess()."""
    if not numeric_columns:
        return df
    q1 = df[numeric_columns].quantile(0.25)
    q3 = df[numeric_columns].quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    keep_mask = pd.Series(True, index=df.index)
    for column in numeric_columns:
        in_range = df[column].isna() | df[column].between(lower[column], upper[column])
        keep_mask &= in_range
    return df[keep_mask]


def scale_and_encode(
    df: pd.DataFrame, numeric_columns: list[str], categorical_columns: list[str]
) -> tuple[np.ndarray, list[str]]:
    """StandardScaler on numeric_columns + OneHotEncoder on categorical_columns,
    concatenated. Returns (encoded_matrix, output_feature_names) where
    output_feature_names maps each matrix column back to its origin
    (e.g. "income" or "region_onehot_West")."""
    n_rows = len(df)

    if numeric_columns:
        numeric_matrix = StandardScaler().fit_transform(df[numeric_columns])
        numeric_names = list(numeric_columns)
    else:
        numeric_matrix = np.empty((n_rows, 0))
        numeric_names = []

    if categorical_columns:
        encoder = OneHotEncoder(sparse_output=False)
        categorical_matrix = encoder.fit_transform(df[categorical_columns])
        categorical_names = [
            f"{column}_onehot_{category}"
            for column, categories in zip(categorical_columns, encoder.categories_)
            for category in categories
        ]
    else:
        categorical_matrix = np.empty((n_rows, 0))
        categorical_names = []

    matrix = np.hstack([numeric_matrix, categorical_matrix])
    feature_names = numeric_names + categorical_names
    return matrix, feature_names


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
    pairwise Cython loop doesn't scale past a few thousand columns."""
    n = len(feature_names)
    if n <= 1:
        # np.corrcoef returns a 0-d scalar (not a 2D array) for a single
        # column -- a failure mode pandas.DataFrame.corr() didn't have.
        return matrix, feature_names, []

    correlation = np.corrcoef(matrix, rowvar=False)
    correlation = np.nan_to_num(correlation, nan=0.0)  # defense-in-depth for any
    correlation = np.abs(correlation)                  # residual zero-variance column

    dropped_indices: set[int] = set()
    for i in range(n):
        if i in dropped_indices:
            continue
        for j in range(i + 1, n):
            if j in dropped_indices:
                continue
            if correlation[i, j] > threshold:
                dropped_indices.add(j)

    kept_indices = [k for k in range(n) if k not in dropped_indices]
    reduced_matrix = matrix[:, kept_indices]
    kept_names = [feature_names[k] for k in kept_indices]
    dropped_names = [feature_names[k] for k in sorted(dropped_indices)]
    return reduced_matrix, kept_names, dropped_names


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
    """Full pipeline entrypoint: raw CSV -> PreprocessingResult. Also writes
    feature_lineage.json to the client's segmenter artifact directory as a
    side effect. Thresholds are keyword-configurable so different clients'
    data can be tuned without code changes -- what counts as an identifier
    or a near-constant column varies with dataset shape."""
    df = read_customer_csv(csv_path)

    # identify_column_types runs on the raw df, per the blueprint's literal
    # pipeline order -- drop_high_missing_columns runs after it, so the
    # resulting lists are re-filtered against whatever actually survived.
    numeric_columns, categorical_columns = identify_column_types(df)
    df, dropped_missing = drop_high_missing_columns(df, threshold=missing_threshold)
    numeric_columns = [c for c in numeric_columns if c in df.columns]
    categorical_columns = [c for c in categorical_columns if c in df.columns]

    df, numeric_columns, categorical_columns, dropped_identifier = drop_identifier_like_columns(
        df,
        numeric_columns,
        categorical_columns,
        identifier_cardinality_ratio=identifier_cardinality_ratio,
        max_categorical_cardinality=max_categorical_cardinality,
        min_rows_for_identifier_check=min_rows_for_identifier_check,
    )

    df, numeric_columns, categorical_columns, dropped_near_constant = drop_near_constant_columns(
        df,
        numeric_columns,
        categorical_columns,
        near_constant_std_threshold=near_constant_std_threshold,
    )

    df = remove_outliers_iqr(df, numeric_columns)

    # Neither drop_high_missing_columns (only >85% missing) nor
    # remove_outliers_iqr (fences only, NaN treated as in-range) guarantees a
    # NaN-free matrix, and scikit-learn's StandardScaler/OneHotEncoder reject
    # NaN input. Sanitize by dropping rows, not imputing -- no fabricated
    # values.
    if numeric_columns:
        df[numeric_columns] = df[numeric_columns].replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=numeric_columns + categorical_columns).reset_index(drop=True)

    cleaned_df = df[numeric_columns + categorical_columns].reset_index(drop=True)

    matrix, feature_names = scale_and_encode(cleaned_df, numeric_columns, categorical_columns)
    matrix, feature_names, dropped_correlated = drop_correlated_features(
        matrix, feature_names, threshold=correlation_threshold
    )

    # Each column lands in exactly one bucket -- the rules above are
    # mutually exclusive by construction, and every step only ever sees
    # what the previous step left behind.
    dropped_columns: dict[str, str] = {}
    for name in dropped_missing:
        dropped_columns[name] = "high_missing"
    for name in dropped_identifier:
        dropped_columns[name] = "identifier_like"
    for name in dropped_near_constant:
        dropped_columns[name] = "near_constant"
    for name in dropped_correlated:
        dropped_columns[name] = "high_correlation"

    lineage_path = segmenter_artifact_path(client_id, "feature_lineage.json")
    with open(lineage_path, "w") as f:
        json.dump({"feature_names": feature_names, "dropped_columns": dropped_columns}, f)

    return PreprocessingResult(
        feature_matrix=matrix,
        cleaned_df=cleaned_df,
        feature_names=feature_names,
        dropped_columns=dropped_columns,
    )
