"""
ICC (Indication → Correction → Continuation) Strategy Implementation

Three-phase state machine:
1. Indication: HTF level broken
2. Correction: LTF pivot forms (trigger zone)
3. Continuation: Price breaks trigger zone → ENTRY

Bar-for-bar port of ProcessNewBar() in ICC_Swing_EA_Simplified.mq5. Each bar i is
processed as the EA processes "the bar that just closed" (shift 1). Section numbers
in comments refer to the EA source.

Known, intentional differences from the EA:
- Position blocking (OnePositionAtATime) is not applied here; every setup is emitted.
  While blocked, the EA leaves the stage untouched, so a blocked setup can fire again
  on a later bar. Apply blocking downstream when simulating one account.
- The EA validates the SL against the live ask/bid on the first tick of the next bar.
  That price is unknown at signal time, so the signal bar's close is used instead.
"""

from __future__ import annotations
import numpy as np
import pandas as pd

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
        - stage: State machine stage after processing the bar
    """
    df = df.copy().reset_index(drop=True)
    n = len(df)

    signal = np.zeros(n, dtype=int)
    signal_bar = np.full(n, -1, dtype=int)
    sl_out = np.full(n, np.nan)
    tp_out = np.full(n, np.nan)
    stage_out = np.zeros(n, dtype=int)

    close = df["close"].to_numpy(dtype=float)

    # Pivot prices placed on the bar where they confirm (NaN elsewhere)
    htf = _detect_pivots(df, cfg.htf_pivot_len)
    ltf = _detect_pivots(df, cfg.ltf_pivot_len)
    htf_ph, htf_pl = htf["high"].to_numpy(), htf["low"].to_numpy()
    ltf_ph, ltf_pl = ltf["high"].to_numpy(), ltf["low"].to_numpy()

    swing = None
    if cfg.use_custom_swing_sl:
        swing_df = _resample_to_timeframe(df, cfg.sl_swing_timeframe)
        swing = (
            swing_df["time"].to_numpy(),
            swing_df["high"].to_numpy(dtype=float),
            swing_df["low"].to_numpy(dtype=float),
        )
    bar_times = df["time"].to_numpy() if "time" in df.columns else None

    # Persistent state (EA section 2). NaN plays the role of the EA's has* flags.
    stage = 0
    trigger_zone = np.nan
    sl_level = np.nan
    htf_res = htf_sup = ltf_res = ltf_sup = np.nan

    for i in range(1, n):
        htf_res_prev, htf_sup_prev, trigger_zone_prev = htf_res, htf_sup, trigger_zone
        cl, cl_prev = close[i], close[i - 1]

        # Section 3: update levels from pivots confirming on this bar
        if not np.isnan(htf_ph[i]):
            htf_res = htf_ph[i]
        if not np.isnan(htf_pl[i]):
            htf_sup = htf_pl[i]
        new_ltf_high = not np.isnan(ltf_ph[i])
        new_ltf_low = not np.isnan(ltf_pl[i])
        if new_ltf_high:
            ltf_res = ltf_ph[i]
        if new_ltf_low:
            ltf_sup = ltf_pl[i]

        # Section 4a: indication breaks (a break can flip an opposite-side setup)
        bull_break = (not np.isnan(htf_res_prev) and not np.isnan(htf_res)
                      and cl_prev < htf_res_prev and cl > htf_res)
        bear_break = (not np.isnan(htf_sup_prev) and not np.isnan(htf_sup)
                      and cl_prev > htf_sup_prev and cl < htf_sup)
        if bull_break and stage <= 0:
            stage = 1
        if bear_break and stage >= 0:
            stage = -1

        # Switch to correction only on a newly confirmed LTF pivot
        if stage == 1 and new_ltf_high:
            stage = 2
            trigger_zone = ltf_res
        if stage == -1 and new_ltf_low:
            stage = -2
            trigger_zone = ltf_sup

        # Section 4b: invalidation, SL tracking, trailing trigger. Invalidation does not
        # skip the updates below, and trigger_zone / sl_level persist across setups.
        if stage == 2:
            if not np.isnan(htf_sup) and cl < htf_sup:
                stage = 0
            if new_ltf_low and not np.isnan(htf_sup) and ltf_sup > htf_sup:
                sl_level = ltf_sup
            if new_ltf_high:
                trigger_zone = ltf_res
        if stage == -2:
            if not np.isnan(htf_res) and cl > htf_res:
                stage = 0
            if new_ltf_high and not np.isnan(htf_res) and ltf_res < htf_res:
                sl_level = ltf_res
            if new_ltf_low:
                trigger_zone = ltf_sup

        # Section 5: entry trigger (requires an LTF sl_level, as the EA does)
        ready = (not np.isnan(trigger_zone_prev) and not np.isnan(trigger_zone)
                 and not np.isnan(sl_level))
        long_cond = stage == 2 and ready and cl_prev < trigger_zone_prev and cl > trigger_zone
        short_cond = stage == -2 and ready and cl_prev > trigger_zone_prev and cl < trigger_zone

        if long_cond or short_cond:
            direction = 1 if long_cond else -1
            final_sl = _resolve_swing_sl(
                direction, cl, sl_level, cfg, spec, swing,
                bar_times[i] if bar_times is not None else None,
            )
            # OpenTrade() refuses an SL on the wrong side of entry
            if not np.isnan(final_sl) and direction * (cl - final_sl) > 0:
                signal[i] = direction
                signal_bar[i] = i
                sl_out[i] = final_sl
                tp_out[i] = cl + direction * spec.pips_to_price(cfg.tp_pips)
            # The EA resets even when no order is sent
            stage = 0
            sl_level = np.nan

        stage_out[i] = stage

    return pd.DataFrame({
        "signal": signal,
        "signal_bar": signal_bar,
        "sl_price": sl_out,
        "tp_price": tp_out,
        "stage": stage_out,
    }, index=df.index)


def _detect_pivots(df: pd.DataFrame, length: int) -> pd.DataFrame:
    """
    Detect pivot highs and lows with confirmation lag.

    A pivot at bar i (strictly above/below the `length` bars on each side) is
    confirmed at bar i+length, matching the EA's GetPivotHigh/GetPivotLow.

    Returns DataFrame with columns: high, low (pivot prices, NaN where no pivot)
    """
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    n = len(df)
    pivot_highs = np.full(n, np.nan)
    pivot_lows = np.full(n, np.nan)

    if n > 2 * length:
        centre = slice(length, n - length)
        is_high = np.ones(n - 2 * length, dtype=bool)
        is_low = np.ones(n - 2 * length, dtype=bool)
        for k in range(1, length + 1):
            is_high &= (high[centre] > high[length - k:n - length - k]) & (high[centre] > high[length + k:n - length + k])
            is_low &= (low[centre] < low[length - k:n - length - k]) & (low[centre] < low[length + k:n - length + k])
        cand = np.arange(length, n - length)
        pivot_highs[cand[is_high] + length] = high[cand[is_high]]
        pivot_lows[cand[is_low] + length] = low[cand[is_low]]

    return pd.DataFrame({"high": pivot_highs, "low": pivot_lows}, index=df.index)


def _resolve_swing_sl(
    direction: int,
    entry_estimate: float,
    fallback_sl: float,
    cfg: StrategyConfig,
    spec: SymbolSpec,
    swing,
    as_of_time,
) -> float:
    """
    Port of the EA's ResolveSwingSL(): use the most recent confirmed swing on the SL
    timeframe if it lies on the correct side of entry, otherwise fall back to the
    LTF sl_level (or NaN when RequireCustomSwingSL rejects the signal).
    """
    if swing is None or as_of_time is None:
        return fallback_sl

    times, highs, lows = swing
    swing_price = _find_swing(
        times, lows if direction == 1 else highs, as_of_time,
        cfg.sl_swing_pivot_len, cfg.sl_max_candidates, find_high=(direction == -1),
    )
    if not np.isnan(swing_price):
        sl = swing_price - direction * spec.pips_to_price(cfg.sl_buffer_pips)
        if direction * (entry_estimate - sl) > 0:
            return sl

    if cfg.require_custom_swing_sl:
        return np.nan
    return fallback_sl


def _find_swing(
    times: np.ndarray,
    values: np.ndarray,
    as_of_time,
    length: int,
    max_candidates: int,
    find_high: bool,
) -> float:
    """
    Port of the EA's FindSwingHigh/FindSwingLow().

    Only bars that closed before the SL-timeframe bar containing `as_of_time` are
    read. Walks back from the newest candidate that has `length` closed bars on its
    right and returns the first pivot found, checking at most max_candidates + 1
    candidate bars. Returns NaN if none is found.
    """
    containing = np.searchsorted(times, np.datetime64(as_of_time), side="right") - 1
    newest_closed = containing - 1
    for k in range(max_candidates + 1):
        cand = newest_closed - length - k
        if cand - length < 0:
            return np.nan
        c = values[cand]
        neighbours = np.r_[values[cand - length:cand], values[cand + 1:cand + length + 1]]
        if (find_high and (c > neighbours).all()) or (not find_high and (c < neighbours).all()):
            return c
    return np.nan


# pandas offset for each supported SL timeframe (keys are lowercase)
_TIMEFRAME_OFFSETS = {
    "1h": "1h", "h1": "1h",
    "4h": "4h", "h4": "4h",
    "1d": "1D", "d1": "1D",
}


def _resample_to_timeframe(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """
    Resample H1 data to a higher timeframe (H4, D1, etc.).

    Returns OHLC data at the target resolution; bars are labelled by their open time.
    """
    if "time" not in df.columns:
        raise ValueError("DataFrame must have 'time' column for resampling")

    offset = _TIMEFRAME_OFFSETS.get(timeframe.lower())
    if offset is None:
        raise ValueError(
            f"Unsupported sl_swing_timeframe {timeframe!r}. Valid: {sorted(_TIMEFRAME_OFFSETS)}"
        )

    resampled = df.set_index("time").resample(offset).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }).dropna()

    return resampled.reset_index()
