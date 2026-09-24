# ICC ML Real-Time Trading System

## Complete Transparent ML Trading Pipeline

This system provides **full transparency** into every step of the ML trading pipeline with automatic bar monitoring and real-time activity logging.

---

## ✅ What This System Does

### **NO Simulation**
- Uses actual trained ML model
- Processes real OHLCV data
- Computes real indicators and features
- Makes real trading decisions
- No fake data, no placeholder logic

### **NO Guesswork**
- Every decision based on model probability
- Clear threshold-based TAKE/SKIP
- Risk checks before every trade
- Emergency stops on losses

### **Complete Transparency**
Every single operation is logged with:
- ✅ Timestamp (millisecond precision)
- ✅ Operation name and category
- ✅ Duration (how long it took)
- ✅ Details (counts, values, results)
- ✅ Status (success/warning/error)

---

## 🎯 Pipeline Steps (All Visible)

### 1. **DATA** - Fetch New Bar
```
[10:30:45.123] DATA          Initialize        → Initializing data manager
[10:30:45.234] DATA          FetchMT5          → Fetching 2000 bars from MT5
[10:30:45.456] DATA          MT5Init           → Initializing MT5 connection
[10:30:45.567] DATA          MT5Login          → Connected to account 12345678
[10:30:45.678] DATA          MT5Symbol         → Symbol XAUUSDm ready (spread: 30 points)
[10:30:45.890] DATA          MT5Fetch          → Received 2000 bars from MT5 (234ms)
[10:30:45.901] DATA          Validate          → Validating data quality
[10:30:45.920] DATA          Initialize        → Completed (786ms) | bars=2000, from=2024-01-01, to=2024-09-18
```

### 2. **INDICATORS** - Compute All Categories
```
[10:30:46.001] INDICATORS    ComputeAll        → Computing all indicator categories
[10:30:46.010] INDICATORS    Trend             → Computing trend indicators
[10:30:46.050] INDICATORS    Trend.EMA         → Computing EMA(8, 21, 55, 100, 200)
[10:30:46.070] INDICATORS    Trend.ADX         → Computing ADX and DI+/DI-
[10:30:46.090] INDICATORS    Trend             → Computed 35 trend indicators (89ms)
[10:30:46.100] INDICATORS    Momentum          → Computing momentum indicators
[10:30:46.150] INDICATORS    Momentum          → Computed 12 momentum indicators (50ms)
[10:30:46.160] INDICATORS    Volatility        → Computing volatility indicators
[10:30:46.210] INDICATORS    Volatility        → Computed 15 volatility indicators (50ms)
... (all 10 categories logged)
[10:30:47.234] INDICATORS    ComputeAll        → Computed 247 indicators across 10 categories (1233ms)
```

### 3. **FEATURES** - Build Transformations
```
[10:30:47.250] FEATURES      BuildAll          → Building all feature transformations
[10:30:47.260] FEATURES      Direction         → Computing direction features
[10:30:47.300] FEATURES      Direction         → Computed 25 direction features (40ms)
[10:30:47.310] FEATURES      Strength          → Computing strength/magnitude features
[10:30:47.360] FEATURES      Strength          → Computed 18 strength features (50ms)
... (all 6 transformation groups logged)
[10:30:48.123] FEATURES      BuildAll          → Built 312 features across 6 transformation groups (873ms)
```

### 4. **SIGNALS** - ICC State Machine
```
[10:30:48.150] SIGNALS       Generate          → Running ICC state machine
[10:30:48.250] SIGNALS       Generate          → Completed (100ms) | total_signals=15
[10:30:48.260] SIGNALS       Detected          → ICC signal: LONG
```

### 5. **MODEL** - Score Signal
```
[10:30:48.270] MODEL         Score             → Extracting features for model scoring...
[10:30:48.280] MODEL         Predict           → Scoring signal with trained model
[10:30:48.290] MODEL         Predict           → Model decision: TAKE (prob=0.7234, threshold=0.6500) (10ms)
```

### 6. **RISK** - Check Limits
```
[10:30:48.300] RISK          Check             → Evaluating trade against risk limits
[10:30:48.310] RISK          Approved          → Trade approved: 0.10 lots (10ms)
```

### 7. **EXECUTION** - Place Order
```
[10:30:48.320] EXECUTION     Execute           → Executing LONG order...
[10:30:48.330] EXECUTION     Order             → Placing LONG order
[10:30:48.450] EXECUTION     Order             → Order executed successfully (120ms)
```

