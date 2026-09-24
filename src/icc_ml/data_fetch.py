"""
Data acquisition and validation.

Supports:
- MetaTrader 5 direct fetch (Windows only, terminal must be running)
- CSV upload (standard schema: time, open, high, low, close, volume)
- Synthetic random walk generation (for testing)
"""

from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional, Tuple
import warnings

import pandas as pd
import numpy as np


def validate_ohlcv(df: pd.DataFrame, max_missing_ratio: float = 0.02) -> dict:
    """
    Validate OHLCV data quality.
    
    Returns dict with validation results and issues found.
    Raises on critical failures (duplicates, non-monotonic time).
    """
    report = {
        "n_rows": len(df),
        "duplicate_timestamps": 0,
        "non_monotonic": False,
        "zero_or_negative_price_rows": 0,
        "high_less_than_low_rows": 0,
        "missing_bar_ratio": None,
    }
    
    # Critical: duplicates
    dupes = df["time"].duplicated().sum()
    report["duplicate_timestamps"] = int(dupes)
    if dupes > 0:
        raise ValueError(
            f"Found {dupes} duplicate timestamps. "
            "This breaks every downstream calculation. Fix the source data."
        )
    
    # Critical: monotonic time
    if not df["time"].is_monotonic_increasing:
        report["non_monotonic"] = True
        raise ValueError(
            "Timestamps are not monotonically increasing. "
            "Sort the data by 'time' ascending before proceeding."
        )
    
    # Price sanity
    price_cols = ["open", "high", "low", "close"]
    for col in price_cols:
        if col in df.columns:
            bad = (df[col] <= 0).sum()
            report["zero_or_negative_price_rows"] += int(bad)
    
    # OHLC consistency
    if all(c in df.columns for c in ["high", "low"]):
        bad_hl = (df["high"] < df["low"]).sum()
        report["high_less_than_low_rows"] = int(bad_hl)
    
    # Missing bars (approximate via median delta)
    if len(df) > 1:
        deltas = df["time"].diff().dt.total_seconds().dropna()
        if len(deltas) > 0:
            median_bar_seconds = deltas.median()
            if median_bar_seconds > 0:
                expected_bars = (df["time"].iloc[-1] - df["time"].iloc[0]).total_seconds() / median_bar_seconds
                actual_bars = len(df)
                report["missing_bar_ratio"] = max(0, 1 - actual_bars / expected_bars)
                
                if report["missing_bar_ratio"] > max_missing_ratio:
                    warnings.warn(
                        f"Missing bar ratio {report['missing_bar_ratio']:.1%} exceeds threshold {max_missing_ratio:.1%}. "
                        f"This may indicate gaps in data (weekends/holidays are normal).",
                        UserWarning
                    )
    
    return report


def get_ohlcv(
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    source: Literal["mt5", "csv"] = "csv",
    csv_path: Optional[str] = None,
) -> Tuple[pd.DataFrame, dict]:
    """
    Fetch OHLCV data from various sources.
    
    Returns:
        (df, report): DataFrame with validated OHLCV data and validation report
    
    Schema:
        time: datetime64[ns], UTC
        open, high, low, close: float64
        volume: float64 (tick volume ok, or 0 if unavailable)
    """
    if source == "mt5":
        df = _fetch_mt5(symbol, timeframe, start, end)
    elif source == "csv":
        if csv_path is None:
            raise ValueError("csv_path required when source='csv'")
        df = _load_csv(csv_path)
    else:
        raise ValueError(f"Unknown source: {source}. Valid options: 'mt5', 'csv'")
    
    # Ensure schema
    df = _standardize_schema(df, start, end)
    
    # Validate
    report = validate_ohlcv(df)
    
    return df, report


def _fetch_mt5(symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
    """
    Fetch data directly from MetaTrader 5.
    
    Requires:
    - Windows OS
    - MT5 terminal running and logged in
    - pip install MetaTrader5
    """
    try:
        import MetaTrader5 as mt5
    except ImportError:
        raise ImportError(
            "MetaTrader5 package not installed. "
            "Install with: pip install MetaTrader5"
        )
    
    # Initialize connection
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize() failed: {mt5.last_error()}")
    
    try:
        # Map timeframe string to MT5 constant
        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
            "W1": mt5.TIMEFRAME_W1,
            "MN1": mt5.TIMEFRAME_MN1,
        }
        tf_const = tf_map.get(timeframe.upper())
        if tf_const is None:
            raise ValueError(f"Unknown timeframe: {timeframe}. Valid: {list(tf_map.keys())}")
        
        # Fetch
        rates = mt5.copy_rates_range(symbol, tf_const, start, end)
        
        if rates is None or len(rates) == 0:
            raise RuntimeError(
                f"MT5 returned no data for {symbol} {timeframe} {start} to {end}. "
                f"Check symbol name and broker history depth."
            )
        
        # Convert to DataFrame
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.rename(columns={"tick_volume": "volume"}, inplace=True)
        
        return df[["time", "open", "high", "low", "close", "volume"]]
    
    finally:
        mt5.shutdown()


def _load_csv(path: str) -> pd.DataFrame:
    """
    Load OHLCV CSV.
    
    Expected schema (case-insensitive, comma-separated):
        time, open, high, low, close, volume
    
    Time column: ISO format, UTC
    """
    df = pd.read_csv(path)
    
    # Normalize column names
    df.columns = [c.strip().lower() for c in df.columns]
    
    # Check required columns
    required = {"time", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}")
    
    # Parse time
    df["time"] = pd.to_datetime(df["time"])
    
    # Add volume if missing
    if "volume" not in df.columns:
        df["volume"] = 0.0
        warnings.warn("No volume column in CSV. Volume features will be skipped.", UserWarning)
    
    return df[["time", "open", "high", "low", "close", "volume"]]


def _standardize_schema(df: pd.DataFrame, start: datetime, end: datetime) -> pd.DataFrame:
    """
    Ensure consistent schema and filter to requested range.
    """
    # Sort by time
    df = df.sort_values("time").reset_index(drop=True)
    
    # Filter to range (loose: include bars touching the boundaries)
    df = df[(df["time"] >= start) & (df["time"] <= end)].copy()
    
    # Ensure dtypes
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = df[col].astype(float)
    
    return df
