"""
Layer 2: Feature engineering - extract direction/strength/acceleration and state/magnitude/recency.

Template A (continuous): Direction / Strength / Acceleration
Template B (discrete): State / Magnitude / Recency

Normalizes features to be scale-independent and regime-invariant.
"""

from __future__ import annotations
import pandas as pd
import numpy as np


def build_all_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract engineered features from raw indicators.
    
    Input: DataFrame with indicators from indicators.compute_all_indicators()
    Output: DataFrame with ~110 normalized, engineered features
    """
    # Make a copy to avoid fragmentation issues
    df = df.copy()
    
    # Apply each feature extraction function
    df = trend_features(df)
    df = momentum_features(df)
    df = volatility_features(df)
    df = market_structure_features(df)
    
    if "volume" in df.columns and df["volume"].sum() > 0:
        df = volume_features(df)
    
    df = mean_reversion_features(df)
    df = regime_features(df)
    df = price_action_features(df)
    df = liquidity_smc_features(df)
    df = time_session_features(df)
    
    # Defragment the DataFrame at the end
    return df.copy()


def trend_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Template A: Direction / Strength / Acceleration
    
    Trend category features:
    - Direction: Is price trending up/down?
    - Strength: How strong is the trend?
    - Acceleration: Is trend strengthening or weakening?
    """
    
    # EMA direction (relative to price)
    for period in [20, 50, 200]:
        if f"ema_{period}" in df.columns:
            df[f"ema{period}_direction"] = np.sign(df["close"] - df[f"ema_{period}"])
            df[f"ema{period}_distance_pct"] = (df["close"] - df[f"ema_{period}"]) / df[f"ema_{period}"]
    
    # EMA alignment (trend consistency)
    if all(f"ema_{p}" in df.columns for p in [20, 50, 200]):
        df["ema_alignment"] = (
            (df["ema_20"] > df["ema_50"]).astype(int) +
            (df["ema_50"] > df["ema_200"]).astype(int) - 1  # Range: -1 to 1
        )
    
    # ADX strength (percentile rank to normalize)
    if "adx" in df.columns:
        df["adx_strength"] = _percentile_rank(df["adx"], 50)
        df["adx_change"] = df["adx"].diff()
        df["adx_direction"] = np.sign(df["adx_change"])
        
        # DI difference
        if "di_plus" in df.columns and "di_minus" in df.columns:
            df["di_diff"] = df["di_plus"] - df["di_minus"]
            df["di_diff_normalized"] = df["di_diff"] / 100.0  # DI is 0-100
    
    # Aroon
    if "aroon_up" in df.columns and "aroon_down" in df.columns:
        df["aroon_direction"] = np.sign(df["aroon_up"] - df["aroon_down"])
        df["aroon_strength"] = abs(df["aroon_up"] - df["aroon_down"]) / 100.0
    
    # Vortex
    if "vortex_pos" in df.columns and "vortex_neg" in df.columns:
        df["vortex_direction"] = np.sign(df["vortex_pos"] - df["vortex_neg"])
        df["vortex_strength"] = abs(df["vortex_pos"] - df["vortex_neg"])
    
    # SuperTrend
    if "supertrend_direction" in df.columns:
        df["supertrend_dir"] = df["supertrend_direction"]  # Already -1/1
        
        if "supertrend" in df.columns:
            df["supertrend_distance_pct"] = (df["close"] - df["supertrend"]) / df["supertrend"]
    
    # Linear regression slope (already an angle)
    if "linreg_slope_20" in df.columns:
        df["linreg_direction"] = np.sign(df["linreg_slope_20"])
        df["linreg_strength"] = abs(df["linreg_slope_20"]) / 45.0  # Normalize by 45 degrees
    
    # MACD
    if "macd" in df.columns and "macd_signal" in df.columns:
        df["macd_direction"] = np.sign(df["macd"] - df["macd_signal"])
        df["macd_strength"] = abs(df["macd"] - df["macd_signal"])
        
        if "macd_hist" in df.columns:
            df["macd_acceleration"] = np.sign(df["macd_hist"].diff())
    
    return df


