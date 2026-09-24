"""
Layer 1: Raw indicator computation across 10 categories.

Categories:
1. Trend
2. Momentum  
3. Volatility
4. Market Structure
5. Volume
6. Mean Reversion
7. Market Regime
8. Price Action
9. Liquidity / SMC
10. Time / Session

Uses pandas_ta for standard indicators where available.
"""

from __future__ import annotations
import pandas as pd
import numpy as np
import pandas_ta as ta


def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all raw indicators across 10 categories.
    
    Input: OHLCV DataFrame (time, open, high, low, close, volume)
    Output: DataFrame with original columns + ~150 indicator columns
    """
    df = df.copy()
    
    # Validate required columns
    required = {"open", "high", "low", "close"}
    if not required.issubset(df.columns):
        raise ValueError(f"DataFrame missing required columns: {required - set(df.columns)}")
    
    # Add each category
    df = add_trend_indicators(df)
    df = add_momentum_indicators(df)
    df = add_volatility_indicators(df)
    df = add_market_structure_raw(df)
    
    # Volume features (skip if no volume data)
    if "volume" in df.columns and df["volume"].sum() > 0:
        df = add_volume_indicators(df)
    
    df = add_mean_reversion_indicators(df)
    df = add_regime_indicators(df)
    df = add_price_action_raw(df)
    df = add_liquidity_smc_raw(df)
    df = add_time_session_raw(df)
    
    return df


def add_trend_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Category 1: Trend indicators (direction, strength)."""
    
    # Moving averages (multiple periods)
    for period in [10, 20, 50, 100, 200]:
        df[f"ema_{period}"] = ta.ema(df["close"], length=period)
        df[f"sma_{period}"] = ta.sma(df["close"], length=period)
    
    # ADX (trend strength)
    adx_df = ta.adx(df["high"], df["low"], df["close"], length=14)
    if adx_df is not None and not adx_df.empty:
        cols = adx_df.columns.tolist()
        adx_col = [c for c in cols if c.startswith("ADX")][0] if any(c.startswith("ADX") for c in cols) else None
        dmp_col = [c for c in cols if c.startswith("DMP")][0] if any(c.startswith("DMP") for c in cols) else None
        dmn_col = [c for c in cols if c.startswith("DMN") or c.startswith("DMM")][0] if any(c.startswith("DMN") or c.startswith("DMM") for c in cols) else None
        
        if adx_col: df["adx"] = adx_df[adx_col]
        if dmp_col: df["di_plus"] = adx_df[dmp_col]
        if dmn_col: df["di_minus"] = adx_df[dmn_col]
    
    # Aroon
    aroon_df = ta.aroon(df["high"], df["low"], length=25)
    if aroon_df is not None and not aroon_df.empty:
        cols = aroon_df.columns.tolist()
        up_col = [c for c in cols if "AROONU" in c][0] if any("AROONU" in c for c in cols) else None
        down_col = [c for c in cols if "AROOND" in c][0] if any("AROOND" in c for c in cols) else None
        
        if up_col: df["aroon_up"] = aroon_df[up_col]
        if down_col: df["aroon_down"] = aroon_df[down_col]
    
    # Vortex Indicator
    vortex_df = ta.vortex(df["high"], df["low"], df["close"], length=14)
    if vortex_df is not None and not vortex_df.empty:
        cols = vortex_df.columns.tolist()
        pos_col = [c for c in cols if "VTXP" in c][0] if any("VTXP" in c for c in cols) else None
        neg_col = [c for c in cols if "VTXM" in c][0] if any("VTXM" in c for c in cols) else None
        
        if pos_col: df["vortex_pos"] = vortex_df[pos_col]
        if neg_col: df["vortex_neg"] = vortex_df[neg_col]
    
    # SuperTrend
    supertrend_df = ta.supertrend(df["high"], df["low"], df["close"], length=10, multiplier=3.0)
    if supertrend_df is not None and not supertrend_df.empty:
        cols = supertrend_df.columns.tolist()
        st_col = [c for c in cols if "SUPERT_" in c and "SUPERTd" not in c][0] if any("SUPERT_" in c and "SUPERTd" not in c for c in cols) else None
        std_col = [c for c in cols if "SUPERTd" in c][0] if any("SUPERTd" in c for c in cols) else None
        
        if st_col: df["supertrend"] = supertrend_df[st_col]
        if std_col: df["supertrend_direction"] = supertrend_df[std_col]
    
    # Linear regression slope
    df["linreg_slope_20"] = ta.linreg(df["close"], length=20, angle=True)
    
    # MACD
    macd_df = ta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd_df is not None and not macd_df.empty:
        cols = macd_df.columns.tolist()
        macd_col = [c for c in cols if c.startswith("MACD_") and "MACDs" not in c and "MACDh" not in c][0] if any(c.startswith("MACD_") and "MACDs" not in c and "MACDh" not in c for c in cols) else None
        signal_col = [c for c in cols if "MACDs" in c][0] if any("MACDs" in c for c in cols) else None
        hist_col = [c for c in cols if "MACDh" in c][0] if any("MACDh" in c for c in cols) else None
        
        if macd_col: df["macd"] = macd_df[macd_col]
        if signal_col: df["macd_signal"] = macd_df[signal_col]
        if hist_col: df["macd_hist"] = macd_df[hist_col]
    
    return df


