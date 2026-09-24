"""
Fully automated MT5 live trading system.

This script connects to MT5, monitors for new bars, scores signals with the trained
model, and automatically executes trades in your account.

WARNING: This places REAL orders. Use demo account first!
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime, timedelta
import time
import logging
from typing import Optional
import MetaTrader5 as mt5
import pandas as pd

# Add src to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from icc_ml.config import StrategyConfig, SymbolSpec
from icc_ml.train import load_model
from icc_ml.live_inference import score_latest_signal, format_trading_decision

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(Path(__file__).parent / "logs" / f"mt5_trader_{datetime.now():%Y%m%d}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class MT5LiveTrader:
    """
    Automated MT5 trading system with ML model integration.
    
    Features:
    - Real-time MT5 connection
    - Automatic bar monitoring
    - ML-based signal scoring
    - Automated order execution
    - Position management
    - Risk controls
    """
    
    def __init__(
        self,
        symbol: str,
        timeframe: str,
        model_path: str,
        strategy_config: StrategyConfig,
        symbol_spec: SymbolSpec,
        lot_size: float = 0.01,
        magic_number: int = 123456,
        max_positions: int = 1,
        dry_run: bool = True,
    ):
        """
        Initialize MT5 live trader.
        
        Args:
            symbol: Trading symbol (e.g., "XAUUSDm", "EURUSD")
            timeframe: Timeframe (e.g., "H1", "M15")
            model_path: Path to trained model
            strategy_config: ICC strategy configuration
            symbol_spec: Symbol specifications
            lot_size: Position size in lots
            magic_number: Magic number for orders
            max_positions: Maximum simultaneous positions
            dry_run: If True, logs only (no real orders)
        """
        self.symbol = symbol
        self.timeframe = timeframe
        self.timeframe_mt5 = self._timeframe_to_mt5(timeframe)
        self.lot_size = lot_size
        self.magic_number = magic_number
        self.max_positions = max_positions
        self.dry_run = dry_run
        
        self.cfg = strategy_config
        self.spec = symbol_spec
        
        # Load model
        logger.info(f"Loading model from {model_path}")
        self.model_bundle = load_model(model_path)
        logger.info(
            f"Model loaded: {self.model_bundle['model_type']}, "
            f"threshold={self.model_bundle['threshold']:.4f}, "
            f"features={len(self.model_bundle['feature_cols'])}"
        )
        
        # State
        self.running = False
        self.last_bar_time: Optional[datetime] = None
        self.open_positions = {}
        
        # Initialize MT5
        if not self._initialize_mt5():
            raise RuntimeError("Failed to initialize MT5")
    
    def _initialize_mt5(self) -> bool:
        """Initialize MT5 connection."""
        if not mt5.initialize():
            logger.error(f"MT5 initialization failed: {mt5.last_error()}")
            return False
        
        # Check account
        account_info = mt5.account_info()
        if account_info is None:
            logger.error("Failed to get account info")
            return False
        
        logger.info(f"Connected to MT5 account: {account_info.login}")
        logger.info(f"Account balance: {account_info.balance} {account_info.currency}")
        logger.info(f"Account leverage: 1:{account_info.leverage}")
        
        # Check symbol
        symbol_info = mt5.symbol_info(self.symbol)
        if symbol_info is None:
            logger.error(f"Symbol {self.symbol} not found")
            return False
        
        if not symbol_info.visible:
            logger.info(f"Symbol {self.symbol} not in Market Watch, adding...")
            if not mt5.symbol_select(self.symbol, True):
                logger.error(f"Failed to add {self.symbol} to Market Watch")
                return False
        
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"  Digits: {symbol_info.digits}")
        logger.info(f"  Point: {symbol_info.point}")
        logger.info(f"  Spread: {symbol_info.spread} points")
        
        return True
    
    def _timeframe_to_mt5(self, tf: str) -> int:
        """Convert timeframe string to MT5 constant."""
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
        return mapping.get(tf, mt5.TIMEFRAME_H1)
    
    def _get_bars(self, count: int = 2000) -> Optional[pd.DataFrame]:
        """Fetch OHLCV bars from MT5."""
        rates = mt5.copy_rates_from_pos(self.symbol, self.timeframe_mt5, 0, count)
        
        if rates is None or len(rates) == 0:
            logger.error(f"Failed to fetch bars: {mt5.last_error()}")
            return None
        
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df = df.rename(columns={'tick_volume': 'volume'})
        df = df[['time', 'open', 'high', 'low', 'close', 'volume']]
        
        return df
    
    def _check_new_bar(self) -> tuple[bool, Optional[pd.DataFrame]]:
        """
        Check if a new bar has formed.
        
        Returns:
            (new_bar_formed, dataframe)
        """
        df = self._get_bars()
        
        if df is None:
            return False, None
        
        latest_bar_time = df.iloc[-1]['time']
        
        if self.last_bar_time is None:
            # First check
            self.last_bar_time = latest_bar_time
            logger.info(f"Initialized at bar: {latest_bar_time}")
            return False, None
        
        if latest_bar_time > self.last_bar_time:
            logger.info(f"New bar formed: {latest_bar_time}")
            self.last_bar_time = latest_bar_time
            return True, df
        
        return False, None
    
    def _get_current_positions(self) -> list:
        """Get currently open positions for this symbol and magic number."""
        positions = mt5.positions_get(symbol=self.symbol)
        
        if positions is None:
            return []
        
        # Filter by magic number
        return [p for p in positions if p.magic == self.magic_number]
    
    def _execute_trade(
        self,
        direction: int,  # 1=BUY, -1=SELL
        sl_price: float,
        tp_price: float,
        comment: str = "",
    ) -> bool:
        """
        Execute trade on MT5.
        
        Args:
            direction: 1 for BUY, -1 for SELL
            sl_price: Stop loss price
            tp_price: Take profit price
            comment: Order comment
        
        Returns:
            True if successful, False otherwise
        """
        # Check position limit
        current_positions = self._get_current_positions()
        if len(current_positions) >= self.max_positions:
            logger.warning(f"Max positions ({self.max_positions}) reached. Not opening new trade.")
            return False
        
        # Get current price
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            logger.error(f"Failed to get tick: {mt5.last_error()}")
            return False
        
        # Determine order type and price
        if direction == 1:  # BUY
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        else:  # SELL
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        
        # Build request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": self.lot_size,
            "type": order_type,
            "price": price,
            "sl": sl_price,
            "tp": tp_price,
            "deviation": 20,
            "magic": self.magic_number,
            "comment": comment[:31],  # MT5 limit
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        if self.dry_run:
            logger.info(f"DRY RUN - Would execute: {request}")
            return True
        
        # Send order
        logger.info(f"Sending order: {direction} {self.lot_size} lots @ {price}")
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order failed: retcode={result.retcode}, {result.comment}")
            return False
        
        logger.info(f"Order executed successfully: ticket={result.order}")
        logger.info(f"  Volume: {result.volume} lots")
        logger.info(f"  Price: {result.price}")
        logger.info(f"  SL: {sl_price}, TP: {tp_price}")
        
        return True
    
    def _process_bar(self, df: pd.DataFrame):
        """
        Process new bar: score signal and execute if needed.
        
        Args:
            df: OHLCV dataframe with sufficient history
        """
        try:
            # Score latest signal
            decision = score_latest_signal(
                df=df,
                model_bundle=self.model_bundle,
                cfg=self.cfg,
                spec=self.spec,
            )
            
            if decision is None:
                logger.debug("No ICC signal on this bar")
                return
            
            # Log decision
            logger.info(format_trading_decision(decision))
            
            # Check if model says SKIP
            if decision["decision"] == "SKIP":
                logger.info(
                    f"Model says SKIP (probability={decision['probability']:.3f}, "
                    f"threshold={decision['threshold']:.3f})"
                )
                return
            
            # Model says TAKE - execute trade
            logger.info(f"Model says TAKE (probability={decision['probability']:.3f})")
            
            success = self._execute_trade(
                direction=decision["direction"],
                sl_price=decision["sl_price"],
                tp_price=decision["tp_price"],
                comment=f"ICC_ML_{decision['probability']:.2f}",
            )
            
            if success:
                logger.info("✓ Trade executed successfully")
            else:
                logger.error("✗ Trade execution failed")
        
        except Exception as e:
            logger.error(f"Error processing bar: {e}", exc_info=True)
    
    def run(self, check_interval: int = 10):
        """
        Main trading loop.
        
        Args:
            check_interval: Seconds between checks for new bars
        """
        self.running = True
        
        logger.info("=" * 80)
        logger.info("MT5 LIVE TRADER STARTED")
        logger.info("=" * 80)
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Timeframe: {self.timeframe}")
        logger.info(f"Lot size: {self.lot_size}")
        logger.info(f"Max positions: {self.max_positions}")
        logger.info(f"Dry run: {self.dry_run}")
        logger.info(f"Check interval: {check_interval}s")
        logger.info("=" * 80)
        
        if self.dry_run:
            logger.warning("⚠️  DRY RUN MODE - No real orders will be placed")
        else:
            logger.warning("🔴 LIVE TRADING MODE - Real orders WILL be placed!")
        
        logger.info("Press Ctrl+C to stop")
        logger.info("")
        
        iteration = 0
        
        try:
            while self.running:
                iteration += 1
                
                # Check for new bar
                new_bar, df = self._check_new_bar()
                
                if new_bar:
                    logger.info(f"\n{'='*60}")
                    logger.info(f"NEW BAR - Processing iteration {iteration}")
                    logger.info(f"{'='*60}")
                    
                    self._process_bar(df)
                    
                    logger.info(f"{'='*60}\n")
                
                else:
                    if iteration % 60 == 0:  # Log every 10 minutes
                        logger.debug(f"Waiting for new bar... (iteration {iteration})")
                
                # Sleep
                time.sleep(check_interval)
        
        except KeyboardInterrupt:
            logger.info("\n⚠️  Keyboard interrupt received")
        
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
        
        finally:
            self.stop()
    
    def stop(self):
        """Stop the trader and cleanup."""
        self.running = False
        
        logger.info("\n" + "=" * 80)
        logger.info("STOPPING MT5 TRADER")
        logger.info("=" * 80)
        
        # Show final positions
        positions = self._get_current_positions()
        logger.info(f"Open positions: {len(positions)}")
        
        for pos in positions:
            logger.info(f"  Ticket: {pos.ticket}, {pos.volume} lots, P&L: {pos.profit}")
        
        # Shutdown MT5
        mt5.shutdown()
        logger.info("MT5 connection closed")
        logger.info("=" * 80)


def main():
    """Entry point for MT5 live trader."""
    import argparse
    
    parser = argparse.ArgumentParser(description="MT5 Automated Trading System")
    parser.add_argument("--symbol", default="XAUUSDm", help="Trading symbol")
    parser.add_argument("--timeframe", default="H1", help="Timeframe (H1, M15, etc)")
    parser.add_argument("--model", required=True, help="Path to trained model")
    parser.add_argument("--lot-size", type=float, default=0.01, help="Lot size")
    parser.add_argument("--max-positions", type=int, default=1, help="Max positions")
    parser.add_argument("--check-interval", type=int, default=10, help="Check interval (seconds)")
    parser.add_argument("--live", action="store_true", help="LIVE MODE (default is dry-run)")
    
    args = parser.parse_args()
    
    # Configuration
    cfg = StrategyConfig(
        htf_pivot_len=2,
        ltf_pivot_len=1,
        tp_pips=2500.0,
        use_custom_swing_sl=True,
        sl_swing_timeframe="4h",
        sl_swing_pivot_len=2,
    )
    
    spec = SymbolSpec(
        name=args.symbol,
        digits=3,
        point=0.001,
        contract_size=100.0,
        typical_spread_points=30.0,
        commission_per_lot_roundturn=0.0,
    )
    
    # Create trader
    trader = MT5LiveTrader(
        symbol=args.symbol,
        timeframe=args.timeframe,
        model_path=args.model,
        strategy_config=cfg,
        symbol_spec=spec,
        lot_size=args.lot_size,
        max_positions=args.max_positions,
        dry_run=not args.live,
    )
    
    # Run
    trader.run(check_interval=args.check_interval)


if __name__ == "__main__":
    main()