def momentum_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Template A: Direction / Strength / Acceleration
    
    Momentum features:
    - Direction: Above/below neutral (50 for RSI, 0 for oscillators)
    - Strength: Distance from neutral
    - Acceleration: Rate of change
    """
    
    # RSI
    for period in [7, 14, 21]:
        col = f"rsi_{period}"
        if col in df.columns:
            df[f"rsi{period}_direction"] = np.sign(df[col] - 50)
            df[f"rsi{period}_distance_50"] = (df[col] - 50) / 50.0  # Normalize to [-1, 1]
            df[f"rsi{period}_change"] = df[col].diff()
            
            # Extreme zones
            df[f"rsi{period}_oversold"] = (df[col] < 30).astype(int)
            df[f"rsi{period}_overbought"] = (df[col] > 70).astype(int)
    
    # Stochastic
    if "stoch_k" in df.columns:
        df["stoch_direction"] = np.sign(df["stoch_k"] - 50)
        df["stoch_distance_50"] = (df["stoch_k"] - 50) / 50.0
        
        if "stoch_d" in df.columns:
            df["stoch_divergence"] = df["stoch_k"] - df["stoch_d"]
            df["stoch_cross_direction"] = np.sign(df["stoch_divergence"])
    
    # CCI
    if "cci" in df.columns:
        df["cci_direction"] = np.sign(df["cci"])
        df["cci_strength"] = np.clip(df["cci"] / 200.0, -1, 1)  # CCI typically -200 to +200
        df["cci_extreme"] = (abs(df["cci"]) > 100).astype(int)
    
    # ROC
    for period in [10, 20]:
        col = f"roc_{period}"
        if col in df.columns:
            df[f"roc{period}_direction"] = np.sign(df[col])
            df[f"roc{period}_strength"] = np.clip(df[col] / 10.0, -1, 1)  # Normalize
    
    # Williams %R
    if "willr" in df.columns:
        df["willr_direction"] = np.sign(df["willr"] + 50)  # %R is -100 to 0
        df["willr_normalized"] = (df["willr"] + 50) / 50.0
    
    return df


def volatility_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Template A: Direction / Strength / Acceleration
    
    Volatility features:
    - Direction: Expanding/contracting
    - Strength: Current volatility level (percentile)
    - Acceleration: Rate of change
    """
    
    # ATR
    for period in [7, 14, 21]:
        col = f"atr_{period}"
        if col in df.columns:
            # Percentile rank (normalized)
            df[f"atr{period}_percentile"] = _percentile_rank(df[col], 50)
            
            # Rate of change
            df[f"atr{period}_change"] = df[col].pct_change()
            df[f"atr{period}_direction"] = np.sign(df[f"atr{period}_change"])
            
            # Relative to price (normalize across symbols)
            df[f"atr{period}_relative"] = df[col] / df["close"]
    
    # Bollinger Bands
    if "bb_percent" in df.columns:
        # %B: where price is within the bands (0 = lower, 1 = upper)
        df["bb_position"] = df["bb_percent"]
        df["bb_extreme_upper"] = (df["bb_percent"] > 0.8).astype(int)
        df["bb_extreme_lower"] = (df["bb_percent"] < 0.2).astype(int)
    
    if "bb_width" in df.columns:
        df["bb_width_percentile"] = _percentile_rank(df["bb_width"], 50)
        df["bb_width_change"] = df["bb_width"].pct_change()
        df["bb_squeeze"] = (df["bb_width_percentile"] < 0.2).astype(int)
    
    # Historical Volatility
    if "hv_20" in df.columns:
        df["hv20_percentile"] = _percentile_rank(df["hv_20"], 50)
        df["hv20_direction"] = np.sign(df["hv_20"].diff())
    
    # Squeeze indicator
    if "squeeze" in df.columns:
        df["squeeze_active"] = df["squeeze"]
        df["bars_since_squeeze"] = _bars_since_event(df["squeeze"] == 1)
    
    # Choppiness Index
    if "chop" in df.columns:
        df["chop_direction"] = np.sign(50 - df["chop"])  # <50 = trending, >50 = choppy
        df["chop_normalized"] = df["chop"] / 100.0
    
    return df