def add_momentum_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Category 2: Momentum indicators (speed, acceleration)."""
    
    # RSI (multiple periods)
    for period in [7, 14, 21]:
        df[f"rsi_{period}"] = ta.rsi(df["close"], length=period)
    
    # Stochastic
    stoch_df = ta.stoch(df["high"], df["low"], df["close"], k=14, d=3)
    if stoch_df is not None and not stoch_df.empty:
        cols = stoch_df.columns.tolist()
        k_col = [c for c in cols if "STOCHk" in c][0] if any("STOCHk" in c for c in cols) else None
        d_col = [c for c in cols if "STOCHd" in c][0] if any("STOCHd" in c for c in cols) else None
        
        if k_col: df["stoch_k"] = stoch_df[k_col]
        if d_col: df["stoch_d"] = stoch_df[d_col]
    
    # CCI
    df["cci"] = ta.cci(df["high"], df["low"], df["close"], length=20)
    
    # ROC (Rate of Change)
    for period in [10, 20]:
        df[f"roc_{period}"] = ta.roc(df["close"], length=period)
    
    # Williams %R
    df["willr"] = ta.willr(df["high"], df["low"], df["close"], length=14)
    
    # Ultimate Oscillator
    df["uo"] = ta.uo(df["high"], df["low"], df["close"])
    
    return df


def add_volatility_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Category 3: Volatility indicators (expansion/contraction)."""
    
    # ATR (multiple periods)
    for period in [7, 14, 21]:
        df[f"atr_{period}"] = ta.atr(df["high"], df["low"], df["close"], length=period)
    
    # Bollinger Bands
    bb_df = ta.bbands(df["close"], length=20, std=2)
    if bb_df is not None and not bb_df.empty:
        # Dynamically find column names (pandas_ta naming varies by version)
        cols = bb_df.columns.tolist()
        upper_col = [c for c in cols if c.startswith("BBU")][0] if any(c.startswith("BBU") for c in cols) else None
        middle_col = [c for c in cols if c.startswith("BBM")][0] if any(c.startswith("BBM") for c in cols) else None
        lower_col = [c for c in cols if c.startswith("BBL")][0] if any(c.startswith("BBL") for c in cols) else None
        width_col = [c for c in cols if c.startswith("BBB")][0] if any(c.startswith("BBB") for c in cols) else None
        percent_col = [c for c in cols if c.startswith("BBP")][0] if any(c.startswith("BBP") for c in cols) else None
        
        if upper_col: df["bb_upper"] = bb_df[upper_col]
        if middle_col: df["bb_middle"] = bb_df[middle_col]
        if lower_col: df["bb_lower"] = bb_df[lower_col]
        if width_col: df["bb_width"] = bb_df[width_col]
        if percent_col: df["bb_percent"] = bb_df[percent_col]
    
    # Historical Volatility
    df["hv_20"] = df["close"].pct_change().rolling(20).std() * np.sqrt(252)
    df["hv_50"] = df["close"].pct_change().rolling(50).std() * np.sqrt(252)
    
    # Keltner Channels
    kc_df = ta.kc(df["high"], df["low"], df["close"], length=20, scalar=2)
    if kc_df is not None and not kc_df.empty:
        # Dynamically find column names
        cols = kc_df.columns.tolist()
        upper_col = [c for c in cols if "KCU" in c][0] if any("KCU" in c for c in cols) else None
        middle_col = [c for c in cols if "KCB" in c][0] if any("KCB" in c for c in cols) else None
        lower_col = [c for c in cols if "KCL" in c][0] if any("KCL" in c for c in cols) else None
        
        if upper_col: df["kc_upper"] = kc_df[upper_col]
        if middle_col: df["kc_middle"] = kc_df[middle_col]
        if lower_col: df["kc_lower"] = kc_df[lower_col]
    
    # Squeeze indicator (BB inside KC)
    if "bb_upper" in df.columns and "kc_upper" in df.columns:
        df["squeeze"] = ((df["bb_upper"] < df["kc_upper"]) & 
                        (df["bb_lower"] > df["kc_lower"])).astype(int)
    
    # Choppiness Index
    df["chop"] = ta.chop(df["high"], df["low"], df["close"], length=14)
    
    return df


