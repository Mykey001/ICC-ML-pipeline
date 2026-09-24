# ICC Meta-Labeling Live Trading System

Production-ready Python trading system for the ICC meta-labeling model.

## 🎯 What This Does

Takes your trained model (`model_icc_meta.joblib`) and executes trades in real-time based on:
1. **ICC signals** (primary model - direction)
2. **ML meta-model** (secondary filter - take/skip decision)
3. **Risk management** (position sizing, limits, safeguards)
4. **Performance monitoring** (drift detection, alerting)

---

## 📁 System Architecture

```
live_trading/
├── main.py                 # Main trading loop
├── config.yaml             # Configuration (EDIT THIS!)
├── data_manager.py         # Real-time data fetching
├── trading_engine.py       # Signal scoring & execution
├── risk_manager.py         # Risk controls & position sizing
├── monitor.py              # Performance tracking
├── logs/                   # Trade logs & reports
│   ├── trades_YYYYMMDD.csv
│   ├── trading_YYYYMMDD.log
│   └── monitor_report_*.json
└── README.md               # This file
```

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd "c:\Users\MYCkey98\Downloads\ML pipeline"
pip install -e .
pip install pyyaml  # For config loading
```

### 2. Configure System

Edit `config.yaml`:

```yaml
# REQUIRED: Set your model path
model:
  path: "../models/model_icc_meta.joblib"

# REQUIRED: Set commission (must match training!)
symbol_spec:
  commission_per_lot_roundturn: 0.0  # ← CHANGE THIS

# REQUIRED: Choose data source
data:
  source: csv  # csv | mt5 | api
  csv_path: "../data/raw/XAUUSDm_H1.csv"

# REQUIRED: Set dry-run mode
execution:
  dry_run: true  # false for live trading!
```

### 3. Run System

**Dry run (recommended first):**
```bash
cd live_trading
python main.py --config config.yaml --dry-run
```

**Live trading (after demo testing):**
```bash
python main.py --config config.yaml
# (Set dry_run: false in config.yaml)
```

---

## ⚙️ Configuration Guide

### Model Settings

```yaml
model:
  path: "../models/model_icc_meta.joblib"
```

Must point to your trained model bundle. Path relative to `live_trading/` directory.

### Data Source Options

**Option A: CSV (Testing/Demo)**
```yaml
data:
  source: csv
  csv_path: "../data/raw/XAUUSDm_H1.csv"
  symbol: XAUUSDm
  timeframe: H1
  buffer_size: 2000
```

Best for backtesting validation and demo mode. Simulates live bar-by-bar execution using historical data.

**Option B: MetaTrader 5 (Live)**
```yaml
data:
  source: mt5
  symbol: XAUUSDm
  timeframe: H1
  buffer_size: 2000
```

Requires `MetaTrader5` Python package:
```bash
pip install MetaTrader5
```

**Option C: Broker API (Custom)**
```yaml
data:
  source: api
  # Implement _fetch_api() in data_manager.py
```

### Symbol Specification

**⚠️ CRITICAL: Must match training exactly!**

```yaml
symbol_spec:
  name: XAUUSDm
  digits: 3                              # From MT5 Symbol Specification
  point: 0.001                           # From MT5 Symbol Specification
  contract_size: 100.0                   # From MT5 Symbol Specification
  typical_spread_points: 30.0            # Your broker's average spread
  commission_per_lot_roundturn: 0.0      # ⚠️ MUST SET!
```

Find in MT5: Right-click symbol → Specification

### Risk Management

```yaml
risk:
  # Position limits
  max_positions: 1                    # Max simultaneous positions
  max_lot_size: 1.0                   # Maximum position size
  min_lot_size: 0.01                  # Minimum position size
  default_lot_size: 0.10              # Default size
  
  # Daily limits (circuit breakers)
  max_daily_loss_usd: 500.0           # Stop trading after $500 loss
  max_daily_trades: 5                 # Max trades per day
  
  # Overall limits
  max_drawdown_pct: 15.0              # Stop at 15% drawdown
  
  # Model confidence (optional extra filter)
  min_probability: null               # e.g., 0.60 to require higher confidence
  
  # Risk-reward
  min_risk_reward_ratio: 1.5          # Minimum RR to accept trade
