# Model Selection Guide for Live Trading

**New Feature:** Choose which trained model to use from your collection

---

## 🎯 Quick Overview

The Live Trading tab (Tab 9) now includes a **Model Selection** feature that:
- ✅ Auto-detects models in common locations
- ✅ Shows model details (size, date, location)
- ✅ Allows manual path specification
- ✅ Validates model before use
- ✅ Displays model specifications and features

---

## 📁 How It Works

### **Option 1: Auto-Detect (Recommended)**

**What it does:**
- Searches for `.joblib` and `.pkl` files in:
  - `ML pipeline/models/`
  - `C:/Users/MYCkey98/Downloads/models/`
- Displays all found models in a table
- Shows size, modification date, and location

**How to use:**
1. Open Streamlit (Tab 9)
2. Select "Auto-detect models"
3. View the models table
4. Choose from dropdown
5. Click to expand details

**Example:**
```
Found 2 model(s):

Model                      Size    Modified           Location
model_icc_meta.joblib     12.5 MB 2026-09-18 14:23  C:/Downloads/models
model_icc_meta.joblib2    11.8 MB 2026-09-17 10:15  C:/Downloads/models

Select Model: ▼ model_icc_meta.joblib (12.5 MB) - 2026-09-18 14:23
```

### **Option 2: Manual Path**

**What it does:**
- Lets you specify exact path to any model file
- Useful for models in custom locations
- Validates file exists before proceeding

**How to use:**
1. Open Streamlit (Tab 9)
2. Select "Specify path manually"
3. Enter full path to model
4. System validates and loads

**Example:**
```
Model Path: C:/Users/MYCkey98/Downloads/models/model_icc_meta.joblib

✓ Using: C:/Users/MYCkey98/Downloads/models/model_icc_meta.joblib
```

---

## 📊 Model Details Display

After selecting a model, you'll see:

### **Model Specifications:**
- **Model Type**: e.g., HistGradientBoosting
- **Features**: Number of features (e.g., 253)
- **Threshold**: Optimized probability threshold (e.g., 0.52)

### **Training Information:**
- **Training Trades**: Sample size used (e.g., 546)
- **Features List**: View first 20 features with expand option

### **Status:**
- ✅ Green success = Model loaded and ready
- ❌ Red error = Model failed to load (with troubleshooting)

---

## 🔍 Your Current Models

Based on your folder `C:/Users/MYCkey98/Downloads/models/`, you have:

### **Model 1: model_icc_meta.joblib**
- Primary trained model
- Most recent version

### **Model 2: model_icc_meta.joblib2**
- Alternative/backup model
- Older version or different configuration

---

## 🎯 Which Model to Use?

### **Questions to Ask:**

**1. Which is more recent?**
- Use the model trained with latest data
- Check "Modified" date in the table

**2. Which performed better?**
- Check training metrics (if you kept logs)
- Compare backtest results
- Review validation scores

**3. Which matches current market?**
- If market regime changed, use model trained in similar conditions
- More recent ≠ always better

**4. Do I need to compare?**
- You can test both on demo account
- Switch between them in Tab 9
- See which performs better live

---

## 💡 Best Practices

### **For Testing:**
```
1. Load model_icc_meta.joblib
2. Configure dry-run mode
3. Test for 1-2 days
4. Record performance

5. Load model_icc_meta.joblib2
6. Same dry-run test
7. Compare results
8. Choose better performer
```

### **For Production:**
```
1. Use most recent model trained on latest data
2. Verify backtest results are good
3. Test on demo first (≥1 month)
4. Monitor for drift
5. Retrain every 3-6 months or when performance degrades
```

### **Model Rotation Strategy:**
```
Keep 3 models:
├── model_current.joblib     → Active in live trading
├── model_previous.joblib    → Backup (proven performer)
└── model_testing.joblib     → New model being validated

When new model proves better:
├── current → previous (archive)
├── testing → current (promote)
└── Train new → testing
```

---

## 🔧 Advanced: Compare Models

### **Quick Comparison Test:**

**Step 1: Test Model 1**
```
1. Tab 9: Select model_icc_meta.joblib
2. Dry-run: Process 100 bars
3. Record: Signals taken, win rate, P&L
```

**Step 2: Test Model 2**
```
1. Tab 9: Select model_icc_meta.joblib2
2. Dry-run: Same 100 bars
3. Record: Same metrics
```

**Step 3: Compare**
```
Metric              Model 1    Model 2    Winner
Signals Taken       25         30         Model 2 (more selective)
Win Rate            65%        58%        Model 1 (more accurate)
Total P&L           +$450      +$380      Model 1 (more profitable)
Avg Probability     0.635      0.598      Model 1 (more confident)

Decision: Use Model 1
```

---

## 🚨 Troubleshooting

### **"No models found"**

**Check 1:** Models exist in search locations
```bash
dir "C:\Users\MYCkey98\Downloads\models\*.joblib"
```

**Check 2:** File extensions are correct
- Should be `.joblib` or `.pkl`
- Not `.txt`, `.dat`, or other formats

**Solution:** Use manual path specification

### **"Failed to load model"**

**Possible causes:**
- Model corrupted
- Incompatible scikit-learn version
- Wrong file format

**Solutions:**
1. Try the other model
2. Retrain using Tabs 1-8
3. Check error details in expander
4. Verify file integrity

### **Model loads but performs poorly**

**Possible causes:**
- Model trained on different data
- Market regime changed
- Model overfitted to training period

**Solutions:**
1. Retrain with recent data
2. Check train/live divergence
3. Adjust risk parameters
4. Consider ensemble of models

---

## 📝 Model Management Tips

### **Naming Convention:**
```
Good:
├── model_icc_meta_2026-09-18.joblib
├── model_icc_meta_2026-09-15.joblib
├── model_icc_meta_baseline.joblib

Better:
├── model_icc_xauusd_h1_546trades_0.52thresh_20260918.joblib
└── Contains: symbol, timeframe, sample size, threshold, date
```

### **Keep Training Logs:**
```
For each model, save:
├── model_xxx.joblib          → The model
├── model_xxx_backtest.csv    → Backtest results
├── model_xxx_folds.json      → CV fold results
└── model_xxx_config.yaml     → Training configuration

Helps track which model is which!
```

### **Version Control:**
```
models/
├── production/
│   └── model_icc_meta.joblib     → Currently used live
├── testing/
│   └── model_icc_meta_new.joblib → Being validated
└── archive/
    ├── model_2026-09-01.joblib   → Old but kept for reference
    └── model_2026-08-15.joblib
```

---

## ✅ Quick Start Checklist

**Using Auto-Detect:**
- [ ] Open Tab 9
- [ ] Select "Auto-detect models"
- [ ] Review models table
- [ ] Choose most recent model
- [ ] Verify details load
- [ ] Proceed to configuration

**Using Manual Path:**
- [ ] Open Tab 9
- [ ] Select "Specify path manually"
- [ ] Enter full path
- [ ] Verify file found
- [ ] Check details load
- [ ] Proceed to configuration

---

## 🎉 Summary

You can now:
- ✅ Choose from multiple trained models
- ✅ See model details before using
- ✅ Switch between models easily
- ✅ Test and compare performance
- ✅ Use models from any location

**Your models:**
- `model_icc_meta.joblib` - Available ✓
- `model_icc_meta.joblib2` - Available ✓

**Next steps:**
1. Open Streamlit Tab 9
2. Select a model
3. Configure live trading
4. Start testing!

---

**Last Updated:** September 18, 2026  
**Feature:** Model Selection v1.0  
**Status:** ✅ Ready to use
