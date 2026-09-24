"""
ICC (Indication → Correction → Continuation) Strategy Implementation

Three-phase state machine:
1. Indication: HTF level broken
2. Correction: LTF pivot forms (trigger zone)
3. Continuation: Price breaks trigger zone → ENTRY

Matches ICC_Swing_EA_Simplified.mq5 behavior exactly.
"""

from __future__ import annotations
from typing import Optional
import pandas as pd
import numpy as np

from .config import StrategyConfig, SymbolSpec


def generate_icc_signals(
    df: pd.DataFrame,
    cfg: StrategyConfig,
    spec: SymbolSpec,
) -> pd.DataFrame:
    """
    Generate ICC strategy signals using the state machine.

    Args:
        df: OHLCV DataFrame
        cfg: Strategy configuration
        spec: Symbol specification

    Returns:
        DataFrame with columns:
        - signal: 1 (long), -1 (short), 0 (no signal)
        - signal_bar: Index where signal occurred
        - sl_price: Stop loss price
        - tp_price: Take profit price
        - stage: Current state machine stage
    """
    df = df.copy().reset_index(drop=True)

    # Initialize output columns
    n = len(df)
    signals = pd.DataFrame({
        "signal": np.zeros(n, dtype=int),
        "signal_bar": np.full(n, -1, dtype=int),
        "sl_price": np.full(n, np.nan),
        "tp_price": np.full(n, np.nan),
        "stage": np.zeros(n, dtype=int),
    }, index=df.index)

    # Detect pivots with confirmation lag
    htf_pivots = _detect_pivots(df, cfg.htf_pivot_len)
    ltf_pivots = _detect_pivots(df, cfg.ltf_pivot_len)

    # State machine variables (persistent across bars)
    stage = 0
    indication_extremum = np.nan
    trigger_zone = np.nan
    sl_level = np.nan

    # Current levels (updated as pivots confirm)
    htf_res = np.nan
    htf_sup = np.nan
    ltf_res = np.nan
    ltf_sup = np.nan

    # Process bar by bar
    for i in range(n):
        # Store previous levels (for crossover detection)
        htf_res_prev = htf_res
        htf_sup_prev = htf_sup
        trigger_zone_prev = trigger_zone

        # Update HTF levels (when new pivots confirm)
        if not np.isnan(htf_pivots["high"][i]):
            htf_res = htf_pivots["high"][i]
        if not np.isnan(htf_pivots["low"][i]):
            htf_sup = htf_pivots["low"][i]

        # Update LTF levels
        if not np.isnan(ltf_pivots["high"][i]):
            ltf_res = ltf_pivots["high"][i]
        if not np.isnan(ltf_pivots["low"][i]):
            ltf_sup = ltf_pivots["low"][i]

        close = df.loc[i, "close"]
        close_prev = df.loc[i-1, "close"] if i > 0 else close

        # ========================================
        # STAGE TRANSITIONS
        # ========================================

        # From neutral: check for indication (HTF break)
        if stage == 0:
            # Bullish indication: close crosses above HTF resistance
            if (not np.isnan(htf_res) and not np.isnan(htf_res_prev) and
                close_prev < htf_res_prev and close > htf_res):
                stage = 1
                indication_extremum = close
                trigger_zone = np.nan
                sl_level = np.nan

            # Bearish indication: close crosses below HTF support
            elif (not np.isnan(htf_sup) and not np.isnan(htf_sup_prev) and
                  close_prev > htf_sup_prev and close < htf_sup):
                stage = -1
                indication_extremum = close
                trigger_zone = np.nan
                sl_level = np.nan

        # From bullish indication: track high, wait for LTF pivot high
        elif stage == 1:
            # Track running max
            if not np.isnan(indication_extremum):
                indication_extremum = max(indication_extremum, df.loc[i, "high"])

            # LTF pivot high confirms → correction phase
            if not np.isnan(ltf_res):
                stage = 2
                trigger_zone = ltf_res

        # From bearish indication: track low, wait for LTF pivot low
        elif stage == -1:
            # Track running min
            if not np.isnan(indication_extremum):
                indication_extremum = min(indication_extremum, df.loc[i, "low"])

            # LTF pivot low confirms → correction phase
            if not np.isnan(ltf_sup):
                stage = -2
                trigger_zone = ltf_sup

        # Bullish correction phase
        elif stage == 2:
            # Invalidation: close breaks back below HTF support
            if not np.isnan(htf_sup) and close < htf_sup:
                stage = 0
                trigger_zone = np.nan
                sl_level = np.nan

            else:
                # Track stop loss: LTF pivot low that forms above HTF support
                if not np.isnan(ltf_sup) and not np.isnan(htf_sup):
                    if ltf_sup > htf_sup:
                        sl_level = ltf_sup

                # Update trigger zone: trail with new LTF pivot highs
                if not np.isnan(ltf_res):
                    trigger_zone = ltf_res

                # Entry condition: close crosses above trigger zone
                if (not np.isnan(trigger_zone) and not np.isnan(trigger_zone_prev) and
                    close_prev < trigger_zone_prev and close > trigger_zone):

                    # Only fire if we have a valid SL
                    if not np.isnan(sl_level) or not cfg.require_custom_swing_sl:
                        signals.loc[i, "signal"] = 1
                        signals.loc[i, "signal_bar"] = i
                        signals.loc[i, "sl_price"] = sl_level if not np.isnan(sl_level) else ltf_sup
                        signals.loc[i, "tp_price"] = close + spec.pips_to_price(cfg.tp_pips)

                        # Reset state machine
                        stage = 0
                        trigger_zone = np.nan
                        sl_level = np.nan

        # Bearish correction phase
        elif stage == -2:
            # Invalidation: close breaks back above HTF resistance
            if not np.isnan(htf_res) and close > htf_res:
                stage = 0
                trigger_zone = np.nan
                sl_level = np.nan

            else:
                # Track stop loss: LTF pivot high that forms below HTF resistance
                if not np.isnan(ltf_res) and not np.isnan(htf_res):
                    if ltf_res < htf_res:
                        sl_level = ltf_res

                # Update trigger zone: trail with new LTF pivot lows
                if not np.isnan(ltf_sup):
                    trigger_zone = ltf_sup

                # Entry condition: close crosses below trigger zone
                if (not np.isnan(trigger_zone) and not np.isnan(trigger_zone_prev) and
                    close_prev > trigger_zone_prev and close < trigger_zone):

                    # Only fire if we have a valid SL
                    if not np.isnan(sl_level) or not cfg.require_custom_swing_sl:
                        signals.loc[i, "signal"] = -1
                        signals.loc[i, "signal_bar"] = i
                        signals.loc[i, "sl_price"] = sl_level if not np.isnan(sl_level) else ltf_res
                        signals.loc[i, "tp_price"] = close - spec.pips_to_price(cfg.tp_pips)

                        # Reset state machine
                        stage = 0
                        trigger_zone = np.nan
                        sl_level = np.nan

        # Store current stage for diagnostics
        signals.loc[i, "stage"] = stage

    # Apply custom swing SL if configured
    if cfg.use_custom_swing_sl:
        signals = _apply_custom_swing_sl(df, signals, cfg, spec)

    return signals


