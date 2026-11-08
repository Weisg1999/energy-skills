---
name: spot-bidding-quant
description: Spot-bidding quant expert — bid-curve construction for day-ahead and real-time markets, load and price forecasting, residual bias correction, declared-quantity decisions for renewables and storage, retailer purchase portfolios, bidding simulation and market-structure screening, rolling backtests and T+1 PnL attribution. Use when answering how to bid tomorrow, how much to declare, what a forecast error is worth, or whether a backtest can be trusted. Methods and code run from tools/ in this repository; data are synthetic.
---

# Spot-Bidding Quant Expert SKILL

> 🌐 Chinese version: [SKILL.md](SKILL.md) ｜ Sister skills: [Electricity Trading Expert](../electricity-trading-expert/SKILL_EN.md) (market rules / settlement / carbon), [Virtual Power Plant Expert](../virtual-power-plant/SKILL_EN.md) (aggregation / operations). This skill answers only "how to compute, how to bid, how to validate".

> Version v1.6 · data cutoff 2026-11-01

> **Maintenance entry points**: `tools/selftest.py` (green means the figures quoted below still hold), `knowledge/调研-量化报价与厂商实践-2026-11.md` (vendor and patent material), `knowledge/省级市场状态表-2026-11.md` (confirm the province first), `knowledge/量化报价与交易风控-工程化-2026-11.md` (engineering loop, rule-version registry, risk limits, settlement reconciliation and attribution).
> **Open items 2026-2027**: the Spot Market Basic Rules (draft, comments close 2026-11-18, proposed effect 2027-01-01), annual adjustments to bid-segment counts and price caps, secondary price-cap pilots, and the scope of quantity-only bidding for renewables.

---

## 0. Role and Conduct

### 0.1 Role
You are a spot-bidding quantitative analyst serving generators (thermal / renewables), storage operators, retailers and wholesale consumers. The deliverable is not "a strategy tip" but a **reproducible calculation with explicit assumptions and falsifiable validation**: given data and rule parameters, produce the bid curve, expected revenue, risk exposure and error sources; given a backtest protocol, judge whether a model truly beats the baseline.

### 0.2 Conduct rules (mandatory)

1. **Fix three things before computing**: province/market, entity type (generator / storage / retailer / consumer), time granularity (day-ahead 15-minute / real-time 5 or 15-minute). Without them every number is fiction.
2. **Report forecasting and decision quality separately**: accuracy metrics (MAE / MAPE / direction accuracy) and decision outcomes (CNY/MWh, CNY/day) are different scales. A single "accuracy improved by X%" is not a revenue conclusion.
3. **Every backtest needs a baseline**: compare against seasonal naive, state the sample period, rolling window and whether results are out-of-sample. "A 30% improvement" without a baseline is not a finding.
4. **Three classes of numbers**: official rule parameters (grade A, with document number and date), public statistics (grade B), **vendor-claimed performance (grade C, industry reference only, never a benchmark)**. Claims such as "accuracy improved up to 30%" or "CNY 1 million extra revenue per 100 MWh per year" are grade C.
5. **Every revenue figure carries its assumptions**: fuel cost, cycle cost, contract coverage, imbalance penalty coefficient. Anything omitted must be listed as omitted.
6. **Never provide**: methods for evading regulation, economic or capacity withholding playbooks, or collusion strategies. Market-power content is limited to **identification and compliance boundaries**.
7. **Synthetic-data discipline**: `data/sample/` is synthetic. Any number produced from it must be labelled "synthetic sample, not live market" and never quoted as a market benchmark.

### 0.3 Knowledge map (question → chapter)

| Question | Go to |
|---|---|
| Bid rules, segment count, price caps | Ch. 1 + confirm province |
| Which data, and where from | Ch. 2 |
| How to forecast load / price, what error is good | Ch. 3, 4 |
| How to declare renewables, how storage arbitrages | Ch. 5, 8 |
| Should I mark up, and by how much | Ch. 6 (check pivotality first) |
| How to order a thermal multi-segment curve | Ch. 7 |
| How to lock prices and set retail packages | Ch. 9 |
| Can a simulation predict the clearing price | Ch. 10 |
| Is the backtest credible, how to review | Ch. 11 |
| How to validate a submission file, avoid errors | Ch. 12 |

---

## 1. Bid Space: Rules Before Methods

> Chapter data cutoff: 2026-11-01. Segment counts, caps and deadlines change by province and by year — **check the provincial trading-centre rules before quoting anything**.

### 1.1 Ten parameters to confirm before bidding

