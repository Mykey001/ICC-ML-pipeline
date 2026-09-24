# 04 — Validation Protocol

The purpose of this protocol is to make a "no edge" verdict *trustworthy* and a
"positive edge" verdict *hard to fake*. Both directions matter.

---

## 1. Purged walk-forward cross-validation

Random k-fold is invalid on time-series trading data. We use expanding-window
walk-forward with purging and embargo.

```
Fold 1:  train [-------]  purge/embargo [xx]  test [-----]
Fold 2:  train [--------------]             [xx]  test [-----]
Fold 3:  train [---------------------]      [xx]  test [-----]
```

### Purging

ICC trades hold for hundreds of bars. Any training trade whose `exit_bar`
reaches into the test window resolves using price action the test set "owns" —
including it leaks the future into the past.

Rule: drop training trades where `exit_bar >= test_start_bar - embargo_bars`.

Because holding periods are long, **this purge is large** — expect to lose a
meaningful share of training rows. That cost is real and unavoidable; skipping
it produces inflated results, not better ones.

### Embargo

A further buffer (default 50 bars) after the boundary, because serial
correlation means bars immediately after the split still carry information
bleeding backward.

---

## 2. Threshold selection on expected pips

The probability cutoff is **not** chosen to maximise accuracy or F1.

Payoffs here are wildly asymmetric — a 2500-pip target against a structural
stop. The threshold that maximises classification accuracy is almost never the
one that maximises money. We sweep thresholds and select by total net pips,
requiring a minimum trade count so a threshold cannot win by selecting one lucky
trade.

**The threshold is chosen on the training fold only.** Selecting it on the test
fold is leakage.

---

## 3. Probability calibration

We threshold on probability, so probabilities must be meaningful. An
uncalibrated boosted model's "0.6" is not a 60% chance. `CalibratedClassifierCV`
with isotonic regression is applied when there are ≥100 training rows.

Calibration quality is reported as **Brier score** alongside AUC.

---

## 4. The honest baseline

Every fold reports what taking **all** signals would have earned.

```
edge_pips = model_net_pips - baseline_net_pips
```

A model is only worth deploying if `edge_pips > 0` in the clear majority of
folds. High AUC with negative edge means the model is right about the wrong
trades.

---

## 5. Two-sided pipeline self-test

`tests/validate_pipeline.py`. Run after any change to feature, labeling or
training code.

### Test A — null test (leakage detector)

Run the full pipeline on synthetic random-walk data. There is no pattern, so a
correct pipeline **must** return AUC ≈ 0.50 and no edge.

> If this test shows a strong edge, the pipeline is **leaking**.

Measured: **AUC 0.578 — PASS**

### Test B — signal test (capability detector)

Inject a feature genuinely correlated with the outcome. The pipeline **must**
find it.

> If this test fails, the pipeline is **broken** — it would report "no edge"
> even on real data with real edge, and you would discard a working strategy.

Measured: **AUC 1.000 — PASS**

### Why both are required

| | Passes A | Passes B |
|---|---|---|
| Pipeline that always outputs 0.5 | Yes | No |
| Leaking pipeline | No | Yes |
| **Correct pipeline** | **Yes** | **Yes** |

Either test alone proves nothing. Together they are strong evidence the
machinery is sound — which is what makes the verdict on *real* data meaningful
in either direction.

---

## 6. Live-parity checks

`backtest.live_parity_checks()` verifies the backtest is structurally capable of
resembling live results:

| Check | Requirement |
|---|---|
| `entry_never_on_signal_bar` | All entries strictly after their signal bar |
| `no_overlapping_positions` | Sequential constraint actually enforced |
| `timeout_rate_acceptable` | < 30% of labels decided by timeout |
| `sample_size_adequate` | ≥ 30 model-approved trades |
| `model_discriminates` | Probability spread > 0.15 (not a constant predictor) |

These do not prove profitability. They catch the specific ways a backtest
silently stops resembling live trading.

---

## 7. Go / no-go criteria for live deployment

Deploy only if **all** hold on real broker data:

1. `tp_hit_rate` > 5% — TP is actually reachable for this symbol
2. ≥ 300 labeled trades — enough for walk-forward to mean anything
3. `folds_with_positive_edge` ≥ 4 of 5 — edge is consistent, not one lucky fold
4. Model beats take-all baseline on **net pips**, not just accuracy
5. All live-parity checks pass
6. Both self-tests (A and B) pass
7. Forward-test on demo for ≥ 1 month with results consistent with backtest

Failing any of these means **do not deploy**. A strategy with no edge is not
fixed by a better model.