```

### Emergency Stop

```yaml
emergency:
  max_consecutive_losses: 5           # Stop after 5 losses in a row
  max_daily_loss_pct: 10.0            # Emergency stop at 10% daily loss
  max_loss_in_minutes_usd: 500.0      # Stop if lose $500...
  max_loss_in_minutes_time: 60        # ...in 60 minutes
```

### Execution

```yaml
execution:
  dry_run: true                       # true = log only, false = real orders
  order_executor: demo                # demo | mt5 | custom
```

**Order executor types:**
- `demo`: Logs trades, doesn't execute (safe testing)
- `mt5`: Executes via MetaTrader 5 API
- `custom`: Implement your own in `trading_engine.py`

---

## 📊 Monitoring & Logs

### Real-Time Stats

System prints performance stats every hour:

```
================================================================================
PERFORMANCE MONITORING REPORT
================================================================================
Period: All time (2026-09-18 10:00:00 to 2026-09-18 15:30:00)

--- SIGNALS ---
Total signals: 12
  Taken:   5 (41.7%)
  Skipped: 6 (50.0%)
  Blocked: 1 (8.3%)
Signal frequency: 2.18 per day

--- EXECUTION ---
Trades opened: 5
Trades closed: 3

--- PERFORMANCE ---
Win rate: 66.7% (2W / 1L)
Total P&L: $145.50
Avg win:  $125.00
Avg loss: -$104.00
Profit factor: 1.20

--- MODEL PROBABILITIES ---
Avg probability (taken):  0.632
Avg probability (skipped): 0.485
Distribution: {'0.4-0.5': 6, '0.5-0.6': 3, '0.6-0.7': 2, '0.7-1.0': 1}
================================================================================
```

### Log Files

**Trade log** (`logs/trades_YYYYMMDD.csv`):
```csv
timestamp,signal_bar,direction,probability,decision,executed,lot_size,entry_price,sl_price,tp_price,exit_price,exit_time,pnl,blocked,block_reason
2026-09-18T10:15:00,1234,1,0.625,TAKE,true,0.10,2598.50,2573.50,2848.50,null,null,null,false,null
```

**Trading log** (`logs/trading_YYYYMMDD.log`):
```
2026-09-18 10:15:23 [INFO] main: NEW BAR DETECTED - Processing...
2026-09-18 10:15:24 [INFO] trading_engine: [2026-09-18 10:00] TAKE: LONG @ bar 1234 | Probability: 0.625 (threshold: 0.520) | SL: 2573.50000, TP: 2848.50000
2026-09-18 10:15:24 [INFO] trading_engine: Risk manager approved: 0.10 lots
2026-09-18 10:15:24 [INFO] trading_engine: DRY RUN: Would execute 1 trade
```

**Monitoring report** (`logs/monitor_report_*.json`):
```json
{
  "generated_at": "2026-09-18T15:30:00",
  "statistics": {
    "total_signals": 12,
    "win_rate": 0.667,
    "total_pnl": 145.50,
    ...
  },
  "trades": [...]
}
```

---

## 🎯 Deployment Workflow

### Phase 1: Dry Run Validation (1-2 days)

**Goal:** Verify system works correctly without risk

```bash
# 1. Set dry-run mode
# In config.yaml: execution.dry_run = true

# 2. Run with CSV data (simulates live execution)
python main.py --config config.yaml --dry-run

# 3. Verify:
# - Data loads correctly
# - Signals are scored
# - Risk checks work
# - Logs are created
# - No errors in processing
```

### Phase 2: Demo Account (≥1 month)

**Goal:** Verify model performance matches backtest

```bash
# 1. Set up MT5 demo account