def _detect_pivots(df: pd.DataFrame, length: int) -> pd.DataFrame:
    """
    Detect pivot highs and lows with confirmation lag.

    A pivot at bar i is confirmed L bars later (at bar i+L).
    This matches the EA's one-bar-at-a-time checking with shift(1+L).

    Returns DataFrame with columns: high, low (pivot prices, NaN where no pivot)
    """
    n = len(df)
    pivot_highs = np.full(n, np.nan)
    pivot_lows = np.full(n, np.nan)

    # Check each candidate position
    for i in range(length, n - length):
        # Pivot high: high[i] is highest in window [i-length, i+length]
        window_high = df["high"].iloc[i - length : i + length + 1]
        if df["high"].iloc[i] > window_high.drop(window_high.index[length]).max():
            # Confirmed at bar i + length
            pivot_highs[i + length] = df["high"].iloc[i]

        # Pivot low: low[i] is lowest in window
        window_low = df["low"].iloc[i - length : i + length + 1]
        if df["low"].iloc[i] < window_low.drop(window_low.index[length]).min():
            pivot_lows[i + length] = df["low"].iloc[i]

    return pd.DataFrame({"high": pivot_highs, "low": pivot_lows}, index=df.index)


def _apply_custom_swing_sl(
    df: pd.DataFrame,
    signals: pd.DataFrame,
    cfg: StrategyConfig,
    spec: SymbolSpec,
) -> pd.DataFrame:
    """
    Replace SL with swing point from a separate timeframe.

    For each signal, search the SL swing timeframe for the most recent
    confirmed swing high (for shorts) or low (for longs) on the correct
    side of entry.
    """
    # Resample to swing timeframe
    swing_df = _resample_to_timeframe(df, cfg.sl_swing_timeframe)

    # Detect swing pivots
    swing_pivots = _detect_pivots(swing_df, cfg.sl_swing_pivot_len)

    # For each signal, find appropriate swing level
    for i in signals[signals["signal"] != 0].index:
        direction = signals.loc[i, "signal"]
        entry_price = df.loc[i, "close"]
        signal_time = df.loc[i, "time"]

        # Find swing level
        swing_price = _find_swing_sl(
            swing_df, swing_pivots, signal_time, entry_price,
            direction, cfg.sl_max_candidates
        )

        if not np.isnan(swing_price):
            # Apply buffer
            if direction == 1:  # Long
                swing_price -= spec.pips_to_price(cfg.sl_buffer_pips)
            else:  # Short
                swing_price += spec.pips_to_price(cfg.sl_buffer_pips)

            signals.loc[i, "sl_price"] = swing_price

        elif cfg.require_custom_swing_sl:
            # No valid swing found and it's required → cancel signal
            signals.loc[i, "signal"] = 0

    return signals