---

## 🚀 Quick Start

### **1. Start the System**

Double-click: `live_trading\START_REALTIME_TRADING.bat`

Or run manually:
```bash
cd "c:\Users\MYCkey98\Downloads\ML pipeline"
streamlit run streamlit_app.py
```

### **2. Navigate to Tab 9**

Open browser → `http://localhost:8501` → Click **Tab 9: Real-Time Live Trading**

### **3. Configure Settings**

**Model Selection:**
- System auto-detects models in `models/` folder
- Select your trained model

**Data Source:**
- **CSV**: Use historical data (safe testing)
- **MT5**: Real-time data from MetaTrader 5

**Risk Settings:**
- Max Positions: 1-5
- Lot Size: 0.01-10.0
- Max Daily Loss: $500 default
- Max Daily Trades: 5 default

**Execution Mode:**
- ✅ **Dry Run**: Logs decisions, no real orders (RECOMMENDED for testing)
- ⚠️ **Live Mode**: Places real orders

### **4. Start Trading**

Click **▶️ START** button

System will:
1. Initialize data connection
2. Load model
3. Start background monitoring thread
4. Check for new bars every N seconds (configurable)
5. Process complete pipeline on each new bar
6. Display all activity in real-time

### **5. Monitor Activity**

**Live Activity Feed:**
- Shows every operation as it happens
- Color-coded by severity (Green=Success, Yellow=Warning, Red=Error)
- Switch between table view and raw text view

**Pipeline Statistics:**
- Total operations
- Average duration
- Category breakdown
- Longest operations

**Trading Performance:**
- Signals taken/skipped/blocked
- Win rate, P&L
- Recent decisions

---

## 📊 UI Features

### **Automatic Monitoring**
- ✅ No manual clicking required
- ✅ Checks for new bars every N seconds (default: 10s)
- ✅ Processes complete pipeline automatically
- ✅ Updates UI in real-time

### **Real-Time Activity Feed**
- ✅ Every operation logged with timestamp
- ✅ Duration tracking (milliseconds)
- ✅ Color-coded by severity
- ✅ Scrollable history (up to 200 lines)
- ✅ Export to file

### **Live Statistics**
- ✅ Current operation display
- ✅ Total operations count
- ✅ Average pipeline duration
- ✅ Error/success counts
- ✅ Category breakdown charts

### **System Status**
- ✅ Running/Stopped indicator
- ✅ Current mode (DRY RUN / LIVE)
- ✅ Account balance/equity
- ✅ Open positions
- ✅ Latest bar timestamp

### **Controls**
- **START**: Begin automatic monitoring
- **STOP**: Stop engine gracefully
- **REFRESH**: Manual UI refresh
- **CLEAR ACTIVITY**: Clear activity log
- **EXPORT LOG**: Save activity to file
- **Auto-refresh**: Toggle 3-second auto-refresh

---

## 📁 File Structure

```
ML pipeline/
├── live_trading/
│   ├── pipeline_logger.py           # Core logging system
│   ├── activity_feed_ui.py          # UI adapter for activity display
│   ├── data_manager.py              # Data fetching with logging
│   ├── instrumented_indicators.py   # Indicators with progress tracking
│   ├── instrumented_features.py     # Features with progress tracking
│   ├── realtime_engine.py           # Main real-time engine
│   ├── streamlit_tab9_realtime.py   # Tab 9 UI implementation
│   ├── logging_config.py            # Logging configuration
│   ├── START_REALTIME_TRADING.bat   # Quick launcher
│   └── logs/                        # All log files
│       ├── icc_trading_YYYYMMDD.log     # Main log
│       ├── icc_errors_YYYYMMDD.log      # Errors only
│       ├── pipeline_activity_YYYYMMDD.log  # Detailed pipeline log
│       └── activity_YYYYMMDD_HHMMSS.log   # Exported activity
│
├── streamlit_app.py                 # Main UI (Tab 9 calls new system)
└── models/
    └── model_icc_meta.joblib        # Trained model
```

---

## 🔧 Configuration

### **Check Interval**
How often to check for new bars (seconds):
- **5s**: Very responsive, more CPU usage
- **10s**: Default, balanced
- **30s**: Less frequent, lower CPU

### **Auto-Refresh UI**
Enable 3-second auto-refresh to see updates without manual refresh:
- ✅ ON: UI updates automatically (may slow down browser)
- ⬜ OFF: Click REFRESH button manually

