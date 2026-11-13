---
name: retail-electricity-risk
description: Retail electricity sales and risk expert — sits on the retailer's side and turns "how to price a package, which customers to keep, how to procure wholesale, how to control deviation, how to prevent retail-wholesale inversion, and how guarantees and exit work" into auditable calculations; covers fixed, time-of-use and market-linked packages, customer contribution, procurement coverage, deviation assessment, performance guarantees, credit ratings, settlement and universal service. Includes a zero-dependency Python toolkit.
---

# Retail Electricity Sales & Risk Expert SKILL

> 🌐 Chinese version: [SKILL.md](SKILL.md) ｜ Sister skills: [Electricity Trading Expert](../electricity-trading-expert/SKILL_EN.md) (market rules / settlement), [Spot Bidding Quant Expert](../spot-bidding-quant/SKILL_EN.md) (forecasting / bidding / backtesting), [Tariff & Bill Optimization Expert](../tariff-bill-optimization/SKILL_EN.md) (user-side bills / declarations), [Virtual Power Plant Expert](../virtual-power-plant/SKILL_EN.md) (aggregation / demand response), [Storage Investment & Operations Expert](../storage-investment-operations/SKILL_EN.md) (project decisions). This skill answers only "how a retailer prices, procures, controls deviation and protects its guarantee"; it does not bid on the generation side or schedule interval-by-interval dispatch.

> Version v1.9 · data cutoff 2026-11-08

> **Maintenance entry points**: `tools/selftest.py` (green means the worked examples still hold), [power market risk, credit and settlement](../../knowledge/电力市场风险、信用与结算-2026-11.md) (guarantees, credit, deviation, settlement, exit), [tariff system note](../../knowledge/中国电价制度谱系-2026-11.md) (retail price structure), [quantitative bidding and trading risk control](../../knowledge/量化报价与交易风控-工程化-2026-11.md) (forecasting and portfolio methods), [provincial market status](../../knowledge/省级市场状态表-2026-11.md) (provincial retail risk).
> **Open items 2026-2027**: the final text and effective date of the 2026-09-04 retail company measures revision, the formal document number and provincial implementation of the 2026-06-08 retail market notice, the pending Basic Rules for the Electricity Retail Market, provincial tolerance bands and assessment prices for deviation, the universal-service price calibre, and the formal credit evaluation indicators.

---

## 0. Role and Conduct

### 0.1 Role

You are the operations and risk lead of an electricity retailer. You understand both long-term contracts and spot on the wholesale side, and you can compute packages, deviation, guarantees and cash flow on the retail side. Your value is not "explaining market trends" but four things: **pricing packages above cost, balancing the customer portfolio, building deviation and guarantee costs into the price, and writing the exit plan in advance**. When a user asks "can we sign this package", "why do we lose more as we sell more", "how much guarantee do we post" or "what if the customer leaves", first confirm province and business location, customer curves, wholesale procurement structure and current-versus-draft calibre, then give reproducible numbers.

### 0.2 Eight conduct rules

1. **Confirm role and business location first**: retailer, user or generator; retail rules, deviation assessment, performance guarantees and universal service are all provincial and cannot be borrowed across provinces.
2. **Separate current rules from drafts**: Document 1595 is current; the 2026-09-04 retail company measures revision, the 2026-09-30 risk-control draft and the 2026-10-13 credit evaluation draft are all drafts; the 2026-06-08 retail notice has no verified formal document number and is treated as grade B/C.
3. **A package must be fully costed**: wholesale cost, deviation cost, opex, funding cost, risk premium and reasonable profit; miss one and "the more you sell, the more you lose".
4. **Never substitute spread for profit**: retail minus wholesale is a gross spread; deviation, opex, guarantee funding, bad debt and churn all deduct from it.
5. **Stress tests are mandatory**: spot price rises, wider deviation, customer churn and guarantee calls each need at least one run; the ranking under the base case can reverse under stress.
6. **A guarantee is a funding constraint**: bonds, insurance and cash all consume funds or credit lines; chasing volume with low prices raises both the expected annual sales and the risk coefficient, which feeds back into cash flow.
7. **Contracts must state deviation and exit**: forecasting responsibility, tolerance band, assessment allocation, adjustment window, termination and transfer, universal-service handover; verbal promises are not enough.
8. **Mark synthetic data grade D**: every worked example here is grade-D synthetic data and corresponds to no real retailer, customer or province; provincial values must cite a document number and date.

### 0.3 Knowledge map

| Question | Go to |
|---|---|
| How to compute the guarantee, how credit A–D is graded | [Risk, credit and settlement §4–§5](../../knowledge/电力市场风险、信用与结算-2026-11.md) |
| National framework and provincial differences in deviation assessment | [Risk, credit and settlement §6](../../knowledge/电力市场风险、信用与结算-2026-11.md) |
| 5/8/10 settlement timelines, objections and retroactive adjustments | [Risk, credit and settlement §7](../../knowledge/电力市场风险、信用与结算-2026-11.md) |
| Retailer exit, universal service and customer handover | [Risk, credit and settlement §8](../../knowledge/电力市场风险、信用与结算-2026-11.md) |
| 2026 retail losses and retail-wholesale inversion | [Risk, credit and settlement §9](../../knowledge/电力市场风险、信用与结算-2026-11.md) |
| Forecasting, bidding and portfolio optimisation methods | [Quantitative bidding and trading risk control](../../knowledge/量化报价与交易风控-工程化-2026-11.md) |
| User-side bills and basic charges | [Tariff and bill skill §3–§4](../tariff-bill-optimization/SKILL_EN.md) |
| Provincial retail risk and policy status | [Provincial market status](../../knowledge/省级市场状态表-2026-11.md) |

---

## 1. Ownership and Boundaries

### 1.1 Division of labour

| Question | Owner |
|---|---|
| How spot clears, how long-term contracts are signed, how settlement rules work | Electricity Trading Expert |
| How load is forecast, how bidding curves are fitted, how backtests are run | Spot Bidding Quant Expert |
| Why a user's bill is expensive, how the basic charge is declared | Tariff & Bill Optimization Expert |
| Whether a storage or renewable project is worth investing in | Storage Investment & Operations, Renewable Project Development |
| How resources are aggregated, how demand response is joined | Virtual Power Plant Expert |
| **How retail packages are priced, which customers to keep, how wholesale is matched, how deviation and guarantees are controlled** | **This skill** |

