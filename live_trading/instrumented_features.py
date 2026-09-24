"""
Instrumented wrapper for feature engineering with detailed logging.

Tracks progress for each feature transformation group:
- Direction features (sign/cross detection)
- Strength features (magnitude/percentile)
- Acceleration features (velocity/momentum)
- State features (regime/condition classification)
- Magnitude features (absolute values/ratios)
- Recency features (time since events)
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from icc_ml import features
from .pipeline_logger import get_pipeline_logger, OperationTimer

plogger = get_pipeline_logger()


def build_all_features_instrumented(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build all feature transformations with detailed progress logging.
    
    Args:
        df: DataFrame with OHLCV + indicators
    
    Returns:
        DataFrame with all feature transformations added
    """
    with OperationTimer(plogger, "FEATURES", "BuildAll", "Building all feature transformations") as timer:
        
        # Start with copy of input
        result = df.copy()
        initial_cols = len(result.columns)
        
        plogger.info("FEATURES", "Start", f"Building features from {len(df.columns)} input columns")
        
        # Track transformation-level computation
        transformations_computed = []
        
        # Direction Features
        with OperationTimer(plogger, "FEATURES", "Direction", "Computing direction features") as cat_timer:
            try:
                start_cols = len(result.columns)
                
                plogger.info("FEATURES", "Direction.Sign", "Computing indicator signs (above/below zero/neutral)")
                # RSI direction
                result["rsi_above_50"] = (result["rsi"] > 50).astype(int)
                result["rsi_above_70"] = (result["rsi"] > 70).astype(int)
                result["rsi_below_30"] = (result["rsi"] < 30).astype(int)
                
                # MACD direction
                result["macd_above_signal"] = (result["macd"] > result["macd_signal"]).astype(int)
                result["macd_positive"] = (result["macd"] > 0).astype(int)
                
                # ADX directional
                result["di_plus_above_di_minus"] = (result["di_plus"] > result["di_minus"]).astype(int)
                
                plogger.info("FEATURES", "Direction.Cross", "Detecting crossovers")
                # EMA crosses
                result["ema8_above_ema21"] = (result["ema_8"] > result["ema_21"]).astype(int)
                result["ema21_above_ema55"] = (result["ema_21"] > result["ema_55"]).astype(int)
                result["ema55_above_ema100"] = (result["ema_55"] > result["ema_100"]).astype(int)
                result["ema_golden_cross"] = ((result["ema_8"] > result["ema_21"]) & (result["ema_21"] > result["ema_55"])).astype(int)
                result["ema_death_cross"] = ((result["ema_8"] < result["ema_21"]) & (result["ema_21"] < result["ema_55"])).astype(int)
                
                # Price vs MA
                result["price_above_ema21"] = (result["close"] > result["ema_21"]).astype(int)
                result["price_above_ema55"] = (result["close"] > result["ema_55"]).astype(int)
                result["price_above_vwap"] = (result["close"] > result["vwap"]).astype(int)
                
                # Bollinger Bands position
                result["price_above_bb_upper"] = (result["close"] > result["bb_upper"]).astype(int)
                result["price_below_bb_lower"] = (result["close"] < result["bb_lower"]).astype(int)
                
                plogger.info("FEATURES", "Direction.Trend", "Computing trend direction signals")
                # SuperTrend direction
                result["supertrend_bullish"] = (result["supertrend_direction"] == 1).astype(int)
                
                # Linear regression slope direction
                result["linreg_slope_positive"] = (result["linreg_slope"] > 0).astype(int)
                
                # Aroon direction
                result["aroon_bullish"] = (result["aroon_up"] > result["aroon_down"]).astype(int)
                
                direction_cols = len(result.columns) - start_cols
                cat_timer.add_detail("features", direction_cols)
                transformations_computed.append(("Direction", direction_cols))
                plogger.success("FEATURES", "Direction", f"Computed {direction_cols} direction features")
                
            except Exception as e:
                plogger.error("FEATURES", "Direction", f"Failed: {e}")
                raise
        
        # Strength Features
        with OperationTimer(plogger, "FEATURES", "Strength", "Computing strength/magnitude features") as cat_timer:
            try:
                start_cols = len(result.columns)
                
                plogger.info("FEATURES", "Strength.Normalized", "Computing normalized strength indicators")
                # Normalize RSI to [-1, 1]
                result["rsi_normalized"] = (result["rsi"] - 50) / 50
                
                # Normalize Stochastic
                result["stoch_k_normalized"] = (result["stoch_k"] - 50) / 50
                
                # Normalize CCI to rough [-1, 1] range (clip extreme values)
                result["cci_normalized"] = result["cci"].clip(-200, 200) / 200
                
                plogger.info("FEATURES", "Strength.Percentile", "Computing percentile rankings")
                # ATR percentile (volatility strength)
                result["atr_pct_rank_20"] = result["atr_pct"].rolling(20).apply(lambda x: pd.Series(x).rank().iloc[-1] / len(x), raw=False)
                result["atr_pct_rank_50"] = result["atr_pct"].rolling(50).apply(lambda x: pd.Series(x).rank().iloc[-1] / len(x), raw=False)
                
                # Volume percentile
                result["volume_rank_20"] = result["volume"].rolling(20).apply(lambda x: pd.Series(x).rank().iloc[-1] / len(x), raw=False)
                
                plogger.info("FEATURES", "Strength.Magnitude", "Computing absolute magnitudes")
                # ADX strength (trend strength regardless of direction)
                result["adx_strength"] = result["adx"] / 100  # Normalize to [0, 1]
                
                # Distance from moving averages (magnitude)
                result["distance_ema21_abs"] = abs(result["distance_pct_ema21"])
                result["distance_ema55_abs"] = abs(result["distance_pct_ema55"])
                
                # MACD histogram magnitude
                result["macd_hist_abs"] = abs(result["macd_hist"])
                
                # Z-score magnitude
                result["zscore_20_abs"] = abs(result["zscore_20"])
                result["zscore_50_abs"] = abs(result["zscore_50"])
                
                plogger.info("FEATURES", "Strength.Ratios", "Computing strength ratios")
                # DI ratio (directional strength)
                result["di_ratio"] = result["di_plus"] / (result["di_minus"] + 1e-6)
                
                # Vortex ratio
                result["vortex_ratio"] = result["vortex_pos"] / (result["vortex_neg"] + 1e-6)
                
                # ATR to price ratio
                result["atr_to_price"] = result["atr"] / result["close"]
                
                strength_cols = len(result.columns) - start_cols
                cat_timer.add_detail("features", strength_cols)
                transformations_computed.append(("Strength", strength_cols))
                plogger.success("FEATURES", "Strength", f"Computed {strength_cols} strength features")
                
            except Exception as e:
                plogger.error("FEATURES", "Strength", f"Failed: {e}")
                raise
        
        # Acceleration Features
        with OperationTimer(plogger, "FEATURES", "Acceleration", "Computing acceleration/velocity features") as cat_timer:
            try:
                start_cols = len(result.columns)
                
                plogger.info("FEATURES", "Acceleration.Delta", "Computing period-over-period changes")
                # RSI momentum (change in RSI)
                result["rsi_delta_1"] = result["rsi"].diff(1)
                result["rsi_delta_5"] = result["rsi"].diff(5)
                
                # ADX momentum
                result["adx_delta_1"] = result["adx"].diff(1)
                result["adx_delta_5"] = result["adx"].diff(5)
                
                # ATR momentum (volatility acceleration)
                result["atr_pct_delta_1"] = result["atr_pct"].diff(1)
                result["atr_pct_delta_5"] = result["atr_pct"].diff(5)
                
                plogger.info("FEATURES", "Acceleration.RateOfChange", "Computing rate of change")
                # MACD acceleration (change in histogram)
                result["macd_hist_delta"] = result["macd_hist"].diff(1)
                result["macd_hist_acceleration"] = result["macd_hist_delta"].diff(1)
                
                # Price momentum
                result["roc_5"] = result["close"].pct_change(5) * 100
                result["roc_10"] = result["close"].pct_change(10) * 100
                result["roc_20"] = result["close"].pct_change(20) * 100
                
                plogger.info("FEATURES", "Acceleration.Velocity", "Computing velocity indicators")
                # EMA velocity (how fast EMAs are moving)
                result["ema21_velocity"] = result["ema_21"].pct_change(1) * 100
                result["ema55_velocity"] = result["ema_55"].pct_change(1) * 100
                
                # Distance velocity (rate of change in distance from MA)
                result["distance_ema21_velocity"] = result["distance_pct_ema21"].diff(1)
                
                acceleration_cols = len(result.columns) - start_cols
                cat_timer.add_detail("features", acceleration_cols)
                transformations_computed.append(("Acceleration", acceleration_cols))
                plogger.success("FEATURES", "Acceleration", f"Computed {acceleration_cols} acceleration features")
                
            except Exception as e:
                plogger.error("FEATURES", "Acceleration", f"Failed: {e}")
                raise
        
        # State Features
        with OperationTimer(plogger, "FEATURES", "State", "Computing state/regime classification features") as cat_timer:
            try:
                start_cols = len(result.columns)
                
                plogger.info("FEATURES", "State.Regime", "Encoding regime states")
                # Trend regime (already computed in indicators, encode)
                # regime_trend: 0=ranging, 1=trending_up, 2=trending_down
                result["regime_trend_ranging"] = (result["regime_trend"] == 0).astype(int)
                result["regime_trend_up"] = (result["regime_trend"] == 1).astype(int)
                result["regime_trend_down"] = (result["regime_trend"] == 2).astype(int)
                
                # Volatility regime
                # regime_volatility: 0=low, 1=normal, 2=high
                result["regime_vol_low"] = (result["regime_volatility"] == 0).astype(int)
                result["regime_vol_normal"] = (result["regime_volatility"] == 1).astype(int)
                result["regime_vol_high"] = (result["regime_volatility"] == 2).astype(int)
                
                plogger.info("FEATURES", "State.Condition", "Classifying market conditions")
                # Overbought/Oversold states
                result["state_overbought"] = ((result["rsi"] > 70) | (result["stoch_k"] > 80)).astype(int)
                result["state_oversold"] = ((result["rsi"] < 30) | (result["stoch_k"] < 20)).astype(int)
                
                # Squeeze state (low volatility)
                result["state_squeeze"] = (result["squeeze"] == 1).astype(int)
                
                # Strong trend state (ADX > 25 + directional agreement)
                result["state_strong_uptrend"] = ((result["adx"] > 25) & (result["di_plus"] > result["di_minus"]) & (result["close"] > result["ema_21"])).astype(int)
                result["state_strong_downtrend"] = ((result["adx"] > 25) & (result["di_plus"] < result["di_minus"]) & (result["close"] < result["ema_21"])).astype(int)
                
                plogger.info("FEATURES", "State.Structure", "Encoding market structure states")
                # Break of structure
                result["state_bos_bullish"] = (result["bos"] == 1).astype(int)
                result["state_bos_bearish"] = (result["bos"] == -1).astype(int)
                
                # Change of character
                result["state_choch"] = (result["choch"] != 0).astype(int)
                
                # Liquidity state
                result["state_liquidity_sweep_high"] = (result["sweep_high"] == 1).astype(int)
                result["state_liquidity_sweep_low"] = (result["sweep_low"] == 1).astype(int)
                
                plogger.info("FEATURES", "State.Session", "Session-based states")
                # Trading session states (already binary, just copy)
                # (session features already in indicators)
                
                state_cols = len(result.columns) - start_cols
                cat_timer.add_detail("features", state_cols)
                transformations_computed.append(("State", state_cols))
                plogger.success("FEATURES", "State", f"Computed {state_cols} state features")
                
            except Exception as e:
                plogger.error("FEATURES", "State", f"Failed: {e}")
                raise
        
        # Magnitude Features
        with OperationTimer(plogger, "FEATURES", "Magnitude", "Computing magnitude/scale features") as cat_timer:
            try:
                start_cols = len(result.columns)
                
                plogger.info("FEATURES", "Magnitude.Range", "Computing candle range metrics")
                # Candle body to range ratio (already in indicators, ensure exists)
                if "candle_body_pct" not in result.columns:
                    result["candle_body_pct"] = result["candle_body"] / result["candle_range"]
                
                # Wick ratios
                result["upper_wick_pct"] = result["upper_wick"] / result["candle_range"]
                result["lower_wick_pct"] = result["lower_wick"] / result["candle_range"]
                
                plogger.info("FEATURES", "Magnitude.Spread", "Computing spread/gap metrics")
                # Bollinger Band width (volatility measure)
                result["bb_width"] = (result["bb_upper"] - result["bb_lower"]) / result["bb_middle"]
                result["bb_percentb"] = (result["close"] - result["bb_lower"]) / (result["bb_upper"] - result["bb_lower"] + 1e-6)
                
                # EMA spread
                result["ema_spread_8_21"] = (result["ema_8"] - result["ema_21"]) / result["ema_21"]
                result["ema_spread_21_55"] = (result["ema_21"] - result["ema_55"]) / result["ema_55"]
                
                plogger.info("FEATURES", "Magnitude.Volume", "Computing volume magnitude metrics")
                # Volume ratio to average
                result["volume_ratio_20"] = result["volume"] / (result["volume"].rolling(20).mean() + 1e-6)
                
                # OBV momentum
                result["obv_normalized"] = result["obv"] / (result["obv"].rolling(50).max() + 1e-6)
                
                magnitude_cols = len(result.columns) - start_cols
                cat_timer.add_detail("features", magnitude_cols)
                transformations_computed.append(("Magnitude", magnitude_cols))
                plogger.success("FEATURES", "Magnitude", f"Computed {magnitude_cols} magnitude features")
                
            except Exception as e:
                plogger.error("FEATURES", "Magnitude", f"Failed: {e}")
                raise
        
        # Recency Features
        with OperationTimer(plogger, "FEATURES", "Recency", "Computing recency/time-since features") as cat_timer:
            try:
                start_cols = len(result.columns)
                
                plogger.info("FEATURES", "Recency.Events", "Computing bars since key events")
                # Bars since swing high/low
                result["bars_since_swing_high"] = features.bars_since_event(result["swing_high"].notna())
                result["bars_since_swing_low"] = features.bars_since_event(result["swing_low"].notna())
                
                # Bars since BOS
                result["bars_since_bos"] = features.bars_since_event(result["bos"] != 0)
                
                # Bars since CHOCH
                result["bars_since_choch"] = features.bars_since_event(result["choch"] != 0)
                
                plogger.info("FEATURES", "Recency.Crosses", "Computing bars since crossovers")
                # Bars since EMA cross
                ema8_above_21_changed = result["ema8_above_ema21"].diff() != 0
                result["bars_since_ema_cross"] = features.bars_since_event(ema8_above_21_changed)
                
                # Bars since MACD cross
                macd_cross = result["macd_above_signal"].diff() != 0
                result["bars_since_macd_cross"] = features.bars_since_event(macd_cross)
                
                plogger.info("FEATURES", "Recency.Extremes", "Computing bars since extreme readings")
                # Bars since RSI overbought/oversold
                result["bars_since_rsi_overbought"] = features.bars_since_event(result["rsi"] > 70)
                result["bars_since_rsi_oversold"] = features.bars_since_event(result["rsi"] < 30)
                
                # Bars since high volatility
                high_vol = result["atr_pct"] > result["atr_pct"].rolling(50).quantile(0.8)
                result["bars_since_high_vol"] = features.bars_since_event(high_vol)
                
                recency_cols = len(result.columns) - start_cols
                cat_timer.add_detail("features", recency_cols)
                transformations_computed.append(("Recency", recency_cols))
                plogger.success("FEATURES", "Recency", f"Computed {recency_cols} recency features")
                
            except Exception as e:
                plogger.error("FEATURES", "Recency", f"Failed: {e}")
                raise
        
        # Summary
        total_features = len(result.columns) - initial_cols
        timer.add_detail("total_features", total_features)
        timer.add_detail("transformation_groups", len(transformations_computed))
        timer.add_detail("bars", len(df))
        timer.add_detail("total_columns", len(result.columns))
        
        # Log breakdown
        breakdown = ", ".join([f"{trans}={count}" for trans, count in transformations_computed])
        plogger.success("FEATURES", "BuildAll", f"Built {total_features} features across {len(transformations_computed)} transformation groups")
        plogger.info("FEATURES", "Breakdown", breakdown)
        
        return result
