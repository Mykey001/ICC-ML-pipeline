# Live Trading UI - Quick Start Guide

**Interactive Streamlit dashboard for live trading with your trained model**

---

## 🚀 Quick Start (2 Steps)

### Step 1: Start the Interface

**Windows:**
```cmd
Double-click: START_LIVE_TRADING_UI.bat
```

**Or manually:**
```bash
cd "c:\Users\MYCkey98\Downloads\ML pipeline"
streamlit run streamlit_app.py
```

### Step 2: Navigate to Live Trading

1. Browser opens automatically at `http://localhost:8501`
2. Click **Tab 9: "Live Trading"** at the top
3. Configure and start trading!

---

## 📊 Dashboard Features

### **9-Tab Complete Pipeline**

```
Tab 1-8: Training Pipeline
├── 1. Data        → Load/fetch data
├── 2. Features    → Compute indicators
├── 3. Signals     → Generate ICC signals
├── 4. Labels      → Simulate trades
├── 5. Train       → Train model
├── 6. Validate    → Check quality
├── 7. Backtest    → Test performance
└── 8. Export      → Save model

Tab 9: Live Trading (NEW!)
├── Real-time monitoring
├── Interactive controls
├── Performance dashboard
└── Risk management UI
```

---

## 🎛️ Live Trading Tab Features

### **Configuration Panel**
- **Data Source**: CSV (testing) or MT5 (live)
- **Symbol & Timeframe**: Match your training
- **Execution Mode**: Dry-run or Live
- **Risk Parameters**: Position size, limits, stops

### **Control Buttons**
- ▶️ **Start Live Trading**: Initialize system
- ⏸️ **Stop Trading**: Graceful shutdown
- 🔄 **Check for New Bar**: Manual update (auto in production)
- 📊 **Refresh Stats**: Update dashboard

### **Live Monitoring**
- **Account Status**: Balance, equity, P&L
- **Performance Stats**: Signals, win rate, trades
- **Model Probabilities**: Distribution chart
- **Recent Decisions**: Last 10 signals with outcomes

### **Safety Features**
- ✅ Position limits
- ✅ Daily loss limits
- ✅ Drawdown protection
- ✅ Emergency stops
- ✅ Dry-run mode

---

## 📋 Usage Workflow

### **First Time Setup**

1. **Train Your Model** (Tabs 1-8)
   ```
   Tab 1 → Load data
   Tab 2 → Compute features
   Tab 3 → Generate signals
   Tab 4 → Create labels
   Tab 5 → Train model
   Tab 6 → Validate
   Tab 7 → Backtest
   Tab 8 → Export model
   ```

2. **Configure Live Trading** (Tab 9)
   - Set data source (CSV for testing)
   - Enable dry-run mode
   - Set risk parameters
   - Configure account balance

3. **Start System**
   - Click "Start Live Trading"
   - System initializes
   - Monitor dashboard

4. **Process Bars**
   - Click "Check for New Bar" to process data
   - View decisions in real-time
   - Monitor performance stats

### **Testing Workflow**

**Phase 1: Dry-Run with CSV (Day 1-2)**
```
1. Set source = CSV
2. Enable dry-run = True
3. Click Start
4. Click "Check for New Bar" repeatedly
5. Verify decisions are logged
6. Check performance stats
```

**Phase 2: Demo with MT5 (Month 1)**
```
1. Install MetaTrader 5 Python package
2. Ensure MT5 terminal is running
3. Set source = MT5
4. Keep dry-run = True (first week)
5. Then set dry-run = False
6. Monitor for ≥1 month
```

**Phase 3: Live Trading (Gradual)**
```
1. Verify demo performance matches backtest
2. Start with minimum lots (0.01)
3. Scale up gradually week by week
4. Monitor closely
```

---

## 📊 Dashboard Sections

### **1. Model Information**
Shows loaded model details:
- Model type (e.g., HistGradientBoosting)
- Number of features (253)
- Optimized threshold (0.52)
- Training sample size (546 trades)

### **2. Trading Configuration**

**Data Source:**
- CSV: Safe testing with historical data
- MT5: Real-time from MetaTrader 5

