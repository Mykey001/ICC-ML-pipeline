# Streamlit Live Trading UI - User Guide

## Overview

The Streamlit UI now includes a comprehensive live trading dashboard (Tab 9) with:
- ✅ **MT5 Connection Status** - Real-time connection monitoring
- ✅ **Live Log Viewer** - See logs directly in the UI
- ✅ **Real-time Stats** - Performance metrics updated live
- ✅ **Position Monitoring** - View open MT5 positions
- ✅ **Connection Testing** - Test MT5/CSV before starting
- ✅ **Emergency Controls** - Stop button with graceful shutdown

## Quick Start

### 1. Launch the UI
```bash
cd "C:\Users\MYCkey98\Downloads\ML pipeline"
streamlit run streamlit_app.py
```

### 2. Navigate to Tab 9: "Live Trading"

### 3. Select Your Model
- **Auto-detect models**: Automatically finds models in `models/` directory
- **Specify path manually**: Enter full path to your model file

The UI will load and validate the model, showing:
- Model type (e.g., HistGradientBoosting)
- Number of features
- Threshold value
- Training statistics

### 4. Configure Trading
**Data Source:**
- **CSV**: For testing with historical data
- **MT5**: For live trading with MetaTrader 5

**Execution Mode:**
- ☑️ **Dry Run** (recommended): Logs decisions without placing orders
- ☐ **Live Mode**: Places real orders (use only after thorough testing!)

**Risk Management:**
- Max Positions: 1
- Lot Size: 0.10
- Max Daily Loss: $500
- Max Daily Trades: 5
- Max Drawdown: 15%

### 5. Test Connection (Important!)
Click **"🔍 Test Connection"** before starting to verify:
- MT5 is running and logged in
- Symbol data is available
- CSV file exists (if using CSV mode)

Expected output:
```
✅ Connected to account 12345678
✅ Fetched 10 bars from XAUUSDm
```

### 6. Start Trading
Click **"▶️ Start Live Trading"**

The system will:
1. Initialize data manager
2. Load model
3. Set up risk management
4. Start monitoring

Status changes to **🟢 SYSTEM RUNNING**

### 7. Monitor Performance

## Features Explained

### MT5 Connection Status Section

**When using MT5 data source, you'll see:**

**Connection Metrics:**
- ✅ Status: Connected / ❌ Not connected
- Account number
- Account balance and currency
- Leverage ratio

**Symbol Information:**
- Current Bid/Ask prices
- Spread in points
- Symbol availability status

**Open Positions:**
- List of all open MT5 positions
- Ticket, symbol, type, volume
- Entry price, current price, P&L
- Opening time

**Use this to:**
- Verify MT5 is working before starting
- Monitor MT5 account status
- Check for existing positions
- Ensure symbol is available

### System Status Display

**Running mode shows:**
- Mode: DRY RUN or LIVE TRADING
- Data Source: CSV or MT5
- Symbol being traded
- Account balance and equity
- Daily P&L (with color coding)
- Open positions count
- Daily trades count
- Latest bar timestamp

### Performance Statistics

**Signal Stats:**
- Total signals seen
- Signals taken (executed)
- Signals skipped (model filtered)
- Signals blocked (risk manager)

**Closed Trades:**
- Number of closed trades
- Win rate percentage
- Total P&L
- Average win/loss amounts

**Model Probabilities:**
- Average probability for taken signals
- Average probability for skipped signals
- Probability distribution chart

### Recent Decisions Table

Shows last 10 signal decisions with:
- Timestamp
- Bar number
- Direction (LONG/SHORT)
- Model probability
- Decision (TAKE/SKIP)
- Executed status
- Block reason (if blocked)

### Live Log Viewer

**Features:**
- Real-time log display
- Color-coded by severity:
  - 🔴 Red: Errors
  - 🟡 Yellow: Warnings
  - 🟢 Green: Success
  - 🔵 Blue: Info
- Adjustable line count (10-200)
- Auto-refresh option (updates every 5 seconds)
- Download full log button
- Scrollable container

**Log shows:**
- Connection events
- Bar processing
- Signal detection
- Model decisions
- Trade executions
- Risk checks
- Errors and warnings

## Control Buttons

### ▶️ Start Live Trading
- Initializes all components
- Loads model
- Starts data manager
- Enables trading engine
- Changes status to RUNNING

### ⏸️ Stop Trading
- Gracefully stops engine
- Closes MT5 connection
- Saves final statistics
- Changes status to STOPPED

### 🔄 Check for New Bar
- Manually triggers bar check
- Processes if new bar closed
- Shows processing results
- Updates statistics

### 📊 Refresh Stats
- Reloads the page
- Updates all metrics
- Refreshes log display

### 🔍 Test Connection
- Tests MT5 connection
- Verifies symbol data
- Checks CSV file
- Shows connection status

## Workflows

### Testing a New Model

1. Train and export model (Tabs 1-8)
2. Go to Tab 9
3. Select your model (should auto-detect)
4. Set data source to CSV
5. Enable Dry Run
6. Click "Test Connection"
7. Click "Start Live Trading"
8. Click "Check for New Bar" repeatedly to simulate live trading
9. Monitor decisions and logs
10. Review performance after 50+ signals
11. Stop when satisfied

### Going Live with MT5