def market_structure_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Template B: State / Magnitude / Recency
    
    Market structure features:
    - State: Current structure bias (bullish/bearish)
    - Magnitude: Swing size
    - Recency: Bars since last structural event
    """
    
    # Structure bias
    if "structure_bias" in df.columns:
        df["structure_bias_current"] = df["structure_bias"]
    
    # Swing range (normalized by ATR)
    if "swing_high" in df.columns and "swing_low" in df.columns:
        swing_range = df["swing_high"] - df["swing_low"]
        
        if "atr_14" in df.columns:
            df["swing_range_atr"] = swing_range / (df["atr_14"] + 1e-9)
        
        # Position within swing range
        df["position_in_swing"] = (df["close"] - df["swing_low"]) / (swing_range + 1e-9)
    
    # Pivot recency
    for length in [1, 2, 5]:
        ph_col = f"pivot_high_{length}"
        pl_col = f"pivot_low_{length}"
        
        if ph_col in df.columns:
            df[f"bars_since_pivot_high_{length}"] = _bars_since_event(df[ph_col].notna())
        
        if pl_col in df.columns:
            df[f"bars_since_pivot_low_{length}"] = _bars_since_event(df[pl_col].notna())
    
    # Distance from recent swing points
    if "swing_high" in df.columns:
        df["distance_from_swing_high"] = (df["close"] - df["swing_high"]) / df["close"]
    
    if "swing_low" in df.columns:
        df["distance_from_swing_low"] = (df["close"] - df["swing_low"]) / df["close"]
    
    return df


def volume_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Template A: Direction / Strength / Acceleration
    
    Volume features:
    - Direction: Increasing/decreasing participation
    - Strength: Relative volume
    - Acceleration: Rate of change
    """
    
    # OBV
    if "obv" in df.columns:
        df["obv_direction"] = np.sign(df["obv"].diff())
        
        # OBV trend (EMA)
        obv_ema = df["obv"].ewm(span=20).mean()
        df["obv_trend_direction"] = np.sign(df["obv"] - obv_ema)
    
    # Volume ratio (relative to average)
    if "volume_ratio" in df.columns:
        df["volume_strength"] = np.clip(df["volume_ratio"], 0, 3) / 3.0  # Normalize
        df["volume_spike"] = (df["volume_ratio"] > 2).astype(int)
        df["volume_dry"] = (df["volume_ratio"] < 0.5).astype(int)
    
    # MFI
    if "mfi" in df.columns:
        df["mfi_direction"] = np.sign(df["mfi"] - 50)
        df["mfi_distance_50"] = (df["mfi"] - 50) / 50.0
        df["mfi_overbought"] = (df["mfi"] > 80).astype(int)
        df["mfi_oversold"] = (df["mfi"] < 20).astype(int)
    
    # CMF
    if "cmf" in df.columns:
        df["cmf_direction"] = np.sign(df["cmf"])
        df["cmf_strength"] = np.clip(df["cmf"] * 2, -1, 1)  # CMF typically -0.5 to +0.5
    
    return df


