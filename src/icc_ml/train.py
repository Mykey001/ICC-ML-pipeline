"""
Model training with purged walk-forward cross-validation.

Key features:
- Expanding window walk-forward (not random k-fold)
- Purging: remove training trades that exit after test start
- Embargo: additional buffer to prevent serial correlation leakage
- Probability calibration (isotonic regression)
- Threshold selection on expected pips, not accuracy, using out-of-sample
  predictions from an inner walk-forward inside each training window
"""

from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import List, Optional, Tuple
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, brier_score_loss
import joblib

from .regime import REGIME_LABEL_COLS, RegimeConfig, regime_config_dict, regime_profile

# Threshold meaning "take every signal" (the model does not filter)
TAKE_ALL_THRESHOLD = 0.0

# Minimum inner out-of-sample predictions needed to choose a threshold
MIN_THRESHOLD_SAMPLES = 50


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
    threshold_source: str = "inner_oos"  # or "take_all_fallback"
    n_threshold_samples: int = 0


def get_feature_columns(df: pd.DataFrame) -> List[str]:
    """
    Extract feature column names from training DataFrame.

    Excludes trade metadata columns and text regime labels, keeps only numeric features.
    """
    exclude = {
        "signal_bar", "direction", "entry_bar", "entry_price",
        "sl_price", "tp_price", "exit_bar", "exit_price",
        "exit_reason", "gross_pips", "spread_cost_pips",
        "slippage_cost_pips", "commission_pips", "net_pips", "win",
        "time",
    } | set(REGIME_LABEL_COLS)

    return [col for col in df.columns
            if col not in exclude and pd.api.types.is_numeric_dtype(df[col])]


def _walk_forward_splits(df: pd.DataFrame, n_folds: int, embargo_bars: int):
    """
    Yield (fold_num, train_idx, test_idx) for purged expanding-window walk-forward.

    Rows (sorted by signal_bar) are split into n_folds + 1 contiguous blocks. The
    first block only ever trains; each later block is one test fold. Training rows
    are purged unless their trade exits more than embargo_bars before the test
    fold's first signal.
    """
    blocks = np.array_split(np.arange(len(df)), n_folds + 1)
    for fold, test_idx in enumerate(blocks[1:], start=1):
        if len(test_idx) == 0:
            continue
        test_start = test_idx[0]
        purge_boundary = df.loc[test_start, "signal_bar"] - embargo_bars
        train_mask = (df.index < test_start) & (df["exit_bar"] < purge_boundary)
        yield fold, df.index[train_mask].to_numpy(), test_idx


def _fit_model(X: pd.DataFrame, y: pd.Series, model_type: str, calibrate: bool, cv: int = 3):
    """
    Build and fit one model, calibrated when requested and there is enough data
    (at least 100 rows and `cv` examples of each class, which calibration CV needs).
    """
    model = build_model(model_type)
    if calibrate and len(X) >= 100 and y.value_counts().min() >= cv:
        model = CalibratedClassifierCV(model, method="isotonic", cv=cv)
    model.fit(X, y)
    return model


