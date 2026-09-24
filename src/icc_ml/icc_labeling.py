"""
Trade simulation and meta-labeling.

Simulates each ICC signal to its real conclusion using the strategy's own exit rules:
- Swing stop loss
- Take profit (TP_Mode: fixed pips, R-multiple or ATR multiple)
- Maximum hold time

Execution model (prices in the data are bid, as MT5 exports them):
- Entry at next bar open (never signal bar close). Longs buy at the ask
  (open + spread), shorts sell at the bid.
- Long SL/TP trigger on the bid; short SL/TP trigger on the ask (bid + spread).
  The spread is therefore paid once per round trip, as on a real account.
- Per-bar spread from a `spread` column (points) when present, else the symbol's
  typical spread. Zero spreads (bad data) are replaced by the median.
- Adverse slippage on the market entry and on stop-loss exits; take profit is a
  limit order and fills at its price.
- A bar that opens beyond SL/TP fills at that open.
- SL and TP inside the same bar: resolved by ExecutionConfig.both_hit_same_bar_policy.
- TP is measured from the requested entry price, and orders whose SL is on the
  wrong side of it are refused, as the EA's OpenTrade() does.
- Trades still open when the data ends are dropped: their outcome is unknown.
- Commission per lot.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional
import warnings

import pandas as pd
import numpy as np

from .config import StrategyConfig, ExecutionConfig, SymbolSpec
from .strategy_icc import tp_distance


@dataclass
class MarketArrays:
    """Bid OHLC and per-bar spread (price units) as numpy arrays."""
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    spread: np.ndarray


def market_arrays(df: pd.DataFrame, spec: SymbolSpec) -> MarketArrays:
    """Extract simulation arrays from an OHLCV DataFrame (optional `spread` column in points)."""
    n = len(df)
    if "spread" in df.columns:
        pts = df["spread"].to_numpy(dtype=float)
        median = np.median(pts[pts > 0]) if (pts > 0).any() else spec.typical_spread_points
        pts = np.where(pts > 0, pts, median)
    else:
        pts = np.full(n, spec.typical_spread_points)
    return MarketArrays(
        open=df["open"].to_numpy(dtype=float),
        high=df["high"].to_numpy(dtype=float),
        low=df["low"].to_numpy(dtype=float),
        close=df["close"].to_numpy(dtype=float),
        spread=pts * spec.point,
    )


def simulate_position(
    m: MarketArrays,
    signal_bar: int,
    direction: int,
    sl_price: float,
    atr: float,
    cfg: StrategyConfig,
    spec: SymbolSpec,
    exec_cfg: ExecutionConfig,
) -> Optional[dict]:
    """
    Simulate one position opened at the bar after `signal_bar`.

    Returns the trade dict, None if the order is refused or there is no next bar,
    or a dict with exit_reason "open_at_end" (exit_bar = number of bars) if the
    position is still open when the data ends.
    """
    n = len(m.open)
    e = signal_bar + 1
    if e >= n or np.isnan(sl_price):
        return None

    point, pip = spec.point, spec.pip
    slip = exec_cfg.slippage_points * point
    requested = m.open[e] + (m.spread[e] if direction == 1 else 0.0)  # ask for buys, bid for sells
    if direction * (requested - sl_price) <= 0:
        return None  # OpenTrade() refuses an SL on the wrong side
    tp_price = requested + direction * tp_distance(cfg, spec, requested, sl_price, atr)
    if np.isnan(tp_price):
        return None
    entry_price = requested + direction * slip

    end = min(n, e + cfg.max_hold_bars)
    hi, lo, op = m.high[e:end], m.low[e:end], m.open[e:end]
    if direction == -1:  # shorts trigger on the ask
        hi, lo, op = hi + m.spread[e:end], lo + m.spread[e:end], op + m.spread[e:end]
    if direction == 1:
        sl_hit, tp_hit = lo <= sl_price, hi >= tp_price
    else:
        sl_hit, tp_hit = hi >= sl_price, lo <= tp_price
    hits = np.flatnonzero(sl_hit | tp_hit)

    if len(hits) == 0:
        if end == n:
            return {"signal_bar": signal_bar, "direction": direction, "entry_bar": e,
                    "exit_bar": n, "exit_reason": "open_at_end"}
        k = end - e - 1
        exit_bar, exit_reason = end - 1, "timeout"
        exit_price = m.close[exit_bar] + (m.spread[exit_bar] if direction == -1 else 0.0)
    else:
        k = hits[0]
        exit_bar = e + k
        gap = k > 0 and (direction * (op[k] - sl_price) <= 0 or direction * (op[k] - tp_price) >= 0)
        if gap:
            if direction * (op[k] - sl_price) <= 0:
                exit_reason, exit_price = "sl", op[k] - direction * slip
            else:
                exit_reason, exit_price = "tp", op[k]
        else:
            take_sl = sl_hit[k] and (not tp_hit[k] or exec_cfg.both_hit_same_bar_policy == "sl_first")
            if take_sl:
                exit_reason, exit_price = "sl", sl_price - direction * slip
            else:
                exit_reason, exit_price = "tp", tp_price

    commission_per_lot = spec.commission_per_lot_roundturn if exec_cfg.apply_commission else 0.0
    commission_pips = commission_per_lot / (pip * spec.contract_size) if pip * spec.contract_size > 0 else 0.0
    spread_cost_pips = (m.spread[e] if direction == 1 else m.spread[exit_bar]) / pip
    slippage_cost_pips = slip / pip * (2 if exit_reason == "sl" else 1)

    net_pips = direction * (exit_price - entry_price) / pip - commission_pips
    gross_pips = net_pips + commission_pips + spread_cost_pips + slippage_cost_pips

    return {
        "signal_bar": signal_bar,
        "direction": direction,
        "entry_bar": e,
        "entry_price": entry_price,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "exit_bar": exit_bar,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "gross_pips": gross_pips,
        "spread_cost_pips": spread_cost_pips,
        "slippage_cost_pips": slippage_cost_pips,
        "commission_pips": commission_pips,
        "net_pips": net_pips,
        "win": 1 if net_pips > 0 else 0,
    }


_TRADE_COLUMNS = [
    "signal_bar", "direction", "entry_bar", "entry_price",
    "sl_price", "tp_price", "exit_bar", "exit_price",
    "exit_reason", "gross_pips", "spread_cost_pips",
    "slippage_cost_pips", "commission_pips", "net_pips", "win",
]


def simulate_icc_trades(
    df: pd.DataFrame,
    signals: pd.DataFrame,
    cfg: StrategyConfig,
    spec: SymbolSpec,
    exec_cfg: ExecutionConfig,
    enforce_one_position: bool = False,
) -> pd.DataFrame:
    """
    Simulate each ICC signal to its conclusion and generate labels.

    Args:
        df: OHLCV DataFrame (optional `spread` column in points)
        signals: ICC signals from strategy_icc.generate_icc_signals()
        cfg: Strategy configuration
        spec: Symbol specification
        exec_cfg: Execution configuration
        enforce_one_position: If True, skip signals while a trade is open (approximation;
                             ea_backtest.run_sequential_backtest reproduces the EA exactly).
                             If False, simulate all signals independently (labeling mode).

    Returns:
        DataFrame with one row per trade:
        - signal_bar: Bar where signal occurred
        - direction: 1 (long) or -1 (short)
        - entry_bar: Bar where entry occurred (signal_bar + 1)
        - entry_price: Fill price (ask for longs, bid for shorts, incl. slippage)
        - sl_price: Stop loss price
        - tp_price: Take profit price
        - exit_bar: Bar where trade closed
        - exit_price: Fill price at exit (incl. slippage on stops)
        - exit_reason: 'tp', 'sl', or 'timeout'
        - gross_pips: P&L before spread, slippage and commission
        - spread_cost_pips, slippage_cost_pips, commission_pips: those costs
        - net_pips: Final P&L after all costs
        - win: 1 if net_pips > 0, else 0 (THE LABEL)
    """
    df = df.reset_index(drop=True)
    m = market_arrays(df, spec)
    has_atr = "atr" in signals.columns
    trades = []
    busy_until = -1

    for idx, sig_row in signals[signals["signal"] != 0].iterrows():
        if enforce_one_position and idx < busy_until:
            continue
        trade = simulate_position(
            m, idx, int(sig_row["signal"]), sig_row["sl_price"],
            sig_row["atr"] if has_atr else np.nan, cfg, spec, exec_cfg,
        )
        if trade is None:
            continue
        if enforce_one_position:
            busy_until = trade["exit_bar"]
        if trade["exit_reason"] != "open_at_end":
            trades.append(trade)

    return pd.DataFrame(trades, columns=_TRADE_COLUMNS)


def diagnose_trades(
    trades: pd.DataFrame,
    cfg: StrategyConfig,
    spec: SymbolSpec,
) -> dict:
    """
    Run diagnostics on labeled trades.
    
    Returns dict with:
    - n_taken: Total trades
    - win_rate: Fraction winning
    - tp_hit_rate: Fraction reaching TP
    - sl_hit_rate: Fraction hitting SL
    - timeout_rate: Fraction timing out
    - warnings: List of diagnostic warnings
    """
    if len(trades) == 0:
        return {"error": "No trades to diagnose"}
    
    n = len(trades)
    wins = (trades["win"] == 1).sum()
    tp_hits = (trades["exit_reason"] == "tp").sum()
    sl_hits = (trades["exit_reason"] == "sl").sum()
    timeouts = (trades["exit_reason"] == "timeout").sum()
    
    report = {
        "n_taken": n,
        "win_rate": wins / n,
        "tp_hit_rate": tp_hits / n,
        "sl_hit_rate": sl_hits / n,
        "timeout_rate": timeouts / n,
        "warnings": [],
    }
    
    # Diagnostic checks
    if report["tp_hit_rate"] < 0.02:
        report["warnings"].append(
            f"TP hit rate {report['tp_hit_rate']:.1%} is extremely low. "
            f"TP target of {cfg.tp_pips} pips ({spec.pips_to_price(cfg.tp_pips):g} price move) "
            f"is likely unreachable for this symbol's pip convention. "
            f"Check symbol digits and adjust tp_pips accordingly."
        )
    
    if report["timeout_rate"] > 0.3:
        report["warnings"].append(
            f"Timeout rate {report['timeout_rate']:.1%} is high. "
            f"Too many trades decided by max_hold_bars={cfg.max_hold_bars} rather than SL/TP. "
            f"This makes labels arbitrary."
        )
    
    if n < 100:
        report["warnings"].append(
            f"Only {n} trades. At least 100 is recommended, 300+ for walk-forward to be meaningful. "
            f"Extend history depth or reduce timeframe."
        )
    
    return report


def attach_features_to_trades(
    trades: pd.DataFrame,
    features: pd.DataFrame,
) -> pd.DataFrame:
    """
    Join features from the signal bar to each trade.
    
    Creates the training matrix: each row is a trade with its features and label.
    
    Args:
        trades: Output from simulate_icc_trades()
        features: Output from features.build_all_features()
    
    Returns:
        DataFrame with trades + features, ready for training
    """
    if len(trades) == 0:
        return trades
    
    # Features are indexed by bar number
    # We want features from the SIGNAL bar (not entry bar)
    features_at_signal = features.loc[trades["signal_bar"]].reset_index(drop=True)
    trades_reset = trades.reset_index(drop=True)
    
    # Concatenate
    joined = pd.concat([trades_reset, features_at_signal], axis=1)
    
    # Drop time column if present (not a feature)
    if "time" in joined.columns:
        joined = joined.drop(columns=["time"])
    
    return joined


def label_summary(trades: pd.DataFrame) -> dict:
    """
    Summary statistics for labeled trades.
    
    Returns dict with key metrics for reporting.
    """
    if len(trades) == 0:
        return {"n_trades": 0}
    
    return {
        "n_trades": len(trades),
        "win_rate": (trades["win"] == 1).mean(),
        "avg_gross_pips": trades["gross_pips"].mean(),
        "avg_net_pips": trades["net_pips"].mean(),
        "total_net_pips": trades["net_pips"].sum(),
        "avg_bars_held": (trades["exit_bar"] - trades["entry_bar"]).mean(),
        "median_bars_held": (trades["exit_bar"] - trades["entry_bar"]).median(),
        "max_bars_held": (trades["exit_bar"] - trades["entry_bar"]).max(),
        "tp_rate": (trades["exit_reason"] == "tp").mean(),
        "sl_rate": (trades["exit_reason"] == "sl").mean(),
        "timeout_rate": (trades["exit_reason"] == "timeout").mean(),
        "long_win_rate": trades[trades["direction"] == 1]["win"].mean() if (trades["direction"] == 1).any() else np.nan,
        "short_win_rate": trades[trades["direction"] == -1]["win"].mean() if (trades["direction"] == -1).any() else np.nan,
    }
