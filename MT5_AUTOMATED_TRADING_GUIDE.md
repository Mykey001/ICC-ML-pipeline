## 🚀 MT5 Fully Automated Trading System

**REAL automated trading: Connects to MT5, monitors live data, executes trades automatically**

---

## 🎯 What This System Does

### **Complete Automation:**
1. ✅ Connects to your MT5 account (demo or live)
2. ✅ Monitors real-time tick data every 10 seconds
3. ✅ Detects when new bars close (H1, M15, etc.)
4. ✅ Fetches historical data for indicators
5. ✅ Scores ICC signals with your trained ML model
6. ✅ Automatically executes trades when model says "TAKE"
7. ✅ Sets stop-loss and take-profit automatically
8. ✅ Manages positions (max 1 by default)
9. ✅ Logs everything to file
10. ✅ Runs 24/7 until you stop it

**This is NOT simulation - this places REAL orders!**

---

## 📋 Prerequisites

### **1. MetaTrader 5 Setup**
```
✓ MT5 terminal installed
✓ Account created (demo for testing)
✓ Logged in and connected
✓ Symbol (XAUUSDm) added to Market Watch
✓ Sufficient balance for lot size
```

### **2. Python Requirements**
```bash
pip install MetaTrader5
pip install pandas numpy scikit-learn joblib
```

### **3. Trained Model**
```
✓ Model trained (Tabs 1-8 in Streamlit)
✓ Model file exists: C:/Users/MYCkey98/Downloads/models/model_icc_meta.joblib
✓ Model validated and backtested
✓ Positive edge confirmed
```

---

## 🚀 Quick Start

### **Step 1: Open MT5**
```
1. Launch MetaTrader 5
2. Log in to your account (DEMO for first test!)
3. Go to View → Market Watch
4. Right-click → Add Symbol → XAUUSDm
5. Ensure connection status shows "Connected"
```

### **Step 2: Choose Your Mode**

**DRY RUN (Recommended First):**
```cmd
Double-click: START_MT5_LIVE_DRY_RUN.bat

What happens:
- Connects to MT5 ✓
- Monitors for signals ✓
- Scores with model ✓
- Logs decisions ✓
- NO orders placed ✗
```

**LIVE MODE (After Testing):**
```cmd
Double-click: START_MT5_LIVE_REAL.bat

What happens:
- Connects to MT5 ✓
- Monitors for signals ✓
- Scores with model ✓
- PLACES REAL ORDERS ✓✓✓
```

### **Step 3: Monitor**
```
Terminal/CMD shows:
- Connection status
- Bar monitoring
- Signal detection
- Trade execution
- All logged to: logs/mt5_trader_YYYYMMDD.log
```

### **Step 4: Stop**
```
Press Ctrl+C in terminal
System stops gracefully
Shows open positions
Closes MT5 connection
```

---

## 🎛️ Configuration

### **Edit Batch Files**

**START_MT5_LIVE_DRY_RUN.bat:**
```batch
REM Update these paths
set MODEL_PATH=C:\Users\MYCkey98\Downloads\models\model_icc_meta.joblib
set SYMBOL=XAUUSDm
set TIMEFRAME=H1
set LOT_SIZE=0.01
```

**Customization:**
- `MODEL_PATH`: Path to your trained model
- `SYMBOL`: Trading symbol (XAUUSDm, EURUSD, GBPUSD, etc.)
- `TIMEFRAME`: H1, H4, M15, M30, D1
- `LOT_SIZE`: Position size (0.01 = 0.01 lots)

---

## 📊 How It Works

### **System Flow:**

```
1. MT5 Connection
   ↓
2. Initialize (load model, get account info)
   ↓
3. Main Loop (every 10 seconds):
   ├── Check if new bar closed
   ├── If yes:
   │   ├── Fetch last 2000 bars from MT5
   │   ├── Compute indicators & features
   │   ├── Run ICC strategy
   │   ├── Score signal with ML model
   │   ├── If model says "TAKE":
   │   │   ├── Check position limits
   │   │   ├── Get current price
   │   │   ├── Calculate SL/TP
   │   │   └── Execute order (if not dry-run)
   │   └── Log decision
   └── Sleep 10 seconds
```

### **Bar Detection:**
```
System remembers: last_bar_time
Every 10 seconds: checks latest bar time
If latest_bar_time > last_bar_time:
    → New bar detected!
    → Process signal
```

### **Trade Execution:**
```
If signal = LONG:
    Type: BUY
    Price: Current ASK
    SL: From ICC strategy
    TP: From ICC strategy (2500 pips default)
    
If signal = SHORT:
    Type: SELL
    Price: Current BID
    SL: From ICC strategy
    TP: From ICC strategy
```

---

## 🔍 What You'll See

### **Startup:**
```
================================================================================
MT5 LIVE TRADER STARTED
================================================================================
Symbol: XAUUSDm
Timeframe: H1
Lot size: 0.01
Max positions: 1
Dry run: True
Check interval: 10s
================================================================================
⚠️  DRY RUN MODE - No real orders will be placed
Press Ctrl+C to stop

Connected to MT5 account: 12345678
Account balance: 10000.0 USD
Account leverage: 1:500
Symbol: XAUUSDm
  Digits: 3
  Point: 0.001
  Spread: 30 points
Initialized at bar: 2026-09-18 14:00:00
```