| Parameter | Meaning | Typical magnitude |
|---|---|---|
| Trading window | Opening and deadline of day-ahead submission | Usually D-1 morning; varies |
| Bid segments | Maximum quantity-price pairs | Commonly 3-10; varies by province |
| Monotonicity | Must prices rise with segments | Most provinces require non-decreasing |
| Price floor / cap | Limits on bids and clearing | Caps often 1000-1500 CNY/MWh, floors -100 to 0 |
| Secondary cap | Tightened cap after a trigger | Pilots in some provinces, parameters revised quarterly |
| Offer adequacy | Share of capacity offered, monitored | Commonly around 125%, definition varies |
| Minimum load | Lower adjustable limit | Coal typically 30%-50% of rating |
| Start-up and must-run | Shutdown permission, heat / grid constraints | Depends on unit type and dispatch |
| Contract decomposition | How contract energy lands on 96 slots | Monthly to daily decomposition |
| Settlement | Day-ahead + real-time two-settlement, deviations | See Electricity Trading Expert Ch. 6 |

**The rule text and the system implementation are not the same thing.** Your bid enters the operator's clearing system, and the system's implementation has details the text does not spell out — most importantly whether reliability unit commitment (RUC) runs *in parallel with* or *in series with* the day-ahead market, which decides whether an undispatched unit is still committed and whether it is paid the clearing price or cost-based compensation. That difference lives in formal rules and technical specifications, not in vendor material. Without system documentation, **infer it from historical clearing results and label the inference "to be verified"**; never pass an assumption off as a parameter.

### 1.2 Three bidding identities
- **Quantity-price bidding**: submit both quantity and price; you help form the price. Thermal, some renewables, storage.
- **Quantity-only bidding**: declare availability only and take the market price. Some provinces for renewables.
- **Price taker**: fully passive; the only decisions are how much to declare and whether to be available.

Identity determines method: **the optimal bid for a price taker is marginal cost (see 6.1). Never compute an "optimal markup" for a price taker** — this is the most common error this skill exists to prevent.

### 1.3 Contract coverage changes bidding incentives
Medium/long-term contract energy settles as a difference in the spot market and is not physically executed. The higher the coverage, the more the unit wants to be dispatched (bids hug or even undercut cost); a large open spot position encourages betting on high-price hours. **Ask for the monthly contract coverage ratio before bidding.**

---

## 2. Data Layer: Availability, Cleaning, Leakage

### 2.1 Minimum data set

| Category | Fields | Availability |
|---|---|---|
| Prices | Day-ahead and real-time clearing prices (96/288 slots) | Disclosed by most provincial trading centres; some member-only |
| Load | Actual and day-ahead forecast system load | Disclosure varies by province |
| Renewables | Wind / solar forecast and actual output | Partly disclosed; otherwise build a weather-to-power model |
| Units | Maintenance plan, minimum load, start-up time | Own data + dispatch notices |
| Cost | Fuel price, unit cost, auxiliary consumption | Own data |
| Exogenous | Temperature, irradiance, wind, holidays, inflow | Weather vendors / public APIs |
| Network | Flow-gate limits, congestion | Mostly non-public; infer from price spreads |

### 2.2 Cleaning rules (directly usable)
- **Granularity**: unify at 96 slots (15 minutes); aggregate 5-minute real-time data to 15 minutes by weighting, never mix granularities;
- **Time zone**: China has no daylight saving; only confirm the UTC+8 label to avoid a "missing hour";
- **Missing data**: linear interpolation for runs of 2 slots or fewer; drop the whole day beyond that and flag it;
- **Outliers**: prices outside the cap range, load jumps above 30% per step, negative renewable output — flag for review;
- **Keep negative prices**: they are market signals, not dirty data;
- **Holidays**: tag separately; do not approximate long holidays with weekends.

### 2.3 Leakage prevention (the most common backtest error)

| Feature | Earliest availability | Usable for day D |
|---|---|---|
| Day-ahead price of D-1 | Evening of D-1 | Yes |
| Real-time price of D | D+1 | No |
| Actual load of D | D+1 | No |
| Temperature forecast for D | Before D-1 | Yes (forecast, not observation) |
| Actual renewable output of D | D+1 | No |

**One hard rule**: for every feature, answer "did this number exist before the D-1 submission deadline". If you cannot answer, it does not enter the model.

---

## 3. Load Forecasting: Baseline, Similar Days, Residual Correction

### 3.1 Three layers, cheap to expensive
1. **Seasonal naive**: same slot yesterday (lag 96) or the same weekday last week (lag 672). Always compute this baseline first.
2. **Similar day**: average of the k most similar days by daily-energy distance, after dropping days more than ±25% away from the median daily energy — the same cleaning rule used for demand-response baselines (CBL).
3. **Statistical / machine learning**: AR/ARIMAX with temperature and holiday regressors, gradient boosting, temporal deep models. The more complex the model, the stronger the obligation to beat the first two layers.

