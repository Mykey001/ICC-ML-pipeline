"""
Main live trading script for ICC meta-labeling model.

Usage:
    python main.py --config config.yaml [--dry-run]

Features:
- Real-time data management
- Model-based signal scoring
- Risk management
- Order execution
- Performance monitoring
"""
import sys
from pathlib import Path
import argparse
import logging
import time
from datetime import datetime
import yaml
import signal as sys_signal

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from icc_ml.config import StrategyConfig, SymbolSpec

from data_manager import DataManager
from trading_engine import TradingEngine, demo_order_executor, mt5_order_executor
from risk_manager import RiskManager, RiskLimits, AccountState, EmergencyStop
from monitor import PerformanceMonitor


# Global state for graceful shutdown
SHUTDOWN_REQUESTED = False


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    global SHUTDOWN_REQUESTED
    print("\n⚠️  Shutdown requested. Finishing current operation...")
    SHUTDOWN_REQUESTED = True


def setup_logging(config: dict):
    """Configure logging."""
    log_config = config.get("logging", {})
    
    level = getattr(logging, log_config.get("level", "INFO"))
    
    handlers = []
    
    if log_config.get("console", True):
        handlers.append(logging.StreamHandler())
    
    if log_config.get("file", True):
        log_dir = Path(config["monitoring"]["log_dir"])
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / f"trading_{datetime.now().strftime('%Y%m%d')}.log"
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )
    
    return logging.getLogger(__name__)


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config


def create_components(config: dict, logger):
    """Create all trading system components."""
    
    # Symbol spec
    spec_config = config["symbol_spec"]
    symbol_spec = SymbolSpec(
        name=spec_config["name"],
        digits=spec_config["digits"],
        point=spec_config["point"],
        contract_size=spec_config["contract_size"],
        typical_spread_points=spec_config["typical_spread_points"],
        commission_per_lot_roundturn=spec_config["commission_per_lot_roundturn"],
    )
    
    # Strategy config
    strat_config = config["strategy"]
    strategy_config = StrategyConfig(
        htf_pivot_len=strat_config["htf_pivot_len"],
        ltf_pivot_len=strat_config["ltf_pivot_len"],
        tp_pips=strat_config["tp_pips"],
        use_custom_swing_sl=strat_config["use_custom_swing_sl"],
        sl_swing_timeframe=strat_config["sl_swing_timeframe"],
        sl_swing_pivot_len=strat_config["sl_swing_pivot_len"],
        sl_max_candidates=strat_config["sl_max_candidates"],
        sl_buffer_pips=strat_config["sl_buffer_pips"],
        require_custom_swing_sl=strat_config["require_custom_swing_sl"],
        one_position_at_a_time=strat_config["one_position_at_a_time"],
        fixed_lots=strat_config["fixed_lots"],
        max_hold_bars=strat_config["max_hold_bars"],
    )
    
    # Data manager
    data_config = config["data"]
    data_manager = DataManager(
        symbol=data_config["symbol"],
        timeframe=data_config["timeframe"],
        buffer_size=data_config["buffer_size"],
        data_source=data_config["source"],
        csv_path=data_config.get("csv_path"),
        mt5_login=data_config.get("mt5_login"),
        mt5_password=data_config.get("mt5_password"),
        mt5_server=data_config.get("mt5_server"),
    )
    
    # Risk manager
    risk_config = config["risk"]
    risk_limits = RiskLimits(
        max_positions=risk_config["max_positions"],
        max_lot_size=risk_config["max_lot_size"],
        min_lot_size=risk_config["min_lot_size"],
        default_lot_size=risk_config["default_lot_size"],
        max_daily_loss_usd=risk_config["max_daily_loss_usd"],
        max_daily_trades=risk_config["max_daily_trades"],
        max_drawdown_pct=risk_config["max_drawdown_pct"],
        min_probability=risk_config.get("min_probability"),
        min_risk_reward_ratio=risk_config["min_risk_reward_ratio"],
    )
    risk_manager = RiskManager(risk_limits)
    
    # Emergency stop
    emergency_config = config["emergency"]
    emergency_stop = EmergencyStop(
        max_consecutive_losses=emergency_config["max_consecutive_losses"],
        max_daily_loss_pct=emergency_config["max_daily_loss_pct"],
        max_loss_in_minutes=(
            emergency_config["max_loss_in_minutes_usd"],
            emergency_config["max_loss_in_minutes_time"],
        ),
    )
    
    # Performance monitor
    monitor = PerformanceMonitor(
        log_dir=config["monitoring"]["log_dir"],
    )
    
    # Order executor
    exec_config = config["execution"]
    executor_type = exec_config["order_executor"]
    
    if executor_type == "demo":
        order_executor = demo_order_executor
    elif executor_type == "mt5":
        order_executor = mt5_order_executor
    else:
        order_executor = None
    
    # Trading engine
    model_path = Path(__file__).parent / config["model"]["path"]
    trading_engine = TradingEngine(
        model_path=str(model_path),
        data_manager=data_manager,
        risk_manager=risk_manager,
        strategy_config=strategy_config,
        symbol_spec=symbol_spec,
        order_executor=order_executor,
        dry_run=exec_config["dry_run"],
    )
    
    return {
        "data_manager": data_manager,
        "trading_engine": trading_engine,
        "risk_manager": risk_manager,
        "emergency_stop": emergency_stop,
        "monitor": monitor,
        "symbol_spec": symbol_spec,
    }