**Risk Management:**
- Max Positions: 1-5
- Lot Size: 0.01-10.0
- Daily Loss Limit: $100-$10,000
- Daily Trade Limit: 1-20
- Max Drawdown: 5%-50%

**Account:**
- Starting Balance: Set your account size

### **3. System Status**

**When Running:**
- 🟢 **SYSTEM RUNNING**
- Shows: Mode, Data Source
- Displays: Balance, Equity, P&L
- Updates: Open positions, daily trades

**When Stopped:**
- 🔴 **SYSTEM STOPPED**
- Instructions to start

### **4. Performance Statistics**

**Signal Metrics:**
- Total signals detected
- Signals taken (% of total)
- Signals skipped by model
- Signals blocked by risk manager

**Trade Performance:**
- Closed trades count
- Win rate (%)
- Total P&L ($)
- Average win/loss amounts

**Model Confidence:**
- Average probability for taken trades
- Average probability for skipped trades
- Probability distribution chart

### **5. Recent Decisions**
Table showing last 10 signals:
- Timestamp
- Bar number
- Direction (LONG/SHORT)
- Model probability
- Decision (TAKE/SKIP)
- Executed status (✅/❌)
- Block reason (if applicable)

---

## ⚙️ Configuration Examples

### **Safe Testing (Recommended Start)**
```
Data Source: csv
CSV Path: data/raw/XAUUSDm_H1.csv
Symbol: XAUUSDm
Timeframe: H1
Dry Run: ✅ (checked)
Max Positions: 1
Lot Size: 0.10
Max Daily Loss: $500
Starting Balance: $10,000
```

### **Demo Account**
```
Data Source: mt5
Symbol: XAUUSDm
Timeframe: H1
Dry Run: ✅ (checked first week)
Max Positions: 1
Lot Size: 0.10
Max Daily Loss: $500
Starting Balance: (your demo balance)
```

### **Live Trading (After Demo Validation)**
```
Data Source: mt5
Symbol: XAUUSDm
Timeframe: H1
Dry Run: ❌ (unchecked)
Max Positions: 1
Lot Size: 0.01 → 0.05 → 0.10 (scale up)
Max Daily Loss: $500
Starting Balance: (your live balance)
```

---

## 🔄 How It Works

### **Behind the Scenes**

When you click "Start Live Trading":
1. Loads your trained model
2. Initializes data manager (CSV or MT5)
3. Creates risk manager with your limits
4. Sets up emergency stops
5. Initializes performance monitor
6. Starts trading engine

When you click "Check for New Bar":
1. Fetches latest data
2. Detects if new bar closed
3. If yes: Scores ICC signal with ML model
4. Applies risk checks
5. Executes or blocks trade
6. Logs decision
7. Updates statistics

### **Data Flow**
```
CSV/MT5 Data → Data Manager → New Bar?
                                 ↓ Yes
                         ICC Signal Detected?
                                 ↓ Yes
                         Model Scores Signal
                                 ↓
                         TAKE or SKIP?
                                 ↓ TAKE
                         Risk Manager Checks
                                 ↓ Approved
                         Execute Order
                                 ↓
                         Log & Monitor
```

---

## 📈 Performance Monitoring

### **Real-Time Metrics**

**System Level:**
- Mode (Dry-run/Live)
- Data source status
- Connection health

**Account Level:**
- Current balance
- Current equity
- Open positions
- Daily P&L
- Daily trades executed

**Signal Level:**
- Total signals today
- Model take rate
- Risk block rate

**Trade Level:**
- Closed trades count
- Win rate
- Profit factor
- Total P&L

**Model Level:**
- Average confidence (taken)
- Average confidence (skipped)
- Probability distribution
- Drift indicators

### **Charts & Visualizations**

**Probability Distribution Bar Chart:**
Shows how model probabilities are distributed:
- 0.0-0.4: Low confidence
- 0.4-0.5: Below threshold
- 0.5-0.6: Just above threshold
- 0.6-0.7: Moderate confidence
- 0.7-1.0: High confidence

**Recent Decisions Table:**
Shows chronological log of recent signals with full details

