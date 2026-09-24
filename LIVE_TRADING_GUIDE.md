# Live Trading Deployment Guide

**Quick reference for taking your trained model from training → live trading**

---

## ✅ Model Status: READY

Your model (`model_icc_meta.joblib`) passed all structural checks:
- ✓ Calibrated model (optimal probabilities)
- ✓ 546 training trades (exceeds minimum 300)
- ✓ Optimized threshold (0.52)
- ✓ 253 features
- ✓ All required components present

---

## 🚀 Getting Started (5 Steps)

### Step 1: Pre-Flight Check (5 minutes)

```bash
cd "c:\Users\MYCkey98\Downloads\ML pipeline\live_trading"
python test_system.py
```

This validates:
- Configuration loads
- Model loads
- Data accessible
- Live inference works
- Risk manager functions

**All tests must pass before proceeding.**

---

### Step 2: Configure System (10 minutes)

Edit `live_trading/config.yaml`:

**Required changes:**
```yaml
# 1. Set commission (CRITICAL - must match training!)
symbol_spec:
  commission_per_lot_roundturn: 0.0  # ← CHANGE THIS

# 2. Verify model path
model:
  path: "../models/model_icc_meta.joblib"

# 3. Choose data source (start with CSV for testing)
data:
  source: csv
  csv_path: "../data/raw/XAUUSDm_H1.csv"
```

**Recommended changes:**
```yaml
# Adjust risk limits for your account
risk:
  default_lot_size: 0.10
  max_daily_loss_usd: 500.0
  max_daily_trades: 5
```

---

### Step 3: Dry Run Test (1-2 days)

Test the system without risking real money:

```bash
cd "c:\Users\MYCkey98\Downloads\ML pipeline\live_trading"
python main.py --config config.yaml --dry-run
```

**What it does:**
- Reads data bar-by-bar (simulating live)
- Scores signals with your model
- Applies risk checks
- Logs all decisions
- **Does NOT place real orders**

**What to verify:**
- [ ] System starts without errors
- [ ] Bars are processed correctly
- [ ] Signals are detected and scored
- [ ] Risk manager allows/blocks appropriately
- [ ] Logs are created in `logs/` directory
- [ ] Can stop gracefully with Ctrl+C

---

### Step 4: Demo Account (≥1 month)

Deploy to MT5 demo account for real validation:

**A. Setup MT5 connection:**
```bash
pip install MetaTrader5
```

**B. Update config:**
```yaml
data:
  source: mt5  # Changed from csv
  
execution:
  dry_run: false  # Changed from true
  order_executor: mt5  # Changed from demo
```

**C. Run system:**
```bash
python main.py --config config.yaml
```

**D. Monitor daily:**
Check logs in `live_trading/logs/`:
- `trading_YYYYMMDD.log` - System log
- `trades_YYYYMMDD.csv` - Trade record
- Performance stats (printed hourly)

**Success criteria (ALL must pass):**
- [ ] Win rate within ±10% of backtest
- [ ] Signal frequency ~2-10 per week (H1 timeframe)
- [ ] No systematic execution issues
- [ ] Model probabilities look normal (avg ~0.55-0.65 for taken trades)
- [ ] No emergency stops triggered
- [ ] Train/live divergence < 15%

**If demo fails any criteria:**
- Do NOT proceed to live
- Investigate the issue
- May need to retrain model with more recent data

---

### Step 5: Live Trading (Gradual Scale)

Only after successful demo testing:

**Week 1:** Minimum size
```yaml
risk:
  default_lot_size: 0.01
```

**Week 2-4:** Half size
```yaml
risk:
  default_lot_size: 0.05
```

**Week 5+:** Full size
```yaml
risk:
  default_lot_size: 0.10
```

Monitor for degradation at each stage.

---

## 📊 What to Monitor

### Daily Checks

1. **Check logs for errors:**
   ```bash
   tail -n 50 live_trading/logs/trading_YYYYMMDD.log
   ```

2. **Review today's trades:**
   ```bash
   # View trades CSV
   # Or check MT5 history
   ```

3. **System still running?**
   ```bash
   # Should see recent timestamps in logs
   ```

### Weekly Review

Run analysis script (create this based on logs):
```python
import pandas as pd

# Load week's trades
df = pd.read_csv('live_trading/logs/trades_YYYYMMDD.csv')

# Calculate metrics
win_rate = (df['pnl'] > 0).mean()
total_pnl = df['pnl'].sum()
avg_probability = df[df['decision']=='TAKE']['probability'].mean()

print(f"Win rate: {win_rate:.1%}")
print(f"Total P&L: ${total_pnl:.2f}")
print(f"Avg probability: {avg_probability:.3f}")
```

### Monthly Review

Compare to backtest expectations:
- Win rate
- Profit factor
- Signal frequency
- Drawdowns