### **New Bar Detected:**
```
============================================================
NEW BAR - Processing iteration 45
============================================================
New bar formed: 2026-09-18 15:00:00
[2026-09-18 15:00] TAKE: LONG @ bar 1234 | Probability: 0.687 (threshold: 0.520) | SL: 2573.50000, TP: 2848.50000
Model says TAKE (probability=0.687)
Sending order: 1 0.01 lots @ 2598.45
Order executed successfully: ticket=98765432
  Volume: 0.01 lots
  Price: 2598.45
  SL: 2573.5, TP: 2848.5
✓ Trade executed successfully
============================================================
```

### **Signal Skipped:**
```
============================================================
NEW BAR - Processing iteration 52
============================================================
New bar formed: 2026-09-18 16:00:00
[2026-09-18 16:00] SKIP: SHORT @ bar 1235 | Probability: 0.485 (threshold: 0.520) | SL: 2625.00000, TP: 2350.00000
Model says SKIP (probability=0.485, threshold=0.520)
============================================================
```

### **No Signal:**
```
No ICC signal on this bar
Waiting for new bar... (iteration 60)
```

---

## 📁 Log Files

All activity logged to: `live_trading/logs/mt5_trader_YYYYMMDD.log`

**Contains:**
- Connection details
- Bar processing
- Signal detection
- Model decisions
- Trade execution
- Errors and warnings
- Position status

**Example log entry:**
```
2026-09-18 15:00:23 [INFO] New bar formed: 2026-09-18 15:00:00
2026-09-18 15:00:24 [INFO] [2026-09-18 15:00] TAKE: LONG @ bar 1234 | Probability: 0.687
2026-09-18 15:00:24 [INFO] Model says TAKE (probability=0.687)
2026-09-18 15:00:25 [INFO] Sending order: 1 0.01 lots @ 2598.45
2026-09-18 15:00:26 [INFO] Order executed successfully: ticket=98765432
```

---

## ⚙️ Advanced Configuration

### **Command-Line Usage:**

Instead of batch files, use Python directly:

```bash
cd live_trading

# Dry run
python mt5_live_trader.py \
  --model "C:/Users/MYCkey98/Downloads/models/model_icc_meta.joblib" \
  --symbol XAUUSDm \
  --timeframe H1 \
  --lot-size 0.01 \
  --max-positions 1 \
  --check-interval 10

# Live mode
python mt5_live_trader.py \
  --model "C:/Users/MYCkey98/Downloads/models/model_icc_meta.joblib" \
  --symbol XAUUSDm \
  --timeframe H1 \
  --lot-size 0.01 \
  --max-positions 1 \
  --live
```

### **Parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--model` | (required) | Path to trained model file |
| `--symbol` | XAUUSDm | Trading symbol |
| `--timeframe` | H1 | Bar timeframe |
| `--lot-size` | 0.01 | Position size in lots |
| `--max-positions` | 1 | Max simultaneous positions |
| `--check-interval` | 10 | Seconds between bar checks |
| `--live` | (flag) | Enable live trading mode |

---

## 🚨 Safety Features

### **Built-in Protection:**

1. **Position Limits**
   - Default: Max 1 position
   - Prevents overexposure
   - Configurable

2. **Dry-Run Mode**
   - Default mode
   - Logs everything
   - No real orders

3. **Magic Number**
   - Tracks system's orders
   - Won't interfere with manual trades
   - Default: 123456

4. **Graceful Shutdown**
   - Ctrl+C stops safely
   - Shows open positions
   - Closes MT5 connection

5. **Error Handling**
   - Catches exceptions
   - Logs errors
   - Continues running

---

## ⚠️ Important Warnings

### **Before Live Trading:**

✅ **MUST DO:**
- [ ] Test on DEMO for ≥1 month
- [ ] Verify trades execute correctly
- [ ] Check SL/TP are set properly
- [ ] Monitor logs daily
- [ ] Start with MINIMUM lot size (0.01)
- [ ] Understand you can lose money

❌ **NEVER:**
- Skip demo testing
- Use on live without testing
- Leave unmonitored
- Use lot size you can't afford to lose
- Ignore error messages

### **Risk Disclosure:**

```
⚠️  TRADING CARRIES RISK OF FINANCIAL LOSS

This system places REAL orders in your MT5 account.

- Past performance does not guarantee future results
- You can lose all your capital
- Only trade with money you can afford to lose
- Demo test for extended period first
- Monitor system continuously
- Stop immediately if performance degrades

The developers are NOT responsible for trading losses.
```

---

## 🔧 Troubleshooting

### **"MT5 initialization failed"**

**Check:**
1. MT5 terminal is open
2. You're logged in
3. Terminal shows "Connected"
4. Python can find MT5: `pip install MetaTrader5`

