"""
Feature validation tools.

- Information Coefficient (IC): Spearman correlation with label
- IC stability: Rolling IC to detect regime-dependent features
- Redundancy clustering: Group highly correlated features
"""

from __future__ import annotations
from typing import List, Optional
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform


def compute_ic(X: pd.DataFrame, y: pd.Series) -> pd.Series:
    """
    Compute Information Coefficient for each feature.
    
    IC = Spearman rank correlation between feature and label.
    
    Args:
        X: Feature matrix
        y: Binary label (win/loss)
    
    Returns:
        Series with IC for each feature, sorted by absolute value
    """
    ics = {}
    
    for col in X.columns:
        feature = X[col].values
        
        # Skip if all NaN or constant
        if np.isnan(feature).all() or np.std(feature) == 0:
            ics[col] = np.nan
            continue
        
        # Remove NaN pairs
        mask = ~(np.isnan(feature) | np.isnan(y.values))
        if mask.sum() < 10:
            ics[col] = np.nan
            continue
        
        # Spearman correlation
        try:
            corr, _ = spearmanr(feature[mask], y.values[mask])
            ics[col] = corr
        except:
            ics[col] = np.nan
    
    ic_series = pd.Series(ics).sort_values(key=abs, ascending=False)
    
    return ic_series


def rolling_ic_stability(
    X: pd.DataFrame,
    y: pd.Series,
    window: int = 200,
    step: int = 50,
) -> pd.DataFrame:
    """
    Compute rolling IC to assess feature stability across regimes.
    
    A feature whose IC flips sign often is regime-dependent, not universally predictive.
    
    Args:
        X: Feature matrix
        y: Binary label
        window: Rolling window size (number of samples)
        step: Step size between windows
    
    Returns:
        DataFrame with columns:
        - feature: Feature name
        - ic_mean: Mean IC across windows
        - ic_std: Std of IC across windows
        - ic_sign_changes: Number of times IC crosses zero
        - stability_score: ic_mean / (ic_std + eps) — higher is more stable
    """
    results = []
    
    for col in X.columns:
        feature = X[col].values
        
        if np.isnan(feature).all() or np.std(feature) == 0:
            continue
        
        ics_over_time = []
        
        for start in range(0, len(X) - window + 1, step):
            end = start + window
            
            feat_window = feature[start:end]
            y_window = y.iloc[start:end].values
            
            # Remove NaN pairs
            mask = ~(np.isnan(feat_window) | np.isnan(y_window))
            if mask.sum() < 20:
                continue
            
            try:
                corr, _ = spearmanr(feat_window[mask], y_window[mask])
                ics_over_time.append(corr)
            except:
                continue
        
        if len(ics_over_time) < 2:
            continue
        
        ic_array = np.array(ics_over_time)
        
        # Count sign changes
        sign_changes = np.sum(np.diff(np.sign(ic_array)) != 0)
        
        # Stability score: mean IC divided by variability
        ic_mean = np.mean(ic_array)
        ic_std = np.std(ic_array)
        stability = ic_mean / (ic_std + 1e-6)
        
        results.append({
            "feature": col,
            "ic_mean": ic_mean,
            "ic_std": ic_std,
            "ic_sign_changes": sign_changes,
            "stability_score": stability,
        })
    
    return pd.DataFrame(results).sort_values("stability_score", ascending=False, key=abs)


def redundancy_clusters(
    X: pd.DataFrame,
    corr_threshold: float = 0.9,
) -> List[List[str]]:
    """
    Group features into redundancy clusters based on correlation.
    
    Features within a cluster are highly correlated (>threshold).
    Keep the highest-IC member of each cluster, discard the rest.
    
    Args:
        X: Feature matrix
        corr_threshold: Correlation threshold for clustering
    
    Returns:
        List of clusters, where each cluster is a list of feature names
    """
    # Compute pairwise Spearman correlation
    corr_matrix = X.corr(method="spearman").abs()
    
    # Convert to distance matrix (1 - correlation)
    dist_matrix = 1 - corr_matrix
    
    # Handle NaNs (features with no variance)
    dist_matrix = dist_matrix.fillna(1.0)
    
    # Ensure diagonal is zero
    np.fill_diagonal(dist_matrix.values, 0)
    
    # Hierarchical clustering
    condensed = squareform(dist_matrix.values)
    linkage_matrix = linkage(condensed, method="average")
    
    # Cut dendrogram at distance = 1 - corr_threshold
    distance_threshold = 1 - corr_threshold
    cluster_labels = fcluster(linkage_matrix, distance_threshold, criterion="distance")
    
    # Group features by cluster
    clusters_dict = {}
    for feature, label in zip(X.columns, cluster_labels):
        if label not in clusters_dict:
            clusters_dict[label] = []
        clusters_dict[label].append(feature)
    
    # Return clusters (filter out singletons if desired)
    clusters = [features for features in clusters_dict.values() if len(features) > 1]
    
    return clusters