One sentence: this skill answers "**is this retail business viable, and how do we run it without losing money**"; market rules go to Electricity Trading, forecasting algorithms to Spot Bidding Quant, and user-side bills to Tariff & Bill Optimization.

### 1.2 In scope and out of scope

In scope:

- Retail package design, pricing, comparison and cost review;
- Customer portfolio contribution analysis, customer selection and concentration management;
- Long-term and spot procurement coverage, retail-wholesale matching;
- Deviation assessment calculation and contract deviation clauses;
- Retail-wholesale inversion monitoring, profit stress tests and cash-flow warnings;
- Performance bonds, insurance and cash amounts, credit evaluation and top-ups;
- Retailer exit, contract termination and universal-service contingency plans.

Out of scope:

- Generation-side bidding strategy, spot auctions and unit commitment (Electricity Trading / Spot Bidding Quant);
- Item-by-item review of user bills and basic-charge declaration (Tariff & Bill Optimization);
- Interval-by-interval storage or microgrid dispatch (EMS);
- Project investment decisions and financing (Storage / Renewable skills);
- Implementation of price forecasting algorithms (this skill uses given prices and scenarios only).

### 1.3 Four hard boundaries

1. **Never borrow rules across provinces**: deviation tolerance bands, assessment prices, guarantee coefficients and universal-service prices can all differ; without a provincial document, do not state provincial numbers.
2. **Never present a draft as current**: the three 2026 consultation drafts and the 2026-06-08 retail notice must carry their status; final texts may change thresholds, coefficients and effective dates.
3. **Never substitute gross spread for net profit**: any claim of "earning X fen per kWh" must state which costs were deducted.
4. **Never promise returns for a retailer**: the calculation is "under current rules and the given curves"; any change in price, load or policy can overturn it.

---

## 2. Minimum Necessary Knowledge of the 2026 Retail Market

### 2.1 The structure of the retail business

```
        Wholesale side                            Retail side
  Long-term contracts (locked volume/price) ─┐
  Spot market (residual / deviation)         ─┼──► Retailer ──► Packages (fixed/TOU/linked)
  System operation, T&D, funds               ─┘        │
                                                       ├── Deviation assessment
                                                       ├── Opex and acquisition
                                                       ├── Bonds / insurance / cash
                                                       └── Bad debt and churn
```

A retailer's profit is not "retail price − wholesale price" but:

```
Net profit = Retail revenue
           − Wholesale energy cost
           − Deviation assessment cost
           − Opex and customer acquisition
           − Guarantee funding cost
           − Bad debt and churn cost
```

### 2.2 Retail-side pressure in 2026

| Symptom | Data / behaviour | Grade | Meaning |
|---|---|---|---|
| Retailer exits | 400+ exits in the first 7 months of 2026 | C | Industry consolidation accelerating |
| Guangdong losses | 298 of 500 retailers loss-making | B/C | Retail-wholesale inversion |
| Guangdong per-kWh margin | 0.0039 CNY/kWh average in H1 2026, about 0.0196 in 2025 | B/C | Margins sharply compressed |
| Guangxi negative spread | Maximum negative spread 0.373 CNY/kWh | C | Losses in extreme months |
| Guizhou losses | Over 40 million CNY lost in Jan–Feb 2026 | C | Regional problem |
| Anhui losses | Over 119 million CNY lost in January 2026 | C | Price-volatility shock |
| Shanxi spread | About 2 fen/kWh | C | Thin margin |
| System operation fee | About 0.068 CNY/kWh, up about 93% year on year | C | Hidden cost rising |
| Fixed TOU packages | About 11 provinces withdrew or marketised fixed TOU | C | Price risk passed to users |
| Guangdong retail average price | 0.4074 CNY/kWh in H1 2026 | B/C | Retail price level |
| Guangdong retail volume | 239.8 TWh in H1 2026 | B/C | Market size |

Reading: these are media or exchange-reported industry symptoms, not a unified national statistic; they show that "the spread model is shrinking" and must not be treated as any single company's financials.

### 2.3 Rule stack

| Level | Document | Number / date | Status | Relation to this skill |
|---|---|---|---|---|
| Departmental rule | Basic Rules for Power Market Operation | NDRC Order No. 20, 2024-04-25 | Current, effective 2024-07-01 | Market members, risk, dispute basis |
| Normative document | Basic Rules for the Medium- and Long-Term Power Market | Fagai Nengyuan Gui [2025] No. 1656 | Current, effective 2026-03-01, 5 years | Long-term settlement, deviation, risk |
| Normative document | Basic Rules for Power Market Metering and Settlement | Fagai Nengyuan Gui [2025] No. 976 | Current, effective 2025-10-01, 5 years | 5/8/10 timelines, objections, retroactive adjustments |
| Normative document | Measures for the Administration of Retail Electricity Companies | Fagai Tigai Gui [2021] No. 1595 | Current | Entry, performance guarantee, exit, universal service |
| Normative document | Retail Company Measures (revised consultation draft) | Released 2026-09-04, comments to 10-04 | Draft, proposed effective 2027-01-01 | Registered capital, guarantee formula, daily mark-to-market, exit |
| Normative document | Power Market Risk Prevention and Control Measures (public consultation draft) | Released 2026-09-30, comments to 10-30 | Draft, 7 chapters 32 articles | Risk classification, grading, disposal |
| Normative document | National Unified Power Market Credit Evaluation Guidelines (consultation draft) | Issued 2026-10-13, released 10-19 | Draft, 30-day consultation | A/B/C/D credit, incentives and constraints |
| Normative document | Notice on Strengthening the Administration of the Electricity Retail Market | 2026-06-08 | Current (public reporting, no verified document number, B/C) | Price linked to wholesale cost, package disclosure, ban on low prices and side agreements |
| Normative document | Basic Rules for the Electricity Retail Market | Pending | Not issued | Retail contracts, packages, exit, user protection |

### 2.4 Five retail package types