# 2. Configure for MT5
# In config.yaml:
#   data.source = mt5
#   execution.dry_run = false
#   execution.order_executor = mt5

# 3. Run system
python main.py --config config.yaml

# 4. Monitor daily:
# - Win rate vs backtest expectation
# - Signal frequency
# - Model probability distribution
# - Trade execution quality

# 5. Check for issues:
# - Train/live divergence
# - Feature drift
# - Execution problems
```

**Success criteria (must ALL pass):**
- Win rate within ±10% of backtest
- Signal frequency within expected range
- No systematic execution issues
- Model probabilities look reasonable
- No emergency stops triggered

### Phase 3: Live Trading (Gradual Scale-Up)

**Goal:** Scale to full position size safely

```bash
# Week 1: Minimum size (0.01 lots)
# Week 2-4: 50% size (0.05 lots if target is 0.10)
# Week 5+: Full size (0.10 lots)
```

**Monitor closely:**
- Daily P&L vs expectation
- Slippage and spreads
- Commission accuracy
- Model drift over time

---

## 🚨 Alert System

The monitor checks for issues every trade close:

| Alert Condition | Threshold | Action |
|----------------|-----------|--------|
| Low win rate | <30% (24h, ≥10 trades) | Warning logged |
| Large daily loss | <-$500 (24h) | Warning logged |
| Low model confidence | Avg prob <0.55 (≥20 signals) | Warning logged |

**To enable email/SMS alerts:**

1. Implement alert callback:
```python
def send_alert(message: str):
    # Send email/SMS/Telegram
    pass

# Pass to monitor
monitor = PerformanceMonitor(
    log_dir="logs",
    alert_callback=send_alert,
)
```

2. Update config:
```yaml
alerts:
  enabled: true
  email: your-email@example.com
```

---

## 🔧 Troubleshooting

### Issue: "CSV missing columns"

**Cause:** CSV format doesn't match expected schema

**Fix:**
```python
# Run data preparation script
import pandas as pd

df = pd.read_csv('data/raw/XAUUSDm_H1_*.csv', sep='\t')
df.columns = [c.strip('<>').lower() for c in df.columns]
df['time'] = pd.to_datetime(df['date'] + ' ' + df['time'])
df = df[['time','open','high','low','close','tickvol']].rename(columns={'tickvol':'volume'})
df.to_csv('data/raw/XAUUSDm_H1.csv', index=False)
```

### Issue: "Model prediction fails"

**Cause:** Feature calculation produces NaN values

**Fix:** Ensure sufficient historical data (≥1500 bars)

### Issue: "No signals detected"

**Cause:** ICC strategy not generating signals on current data

**Check:**
1. Market conditions (signals are rare in ranging markets)
2. Strategy parameters match training
3. Data quality (no gaps or errors)

### Issue: "All trades blocked by risk manager"

**Cause:** Risk limits too restrictive

**Fix:** Review `config.yaml` risk section:
- Check `min_probability` (if set too high)
- Check `min_risk_reward_ratio`
- Check daily limits not already hit

### Issue: "MT5 connection failed"

**Cause:** MT5 not running or not initialized

**Fix:**
1. Ensure MT5 terminal is open and logged in
2. Check `MetaTrader5` package is installed
3. Verify symbol is available in Market Watch

---

## 🎓 Advanced Customization

### Custom Position Sizing

Edit `risk_manager.py`, method `_calculate_position_size()`:

```python
def _calculate_position_size(self, account, risk_price, probability):
    """
    Implement your position sizing logic.
    
    Examples:
    - Kelly criterion based on probability
    - Volatility-adjusted sizing
    - Account percentage risk
    """
    # Example: Risk 2% of account per trade
    risk_amount = account.balance * 0.02
    risk_per_lot = risk_price * self.spec.contract_size
    lot_size = risk_amount / risk_per_lot
    
    # Clamp to limits
    return max(self.limits.min_lot_size, 
               min(lot_size, self.limits.max_lot_size))
