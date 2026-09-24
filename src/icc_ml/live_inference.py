"""
Live inference - score the latest closed bar in production.

This module provides the interface between the trained model and live trading.
"""

from __future__ import annotations
from typing import Tuple, Optional
import warnings

import pandas as pd
import numpy as np

from .config import StrategyConfig, SymbolSpec
from .indicators import compute_all_indicators
from .features import build_all_features
from .strategy_icc import generate_icc_signals
from .train import load_model


def score_latest_signal(
    df: pd.DataFrame,
    model_bundle: dict,
    cfg: StrategyConfig,
    spec: SymbolSpec,
) -> Optional[dict]:
    """
    Score the most recent ICC signal (if any).
    
    This is the function you call in a live trading loop:
    1. Fetch latest OHLCV data
    2. Check if ICC generated a signal on the last closed bar
    3. If yes, score it with the model → TAKE or SKIP
    
    Args:
        df: OHLCV DataFrame (must include sufficient history for indicators)
        model_bundle: Loaded model bundle from train.load_model()
        cfg: Strategy configuration
        spec: Symbol specification
    
    Returns:
        Dict with decision if signal exists, None otherwise:
        {
            "signal_bar": int,
            "direction": 1 or -1,
            "sl_price": float,
            "tp_price": float,
            "probability": float (model's win probability),
            "decision": "TAKE" or "SKIP",
            "timestamp": datetime,
        }
    """
    # Validate model bundle
    if "model" not in model_bundle or "feature_cols" not in model_bundle:
        raise ValueError("Invalid model bundle. Must contain 'model' and 'feature_cols'.")
    
    model = model_bundle["model"]
    feature_cols = model_bundle["feature_cols"]
    threshold = model_bundle.get("threshold", 0.5)
    
    # Compute indicators and features
    df_with_indicators = compute_all_indicators(df)
    df_with_features = build_all_features(df_with_indicators)
    
    # Generate ICC signals
    signals = generate_icc_signals(df, cfg, spec)
    
    # Check if the LAST bar has a signal
    last_idx = len(df) - 1
    if signals.loc[last_idx, "signal"] == 0:
        return None  # No signal on last bar
    
    # Extract signal details
    signal_row = signals.loc[last_idx]
    direction = int(signal_row["signal"])
    sl_price = signal_row["sl_price"]
    tp_price = signal_row["tp_price"]
    
    # Extract features for this signal
    try:
        features = df_with_features.loc[last_idx, feature_cols].values.reshape(1, -1)
    except KeyError as e:
        raise ValueError(f"Feature columns mismatch. Missing: {e}")
    
    # Check for NaNs in features
    if np.isnan(features).any():
        warnings.warn(
            f"Features contain NaN values. Model may produce unreliable predictions. "
            f"This usually means insufficient history for indicator calculation.",
            UserWarning
        )
    
    # Predict
    probability = model.predict_proba(features)[0, 1]
    
    # Decision
    decision = "TAKE" if probability >= threshold else "SKIP"
    
    return {
        "signal_bar": last_idx,
        "direction": direction,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "probability": float(probability),
        "decision": decision,
        "threshold": threshold,
        "timestamp": df.loc[last_idx, "time"] if "time" in df.columns else None,
    }


def batch_score_signals(
    df: pd.DataFrame,
    model_bundle: dict,
    cfg: StrategyConfig,
    spec: SymbolSpec,
) -> pd.DataFrame:
    """
    Score all ICC signals in a DataFrame (backtesting or batch processing).
    
    Args:
        df: OHLCV DataFrame
        model_bundle: Loaded model bundle
        cfg: Strategy configuration
        spec: Symbol specification
    
    Returns:
        DataFrame with columns:
        - signal_bar: Bar index
        - direction: 1 or -1
        - sl_price, tp_price: Trade parameters
        - probability: Model's predicted win probability
        - decision: "TAKE" or "SKIP"
    """
    model = model_bundle["model"]
    feature_cols = model_bundle["feature_cols"]
    threshold = model_bundle.get("threshold", 0.5)
    
    # Compute features
    df_with_indicators = compute_all_indicators(df)
    df_with_features = build_all_features(df_with_indicators)
    
    # Generate signals
    signals = generate_icc_signals(df, cfg, spec)
    
    # Filter to actual signals
    signal_bars = signals[signals["signal"] != 0].index.tolist()
    
    if len(signal_bars) == 0:
        return pd.DataFrame(columns=[
            "signal_bar", "direction", "sl_price", "tp_price",
            "probability", "decision"
        ])
    
    results = []
    
    for idx in signal_bars:
        signal_row = signals.loc[idx]
        
        # Extract features
        try:
            features = df_with_features.loc[idx, feature_cols].values.reshape(1, -1)
        except KeyError:
            warnings.warn(f"Feature mismatch at bar {idx}. Skipping.", UserWarning)
            continue
        
        # Skip if features have NaNs
        if np.isnan(features).any():
            continue
        
        # Predict
        probability = model.predict_proba(features)[0, 1]
        decision = "TAKE" if probability >= threshold else "SKIP"
        
        results.append({
            "signal_bar": idx,
            "direction": int(signal_row["signal"]),
            "sl_price": signal_row["sl_price"],
            "tp_price": signal_row["tp_price"],
            "probability": float(probability),
            "decision": decision,
        })
    
    return pd.DataFrame(results)


