"""
Trade simulation and meta-labeling.

Simulates each ICC signal to its real conclusion using the strategy's own exit rules:
- Swing stop loss
- Fixed pip take profit  
- Maximum hold time

Applies execution realism:
- Entry at next bar open (never signal bar close)
- Spread on entry and exit
- Adverse slippage both sides
- Commission per lot
- Pessimistic assumption: when SL & TP both hit same bar, assume SL first
"""

from __future__ import annotations
from typing import Literal
import warnings

import pandas as pd
import numpy as np

from .config import StrategyConfig, ExecutionConfig, SymbolSpec


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
        df: OHLCV DataFrame
        signals: ICC signals from strategy_icc.generate_icc_signals()
        cfg: Strategy configuration
        spec: Symbol specification
        exec_cfg: Execution configuration
        enforce_one_position: If True, block new signals while a trade is open (backtest mode).
                             If False, simulate all signals independently (labeling mode).
    
    Returns:
        DataFrame with one row per trade:
        - signal_bar: Bar where signal occurred
        - direction: 1 (long) or -1 (short)
        - entry_bar: Bar where entry occurred (signal_bar + 1)
        - entry_price: Actual entry price (with spread & slippage)
        - sl_price: Stop loss price
        - tp_price: Take profit price
        - exit_bar: Bar where trade closed
        - exit_price: Actual exit price (with spread & slippage)
        - exit_reason: 'tp', 'sl', or 'timeout'
        - gross_pips: P&L before costs
        - spread_cost_pips: Spread cost
        - slippage_cost_pips: Slippage cost
        - commission_pips: Commission cost
        - net_pips: Final P&L after all costs
        - win: 1 if net_pips > 0, else 0 (THE LABEL)
    """
    trades = []
    active_trade = None  # For enforce_one_position mode
    
    # Get signal rows
    signal_rows = signals[signals["signal"] != 0].copy()
    
    for idx, sig_row in signal_rows.iterrows():
        # Check if blocked by active position
        if enforce_one_position and active_trade is not None:
            if active_trade["exit_bar"] > idx:
                continue  # Skip this signal
        
        # Simulate this trade
        trade = _simulate_single_trade(
            df, idx, sig_row, cfg, spec, exec_cfg
        )
        
        if trade is not None:
            trades.append(trade)
            
            if enforce_one_position:
                active_trade = trade
    
    if len(trades) == 0:
        # Return empty DataFrame with correct schema
        return pd.DataFrame(columns=[
            "signal_bar", "direction", "entry_bar", "entry_price",
            "sl_price", "tp_price", "exit_bar", "exit_price",
            "exit_reason", "gross_pips", "spread_cost_pips",
            "slippage_cost_pips", "commission_pips", "net_pips", "win"
        ])
    
    return pd.DataFrame(trades)


def _simulate_single_trade(
    df: pd.DataFrame,
    signal_bar: int,
    sig_row: pd.Series,
    cfg: StrategyConfig,
    spec: SymbolSpec,
    exec_cfg: ExecutionConfig,
) -> dict:
    """
    Simulate one trade from signal to exit.
    
    Returns trade dict or None if trade cannot be taken.
    """
    direction = int(sig_row["signal"])
    
    # Entry: NEXT bar open (never signal bar close)
    entry_bar = signal_bar + 1
    if entry_bar >= len(df):
        return None  # Signal at last bar, no entry possible
    
    entry_price_raw = df.loc[entry_bar, "open"]
    
    # Apply spread and slippage (adverse)
    spread_price = spec.point * exec_cfg.slippage_points
    slippage_price = spec.point * exec_cfg.slippage_points
    
    if direction == 1:  # Long
        entry_price = entry_price_raw + spread_price + slippage_price
    else:  # Short
        entry_price = entry_price_raw - spread_price - slippage_price
    
    # SL and TP from signal
    sl_price = sig_row["sl_price"]
    tp_price = sig_row["tp_price"]
    
    if np.isnan(sl_price) or np.isnan(tp_price):
        return None  # Invalid signal
    
    # Commission
    commission_per_lot = spec.commission_per_lot_roundturn if exec_cfg.apply_commission else 0.0
    commission_pips = commission_per_lot / (spec.pip * spec.contract_size) if spec.pip * spec.contract_size > 0 else 0.0
    
    # Simulate forward from entry bar
    max_bars = cfg.max_hold_bars
    for bars_held in range(max_bars):
        bar = entry_bar + bars_held
        if bar >= len(df):
            # Ran out of data → timeout
            exit_bar = len(df) - 1
            exit_price = df.loc[exit_bar, "close"]
            exit_reason = "timeout"
            break
        
        high = df.loc[bar, "high"]
        low = df.loc[bar, "low"]
        close = df.loc[bar, "close"]
        
        # Check if SL or TP hit
        if direction == 1:
            sl_hit = low <= sl_price
            tp_hit = high >= tp_price
        else:
            sl_hit = high >= sl_price
            tp_hit = low <= tp_price
        
        # Both hit in same bar?
        if sl_hit and tp_hit:
            # Apply policy
            if exec_cfg.both_hit_same_bar_policy == "sl_first":
                tp_hit = False  # Pessimistic: SL hit first
            else:
                sl_hit = False  # Optimistic: TP hit first
        
        if tp_hit:
            exit_bar = bar
            exit_price = tp_price
            exit_reason = "tp"
            break
        
        elif sl_hit:
            exit_bar = bar
            exit_price = sl_price
            exit_reason = "sl"
            break
    
    else:
        # Max hold reached → timeout at current close
        exit_bar = entry_bar + max_bars - 1
        if exit_bar >= len(df):
            exit_bar = len(df) - 1
        exit_price = df.loc[exit_bar, "close"]
        exit_reason = "timeout"
    
    # Apply spread and slippage on exit (adverse)
    if direction == 1:
        exit_price = exit_price - spread_price - slippage_price
    else:
        exit_price = exit_price + spread_price + slippage_price
    
    # Calculate P&L
    if direction == 1:
        gross_price = exit_price - entry_price
    else:
        gross_price = entry_price - exit_price
    
    gross_pips = spec.price_to_pips(gross_price)
    
    # Costs
    spread_cost_pips = spec.price_to_pips(spread_price) * 2  # Entry + exit
    slippage_cost_pips = spec.price_to_pips(slippage_price) * 2
    
    # Net P&L
    net_pips = gross_pips - spread_cost_pips - slippage_cost_pips - commission_pips
    
    # The label
    win = 1 if net_pips > 0 else 0
    
    return {
        "signal_bar": signal_bar,
        "direction": direction,
        "entry_bar": entry_bar,
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
        "win": win,
    }


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
