# 01 — Market Information Taxonomy

## Purpose

Indicators are not features. An indicator is a *measurement*; a feature is the
*information that measurement carries*, expressed in a form a model can learn
from across different instruments, volatility regimes and time periods.

Feeding raw indicator values into a model is the single most common mistake in
retail trading ML. Raw values are:

- **scale-dependent** — an ATR of 0.0012 means nothing without knowing the instrument
- **highly correlated** — EMA20, EMA50, HMA20 and DEMA20 all say almost the same thing
- **non-stationary** — an RSI of 65 in 2019 does not imply the same thing as in 2024

The taxonomy below solves this by asking, for each category, *what question is
this family of indicators actually answering?* — then extracting that answer.

---

## The 10 categories

| # | Category | The question it answers |
|---|---|---|
| 1 | Trend | Which way is price biased, how strongly, and is that changing? |
| 2 | Momentum | How fast is price moving, and is it accelerating or exhausting? |
| 3 | Volatility | How large are moves right now relative to normal? |
| 4 | Market Structure | What is the swing-high/low sequence saying about control? |
| 5 | Volume | Is participation confirming or diverging from price? |
| 6 | Mean Reversion | How stretched is price, and is it snapping back? |
| 7 | Market Regime | Which of the above should we even be listening to? |
| 8 | Price Action | What does the candle geometry itself say? |
| 9 | Liquidity / SMC | Where is resting liquidity, and was it just taken? |
| 10 | Time / Session | When is this happening? |

---

## Two extraction templates

Every category maps onto one of two templates. This is what makes the feature
set systematic rather than a pile of ad-hoc columns.

### Template A — Direction / Strength / Acceleration
Applies to categories **1, 2, 3, 5, 6** (continuous, signed measurements).

| Level | Question | Example |
|---|---|---|
| Direction | Which way? | `ema20_direction`, `rsi_direction` |
| Strength | How much? | `adx_strength`, `rsi_distance_50` |
| Acceleration | Getting stronger or weaker? | `adx_change`, `macd_acceleration` |

The third level is the one most retail systems omit, and often the most useful.
"Is the market trending?" is a far weaker question than "is the trend
strengthening or decaying?"

### Template B — State / Magnitude / Recency
Applies to categories **4, 7, 8, 9, 10** (discrete events and regimes).

| Level | Question | Example |
|---|---|---|
| State | What is true now? | `structure_bias`, `inside_active_fvg` |
| Magnitude | How significant? | `sweep_magnitude_atr`, `swing_leg_size_atr` |
| Recency | How long since? | `bars_since_last_bos`, `bars_since_last_sweep` |

Recency matters because event flags alone are almost always zero. A raw
`bos_bullish` column is 0 on ~98% of bars and carries little information;
`bars_since_last_bos` is informative on every bar.

---

## Normalisation rules

A feature must mean the same thing on XAUUSD at $2,400 as on EURUSD at 1.08,
and in a calm week as in a volatile one. Three rules enforce that:

1. **Express distances in ATR units**, never raw price
   (`body_size_relative_to_atr`, not `body_size`)
2. **Express levels as percentile ranks** over a rolling window
   (`atr_percentile`, not `atr`)
3. **Express deviations as z-scores or ratios**
   (`price_zscore`, `volume_relative_to_average`)

Bounded oscillators (RSI, Stochastic, %B) are already normalised and pass
through unchanged.

---

## Cyclical encoding for time

Raw `hour = 23` and `hour = 0` are adjacent in reality but maximally distant
numerically. Any time-of-day or day-of-week feature is therefore encoded as a
sin/cos pair:

```
hour_sin = sin(2π · hour / 24)
hour_cos = cos(2π · hour / 24)
```

The raw `hour` column is retained only for grouping and diagnostics, not as a
model input.

---

## Redundancy is expected, and handled later

This taxonomy deliberately produces overlapping features. ADX (category 1),
Choppiness Index (3) and the Hurst exponent (6) are three different ways of
asking "how trendy is this market."

That overlap is **not** removed at design time — doing so would bake in an
untested assumption about which proxy is best. It is removed empirically in
`validation.py` via correlation clustering, keeping the cluster member with the
highest information coefficient against the actual label.

---

## Implementation map

| Category | Layer 1 (raw) | Layer 2 (extracted) |
|---|---|---|
| 1 Trend | `indicators.add_trend_indicators` | `features.trend_features` |
| 2 Momentum | `add_momentum_indicators` | `momentum_features` |
| 3 Volatility | `add_volatility_indicators` | `volatility_features` |
| 4 Structure | `add_market_structure_raw` | `market_structure_features` |
| 5 Volume | `add_volume_indicators` | `volume_features` |
| 6 Mean Reversion | (derived) | `mean_reversion_features` |
| 7 Regime | (derived) | `regime_features` |
| 8 Price Action | `add_price_action_raw` | `price_action_features` |
| 9 Liquidity/SMC | `add_liquidity_smc_raw` | `liquidity_smc_features` |
| 10 Time/Session | `add_time_session_raw` | `time_session_features` |

Current output: **~110 engineered features**.