def _resample_to_timeframe(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """
    Resample H1 data to a higher timeframe (H4, D1, etc.).

    Returns OHLC data at the target resolution.
    """
    if "time" not in df.columns:
        raise ValueError("DataFrame must have 'time' column for resampling")

    df = df.set_index("time")

    # Map timeframe string to pandas offset (lowercase for pandas >= 2.0)
    tf_map = {
        "1h": "1h", "4h": "4h", "1d": "1D", "1D": "1D",
        "H1": "1h", "H4": "4h", "D1": "1D",
    }
    offset = tf_map.get(timeframe.lower(), "4h")

    # Resample OHLC
    resampled = df.resample(offset).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }).dropna()

    return resampled.reset_index()


def _find_swing_sl(
    swing_df: pd.DataFrame,
    swing_pivots: pd.DataFrame,
    signal_time: pd.Timestamp,
    entry_price: float,
    direction: int,
    max_candidates: int,
) -> float:
    """
    Find the most recent confirmed swing point on the correct side of entry.

    Args:
        swing_df: Resampled OHLC data
        swing_pivots: Detected pivots
        signal_time: When the signal occurred
        entry_price: Entry price
        direction: 1 (long) or -1 (short)
        max_candidates: How many pivots to check

    Returns:
        Swing price, or NaN if no valid swing found
    """
    # Only consider pivots confirmed at or before signal time
    valid_mask = swing_df["time"] <= signal_time

    if direction == 1:
        # Long: need swing low below entry
        candidates = swing_pivots.loc[valid_mask, "low"].dropna()
        candidates = candidates[candidates < entry_price]

        if len(candidates) == 0:
            return np.nan

        # Most recent (last max_candidates)
        candidates = candidates.tail(max_candidates)

        # Return the most recent valid swing low
        return candidates.iloc[-1]

    else:
        # Short: need swing high above entry
        candidates = swing_pivots.loc[valid_mask, "high"].dropna()
        candidates = candidates[candidates > entry_price]

        if len(candidates) == 0:
            return np.nan

        candidates = candidates.tail(max_candidates)
        return candidates.iloc[-1]