def mean_reversion_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Template A: Direction / Strength / Acceleration
    
    Mean reversion features:
    - Direction: Extended/contracted relative to mean
    - Strength: Degree of extension
    - Acceleration: Rate of return toward mean
    """
    
    # Z-scores
    for period in [20, 50]:
        col = f"zscore_{period}"
        if col in df.columns:
            df[f"zscore{period}_direction"] = np.sign(df[col])
            df[f"zscore{period}_strength"] = np.clip(abs(df[col]) / 2.0, 0, 1)  # Normalize
            df[f"zscore{period}_extreme"] = (abs(df[col]) > 2).astype(int)
            df[f"zscore{period}_change"] = df[col].diff()
    
    # Distance from EMA
    for period in [20, 50]:
        col = f"distance_ema_{period}_pct"
        if col in df.columns:
            df[f"ema{period}_deviation_direction"] = np.sign(df[col])
            df[f"ema{period}_deviation_strength"] = np.clip(abs(df[col]) * 20, 0, 1)
    
    # Hurst exponent
    if "hurst_100" in df.columns:
        df["hurst_mean_reverting"] = (df["hurst_100"] < 0.5).astype(int)
        df["hurst_trending"] = (df["hurst_100"] > 0.5).astype(int)
        df["hurst_deviation_from_random"] = df["hurst_100"] - 0.5
    
    return df


def regime_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Template B: State / Magnitude / Recency
    
    Regime features:
    - State: Current regime classification
    - Magnitude: Regime strength
    - Recency: Bars since regime change
    """
    
    # Trending regime
    if "regime_trending" in df.columns:
        df["regime_is_trending"] = df["regime_trending"]
        df["bars_since_trend_start"] = _bars_since_event(
            (df["regime_trending"] == 1) & (df["regime_trending"].shift(1) == 0)
        )
        df["bars_since_range_start"] = _bars_since_event(
            (df["regime_trending"] == 0) & (df["regime_trending"].shift(1) == 1)
        )
    
    # Volatility regime
    if "regime_high_vol" in df.columns:
        df["regime_is_high_vol"] = df["regime_high_vol"]
        df["bars_since_vol_spike"] = _bars_since_event(
            (df["regime_high_vol"] == 1) & (df["regime_high_vol"].shift(1) == 0)
        )
    
    # Bull/bear regime
    if "regime_bull" in df.columns:
        df["regime_is_bull"] = df["regime_bull"]
        df["bars_since_regime_change"] = _bars_since_event(
            df["regime_bull"] != df["regime_bull"].shift(1)
        )
    
    return df