def _inner_oos_predictions(
    df: pd.DataFrame,
    feature_cols: List[str],
    n_inner: int,
    embargo_bars: int,
    calibrate: bool,
    model_type: str,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Out-of-sample predictions inside a training window, via a nested walk-forward.

    Returns (y_true, y_proba, net_pips) over all inner test rows.
    """
    df = df.reset_index(drop=True)
    ys, ps, pips = [], [], []
    for _, tr, te in _walk_forward_splits(df, n_inner, embargo_bars):
        if len(tr) < 30 or df.loc[tr, "win"].nunique() < 2:
            continue
        model = _fit_model(df.loc[tr, feature_cols], df.loc[tr, "win"], model_type, calibrate)
        ys.append(df.loc[te, "win"].to_numpy())
        ps.append(model.predict_proba(df.loc[te, feature_cols])[:, 1])
        pips.append(df.loc[te, "net_pips"].to_numpy())
    if not ys:
        return np.array([]), np.array([]), np.array([])
    return np.concatenate(ys), np.concatenate(ps), np.concatenate(pips)


def train_walk_forward(
    df: pd.DataFrame,
    feature_cols: List[str],
    n_folds: int = 5,
    embargo_bars: int = 50,
    calibrate: bool = True,
    model_type: str = "HistGradientBoosting",
    n_inner_folds: int = 3,
) -> Tuple[List[FoldResult], pd.DataFrame]:
    """
    Train using purged expanding-window walk-forward CV.

    Each fold's threshold is chosen on out-of-sample predictions from an inner
    walk-forward over that fold's training rows only, never on in-sample
    predictions and never on the test fold.

    Args:
        df: Training matrix (trades + features + labels)
        feature_cols: List of feature column names
        n_folds: Number of test folds (data is split into n_folds + 1 blocks)
        embargo_bars: Embargo period (bars) after train/test boundary
        calibrate: Whether to calibrate probabilities
        model_type: Model to use
        n_inner_folds: Inner walk-forward folds used for threshold selection

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
    fold_size = n // (n_folds + 1)

    if fold_size < 50:
        warnings.warn(
            f"Fold size {fold_size} is very small. Results may be unreliable. "
            f"Consider reducing n_folds or extending history.",
            UserWarning
        )

    carry_cols = [c for c in REGIME_LABEL_COLS + ["regime_alignment"] if c in df.columns]
    fold_results = []
    oos_predictions = []

    for fold, train_indices, test_indices in _walk_forward_splits(df, n_folds, embargo_bars):
        if len(train_indices) < 30:
            warnings.warn(
                f"Fold {fold}: Only {len(train_indices)} training samples after purging. "
                f"Skipping fold.",
                UserWarning
            )
            continue

        # Extract train/test sets
        X_train = df.loc[train_indices, feature_cols]
        y_train = df.loc[train_indices, "win"]

        X_test = df.loc[test_indices, feature_cols]
        y_test = df.loc[test_indices, "win"]
        pips_test = df.loc[test_indices, "net_pips"]

        model = _fit_model(X_train, y_train, model_type, calibrate)

        # Predict on test set
        y_pred_proba = model.predict_proba(X_test)[:, 1]

        # Metrics (AUC is undefined when the test fold has a single class)
        auc = roc_auc_score(y_test, y_pred_proba) if y_test.nunique() == 2 else np.nan
        brier = brier_score_loss(y_test, y_pred_proba)

        # Select threshold on inner out-of-sample predictions from the training rows
        inner_y, inner_p, inner_pips = _inner_oos_predictions(
            df.loc[train_indices], feature_cols, n_inner_folds, embargo_bars, calibrate, model_type
        )
        if len(inner_y) >= MIN_THRESHOLD_SAMPLES:
            threshold = select_threshold_on_pips(inner_y, inner_p, inner_pips)
            threshold_source = "inner_oos"
        else:
            threshold = TAKE_ALL_THRESHOLD
            threshold_source = "take_all_fallback"

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
            fold_num=fold,
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
            threshold_source=threshold_source,
            n_threshold_samples=len(inner_y),
        ))

        # Store OOS predictions
        for idx, test_idx in enumerate(test_indices):
            row = {
                "signal_bar": df.loc[test_idx, "signal_bar"],
                "fold": fold,
                "y_true": y_test.iloc[idx],
                "y_pred_proba": y_pred_proba[idx],
                "y_pred": y_pred[idx],
                "net_pips": pips_test.iloc[idx],
                "direction": df.loc[test_idx, "direction"],
            }
            for c in carry_cols:
                row[c] = df.loc[test_idx, c]
            oos_predictions.append(row)
    
    oos_df = pd.DataFrame(oos_predictions)
    
    return fold_results, oos_df


