# ICC-ML Project Summary

**One-page quick reference** | Full details → [CODEBASE_INDEX.md](CODEBASE_INDEX.md)

---

## 🎯 What Is This?

A **meta-labeling ML pipeline** for trading. The ICC strategy picks direction; ML decides take/skip.

```
Primary Model (ICC) → "Go LONG at X"
Meta-Model (ML)     → "Should I take this signal?" [YES/NO]
```

**Why this works:** Easier to predict "is this setup good?" than "which way will price go?"

---

## 📂 Key Files to Know

| File | What It Does |
|------|--------------|
| `README.md` | Start here: quick start, project layout |
| `streamlit_app.py` | **Main GUI** (8 tabs: data → features → train → deploy) |
| `01_icc_model_training.ipynb` | Step-by-step notebook walkthrough |
| `default.yaml` | ⚠️ **Set your broker's commission here** |
| `ICC_Swing_EA_Simplified.mq5` | MT5 Expert Advisor (reference implementation) |
| `data/raw/XAUUSDm_H1.csv` | ✅ Cleaned data ready to use |
| `01-05_*.md` | **Read these first** → methodology docs |

---

## 🚦 Quick Start

```bash
# Install
pip install -e .

# Run GUI
streamlit run streamlit_app.py

# Or notebook
jupyter lab 01_icc_model_training.ipynb
```

**GUI tabs (do in order):**
1. Data → upload/fetch OHLCV
2. Features → compute ~110 features
3. Signals → run ICC state machine
4. Labels → simulate trades
5. Train → walk-forward CV
6. Validate → IC analysis + self-tests
7. Backtest → sequential execution
8. Export → save model if all checks pass

---

## ⚠️ Before You Start

### 1. Set Commission (REQUIRED)
```yaml
# In default.yaml:
commission_per_lot_roundturn: 0.0  ← CHANGE THIS
```
Find it: MT5 → Account → Trade conditions, or ask broker

### 2. Understand TP Convention
```
TP_Pips = 2500 means:
  XAUUSD (3 digits) → $25.00 move    ✅ sane
  EURUSD (5 digits) → 0.2500 move    ❌ unreachable
```

### 3. History Depth
- **Current:** 2.7 years (below recommended)
- **Recommended:** 7–10 years (multiple regimes)

---

## 📊 Pipeline in 8 Steps

```
1. DATA        → Load OHLCV (MT5/CSV/synthetic)
2. FEATURES    → ~110 engineered features (10 categories)
3. SIGNALS     → ICC state machine (indication→correction→continuation)
4. LABELS      → Simulate each trade to real SL/TP exit
5. TRAIN       → Purged walk-forward CV (5 folds)
6. VALIDATE    → IC analysis + two-sided self-tests
7. BACKTEST    → Sequential execution + parity checks
8. EXPORT      → Save model if go/no-go criteria met
```

---

## 🎓 Documentation (Read These First)

| Doc | Topic | Time |
|-----|-------|------|
| `README.md` | Overview + quick start | 5 min |
| `02_icc_strategy_specification.md` | ICC state machine | 10 min |
| `03_labeling_and_meta_labeling.md` | Why meta-labeling | 8 min |
| `04_validation_protocol.md` | How we prevent false results | 12 min |
| `01_market_information_taxonomy.md` | Feature engineering | 15 min |
| `05_data_requirements.md` | Data export guide | 8 min |

**Total reading time:** ~60 minutes  
**Worth it?** Yes. These explain WHY the design choices matter.

---

## 🧪 Validation (How We Know Results Are Real)

### Two-Sided Self-Test
| Test | Data | Expected | Result |
|------|------|----------|--------|
| **A (leakage check)** | Random walk | AUC ~0.50 (no edge) | 0.578 ✅ |
| **B (capability check)** | Injected signal | AUC >0.70 (finds it) | 1.000 ✅ |

**Both must pass.** If only A passes → broken pipeline. If only B passes → leaking pipeline.

### Go/No-Go Checklist (Before Live)
- [ ] TP hit rate > 5%
- [ ] ≥300 labeled trades
- [ ] Positive edge in ≥4/5 folds
- [ ] Beats take-all baseline (net pips)
- [ ] All parity checks pass
- [ ] Both self-tests pass
- [ ] Demo forward-test ≥1 month

**If any fail → DO NOT DEPLOY**

---

## 🔑 Key Concepts

### Meta-Labeling
```python
# Wrong (hard):
"Will price go up or down?"

# Right (easier):
"Given ICC says go LONG, should I take it?"
```

### Labeling ≠ Backtest
```python
# Labeling mode (training data):
simulate_icc_trades(enforce_one_position=False)
# → Every signal simulated independently
# → Maximizes training samples

# Backtest mode (P&L):
simulate_icc_trades(enforce_one_position=True)
# → One position at a time
# → Measures real account performance
```

### Threshold Selection
```python
# Wrong:
threshold = argmax(accuracy)

# Right:
threshold = argmax(net_pips)  # with min_trades constraint
```

### The Honest Baseline
```python
edge_pips = model_pips - baseline_take_all_pips

# 55% win rate is meaningless if baseline wins 55%
# Report edge, not raw performance
```

