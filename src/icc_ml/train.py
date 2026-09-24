"""
Model training with purged walk-forward cross-validation.

Key features:
- Expanding window walk-forward (not random k-fold)
- Purging: remove training trades that exit after test start
- Embargo: additional buffer to prevent serial correlation leakage
- Probability calibration (isotonic regression)
- Threshold selection on expected pips, not accuracy
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Tuple
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_auc_score, brier_score_loss
import joblib


@dataclass
class FoldResult:
    """Results from one walk-forward fold."""
    fold_num: int
    train_size: int
    test_size: int
    auc: float
    brier: float
    threshold: float
    baseline_net_pips: float
    model_net_pips: float
    edge_pips: float
    n_taken: int
    win_rate_if_taken: float


def get_feature_columns(df: pd.DataFrame) -> List[str]:
    """
    Extract feature column names from training DataFrame.
    
    Excludes trade metadata columns, keeps only actual features.
    """
    exclude = {
        "signal_bar", "direction", "entry_bar", "entry_price",
        "sl_price", "tp_price", "exit_bar", "exit_price",
        "exit_reason", "gross_pips", "spread_cost_pips",
        "slippage_cost_pips", "commission_pips", "net_pips", "win",
        "time",
    }
    
    return [col for col in df.columns if col not in exclude]


def train_walk_forward(
    df: pd.DataFrame,
    feature_cols: List[str],
    n_folds: int = 5,
    embargo_bars: int = 50,
    calibrate: bool = True,
    model_type: str = "HistGradientBoosting",
) -> Tuple[List[FoldResult], pd.DataFrame]:
    """
    Train using purged expanding-window walk-forward CV.
    
    Args:
        df: Training matrix (trades + features + labels)
        feature_cols: List of feature column names
        n_folds: Number of walk-forward folds
        embargo_bars: Embargo period (bars) after train/test boundary
        calibrate: Whether to calibrate probabilities
        model_type: Model to use
    
    Returns:
        (fold_results, oos_predictions)
        - fold_results: List of FoldResult objects
        - oos_predictions: DataFrame with out-of-sample predictions for all trades
    """
    if "win" not in df.columns:
        raise ValueError("DataFrame must have 'win' column (the label)")
    
    if "net_pips" not in df.columns:
        raise ValueError("DataFrame must have 'net_pips' column for threshold selection")
    
    if "exit_bar" not in df.columns:
        raise ValueError("DataFrame must have 'exit_bar' column for purging")
    
    # Sort by signal bar (chronological)
    df = df.sort_values("signal_bar").reset_index(drop=True)
    
    n = len(df)
    fold_size = n // n_folds
    
    if fold_size < 50:
        warnings.warn(
            f"Fold size {fold_size} is very small. Results may be unreliable. "
            f"Consider reducing n_folds or extending history.",
            UserWarning
        )
    
    fold_results = []
    oos_predictions = []
    
    for fold in range(n_folds):
        # Test window for this fold
        test_start_idx = (fold + 1) * fold_size
        if fold == n_folds - 1:
            test_end_idx = n  # Last fold takes remainder
        else:
            test_end_idx = (fold + 2) * fold_size
        
        if test_start_idx >= n:
            break
        
        test_indices = range(test_start_idx, min(test_end_idx, n))
        test_start_bar = df.loc[test_start_idx, "signal_bar"]
        
        # Train: all data before test window
        # Apply purging: remove trades that exit after (test_start_bar - embargo_bars)
        purge_boundary = test_start_bar - embargo_bars
        train_mask = (df.index < test_start_idx) & (df["exit_bar"] < purge_boundary)
        train_indices = df[train_mask].index.tolist()
        
        if len(train_indices) < 30:
            warnings.warn(
                f"Fold {fold+1}: Only {len(train_indices)} training samples after purging. "
                f"Skipping fold.",
                UserWarning
            )
            continue
        
        # Extract train/test sets
        X_train = df.loc[train_indices, feature_cols]
        y_train = df.loc[train_indices, "win"]
        pips_train = df.loc[train_indices, "net_pips"]
        
        X_test = df.loc[test_indices, feature_cols]
        y_test = df.loc[test_indices, "win"]
        pips_test = df.loc[test_indices, "net_pips"]
        
        # Build and train model
        model = build_model(model_type)
        
        # Calibrate if requested and enough samples
        if calibrate and len(train_indices) >= 100:
            model = CalibratedClassifierCV(model, method="isotonic", cv=3)
        
        model.fit(X_train, y_train)
        
        # Predict on test set
        y_pred_proba = model.predict_proba(X_test)[:, 1]
        
        # Metrics
        auc = roc_auc_score(y_test, y_pred_proba)
        brier = brier_score_loss(y_test, y_pred_proba)
        
        # Select threshold on TRAINING set (to prevent leakage)
        threshold = select_threshold_on_pips(
            y_train, model.predict_proba(X_train)[:, 1], pips_train
        )
        
        # Apply threshold to test set
        y_pred = (y_pred_proba >= threshold).astype(int)
        
        # Baseline: take all signals
        baseline_net_pips = pips_test.sum()
        
        # Model-filtered: take only where y_pred == 1
        taken_mask = y_pred == 1
        model_net_pips = pips_test[taken_mask].sum() if taken_mask.any() else 0.0
        n_taken = taken_mask.sum()
        win_rate_if_taken = y_test[taken_mask].mean() if taken_mask.any() else 0.0
        
        edge_pips = model_net_pips - baseline_net_pips
        
        # Store fold result
        fold_results.append(FoldResult(
            fold_num=fold + 1,
            train_size=len(train_indices),
            test_size=len(test_indices),
            auc=auc,
            brier=brier,
            threshold=threshold,
            baseline_net_pips=baseline_net_pips,
            model_net_pips=model_net_pips,
            edge_pips=edge_pips,
            n_taken=n_taken,
            win_rate_if_taken=win_rate_if_taken,
        ))
        
        # Store OOS predictions
        for idx, test_idx in enumerate(test_indices):
            oos_predictions.append({
                "signal_bar": df.loc[test_idx, "signal_bar"],
                "fold": fold + 1,
                "y_true": y_test.iloc[idx],
                "y_pred_proba": y_pred_proba[idx],
                "y_pred": y_pred[idx],
                "net_pips": pips_test.iloc[idx],
                "direction": df.loc[test_idx, "direction"],
            })
    
    oos_df = pd.DataFrame(oos_predictions)
    
    return fold_results, oos_df


def build_model(model_type: str):
    """
    Build sklearn classifier.
    
    Supported types:
    - HistGradientBoosting (default, handles missing values)
    - RandomForest
    - LogisticRegression
    - LightGBM (if installed)
    - XGBoost (if installed)
    """
    if model_type == "HistGradientBoosting":
        return HistGradientBoostingClassifier(
            max_iter=100,
            learning_rate=0.1,
            max_depth=5,
            random_state=42,
        )
    
    elif model_type == "RandomForest":
        return RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=20,
            random_state=42,
        )
    
    elif model_type == "LogisticRegression":
        return LogisticRegression(
            max_iter=1000,
            random_state=42,
        )
    
    elif model_type == "LightGBM":
        try:
            import lightgbm as lgb
            return lgb.LGBMClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42,
            )
        except ImportError:
            warnings.warn("LightGBM not installed. Falling back to HistGradientBoosting.", UserWarning)
            return build_model("HistGradientBoosting")
    
    elif model_type == "XGBoost":
        try:
            import xgboost as xgb
            return xgb.XGBClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42,
            )
        except ImportError:
            warnings.warn("XGBoost not installed. Falling back to HistGradientBoosting.", UserWarning)
            return build_model("HistGradientBoosting")
    
    else:
        raise ValueError(f"Unknown model_type: {model_type}")


def select_threshold_on_pips(
    y_true: pd.Series,
    y_proba: np.ndarray,
    pips: pd.Series,
    min_trades: int = 10,
) -> float:
    """
    Select probability threshold that maximizes net pips.
    
    Sweeps thresholds from 0.1 to 0.9 and picks the one with highest
    total pips, subject to minimum trade count constraint.
    
    Args:
        y_true: True labels
        y_proba: Predicted probabilities
        pips: Net pips per trade
        min_trades: Minimum trades required for threshold to be valid
    
    Returns:
        Optimal threshold
    """
    thresholds = np.arange(0.1, 0.91, 0.05)
    best_threshold = 0.5
    best_pips = pips.sum()  # Baseline (take all)
    
    for thresh in thresholds:
        mask = y_proba >= thresh
        if mask.sum() < min_trades:
            continue  # Not enough trades
        
        total_pips = pips[mask].sum()
        
        if total_pips > best_pips:
            best_pips = total_pips
            best_threshold = thresh
    
    return best_threshold


def summarize_folds(fold_results: List[FoldResult]) -> dict:
    """
    Aggregate fold results into summary statistics.
    
    Returns dict with mean metrics and per-fold breakdown.
    """
    if len(fold_results) == 0:
        return {"error": "No fold results to summarize"}
    
    aucs = [f.auc for f in fold_results]
    briers = [f.brier for f in fold_results]
    edges = [f.edge_pips for f in fold_results]
    
    return {
        "n_folds": len(fold_results),
        "mean_auc": np.mean(aucs),
        "std_auc": np.std(aucs),
        "mean_brier": np.mean(briers),
        "total_edge_pips": sum(edges),
        "mean_edge_per_fold": np.mean(edges),
        "folds_with_positive_edge": sum(1 for e in edges if e > 0),
        "per_fold": [
            {
                "fold": f.fold_num,
                "auc": f.auc,
                "brier": f.brier,
                "edge_pips": f.edge_pips,
                "n_taken": f.n_taken,
                "win_rate": f.win_rate_if_taken,
            }
            for f in fold_results
        ],
    }


def fit_final_model(
    df: pd.DataFrame,
    feature_cols: List[str],
    threshold: float,
    model_type: str = "HistGradientBoosting",
    calibrate: bool = True,
    out_path: Optional[str] = None,
) -> dict:
    """
    Fit final model on ALL available data for deployment.
    
    Use the threshold from walk-forward CV (don't recompute on full data).
    
    Args:
        df: Full training matrix
        feature_cols: Feature column names
        threshold: Threshold from CV
        model_type: Model type
        calibrate: Whether to calibrate
        out_path: Path to save model (optional)
    
    Returns:
        Dict with model bundle metadata
    """
    X = df[feature_cols]
    y = df["win"]
    
    model = build_model(model_type)
    
    if calibrate and len(df) >= 100:
        model = CalibratedClassifierCV(model, method="isotonic", cv=5)
    
    model.fit(X, y)
    
    bundle = {
        "model": model,
        "feature_cols": feature_cols,
        "threshold": threshold,
        "n_training_trades": len(df),
        "model_type": model_type,
    }
    
    if out_path is not None:
        joblib.dump(bundle, out_path)
        print(f"Model saved to {out_path}")
    
    return bundle


def load_model(path: str) -> dict:
    """
    Load a saved model bundle.
    
    Returns dict with model, feature_cols, threshold.
    """
    return joblib.load(path)