def price_action_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Template B: State / Magnitude / Recency
    
    Price action features:
    - State: Candle type
    - Magnitude: Size relative to recent candles
    - Recency: Bars since last pattern
    """
    
    # Candle body relative to ATR
    if "candle_body" in df.columns and "atr_14" in df.columns:
        df["body_size_relative_to_atr"] = df["candle_body"] / (df["atr_14"] + 1e-9)
        df["large_body"] = (df["body_size_relative_to_atr"] > 1.5).astype(int)
    
    # Candle range relative to ATR
    if "candle_range" in df.columns and "atr_14" in df.columns:
        df["range_size_relative_to_atr"] = df["candle_range"] / (df["atr_14"] + 1e-9)
    
    # Body/wick ratios
    if "body_to_range_ratio" in df.columns:
        df["body_dominance"] = df["body_to_range_ratio"]
        df["doji"] = (df["body_to_range_ratio"] < 0.1).astype(int)
    
    if "upper_wick_to_range" in df.columns:
        df["upper_wick_dominance"] = df["upper_wick_to_range"]
        df["hammer_like"] = ((df["upper_wick_to_range"] < 0.3) & 
                             (df["lower_wick_to_range"] > 0.5)).astype(int)
    
    # Consecutive candles
    if "consecutive_bull" in df.columns:
        df["bull_streak"] = df["consecutive_bull"]
        df["strong_bull_streak"] = (df["consecutive_bull"] >= 3).astype(int)
    
    if "consecutive_bear" in df.columns:
        df["bear_streak"] = df["consecutive_bear"]
        df["strong_bear_streak"] = (df["consecutive_bear"] >= 3).astype(int)
    
    # Engulfing patterns
    if "engulfing_bull" in df.columns:
        df["engulfing_bull_signal"] = df["engulfing_bull"]
        df["bars_since_bull_engulf"] = _bars_since_event(df["engulfing_bull"] == 1)
    
    if "engulfing_bear" in df.columns:
        df["engulfing_bear_signal"] = df["engulfing_bear"]
        df["bars_since_bear_engulf"] = _bars_since_event(df["engulfing_bear"] == 1)
    
    return df


def liquidity_smc_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Template B: State / Magnitude / Recency
    
    Liquidity/SMC features:
    - State: Inside FVG, near equal levels
    - Magnitude: Gap/sweep size
    - Recency: Bars since last liquidity event
    """
    
    # Fair Value Gaps
    if "fvg_bull" in df.columns:
        df["inside_bull_fvg"] = df["fvg_bull"]
        df["bars_since_bull_fvg"] = _bars_since_event(df["fvg_bull"] == 1)
    
    if "fvg_bear" in df.columns:
        df["inside_bear_fvg"] = df["fvg_bear"]
        df["bars_since_bear_fvg"] = _bars_since_event(df["fvg_bear"] == 1)
    
    # Equal highs/lows
    if "equal_highs" in df.columns:
        df["at_equal_highs"] = df["equal_highs"]
        df["bars_since_equal_highs"] = _bars_since_event(df["equal_highs"] == 1)
    
    if "equal_lows" in df.columns:
        df["at_equal_lows"] = df["equal_lows"]
        df["bars_since_equal_lows"] = _bars_since_event(df["equal_lows"] == 1)
    
    # Liquidity sweeps
    if "sweep_high" in df.columns:
        df["sweep_high_occurred"] = df["sweep_high"]
        df["bars_since_sweep_high"] = _bars_since_event(df["sweep_high"] == 1)
    
    if "sweep_low" in df.columns:
        df["sweep_low_occurred"] = df["sweep_low"]
        df["bars_since_sweep_low"] = _bars_since_event(df["sweep_low"] == 1)
    
    # Previous day high/low distance
    if "pdh" in df.columns:
        df["distance_from_pdh"] = (df["close"] - df["pdh"]) / df["close"]
    
    if "pdl" in df.columns:
        df["distance_from_pdl"] = (df["close"] - df["pdl"]) / df["close"]
    
    return df


def time_session_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Template B: State / Magnitude / Recency
    
    Time/session features (already cyclically encoded in indicators layer).
    """
    
    # Session features are already binary indicators
    # Just pass through the ones that exist
    session_cols = ["session_london", "session_ny", "session_tokyo", "session_overlap"]
    
    for col in session_cols:
        if col in df.columns:
            df[f"{col}_active"] = df[col]
    
    # Cyclical encodings (hour_sin, hour_cos, dow_sin, dow_cos) pass through unchanged
    
    return df


# ============================================================================
# Helper functions
# ============================================================================

def _percentile_rank(series: pd.Series, window: int) -> pd.Series:
    """
    Calculate rolling percentile rank (0 to 1).
    
    Current value's percentile relative to past window values.
    """
    return series.rolling(window).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) > 0 else np.nan,
        raw=True
    )


def _bars_since_event(condition: pd.Series) -> pd.Series:
    """
    Count bars since last True value in a boolean series.
    
    Returns 0 when condition is True, increments each bar after.
    """
    # Find indices where condition is True
    events = condition.astype(int)
    
    # Create cumulative counter that resets at each event
    result = pd.Series(np.nan, index=condition.index)
    last_event_idx = -1
    
    for i in range(len(condition)):
        if events.iloc[i]:
            result.iloc[i] = 0
            last_event_idx = i
        elif last_event_idx >= 0:
            result.iloc[i] = i - last_event_idx
    
    return result