---

## 🏗️ Architecture

### 10 Feature Categories
1. **Trend** → direction, strength, acceleration
2. **Momentum** → speed, exhaustion
3. **Volatility** → current vs normal
4. **Structure** → swing highs/lows
5. **Volume** → participation
6. **Mean Reversion** → stretch & snap
7. **Regime** → market state
8. **Price Action** → candle geometry
9. **Liquidity/SMC** → liquidity sweeps
10. **Time/Session** → temporal context

### Extraction Templates
```python
# Template A (Continuous):
direction, strength, acceleration

# Template B (Discrete):
state, magnitude, recency
```

**Output:** ~110 normalized features

---

## 📈 What to Expect

### On Synthetic Data (Random Walk)
- **Expected:** No edge (AUC ~0.50)
- **Measured:** 0.578 ✅
- **Interpretation:** Pipeline correctly finds no pattern where none exists

### On Real Data (XAUUSD)
- **Baseline:** 37–44% win rate (measured)
- **Goal:** Beat baseline by filtering losers
- **Success:** `edge_pips > 0` in ≥80% of folds

### Realistic Trade Frequency
- **Signals per year:** ~300-500 (H1 timeframe)
- **Avg hold time:** ~420 bars (17.5 days on H1)
- **Sequential blocking:** ~90% of signals blocked by one-position rule
- **Model-approved:** ~40-80 trades/year (after filtering)

---

## 🛠️ Status Check

| Component | Status | Notes |
|-----------|--------|-------|
| Documentation | ✅ | 5 detailed methodology docs |
| GUI | ✅ | Full 8-tab pipeline |
| Config | ⚠️ | Commission = 0 (placeholder) |
| Data | ✅ | XAUUSDm H1 cleaned & ready |
| History | ⚠️ | 2.7 years (want 7-10) |
| Notebook | ⚠️ | Empty (no signatures) |
| Source code | ❌ | `src/icc_ml/` not visible |
| Tests | ❌ | `tests/` not in workspace |

---

## 🚨 Common Mistakes to Avoid

### 1. Wrong TP for Symbol
```
EURUSD with tp_pips=2500 → 0% hit rate
Always check: diagnose_trades() → tp_hit_rate
```

### 2. Not Setting Commission
```
Train with commission=0, live with commission>0
→ Instant train/live divergence
```

### 3. Insufficient History
```
3 years all in trending regime
→ Model fails when regime changes
→ Walk-forward doesn't reveal this
```

### 4. Trusting High Accuracy
```
90% accurate on losers ≠ profitable
Check: beats_baseline_on_net_pips
```

### 5. Skipping Self-Tests
```
"Looks profitable, let's deploy"
→ Could be leakage, not edge
→ Run tests/validate_pipeline.py first
```

---

## 📞 Quick Troubleshooting

**Problem:** "0% TP hit rate"  
**Fix:** Reduce `tp_pips` for 5-digit quotes (250-400 range)

**Problem:** "Too few signals"  
**Fix:** Extend history or switch to more active symbol

**Problem:** "Negative edge despite high AUC"  
**Fix:** Check threshold selection (optimize on pips, not accuracy)

**Problem:** "Test A fails (AUC >0.60 on random data)"  
**Fix:** Pipeline is leaking → check entry timing, feature calculation

**Problem:** "Test B fails (AUC <0.70 on injected signal)"  
**Fix:** Pipeline can't learn → check feature extraction, labels

---

## 🎯 Success Formula

```python
good_data = (
    7+ years history
    × correct broker specs
    × appropriate tp_pips for symbol
)

sound_methodology = (
    meta_labeling
    × execution_realism
    × purged_walk_forward
    × honest_baseline
)

rigorous_validation = (
    two_sided_tests
    × live_parity_checks
    × go_no_go_criteria
)

success = good_data × sound_methodology × rigorous_validation
```

---

## 📚 Next Steps

### For First-Time Users
1. Read README.md (5 min)
2. Read 02_icc_strategy_specification.md (10 min)
3. Read 03_labeling_and_meta_labeling.md (8 min)
4. Set commission in default.yaml
5. Run GUI: `streamlit run streamlit_app.py`
6. Work through tabs 1-8

### For Developers
1. Check if `src/icc_ml/` exists (not visible in workspace)
2. Run self-tests: `python tests/validate_pipeline.py`
3. Review CODEBASE_INDEX.md for full architecture
4. Extend features or add new models

### For Researchers
1. Read all 5 methodology docs (60 min)
2. Study validation protocol (04_validation_protocol.md)
3. Run notebook (01_icc_model_training.ipynb)
4. Experiment with different timeframes/symbols

---

## 📖 Related Files

- **Full index:** [CODEBASE_INDEX.md](CODEBASE_INDEX.md) (comprehensive technical reference)
- **Project root:** [README.md](README.md) (quick start & layout)
- **Methodology:** 01-05_*.md (5 detailed documents)

---

**Last Updated:** September 16, 2026  
**Version:** 1.0.0  
**Status:** Ready for training (after commission set)