def select_best_from_clusters(
    clusters: List[List[str]],
    ic: pd.Series,
) -> List[str]:
    """
    Select the highest-IC feature from each cluster.
    
    Args:
        clusters: List of feature clusters from redundancy_clusters()
        ic: IC series from compute_ic()
    
    Returns:
        List of selected feature names (one per cluster)
    """
    selected = []
    
    for cluster in clusters:
        # Get IC for each feature in cluster
        cluster_ics = {feat: abs(ic.get(feat, 0)) for feat in cluster}
        
        # Select best
        best_feat = max(cluster_ics, key=cluster_ics.get)
        selected.append(best_feat)
    
    return selected


def feature_importance_from_model(
    model,
    feature_cols: List[str],
    top_n: Optional[int] = 30,
) -> pd.DataFrame:
    """
    Extract feature importance from trained model.
    
    Args:
        model: Trained sklearn model with feature_importances_ attribute
        feature_cols: List of feature names
        top_n: Return only top N features (None = all)
    
    Returns:
        DataFrame with columns: feature, importance
    """
    # Try to get feature importances
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
    elif hasattr(model, "base_estimator") and hasattr(model.base_estimator, "feature_importances_"):
        # Calibrated classifier wraps the base estimator
        importances = model.base_estimator.feature_importances_
    elif hasattr(model, "calibrated_classifiers_"):
        # CalibratedClassifierCV stores list of calibrated classifiers
        # Take the first one
        importances = model.calibrated_classifiers_[0].base_estimator.feature_importances_
    else:
        raise ValueError("Model does not have feature_importances_ attribute")
    
    df = pd.DataFrame({
        "feature": feature_cols,
        "importance": importances,
    }).sort_values("importance", ascending=False)
    
    if top_n is not None:
        df = df.head(top_n)
    
    return df


def check_feature_leakage(
    X: pd.DataFrame,
    y: pd.Series,
    leakage_threshold: float = 0.95,
) -> pd.DataFrame:
    """
    Check for suspiciously high IC that might indicate leakage.
    
    A feature with |IC| > 0.95 is almost perfectly correlated with the label,
    which usually indicates lookahead bias or label contamination.
    
    Args:
        X: Feature matrix
        y: Binary label
        leakage_threshold: IC threshold above which we flag as suspicious
    
    Returns:
        DataFrame with suspected leakage features
    """
    ic = compute_ic(X, y)
    
    suspicious = ic[ic.abs() > leakage_threshold]
    
    if len(suspicious) > 0:
        print(f"⚠️  WARNING: {len(suspicious)} features have |IC| > {leakage_threshold}")
        print("This is suspicious and may indicate leakage:")
        print(suspicious)
    
    return suspicious.to_frame("IC")


def compare_train_test_distributions(
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    feature_cols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Compare feature distributions between train and test sets.
    
    Large distribution shifts can cause train/test performance divergence.
    
    Args:
        X_train: Training features
        X_test: Test features
        feature_cols: Features to compare (None = all)
    
    Returns:
        DataFrame with columns:
        - feature: Feature name
        - train_mean: Mean in training set
        - test_mean: Mean in test set
        - train_std: Std in training set
        - test_std: Std in test set
        - mean_shift: Relative difference in means
    """
    if feature_cols is None:
        feature_cols = X_train.columns.tolist()
    
    results = []
    
    for col in feature_cols:
        if col not in X_train.columns or col not in X_test.columns:
            continue
        
        train_vals = X_train[col].dropna()
        test_vals = X_test[col].dropna()
        
        if len(train_vals) == 0 or len(test_vals) == 0:
            continue
        
        train_mean = train_vals.mean()
        test_mean = test_vals.mean()
        train_std = train_vals.std()
        test_std = test_vals.std()
        
        # Relative shift
        mean_shift = abs(test_mean - train_mean) / (abs(train_mean) + 1e-9)
        
        results.append({
            "feature": col,
            "train_mean": train_mean,
            "test_mean": test_mean,
            "train_std": train_std,
            "test_std": test_std,
            "mean_shift": mean_shift,
        })
    
    return pd.DataFrame(results).sort_values("mean_shift", ascending=False)