def add_market_structure_raw(df: pd.DataFrame) -> pd.DataFrame:
    """Category 4: Market structure (swing highs/lows, BOS, CHOCH)."""
    
    # Pivot highs/lows with different lengths
    for length in [1, 2, 5]:
        df[f"pivot_high_{length}"] = _detect_pivot_high(df["high"].values, length)
        df[f"pivot_low_{length}"] = _detect_pivot_low(df["low"].values, length)
    
    # Swing highs/lows (running max/min between pivots)
    df["swing_high"] = df["high"].rolling(20, min_periods=1).max()
    df["swing_low"] = df["low"].rolling(20, min_periods=1).min()
    
    # Structure bias (simple: price above/below midpoint)
    df["structure_midpoint"] = (df["swing_high"] + df["swing_low"]) / 2
    df["structure_bias"] = np.where(df["close"] > df["structure_midpoint"], 1, -1)
    
    return df


def add_volume_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Category 5: Volume indicators (participation, money flow)."""
    
    # OBV
    df["obv"] = ta.obv(df["close"], df["volume"])
    
    # Volume SMA
    df["volume_sma_20"] = ta.sma(df["volume"], length=20)
    
    # VWAP (approximation using cumulative)
    df["vwap"] = (df["close"] * df["volume"]).cumsum() / df["volume"].cumsum()
    
    # MFI (Money Flow Index)
    df["mfi"] = ta.mfi(df["high"], df["low"], df["close"], df["volume"], length=14)
    
    # CMF (Chaikin Money Flow)
    df["cmf"] = ta.cmf(df["high"], df["low"], df["close"], df["volume"], length=20)
    
    # Volume relative to average
    df["volume_ratio"] = df["volume"] / df["volume_sma_20"]
    
    return df


def add_mean_reversion_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Category 6: Mean reversion (distance from mean, extremes)."""
    
    # Z-score relative to moving average
    for period in [20, 50]:
        ma = df["close"].rolling(period).mean()
        std = df["close"].rolling(period).std()
        df[f"zscore_{period}"] = (df["close"] - ma) / (std + 1e-9)
    
    # Distance from EMA as percentage
    for period in [20, 50]:
        if f"ema_{period}" in df.columns:
            df[f"distance_ema_{period}_pct"] = (df["close"] - df[f"ema_{period}"]) / df[f"ema_{period}"]
    
    # Hurst exponent (long-term mean reversion tendency)
    df["hurst_100"] = df["close"].rolling(100).apply(_hurst_exponent, raw=True)
    
    return df