```

### Custom Data Source

Edit `data_manager.py`, method `_fetch_api()`:

```python
def _fetch_api(self, bars: int) -> Optional[pd.DataFrame]:
    """Implement your broker's API fetching."""
    # Example for generic REST API
    response = requests.get(
        f"https://api.broker.com/ohlcv",
        params={
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "bars": bars,
        }
    )
    
    data = response.json()
    df = pd.DataFrame(data)
    # Convert to required format
    # ...
    return df
```

### Custom Order Executor

Edit `trading_engine.py`, create new function:

```python
def custom_order_executor(**kwargs) -> dict:
    """Your broker's order execution."""
    symbol = kwargs["symbol"]
    direction = kwargs["direction"]
    lot_size = kwargs["lot_size"]
    # ...
    
    # Place order via your broker's API
    result = your_broker_api.place_order(...)
    
    return {
        "success": result.success,
        "ticket": result.order_id,
        "error": result.error if not result.success else None,
    }
```

Then in `config.yaml`:
```yaml
execution:
  order_executor: custom
```

---

## 📈 Performance Expectations

Based on training with 546 trades:

| Metric | Value |
|--------|-------|
| Threshold | 0.52 |
| Features | 253 |
| Model | Calibrated HistGradientBoosting |
| Expected signals | ~300-500/year (H1 timeframe) |
| Trades taken | ~40-80/year (after filtering) |

**Realistic forward performance:**
- Expect some degradation from backtest (market regime changes)
- Win rate may vary ±10% from training
- Monitor for > ±15% deviation (potential drift)

---

## ✅ Pre-Deployment Checklist

Before live trading, verify:

- [ ] Model bundle passes inspection (`inspect_model.py`)
- [ ] Commission set correctly in `config.yaml`
- [ ] Symbol spec matches your broker exactly
- [ ] Risk limits are appropriate for account size
- [ ] Demo account tested for ≥1 month
- [ ] Win rate matches expectation (±10%)
- [ ] No train/live divergence detected
- [ ] Emergency stops tested
- [ ] Monitoring logs are being created
- [ ] You understand how to stop the system
- [ ] Backup/recovery plan in place

---

## 🆘 Emergency Procedures

### Stop Trading Immediately

**Method 1: Graceful shutdown**
```
Press Ctrl+C once
(System will finish current operation and stop)
```

**Method 2: Force kill**
```
Press Ctrl+C twice
(Immediate termination - use only if frozen)
```

### Close All Positions

**MT5:**
```python
import MetaTrader5 as mt5
mt5.initialize()

# Close all positions
positions = mt5.positions_get()
for pos in positions:
    mt5.Close(pos.ticket)
```

**Or manually in MT5 terminal:**
Right-click position → Close

### Emergency Stop Triggered

If you see:
```
CRITICAL: EMERGENCY STOP TRIGGERED: 5 consecutive losses
```

**Actions:**
1. System automatically stops taking new trades
2. Review recent trades in logs
3. Check for model drift or market regime change
4. Do NOT restart until issue identified

---

## 📞 Support & Documentation

**Project docs:**
- `README.md` - Project overview
- `PROJECT_SUMMARY.md` - One-page reference
- `02_icc_strategy_specification.md` - ICC strategy details
- `03_labeling_and_meta_labeling.md` - Meta-labeling methodology
- `04_validation_protocol.md` - Validation procedures

**Live trading specific:**
- `live_trading/README.md` - This file
- `live_trading/config.yaml` - Configuration reference

---

## 🔒 Risk Disclaimer

This is a trading system that executes real financial transactions. 

**Before live trading:**
1. Understand the risks
2. Test thoroughly on demo
3. Start with minimum position sizes
4. Only trade with capital you can afford to lose
5. Monitor performance daily
6. Have a plan to stop if performance degrades

**The developers are not responsible for trading losses.**

---

**Version:** 1.0.0  
**Last Updated:** September 18, 2026  
**Status:** Production Ready