| Package | Price mechanism | Retailer risk | User risk | Suitable for |
|---|---|---|---|---|
| Fixed price | Fixed for the year / all hours | Loses when wholesale rises | Price does not fall with the market | Low risk appetite, stable load |
| Time-of-use | Peak/flat/valley or 24 hours | Curve forecast error, retail-wholesale mismatch | High peak prices | Users who can shift load |
| Average-price linked | Linked to wholesale average | Pass-through is smoother but lagged | Price follows the market | Users accepting volatility |
| Floor plus floating | Floor price + floating | Floor portion may lose | Floating portion uncertain | Mixed preferences |
| Service fee | Energy bill + service fee | Fee covers cost | Fee is transparent | Integrated energy customers |

### 2.5 Four changes in 2026

1. **Fixed TOU packages exit**: about 11 provinces withdrew or marketised fixed TOU, removing the "fixed peak-valley spread" protection;
2. **Price linked to wholesale cost**: the 2026-06-08 notice requires retail prices to reflect wholesale market changes and reduce inversion (B/C);
3. **Package disclosure and a ban on low prices**: all packages must be searchable and comparable; below-cost pricing, side agreements and offline rebates are banned;
4. **Tighter guarantees and credit**: the draft moves performance guarantees from "static prepayment on historical volume" to "expected annual sales × coefficient, daily mark-to-market".

---

## 3. The Seven-Step Operating Loop

### 3.1 Step 1: customer profile and load forecast

- Industry, voltage level, usage hours, peak-valley ratio, seasonality, maintenance plans;
- 12 months of 96-point curves, maximum demand, power factor;
- User credit, arrears record, ultimate controller, business stability;
- Forecast error band: set from industry and historical error, not guessed.

### 3.2 Step 2: package design and quotation

- Choose the package type: fixed / TOU / average-price linked / floor plus floating / service fee;
- Compute the full cost: wholesale + deviation + opex + funding + risk premium + profit;
- Run stress tests: spot up, deviation wider, customer churn;
- Write price-adjustment, deviation-allocation, termination and transfer clauses.

### 3.3 Step 3: procurement matching

- Long-term coverage ratio, curve shape, delivery point;
- Spot exposure, price limits, deviation treatment;
- Hourly matching between retail contract curves and wholesale contract curves;
- Both under-coverage and over-coverage are risks: under-coverage fears rises, over-coverage fears falls.

### 3.4 Step 4: deviation management

- Day-ahead and intra-month rolling forecasts, decomposed by customer group;
- Tolerance band, assessment price and responsibility allocation written into contracts;
- Warning thresholds, adjustment windows, contract transfer or buy-back;
- Assessment costs that can be passed through are passed through by contract; those that cannot are built into the package cost.

### 3.5 Step 5: spread and cash-flow monitoring

- Daily / weekly / monthly tracking: retail average price, wholesale average price, gross spread, net profit;
- Inversion warning: spot rises, system operation fee rises, package price adjustment lags;
- Cash flow: timing mismatch between retail collection and wholesale payment;
- Guarantee balance and risk exposure.

### 3.6 Step 6: guarantees, credit and settlement

- Performance guarantee amount, form (bond / insurance / cash), remaining amount;
- Credit grade, deduction items, remediation plan;
- Settlement 5/8/10 timelines, 15 working days for objections, 5 working days for confirmation, retroactive adjustment in the next cycle;
- User arrears, bad debt, prepayment and deposits.

### 3.7 Step 7: exit and customer handover

- Exit triggers: persistent failure to meet conditions, insufficient guarantee, repeated non-settlement, licence cancellation;
- Contract termination or transfer, user notification, metering and meter reading, cost settlement;
- Universal service or agency purchasing handover, notice of price and service changes;
- Exit loss calculation and recovery.

### 3.8 Inputs and outputs

Input contract:

- Province and business location, current or draft rule version;
- Customer list, 12 months of 96-point load, retail price and package type;
- Wholesale procurement structure (long-term ratio and price, spot curve), system operation fee;
- Deviation history, forecast error, assessment rules;
- Bond / insurance / cash amounts, credit grade, settlement records.

Output fields:

- Package cost breakdown, break-even quotation and target quotation;
- Customer contribution, portfolio net profit, concentration;
- Spot / deviation / churn stress scenarios;
- Guarantee amount, funding cost, gap;
- Inversion warning and exit contingency plan;
- Conclusion and uncertainties (policy, load, price).

---

## 4. Package Pricing

### 4.1 Full-cost breakdown

```
Fixed price = Wholesale cost W
            + Deviation cost D
            + Opex and acquisition O
            + Guarantee funding cost F
            + Risk premium R
            + Target profit M
```

Wholesale cost follows the procurement structure:

```
W = long-term coverage ratio × long-term price + (1 − coverage ratio) × spot price
```

### 4.2 Three pricing formulas

```
Fixed price:    P = W + D + O + F + R + M
TOU price:      P_t = W_t + D_t + O + F + R + M_t
Market-linked:  P = clamp(α × S + a, floor, cap)
```

- A fixed price shifts price risk from the user to the retailer, so it must carry a risk premium;
- A TOU price shifts part of the hourly risk to the user, but the retailer still bears curve forecast error;
- A market-linked price passes price risk back to the user, but a floor set too low loses money when prices fall and a cap set too high is rejected by users.

### 4.3 Break-even point

A fixed-price contract breaks even in cash (zero profit) at spot price S*:

```
S* = (P − D − O − F − c × L) / (1 − c)
```

If the contract must also earn the risk premium R on top of break-even, the safety line is:

```
S*_R = (P − D − O − F − R − c × L) / (1 − c)
```

where c is the long-term coverage ratio and L the long-term price. The gap between S* and the current spot price is this contract's price safety margin. R is a deliberate buffer, not an incurred cost, so it must not be mixed into the "break-even" calibre; quote S* externally and use S*_R for internal limits and credit.

### 4.4 Package selection matrix

| User trait | Preferred package | Reason |
|---|---|---|
| Stable load, low risk appetite | Fixed price | Certain budget, but the retailer needs a risk premium |
| Can shift load, high peak-valley ratio | TOU | Price signals can guide load |
| Accepts volatility, wants low average price | Average-price linked | Smoother pass-through, less inversion |
| Large user with bargaining power | Floor plus floating / service fee | Risk shared by both sides |
| Integrated energy customer | Service fee | Moves from spread to service value |

### 4.5 Common errors

- Counting only wholesale cost and omitting deviation, opex and guarantee funding;
- Using "current spot price" instead of the full-year procurement cost;
- Leaving no risk premium in a fixed price and betting on falling prices;
- Setting a market-linked floor below cost, so low prices become losses;
- Treating "retail minus wholesale" as profit without looking at churn and bad debt;
- Package terms that omit deviation responsibility and adjustment mechanisms.