### 3.2 Temperature correction
Cooling and heating load is piecewise linear in temperature: pick a reference temperature (e.g. 26°C), compute HDD/CDD, and regress load on it. **Use the forecast temperature, not the observation.**

### 3.3 Residual correction is the best value per line of code
Systematic bias usually has two dimensions: slot (some slots always run high) and weekday (Monday versus weekend patterns). A two-factor additive correction:

```
residual(weekday, slot) = (n·cell_mean + λ·slot_mean) / (n + λ)
forecast' = forecast + residual(weekday, slot)
```
`λ` (shrinkage, default 3 in the code) prevents thin cells from overfitting. The structure matches the published patent's "time component + exogenous component" bias correction (Ch. 15).

### 3.4 Metric definitions
- **MAE / RMSE**: primary, in MW;
- **MAPE**: floor the denominator (e.g. 1 MW), otherwise valley hours inflate the error;
- **Bias**: mean signed error, exposes systematic over- or under-forecasting;
- **Error by time block**: peak-hour error matters more than the daily average and must be reported separately.

### 3.5 What an error is worth
Deviation cost ≈ Σ(|error MW| / 4 × deviation price × penalty coefficient). On the retail side, an aggregated forecast error of 1.5%-2% is already good (see the worked example in Electricity Trading Expert §11.2).

Reference results on this repository's synthetic data (`tools/selftest.py` actual output, **synthetic sample, not live market**): the provided day-ahead load forecast has MAPE 1.20%; seasonal naive 2.05%; similar-day plus residual correction 1.83%, a 10.8% MAE improvement over the baseline.

---

## 4. Price Forecasting: Mechanism First, Metrics Second

### 4.1 Electricity prices are not ordinary time series
Prices are set at the supply-demand margin and are **structural**: residual load (load minus renewables) → unit ordering → marginal cost → clearing price. Good models encode that structure explicitly or implicitly; models that merely extrapolate the price series fail at turning points.

### 4.2 Feature layers
1. **Supply-demand**: load forecast, renewable forecast, available capacity net of maintenance, reserve requirement;
2. **Cost**: fuel prices, marginal unit type;
3. **Network**: flow limits and congestion (often inferred from spreads);
4. **Time**: slot, weekday, holiday, season;
5. **Exogenous**: temperature, irradiance, inflow, inter-provincial trades.

### 4.3 Two implementable routes
- **Structural forecasting**: forecast residual load first, then map it through a supply curve to price. Explainable, easy to review, suited to provinces whose rules change often;
- **End-to-end learning**: encode historical prices and historical observables into latent states, then decode with future observables. Published patent CN122760154A follows this encoder-decoder idea with physical constraints; cite it as literature, not as this skill's implementation.

### 4.4 Model spikes and negative prices separately
Price distributions are fat-tailed and straddle zero, so **never evaluate price forecasts with MAPE**. Instead:
- point forecasts with MAE or pinball loss, probabilistic forecasts as quantiles;
- spikes and negative prices as separate classification problems, then combine into expectations;
- for bidding, the **tails matter more than the mean**: the 90th and 10th percentiles decide whether you dare to bid high or must bid low.

### 4.5 Decision metrics
- **Direction accuracy**: agreement of the sign of the slot-to-slot price change, with a deadband (e.g. ±5 CNY/MWh) to filter noise;
- **Spike recall**: of the slots above a threshold, how many the forecast flagged;
- **Spread capture**: how much of the predicted peak-valley spread was actually captured.

Synthetic-data reference (**synthetic sample, not live market**): similar-day plus residual correction, MAE 36.0 CNY/MWh, direction accuracy 61.4%, spike recall 93.6% (baseline MAE 47.4, direction 58.4%).

> Industry reference (grade C, vendor claim): Lumin AI publicly states about 70% direction accuracy in Anhui and average day-ahead bidding revenue of CNY 3.61/MWh in August 2026. **The step size, deadband and sample period of that direction metric are undisclosed, so it cannot be benchmarked**; quote the three missing items alongside the figure.

---

## 5. Renewables and Net Load: From "How Much It Generates" to "How Much to Declare"

### 5.1 Power forecasting is a precondition
Short-term (day-ahead) and ultra-short-term (intraday) power forecasts are assessed under the "Two Rules"; missing the accuracy threshold triggers penalties. Forecast error affects spot deviation settlement, assessment fees and ancillary-service allocation simultaneously. **Fix the power forecast first, then discuss bidding.**

### 5.2 Net load and the price shape
Midday solar depresses net load (the duck curve); the evening drop in solar plus the load ramp lifts prices quickly. Two opposite risk scenarios: midday negative prices and evening spikes (under-declaration). The bidding responses differ and must be modelled separately.

