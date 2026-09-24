"""
System test script - validates all components before live trading.

Run this BEFORE starting live trading to catch configuration issues.
"""
import sys
from pathlib import Path
import yaml

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from icc_ml.train import load_model
from icc_ml.config import StrategyConfig, SymbolSpec
from icc_ml.live_inference import live_trading_checklist

from data_manager import DataManager
from risk_manager import RiskManager, RiskLimits, AccountState


def test_config_loading():
    """Test 1: Configuration file loads correctly."""
    print("\n" + "="*80)
    print("TEST 1: Configuration Loading")
    print("="*80)
    
    try:
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
        
        print("✓ Config file loads")
        print(f"  Model path: {config['model']['path']}")
        print(f"  Data source: {config['data']['source']}")
        print(f"  Dry run: {config['execution']['dry_run']}")
        
        # Check critical settings
        if config['symbol_spec']['commission_per_lot_roundturn'] == 0.0:
            print("⚠ WARNING: Commission is 0.0 (not set)")
        else:
            print(f"✓ Commission set: {config['symbol_spec']['commission_per_lot_roundturn']}")
        
        return True, config
        
    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False, None


def test_model_loading(config):
    """Test 2: Model bundle loads correctly."""
    print("\n" + "="*80)
    print("TEST 2: Model Loading")
    print("="*80)
    
    try:
        model_path = Path(__file__).parent / config['model']['path']
        
        if not model_path.exists():
            print(f"✗ Model file not found: {model_path}")
            return False, None
        
        bundle = load_model(str(model_path))
        
        print(f"✓ Model loaded")
        print(f"  Type: {bundle['model_type']}")
        print(f"  Features: {len(bundle['feature_cols'])}")
        print(f"  Threshold: {bundle['threshold']:.4f}")
        print(f"  Training trades: {bundle.get('n_training_trades', 'unknown')}")
        
        # Verify required keys
        required = ['model', 'feature_cols', 'threshold']
        missing = [k for k in required if k not in bundle]
        
        if missing:
            print(f"✗ Missing keys in model bundle: {missing}")
            return False, None
        
        print("✓ Model bundle structure valid")
        
        return True, bundle
        
    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False, None


def test_data_manager(config):
    """Test 3: Data manager can fetch data."""
    print("\n" + "="*80)
    print("TEST 3: Data Manager")
    print("="*80)
    
    try:
        data_config = config['data']
        
        dm = DataManager(
            symbol=data_config['symbol'],
            timeframe=data_config['timeframe'],
            buffer_size=data_config['buffer_size'],
            data_source=data_config['source'],
            csv_path=data_config.get('csv_path'),
        )
        
        print("✓ DataManager created")
        
        # Try to initialize
        if not dm.initialize():
            print("✗ Failed to initialize data")
            return False, None
        
        df = dm.get_buffer()
        
        print(f"✓ Data loaded: {len(df)} bars")
        print(f"  Columns: {list(df.columns)}")
        print(f"  Date range: {df['time'].min()} to {df['time'].max()}")
        
        # Validate data
        is_valid, errors = dm.validate_data(df)
        
        if not is_valid:
            print(f"⚠ Data validation issues: {errors}")
        else:
            print("✓ Data validation passed")
        
        return True, dm
        
    except Exception as e:
        print(f"✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def test_live_inference(config, model_bundle, data_manager):
    """Test 4: Live inference on recent data."""
    print("\n" + "="*80)
    print("TEST 4: Live Inference")
    print("="*80)
    
    try:
        # Create configs
        spec_config = config["symbol_spec"]
        symbol_spec = SymbolSpec(
            name=spec_config["name"],
            digits=spec_config["digits"],
            point=spec_config["point"],
            contract_size=spec_config["contract_size"],
            typical_spread_points=spec_config["typical_spread_points"],
            commission_per_lot_roundturn=spec_config["commission_per_lot_roundturn"],
        )
        
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
        
        print("✓ Configs created")
        
        # Run live trading checklist
        df = data_manager.get_buffer()
        
        print("\nRunning live trading checklist...")
        checks = live_trading_checklist(
            df=df,
            model_bundle=model_bundle,
            cfg=strategy_config,
            spec=symbol_spec,
        )
        
        print("\nChecklist results:")
        for key, value in checks.items():
            if isinstance(value, bool):
                status = "✓" if value else "✗"
                print(f"  {status} {key}: {value}")
            else:
                print(f"    {key}: {value}")
        
        if checks.get("all_passed"):
            print("\n✓ All live trading checks passed")
            return True
        else:
            print(f"\n✗ Failed checks: {checks.get('failed_checks')}")
            return False
        
    except Exception as e:
        print(f"✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_risk_manager(config):
    """Test 5: Risk manager functions correctly."""
    print("\n" + "="*80)
    print("TEST 5: Risk Manager")
    print("="*80)
    
    try:
        risk_config = config["risk"]
        
        limits = RiskLimits(
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
        
        rm = RiskManager(limits)
        
        print("✓ RiskManager created")
        
        # Test with mock trade
        account = AccountState(
            balance=10000.0,
            equity=10000.0,
            open_positions=0,
            daily_pnl=0.0,
            daily_trades=0,
        )
        
        # Simulate a trade check
        allowed, reason, lot_size = rm.check_trade_allowed(
            account=account,
            signal_probability=0.65,
            signal_direction=1,
            sl_price=2570.0,
            tp_price=2845.0,
            entry_price=2595.0,
        )
        
        print(f"  Test trade: allowed={allowed}, reason={reason}, lot_size={lot_size}")
        
        if allowed:
            print("✓ Risk manager allows reasonable trades")
        else:
            print(f"⚠ Trade blocked: {reason}")
        
        return True
        
    except Exception as e:
        print(f"✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all system tests."""
    print("\n" + "="*80)
    print("ICC ML LIVE TRADING SYSTEM - PRE-DEPLOYMENT TEST")
    print("="*80)
    print("\nThis script validates your system configuration.")
    print("Fix any issues before starting live trading.\n")
    
    results = {}
    
    # Test 1: Config
    success, config = test_config_loading()
    results['config'] = success
    
    if not success:
        print("\n✗ Cannot proceed without valid config")
        return
    
    # Test 2: Model
    success, model_bundle = test_model_loading(config)
    results['model'] = success
    
    if not success:
        print("\n✗ Cannot proceed without valid model")
        return
    
    # Test 3: Data
    success, data_manager = test_data_manager(config)
    results['data'] = success
    
    if not success:
        print("\n✗ Cannot proceed without data access")
        return
    
    # Test 4: Inference
    success = test_live_inference(config, model_bundle, data_manager)
    results['inference'] = success
    
    # Test 5: Risk
    success = test_risk_manager(config)
    results['risk'] = success
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name:.<40} {status}")
    
    all_passed = all(results.values())
    
    print("\n" + "="*80)
    
    if all_passed:
        print("✓ ALL TESTS PASSED")
        print("\nSystem is ready for deployment.")
        print("\nNext steps:")
        print("  1. Start with dry-run mode: python main.py --dry-run")
        print("  2. Verify dry-run behavior for 1-2 days")
        print("  3. Deploy to demo account for ≥1 month")
        print("  4. If demo matches backtest, consider live trading")
    else:
        print("✗ SOME TESTS FAILED")
        print("\nFix the issues above before deploying.")
        print("Re-run this script after fixing.")
    
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