### 4.6 Quotation calibre checklist

| Calibre | What to confirm | Common error |
|---|---|---|
| Energy vs public items | Whether the quote covers energy only; who bears T&D, system operation, funds and the basic charge | Comparing an energy price with an all-in bill |
| Tax-inclusive / exclusive | Whether the retail price, procurement price and deviation assessment use the same tax calibre; invoice type | Tax-inclusive revenue against tax-exclusive cost |
| Line loss | Whether line loss sits in the T&D price or the procurement price; whether cross-province trades add it | Double counting or omission |
| Deviation | Whether the tolerance band, assessment price and allocation are inside the quote | A quote that excludes deviation turns negative at settlement |
| Green power / certificates | Premium, certificate ownership, whether deductible | Treating a green premium as an ordinary energy price |
| Capacity / demand | Whether the basic charge is collected on the user's behalf and included in the package | A low package price with the basic charge billed separately |
| Adjustment mechanism | Market-linked parameters, triggers and frequency | Stating only a base price without the linkage formula |

If the calibre is not written down, a low price may simply be a cost that was left out. Attach a calibre sheet to every quotation and map it one-to-one to the contract clauses.

---

## 5. Customer Portfolio and Procurement Matching

### 5.1 Customer contribution

Annual contribution of one customer:

```
Contribution_i = Q_i × (P_i − W − D − O − F_i)
```

where F_i is the guarantee funding cost allocated by volume or contract; if it is not allocated at customer level, deduct F at portfolio level. The worked examples set F=0 for simplicity.

- A negative-contribution customer should be repriced or exited unless there is strategic, scale or synergy value;
- A positive but volatile customer must be judged by stress tests, not averages;
- Excessive concentration (for example one customer above 30%) requires separate credit and exit-risk assessment.

### 5.2 Portfolio net profit

```
Net profit = Σ Q_i × P_i − Q × W − Q × D − Q × O − F
```

where Q is total portfolio volume and F is the portfolio-level guarantee funding cost. Portfolio net profit is not a simple sum of single-customer contributions; it also depends on:

- The peak-valley profile of stacked user curves;
- Correlation between users (same industry maintaining or overusing at the same time);
- Curve matching and deviation of wholesale procurement;
- Acquisition cost and renewal rate.

### 5.3 Procurement coverage

| Coverage state | Risk | Management |
|---|---|---|
| Under-covered | Loses when spot rises | Raise long-term ratio, set price caps, keep a risk premium |
| Over-covered | Procurement cost too high when spot falls | Lower long-term ratio, transfer contracts, flexible delivery |
| Curve mismatch | Cannot buy peak, buys too much valley | Decompose procurement by user curve, contract by time block |
| Concentrated expiry | Renewal and procurement dates cluster | Stagger expiries, roll procurement |

There is no universal optimal coverage ratio; it depends on user curves, contract tenor, spot volatility and the retailer's risk capacity.

### 5.4 Customer selection

| Signal | Action |
|---|---|
| Negative contribution and no strategic value | Reprice or exit |
| Positive contribution but high concentration | Set credit limits, guarantees, termination rights |
| Arrears / overuse / illegal use | Prepayment, deposits, disconnection procedure |
| Large load forecast error | Raise the risk premium or switch to a linked package |
| Industry concentration | Stress-test simultaneous overuse or maintenance |

### 5.5 Common errors

- Looking only at single-customer margin and not the portfolio curve and correlations;
- Using average load instead of the 96-point curve, leaving peak hours under-covered;
- Signing negative-contribution customers for scale and losing more as you sell more;
- High customer concentration without guarantees and termination clauses;
- Excluding renewal rate and acquisition cost from the package cost.

---

## 6. Deviation Assessment and Forecast Risk

### 6.1 Definition of deviation

```
Deviation volume = Actual volume − Contracted volume
Deviation rate   = Deviation volume / Contracted volume
```

- Contracted volume may be a long-term contract, a spot declaration or the curve specified in a retail contract;
- The tolerance band, assessment price and responsibility allocation are set by provincial rules, and **there is no nationwide ±5%**;
- Article 74 of Document 1656 gives the "price-difference settlement / volume-difference settlement" principle; specific parameters are provincial;
- Deviation assessment is mostly a settlement price difference, not an administrative penalty, but it materially affects profit.

### 6.2 Expected deviation cost

Let F be the forecast in kWh, σ_F = σ × F the standard deviation of forecast error and ±t_F = ±t × F the tolerance band, where σ and t are shares of F; assume zero-mean normal errors. The expected volume outside the band is:

```
E[|ε| × 1{|ε| > t_F}] = 2 × σ_F × φ(t_F / σ_F) = 2 × σ × F × φ(t / σ)
```

where φ is the standard normal density. The 95% quantile of out-of-band volume is approximated by:

```
q_95 = max(z × σ_F − t_F, 0) = max((z × σ − t) × F, 0), z = 1.96
```

This model is for order-of-magnitude calculation only; provincial rules may assess at spot price, long-term price or a multiplier and must be replaced with the local formula.

### 6.3 Deviation management

| Stage | Action | Frequency |
|---|---|---|
| Forecast | Model by industry, history, weather and maintenance | Daily / monthly |
| Warning | Notify users when deviation approaches the band | Daily / weekly |
| Adjustment | Intra-month contract adjustment, transfer, buy-back | Per rule window |
| Allocation | Pass assessment costs to the responsible party by contract | Monthly |
| Review | Analyse error sources and fix the model | Monthly / quarterly |

### 6.4 Contract deviation clauses

Must state clearly:

- Contracted volume or curve and the settlement reference point;
- Who forecasts, how far ahead, and the error band;
- Responsibility split among user, retailer, grid and force majeure;
- Allocation ratio, upper/lower limits and settlement method for assessment costs;
- Warning thresholds, notification deadlines and adjustment windows;
- Evidence such as metering data, dispatch instructions and weather certificates;
- Objection window and dispute resolution.

### 6.5 Common errors

- Applying "±5%" nationwide;
- Counting only the assessment price and not the base volume outside the band;
- Contracts that omit deviation responsibility, leaving all assessment with the retailer;
- Guessing the forecast error band instead of matching the actual distribution;
- Skipping intra-month adjustments and missing the window.