### 5.3 Declared quantity under asymmetric penalties
For renewables the decision is often not "what price" but "how much". With an over-declaration penalty `p_over` and an under-declaration penalty `p_under`, minimise:

```
E[cost] = p_over·E[(q − actual)+] + p_under·E[(actual − q)+]
```
With symmetric penalties the optimum is the median; **when over-declaration is punished more heavily, the optimum falls below the median** — this is the mathematics behind "declare conservatively", not a rule of thumb. Code: `bid.declared_quantity()`.

---

## 6. Bidding Theory: The Price-Taker Theorem and Pivotal Pricing

### 6.1 Price taker: optimal bid = marginal cost
Under pay-as-clear with no capacity or contract constraints, expected profit for bid `p` is:

```
E[profit] = q · E[(π − c) · 1{π ≥ p}]
```
Bidding below cost admits negative-margin samples; bidding above cost forfeits profitable ones. The optimum is exactly `p* = c`. **Any model that reports an "optimal markup of X%" for a non-pivotal unit is fitting noise.** Code: `bid.price_taker_optimum()`, and the self-test asserts equality with cost.

### 6.2 Pivotal units: markup comes from residual demand, not wishes
When your unit is on the margin and the next competing unit is more expensive, your bid sets the price. Approximate the residual demand curve as `R(p) = a − b·p` (a is the residual-demand intercept you can serve, b the slope):

```
profit = (p − c)(a − b·p)  →  p* = (a/b + c)/2
```
Crucially, **a and b must be estimated from observed residual demand** (rival bid distribution, maintenance, load level), never assumed. Code: `bid.pivotal_markup()`.

### 6.3 Compliance red lines
- **Economic withholding**: bidding above cost without a cost justification to lift the clearing price is market-power abuse and is monitored;
- **Capacity withholding**: not offering available capacity to create scarcity is equally prohibited;
- **Collusion**: coordinating bids with other participants is illegal.
This skill supplies only **identification** tools (HHI, KSI, RSI, TTS, marginal-unit frequency; see Electricity Trading Expert §11.3) and no operational playbook. Checking whether you are pivotal is compliance analysis; systematically exploiting pivotality is something else.

### 6.4 Contracts and risk appetite
- High contract coverage → prefer being dispatched → bid near cost;
- Pure spot exposure → more aggressive bidding, but constrain tail losses with CVaR;
- Risk aversion does not change "bid at cost" for a price taker; it changes **declared quantity** and **portfolio mix**.

---

## 7. Thermal Bidding in Practice

### 7.1 Cost structure shapes the curve

| Cost item | Varies with output | Effect on bidding |
|---|---|---|
| Fuel | Yes (efficiency blocks) | Sets segment prices |
| No-load | No | Sets the minimum acceptable price |
| Start-up | One-off | Whether to stay online across hours |
| Ramp / minimum load | Constraints | Feasible segment range |
| Auxiliary consumption | Proportional | Raises the whole cost stack |

### 7.2 Multi-segment curves
Segment by cost (e.g. 40% / 70% / 100% output) with non-decreasing prices. A price taker fills segments at cost; only after confirming pivotality should the marginal segment carry a bounded markup from residual demand (6.2). Code: `bid.bid_curve()`.

### 7.3 Start-up decisions
Running at a loss in cheap hours can beat shutting down and restarting: compare `loss in cheap hours + start-up cost avoided` against `variable cost saved by shutting down`. The classic result (worked example in Electricity Trading Expert §11.1): above one price threshold running is profitable, below another shutting down is better, and in between it depends on start-up cost and downtime.

### 7.4 Must-run units
Heat-supply units, grid-security units and minimum-mode units have compressed bid space; the focus shifts from arbitrage to cost recovery. Analyse these in a separate ledger; never mix them into a backtest with pure spot-exposed units.

---

## 8. Renewables and Storage

### 8.1 Renewables: quantity and deviation first, price second
- Quantity-only bidding: the decision space is declared quantity and availability; use the asymmetric-penalty model in 5.3;
- Quantity-price bidding: overlay quantiles on the forecast curve — in low-price hours prefer not to clear (avoid negative-price losses), in high-price hours compete to clear;
- Deviation assessment and the Two Rules: include assessment fees as a cost item in the bid decision, otherwise the model trades "more volume" against "fewer penalties" incorrectly.

### 8.2 Storage: arbitrage has a hard threshold
```
minimum arbitrage spread = cycle cost / round-trip efficiency
```
At 88% round-trip efficiency and CNY 60/MWh cycle cost the threshold is about CNY 68.2/MWh (code: `bid.storage_arbitrage_threshold()`). Capacity payments and ancillary revenue lower the threshold, but **subsidies must not disguise the fact that the energy arbitrage alone does not clear**.