---

## 🚨 Safety Features

### **Automatic Protections**

**Position Limits:**
- Prevents overexposure
- Max 1-5 simultaneous positions

**Daily Loss Limit:**
- Stops trading after threshold
- Default: $500 loss

**Drawdown Protection:**
- Monitors account drawdown
- Stops at max % (default 15%)

**Emergency Stops:**
Automatically trigger on:
- 5 consecutive losses
- 10% daily loss
- $500 loss in 60 minutes

### **Manual Controls**

**Stop Button:**
- Graceful shutdown
- Completes current operation
- Saves all logs

**Dry-Run Mode:**
- All decisions logged
- NO real orders placed
- Perfect for testing

---

## 📁 Log Files

All activity logged to: `live_trading/logs/`

**Files created:**
- `trading_YYYYMMDD.log` - System log
- `trades_YYYYMMDD.csv` - Trade details
- `monitor_report_*.json` - Performance reports

**View logs:**
```bash
# System log
type live_trading\logs\trading_20260918.log

# Trades CSV
# Open in Excel or pandas
```

---

## ⚠️ Important Notes

### **Before Live Trading**

✅ **Must complete:**
- [ ] Train model (Tab 5)
- [ ] Validate model (Tab 6)
- [ ] Backtest passes (Tab 7)
- [ ] Export model (Tab 8)
- [ ] Test dry-run mode (1-2 days)
- [ ] Test demo account (≥1 month)
- [ ] Verify performance matches backtest
- [ ] Understand all controls
- [ ] Know how to stop system

### **Commission Setting**

⚠️ **CRITICAL**: Commission must match training!

In Sidebar → Symbol Specification:
```
Commission / lot round turn: 0.0  ← SET THIS
```

Must be EXACT same value used in training or results will diverge.

### **Risk Management**

💡 **Recommended Starting Limits:**
- Max Positions: 1
- Lot Size: 0.01 (minimum)
- Daily Loss: 2-5% of account
- Drawdown: 10-15%

Scale up gradually as confidence grows.

---

## 🔧 Troubleshooting

### **Common Issues**

**"No trained model found"**
- Complete Tabs 1-8 first
- Click "Export" in Tab 8
- Model saved to `models/model_icc_meta.joblib`

**"Failed to initialize data manager"**
- Check CSV path is correct
- Ensure CSV has required columns
- For MT5: ensure terminal is running

**"MT5 not initialized"**
- Install: `pip install MetaTrader5`
- Open MT5 terminal
- Log in to account
- Symbol must be in Market Watch

**System freezes**
- Click Stop button
- Wait for graceful shutdown
- If frozen: close browser tab and restart

**No signals appearing**
- Normal - ICC signals are rare (2-10 per week)
- Check H1 timeframe has data
- Verify strategy parameters match training

---

## 📖 Additional Resources

**Documentation:**
- Full technical docs: `live_trading/README.md`
- Quick deployment: `LIVE_TRADING_GUIDE.md`
- System status: `DEPLOYMENT_COMPLETE.md`

**Configuration:**
- Command-line version: `live_trading/config.yaml`
- Main script: `live_trading/main.py`

**Testing:**
- System validation: `live_trading/test_system.py`

---

## 🎯 Quick Tips

### **For Testing**
1. Use CSV data source
2. Enable dry-run mode
3. Click "Check for New Bar" repeatedly to simulate time
4. Monitor decisions in table
5. Verify logs are created

### **For Demo**
1. Switch to MT5 data source
2. Keep dry-run enabled first week
3. Let system run in real-time
4. Check dashboard periodically
5. Review logs daily

### **For Live**
1. Verify demo matches backtest
2. Start with 0.01 lots
3. Monitor constantly first week
4. Scale up gradually
5. Stop if >15% deviation

---

## 🎉 You're Ready!

**Start the UI:**
```bash
streamlit run streamlit_app.py
```

**Navigate to Tab 9 and begin testing!**

---

**Version:** 1.0.0  
**Last Updated:** September 18, 2026  
**Status:** Production Ready  

**Good luck with your live trading! 🚀**