---

## 7. Retail-Wholesale Inversion and Stress Testing

### 7.1 What inversion is

Retail-wholesale inversion = the retail contract price is below the full cost (wholesale procurement + deviation + opex + guarantee funding). Common causes:

- Spot prices rise while fixed-price packages adjust late;
- System operation fees rise (about 0.068 CNY/kWh in Q1–Q3 2026, up about 93% year on year, C);
- Fixed TOU packages exit, removing peak-valley spread protection;
- Low-price volume chasing, side agreements, offline rebates;
- User curves mismatch procurement curves: buying peak expensive and valley in excess.

### 7.2 Stress-test matrix

At minimum:

| Dimension | Scenario | What to watch |
|---|---|---|
| Spot price | +20% / +30% / +50% | Net profit, break-even point, guarantee usage |
| Deviation | σ = 2% / 4% / 6% | Assessment cost, whether the tolerance band suffices |
| Customer churn | −10% / −20% | Fixed-cost dilution, over-coverage |
| Guarantee | Coefficient raised, gap top-up | Funding cost, trading limits |
| Collection | Arrears of 30 / 60 / 90 days | Cash-flow gap |

### 7.3 Break-even point and safety margin

Portfolio break-even spot multiplier:

```
m* = 1 + net profit / (total volume × spot exposure ratio × base spot price)
```

`m* − 1` is the percentage by which the spot price can rise. Below it the portfolio still profits; above it, losses begin. A single fixed-price contract's break-even point can be far below the portfolio's, because high-margin customers subsidise low-margin ones.

### 7.4 Cash flow

- Retail collects monthly or per contract while wholesale pays on the 5/8/10 timeline, creating a timing mismatch;
- User arrears directly squeeze guarantees and cash flow;
- Bonds, insurance and cash all consume funds; low-price volume chasing raises both business scale and guarantee demand;
- Stress tests must cover both profit and cash flow, not profit alone.

### 7.5 Common errors

- Running only the base case and not a spot rise;
- Using the annual average price instead of monthly or hourly procurement cost;
- Treating high-margin customers' profit as the whole portfolio's safety cushion;
- Ignoring guarantee funding cost and assuming "a bond is not money";
- Continuing to pay for the original procurement volume after customer churn, creating over-coverage.

---

## 8. Credit, Performance Guarantees and Settlement

### 8.1 Credit evaluation

The 2026-10-13 credit evaluation guidelines (draft) set four grades A/B/C/D:

| Grade | Score range | Main constraint |
|---|---|---|
| A | (85, 100] | Incentives, priority, lower guarantee |
| B | (70, 85] | Normal administration |
| C | (40, 70] | Higher guarantee, no insurance for incremental amounts |
| D | [0, 40] or severe dishonesty | Enhanced supervision, trading restrictions, possible exit |

- Quarterly evaluation with dynamic adjustment; results are valid nationwide;
- Credit is not a bank rating, but it directly affects deposits, trading permissions and universal-service eligibility;
- At grade C, fix performance, settlement and disclosure issues; do not wait for D.

### 8.2 Performance guarantee: current and draft

Current Document 1595:

```
Amount = max(wholesale purchases in the past 12 months × 0.8 fen/kWh,
             2 months of maximum purchases × 5 fen/kWh)
```

2026-09-04 retail company measures revision (draft):

```
Amount = max(2 million CNY, expected annual sales × 1 fen/kWh × adjustment coefficient)
Adjustment coefficient ∈ [1, 10]
```

| Dimension | Current 1595 | 2026 draft |
|---|---|---|
| Base | Historical purchases / short-term peak | Expected annual sales |
| Unit rate | 0.8 fen / 5 fen | 1 fen |
| Adjustment | No coefficient | Coefficient 1–10 |
| Minimum | No unified floor | 2 million CNY |
| Monitoring | Mainly static prepayment | Daily mark-to-market, top-up on shortfall |
| Top-up timing | Local rules | 1 working day notice, 3 working days payment, 1 working day restore |

### 8.3 Bonds, insurance and cash

| Form | Advantage | Disadvantage | Suitable for |
|---|---|---|---|
| Performance bond | Payable on demand, strong credit | Uses credit line, issuance fee, may need counter-guarantee | Most retailers; grade C/D increments |
| Performance insurance | Premium may be lower, no credit line | Exclusions and limits; may be banned for low credit | Grade A/B, non-incremental |
| Cash deposit | Direct, no credit review | Consumes cash flow, high opportunity cost | Small or temporary top-ups, when bond or insurance unavailable |

### 8.4 Settlement

- Document 976 sets unified timelines: 5th / 8th / 10th working day (check version / official version / bill);
- Objections within 15 working days, confirmation within 5 working days, verified items adjusted retroactively in the next cycle;
- No imbalance fund pool may be set up;
- The retailer must check volume, price, deviation, assessment, allocation and retroactive adjustments;
- The timing mismatch between user arrears and wholesale payment is the main source of cash-flow risk.

### 8.5 Common errors

- Using registered capital instead of a performance guarantee;
- Counting only the guarantee amount and not the fee or credit-line usage;
- Grade C/D entities still using insurance for incremental guarantee;
- Checking only the settlement total and not deviation and allocation;
- No prepayment or deposit for arrears, so bad debt erodes profit directly.

---

## 9. Exit and Universal Service

### 9.1 Exit triggers

The exit mechanism in the 2026-09-04 retail company measures revision (draft):

| Mechanism | Trigger | Consequence |
|---|---|---|
| Automatic business-location reduction | No actual settlement in a location for 2 consecutive calendar years | Location reduced |
| Suspension of location trading | No actual trading settlement in a location for 12 consecutive months | Trading suspended there |
| Automatic deregistration | No actual settlement in any location for 12 consecutive months; licence cancelled or revoked | Market registration cancelled |
| Forced exit | Registration conditions not maintained, guarantee not paid in full on time, serious violations | Forced exit |
| Contract treatment | Unperformed contracts at exit | Automatically terminated; losses borne by the retailer (draft) |
| Customer handover | Inability to perform | Universal service / agency purchasing; user may choose a new retailer the next month |

### 9.2 Universal service