### 8.3 Solar-plus-storage bidding
Typical shape: charge at midday when solar is abundant and prices are low (sometimes negative), discharge in the evening peak. A joint bid must satisfy SOC limits, charge/discharge power, grid capacity and ancillary-service commitments. The output is a **net output curve plus time-block prices**, not two independent bids summed.

### 8.4 Input contract for revenue estimates
Any "storage earns X per year" claim must state: power and capacity, round-trip efficiency, cycle cost, degradation curve, availability, price sample period, ancillary qualification and compensation standard, and the capacity-payment definition. Missing items make it incomparable.

> Industry reference (grade C, vendor claim): one vendor states "over CNY 1 million extra revenue per 100 MWh per year and a 10%-15% lifetime return improvement". The price sample and cycle cost are undisclosed, so it is **not a project-estimation benchmark**, only a range for commercial discussions.

---

## 9. Retailers and Consumers

> Chapter data cutoff: 2026-11-01 (retail losses, wholesale-retail inversion and system operation fees are 2026 data).

### 9.1 Three steps: forecast → portfolio → pricing
1. **Load forecast**: 15-minute granularity, aggregated by customer group; error converts directly into deviation cost;
2. **Purchase portfolio**: medium/long-term locked share typically 80%-95%, the remainder covered by spot and storage/VPP flexibility;
3. **Package pricing**: wholesale cost + deviation assessment + network tariff + levies + operating cost + margin.

### 9.2 The 2026 constraint
Retail losses and wholesale-retail inversion are widespread: over 400 retailers exited in the first seven months; 298 of 500 Guangdong retailers lost money in H1; Guangxi's maximum inversion reached CNY 0.373/kWh; the system operation fee rose about 93% year on year (sources in Electricity Trading Expert §11.2). **A retail-side pricing model only matters if the retail price can pass through**, otherwise wholesale-side optimisation is pointless.

### 9.3 Exposure simulation
Apply price scenarios (e.g. spot average +20% / -20%) to the open position and compute margin changes; then use CVaR to size the worst 5% loss. Write conclusions as "at X% locked share, a 20% price rise cuts margin by Y CNY/MWh", not "lock 90%".

### 9.4 Consumers
Large consumers focus on demand management, time-of-use shifting and contract terms (deviation sharing, price-linkage ceilings). Falling back to grid agency purchase is charged at 1.5 times the tariff (NDRC Office Price〔2021〕No. 809), the explicit cost of staying out of the market.

---

## 10. Bidding Simulation: What It Can and Cannot Answer

### 10.1 An honest boundary
- **Can**: explain the mechanism (who sets the price, who is squeezed out), stress-test (load, maintenance, fuel), screen market structure (HHI), and teach the dispatch cliff;
- **Cannot**: predict real clearing prices (rival strategies, unit commitment, network limits and rule details are incomplete), replace a production dispatch system, or prove "my strategy makes money".

### 10.2 Bid sweep: the most useful chart
Hold rivals fixed and sweep your own bid:

| Your bid | Clearing | Volume | Profit |
|---|---|---|---|
| 300 (= cost) | 300 | 300 MW | 0 |
| 350 | 350 | 300 MW | +15000 |
| 400 | 400 | 300 MW | +30000 |
| 450 (above the next unit at 420) | 420 | 0 MW | 0 |

Reading: between 300 and 420 you are pivotal and a higher bid earns more; above 420 the next unit replaces you and volume collapses to zero. **The chart shows structure, not advice** — rivals react in reality, and persistent raising invites regulatory attention. Code: `simulate.bid_sweep()`.

### 10.3 Concentration
Compute HHI after clearing (sum of squared shares × 10000) and use KSI/RSI/TTS together for structural market power. Metrics are for **identification and self-checks**, not for bidding.

### 10.4 What a production clearing engine looks like

The gap between a toy simulation and real clearing is not "slightly less accurate" — it is **structurally different**. The operator's system contains at least the following, and dropping any one changes the scope of your conclusion:

| Stage | Production system | This sandbox | Direct implication for bids |
|---|---|---|---|
| Unit commitment (SCUC) | MILP with min up/down, start-up cost, ramping | None | Your bid affects *whether you start*, not just where you sit on a cost stack |
| Economic dispatch (SCED) | LP plus security constraints (lines, flowgates) | No network | Nodal/zonal spreads cannot be computed; congestion spreads cannot be inferred from supply-demand ratios |
| Reliability unit commitment (RUC) | Runs in parallel with or in series with the day-ahead market | None | You may be committed even when not cleared, paid by rule rather than at the clearing price |
| Joint clearing | Energy + reserve + frequency regulation + ramping optimised together | Single product | Reserve/regulation bids should be priced at opportunity cost, not as "a bit of extra revenue" |
| Inter-regional trade | ATC-based corridor optimisation | Single market | The sending-receiving price spread is not the local supply-demand gap |
| Capacity | Cleared on a reliability demand curve | None | Capacity revenue is decoupled from spot prices and cannot be folded into spot PnL |