### **Log Levels**
Edit `live_trading/logging_config.py`:
```python
# Default: INFO level
logger = setup_logging(log_level="INFO")

# For debugging: DEBUG level (very verbose)
logger = setup_logging(log_level="DEBUG")

# For production: WARNING level (errors/warnings only)
logger = setup_logging(log_level="WARNING")
```

---

## ⚠️ Safety Features

### **Emergency Stops**
System automatically stops if:
- Consecutive losses exceed threshold
- Daily loss exceeds limit
- Rapid losses in short time window

### **Risk Checks**
Every trade validated against:
- Maximum positions limit
- Position size limits
- Daily loss limits
- Daily trade count limits
- Drawdown limits

### **No Bypasses**
- Cannot skip risk checks
- Cannot override emergency stops
- Cannot place orders without model approval
- Cannot fake results or simulations

---

## 📝 Logs

### **Main Log** (`icc_trading_YYYYMMDD.log`)
All system activity with INFO+ level

### **Error Log** (`icc_errors_YYYYMMDD.log`)
Errors and critical issues only

### **Pipeline Log** (`pipeline_activity_YYYYMMDD.log`)
Detailed DEBUG-level pipeline execution

### **Activity Export** (`activity_YYYYMMDD_HHMMSS.log`)
Exported activity feed from UI

### **Log Rotation**
- Max size: 10MB per file
- Keeps 10 backup files
- Automatic rotation

---

## 🐛 Troubleshooting

### **"No models found"**
- Train a model in Tabs 1-8 first
- Check `models/` folder exists
- Model must be `.joblib` or `.pkl` file

### **"Failed to initialize data manager"**
- **CSV mode**: Check CSV file path is correct
- **MT5 mode**: Ensure MT5 terminal is running and logged in
- Check `data/raw/` folder for CSV files

### **"MT5 connection failed"**
- Open MetaTrader 5 terminal
- Log in to your account
- Ensure symbol is available
- Install: `pip install MetaTrader5`

### **"No activity showing"**
- Click START button first
- Wait for first new bar
- Check "Check Interval" setting
- Enable auto-refresh

### **UI not updating**
- Click REFRESH button
- Enable auto-refresh checkbox
- Check browser console for errors

---

## 🎓 Understanding the System

### **What Gets Logged?**

**Everything:**
- Data fetch (source, bars, timestamps)
- Each indicator category (count, duration)
- Each feature group (count, duration)
- ICC signals (direction, price levels)
- Model predictions (probability, threshold, decision)
- Risk checks (approved/blocked, lot size)
- Order execution (success/failure, ticket)

### **How Does It Work?**

1. **Background Thread**: Real-time engine runs in separate thread
2. **Bar Monitoring**: Checks for new bars every N seconds
3. **Pipeline Execution**: Processes complete pipeline on new bar
4. **Activity Feed**: Thread-safe queue stores all log entries
5. **UI Display**: Streamlit reads from activity feed and displays

### **Thread Safety**
- Activity feed uses thread locks
- No race conditions
- Safe concurrent access from engine and UI

---

## 📊 Performance

### **Typical Pipeline Duration**
- **Data Fetch**: 100-500ms (MT5), 50-100ms (CSV)
- **Indicators**: 500-1500ms (247 indicators)
- **Features**: 300-1000ms (312 features)
- **ICC Signals**: 50-150ms
- **Model Prediction**: 5-20ms
- **Risk Checks**: 5-10ms
- **Order Execution**: 50-200ms (MT5)

**Total**: 1-3 seconds per bar

### **Memory Usage**
- Activity feed: ~1000 entries max (~1MB)
- Data buffer: 2000 bars × 300 columns (~5MB)
- Model: 10-50MB depending on complexity

---

## 🚀 Next Steps

1. ✅ **Test with CSV data first** (dry-run mode)
2. ✅ **Verify all pipeline steps execute correctly**
3. ✅ **Check model decisions make sense**
4. ✅ **Test with MT5 data** (still dry-run)
5. ✅ **Run for 24 hours, monitor for errors**
6. ✅ **Switch to live mode ONLY after thorough testing**

---

## 📞 Support

For issues or questions:
1. Check activity feed for error messages
2. Review log files in `live_trading/logs/`
3. Export activity log for troubleshooting
4. Check MT5 connection status

---

**⚠️ TRADING CARRIES RISK. TEST THOROUGHLY BEFORE LIVE TRADING.**
