"""
Instrumented wrapper for indicators computation with detailed logging.

Tracks progress for each indicator category:
- Trend indicators
- Momentum indicators
- Volatility indicators
- Market structure
- Volume indicators
- Mean reversion
- Regime detection
- Price action patterns
- Liquidity/SMC
- Time-based features
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from icc_ml import indicators
from .pipeline_logger import get_pipeline_logger, OperationTimer

plogger = get_pipeline_logger()


def compute_all_indicators_instrumented(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all indicators with detailed progress logging.
    
    Args:
        df: OHLCV DataFrame
    
    Returns:
        DataFrame with all indicators added
    """
    with OperationTimer(plogger, "INDICATORS", "ComputeAll", "Computing all indicator categories") as timer:
        
        # Start with copy of input
        result = df.copy()
        initial_cols = len(result.columns)
        
        plogger.info("INDICATORS", "Start", f"Computing indicators on {len(df)} bars")
        
        # Track category-level computation
        categories_computed = []
        
        # Trend Indicators
        with OperationTimer(plogger, "INDICATORS", "Trend", "Computing trend indicators") as cat_timer:
            try:
                # EMA family
                plogger.info("INDICATORS", "Trend.EMA", "Computing EMA(8, 21, 55, 100, 200)")
                for period in [8, 21, 55, 100, 200]:
                    result[f"ema_{period}"] = indicators.ema(df["close"], period)
                
                # ADX and directional indicators
                plogger.info("INDICATORS", "Trend.ADX", "Computing ADX and DI+/DI-")
                adx_df = indicators.adx(df["high"], df["low"], df["close"], period=14)
                for col in adx_df.columns:
                    result[col] = adx_df[col]
                
                # Aroon
                plogger.info("INDICATORS", "Trend.Aroon", "Computing Aroon indicators")
                aroon_df = indicators.aroon(df["high"], df["low"], period=25)
                for col in aroon_df.columns:
                    result[col] = aroon_df[col]
                
                # Vortex
                plogger.info("INDICATORS", "Trend.Vortex", "Computing Vortex indicators")
                vortex_df = indicators.vortex(df["high"], df["low"], df["close"], period=14)
                for col in vortex_df.columns:
                    result[col] = vortex_df[col]
                
                # SuperTrend
                plogger.info("INDICATORS", "Trend.SuperTrend", "Computing SuperTrend")
                st_df = indicators.supertrend(df["high"], df["low"], df["close"], period=10, multiplier=3.0)
                for col in st_df.columns:
                    result[col] = st_df[col]
                
                # Linear Regression
                plogger.info("INDICATORS", "Trend.LinReg", "Computing linear regression trend")
                result["linreg_slope"] = indicators.linreg_slope(df["close"], period=20)
                result["linreg_angle"] = indicators.linreg_angle(df["close"], period=20)
                
                # MACD
                plogger.info("INDICATORS", "Trend.MACD", "Computing MACD")
                macd_df = indicators.macd(df["close"])
                for col in macd_df.columns:
                    result[col] = macd_df[col]
                
                trend_cols = len(result.columns) - initial_cols
                cat_timer.add_detail("features", trend_cols)
                categories_computed.append(("Trend", trend_cols))
                plogger.success("INDICATORS", "Trend", f"Computed {trend_cols} trend indicators")
                
            except Exception as e:
                plogger.error("INDICATORS", "Trend", f"Failed: {e}")
                raise
        
        # Momentum Indicators
        with OperationTimer(plogger, "INDICATORS", "Momentum", "Computing momentum indicators") as cat_timer:
            try:
                start_cols = len(result.columns)
                
                # RSI
                plogger.info("INDICATORS", "Momentum.RSI", "Computing RSI(14)")
                result["rsi"] = indicators.rsi(df["close"], period=14)
                
                # Stochastic
                plogger.info("INDICATORS", "Momentum.Stochastic", "Computing Stochastic oscillator")
                stoch_df = indicators.stochastic(df["high"], df["low"], df["close"], k_period=14, d_period=3)
                for col in stoch_df.columns:
                    result[col] = stoch_df[col]
                
                # CCI
                plogger.info("INDICATORS", "Momentum.CCI", "Computing CCI")
                result["cci"] = indicators.cci(df["high"], df["low"], df["close"], period=20)
                
                # ROC
                plogger.info("INDICATORS", "Momentum.ROC", "Computing Rate of Change")
                result["roc"] = indicators.roc(df["close"], period=10)
                
                # Williams %R
                plogger.info("INDICATORS", "Momentum.WilliamsR", "Computing Williams %R")
                result["willr"] = indicators.willr(df["high"], df["low"], df["close"], period=14)
                
                momentum_cols = len(result.columns) - start_cols
                cat_timer.add_detail("features", momentum_cols)
                categories_computed.append(("Momentum", momentum_cols))
                plogger.success("INDICATORS", "Momentum", f"Computed {momentum_cols} momentum indicators")
                
            except Exception as e:
                plogger.error("INDICATORS", "Momentum", f"Failed: {e}")
                raise
        
        # Volatility Indicators
        with OperationTimer(plogger, "INDICATORS", "Volatility", "Computing volatility indicators") as cat_timer:
            try:
                start_cols = len(result.columns)
                
                # ATR
                plogger.info("INDICATORS", "Volatility.ATR", "Computing ATR(14)")
                result["atr"] = indicators.atr(df["high"], df["low"], df["close"], period=14)
                result["atr_pct"] = result["atr"] / df["close"] * 100
                
                # Bollinger Bands
                plogger.info("INDICATORS", "Volatility.BB", "Computing Bollinger Bands")
                bb_df = indicators.bollinger_bands(df["close"], period=20, std=2.0)
                for col in bb_df.columns:
                    result[col] = bb_df[col]
                
                # Historical Volatility
                plogger.info("INDICATORS", "Volatility.HV", "Computing historical volatility")
                for period in [10, 20, 30]:
                    result[f"hv_{period}"] = indicators.historical_volatility(df["close"], period=period)
                
                # Squeeze indicator
                plogger.info("INDICATORS", "Volatility.Squeeze", "Computing squeeze indicator")
                result["squeeze"] = indicators.squeeze_indicator(df["high"], df["low"], df["close"])
                
                volatility_cols = len(result.columns) - start_cols
                cat_timer.add_detail("features", volatility_cols)
                categories_computed.append(("Volatility", volatility_cols))
                plogger.success("INDICATORS", "Volatility", f"Computed {volatility_cols} volatility indicators")
                
            except Exception as e:
                plogger.error("INDICATORS", "Volatility", f"Failed: {e}")
                raise
        
        # Market Structure
        with OperationTimer(plogger, "INDICATORS", "Structure", "Computing market structure") as cat_timer:
            try:
                start_cols = len(result.columns)
                
                plogger.info("INDICATORS", "Structure.Pivots", "Computing swing highs/lows")
                result["swing_high"] = indicators.swing_high(df["high"], period=5)
                result["swing_low"] = indicators.swing_low(df["low"], period=5)
                
                plogger.info("INDICATORS", "Structure.BOS", "Detecting break of structure")
                result["bos"] = indicators.break_of_structure(df["high"], df["low"], df["close"])
                
                plogger.info("INDICATORS", "Structure.CHOCH", "Detecting change of character")
                result["choch"] = indicators.change_of_character(df["high"], df["low"], df["close"])
                
                structure_cols = len(result.columns) - start_cols
                cat_timer.add_detail("features", structure_cols)
                categories_computed.append(("Structure", structure_cols))
                plogger.success("INDICATORS", "Structure", f"Computed {structure_cols} structure indicators")
                
            except Exception as e:
                plogger.error("INDICATORS", "Structure", f"Failed: {e}")
                raise
        
        # Volume Indicators
        with OperationTimer(plogger, "INDICATORS", "Volume", "Computing volume indicators") as cat_timer:
            try:
                start_cols = len(result.columns)
                
                plogger.info("INDICATORS", "Volume.OBV", "Computing On-Balance Volume")
                result["obv"] = indicators.obv(df["close"], df["volume"])
                
                plogger.info("INDICATORS", "Volume.VWAP", "Computing VWAP")
                result["vwap"] = indicators.vwap(df["high"], df["low"], df["close"], df["volume"])
                
                plogger.info("INDICATORS", "Volume.MFI", "Computing Money Flow Index")
                result["mfi"] = indicators.mfi(df["high"], df["low"], df["close"], df["volume"], period=14)
                
                plogger.info("INDICATORS", "Volume.CMF", "Computing Chaikin Money Flow")
                result["cmf"] = indicators.cmf(df["high"], df["low"], df["close"], df["volume"], period=20)
                
                volume_cols = len(result.columns) - start_cols
                cat_timer.add_detail("features", volume_cols)
                categories_computed.append(("Volume", volume_cols))
                plogger.success("INDICATORS", "Volume", f"Computed {volume_cols} volume indicators")
                
            except Exception as e:
                plogger.error("INDICATORS", "Volume", f"Failed: {e}")
                raise
        
        # Mean Reversion
        with OperationTimer(plogger, "INDICATORS", "MeanReversion", "Computing mean reversion indicators") as cat_timer:
            try:
                start_cols = len(result.columns)
                
                plogger.info("INDICATORS", "MeanReversion.ZScore", "Computing Z-scores")
                for period in [20, 50, 100]:
                    result[f"zscore_{period}"] = indicators.zscore(df["close"], period=period)
                
                plogger.info("INDICATORS", "MeanReversion.Hurst", "Computing Hurst exponent")
                result["hurst"] = indicators.hurst_exponent(df["close"], period=100)
                
                plogger.info("INDICATORS", "MeanReversion.Distance", "Computing distance from MA")
                result["distance_pct_ema21"] = (df["close"] - result["ema_21"]) / result["ema_21"] * 100
                result["distance_pct_ema55"] = (df["close"] - result["ema_55"]) / result["ema_55"] * 100
                
                mr_cols = len(result.columns) - start_cols
                cat_timer.add_detail("features", mr_cols)
                categories_computed.append(("MeanReversion", mr_cols))
                plogger.success("INDICATORS", "MeanReversion", f"Computed {mr_cols} mean reversion indicators")
                
            except Exception as e:
                plogger.error("INDICATORS", "MeanReversion", f"Failed: {e}")
                raise
        
        # Regime Detection
        with OperationTimer(plogger, "INDICATORS", "Regime", "Computing regime indicators") as cat_timer:
            try:
                start_cols = len(result.columns)
                
                plogger.info("INDICATORS", "Regime.Trend", "Classifying trend regime")
                result["regime_trend"] = indicators.regime_trend(result["adx"], result["di_plus"], result["di_minus"])
                
                plogger.info("INDICATORS", "Regime.Volatility", "Classifying volatility regime")
                result["regime_volatility"] = indicators.regime_volatility(result["atr_pct"])
                
                regime_cols = len(result.columns) - start_cols
                cat_timer.add_detail("features", regime_cols)
                categories_computed.append(("Regime", regime_cols))
                plogger.success("INDICATORS", "Regime", f"Computed {regime_cols} regime indicators")
                
            except Exception as e:
                plogger.error("INDICATORS", "Regime", f"Failed: {e}")
                raise
        
        # Price Action Patterns
        with OperationTimer(plogger, "INDICATORS", "PriceAction", "Computing price action patterns") as cat_timer:
            try:
                start_cols = len(result.columns)
                
                plogger.info("INDICATORS", "PriceAction.Candles", "Analyzing candlestick patterns")
                result["candle_body"] = abs(df["close"] - df["open"])
                result["candle_range"] = df["high"] - df["low"]
                result["candle_body_pct"] = result["candle_body"] / result["candle_range"]
                
                result["upper_wick"] = df["high"] - df[["close", "open"]].max(axis=1)
                result["lower_wick"] = df[["close", "open"]].min(axis=1) - df["low"]
                
                plogger.info("INDICATORS", "PriceAction.Patterns", "Detecting engulfing and pin bars")
                result["bullish_engulfing"] = indicators.bullish_engulfing(df["open"], df["close"])
                result["bearish_engulfing"] = indicators.bearish_engulfing(df["open"], df["close"])
                result["pin_bar"] = indicators.pin_bar(df["open"], df["high"], df["low"], df["close"])
                
                plogger.info("INDICATORS", "PriceAction.Streaks", "Computing consecutive bars")
                result["consecutive_up"] = indicators.consecutive_up(df["close"])
                result["consecutive_down"] = indicators.consecutive_down(df["close"])
                
                pa_cols = len(result.columns) - start_cols
                cat_timer.add_detail("features", pa_cols)
                categories_computed.append(("PriceAction", pa_cols))
                plogger.success("INDICATORS", "PriceAction", f"Computed {pa_cols} price action indicators")
                
            except Exception as e:
                plogger.error("INDICATORS", "PriceAction", f"Failed: {e}")
                raise
        
        # Liquidity/SMC
        with OperationTimer(plogger, "INDICATORS", "Liquidity", "Computing liquidity indicators") as cat_timer:
            try:
                start_cols = len(result.columns)
                
                plogger.info("INDICATORS", "Liquidity.FVG", "Detecting fair value gaps")
                result["fvg_bullish"] = indicators.fair_value_gap_bullish(df["high"], df["low"])
                result["fvg_bearish"] = indicators.fair_value_gap_bearish(df["high"], df["low"])
                
                plogger.info("INDICATORS", "Liquidity.EqualLevels", "Detecting equal highs/lows")
                result["equal_highs"] = indicators.equal_highs(df["high"], tolerance=0.001)
                result["equal_lows"] = indicators.equal_lows(df["low"], tolerance=0.001)
                
                plogger.info("INDICATORS", "Liquidity.Sweeps", "Detecting liquidity sweeps")
                result["sweep_high"] = indicators.liquidity_sweep_high(df["high"], df["close"])
                result["sweep_low"] = indicators.liquidity_sweep_low(df["low"], df["close"])
                
                plogger.info("INDICATORS", "Liquidity.Daily", "Computing previous daily high/low")
                result["pdh"] = indicators.previous_day_high(df["time"], df["high"])
                result["pdl"] = indicators.previous_day_low(df["time"], df["low"])
                
                liquidity_cols = len(result.columns) - start_cols
                cat_timer.add_detail("features", liquidity_cols)
                categories_computed.append(("Liquidity", liquidity_cols))
                plogger.success("INDICATORS", "Liquidity", f"Computed {liquidity_cols} liquidity indicators")
                
            except Exception as e:
                plogger.error("INDICATORS", "Liquidity", f"Failed: {e}")
                raise
        
        # Time-based Features
        with OperationTimer(plogger, "INDICATORS", "Time", "Computing time-based features") as cat_timer:
            try:
                start_cols = len(result.columns)
                
                plogger.info("INDICATORS", "Time.Extract", "Extracting time components")
                result["hour"] = df["time"].dt.hour
                result["day_of_week"] = df["time"].dt.dayofweek
                
                plogger.info("INDICATORS", "Time.Session", "Detecting trading sessions")
                result["session_asia"] = ((result["hour"] >= 0) & (result["hour"] < 8)).astype(int)
                result["session_london"] = ((result["hour"] >= 8) & (result["hour"] < 16)).astype(int)
                result["session_ny"] = ((result["hour"] >= 13) & (result["hour"] < 21)).astype(int)
                
                time_cols = len(result.columns) - start_cols
                cat_timer.add_detail("features", time_cols)
                categories_computed.append(("Time", time_cols))
                plogger.success("INDICATORS", "Time", f"Computed {time_cols} time features")
                
            except Exception as e:
                plogger.error("INDICATORS", "Time", f"Failed: {e}")
                raise
        
        # Summary
        total_indicators = len(result.columns) - initial_cols
        timer.add_detail("total_indicators", total_indicators)
        timer.add_detail("categories", len(categories_computed))
        timer.add_detail("bars", len(df))
        
        # Log breakdown
        breakdown = ", ".join([f"{cat}={count}" for cat, count in categories_computed])
        plogger.success("INDICATORS", "ComputeAll", f"Computed {total_indicators} indicators across {len(categories_computed)} categories")
        plogger.info("INDICATORS", "Breakdown", breakdown)
        
        return result