def run_trading_loop(components: dict, config: dict, logger):
    """Main trading loop."""
    
    data_manager = components["data_manager"]
    trading_engine = components["trading_engine"]
    emergency_stop = components["emergency_stop"]
    monitor = components["monitor"]
    
    # Initialize account state (mock for now - replace with real broker API)
    account = AccountState(
        balance=10000.0,  # Starting balance
        equity=10000.0,
        open_positions=0,
        daily_pnl=0.0,
        daily_trades=0,
    )
    
    logger.info("=" * 80)
    logger.info("STARTING LIVE TRADING SYSTEM")
    logger.info("=" * 80)
    logger.info(f"Mode: {'DRY RUN' if config['execution']['dry_run'] else 'LIVE TRADING'}")
    logger.info(f"Symbol: {config['data']['symbol']}")
    logger.info(f"Timeframe: {config['data']['timeframe']}")
    logger.info(f"Data source: {config['data']['source']}")
    logger.info(f"Model: {config['model']['path']}")
    logger.info("=" * 80)
    
    # Initialize data
    logger.info("Initializing data manager...")
    if not data_manager.initialize():
        logger.error("Failed to initialize data manager. Exiting.")
        return
    
    logger.info("✓ Data manager initialized")
    
    # Start trading engine
    trading_engine.start()
    logger.info("✓ Trading engine started")
    
    # Main loop
    check_interval = config["timing"]["check_interval_seconds"]
    iteration = 0
    
    logger.info(f"\n{'='*80}")
    logger.info("ENTERING MAIN LOOP")
    logger.info(f"Checking for new bars every {check_interval} seconds")
    logger.info(f"Press Ctrl+C to stop gracefully")
    logger.info(f"{'='*80}\n")
    
    try:
        while not SHUTDOWN_REQUESTED:
            iteration += 1
            
            # Check for emergency stop
            should_stop, stop_reason = emergency_stop.check(account)
            if should_stop:
                logger.critical(f"EMERGENCY STOP TRIGGERED: {stop_reason}")
                break
            
            # Check for new bar
            new_bar, df = data_manager.update()
            
            if new_bar:
                logger.info(f"\n{'='*60}")
                logger.info(f"NEW BAR DETECTED - Processing...")
                logger.info(f"{'='*60}")
                
                # Process the bar
                decision = trading_engine.process_bar(account)
                
                if decision is not None:
                    # Record in monitor
                    monitor.record_signal(decision)
                    
                    # Update emergency stop if trade was executed
                    if decision.get("executed"):
                        # In real implementation, track position and update on close
                        pass
                
                logger.info(f"{'='*60}\n")
            
            else:
                if iteration % 10 == 0:  # Log every 10 checks
                    logger.debug(f"No new bar. Waiting... (iteration {iteration})")
            
            # Print stats periodically
            if iteration % 60 == 0:  # Every ~60 minutes (assuming 60s checks)
                monitor.print_stats()
            
            # Sleep
            time.sleep(check_interval)
    
    except KeyboardInterrupt:
        logger.info("\nKeyboard interrupt received")
    
    except Exception as e:
        logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
    
    finally:
        # Cleanup
        logger.info("\n" + "="*80)
        logger.info("SHUTTING DOWN")
        logger.info("="*80)
        
        trading_engine.stop()
        data_manager.shutdown()  # Close MT5 connection
        
        # Final stats
        logger.info("\nFinal statistics:")
        monitor.print_stats()
        
        # Export report
        report_path = monitor.export_report()
        logger.info(f"\nFull report exported to: {report_path}")
        
        logger.info("\n✓ Shutdown complete")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="ICC ML Live Trading System"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force dry-run mode (no real orders)",
    )
    
    args = parser.parse_args()
    
    # Load config
    config_path = Path(__file__).parent / args.config
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)
    
    config = load_config(config_path)
    
    # Override dry-run if specified
    if args.dry_run:
        config["execution"]["dry_run"] = True
    
    # Setup logging
    logger = setup_logging(config)
    
    # Register signal handler
    sys_signal.signal(sys_signal.SIGINT, signal_handler)
    
    # Welcome message
    logger.info("\n" + "="*80)
    logger.info("ICC META-LABELING LIVE TRADING SYSTEM")
    logger.info("="*80)
    logger.info(f"Config: {config_path}")
    logger.info(f"Started: {datetime.now()}")
    
    if config["execution"]["dry_run"]:
        logger.warning("⚠️  DRY RUN MODE - No real orders will be placed")
    else:
        logger.warning("🔴 LIVE TRADING MODE - Real orders will be placed!")
        logger.warning("    Press Ctrl+C within 10 seconds to abort...")
        time.sleep(10)
    
    logger.info("="*80 + "\n")
    
    # Create components
    logger.info("Creating trading system components...")
    components = create_components(config, logger)
    logger.info("✓ All components created\n")
    
    # Run
    run_trading_loop(components, config, logger)


if __name__ == "__main__":
    main()