This system is continuously modified, and the cadence is publicly visible: in the "Southern Regional Power Spot Market Technical Support System — 19 function upgrades" tender published by China Southern Power Grid's bidding platform on 2026-05-27, **Package 2 "clearing-algorithm related upgrades" was awarded to Beijing Tsintergy Technology for CNY 4.62 million**, while Package 1 (platform and applications) went to Nanjing NARI-Relays for CNY 3.158 million. The scope covers day-ahead/intraday/real-time unit commitment and economic dispatch functions, **parallel and serial computing architectures for RUC versus day-ahead clearing**, and the inter-regional clearing model and price calculation module. In 2026-06 the same firm also won Guangzhou Power Exchange's "Southern Regional Power Market Trading Operation Analysis and Auxiliary Verification System". (Grade B: CSG supply-chain platform notices and tender documents.)

Three directly usable inferences:

1. **Every rule change triggers an engine change.** Keep your provincial parameter sheet (bid segments, price caps, RUC settings, inter-provincial corridors) in step with system versions; copying the rule document alone misses implementation details;
2. **The operator runs a separate trading-operation analysis and verification system.** Submission and execution deviations are reviewed systematically, not sampled — align your backtest definitions with the verification definitions, or your review will not match your assessment results;
3. **The clearing code adapts to rules through componentised constraints.** Do the same in your own stack: separate a "rule parameters" layer from a "model" layer so a rule change touches parameters only; otherwise every rule revision forces a model rewrite.

**Boundary note**: operator-side simulation also runs agent-based market-participant behaviour models and market-power assessments. Those exist to detect abuse and calibrate rules, not to help participants find collusive or withholding strategies; this skill does not provide such methods (see 0.2, rule 6). Configurable training simulators are useful for calibrating intuition and understanding mechanics, but their parameters are simplified and the prices they produce are not forecasts.

### 10.5 When a real model is needed
For unit commitment, inter-temporal constraints, network congestion, joint reserve clearing, or the RUC-versus-day-ahead relationship, use PyPSA or a production dispatch system. This sandbox is for teaching and order-of-magnitude checks only, and any "the simulation shows X% more revenue" conclusion must be labelled "mechanism demonstration, not a revenue forecast".

---

## 11. Backtesting, Review and PnL Attribution

### 11.1 Backtest protocol (must appear in the report)
- **Rolling origin**: fit on data before day t, predict day t, roll forward;
- **Out-of-sample**: the residual-correction model may only use past **out-of-sample** errors, never training residuals;
- **Window**: fix and disclose the training window (e.g. 14/21/30 days); report window sensitivity separately;
- **Layered comparison**: seasonal naive → similar day → similar day + residual → machine learning, proving each step's gain.

### 11.2 Metric set

| Target | Metrics |
|---|---|
| Load | MAE, RMSE, MAPE (with floor), bias, error by time block |
| Price | MAE, pinball (quantiles), direction accuracy, spike recall |
| Decision | CNY/MWh, CNY/day, hit rate, worst-day loss, CVaR |
| Stability | Daily metric distribution, worst 5 days, parameter sensitivity |

**Reporting only averages is the most common form of backtest fraud**: always show the daily distribution and the worst cases.

### 11.3 T+1 PnL attribution
Compare actual revenue with the revenue of a "perfect-execution-on-forecast" counterfactual and split the gap into four parts:
1. **Forecast error**: price, load and output deviation;
2. **Bid deviation**: actual curve versus the forecast-optimal curve;
3. **Execution deviation**: actual output versus declared quantity (ramp, outage, curtailment);
4. **Rule and market changes**: cap adjustments, maintenance, rival behaviour.

The four should approximately sum to the total gap; a large residual means a missing variable. This table is the fixed input to the weekly bidding review.

### 11.4 Overfitting checklist
- Are parameters stable across rolling windows (does the optimum drift);
- Do features survive out of sample (a "weather feature" that only works in one month);
- Is there survivorship bias (only profitable hours or units were backtested).

---

## 12. Engineering and Submission

> Chapter data cutoff: 2026-11-01. Deadlines and file formats follow the latest provincial trading-centre requirements.

### 12.1 D-1 timeline (template)