def live_trading_checklist(
    df: pd.DataFrame,
    model_bundle: dict,
    cfg: StrategyConfig,
    spec: SymbolSpec,
) -> dict:
    """
    Pre-deployment checklist for live trading readiness.
    
    Verifies:
    - Model can score recent data
    - Features compute without NaN issues
    - ICC signals generate correctly
    - All components match expected interfaces
    
    Args:
        df: Recent OHLCV data (last ~2000 bars)
        model_bundle: Loaded model bundle
        cfg: Strategy configuration
        spec: Symbol specification
    
    Returns:
        Dict with boolean checks and diagnostics
    """
    checks = {}
    
    # 1. Data quality
    if len(df) < 1500:
        checks["sufficient_history"] = False
        checks["history_bars"] = len(df)
    else:
        checks["sufficient_history"] = True
        checks["history_bars"] = len(df)
    
    # 2. Indicators compute
    try:
        df_ind = compute_all_indicators(df)
        checks["indicators_compute"] = True
        checks["n_indicator_cols"] = len([c for c in df_ind.columns if c not in df.columns])
    except Exception as e:
        checks["indicators_compute"] = False
        checks["indicator_error"] = str(e)
    
    # 3. Features compute
    try:
        df_feat = build_all_features(df_ind)
        checks["features_compute"] = True
        checks["n_feature_cols"] = len([c for c in df_feat.columns if c not in df.columns])
        
        # Check for excessive NaNs
        feature_cols = [c for c in df_feat.columns if c not in ["time"]]
        nan_pct = df_feat[feature_cols].isna().mean().mean()
        checks["feature_nan_pct"] = nan_pct
        checks["acceptable_nan_rate"] = nan_pct < 0.1
    except Exception as e:
        checks["features_compute"] = False
        checks["feature_error"] = str(e)
    
    # 4. ICC signals generate
    try:
        signals = generate_icc_signals(df, cfg, spec)
        n_signals = (signals["signal"] != 0).sum()
        checks["icc_signals_generate"] = True
        checks["n_signals_in_data"] = n_signals
    except Exception as e:
        checks["icc_signals_generate"] = False
        checks["icc_error"] = str(e)
    
    # 5. Model can score
    try:
        model = model_bundle["model"]
        feature_cols = model_bundle["feature_cols"]
        
        # Try to extract features for last bar
        features = df_feat.loc[len(df)-1, feature_cols].values.reshape(1, -1)
        
        # Try to predict
        proba = model.predict_proba(features)[0, 1]
        
        checks["model_can_score"] = True
        checks["test_probability"] = float(proba)
    except Exception as e:
        checks["model_can_score"] = False
        checks["model_error"] = str(e)
    
    # 6. Feature columns match
    try:
        model_features = set(model_bundle["feature_cols"])
        available_features = set(df_feat.columns)
        missing = model_features - available_features
        
        if len(missing) == 0:
            checks["feature_cols_match"] = True
        else:
            checks["feature_cols_match"] = False
            checks["missing_features"] = list(missing)
    except:
        checks["feature_cols_match"] = None
    
    # Summary
    critical_checks = [
        checks.get("sufficient_history", False),
        checks.get("indicators_compute", False),
        checks.get("features_compute", False),
        checks.get("icc_signals_generate", False),
        checks.get("model_can_score", False),
        checks.get("feature_cols_match", False),
    ]
    
    checks["all_passed"] = all(critical_checks)
    checks["failed_checks"] = [
        k for k, v in checks.items()
        if isinstance(v, bool) and not v
        and k in ["sufficient_history", "indicators_compute", "features_compute",
                  "icc_signals_generate", "model_can_score", "feature_cols_match"]
    ]
    
    return checks


def format_trading_decision(decision: dict) -> str:
    """
    Format a trading decision for logging or display.
    
    Args:
        decision: Output from score_latest_signal()
    
    Returns:
        Formatted string
    """
    if decision is None:
        return "No signal"
    
    direction_str = "LONG" if decision["direction"] == 1 else "SHORT"
    timestamp_str = decision["timestamp"].strftime("%Y-%m-%d %H:%M") if decision["timestamp"] else "N/A"
    
    return (
        f"[{timestamp_str}] {decision['decision']}: {direction_str} @ bar {decision['signal_bar']} | "
        f"Probability: {decision['probability']:.3f} (threshold: {decision['threshold']:.3f}) | "
        f"SL: {decision['sl_price']:.5f}, TP: {decision['tp_price']:.5f}"
    )