**If >15% degradation:** Consider retraining with more recent data.

---

## 🚨 Emergency Procedures

### Stop System Immediately

**Graceful (recommended):**
```
Press Ctrl+C once
Wait for "Shutdown complete" message
```

**Force (if frozen):**
```
Press Ctrl+C twice
Or close terminal
```

### Emergency Stops Are Triggered Automatically

System stops taking new trades if:
- 5 consecutive losses
- Daily loss > 10% of account
- $500 loss in 60 minutes
- Daily loss limit reached
- Max drawdown exceeded

**When emergency stop triggers:**
1. System logs: `EMERGENCY STOP TRIGGERED: [reason]`
2. No new trades will be taken
3. Existing positions remain open
4. Investigate before restarting

### Close All Positions Manually

**In MT5:**
1. Open "Trade" tab
2. Right-click position
3. Select "Close"

**Or via Python:**
```python
import MetaTrader5 as mt5
mt5.initialize()

positions = mt5.positions_get()
for pos in positions:
    # Build close request
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": pos.ticket,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY,
        "price": mt5.symbol_info_tick(pos.symbol).bid if pos.type == 0 else mt5.symbol_info_tick(pos.symbol).ask,
    }
    mt5.order_send(request)
```

---

## 📁 System Files

```
ML pipeline/
├── models/
│   └── model_icc_meta.joblib          # Your trained model ✓
├── live_trading/
│   ├── main.py                        # Main trading loop
│   ├── config.yaml                    # Configuration ← EDIT THIS
│   ├── test_system.py                 # Pre-deployment tests
│   ├── data_manager.py                # Data fetching
│   ├── trading_engine.py              # Signal scoring & execution
│   ├── risk_manager.py                # Risk controls
│   ├── monitor.py                     # Performance tracking
│   ├── logs/                          # Log files (created on run)
│   │   ├── trading_YYYYMMDD.log
│   │   ├── trades_YYYYMMDD.csv
│   │   └── monitor_report_*.json
│   └── README.md                      # Full documentation
└── LIVE_TRADING_GUIDE.md              # This file
```

---

## 🎯 Quick Command Reference

**Test system:**
```bash
cd live_trading
python test_system.py
```

**Dry run (safe testing):**
```bash
python main.py --config config.yaml --dry-run
```

**Live trading (after demo validation):**
```bash
python main.py --config config.yaml
```

**Stop trading:**
```
Press Ctrl+C
```

**View today's log:**
```bash
tail -f logs/trading_$(date +%Y%m%d).log
```

**View all trades:**
```bash
cat logs/trades_*.csv | less
```

---

## ⚠️ Critical Reminders

1. **Test on demo first** - Minimum 1 month
2. **Start small** - Scale up gradually
3. **Monitor daily** - Check logs and performance
4. **Have stop criteria** - Know when to stop
5. **Commission must match** - Training and live must use same value
6. **Symbol spec must match** - Digits, point, contract size
7. **No modifications during live** - Test changes on demo first

---

## 📞 Troubleshooting Quick Fixes

| Issue | Fix |
|-------|-----|
| "Config file not found" | Run from `live_trading/` directory |
| "Model not found" | Check path in config.yaml |
| "CSV missing columns" | Run data prep script in README |
| "MT5 not initialized" | Ensure MT5 terminal is open |
| "No signals" | Normal - ICC signals are rare |
| "All trades blocked" | Check risk limits in config |
| System frozen | Press Ctrl+C to stop |

Full troubleshooting: See `live_trading/README.md`

---

## ✅ Pre-Go-Live Checklist

**Before demo:**
- [ ] All system tests pass
- [ ] Commission set correctly
- [ ] Risk limits appropriate
- [ ] Can start and stop system
- [ ] Logs are created correctly

**Before live:**
- [ ] Demo ran ≥1 month
- [ ] Win rate matches expectation (±10%)
- [ ] No emergency stops on demo
- [ ] Slippage/spreads acceptable
- [ ] Ready to monitor daily
- [ ] Know how to stop immediately
- [ ] Account funded appropriately

---

## 📈 Expected Performance

Based on your trained model:

| Metric | Value |
|--------|-------|
| Model type | Calibrated HistGradientBoosting |
| Features | 253 |
| Training trades | 546 |
| Threshold | 0.52 (optimized on pips) |
| Expected signals | ~300-500/year (H1) |
| Signals taken | ~40-80/year (after filtering) |
| Avg hold time | ~17 days |

**Realistic forward expectations:**
- Some degradation from backtest is normal
- Win rate may vary ±10%
- Monitor for >±15% deviation (potential drift)
- May need retraining every 6-12 months

---

**Good luck with your deployment! 🚀**

For detailed documentation, see `live_trading/README.md`
