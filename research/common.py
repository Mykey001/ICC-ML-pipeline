"""Shared setup for the research scripts (see research/PROTOCOL.md)."""

from __future__ import annotations
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from icc_ml.config import StrategyConfig, ExecutionConfig, SYMBOL_PRESETS  # noqa: E402
from icc_ml.data_fetch import load_mt5_export  # noqa: E402

DATA_PATH = ROOT / "data" / "raw" / "XAUUSDm_H1_202201162300_202609161200.csv"
RESULTS = ROOT / "research" / "results"
HOLDOUT_START = pd.Timestamp("2025-09-16")

SPEC = SYMBOL_PRESETS["XAUUSDm"]
EXEC = ExecutionConfig(slippage_points=5.0, both_hit_same_bar_policy="sl_first")
MIN_TRADES_PER_YEAR = 15


def load_data() -> pd.DataFrame:
    """Full history (development + holdout)."""
    return load_mt5_export(str(DATA_PATH))


def development(df: pd.DataFrame) -> pd.DataFrame:
    """Development period only (everything before the holdout)."""
    return df[df["time"] < HOLDOUT_START].reset_index(drop=True)


# ---- search space (PROTOCOL.md) -------------------------------------------
_SL = {"swing_h4": dict(use_custom_swing_sl=True, sl_swing_timeframe="4h"),
       "swing_d1": dict(use_custom_swing_sl=True, sl_swing_timeframe="D1"),
       "ltf": dict(use_custom_swing_sl=False)}
_TP = ([("fixed", dict(tp_mode="fixed_pips", tp_pips=v)) for v in (1500, 2500, 4000)]
       + [("r", dict(tp_mode="r_multiple", tp_r_multiple=v)) for v in (0.75, 1.0, 1.5, 2.0)]
       + [("atr", dict(tp_mode="atr", tp_atr_mult=v)) for v in (3, 5, 8)])


def search_space() -> list[dict]:
    """All 2,160 configurations as flat parameter dicts."""
    grid = []
    for htf, ltf, sl, buf, (tp_kind, tp), trend, max_sl in itertools.product(
        (2, 3, 4), (1, 2), _SL, (0, 200), _TP, ("none", "ema"), (0, 5, 7)
    ):
        grid.append({"htf_pivot_len": htf, "ltf_pivot_len": ltf, "sl": sl, "sl_buffer_pips": buf,
                     "tp_kind": tp_kind, **tp, "trend_filter": trend, "max_sl_atr": float(max_sl)})
    return grid


def to_config(p: dict) -> StrategyConfig:
    """StrategyConfig for one flat parameter dict."""
    kw = {k: v for k, v in p.items() if k not in ("sl", "tp_kind", "config_id")}
    return StrategyConfig(**kw, **_SL[p["sl"]])


def config_label(p: dict) -> str:
    """Short human-readable description of a configuration."""
    tp = {"fixed": f"TP {p.get('tp_pips', 0):.0f}p", "r": f"TP {p.get('tp_r_multiple', 0)}R",
          "atr": f"TP {p.get('tp_atr_mult', 0)}ATR"}[p["tp_kind"]]
    parts = [f"piv {p['htf_pivot_len']}/{p['ltf_pivot_len']}", f"SL {p['sl']}", tp]
    if p["sl_buffer_pips"]:
        parts.append(f"buf {p['sl_buffer_pips']}")
    if p["trend_filter"] != "none":
        parts.append("EMA200 trend")
    if p["max_sl_atr"]:
        parts.append(f"maxSL {p['max_sl_atr']:.0f}ATR")
    return ", ".join(parts)


def monthly_sharpe(monthly: pd.DataFrame | pd.Series):
    """Mean / std of monthly net pips (per row if a DataFrame of configs x months)."""
    if isinstance(monthly, pd.Series):
        std = monthly.std(ddof=1)
        return monthly.mean() / std if std > 0 else np.nan
    return monthly.mean(axis=1) / monthly.std(axis=1, ddof=1).replace(0, np.nan)
