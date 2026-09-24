"""
Sequential single-account backtest with the EA's exact position blocking.

The ICC state machine is run bar by bar; each signal is simulated immediately,
and the position's exit bar is fed back so later setups are blocked exactly as
OnePositionAtATime does in the EA (a blocked setup keeps its state and can fire
once the position has closed).
"""

from __future__ import annotations
from typing import Callable, Optional

import numpy as np
import pandas as pd

from .config import StrategyConfig, ExecutionConfig, SymbolSpec
from .icc_labeling import market_arrays, simulate_position, _TRADE_COLUMNS
from .strategy_icc import generate_icc_signals


def run_sequential_backtest(
    df: pd.DataFrame,
    cfg: StrategyConfig,
    spec: SymbolSpec,
    exec_cfg: ExecutionConfig,
    take_signal: Optional[Callable[[int, int], bool]] = None,
) -> pd.DataFrame:
    """
    Backtest what one account running the EA would have traded.

    Args:
        df: OHLCV DataFrame (optional `spread` column in points)
        cfg: Strategy configuration
        spec: Symbol specification
        exec_cfg: Execution configuration
        take_signal: Optional filter(bar, direction) -> bool, e.g. the meta-model.
            A skipped signal opens no position (the state machine still resets,
            as it does when the EA sends no order).

    Returns:
        Trades in the same format as icc_labeling.simulate_icc_trades(). A position
        still open when the data ends blocks the rest of the data and is dropped.
    """
    df = df.reset_index(drop=True)
    m = market_arrays(df, spec)
    trades = []

    def on_signal(bar: int, direction: int, sl_price: float, atr: float) -> Optional[int]:
        if take_signal is not None and not take_signal(bar, direction):
            return None
        trade = simulate_position(m, bar, direction, sl_price, atr, cfg, spec, exec_cfg)
        if trade is None:
            return None
        if trade["exit_reason"] != "open_at_end":
            trades.append(trade)
        return trade["exit_bar"]

    generate_icc_signals(df, cfg, spec, on_signal=on_signal)
    return pd.DataFrame(trades, columns=_TRADE_COLUMNS)


def monthly_pnl(trades: pd.DataFrame, times: pd.Series, months: Optional[pd.PeriodIndex] = None) -> pd.Series:
    """
    Net pips per calendar month, keyed by the month the trade closed.

    Args:
        trades: Output of run_sequential_backtest()
        times: Bar timestamps of the backtested DataFrame
        months: Months to report (missing months are 0); defaults to the span of `times`
    """
    if months is None:
        months = pd.period_range(times.iloc[0], times.iloc[-1], freq="M")
    if len(trades) == 0:
        return pd.Series(0.0, index=months)
    closed = pd.to_datetime(times.to_numpy()[trades["exit_bar"].to_numpy()]).to_period("M")
    return trades.groupby(closed)["net_pips"].sum().reindex(months, fill_value=0.0)


def summarize_backtest(trades: pd.DataFrame, monthly: pd.Series) -> dict:
    """Headline statistics for a sequential backtest."""
    pnl = trades["net_pips"].to_numpy() if len(trades) else np.array([])
    equity = np.cumsum(pnl)
    drawdown = (np.maximum.accumulate(equity) - equity).max() if len(pnl) else 0.0
    gains, losses = pnl[pnl > 0].sum(), -pnl[pnl <= 0].sum()
    std = monthly.std(ddof=1)
    return {
        "n_trades": len(pnl),
        "net_pips": float(pnl.sum()),
        "win_rate": float((pnl > 0).mean()) if len(pnl) else np.nan,
        "profit_factor": float(gains / losses) if losses > 0 else np.inf,
        "avg_pips": float(pnl.mean()) if len(pnl) else np.nan,
        "max_drawdown_pips": float(drawdown),
        "monthly_sharpe": float(monthly.mean() / std) if std > 0 else np.nan,
        "months": len(monthly),
        "tp_rate": float((trades["exit_reason"] == "tp").mean()) if len(pnl) else np.nan,
        "long_share": float((trades["direction"] == 1).mean()) if len(pnl) else np.nan,
    }