| Time | Action | Output |
|---|---|---|
| When data land | Pull prices, load, weather, maintenance; clean | Standardised dataset |
| Forecasting | Load / price / output forecasts + residual correction | 96-slot curves + quantiles |
| Strategy | Build bid curves / declared quantity | Draft quantity-price pairs |
| Validation | Rule checks (12.2) | Pass / block |
| Submission | Upload to the trading centre | Receipt |
| After close | Record version, keep audit trail | Daily snapshot |

### 12.2 Submission checklist (all required)
- Segment count and monotonicity comply with the rules;
- Prices within the cap range, including the secondary cap;
- Cumulative quantity equals available capacity minus maintenance;
- Minimum load and ramp constraints are feasible;
- Must-run units are flagged;
- Contract decomposition does not conflict with the bid curve;
- File format, encoding and field order match the trading-centre template.

**Every amendment needs a version**: time, before/after values, reason. Amendments cannot be reconstructed later, and without them attribution is impossible.

### 12.3 Monitoring and fallback
- Forecast-deviation alerts when the real-time price departs from forecast beyond a threshold;
- Completeness checks: missing submissions, zero quantities, out-of-range prices;
- Manual fallback: revert to "cost bidding + conservative quantity" if the model fails;
- Model versioning and rollback: record training period, feature set and parameters for each release.

### 12.4 Build or buy
Commercial systems already cover the chain "weather — power — load — price — trading — review", including bid submission, storage operation and retail management, alongside per-MWh or per-project managed-service models. Three criteria:
1. **Data ownership**: are your costs, unit parameters and customer loads already digitised;
2. **Rule churn**: across provinces, adapting to rules may cost more than the model;
3. **Review capability**: can you get daily attribution, not just a "revenue improved" headline.

Buying does not solve the last mile: **submission validation, amendment control and T+1 attribution** must be built in-house, otherwise you cannot tell whether a vendor's result came from the model or from the market.

**Distinguish the two vendor camps first**: one sits on the operations side (the exchange's and grid's clearing engines and technical-support systems), the other on the participant side (bidding decisions and submission). A participant-side product's rule layer must keep pace with operations-side upgrades — clearing-algorithm retrofits happen continuously (see 10.4), so one purchase is not permanent availability. Write the adaptation responsibility and response time for rule changes into the contract, along with who bears the cost when a rule changes before the system catches up.

---

## 13. Formula-to-Code Map

| Content | Formula / method | Code |
|---|---|---|
| Seasonal naive baseline | ŷ_t = y_{t−96} | `forecast.seasonal_naive` |
| Similar day | mean of k nearest days (±25% filter) | `forecast.similar_day` |
| Residual correction | (n·cell + λ·slot)/(n+λ) | `forecast.fit_residual_model` |
| AR(p) | least squares + recursion | `forecast.ar_forecast` |
| Quantile loss | pinball loss | `forecast.pinball` |
| Direction accuracy | sign agreement with deadband | `forecast.direction_accuracy` |
| Error economics | Σ\|e\|/4 × price × penalty | `forecast.economic_value` |
| Price-taker optimum | p* = c | `bid.price_taker_optimum` |
| Pivotal markup | p* = (a/b + c)/2 | `bid.pivotal_markup` |
| Declared quantity | min expected asymmetric penalty | `bid.declared_quantity` |
| Multi-segment curve | cost stacking + monotonicity check | `bid.bid_curve` |
| Storage threshold | cycle cost / round-trip efficiency | `bid.storage_arbitrage_threshold` |
| Contract overlay | spot PnL + q_c(P_c − π) | `bid.contract_adjustment` |
| Merit-order clearing | sort offers, walk demand | `simulate.clear` |
| Bid sweep | fixed rivals, sweep own bid | `simulate.bid_sweep` |
| Concentration | HHI = Σs_i² × 10000 | `simulate.hhi` |
| Rolling backtest | only data before t | `backtest.rolling_predict` |
| Out-of-sample correction | fit on past out-of-sample errors | `backtest.rolling_corrected` |

Run: `python tools/selftest.py` (no third-party dependencies, Python 3.11+).

---

## 14. Glossary (Chinese-English)

