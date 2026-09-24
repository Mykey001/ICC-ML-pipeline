# ICC-ML

Machine-learning meta-labeling layer for the **ICC Swing** trading strategy.

The ICC strategy decides *direction*. This project trains a model to decide
*whether to take each signal* — keeping trades that reach the take-profit
target and suppressing those that end at the stop.

---

## Quick start

```bash
pip install -e .
streamlit run app/streamlit_app.py          # GUI
jupyter lab notebooks/                       # step-by-step notebook
python tests/validate_pipeline.py            # pipeline self-test
```

---

## Project layout

```
icc_ml/
├── app/streamlit_app.py            GUI — one tab per pipeline stage
├── notebooks/
│   └── 01_icc_model_training.ipynb step-by-step training walkthrough
├── src/icc_ml/
│   ├── config.py                   symbol specs, strategy & execution params
│   ├── data_fetch.py               MT5 / CSV / synthetic + quality gate
│   ├── indicators.py               Layer 1 — raw indicators, 10 categories
│   ├── features.py                 Layer 2 — ~110 engineered features
│   ├── strategy_icc.py             primary model — ICC state machine
│   ├── icc_labeling.py             meta-labels — real SL/TP simulation
│   ├── train.py                    purged walk-forward CV + calibration
│   ├── backtest.py                 sequential execution + parity checks
│   ├── validation.py               IC, IC stability, redundancy clustering
│   ├── live_inference.py           score the latest closed bar
│   └── synthetic_data.py           random-walk generator (testing only)
├── tests/validate_pipeline.py      two-sided leakage / capability test
├── ea/ICC_Swing_EA_Simplified.mq5  MQL5 EA (TP_Pips = 2500)
├── docs/                           methodology — read these first
├── config/default.yaml             parameter template
├── data/{raw,processed,exports}
├── models/                         trained model bundles
└── reports/
```

---

## Documentation

| Doc | Contents |
|---|---|
| `docs/01_market_information_taxonomy.md` | Indicators vs features; the two extraction templates |
| `docs/02_icc_strategy_specification.md` | Formal ICC spec; the EA↔Python contract |
| `docs/03_labeling_and_meta_labeling.md` | Why meta-labeling; execution realism |
| `docs/04_validation_protocol.md` | Purged walk-forward; self-tests; go/no-go |
| `docs/05_data_requirements.md` | **What you need to provide** |

---

## Pipeline

```
OHLCV → indicators → features → ICC signals → meta-labels
      → purged walk-forward training → backtest → export → live
```

| Stage | Module | Output |
|---|---|---|
| Data | `data_fetch` | Validated OHLCV |
| Layer 1 | `indicators` | ~150 raw indicator columns |
| Layer 2 | `features` | ~110 engineered features |
| Primary model | `strategy_icc` | Trade direction + SL |
| Meta-labels | `icc_labeling` | win/loss per signal |
| Training | `train` | Calibrated model + threshold |
| Evaluation | `backtest` | Sequential P&L vs baseline |
| Live | `live_inference` | TAKE / SKIP decision |

---

## Design decisions that matter

**Meta-labeling, not direction prediction.** Predicting "which way will price
go" is a low signal-to-noise problem. Predicting "will *this* setup work" is
conditioned on a real structural pattern and is far more learnable.

**Labeling mode ≠ backtest mode.** Labels are built with every signal simulated
independently; the one-position constraint is applied only when measuring P&L.
Enforcing it during labeling discards ~90% of training data and makes the target
depend on scheduling luck rather than market state.

**Threshold chosen on expected pips, not accuracy.** With a 2500-pip target
against a structural stop, the payoff is asymmetric and the most accurate cutoff
is rarely the most profitable one.

**Pessimistic fills.** Next-bar-open entry, spread and slippage both sides,
commission, and when a bar contains both SL and TP the **stop is assumed first**.

**Every result is reported against the take-all baseline.** A 55% win rate means
nothing if the unfiltered strategy already won 55%.

---

## Pip convention — check before changing symbols

`PipSize()` = `10 × point` on 3/5-digit quotes, `1 × point` otherwise.

| Symbol | 2500 pips | Verdict |
|---|---|---|
| XAUUSD | $25.00 | Sane |
| US30 | 25 points | Sane |
| EURUSD | 0.2500 | **Unreachable — 0% TP hit rate** |

The pipeline warns automatically when `tp_hit_rate < 2%`.

---

## Pipeline self-test

`tests/validate_pipeline.py` runs two tests that must **both** pass:

| Test | Expectation | Measured |
|---|---|---|
| A — null (random data) | AUC ≈ 0.50 → no leakage | 0.578 PASS |
| B — signal (injected feature) | AUC > 0.70 → can learn | 1.000 PASS |

Either alone proves nothing: a constant predictor passes A, a leaking pipeline
passes B. Together they make a verdict on real data trustworthy in either
direction.

---

## Go / no-go for live

1. `tp_hit_rate` > 5%
2. ≥ 300 labeled trades
3. Positive edge in ≥ 4 of 5 folds
4. Beats take-all baseline on **net pips**
5. All live-parity checks pass
6. Both self-tests pass
7. Demo forward-test ≥ 1 month, consistent with backtest

Failing any of these means do not deploy. **A strategy with no edge is not fixed
by a better model.**
