"""
Step 3: train the meta-model on the selected strategy (PROTOCOL.md, "Meta-model").

- Labels: independent (non-sequential) signals of the selected configuration,
  development period only.
- Features: engineered features minus raw price levels and history-dependent
  cumulative series (obv, vwap), plus regime features.
- Up to three model variants compared by purged walk-forward edge; the deployment
  threshold comes from the pooled walk-forward OOS predictions.
- The final model is fit on all development trades and saved to
  models/model_icc_meta_v2.joblib.

Writes research/results/meta_model.json. Holdout bars are never used for training.
"""

from __future__ import annotations
import json
import warnings

import numpy as np
import pandas as pd

from common import ROOT, RESULTS, SPEC, EXEC, HOLDOUT_START, load_data, to_config
from icc_ml.indicators import compute_all_indicators
from icc_ml.features import build_all_features
from icc_ml.strategy_icc import generate_icc_signals
from icc_ml.icc_labeling import simulate_icc_trades, attach_features_to_trades
from icc_ml.regime import compute_regimes, attach_regimes_to_trades, regime_oos_report
from icc_ml.train import (get_feature_columns, train_walk_forward, summarize_folds,
                          select_deployment_threshold, fit_final_model)

warnings.filterwarnings("ignore")

VARIANTS = ["HistGradientBoosting", "HistGradientBoostingRegularized", "LogisticRegression"]

# Raw price levels (non-stationary) and history-dependent cumulative series
EXCLUDED_FEATURES = (
    {"open", "high", "low", "close", "supertrend", "bb_upper", "bb_middle", "bb_lower",
     "kc_upper", "kc_middle", "kc_lower", "swing_high", "swing_low", "structure_midpoint",
     "obv", "vwap", "volume_sma_20", "macd", "macd_signal", "macd_hist", "macd_strength",
     "atr_7", "atr_14", "atr_21", "candle_body", "candle_range", "candle_upper_wick",
     "candle_lower_wick", "pdh", "pdl", "di_diff"}
    | {f"{p}_{n}" for p in ("ema", "sma") for n in (10, 20, 50, 100, 200)}
)


def build_feature_frame(df: pd.DataFrame) -> tuple:
    """Features and regimes on the full history (all causal, verified by truncation tests)."""
    features = build_all_features(compute_all_indicators(df[["time", "open", "high", "low", "close", "volume"]]))
    return features, compute_regimes(df)


def training_matrix(df, features, regimes, cfg):
    """Independent labeled trades of `cfg` on df, with features and regimes attached."""
    signals = generate_icc_signals(df, cfg, SPEC)
    trades = simulate_icc_trades(df, signals, cfg, SPEC, EXEC)
    trades = attach_regimes_to_trades(trades, regimes)
    joined = attach_features_to_trades(trades, features.iloc[:len(df)]).dropna(subset=["win"])
    cols = [c for c in get_feature_columns(joined) if c not in EXCLUDED_FEATURES]
    keep = [c for c in cols if joined[c].notna().mean() > 0.9 and joined[c].nunique(dropna=True) > 1]
    return joined.dropna(subset=keep).reset_index(drop=True), keep


def main():
    sel = json.loads((RESULTS / "selection.json").read_text())
    cfg = to_config(sel["chosen_params"])
    full = load_data()
    features, regimes = build_feature_frame(full)
    dev = full[full["time"] < HOLDOUT_START].reset_index(drop=True)
    joined, feature_cols = training_matrix(dev, features, regimes, cfg)
    print(f"training matrix: {len(joined)} trades x {len(feature_cols)} features, base win rate {joined['win'].mean():.3f}")

    results = {}
    for variant in VARIANTS:
        res, oos = train_walk_forward(joined, feature_cols, n_folds=5, embargo_bars=50,
                                      calibrate=True, model_type=variant)
        s = summarize_folds(res)
        results[variant] = {"summary": s, "oos": oos}
        print(f"{variant:34s} AUC {s['mean_auc']:.3f}  edge {s['total_edge_pips']:+,.0f} pips  "
              f"folds +edge {s['folds_with_positive_edge']}/{s['n_folds']}")

    best = max(VARIANTS, key=lambda v: results[v]["summary"]["total_edge_pips"])
    s, oos = results[best]["summary"], results[best]["oos"]
    passes = s["total_edge_pips"] > 0 and s["folds_with_positive_edge"] >= 0.6 * s["n_folds"]
    threshold = select_deployment_threshold(oos)

    models_dir = ROOT / "models"
    models_dir.mkdir(exist_ok=True)
    bundle = fit_final_model(joined, feature_cols, threshold, model_type=best,
                             out_path=str(models_dir / "model_icc_meta_v2.joblib"),
                             pip=SPEC.pip, strategy_cfg=cfg)

    out = {
        "strategy": sel["chosen_label"], "n_trades": len(joined), "n_features": len(feature_cols),
        "base_win_rate": float(joined["win"].mean()),
        "variants": {v: {k: r["summary"][k] for k in ("mean_auc", "std_auc", "mean_brier", "total_edge_pips",
                                                     "folds_with_positive_edge", "n_folds")}
                     for v, r in results.items()},
        "selected_variant": best, "per_fold": s["per_fold"],
        "deployment_threshold": float(threshold),
        "meta_model_adds_value_on_development": bool(passes),
        "oos_by_regime": regime_oos_report(oos, by="regime_trend").to_dict("records"),
        "oos_by_vol": regime_oos_report(oos, by="regime_vol").to_dict("records"),
        "feature_cols": feature_cols,
        "bundle_path": str(models_dir / "model_icc_meta_v2.joblib"),
    }
    (RESULTS / "meta_model.json").write_text(json.dumps(out, indent=2, default=float))
    print(json.dumps({k: v for k, v in out.items() if k not in ("feature_cols", "per_fold")}, indent=2, default=float))


if __name__ == "__main__":
    main()