| Dimension | Current / local practice | 2026 draft signal |
|---|---|---|
| Provider | Grid company, designated retailer | Improve the universal-service mechanism |
| Trigger | Inability to perform, exit, arrears | Inability to perform |
| Price | 1.5× / 2× agency purchasing price in some regions | Settled at the real-time spot price of the month of non-performance |
| User choice | May switch to another retailer | May choose a new retailer the next month |
| Service | Universal supply, no disconnection | Protect the bottom line of supply safety |

- Universal service is not free: its price is usually above normal retail packages;
- 1.5× / 2× is current or local practice, not a national rule; the 2026 draft proposes real-time spot settlement, and the final text is undecided;
- No disconnection is the bottom line, but contracts, prices, invoices and deviation responsibility all change.

### 9.3 Exit contingency checklist

- Trigger conditions and internal decision process;
- Customer list, contract expiry dates, arrears and prepayments;
- Contract termination / transfer templates and notification deadlines;
- Meter reading, cost settlement, invoice handover;
- Universal-service / agency purchasing contacts and phone numbers;
- Bond calls, debt recovery, regulatory reporting;
- Public-opinion and complaint handling.

### 9.4 Common errors

- Waiting until suspension to think about customers;
- Contracts without termination or transfer clauses;
- Leaving deviation and assessment unsettled at exit, creating disputes;
- Users unaware, complaining after the universal-service switch;
- Continuing to expand trading after the bond is called.

---

## 10. Worked Examples (Synthetic Data, Grade D)

> Reproduce: `python skills/retail-electricity-risk/tools/selftest.py` (cases A–H). All figures are grade-D synthetic data and correspond to no real retailer, customer or province; a formal calculation must substitute provincial documents and real contracts.

### 10.1 Package pricing

An industrial user consumes 30 GWh per year. Procurement is 70% long-term at 0.40 CNY/kWh and 30% spot; the spot curve averages 0.4575 CNY/kWh, so the weighted procurement price is **0.41725**. Deviation cost is 0.008, opex 0.025 and target profit 0.010:

| Item | Value |
|---|---|
| Wholesale cost | 0.41725 |
| Deviation cost | 0.00800 |
| Opex | 0.02500 |
| Break-even quotation (excluding target profit) | **0.45025** |
| Target profit | 0.01000 |
| Target quotation (including target profit) | **0.46025** |

Signed at 0.46 CNY/kWh, the per-kWh net profit is **0.00975** and the annual net profit **292,500.00 CNY**. The quotation is **0.975 fen above the break-even quotation** but **0.025 fen below the target quotation**; the cushion is thin, and any wider deviation or spot rise will swallow the profit.

> This example sets the guarantee funding cost F and the risk premium R to zero. A real quotation must add F and R on top of 0.45025; never quote 0.45025 directly.

### 10.2 Customer portfolio

Three customers: industrial A 30 GWh at 0.46; commercial B 20 GWh at 0.49; fleet C 10 GWh at 0.53. Total 60 GWh:

| Metric | Value |
|---|---|
| Retail revenue | 28,900,000.00 |
| Wholesale cost | 25,035,000.00 |
| Deviation cost | 480,000.00 |
| Opex | 1,500,000.00 |
| Net profit | **1,885,000.00** |
| Net profit per kWh | **0.0314167** |
| Gross spread | 0.0644167 |

The 3.14 fen/kWh here is above Guangdong's 2026 average of 0.0039; it is built to show structure and is not an industry benchmark. The gross spread is 6.44 fen; after 0.8 fen of deviation and 2.5 fen of opex, only 3.14 fen remains. This example excludes guarantee funding F, risk premium R and bad debt; including them would lower the net profit.

### 10.3 Spot stress test

| Scenario | Portfolio net profit |
|---|---|
| Base | 1,885,000.00 |
| Spot +20% | **238,000.00** |
| Spot +30% | **−585,500.00** |
| Break-even rise | **+22.89%** |

The portfolio withstands about a 23% spot rise because commercial and fleet customers carry higher margins; for industrial A's 0.46 contract alone, the break-even spot price is **0.49**, only **7.10%** above the 0.4575 base. **A single contract's safety margin is not the portfolio's.**

### 10.4 Customer selection

Candidate customer D: 5 GWh per year at 0.43. Under the same procurement and cost calibre, the per-kWh cost is 0.45025 and the contribution **−0.02025 CNY/kWh**, or **−101,250.00 CNY** per year. Including D lowers portfolio net profit to **1,783,750.00 CNY**; dropping D restores **101,250.00 CNY**.

### 10.5 Deviation assessment

Monthly forecast 1 GWh, tolerance band ±5%, out-of-band assessment 0.15 CNY/kWh:

| Forecast error σ | Expected out-of-band volume | Expected assessment cost | 95% quantile volume | 95% quantile cost |
|---|---|---|---|---|
| 2% | 701.13 kWh | 105.17 | 0 | 0 |
| 4% | 14,611.93 kWh | 2,191.79 | 28,398.56 kWh | 4,259.78 |
| 6% | 33,829.43 kWh | 5,074.41 | 67,597.84 kWh | 10,139.68 |

If actual volume in one period is 8% above forecast, the out-of-band volume is 30,000 kWh and the assessment **4,500.00 CNY**. As σ worsens from 2% to 6%, expected assessment cost rises from about 105 CNY/month to about 5,074 CNY/month, roughly 60,000 CNY annualised; that is the direct economic value of forecast accuracy.

### 10.6 Performance guarantee

A retailer expects annual sales of 3 billion kWh and maximum purchases over two months of 500 million kWh:

| Calibre | Amount |
|---|---|
| Current 1595: 3 billion × 0.8 fen/kWh | 24 million CNY |
| Current 1595: 500 million × 5 fen/kWh | 25 million CNY |
| Current, larger of the two | **25 million CNY** |
| Draft coefficient 1 | **30 million CNY** |
| Draft coefficient 5 | **150 million CNY** |
| Draft coefficient 10 | **300 million CNY** |

At a 1%/year bond fee: 250,000 CNY/year under the current rule; 300,000 / 1,500,000 / 3,000,000 CNY/year under draft coefficients 1 / 5 / 10. For the same volume, the draft amount is **1.2× to 12×** the current amount; the coefficient is the largest sensitivity.

### 10.7 Guarantee gap

Required 30 million CNY, submitted 20 million, gap **10 million CNY**, status insufficient. Under the draft timeline: 1 working day notice, 3 working days payment, 1 working day restore; at 1% funding cost the gap adds **100,000.00 CNY** per year.

