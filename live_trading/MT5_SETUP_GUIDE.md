# MT5 Live Trading Setup Guide

## Overview

This guide walks you through connecting the live trading system to your actual MetaTrader 5 terminal and ensuring data is processed exactly like the training pipeline.

## Data Pipeline Verification

The system correctly processes live data through the same pipeline as training:

```
MT5 → OHLCV bars → indicators → features → ICC signals → model scoring → trade decision
```

**Key modules:**
- `data_manager.py`: Fetches OHLCV from MT5
- `live_inference.score_latest_signal()`: Runs full pipeline (indicators → features → signals)
- `trading_engine.py`: Orchestrates the process

## MT5 Connection Setup

### Option 1: Use Already Logged-In Terminal (Easiest)

1. **Open MT5 terminal** and log in to your account
2. **Leave it running** in the background
3. **Update config.yaml**:
   ```yaml
   data:
     source: mt5  # Changed from 'csv'
     symbol: XAUUSDm
     timeframe: H1
   ```
4. **Run the system** - it will connect to your open terminal:
   ```bash
   python main.py --config config.yaml --dry-run
   ```

### Option 2: Programmatic Login (Automated)

1. **Get your MT5 credentials**:
   - Account number (login)
   - Password
   - Server name (e.g., "MetaQuotes-Demo", "YourBroker-Real")

2. **Update config.yaml**:
   ```yaml
   data:
     source: mt5
     symbol: XAUUSDm
     timeframe: H1
     
     # MT5 login credentials
     mt5_login: 12345678  # Your account number
     mt5_password: "YourPassword"  # Your password
     mt5_server: "MetaQuotes-Demo"  # Your broker server
   ```

3. **Security note**: Keep config.yaml private! Consider using environment variables:
   ```python
   import os
   mt5_password = os.environ.get("MT5_PASSWORD")
   ```

## Configuration Checklist

### 1. Data Source
```yaml
data:
  source: mt5  # ✓ Changed from 'csv'
```

### 2. Symbol Must Match Training
```yaml
data:
  symbol: XAUUSDm  # Must match your trained model
```

### 3. Timeframe Must Match Training
```yaml
data:
  timeframe: H1  # Must match your trained model
```

### 4. Strategy Parameters Must Match Training
```yaml
strategy:
  htf_pivot_len: 2  # Must match training
  ltf_pivot_len: 1
  tp_pips: 2500.0
  use_custom_swing_sl: true
  sl_swing_timeframe: "4h"
  sl_swing_pivot_len: 2
```

**Critical:** If these don't match training, the model will see different signals!

### 5. Symbol Specification Must Match Training
```yaml
symbol_spec:
  name: XAUUSDm
  digits: 3
  point: 0.001
  contract_size: 100.0
  typical_spread_points: 30.0
  commission_per_lot_roundturn: 0.0  # Update for your broker!
```

### 6. Model Path
```yaml
model:
  path: "../../models/model_icc_meta.joblib"  # Verify this exists
```

## Testing the Connection

### Step 1: Dry Run Test
```bash
cd live_trading
python main.py --config config.yaml --dry-run
```

**Expected output:**
```
✓ Connected to MT5 account: 12345678
  Balance: 10000.00 USD
  Leverage: 1:100
✓ Symbol XAUUSDm ready (spread: 30 points)
Initialized with 2000 bars, latest: 2026-09-18 12:00:00
✓ Data manager initialized
✓ Trading engine started
```

### Step 2: Verify Data Pipeline
The log should show:
```
Processing bar 1999, time=2026-09-18 12:00:00
[Signal scoring with full feature pipeline]
```

### Step 3: Check for Signals
When an ICC signal appears:
```
NEW BAR DETECTED - Processing...
═══════════════════════════════════════════
ICC SIGNAL DETECTED
Direction: BUY (1)
Entry: 2645.120
SL: 2630.500 (14.6 pips)
TP: 2670.120 (25.0 pips)
Model Probability: 0.6234
Threshold: 0.5500
Decision: TAKE ✓
═══════════════════════════════════════════
DRY RUN - Would execute: BUY 0.10 lots
```

## Switching to Live Trading

**WARNING: This places real orders with real money!**

### Prerequisites
1. ✓ Tested thoroughly in dry-run mode
2. ✓ Verified model performance on recent data
3. ✓ Confirmed all parameters match training
4. ✓ Set appropriate lot sizes for your account
5. ✓ Configured risk limits