**Solution:**
```bash
# Test MT5 connection
python -c "import MetaTrader5 as mt5; print('MT5 installed:', mt5.initialize())"
```

### **"Symbol XAUUSDm not found"**

**Check:**
1. Symbol name is correct
2. Symbol in Market Watch
3. Symbol is available on your broker

**Solution:**
- Right-click Market Watch → Add Symbol
- Or change SYMBOL in batch file

### **"Failed to fetch bars"**

**Check:**
1. Symbol has historical data
2. MT5 is connected to server
3. Timeframe is valid

**Solution:**
- Open a chart for the symbol in MT5
- Wait for data to load
- Restart system

### **"Order failed: retcode=..."**

**Common codes:**
- 10006: Request rejected (check trading permissions)
- 10013: Invalid request (check lot size)
- 10016: Market closed
- 10019: No money (insufficient balance)

**Solution:**
- Check MT5 terminal for details
- Ensure trading is enabled
- Check account balance
- Wait for market hours

### **No signals appearing**

**This is NORMAL:**
- ICC signals are rare (2-10 per week on H1)
- System is working correctly
- Just waiting for setup

**Check logs:**
```
No ICC signal on this bar
```
= System is working, just no signal

---

## 📈 Expected Behavior

### **Signal Frequency:**
- **H1 timeframe**: ~2-10 signals per week
- **M15 timeframe**: More frequent
- **H4 timeframe**: Less frequent

### **System Activity:**
```
Every 10 seconds:
- Check for new bar
- If no new bar: sleep
- If new bar: process (takes 1-2 seconds)
```

### **Trade Execution:**
```
When model says TAKE:
- Order sent in <1 second
- Confirmation logged
- Position opened with SL/TP
```

---

## 📊 Monitoring Checklist

### **Daily:**
- [ ] Check system is still running
- [ ] Review log file
- [ ] Check open positions in MT5
- [ ] Verify account balance
- [ ] Look for errors

### **Weekly:**
- [ ] Calculate win rate
- [ ] Compare to backtest expectations
- [ ] Check for slippage/spread issues
- [ ] Review all executed trades
- [ ] Adjust lot size if needed

### **Monthly:**
- [ ] Full performance analysis
- [ ] Compare to model expectations
- [ ] Check for drift
- [ ] Consider retraining if >15% deviation

---

## 🎯 Deployment Phases

### **Phase 1: Dry-Run (2-3 days)**
```
Mode: DRY_RUN
Account: DEMO
Lot Size: 0.01
Duration: 2-3 days

Goal: Verify system works
Check: Signals detected, decisions logged, no crashes
```

### **Phase 2: Demo Live (1 month minimum)**
```
Mode: LIVE
Account: DEMO
Lot Size: 0.01
Duration: ≥1 month

Goal: Verify trades execute correctly
Check: Orders placed, SL/TP set, performance matches backtest
```

### **Phase 3: Live Micro (2 weeks)**
```
Mode: LIVE
Account: REAL
Lot Size: 0.01 (minimum)
Duration: 2 weeks

Goal: Verify on real account
Check: Everything works, no surprises
```

### **Phase 4: Live Gradual Scale**
```
Week 1-2: 0.01 lots
Week 3-4: 0.03 lots
Week 5-6: 0.05 lots
Week 7+: 0.10 lots (target)

Monitor closely at each step
```

---

## ✅ Quick Start Checklist

**Setup:**
- [ ] MT5 installed and logged in
- [ ] MetaTrader5 Python package installed
- [ ] Symbol added to Market Watch
- [ ] Model trained and exported
- [ ] Batch files configured with correct paths

**First Run (Dry):**
- [ ] Double-click START_MT5_LIVE_DRY_RUN.bat
- [ ] Verify connection successful
- [ ] Wait for first bar (up to 1 hour on H1)
- [ ] Check signal is processed
- [ ] Review log file
- [ ] Stop with Ctrl+C

**Demo Trading:**
- [ ] Verify dry-run works perfectly
- [ ] Switch to DEMO account in MT5
- [ ] Double-click START_MT5_LIVE_REAL.bat
- [ ] Type YES to confirm
- [ ] Monitor for 1 month
- [ ] Check trades are executed
- [ ] Verify SL/TP are correct
- [ ] Compare to backtest

**Live Trading (Only After Demo Success):**
- [ ] All demo tests passed
- [ ] Performance matches expectations
- [ ] Switch to LIVE account
- [ ] Start with 0.01 lots
- [ ] Monitor constantly
- [ ] Scale up gradually

---

## 🎉 Summary

You now have a **fully automated MT5 trading system** that:

✅ Connects to your MT5 account
✅ Monitors live market data
✅ Detects ICC strategy signals
✅ Scores with your ML model
✅ Executes trades automatically
✅ Manages positions with SL/TP
✅ Logs everything
✅ Runs 24/7

**Start with:** `START_MT5_LIVE_DRY_RUN.bat`

**Good luck! 🚀**

---

**Last Updated:** September 18, 2026  
**Version:** 1.0  
**Status:** Production Ready - FULLY AUTOMATED
