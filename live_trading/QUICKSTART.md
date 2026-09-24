# Live Trading Quick Start

## What Was Fixed

### Problem
- MT5 connection existed but wasn't actually connecting to live terminal
- Config defaulted to CSV data source
- Missing MT5 login credentials support

### Solution
1. ✓ Added MT5 login/password/server configuration
2. ✓ Fixed `data_manager.py` to properly initialize and maintain MT5 connection
3. ✓ Updated config to support both logged-in terminal and programmatic login
4. ✓ Added connection cleanup on shutdown
5. ✓ Verified data pipeline: MT5 → indicators → features → ICC signals → model

## Verified Data Pipeline

**The live system now processes data exactly like training:**

```
MT5 Raw Data
    ↓
compute_all_indicators() — ~150 indicators (EMAs, RSI, Bollinger, etc.)
    ↓
build_all_features() — ~200 features (trend, momentum, volatility, etc.)
    ↓
generate_icc_signals() — ICC strategy logic (HTF/LTF pivots, swing SL, TP)
    ↓
Model Scoring — predict win probability
    ↓
TAKE or SKIP decision
```

## How to Run

### Step 1: Test Connection (Recommended)
```bash
cd live_trading
python test_mt5_connection.py
```

Expected: All tests pass or only test 1 fails (needs 1500+ bars)

### Step 2: Configure MT5 Connection

**Option A: Use logged-in terminal** (easiest)
- Open MT5 and log in
- Leave it running
- Config already set to `source: mt5`

**Option B: Programmatic login**
Edit `config.yaml`:
```yaml
data:
  source: mt5
  mt5_login: YOUR_ACCOUNT_NUMBER
  mt5_password: "YOUR_PASSWORD"
  mt5_server: "YOUR_BROKER_SERVER"
```

### Step 3: Run in Dry-Run Mode
```bash
python main.py --config config.yaml --dry-run
```

Logs show:
```
✓ Connected to MT5 account: 12345678
✓ Symbol XAUUSDm ready
Initialized with 2000 bars
NEW BAR DETECTED - Processing...
ICC SIGNAL DETECTED → Model says TAKE/SKIP
DRY RUN - Would execute trade
```

### Step 4: Monitor Performance
- Watch logs in `logs/trading_YYYYMMDD.log`
- Review decisions (TAKE vs SKIP)
- Check model probabilities vs threshold
- Verify signals match expectations

### Step 5: Go Live (When Ready)

**⚠️ WARNING: Real money!**

Edit `config.yaml`:
```yaml
execution:
  dry_run: false  # DANGER!
  order_executor: mt5
```

Run:
```bash
python main.py --config config.yaml
```

System gives 10-second abort window.

## Key Configuration

### Must Match Training
```yaml
data:
  symbol: XAUUSDm  # Your trained symbol
  timeframe: H1    # Your trained timeframe

strategy:
  htf_pivot_len: 2     # Must match training
  ltf_pivot_len: 1
  tp_pips: 2500.0
  use_custom_swing_sl: true
  sl_swing_timeframe: "4h"
  sl_swing_pivot_len: 2

symbol_spec:
  # Must match training config
```

### Risk Management
```yaml
risk:
  max_positions: 1
  default_lot_size: 0.10
  max_daily_loss_usd: 500.0
  max_daily_trades: 5
  
execution:
  dry_run: true  # Start with this!
```

## Troubleshooting

### MT5 not connecting
- Check MT5 terminal is running (Option A)
- Verify credentials (Option B)
- Ensure symbol exists in broker

### No signals appearing
- Normal if market doesn't meet ICC conditions
- Check recent bars for HTF/LTF pivots
- Verify strategy parameters

### Model always says SKIP
- Model is working correctly!
- Filtering low-probability signals
- Check threshold vs actual probabilities

### Features contain NaN
- Normal for first ~500 bars
- Indicators need history to compute
- System continues once enough history

## What Each File Does

- `config.yaml` — All settings
- `main.py` — Main entry point, orchestrates system
- `data_manager.py` — MT5 connection & data fetching
- `trading_engine.py` — Signal scoring & execution logic
- `risk_manager.py` — Risk checks & limits
- `monitor.py` — Performance tracking
- `test_mt5_connection.py` — Verification script

## Understanding Model Decisions

### TAKE
```
Model Probability: 0.6234
Threshold: 0.5500
Decision: TAKE ✓
→ Historical win rate above threshold
→ Trade executed
```

### SKIP
```
Model Probability: 0.4821
Threshold: 0.5500
Decision: SKIP
→ Historical win rate below threshold
→ Trade filtered out
```

**This is correct behavior!** The model protects capital by skipping low-quality signals.

## Next Steps

1. [ ] Run test_mt5_connection.py
2. [ ] Observe dry-run for 24-48 hours
3. [ ] Review signal quality and decisions
4. [ ] Compare to backtest expectations
5. [ ] Adjust lot size if needed
6. [ ] Enable live trading gradually
7. [ ] Monitor actively for first week

## Files Created/Modified

**New:**
- `MT5_SETUP_GUIDE.md` — Detailed setup instructions
- `test_mt5_connection.py` — Connection verification
- `QUICKSTART.md` — This file

**Modified:**
- `config.yaml` — Added MT5 credentials
- `data_manager.py` — Fixed MT5 connection logic
- `main.py` — Pass credentials, cleanup on exit

## Verification

Run this to confirm everything works:
```bash
python test_mt5_connection.py
```

Expected output:
```
TEST 1: MT5 CONNECTION — ✓ PASS (or expected fail on 100 bars)
TEST 2: DATA PIPELINE — ✓ PASS
TEST 3: MODEL SCORING — ✓ PASS
TEST 4: CONFIG CONSISTENCY — ✓ PASS
```

---

**You're ready to trade!** Start with dry-run mode and observe carefully.