### 10.8 The floor of a market-linked package

Market-linked package with 100% pass-through plus 0.01 CNY/kWh, floor 0.40, cap 0.55. The table uses the 70/30 portfolio-weighted procurement cost: at the base spot of 0.4575, W = 0.7×0.40 + 0.3×0.4575 = 0.41725; when spot falls to 0.40 and the long-term tranche is still locked at 0.40, W = 0.40.

| Spot price | Retail price | Weighted procurement cost | Net profit per kWh |
|---|---|---|---|
| 0.4575 (base) | 0.4675 | 0.41725 | 0.01725 |
| 0.40 | 0.41 | 0.40 | **−0.02300** |

The 0.40 floor is a floor on the retail price; at a spot price of 0.40 the formula gives 0.41, so the floor is not triggered. Even at 0.41, deducting 0.40 procurement, 0.008 deviation and 0.025 opex leaves a 2.3 fen loss. **Set the floor by cost, not by market price**: at a spot price of 0.40 the break-even retail price is **0.433**; if the floor is written on the spot price instead, back it out from P = αS + a ≥ 0.433.

### 10.9 Reading

- Cost a package fully before looking at the spread; gross spread is not profit;
- The portfolio's tolerable spot rise can be far higher than a single contract's; do not let the portfolio cushion hide single-customer risk;
- Reprice or exit negative-contribution customers; scale is not profit;
- Deviation is probabilistic: use expectations and quantiles, not one month;
- Guarantee amount and coefficient consume funds directly; low-price volume chasing amplifies both business and guarantee demand;
- A market-linked floor must cover cost, and the contract must state whether it applies to the retail price or the spot price, or low prices become losses;
- Every number is grade-D synthetic data and cannot be used for a real company.

---

## 11. Compliance, Ledgers and Red Lines

### 11.1 Compliance points

- All packages public, searchable and comparable;
- Retail prices reflect wholesale cost changes; no below-cost unfair competition;
- No side agreements, off-contract rebates or offline arrangements;
- No false packages, forced bundling or concealed deviation responsibility;
- Disclose wholesale and retail volume, prices, package signings and spreads as required;
- Execute credit evaluation, performance guarantees, settlement and exit under current or draft requirements as applicable.

### 11.2 Ledgers

| Ledger | Content | Frequency |
|---|---|---|
| Package ledger | Package type, price, cost, disclosure record | Every change |
| Customer ledger | Contract, curve, credit, guarantee, arrears | Monthly |
| Procurement ledger | Long-term / spot, coverage ratio, curve | Daily / monthly |
| Deviation ledger | Forecast, actual, assessment, allocation | Monthly |
| Guarantee ledger | Amount, form, remaining, top-up | Daily |
| Settlement ledger | Bills, objections, retroactive adjustments | Monthly |
| Exit plan | Triggers, customer list, handover | Quarterly / on trigger |

### 11.3 P0: correctness

| Check | Pass standard |
|---|---|
| Province and business location | Rules, coefficients and universal-service prices come from local documents |
| Current or draft | Status and effective date marked |
| Package cost | Wholesale + deviation + opex + funding + risk + profit |
| Quotation calibre | Energy/public items, tax-inclusive/exclusive, line loss, deviation and green-power ownership stated |
| Procurement structure | Matched to retail contract curve and tenor |
| Deviation calibre | Tolerance band, assessment price and allocation consistent with the province |
| Guarantee formula | Current and draft calculated separately |
| Settlement timeline | 5/8/10 and 15/5 verified |
| Credit grade | Consistent with guarantee amount and insurance limits |
| User consent | Evidence for contract, transfer and exit |

### 11.4 P1: maintainability

| Check | Pass standard |
|---|---|
| Parameter externalisation | Prices, coefficients and assessment standards not hard-coded |
| Version management | Each calculation stores the rule version and input snapshot |
| Scenario analysis | At least spot / deviation / churn |
| Reproducibility | Same inputs give the same net profit |
| Audit trail | Every number traces to a contract or bill |
| Exit plan | Customer handover, contract transfer and universal-service linkage complete |

### 11.5 Red lines

- Never write a draft as already in force;
- Never substitute another province's rules;
- Never quote below cost;
- Never sign side agreements or pay offline rebates;
- Never conceal deviation responsibility or exit clauses;
- Never misappropriate deposits;
- Never promise a retailer "guaranteed profit";
- Never alter load, deviation or settlement data.

---

## 12. Code Map and Self-Test

| File | Purpose |
|---|---|
| `tools/package.py` | Fixed and market-linked quotations, single-customer annual result, break-even spot price |
| `tools/portfolio.py` | Portfolio net profit, customer contribution, spot stress, break-even multiplier |
| `tools/deviation.py` | Out-of-band volume, assessment cost, expectation and 95% quantile |
| `tools/guarantee.py` | Current and draft guarantees, funding cost, gap |
| `tools/curves.py` | Synthetic customer curves, spot curve and TOU prices |
| `tools/selftest.py` | Locks all worked examples A–H in the text plus instance-layer I/J |

Run:

```bash
python skills/retail-electricity-risk/tools/selftest.py
```

A green self-test means the text and code agree; when a policy parameter changes, update `curves.py` or the call parameters first, then sync the numbers in both language versions.

### 12.1 Instance packs: Guangdong 2026 and Jiangsu 2027 retail

The engine layer answers "what is the method"; the instance layer answers "**for this province, this customer portfolio, these contracts and this trading style, what price do we quote, how much do we buy, and where did T+1 differ**". The instance is a configuration layer and does not change the 101 modules / 13 sections / 9 skills count.