def build_model(model_type: str):
    """
    Build sklearn classifier.
    
    Supported types:
    - HistGradientBoosting (default, handles missing values)
    - HistGradientBoostingRegularized (shallower, more regularised)
    - RandomForest
    - LogisticRegression (median imputation + standardisation, L2 C=0.1)
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
    
    elif model_type == "HistGradientBoostingRegularized":
        # Shallower trees, slower learning and larger leaves: for small trade samples
        return HistGradientBoostingClassifier(
            max_iter=200,
            learning_rate=0.05,
            max_depth=3,
            min_samples_leaf=40,
            l2_regularization=1.0,
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
        # Features have very different scales; impute any NaN and standardise first
        return make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(C=0.1, max_iter=2000, random_state=42),
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
    total pips, subject to minimum trade count constraint. Only predictions the
    model was not trained on should be passed in.

    Args:
        y_true: True labels
        y_proba: Predicted probabilities
        pips: Net pips per trade
        min_trades: Minimum trades required for threshold to be valid

    Returns:
        Optimal threshold, or TAKE_ALL_THRESHOLD if no threshold beats taking every signal
    """
    y_proba = np.asarray(y_proba)
    pips = np.asarray(pips)
    thresholds = np.arange(0.1, 0.91, 0.05)
    best_threshold = TAKE_ALL_THRESHOLD
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
        "mean_auc": np.nanmean(aucs),
        "std_auc": np.nanstd(aucs),
        "mean_brier": np.mean(briers),
        "total_edge_pips": sum(edges),
        "mean_edge_per_fold": np.mean(edges),
        "folds_with_positive_edge": sum(1 for e in edges if e > 0),
        "per_fold": [
            {
                "fold": f.fold_num,
                "n_train": f.train_size,
                "n_test": f.test_size,
                "auc": f.auc,
                "brier": f.brier,
                "threshold": f.threshold,
                "threshold_source": f.threshold_source,
                "edge_pips": f.edge_pips,
                "n_taken": f.n_taken,
                "win_rate": f.win_rate_if_taken,
            }
            for f in fold_results
        ],
    }


def select_deployment_threshold(oos: pd.DataFrame, min_trades: int = 30) -> float:
    """
    Threshold for the final model, chosen on the pooled walk-forward OOS predictions.

    Every prediction used comes from a model that never saw that trade. The
    walk-forward edge figures do not use this threshold, so they stay unbiased.
    Returns TAKE_ALL_THRESHOLD if no threshold beats taking every signal.
    """
    if len(oos) == 0:
        return TAKE_ALL_THRESHOLD
    return select_threshold_on_pips(oos["y_true"], oos["y_pred_proba"], oos["net_pips"], min_trades)


def fit_final_model(
    df: pd.DataFrame,
    feature_cols: List[str],
    threshold: float,
    model_type: str = "HistGradientBoosting",
    calibrate: bool = True,
    out_path: Optional[str] = None,
    pip: Optional[float] = None,
    regime_cfg: Optional[RegimeConfig] = None,
    strategy_cfg=None,
) -> dict:
    """
    Fit final model on ALL available data for deployment.

    Use the threshold from walk-forward CV (see select_deployment_threshold);
    don't recompute it on the model's own training data.

    If the training matrix carries regime labels, the bundle also stores the
    per-regime profile and regime configuration so live decisions can report
    the current regime and its historical behaviour.

    Args:
        df: Full training matrix
        feature_cols: Feature column names
        threshold: Threshold from CV
        model_type: Model type
        calibrate: Whether to calibrate
        out_path: Path to save model (optional)
        pip: Pip size, for the regime profile's SL distance column
        regime_cfg: Regime configuration used to build the regime columns
        strategy_cfg: StrategyConfig the training trades came from; stored so the
            model is only ever run behind the same strategy settings

    Returns:
        Dict with model bundle metadata
    """
    model = _fit_model(df[feature_cols], df["win"], model_type, calibrate, cv=5)

    bundle = {
        "model": model,
        "feature_cols": feature_cols,
        "threshold": threshold,
        "n_training_trades": len(df),
        "model_type": model_type,
    }

    if "regime" in df.columns:
        bundle["regime_config"] = regime_config_dict(regime_cfg or RegimeConfig())

    if strategy_cfg is not None:
        bundle["strategy_config"] = asdict(strategy_cfg)
        bundle["regime_profile"] = regime_profile(df, pip=pip)

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