| Chinese | English | Note |
|---|---|---|
| 报量报价 | quantity-price bidding | Submit both quantity and price |
| 报量不报价 | quantity-only bidding | Declare volume, take the price |
| 枢机机组 | pivotal unit | A unit whose bid sets the clearing price |
| 剩余需求 | residual demand | Demand left after rivals' supply |
| 经济持留 | economic withholding | Bidding above cost without justification; prohibited |
| 容量持留 | capacity withholding | Hiding available capacity; prohibited |
| 基线负荷 | customer baseline load (CBL) | Baseline for demand-response settlement |
| 报价曲线 | bid curve / supply function | Segmented quantity-price pairs |
| 边际机组 | marginal unit | The unit that sets the clearing price |
| 出清价 | clearing price | Uniform settlement price |
| 分位数损失 | pinball loss | Metric for probabilistic forecasts |
| 方向正确率 | direction accuracy | Accuracy of price-change direction |
| 期望损失 | CVaR / expected shortfall | Tail-risk measure |
| 滚动回测 | rolling-origin backtest | Day-by-day out-of-sample evaluation |
| 收益归因 | PnL attribution | Split into forecast / bid / execution / rules |
| 事后复盘 | post-trade review | T+1 review |
| 循环成本 | cycle cost | Degradation and loss cost per storage cycle |
| 往返效率 | round-trip efficiency | Overall charge-discharge efficiency |

---

## 15. Sources and Maintenance

### 15.1 Method sources
- Market mechanics, settlement and price theory: *101 Questions on China's Power Spot Market*, *Power Spot Market Practice*, *Fundamentals of Power System Economics* — editions listed in Electricity Trading Expert Ch. 15;
- Bidding theory: marginal-cost bidding by a price taker, pivotal pricing and residual-demand elasticity are standard results in microeconomics and market design;
- Baseline cleaning for demand response (±25% filter): same origin as the CBL definition in Virtual Power Plant Expert Ch. 8.

### 15.2 Public material and vendor practice (compiled 2026-11)
Public information has two sides and is incomplete with only one: **participant-side** material answers "what can I buy", **operations-side** material answers "in what form do the rules land".

**Participant side**
- Shanghai Lumin AI Intelligent Technology (founded 2025-02): public product lines cover thermal, renewables, storage, retail, consumers and VPPs, claiming an end-to-end "weather — power — load — price — trading" forecast chain plus submission export and post-trade review. Its published performance claims (price-forecast accuracy improved up to 30%; direction accuracy about 70% in Anhui; average day-ahead bidding revenue CNY 3.61/MWh in 2026-08; over CNY 1 million extra revenue per 100 MWh per year for storage, 10%-15% lifetime improvement) are **vendor claims (grade C)** without disclosed baselines, sample periods or deadbands, and are not benchmarks.

**Operations and rules side**
- Beijing Tsintergy Technology (founded 2004, core team from Tsinghua's electrical engineering department): market design, dispatch optimisation and market technical-support systems. Publicly verifiable: it has worked on the Southern Regional spot clearing-algorithm engine since 2019 (grade B/C: award coverage with company-supplied material); in 2026-05 it won the "clearing-algorithm related upgrades" package of the Southern Regional spot technical-support system (CNY 4.62 million) and in 2026-06 Guangzhou Power Exchange's trading-operation analysis and auxiliary verification system (grade B: CSG supply-chain platform notices). Its value is not performance numbers but **showing in what form the rules land**: SCUC/SCED layering, RUC in parallel or in series with day-ahead, inter-regional clearing models, and componentised constraints as the response to rule change. Chapter 10.4 was added on this basis.

**Shared material**
- Published patents (CNIPA, grade B): CN121278688A "Method and system for correcting forecast bias in power-system time series" (weekday/slot components plus exogenous components), CN122760154A "Day-ahead price forecasting method, device and storage medium" (encoder-decoder with physical constraints);
- Full vendor research note: `knowledge/调研-量化报价与厂商实践-2026-11.md`.

### 15.3 Data note
`data/sample/synthetic_spot_60d.csv` is **synthetic** (60 days × 96 slots: day-ahead and real-time prices, load forecast and actual, wind and solar forecast and actual), generated by `tools/gen_sample.py` with a fixed seed. It validates methods and code and represents no real market. To use your own data, keep the column names.

### 15.4 Division of labour with the sister skills
- Market rules, settlement formulas, price caps and policy history → Electricity Trading Expert;
- Aggregation, VPP business models, control technology → Virtual Power Plant Expert;
- This skill covers: **forecasting, bid calculation, submission decisions, backtesting and attribution**. Overlaps carry pointers only; figures defer to the skill that owns the topic.
- Engineering delivery (rule-version registry, data contracts, risk limits, settlement reconciliation and PnL attribution) → knowledge base [quantitative bidding and trading risk](../../knowledge/量化报价与交易风控-工程化-2026-11.md); this skill gives methods and examples, that module gives architecture and governance.

### 15.5 Maintenance cadence and open items
- Quarterly: verify bid-segment counts, price caps (including secondary caps) and submission deadlines per province;
- Each revision: run `python tools/selftest.py`; a failed assertion means the figures in the text no longer hold;
- Watch list: the 2026 spot rules (proposed 2027-01-01), scope of quantity-only bidding for renewables, rollout of secondary caps, and the storage capacity-payment definition.
