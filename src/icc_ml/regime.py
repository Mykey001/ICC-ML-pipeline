"""
Market regime labelling and per-regime behaviour profiles.

Two causal axes, computed only from bars up to and including the labelled bar:
- Trend:      "up" / "down" when ADX >= threshold (sign of DI+ minus DI-), else "range"
- Volatility: "low" / "normal" / "high" from the percentile rank of ATR within its
              own trailing window

Per trade, alignment says whether the trade goes with the trend (+1), against it
(-1), or was taken in a range (0).

The trailing volatility window must fit inside the bar buffer used live (2000
bars in live_trading/config.yaml and forward_test/config.yaml), otherwise live
regime values would differ from training.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np
import pandas as pd
import pandas_ta as ta


@dataclass
class RegimeConfig:
    """Regime definition parameters."""
    adx_length: int = 14
    adx_trend_threshold: float = 25.0
    atr_length: int = 14
    vol_lookback_bars: int = 1500  # must stay below the live bar buffer
    vol_low_cut: float = 1 / 3     # percentile rank below this -> "low"
    vol_high_cut: float = 2 / 3    # percentile rank above this -> "high"
    min_trades: int = 30           # below this, per-regime statistics are flagged unreliable


# Numeric model features added by attach_regimes_to_trades()
REGIME_FEATURE_COLS = ["regime_vol_rank", "regime_vol_code", "regime_trend_code", "regime_alignment"]

# Text labels carried alongside trades (never model features)
REGIME_LABEL_COLS = ["regime", "regime_trend", "regime_vol"]

_VOL_NAMES = {0: "low", 1: "normal", 2: "high"}
_TREND_NAMES = {1: "up", -1: "down", 0: "range"}


def compute_regimes(df: pd.DataFrame, cfg: Optional[RegimeConfig] = None) -> pd.DataFrame:
    """
    Label every bar with its trend and volatility regime.

    Args:
        df: OHLCV DataFrame
        cfg: Regime configuration

    Returns:
        DataFrame (positional index, one row per bar) with columns:
        - regime_vol_rank: ATR percentile rank in its trailing window (0-1)
        - regime_vol_code: 0 low, 1 normal, 2 high (NaN during warm-up)
        - regime_trend_code: 1 up, -1 down, 0 range (NaN during warm-up)
        - regime_vol, regime_trend, regime: text labels ("unknown" during warm-up)
    """
    cfg = cfg or RegimeConfig()
    df = df.reset_index(drop=True)

    atr = ta.atr(df["high"], df["low"], df["close"], length=cfg.atr_length)
    vol_rank = atr.rolling(cfg.vol_lookback_bars, min_periods=cfg.vol_lookback_bars).rank(pct=True)
    vol_code = pd.Series(
        np.select([vol_rank < cfg.vol_low_cut, vol_rank > cfg.vol_high_cut], [0.0, 2.0], 1.0),
        index=df.index,
    ).where(vol_rank.notna())

    adx_df = ta.adx(df["high"], df["low"], df["close"], length=cfg.adx_length)
    adx = adx_df[[c for c in adx_df.columns if c.startswith("ADX")][0]]
    dmp = adx_df[[c for c in adx_df.columns if c.startswith("DMP")][0]]
    dmn = adx_df[[c for c in adx_df.columns if c.startswith("DMN") or c.startswith("DMM")][0]]
    trend_code = pd.Series(
        np.where(adx >= cfg.adx_trend_threshold, np.sign(dmp - dmn), 0.0),
        index=df.index,
    ).where(adx.notna() & dmp.notna() & dmn.notna())

    out = pd.DataFrame({
        "regime_vol_rank": vol_rank,
        "regime_vol_code": vol_code,
        "regime_trend_code": trend_code,
    }, index=df.index)
    out["regime_vol"] = vol_code.map(_VOL_NAMES).fillna("unknown")
    out["regime_trend"] = trend_code.map(_TREND_NAMES).fillna("unknown")
    out["regime"] = np.where(
        (out["regime_vol"] == "unknown") | (out["regime_trend"] == "unknown"),
        "unknown",
        out["regime_trend"] + "|" + out["regime_vol"],
    )
    return out


def attach_regimes_to_trades(trades: pd.DataFrame, regimes: pd.DataFrame) -> pd.DataFrame:
    """
    Add the signal bar's regime (features and labels) to each trade.

    Args:
        trades: DataFrame with signal_bar and direction columns
        regimes: Output of compute_regimes() for the same bars

    Returns:
        Copy of trades with REGIME_FEATURE_COLS and REGIME_LABEL_COLS added
    """
    out = trades.drop(columns=[c for c in REGIME_FEATURE_COLS + REGIME_LABEL_COLS if c in trades.columns])
    at_signal = regimes.loc[out["signal_bar"].to_numpy()].reset_index(drop=True)
    at_signal.index = out.index
    out = pd.concat([out, at_signal], axis=1)
    out["regime_alignment"] = out["direction"] * out["regime_trend_code"]
    return out


def regime_alignment(direction: int, trend_code: float) -> float:
    """Alignment of one trade with the trend: 1 with, -1 against, 0 range."""
    return direction * trend_code


def regime_profile(
    trades: pd.DataFrame,
    by: str = "regime",
    min_trades: int = 30,
    pip: Optional[float] = None,
) -> pd.DataFrame:
    """
    Describe how the strategy behaves in each regime.

    Args:
        trades: Labeled trades with a regime column (see attach_regimes_to_trades)
        by: Column to group by ("regime", "regime_trend", "regime_vol" or "regime_alignment")
        min_trades: Groups smaller than this are marked reliable=False
        pip: Pip size (SymbolSpec.pip); needed for median_sl_pips, otherwise NaN

    Returns:
        One row per regime: trade count and share, win rate, TP rate, average and
        total net pips, median bars held, median SL distance (pips) and long/short
        win rates
    """
    if len(trades) == 0 or by not in trades.columns:
        return pd.DataFrame()

    t = trades.copy()
    t["_held"] = t["exit_bar"] - t["entry_bar"]
    t["_tp"] = (t["exit_reason"] == "tp").astype(float)
    t["_long_win"] = t["win"].where(t["direction"] == 1)
    t["_short_win"] = t["win"].where(t["direction"] == -1)
    t["_sl_pips"] = (t["entry_price"] - t["sl_price"]).abs() / pip if pip else np.nan

    g = t.groupby(by, dropna=False)
    prof = pd.DataFrame({
        "n_trades": g.size(),
        "win_rate": g["win"].mean(),
        "tp_rate": g["_tp"].mean(),
        "avg_net_pips": g["net_pips"].mean(),
        "total_net_pips": g["net_pips"].sum(),
        "median_bars_held": g["_held"].median(),
        "median_sl_pips": g["_sl_pips"].median(),
        "long_share": g["direction"].apply(lambda d: (d == 1).mean()),
        "long_win_rate": g["_long_win"].mean(),
        "short_win_rate": g["_short_win"].mean(),
    })
    prof.insert(1, "share", prof["n_trades"] / prof["n_trades"].sum())
    prof["reliable"] = prof["n_trades"] >= min_trades
    return prof.sort_values("n_trades", ascending=False).reset_index().rename(columns={by: "regime"})


def regime_oos_report(oos: pd.DataFrame, by: str = "regime", min_trades: int = 30) -> pd.DataFrame:
    """
    Out-of-sample model performance per regime.

    Args:
        oos: OOS predictions from train.train_walk_forward() (must carry the `by` column)
        by: Regime column to group by
        min_trades: Groups smaller than this are marked reliable=False

    Returns:
        One row per regime: trades, base win rate, take-all pips, trades the model
        took, model pips, edge (model minus take-all), and AUC where computable
    """
    from sklearn.metrics import roc_auc_score

    if len(oos) == 0 or by not in oos.columns:
        return pd.DataFrame()

    rows = []
    for regime, g in oos.groupby(by, dropna=False):
        taken = g["y_pred"] == 1
        auc = np.nan
        if len(g) >= min_trades and g["y_true"].nunique() == 2:
            auc = roc_auc_score(g["y_true"], g["y_pred_proba"])
        rows.append({
            "regime": regime,
            "n_trades": len(g),
            "base_win_rate": g["y_true"].mean(),
            "take_all_pips": g["net_pips"].sum(),
            "n_taken": int(taken.sum()),
            "win_rate_if_taken": g.loc[taken, "y_true"].mean() if taken.any() else np.nan,
            "model_pips": g.loc[taken, "net_pips"].sum(),
            "edge_pips": g.loc[taken, "net_pips"].sum() - g["net_pips"].sum(),
            "auc": auc,
            "reliable": len(g) >= min_trades,
        })
    return pd.DataFrame(rows).sort_values("n_trades", ascending=False).reset_index(drop=True)


def describe_expectation(profile: pd.DataFrame, regime: str) -> dict:
    """
    Look up what the training data says about a regime, for live decisions.

    Args:
        profile: Output of regime_profile() stored in the model bundle
        regime: Regime label of the current bar

    Returns:
        Dict with the regime's historical statistics, or a note if it was not
        seen (or seen too rarely) in training
    """
    if profile is None or len(profile) == 0:
        return {"regime": regime, "note": "no regime profile in model bundle"}
    row = profile[profile["regime"] == regime]
    if len(row) == 0:
        return {"regime": regime, "note": "regime never seen in training data"}
    r = row.iloc[0].to_dict()
    if not r.get("reliable", True):
        r["note"] = f"only {int(r['n_trades'])} training trades in this regime - statistics unreliable"
    return r


def regime_config_dict(cfg: RegimeConfig) -> dict:
    """Serialisable form of the regime configuration (for the model bundle)."""
    return asdict(cfg)