def add_regime_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Category 7: Market regime classification."""
    
    # Trend vs range regime (using ADX)
    if "adx" in df.columns:
        df["regime_trending"] = (df["adx"] > 25).astype(int)
    
    # Volatility regime (high/low vol)
    if "atr_14" in df.columns:
        atr_ma = df["atr_14"].rolling(50).mean()
        df["regime_high_vol"] = (df["atr_14"] > atr_ma * 1.2).astype(int)
    
    # Bull/bear regime (price vs long MA)
    if "ema_200" in df.columns:
        df["regime_bull"] = (df["close"] > df["ema_200"]).astype(int)
    
    return df


def add_price_action_raw(df: pd.DataFrame) -> pd.DataFrame:
    """Category 8: Price action patterns (candle geometry)."""
    
    # Candle components
    df["candle_body"] = abs(df["close"] - df["open"])
    df["candle_range"] = df["high"] - df["low"]
    df["candle_upper_wick"] = df["high"] - df[["open", "close"]].max(axis=1)
    df["candle_lower_wick"] = df[["open", "close"]].min(axis=1) - df["low"]
    
    # Relative sizes
    df["body_to_range_ratio"] = df["candle_body"] / (df["candle_range"] + 1e-9)
    df["upper_wick_to_range"] = df["candle_upper_wick"] / (df["candle_range"] + 1e-9)
    df["lower_wick_to_range"] = df["candle_lower_wick"] / (df["candle_range"] + 1e-9)
    
    # Candle direction
    df["candle_bullish"] = (df["close"] > df["open"]).astype(int)
    
    # Consecutive bars
    df["consecutive_bull"] = _consecutive_count(df["candle_bullish"] == 1)
    df["consecutive_bear"] = _consecutive_count(df["candle_bullish"] == 0)
    
    # Engulfing patterns (simple)
    bull_engulf = ((df["candle_bullish"] == 1) & 
                   (df["candle_bullish"].shift(1) == 0) &
                   (df["close"] > df["open"].shift(1)) &
                   (df["open"] < df["close"].shift(1)))
    df["engulfing_bull"] = bull_engulf.astype(int)
    
    bear_engulf = ((df["candle_bullish"] == 0) & 
                   (df["candle_bullish"].shift(1) == 1) &
                   (df["close"] < df["open"].shift(1)) &
                   (df["open"] > df["close"].shift(1)))
    df["engulfing_bear"] = bear_engulf.astype(int)
    
    return df


def add_liquidity_smc_raw(df: pd.DataFrame) -> pd.DataFrame:
    """Category 9: Liquidity concepts (FVG, equal highs/lows, sweeps)."""
    
    # Fair Value Gaps (3-candle imbalance), flagged on the candle that completes the
    # pattern so only closed bars are used
    bull_fvg = df["low"] > df["high"].shift(2)
    bear_fvg = df["high"] < df["low"].shift(2)
    df["fvg_bull"] = bull_fvg.astype(int)
    df["fvg_bear"] = bear_fvg.astype(int)
    
    # Equal highs/lows (within tolerance)
    tolerance = 0.001  # 0.1%
    equal_highs = abs(df["high"] - df["high"].shift(1)) / df["high"] < tolerance
    equal_lows = abs(df["low"] - df["low"].shift(1)) / df["low"] < tolerance
    df["equal_highs"] = equal_highs.astype(int)
    df["equal_lows"] = equal_lows.astype(int)
    
    # Liquidity sweeps (break above recent high then reverse)
    recent_high = df["high"].rolling(10).max().shift(1)
    recent_low = df["low"].rolling(10).min().shift(1)
    
    sweep_high = (df["high"] > recent_high) & (df["close"] < recent_high)
    sweep_low = (df["low"] < recent_low) & (df["close"] > recent_low)
    df["sweep_high"] = sweep_high.astype(int)
    df["sweep_low"] = sweep_low.astype(int)
    
    # Previous day high/low (for intraday data): the prior trading day in the data,
    # never the current day's still-forming range
    if "time" in df.columns:
        day = df["time"].dt.normalize()
        prev_high = df["high"].groupby(day).max().shift(1)
        prev_low = df["low"].groupby(day).min().shift(1)
        df["pdh"] = day.map(prev_high).to_numpy()
        df["pdl"] = day.map(prev_low).to_numpy()
    
    return df


def add_time_session_raw(df: pd.DataFrame) -> pd.DataFrame:
    """Category 10: Time and session features."""
    
    if "time" not in df.columns:
        return df
    
    # Ensure datetime
    if not pd.api.types.is_datetime64_any_dtype(df["time"]):
        df["time"] = pd.to_datetime(df["time"])
    
    # Hour of day (UTC)
    df["hour"] = df["time"].dt.hour
    
    # Day of week (0=Monday, 6=Sunday)
    df["dow"] = df["time"].dt.dayofweek
    
    # Cyclical encoding (for model input)
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["dow_sin"] = np.sin(2 * np.pi * df["dow"] / 7)
    df["dow_cos"] = np.cos(2 * np.pi * df["dow"] / 7)
    
    # Major forex sessions (UTC times, approximate)
    df["session_london"] = ((df["hour"] >= 8) & (df["hour"] < 16)).astype(int)
    df["session_ny"] = ((df["hour"] >= 13) & (df["hour"] < 21)).astype(int)
    df["session_tokyo"] = ((df["hour"] >= 0) & (df["hour"] < 8)).astype(int)
    df["session_overlap"] = (df["session_london"] & df["session_ny"]).astype(int)
    
    return df


# ============================================================================
# Helper functions
# ============================================================================

def _detect_pivot_high(high: np.ndarray, length: int) -> pd.Series:
    """
    Detect pivot highs with confirmation lag.
    
    A pivot high at index i requires:
    high[i] > high[i-k] AND high[i] > high[i+k] for all k in 1..length
    
    Returns NaN until confirmed (length bars later).
    """
    n = len(high)
    pivots = np.full(n, np.nan)
    
    for i in range(length, n - length):
        candidate = high[i]
        is_pivot = True
        
        # Check left side
        for k in range(1, length + 1):
            if high[i - k] >= candidate:
                is_pivot = False
                break
        
        if is_pivot:
            # Check right side
            for k in range(1, length + 1):
                if high[i + k] >= candidate:
                    is_pivot = False
                    break
        
        if is_pivot:
            pivots[i + length] = candidate  # Confirmed after length bars
    
    return pd.Series(pivots)


def _detect_pivot_low(low: np.ndarray, length: int) -> pd.Series:
    """Detect pivot lows (mirror of pivot high)."""
    n = len(low)
    pivots = np.full(n, np.nan)
    
    for i in range(length, n - length):
        candidate = low[i]
        is_pivot = True
        
        for k in range(1, length + 1):
            if low[i - k] <= candidate:
                is_pivot = False
                break
        
        if is_pivot:
            for k in range(1, length + 1):
                if low[i + k] <= candidate:
                    is_pivot = False
                    break
        
        if is_pivot:
            pivots[i + length] = candidate
    
    return pd.Series(pivots)


def _consecutive_count(condition: pd.Series) -> pd.Series:
    """Count consecutive True values in a boolean series."""
    groups = (condition != condition.shift()).cumsum()
    counts = condition.groupby(groups).cumsum()
    return counts * condition  # Zero out False streaks


def _hurst_exponent(prices: np.ndarray) -> float:
    """
    Estimate Hurst exponent (mean reversion tendency).
    
    H < 0.5: mean reverting
    H = 0.5: random walk
    H > 0.5: trending
    """
    if len(prices) < 20 or np.isnan(prices).any():
        return np.nan
    
    lags = range(2, min(20, len(prices) // 2))
    tau = []
    
    for lag in lags:
        pp = np.subtract(prices[lag:], prices[:-lag])
        tau.append(np.std(pp))
    
    if len(tau) < 2:
        return np.nan
    
    # Linear regression: log(tau) = H * log(lag) + const
    try:
        poly = np.polyfit(np.log(lags), np.log(tau), 1)
        return poly[0]
    except:
        return np.nan
