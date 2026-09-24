"""
Real-time data management for live trading.

Handles:
- Data fetching (MT5, CSV, or API)
- Historical data caching
- Data validation
- Update detection

Enhanced with transparent step-by-step logging.
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Literal
import logging

from .pipeline_logger import get_pipeline_logger, OperationTimer, ActivityLevel


logger = logging.getLogger(__name__)
plogger = get_pipeline_logger()


class DataManager:
    """
    Manages real-time OHLCV data for live trading.
    
    Features:
    - Maintains rolling buffer of historical bars
    - Detects new bar closes
    - Validates data quality
    - Supports multiple data sources
    """
    
    def __init__(
        self,
        symbol: str,
        timeframe: str = "H1",
        buffer_size: int = 2000,
        data_source: Literal["mt5", "csv", "api"] = "csv",
        csv_path: Optional[str] = None,
        mt5_login: Optional[int] = None,
        mt5_password: Optional[str] = None,
        mt5_server: Optional[str] = None,
    ):
        """
        Initialize data manager.
        
        Args:
            symbol: Trading symbol (e.g., "XAUUSDm")
            timeframe: Timeframe (e.g., "H1", "H4", "D1")
            buffer_size: Number of historical bars to maintain
            data_source: Data source type
            csv_path: Path to CSV file (if data_source="csv")
            mt5_login: MT5 account number (if data_source="mt5")
            mt5_password: MT5 password (if data_source="mt5")
            mt5_server: MT5 server name (if data_source="mt5")
        """
        self.symbol = symbol
        self.timeframe = timeframe
        self.buffer_size = buffer_size
        self.data_source = data_source
        self.csv_path = csv_path
        self.mt5_login = mt5_login
        self.mt5_password = mt5_password
        self.mt5_server = mt5_server
        
        self._buffer: Optional[pd.DataFrame] = None
        self._last_bar_time: Optional[datetime] = None
        self._mt5_initialized = False
        
        logger.info(
            f"DataManager initialized: {symbol} {timeframe}, "
            f"source={data_source}, buffer={buffer_size}"
        )
    
    def initialize(self) -> bool:
        """
        Load initial historical data.
        
        Returns:
            True if successful, False otherwise
        """
        with OperationTimer(plogger, "DATA", "Initialize", "Initializing data manager") as timer:
            try:
                plogger.info("DATA", "Initialize", f"Fetching {self.buffer_size} bars from {self.data_source}")
                
                df = self._fetch_data(bars=self.buffer_size)
                
                if df is None:
                    plogger.error("DATA", "Initialize", "Failed to fetch data")
                    logger.error("Failed to fetch data")
                    return False
                
                plogger.info("DATA", "Initialize", f"Received {len(df)} bars")
                
                if len(df) < 1500:
                    plogger.error(
                        "DATA", "Initialize",
                        f"Insufficient data: {len(df)} bars (need ≥1500 for indicators)"
                    )
                    logger.error(
                        f"Insufficient data: {len(df)} bars "
                        f"(need ≥1500 for indicators)"
                    )
                    return False
                
                # Validate data
                plogger.info("DATA", "Validate", "Validating data quality")
                is_valid, errors = self.validate_data(df)
                
                if not is_valid:
                    plogger.warning("DATA", "Validate", f"Data quality issues: {'; '.join(errors)}")
                    logger.warning(f"Data quality issues: {errors}")
                else:
                    plogger.success("DATA", "Validate", "Data quality checks passed")
                
                self._buffer = df
                self._last_bar_time = df.iloc[-1]["time"]
                
                timer.add_detail("bars", len(df))
                timer.add_detail("from", str(df.iloc[0]["time"])[:19])
                timer.add_detail("to", str(df.iloc[-1]["time"])[:19])
                timer.add_detail("symbol", self.symbol)
                timer.add_detail("timeframe", self.timeframe)
                
                logger.info(
                    f"Initialized with {len(df)} bars, "
                    f"latest: {self._last_bar_time}"
                )
                return True
                
            except Exception as e:
                plogger.error("DATA", "Initialize", f"Initialization failed: {e}")
                logger.error(f"Failed to initialize: {e}", exc_info=True)
                return False
    
    def update(self) -> tuple[bool, Optional[pd.DataFrame]]:
        """
        Check for new bar and update buffer.
        
        Returns:
            (new_bar_closed, updated_dataframe)
            - new_bar_closed: True if a new bar closed since last update
            - updated_dataframe: Full buffer if new bar, None otherwise
        """
        if self._buffer is None:
            raise RuntimeError("DataManager not initialized. Call initialize() first.")
        
        with OperationTimer(plogger, "DATA", "Update", "Checking for new bar") as timer:
            try:
                plogger.info("DATA", "Fetch", f"Fetching latest bars from {self.data_source}")
                
                # Fetch latest data
                df = self._fetch_data(bars=100)  # Only need recent bars
                
                if df is None or len(df) == 0:
                    plogger.warning("DATA", "Fetch", "No data received in update")
                    logger.warning("No data received in update")
                    return False, None
                
                latest_time = df.iloc[-1]["time"]
                plogger.info("DATA", "Fetch", f"Latest bar time: {latest_time}")
                
                # Check if new bar closed
                if latest_time <= self._last_bar_time:
                    # No new bar
                    plogger.debug("DATA", "Update", f"No new bar (latest: {latest_time}, last: {self._last_bar_time})")
                    return False, None
                
                plogger.success("DATA", "NewBar", f"New bar detected: {latest_time}")
                logger.info(f"New bar detected: {latest_time}")
                
                # Append new bars to buffer
                new_bars = df[df["time"] > self._last_bar_time]
                plogger.info("DATA", "Update", f"Appending {len(new_bars)} new bar(s) to buffer")
                
                self._buffer = pd.concat([self._buffer, new_bars], ignore_index=True)
                
                # Trim buffer to size
                if len(self._buffer) > self.buffer_size:
                    trimmed = len(self._buffer) - self.buffer_size
                    self._buffer = self._buffer.iloc[-self.buffer_size:].reset_index(drop=True)
                    plogger.info("DATA", "Update", f"Trimmed {trimmed} old bars from buffer")
                
                # Update last bar time
                self._last_bar_time = latest_time
                
                timer.add_detail("new_bars", len(new_bars))
                timer.add_detail("buffer_size", len(self._buffer))
                timer.add_detail("latest_time", str(latest_time)[:19])
                
                return True, self._buffer.copy()
                
            except Exception as e:
                plogger.error("DATA", "Update", f"Update failed: {e}")
                logger.error(f"Error in update: {e}", exc_info=True)
                return False, None
    
    def get_buffer(self) -> pd.DataFrame:
        """Get current data buffer (defensive copy)."""
        if self._buffer is None:
            raise RuntimeError("DataManager not initialized")
        return self._buffer.copy()
    
    def _fetch_data(self, bars: int) -> Optional[pd.DataFrame]:
        """
        Fetch data from configured source.
        
        Args:
            bars: Number of bars to fetch
        
        Returns:
            DataFrame with columns: time, open, high, low, close, volume
        """
        if self.data_source == "csv":
            return self._fetch_csv(bars)
        elif self.data_source == "mt5":
            return self._fetch_mt5(bars)
        elif self.data_source == "api":
            return self._fetch_api(bars)
        else:
            raise ValueError(f"Unknown data source: {self.data_source}")
    
    def _fetch_csv(self, bars: int) -> Optional[pd.DataFrame]:
        """Fetch from CSV file (for testing/demo)."""
        with OperationTimer(plogger, "DATA", "FetchCSV", f"Reading CSV: {self.csv_path}") as timer:
            if self.csv_path is None:
                raise ValueError("csv_path not set")
            
            path = Path(self.csv_path)
            if not path.exists():
                plogger.error("DATA", "FetchCSV", f"CSV file not found: {path}")
                logger.error(f"CSV file not found: {path}")
                return None
            
            plogger.info("DATA", "FetchCSV", f"Reading file: {path.name}")
            
            # Read CSV
            df = pd.read_csv(path)
            plogger.info("DATA", "FetchCSV", f"Read {len(df)} total bars from CSV")
            
            # Parse time column
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"])
                plogger.debug("DATA", "FetchCSV", "Parsed time column")
            else:
                plogger.error("DATA", "FetchCSV", f"CSV missing 'time' column. Columns: {list(df.columns)}")
                logger.error(f"CSV missing 'time' column. Columns: {list(df.columns)}")
                return None
            
            # Validate columns
            required = ["time", "open", "high", "low", "close", "volume"]
            missing = [c for c in required if c not in df.columns]
            
            if missing:
                plogger.error("DATA", "FetchCSV", f"CSV missing columns: {missing}")
                logger.error(f"CSV missing columns: {missing}")
                return None
            
            plogger.success("DATA", "FetchCSV", "All required columns present")
            
            # Sort by time
            df = df.sort_values("time").reset_index(drop=True)
            plogger.debug("DATA", "FetchCSV", "Sorted by time")
            
            # Return last N bars
            result = df.iloc[-bars:].reset_index(drop=True)
            
            timer.add_detail("total_bars", len(df))
            timer.add_detail("returned_bars", len(result))
            timer.add_detail("from", str(result.iloc[0]["time"])[:19])
            timer.add_detail("to", str(result.iloc[-1]["time"])[:19])
            
            return result
    
    def _fetch_mt5(self, bars: int) -> Optional[pd.DataFrame]:
        """Fetch from MetaTrader 5."""
        with OperationTimer(plogger, "DATA", "FetchMT5", f"Fetching {bars} bars from MT5") as timer:
            try:
                import MetaTrader5 as mt5
                
                # Initialize MT5 if not already done
                if not self._mt5_initialized:
                    plogger.info("DATA", "MT5Init", "Initializing MT5 connection")
                    
                    if not mt5.initialize():
                        plogger.error("DATA", "MT5Init", f"MT5 initialization failed: {mt5.last_error()}")
                        logger.error(f"MT5 initialization failed: {mt5.last_error()}")
                        return None
                    
                    plogger.success("DATA", "MT5Init", "MT5 initialized successfully")
                    
                    # Login if credentials provided
                    if self.mt5_login and self.mt5_password and self.mt5_server:
                        plogger.info("DATA", "MT5Login", f"Logging into account {self.mt5_login} on {self.mt5_server}")
                        
                        authorized = mt5.login(
                            login=self.mt5_login,
                            password=self.mt5_password,
                            server=self.mt5_server
                        )
                        
                        if not authorized:
                            plogger.error("DATA", "MT5Login", f"Login failed: {mt5.last_error()}")
                            logger.error(f"MT5 login failed: {mt5.last_error()}")
                            mt5.shutdown()
                            return None
                        
                        # Verify account info
                        account_info = mt5.account_info()
                        if account_info is None:
                            plogger.error("DATA", "MT5Login", "Failed to get account info after login")
                            logger.error("Failed to get account info after login")
                            mt5.shutdown()
                            return None
                        
                        plogger.success(
                            "DATA", "MT5Login",
                            f"Connected to account {account_info.login}",
                            details={
                                "balance": f"{account_info.balance:.2f} {account_info.currency}",
                                "leverage": f"1:{account_info.leverage}"
                            }
                        )
                        logger.info(f"✓ Connected to MT5 account: {account_info.login}")
                        logger.info(f"  Balance: {account_info.balance} {account_info.currency}")
                        logger.info(f"  Leverage: 1:{account_info.leverage}")
                    else:
                        # No credentials - use already logged-in terminal
                        plogger.info("DATA", "MT5Login", "Using existing terminal connection")
                        logger.info("MT5 initialized using existing terminal connection")
                        account_info = mt5.account_info()
                        if account_info:
                            plogger.info("DATA", "MT5Login", f"Using account: {account_info.login}")
                            logger.info(f"  Using account: {account_info.login}")
                    
                    # Ensure symbol is visible
                    plogger.info("DATA", "MT5Symbol", f"Checking symbol: {self.symbol}")
                    symbol_info = mt5.symbol_info(self.symbol)
                    if symbol_info is None:
                        plogger.error("DATA", "MT5Symbol", f"Symbol {self.symbol} not found")
                        logger.error(f"Symbol {self.symbol} not found")
                        mt5.shutdown()
                        return None
                    
                    if not symbol_info.visible:
                        plogger.info("DATA", "MT5Symbol", f"Adding {self.symbol} to Market Watch")
                        logger.info(f"Adding {self.symbol} to Market Watch...")
                        if not mt5.symbol_select(self.symbol, True):
                            plogger.error("DATA", "MT5Symbol", f"Failed to add {self.symbol} to Market Watch")
                            logger.error(f"Failed to add {self.symbol} to Market Watch")
                            mt5.shutdown()
                            return None
                    
                    plogger.success(
                        "DATA", "MT5Symbol",
                        f"Symbol {self.symbol} ready",
                        details={
                            "spread": f"{symbol_info.spread} points",
                            "digits": symbol_info.digits,
                            "point": symbol_info.point
                        }
                    )
                    logger.info(f"✓ Symbol {self.symbol} ready (spread: {symbol_info.spread} points)")
                    self._mt5_initialized = True
                
                # Get rates
                plogger.info("DATA", "MT5Fetch", f"Requesting {bars} bars of {self.symbol} {self.timeframe}")
                rates = mt5.copy_rates_from_pos(self.symbol, self._timeframe_to_mt5(), 0, bars)
                
                if rates is None or len(rates) == 0:
                    plogger.error("DATA", "MT5Fetch", f"No data from MT5: {mt5.last_error()}")
                    logger.error(f"No data from MT5: {mt5.last_error()}")
                    return None
                
                plogger.success("DATA", "MT5Fetch", f"Received {len(rates)} bars from MT5")
                
                # Convert to DataFrame
                plogger.info("DATA", "MT5Parse", "Converting to DataFrame")
                df = pd.DataFrame(rates)
                df["time"] = pd.to_datetime(df["time"], unit="s")
                
                # Rename columns
                df = df.rename(columns={
                    "tick_volume": "volume"
                })
                
                # Select required columns
                df = df[["time", "open", "high", "low", "close", "volume"]]
                
                timer.add_detail("bars", len(df))
                timer.add_detail("from", str(df.iloc[0]["time"])[:19])
                timer.add_detail("to", str(df.iloc[-1]["time"])[:19])
                timer.add_detail("symbol", self.symbol)
                timer.add_detail("timeframe", self.timeframe)
                
                return df
                
            except ImportError:
                plogger.error("DATA", "MT5Fetch", "MetaTrader5 package not installed")
                logger.error("MetaTrader5 package not installed. Install: pip install MetaTrader5")
                return None
            except Exception as e:
                plogger.error("DATA", "MT5Fetch", f"MT5 fetch error: {e}")
                logger.error(f"MT5 fetch error: {e}", exc_info=True)
                return None
    
    def _fetch_api(self, bars: int) -> Optional[pd.DataFrame]:
        """Fetch from broker API (implement for your broker)."""
        raise NotImplementedError(
            "API data fetching not implemented. "
            "Implement this method for your broker's API."
        )
    
    def _timeframe_to_mt5(self) -> int:
        """Convert timeframe string to MT5 constant."""
        import MetaTrader5 as mt5
        
        mapping = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
            "W1": mt5.TIMEFRAME_W1,
        }
        
        if self.timeframe not in mapping:
            raise ValueError(f"Unknown timeframe: {self.timeframe}")
        
        return mapping[self.timeframe]
    
    def validate_data(self, df: pd.DataFrame) -> tuple[bool, list[str]]:
        """
        Validate data quality.
        
        Returns:
            (is_valid, error_messages)
        """
        with OperationTimer(plogger, "DATA", "Validate", "Validating data quality") as timer:
            errors = []
            
            # Check required columns
            required = ["time", "open", "high", "low", "close", "volume"]
            missing = [c for c in required if c not in df.columns]
            if missing:
                errors.append(f"Missing columns: {missing}")
                plogger.error("DATA", "Validate", f"Missing columns: {missing}")
            
            # Check for NaN values
            if df[required].isna().any().any():
                nan_counts = df[required].isna().sum()
                errors.append("Data contains NaN values")
                plogger.warning("DATA", "Validate", f"NaN values found: {nan_counts[nan_counts > 0].to_dict()}")
            
            # Check OHLC logic
            if not (df["high"] >= df["low"]).all():
                bad_count = (~(df["high"] >= df["low"])).sum()
                errors.append("High < Low detected")
                plogger.error("DATA", "Validate", f"High < Low in {bad_count} bars")
            
            if not ((df["high"] >= df["open"]) & (df["high"] >= df["close"])).all():
                bad_count = (~((df["high"] >= df["open"]) & (df["high"] >= df["close"]))).sum()
                errors.append("High < Open or Close detected")
                plogger.error("DATA", "Validate", f"High < Open/Close in {bad_count} bars")
            
            if not ((df["low"] <= df["open"]) & (df["low"] <= df["close"])).all():
                bad_count = (~((df["low"] <= df["open"]) & (df["low"] <= df["close"]))).sum()
                errors.append("Low > Open or Close detected")
                plogger.error("DATA", "Validate", f"Low > Open/Close in {bad_count} bars")
            
            # Check for duplicates
            if df["time"].duplicated().any():
                dup_count = df["time"].duplicated().sum()
                errors.append("Duplicate timestamps detected")
                plogger.warning("DATA", "Validate", f"Duplicate timestamps: {dup_count}")
            
            # Check time ordering
            if not df["time"].is_monotonic_increasing:
                errors.append("Time not monotonically increasing")
                plogger.error("DATA", "Validate", "Time not monotonically increasing")
            
            is_valid = len(errors) == 0
            
            if is_valid:
                timer.add_detail("status", "PASS")
                timer.add_detail("bars", len(df))
            else:
                timer.add_detail("status", "FAIL")
                timer.add_detail("errors", len(errors))
            
            return is_valid, errors
    
    def shutdown(self):
        """Clean up resources (e.g., close MT5 connection)."""
        plogger.info("DATA", "Shutdown", "Shutting down data manager")
        
        if self._mt5_initialized:
            try:
                import MetaTrader5 as mt5
                mt5.shutdown()
                plogger.success("DATA", "Shutdown", "MT5 connection closed")
                logger.info("MT5 connection closed")
                self._mt5_initialized = False
            except Exception as e:
                plogger.error("DATA", "Shutdown", f"Error shutting down MT5: {e}")
                logger.error(f"Error shutting down MT5: {e}")