### Enable Live Trading
```yaml
execution:
  dry_run: false  # ⚠️ DANGER ZONE
  order_executor: mt5  # Use real MT5 execution
```

### Run Live
```bash
python main.py --config config.yaml
```

System will give you 10 seconds to abort:
```
🔴 LIVE TRADING MODE - Real orders will be placed!
    Press Ctrl+C within 10 seconds to abort...
```

## Data Pipeline Details

### What Happens on Each New Bar

1. **Data Manager** fetches latest OHLCV from MT5
   - Maintains rolling buffer of 2000 bars
   - Detects new bar closes

2. **Live Inference** processes the data:
   ```python
   # In live_inference.score_latest_signal():
   df_with_indicators = compute_all_indicators(df)  # ~150 indicators
   df_with_features = build_all_features(df_with_indicators)  # ~200 features
   signals = generate_icc_signals(df, cfg, spec)  # ICC strategy
   ```

3. **Model Scoring**:
   - Extracts features for the last bar
   - Predicts win probability
   - Compares to threshold → TAKE or SKIP

4. **Risk Checks**:
   - Position limits
   - Daily loss limits
   - Risk/reward ratio
   - Emergency stop conditions

5. **Execution** (if all checks pass):
   - Submits order to MT5
   - Logs trade details
   - Updates monitoring

### Feature Consistency Verification

The system ensures training/live consistency:

```python
# Training saved these:
model_bundle["feature_cols"]  # Exact feature names
model_bundle["threshold"]  # Optimal threshold

# Live uses same:
features = df_with_features.loc[last_idx, feature_cols]
decision = "TAKE" if probability >= threshold else "SKIP"
```

## Troubleshooting

### "MT5 initialization failed"
- Ensure MT5 terminal is installed
- Check if terminal is running (Option 1)
- Verify credentials (Option 2)
- Install package: `pip install MetaTrader5`

### "Symbol XAUUSDm not found"
- Check symbol name in your broker
- Some brokers use "XAUUSD" not "XAUUSDm"
- Update config.yaml with correct symbol

### "Insufficient data: X bars (need ≥1500)"
- Increase buffer_size in config
- Ensure symbol has historical data in MT5
- Wait for more bars to accumulate

### "Features contain NaN values"
- Normal for first ~500 bars (indicators need history)
- System will warn but continue
- No real trades until features are valid

### "Model says SKIP for all signals"
- Model is working correctly - it's filtering out low-quality signals
- Check model threshold vs probabilities
- Verify training performance on recent data

### No signals appearing
- Verify ICC strategy parameters match training
- Check if market conditions match training data
- Review ICC signal logic in `strategy_icc.py`

## Performance Monitoring

### Real-time Logs
```bash
tail -f logs/trading_20260918.log
```

### Statistics
Press Ctrl+C to stop and see final stats:
```
═══════════════════════════════════════════
FINAL STATISTICS
═══════════════════════════════════════════
Signals seen: 15
Signals taken: 8
Signals skipped: 7 (46.7%)
Trades executed: 8
Win rate: 62.5%
Net P&L: +125.5 pips
═══════════════════════════════════════════
```

### Full Report
Exported to `logs/performance_report_YYYYMMDD_HHMMSS.json`

## Safety Features

### Automatic Protections
- **Position limits**: Won't exceed max_positions
- **Daily loss limit**: Stops if daily loss > threshold
- **Emergency stop**: Halts on consecutive losses
- **Risk/reward filter**: Skips trades below min R:R
- **Model confidence**: Optional min probability filter

### Manual Controls
- **Ctrl+C**: Graceful shutdown (finishes current operation)
- **config.yaml edits**: Reload by restarting
- **Close positions**: Use MT5 terminal directly

## Best Practices

1. **Start small**: Use minimum lot size initially
2. **Monitor closely**: Watch first few days actively
3. **Track performance**: Compare to backtest expectations
4. **Check logs daily**: Review decisions and errors
5. **Update model**: Retrain periodically on new data
6. **Respect the system**: Don't override model decisions manually

## Next Steps

1. [ ] Configure MT5 credentials in config.yaml
2. [ ] Run dry-run test
3. [ ] Verify data pipeline in logs
4. [ ] Observe for 24-48 hours
5. [ ] Review first signals and decisions
6. [ ] Gradually increase lot size if performing well
7. [ ] Set up monitoring alerts
8. [ ] Document any issues or observations

---

**Remember**: The model filters signals based on historical win probability. "SKIP" is not a failure - it's the system protecting your capital.