1. Complete testing workflow above
2. Open MT5 terminal and log in
3. Go to Tab 9
4. Set data source to MT5
5. Click "Test Connection" - verify green checkmarks
6. Review MT5 connection status section
7. Keep Dry Run enabled for final test
8. Click "Start Live Trading"
9. Monitor for 24-48 hours
10. Review all decisions and logs
11. If satisfied, disable Dry Run
12. Restart for live trading

### Monitoring Live Trading

1. Keep Streamlit UI open
2. Check status section regularly
3. Monitor daily P&L
4. Review recent decisions
5. Watch live logs for errors
6. Check MT5 positions align with UI
7. Verify risk limits are respected
8. Stop immediately if issues appear

## Safety Features

### Automatic Protections
- **Position Limits**: Won't exceed max_positions
- **Daily Loss Limit**: Stops if daily loss exceeds threshold
- **Emergency Stop**: Halts on consecutive losses
- **Drawdown Protection**: Stops at max drawdown percentage
- **Model Filtering**: Only takes high-probability signals

### Manual Controls
- **Stop Button**: Immediately stops trading
- **Dry Run Toggle**: Safe testing mode
- **Connection Test**: Pre-flight check
- **Log Monitoring**: Real-time error detection

### Warning Indicators
- 🚨 Emergency stop message (red)
- ⚠️ Trade blocked warnings (yellow)
- ❌ Connection failures (red)
- 🔴 System stopped (red)

## Troubleshooting

### MT5 Not Connecting
**Symptoms:**
- ❌ MT5 not connected
- Connection test fails

**Solutions:**
1. Open MT5 terminal
2. Log in to your account
3. Click "Test Connection" again
4. Check symbol is in Market Watch
5. Verify MetaTrader5 package installed: `pip install MetaTrader5`

### No Logs Appearing
**Symptoms:**
- "No log files found yet"
- Empty log viewer

**Solutions:**
1. Start the trading system first
2. Check `live_trading/logs/` directory exists
3. Process at least one bar
4. Refresh the page

### Model Not Found
**Symptoms:**
- "No trained models found"
- Model list is empty

**Solutions:**
1. Train a model in Tabs 1-8
2. Export model in Tab 8
3. Check `models/` directory
4. Use "Specify path manually" option
5. Enter full path to model file

### System Starts But No Signals
**Symptoms:**
- Status shows running
- No signals in Recent Decisions
- Logs show "No ICC signal"

**Explanation:**
- This is **normal** behavior
- ICC signals only occur when specific market conditions are met
- Model is working correctly
- Wait for HTF/LTF pivot alignments

**Verify:**
1. Check logs for "Processing bar" messages
2. Ensure data is updating
3. Review ICC strategy parameters
4. Compare to historical signal frequency

### High Skip Rate
**Symptoms:**
- Most signals show "SKIP"
- Model probability < threshold

**Explanation:**
- This is **correct** behavior
- Model is filtering low-quality signals
- Protects capital from losing trades

**Verify:**
1. Check model threshold (e.g., 0.55)
2. Compare probabilities to threshold
3. Review model performance in Tab 7
4. Confirm this matches backtest behavior

## Best Practices

### Before Going Live
- [ ] Test with CSV data first
- [ ] Run dry-run for 24+ hours
- [ ] Review all decisions and logs
- [ ] Verify signal quality matches backtest
- [ ] Test emergency stop
- [ ] Test stop/restart cycle
- [ ] Check log file creation

### During Live Trading
- [ ] Monitor UI regularly (every 4-8 hours)
- [ ] Check daily P&L vs expectations
- [ ] Review recent decisions
- [ ] Watch logs for errors
- [ ] Verify MT5 positions match UI
- [ ] Document any unusual behavior
- [ ] Stop if performance degrades >15%

### Maintenance
- [ ] Download logs weekly
- [ ] Review performance metrics
- [ ] Check disk space for logs
- [ ] Update model if needed (retrain)
- [ ] Test connection daily
- [ ] Backup model files
- [ ] Keep UI version updated

## Keyboard Shortcuts

- **Ctrl+R**: Refresh page (Firefox/Chrome)
- **F5**: Refresh page (all browsers)
- **Ctrl+F**: Search in logs
- **Ctrl+Shift+R**: Hard refresh (clear cache)

## Tips

1. **Keep it Open**: Leave Streamlit UI open in a browser tab
2. **Multiple Monitors**: Put UI on second monitor for continuous monitoring
3. **Auto-Refresh**: Enable log auto-refresh for passive monitoring
4. **Download Logs**: Save logs before they get too large
5. **Test Everything**: Test connection before every trading session
6. **Start Small**: Use minimum lot size initially
7. **Document Issues**: Screenshot any errors immediately

## Next Steps

1. ✅ Complete Tabs 1-8 (train and validate model)
2. ✅ Go to Tab 9
3. ✅ Test connection
4. ✅ Run dry-run for 24-48 hours
5. ✅ Review performance
6. ✅ Enable live trading when confident

---

**Remember:** The UI shows you **everything** the system is doing in real-time. Trust the model's SKIP decisions - they protect your capital.

For technical details, see:
- `MT5_SETUP_GUIDE.md` - MT5 configuration
- `QUICKSTART.md` - System overview
- `live_trading/README.md` - Live trading details
