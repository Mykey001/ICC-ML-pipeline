"""
Step 4: single evaluation on the holdout (2025-09-16 -> 2026-09-16).

Runs after the strategy configuration (selection.json), meta-model and threshold
(models/model_icc_meta_v2.joblib) are frozen. One continuous sequential backtest
over the full history; only trades signalled inside the holdout are counted. The
meta-model filter is switched on at the holdout start.

Writes research/results/holdout.json.
"""

from __future__ import annotations
import importlib
import json
import warnings

import joblib
import numpy as np
import pandas as pd

from common import ROOT, RESULTS, SPEC, EXEC, HOLDOUT_START, load_data, to_config
from icc_ml.ea_backtest import run_sequential_backtest, monthly_pnl, summarize_backtest
from icc_ml.regime import regime_alignment, regime_profile, attach_regimes_to_trades

warnings.filterwarnings("ignore")
step2 = importlib.import_module("02_select_strategy")
step3 = importlib.import_module("03_train_meta_model")


def holdout_stats(trades, full, start_bar):
    t = trades[trades["signal_bar"] >= start_bar].reset_index(drop=True)
    times = full["time"]
    months = pd.period_range(times.iloc[start_bar], times.iloc[-1], freq="M")
    return t, summarize_backtest(t, monthly_pnl(t, times, months))


def main():
    sel = json.loads((RESULTS / "selection.json").read_text())
    cfg = to_config(sel["chosen_params"])
    bundle = joblib.load(ROOT / "models" / "model_icc_meta_v2.joblib")
    full = load_data()
    start_bar = int(np.searchsorted(full["time"].to_numpy(), np.datetime64(HOLDOUT_START)))

    features, regimes = step3.build_feature_frame(full)
    frame = features.join(regimes[["regime_vol_rank", "regime_vol_code", "regime_trend_code"]])
    cols = bundle["feature_cols"]
    model, threshold = bundle["model"], bundle["threshold"]

    def model_filter(bar: int, direction: int, sl_price: float, atr: float) -> bool:
        if bar < start_bar:
            return True
        row = frame.loc[bar].copy()
        row["regime_alignment"] = regime_alignment(direction, regimes.loc[bar, "regime_trend_code"])
        return model.predict_proba(row[cols].to_numpy(dtype=float).reshape(1, -1))[0, 1] >= threshold

    out = {"strategy": sel["chosen_label"], "threshold": float(threshold), "holdout_start": str(HOLDOUT_START)}
    runs = {
        "selected_strategy": run_sequential_backtest(full, cfg, SPEC, EXEC),
        "selected_strategy_with_model": run_sequential_backtest(full, cfg, SPEC, EXEC, take_signal=model_filter),
        "default_strategy_reference": run_sequential_backtest(full, to_config(step2.DEFAULT), SPEC, EXEC),
    }
    for name, trades in runs.items():
        t, stats = holdout_stats(trades, full, start_bar)
        out[name] = stats
        if name == "selected_strategy":
            out["selected_strategy_random_timing"] = step2.random_timing(full, cfg, t)
            prof = regime_profile(attach_regimes_to_trades(t, regimes), by="regime_trend", pip=SPEC.pip)
            out["selected_strategy_by_trend"] = prof.to_dict("records")

    s, m = out["selected_strategy"], out["selected_strategy_with_model"]
    out["strategy_holds_up"] = bool(s["net_pips"] > 0 and s["profit_factor"] > 1.1)
    out["model_holds_up"] = bool(m["net_pips"] >= s["net_pips"])
    (RESULTS / "holdout.json").write_text(json.dumps(out, indent=2, default=float))
    print(json.dumps(out, indent=2, default=float))


if __name__ == "__main__":
    main()