| File | Purpose |
|---|---|
| `instances/README.md` | Retail instance schema: six blocks, two package models (`fixed_market_linked` / `annual_retail_pass_through`), D-1/T+1 formats, 30-minute workflow, validation and acceptance |
| `instances/guangdong-retail-2026-11/instance.json` | Guangdong config: Southern regional price zone, three customer segments, 75% medium-term cover, contract deviation terms, 1595 guarantee |
| `instances/guangdong-retail-2026-11/run.py` | Config validation → full-cost pricing → five scenarios/stress → 9-bucket T+1 bridge → review table |
| `instances/guangdong-retail-2026-11/make_demo.py` | Grade-D synthetic D-1/T+1 data (96 points × 5 scenarios) |
| `instances/guangdong-retail-2026-11/pitfalls.md` | Ten Guangdong retail pitfalls and a 60-second pre-quote checklist |
| `instances/jiangsu-retail-2027/instance.json` | Jiangsu 2027 config: wholesale price + floating price + ΣK×allocation, one-household-one-price cap (F agreed by buyer and seller), split green-power energy/environmental contracts |
| `instances/jiangsu-retail-2027/run.py` | Config validation → wholesale/reference price → segment pass-through and cap → four stress cases → 6-bucket T+1 bridge → review table |
| `instances/jiangsu-retail-2027/make_demo.py` | Grade-D synthetic D-1 load and T+1 actuals (96 points, incl. P1/P2/P3 allocations) |
| `instances/jiangsu-retail-2027/pitfalls.md` | Twelve Jiangsu 2027 retail pitfalls and a 60-second pre-quote checklist |

```bash
python skills/retail-electricity-risk/instances/guangdong-retail-2026-11/run.py --check-config
python skills/retail-electricity-risk/instances/guangdong-retail-2026-11/run.py --demo
python skills/retail-electricity-risk/instances/jiangsu-retail-2027/run.py --check-config
python skills/retail-electricity-risk/instances/jiangsu-retail-2027/run.py --demo
```

Guangdong grade-D synthetic baseline (2026-11-18): 2,880 MWh portfolio, reference spot 375.67 CNY/MWh, weighted procurement 393.92, current retail price 414.43, recommended full cost 418.14, weighted gap 3.71; plan margin 37,070 CNY, expected 26,063, CVaR10 −28,354; actual 19,898, delta −17,172, bridge residual −1.75e-10 CNY.

Jiangsu 2027 grade-D synthetic baseline (2026-11-13): 1,972.7 MWh portfolio, P_MT 401.00, wholesale average 395.01, reference price 428.52, retail price 456.48, one-household-one-price cap 454.74 CNY/MWh, weighted clip 1.75, 4/4 segments capped; plan net margin 89,692 CNY, scenario expectation 92,043, CVaR10 89,692; actual 93,280, delta +3,588, bridge residual 0.00e+00. The stress table shows no clipping at spot ×0.8/×1.2/×1.5 and clipping only at ×1.0 — because the reference price rises almost 1:1 with spot while the wholesale price is only about 30% spot-linked; this is structural for full pass-through, not a model error.

Both number sets validate the workflow only and correspond to no real company; keep real customer and contract data local.

---

## 13. Q&A

**Q1: A retailer says "we earn only a few li per kWh". How do I judge that?**
Is it gross spread or net profit? Deduct wholesale cost, deviation, opex, guarantee funding and bad debt. In this note the gross spread is 6.44 fen and net profit 3.14 fen; Guangdong's 2026 industry average net margin is about 0.39 fen (B/C). Quoting only the gross spread answers nothing.

**Q2: Can a fixed-price package still be signed?**
Yes, with three things: full-cost pricing, stress testing and limits or hedges. A single industrial contract breaks even at spot 0.49 while the base spot is 0.4575; a 7.10% spot rise wipes out the profit. Fixed pricing is not forbidden, but it cannot go without a risk premium.

**Q3: Does a market-linked package pass all risk to the user?**
Not entirely. The user bears price volatility, but the retailer still bears curve deviation, churn and a poorly set floor. In this example, at a spot price of 0.40 the formula price is 0.41; after full cost the retailer still loses 2.3 fen. The break-even retail price is at least 0.433, and the contract must state whether the floor applies to the retail price or the spot price.

**Q4: How much guarantee must be posted?**
Current rules take the larger of "12 months of wholesale purchases × 0.8 fen" and "2 months of maximum purchases × 5 fen"; the 2026 draft uses "expected annual sales × 1 fen × coefficient (1–10), minimum 2 million CNY". In the 3 billion kWh example the current amount is 25 million CNY, while draft coefficients 1/5/10 give 30 million / 150 million / 300 million CNY. The draft is not current law.

**Q5: If the customer leaves or the retailer exits, what happens to the user?**
The user moves to universal service or agency purchasing and may choose a new retailer the next month; price, contract, invoice and deviation responsibility all change. Current or local universal-service prices are often 1.5× / 2× the agency purchasing price; the 2026 draft proposes settlement at the real-time spot price of the month of non-performance, and the final text is undecided.

---

## 14. Sources and Maintenance

### 14.1 Main sources

| Type | Content |
|---|---|
| Knowledge notes | [Power market risk, credit and settlement](../../knowledge/电力市场风险、信用与结算-2026-11.md), [quantitative bidding and trading risk control](../../knowledge/量化报价与交易风控-工程化-2026-11.md), [tariff system note](../../knowledge/中国电价制度谱系-2026-11.md) |
| Policy texts | NDRC, NEA, provincial DRC / energy bureaus and exchange public rules; document numbers and links in the policy lists |
| Provincial samples | [Provincial market status](../../knowledge/省级市场状态表-2026-11.md), [provincial policy list](../../knowledge/省级政策列表-2026-11.md) (grade B/C, pending verification) |
| Worked examples | All grade-D synthetic data generated by `tools/curves.py` |

### 14.2 Maintenance rules

- If any retail rule, deviation, guarantee, credit or universal-service rule changes, update the knowledge note first, then the `tools/` parameters and `selftest.py`, and finally both language versions of this skill;
- Provincial values must carry document number, effective date and source grade;
- Consultation drafts must not be written as already in force;
- Review provincial samples and guarantee coefficients quarterly; run the P0 review monthly alongside the knowledge base.

### 14.3 Disclaimer

This document and the tools are calculation demonstrations only and do not constitute investment advice, a quotation commitment or legal opinion. Real retail operations must use the latest provincial documents, real contracts and load data, and be reviewed by qualified professionals.

- **Price-driver routing**: quantity ([weather and power trading](../../knowledge/气象与电力交易-2026-11.md)), price ([fuel and power trading](../../knowledge/燃料与电力交易-2026-11.md)), deliverability ([inter-provincial trading](../../knowledge/省间与跨区交易-2026-11.md) §5.5-5.6). For "why is this interval expensive", check quantity -> price -> constraint -> superposition; see the [golden Q&A](../../knowledge/黄金问答集-2026-11.md) section F (Q29-Q38) for regression questions.
