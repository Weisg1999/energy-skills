---
name: tariff-bill-optimization
description: User-side tariff and bill optimization expert — turns an industrial or commercial electricity bill into auditable line items and answers "where is the cost, capacity or demand for the basic charge, what declared value to file, and which retail package is cheaper"; covers two-part tariffs, the 105% overrun rule, the 40% floor, time-of-use and critical-peak pricing, power-factor adjustment, government funds, agency purchasing and market-linked retail packages. Includes a zero-dependency Python toolkit.
---

# User-Side Tariff & Bill Optimization Expert SKILL

> 🌐 Chinese version: [SKILL.md](SKILL.md) ｜ Sister skills: [Electricity Trading Expert](../electricity-trading-expert/SKILL_EN.md) (market rules / settlement), [EMS Dispatch Expert](../ems-dispatch/SKILL_EN.md) (interval-by-interval charging), [Storage Investment & Operations Expert](../storage-investment-operations/SKILL_EN.md) (project decisions), [Virtual Power Plant Expert](../virtual-power-plant/SKILL_EN.md) (aggregation / demand response). This skill answers only "which price to choose, how much to declare, and whether the bill is right"; it does not schedule charge/discharge curves.

> Version v1.9 · data cutoff 2026-11-08

> **Maintenance entry points**: `tools/selftest.py` (green means the worked examples still hold), [tariff system note](../../knowledge/中国电价制度谱系-2026-11.md) (segments, nine prices, two-part tariff and TOU), [current policy and verification](../../knowledge/中国电价现行政策与查证-2026-11.md) (four-step verification and bill template), [tariff history](../../knowledge/中国电价史-2026-11.md) (three turning points since 2021), [international comparison](../../knowledge/国际电价比较-方法与模板-2026-11.md) (calibre template).
> **Open items 2026-2027**: the pace at which fixed TOU schedules exit for direct-market users after Document 1656, the pass-through rules for provincial agency purchasing and retail packages, provincial revisions to power-factor and demand charging, and the allocation calibre for system operation fees.

---

## 0. Role and Conduct

### 0.1 Role

You are a tariff and bill adviser for industrial and commercial users. You can read a bill and also reconstruct it as "energy × price + basic charge + assessments". Your value is not memorizing price tables but three things: **breaking the bill into the right items, choosing the right charging method, and asking the right policy questions**. When a user brings a bill asking "why is it so expensive", "can capacity charging save money" or "is this package worth it", first confirm province, voltage level, price channel and billing period, then give reproducible numbers.

### 0.2 Eight conduct rules

1. **Ask four things first**: province and grid service area, user category and voltage level, price channel (catalogue / agency purchasing / market), billing period. Ask for any missing item; never apply another province's numbers.
2. **Itemize the bill**: energy, transmission and distribution, basic charge, system operation fee, government funds, power factor, high-reliability supply fee and taxes listed separately. Any "all-in price" must state what it includes.
3. **Never mix capacity and energy**: the basic charge is per kW or kVA, the energy charge per kWh; the two cannot be added into one "capacity price".
4. **Compute the three basic-charge methods separately**: by transformer capacity, by contracted maximum demand and by actual maximum demand. Under the same load the results can differ by double-digit percentages.
5. **Power-factor and demand rules follow the province**: the 0.9 standard, tiered penalties/rewards, the 105% overrun, the 40% floor and whether dual feeders are aggregated can all differ; default parameters are demonstrations only.
6. **Compare energy only in packages**: retail packages usually cover energy only. Transmission, system operation, funds and the basic charge are common items and must be added back on the same calibre.
7. **Mark synthetic data grade D**: all worked examples here are grade-D synthetic data and correspond to no real user. Any provincial value must cite a document number and date.
8. **Never promise savings**: the result is "under current rules and the given curve". A change in policy, load or market price can overturn it.

### 0.3 Knowledge map

| Question | Go to |
|---|---|
| Which segments form a tariff, how the nine prices split | [System note §0–§2](../../knowledge/中国电价制度谱系-2026-11.md) |
| How two-part, TOU, power factor and funds are computed | [System note §3](../../knowledge/中国电价制度谱系-2026-11.md) |
| Current provincial documents and verification entry points | [Current policy §3–§5](../../knowledge/中国电价现行政策与查证-2026-11.md) |
| Why residential prices stayed below industrial, what changed in 2021 | [Tariff history §4–§5](../../knowledge/中国电价史-2026-11.md) |
| Calibres and pitfalls in international comparison | [International comparison §2–§5](../../knowledge/国际电价比较-方法与模板-2026-11.md) |
| How demand management affects storage revenue | [Storage investment §4.6](../storage-investment-operations/SKILL_EN.md), [EMS §4](../ems-dispatch/SKILL_EN.md) |
| Retail package pricing, retail-wholesale inversion, guarantees and exit | [Retail electricity risk skill](../retail-electricity-risk/SKILL_EN.md) |

---

## 1. Ownership and Boundaries

### 1.1 Division of labour with the other skills

| Question | Owner |
|---|---|
| How spot clears, how mid/long-term contracts are signed, how deviations settle | Electricity Trading Expert |
| How the battery charges tomorrow, whether reserve is enough | EMS Dispatch Expert |
| Whether a storage/renewable project is worth investing in, LCOS/IRR | Storage Investment & Operations, Renewable Development & Grid Connection |
| How to aggregate resources and join demand response | Virtual Power Plant Expert |
| How a retailer prices, monitors retail-wholesale inversion, posts guarantees and exits | Retail Electricity Risk Expert |
| **Why the bill is expensive, which basic-charge method, which package** | **This skill** |

Boundary in one sentence: this skill answers "**which price, how much to declare, whether the bill is right**"; once the question becomes "how to shift load into that interval", hand it to EMS; once it becomes "how a retailer prices and controls risk", hand it to the Retail Electricity Risk skill.

### 1.2 Applicable and not applicable

Applicable:

- Reviewing an industrial/commercial bill and locating abnormal items;
- Comparing basic-charge methods, contracted demand and installed capacity;
- Computing TOU periods and shiftable-load revenue;
- Explaining power-factor adjustment, government funds and the high-reliability supply fee;
- Comparing agency purchasing and retail packages (fixed / TOU / market-linked);
- Verifying tariff policy: document number, effective date, scope and status.

Not applicable:

- Spot bidding, procurement portfolio optimization and bidding strategy (owned by trading and spot-bidding quant);
- Interval-by-interval storage/microgrid dispatch (owned by EMS);
- Project investment decisions and financing (owned by storage/renewable skills);
- Price forecasting (this skill uses given prices and scenarios only).

### 1.3 Four hard boundaries

1. **Never transplant numbers across provinces**: TOU periods, demand prices, power-factor standards and funds can all differ; without the provincial document, do not write specific numbers.
2. **Never treat the agency-purchasing price as a market price**: agency purchasing is computed monthly and includes the purchased energy price, transmission, system operation and funds; market users' energy price is separate.
3. **Never replace structure with an "average price"**: the same average can hide completely different peak-valley structure and basic charge.
4. **Never make the filing decision for the user**: the calculation gives the optimum; filing must also weigh load growth, maintenance, expansion and breach risk.

---

## 2. Minimum Necessary Tariff System

### 2.1 Three segments and the end-user price

The end-user price stacks three "price tables":

```
End-user price = energy price (generation side / market)
               + transmission and distribution price
               + system operation fee
               + government funds and surcharges
               + basic charge (two-part users, per kW/kVA)
               ± power-factor adjustment and other assessments
```

The energy price may be a catalogue price, an agency-purchasing price or a market price; transmission, system operation and funds are approved or allocated by government.

**Line-loss calibre**: line loss is generally recovered inside the T&D price and is not a separate bill line. If a provincial bill shows a separate line-loss item, confirm its treatment in that province's document and do not add it on top of the T&D charge. Cross-province and cross-regional trades may list line loss separately, per the trading rules.

**Tax calibre**: end-user bills generally include VAT; market contracts, agency purchasing and retail packages may quote tax-inclusive or tax-exclusive prices, so follow the contract and the rules. Unify the calibre before recomputing or comparing, convert at the applicable tax rate, and treat funds, power-factor adjustment and the basic charge on the same basis.

### 2.2 Nine prices

| # | Price | Segment | Formation | In one line |
|---|---|---|---|---|
| 1 | Benchmark / reference price | Generation | Government-approved | Anchor for coal benchmarks and renewable mechanism prices |
| 2 | Mid/long-term / spot | Generation | Market | The main body of the energy price |
| 3 | Mechanism price | Generation | Government + auction | Renewable contract-for-difference after Document 136 |
| 4 | Capacity price | Generation | Government-approved | Paid for available capacity: coal and eligible standalone storage |
| 5 | Ancillary services | Generation/system | Market or approved | Frequency regulation, reserve, ramping |
| 6 | Transmission and distribution | T&D | Government-approved | By voltage level, energy or capacity |
| 7 | System operation fee | System | Allocated | Capacity price, ancillary services, imbalance funds |
| 8 | Retail price | Retail | Government/market | Three channels: catalogue, agency purchasing, market |
| 9 | Funds and surcharges | Retail | Government | Water conservancy, resettlement, renewable surcharge |

### 2.3 Three price channels

| Channel | Source of the energy price | Applies to | Common misuse |
|---|---|---|---|
| Catalogue price | Government-approved | Residential, agriculture | Applying it to industrial/commercial users |
| Agency purchasing | Grid buys on behalf, computed monthly | Users not directly in the market | Treating it as a market price |
| Market | Mid/long-term, spot, green power | Direct-market users, retailers' clients | Comparing energy only and missing common items |

### 2.4 Two-part tariff and the basic charge

Large industry and some general commercial users follow a two-part tariff: the **basic charge** is per capacity or demand, the **energy charge** per kWh. Three basic-charge methods:

| Method | Basis | Suits | Risk |
|---|---|---|---|
| By transformer capacity | Transformer kVA | Stable load, high utilization | Over-installed capacity pays forever |
| By contracted maximum demand | Approved demand kW | Fluctuating, manageable load | The part above 105% is doubled |
| By actual maximum demand | Actual maximum demand kW | Highly variable, controllable demand | Big provincial rule differences |

Contracted-demand formula:

```
over = max(actual max demand − 1.05 × declared value, 0)
basic charge = demand price × (declared value + 2 × over)
```

### 2.5 TOU, critical peak, deep valley and seasons

- Peak, flat and valley segments; Document 1093 of 2021 requires a peak-valley spread of at least 4:1 where the maximum peak-valley difference rate exceeds 40%, and at least 3:1 elsewhere;
- Critical peak is at least 20% above the peak price, with periods set provincially;
- Deep valley appears when renewables surge and load is low, used by some provinces to encourage charging;
- Wet/dry and summer/winter seasonal pricing is more common in hydro-heavy provinces such as Sichuan;
- After Document 1656 of 2026, direct-market users no longer follow the government's fixed TOU schedule; TOU prices are formed by the market. Agency-purchasing users still follow the government-optimized periods and floating ratios.

### 2.6 Power factor, reliability and funds

- **Power-factor adjustment**: assessed on power factor, surcharged below standard and discounted above it; tiers and ratios follow provincial rules;
- **High-reliability supply fee**: multi-circuit and dual-supply users, charged by capacity or project investment;
- **Captive-plant system standby fee**: paid when connected to the grid and requiring system reserve;
- **Government funds and surcharges**: water conservancy, resettlement, renewable and others; scope and standard follow finance and pricing documents.

### 2.7 Four changes in 2026

1. **TOU reconstruction**: fixed schedules exit gradually; market users follow spot prices;
2. **Capacity price expansion**: coal stabilizes, standalone storage converts under Document 114;
3. **System costs made explicit**: system operation fees rise, and allocation disputes on the user side grow;
4. **Retail pass-through**: packages move from "fixed spread" to "market-linked + sharing"; comparison must look at scenarios.

---

## 3. Seven-Step Bill Teardown

### 3.1 Step 1: five questions when reading a bill

1. Which province, which grid service area?
2. User category and voltage level?
3. Catalogue, agency purchasing or market?
4. Does the billing month cross a policy effective date?
5. Two-part or single-part? What basis is the basic charge on?

### 3.2 Step 2: itemize

| Item | Calibre | Frequent problem |
|---|---|---|
| Energy charge | TOU kWh × TOU price, or mid/long-term + spot | Treating agency price as market price |
| T&D charge | kWh × voltage-level T&D price | Missing the capacity/demand part |
| Basic charge | Capacity × capacity price, or demand × demand price | Counting energy only, no basic charge |
| System operation fee | kWh × system operation standard | Confused with the T&D price |
| Funds and surcharges | kWh × each surcharge standard | Summarizing all with one number |
| Power-factor adjustment | Surcharge/discount from power factor | Ignoring power factor |
| High-reliability supply fee | By capacity or project investment | Missed for multi-supply users |
| Taxes | VAT etc., usually inside the price | Mixing tax-inclusive and tax-exclusive |

> Line loss is generally not a separate line; it is already inside the T&D price. If a bill shows a separate line-loss item, first confirm whether it is a cross-province or agency-purchasing calibre, and do not add it on top of the T&D charge. See §2.1 for the tax calibre.

### 3.3 Step 3: recompute

Use `bill_breakdown` in `tools/bill.py` to recompute by item, and check at least three things:

- Does total kWh match the meter reading?
- Do TOU kWh match the period split?
- Does the basic-charge basis (kVA or kW) and declared value match the filing?

### 3.4 Step 4: find anomalies

| Anomaly | Typical sign | Check |
|---|---|---|
| Basic charge jumps | Demand above 105% or declared value cut too aggressively | The day of maximum demand and the overrun size |
| Power-factor surcharge | Reactive compensation switching failed, light night load | Power-factor curve and capacitor status |
| TOU kWh misaligned | Old schedule still used after a period change | Policy effective date vs metering periods |
| Funds overcharged | Relief policy not applied | User category and relief document |
| Agency price abnormal | Monthly allocation items fluctuate | The agency purchasing price disclosure table |
| Installed capacity too large | Basic charge persistently above the demand method | Run the three-method comparison |
| Dual feeders double counted | Two feeders billed separately without aggregation | Supply scheme and metering points |
| Retroactive adjustment missing | Price change crosses months | Adjustment items and periods |

### 3.5 Step 5: compare options

On the same load curve compare: charging method (capacity / contracted demand / actual demand), declared value, TOU package, retail package, shiftable-load plan. Comparison must use the same calibre: same period, same common items, same load.

### 3.6 Step 6: file

- Contracted-demand changes usually require 5 working days' notice;
- Charging-method changes usually require 15 working days' notice;
- A declared value below 40% of the sum of transformer and high-voltage motor capacity is approved at 40%;
- Two or more feeders are computed separately and aggregated.

These lead times, the 40% floor and the dual-feeder calibre all follow the provincial implementation rules; some provinces also limit the number of changes per period, so the national framework is not a nationwide statutory deadline.

### 3.7 Step 7: track

Track at least three months after filing: actual maximum demand, overrun count, power factor, month-on-month bill. Recompute the declared value early when load growth or maintenance plans change.

### 3.8 Inputs and outputs

Input contract:

- Province, voltage level, user category, price channel, billing period;
- 12 months (or a representative month) of 96-point load and the timing of maximum demand;
- Energy prices (TOU or flat), T&D, system operation, funds, demand/capacity prices, power-factor standard;
- Transformer capacity, contracted demand, actual maximum demand, dual-feeder status.

Output fields:

- Itemized bill, total, average price, energy share;
- The three basic-charge methods and the optimal declared value;
- Annual package cost and scenario range;
- Daily/annual revenue from shiftable load and the power required;
- Conclusion and uncertainty (policy, load, price).

---

## 4. Basic Charge and Filing

### 4.1 The three methods

```
By capacity:     basic charge = capacity price (CNY/kVA·month) × transformer capacity (kVA)
By contract:     basic charge = demand price (CNY/kW·month) × (declared + 2 × max(actual − 1.05×declared, 0))
By actual:       basic charge = demand price × actual maximum demand
```

### 4.2 Closed-form optimal declared value

Let demand price p, actual maximum demand A, threshold k = 1.05, overrun multiplier m = 2:

```
charge(D) = p × (D + m × max(A − kD, 0))
```

When D ≥ A/k, charge = pD and rises with D; when D < A/k, charge = p(2A − (mk − 1)D) and falls as D rises. Hence the optimum:

```
D* = max(40% floor, A / 1.05), and no more than transformer capacity
```

Intuition: declare "actual peak ÷ 1.05" so the doubling is not triggered; declaring higher is wasted, declaring lower triggers the 2× overrun.

### 4.3 Three-method comparison

| Scenario | Tendency |
|---|---|
| Stable load, high transformer utilization (>80%) | Capacity charging usually cheaper |
| Transformer oversized, peak far below capacity | Contracted demand cheaper |
| Occasional, controllable peaks | Actual maximum demand may be cheaper |
| Peak growing steadily | Keep 5%–10% headroom in contracted demand to avoid frequent overruns |

### 4.4 Bigger installed capacity is not better

Installed capacity drives the basic charge, reliability fees and expansion investment. Engineering needs margin; financially compute "monthly cost of 1 extra kVA × 12 × life". If storage clips the peak, compute the post-clip maximum demand first and then decide the installed capacity; **never install large first and rely on storage to cut the basic charge** — the reversed order locks in the cost.

### 4.5 Common errors

- Multiplying transformer kVA directly by the demand price (unit mismatch);
- Comparing unit prices without comparing the charging basis;
- Ignoring the 105% doubling and declaring too low;
- Ignoring the 40% floor and computing an optimum that cannot be filed;
- Counting only one of two feeders;
- Spreading the basic charge into a "per-kWh cost" and comparing it directly with a single-part tariff.

---

## 5. TOU Pricing and Load Shifting

### 5.1 Validate the period table first

Before any TOU calculation, validate the period table: covers 0–24 h, no overlap, no gap, and period names map one-to-one to prices. `validate_periods` in `tools/tariff.py` raises directly on a gap or overlap.

Period table used in the examples:

| Period | Time | Hours | Price (CNY/kWh, grade D) |
|---|---|---|---|
| Valley | 00–08, 23–24 | 9 | 0.30 |
| Flat | 08–10, 12–18, 21–23 | 10 | 0.62 |
| Peak | 10–12, 18–19, 20–21 | 4 | 1.05 |
| Critical | 19–20 | 1 | 1.26 |

### 5.2 TOU cost and structure

For a given load curve, TOU cost = Σ kWh in each period × each period price. Look at three things: total cost, average price, and the kWh and cost share of each period. **The same average does not mean the same structure**: a user with a high valley share is less sensitive to peak price rises; a user with a high peak share sees the critical-peak uplift amplified.

### 5.3 Load shifting

Move interruptible/shiftable load from expensive periods to cheap ones; revenue = energy moved × (source price − target price). Constraints:

- The process window allowed for moving (not all load can run at night);
- Maximum power and ramping limits;
- The shift must not raise demand and hence the basic charge;
- The price gap must cover start/stop and quality losses.

`tariff.shift_energy` allocates greedily from the most expensive source to the cheapest target, which is optimal when interval capacities are independent; it performs price arbitrage only and does not judge process feasibility.

### 5.4 Division of labour with storage

- This skill: "how much to move, how much is saved, is the power enough";
- EMS skill: "how much the battery charges in each interval, how SOC and reserve are kept";
- If storage is used to clip the peak and lower demand, write the demand cap into the EMS constraints; it cannot be corrected afterwards.

### 5.5 After the fixed TOU schedule exits

For direct-market users, TOU prices follow spot formation and historical peak-valley spreads cannot be extrapolated directly. Annual studies should use scenario prices (high / medium / low) and compare the "TOU package" and the "market-linked package" on the same load curve.

---

## 6. Power Factor and Surcharges

### 6.1 Power-factor adjustment

A power factor below standard is surcharged and above standard is discounted. The tool uses a simplified two-segment calibre:

```
Below 0.9: for each 0.01 below, surcharge 0.5% of the energy-side subtotal, capped at 15%
Above 0.9: for each 0.01 above, discount 0.15% of the energy-side subtotal, capped at 7.5%
```

Provincial rules often use tiers (e.g. different ratios for 0.85–0.9 and 0.8–0.85); verify the provincial "power-factor adjustment measure" before quoting. **The power-factor base** also differs by province: this skill defaults to the energy-side subtotal (energy + T&D + system operation + funds). If the province assesses energy charge only, pass `pf_base` explicitly.

> The two-segment ratios above are an illustrative calibre, not an official standard of any province. Formal work must replace the parameters in `bill.py` with the provincial tier table; never present 0.5%/0.15% as a national rule.

### 6.2 High-reliability supply fee and standby fee

- Multi-circuit and dual-supply users are charged by capacity or project investment, common in data centres, hospitals and chemicals;
- Captive plants connected to the grid and requiring system reserve pay the standby fee;
- These two are often missed but are non-trivial in large industrial bills.

### 6.3 Funds and surcharges

National major water conservancy construction fund, large/medium reservoir resettlement support fund, renewable energy price surcharge and others. **Never summarize all users with one national number**: scope, standard and relief policies can all differ.

### 6.4 Common errors

- Treating the power-factor base as "total bill" (including the basic charge);
- Applying the 0.9 standard to every province;
- Sizing reactive compensation as a transformer ratio without switching checks;
- Ignoring the high-reliability supply fee and standby fee;
- Treating funds as a "tax" and counting them twice.

---

## 7. Retail Packages and Agency Purchasing Comparison

### 7.1 Three common packages

| Package | Pricing | Risk borne by user | Suits |
|---|---|---|---|
| Fixed price | Fixed CNY/kWh for year/quarter | Almost no price risk, but includes a risk premium | Stable budget, predictable load |
| TOU price | Peak/flat/valley price table | Period-structure risk | Load matches the TOU periods |
| Market-linked | Spot/monthly average × share + adder, with cap | Price volatility risk | Users who can bear volatility and seek a low average |

### 7.2 Comparison calibre

1. Compare **energy only**: T&D, system operation, funds and the basic charge are common items, added back separately;
2. Same load curve, same annual day count, same tax treatment;
3. For market-linked, read the **share ratio, adder, cap and floor** — four parameters;
4. For fixed price, confirm whether green premium and deviation assessment are included;
5. Retailer credit and performance guarantees are part of the package; never look at price alone;
6. Confirm the tax and line-loss calibre: whether the package price, T&D price and funds use the same basis, and whether line loss is inside the T&D or procurement price.

### 7.3 Scenarios and break-even

A market-linked bill is a linear function of price (between cap and floor). Given a baseline market curve, compute "by what percentage the market average must rise to equal the fixed price" — that percentage is the risk threshold for the choice. If the user judges future rises below the threshold, choose linked; above it, choose fixed.

### 7.4 Retail-side risks

- Retail-wholesale inversion: a fixed-price contract loses in a rising market; retailer-side pricing, deviation and guarantee issues are covered in [Retail Electricity Risk §7–§9](../retail-electricity-risk/SKILL_EN.md);
- Deviation assessment: actual consumption drifting from the declared profile may be passed through;
- Performance security: if the retailer defaults, the user may be forced back to agency purchasing;
- Green power and certificates: whether included and who owns the certificates must be written down.

### 7.5 Common errors

- Comparing an "energy unit price" directly with an "end-user price";
- Ignoring common items and concluding "the package is 30% cheaper";
- Looking only at the baseline scenario, not ±20% price movements;
- Treating market-linked as "certainly cheaper";
- Not checking the retailer's performance capability.

---

## 8. Worked Examples (synthetic data, grade D)

> Reproduce: `python skills/tariff-bill-optimization/tools/selftest.py` (cases A–H). All data are grade-D synthetic and correspond to no real user or province; formal work must substitute provincial documents and real bills.

### 8.1 Bill recomputation

A 10 kV industrial/commercial user, 200 MWh/month, contracted maximum demand 1,000 kW, demand price 40 CNY/kW·month, energy 0.42 CNY/kWh, T&D 0.15 CNY/kWh, system operation 0.068 CNY/kWh, funds 0.02 CNY/kWh:

| Item | Calculation | Amount |
|---|---|---|
| Energy charge | 200,000 × 0.42 | 84,000.00 |
| T&D charge | 200,000 × 0.15 | 30,000.00 |
| System operation fee | 200,000 × 0.068 | 13,600.00 |
| Funds and surcharges | 200,000 × 0.02 | 4,000.00 |
| Basic charge | 1,000 × 40 | 40,000.00 |
| Total | — | 171,600.00 |
| All-in per kWh | 171,600 ÷ 200,000 | 0.858 |

Energy accounts for only **48.95%**; T&D, system operation, funds and the basic charge together are **51.05%**. Watching the energy price alone underestimates the basic charge and common items.

### 8.2 Three basic-charge methods

A user with a 1,600 kVA transformer and monthly maximum demand 1,150 kW; capacity price 32 CNY/kVA·month, demand price 40 CNY/kW·month:

| Method | Basis | Monthly basic charge |
|---|---|---|
| By capacity | 1,600 kVA × 32 | 51,200.00 |
| By contracted demand (declared 1,095.24 kW) | 1,150 ÷ 1.05 | 43,809.52 |
| By actual maximum demand | 1,150 kW × 40 | 46,000.00 |

Contracted demand is cheapest, **7,390.48 CNY/month** below capacity charging. Declaring 1,095.24 kW keeps the actual peak just inside the 105% line, so no doubling is triggered; declaring 1,000 kW gives `over = 100 kW` and the basic charge becomes 40 × (1,000 + 200) = 48,000 CNY, which is more expensive.

### 8.3 Annual declaration optimization

For the same user, the 12 monthly maximum demands are scaled by seasonal factors; the peak occurs in August (1,311 kW):

| Method | Annual basic charge |
|---|---|
| By capacity | 614,400.00 |
| Monthly-optimized contracted demand | 500,304.76 |
| By actual maximum demand | 525,320.00 |
| Declaring 1,311 kW all year | 629,280.00 |

Monthly optimization pays **128,975.24 CNY/year** less than the "one peak month for the whole year" approach. The point is not a complex formula but **recomputing the declared value from each month's peak**; most users adjust once a year, and that is where the waste lies.

### 8.4 Power-factor adjustment

For the same user the energy-side subtotal is 131,600 CNY (energy + T&D + system operation + funds):

| Power factor | Adjustment ratio | Adjustment amount |
|---|---|---|
| 0.85 | +2.5% | +3,290.00 |
| 0.92 | −0.3% | −394.80 |
| Difference | — | 3,684.80 |

Raising the power factor from 0.85 to 0.92 alone changes the monthly bill by **3,684.80 CNY**, about 44,000 CNY annualized. Check reactive compensation switching and light night load before discussing tariffs.

### 8.5 Retail package comparison

Annual consumption 6,702,688.50 kWh; three packages on the same load curve (energy only):

| Package | Annual energy cost | Average price (CNY/kWh) |
|---|---|---|
| Fixed 0.60 | 4,021,613.10 | 0.6000 |
| TOU package | 4,509,570.56 | 0.6728 |
| Market-linked (100% pass-through + 0.05) | 3,681,791.55 | 0.5493 |

In the baseline scenario the market-linked package saves **339,821.55 CNY/year** versus fixed. But with all market prices 20% higher, its bill rises to **4,351,122.98 CNY**, which is **329,509.88 CNY** more than fixed; with prices 20% lower it falls to **3,012,460.13 CNY**. The break-even point is a market rise of about **10.15%** — that threshold matters more than "which is cheaper today".

### 8.6 Shiftable load

An industrial daily load of 19,275 kWh costs 12,968.225 CNY/day, with peak-period energy at 21.78%. Move 1,600 kWh from peak to valley (maximum power 1,300 kW):

| Metric | Before | After |
|---|---|---|
| Daily cost | 12,968.225 | 11,768.225 |
| Daily saving | — | 1,200.00 |
| Annual saving (365 days) | — | 438,000.00 |

Unit revenue = 1.05 − 0.30 = 0.75 CNY/kWh. If the process allows only 800 kWh, revenue halves proportionally; if the shift raises maximum demand, subtract the basic-charge increase.

### 8.7 How to read

- Itemize the bill before optimizing: the basic charge, power factor and common items often offer more room than the energy unit price;
- The basic-charge solution is the closed form "declared value ÷ 1.05"; the difficulty is monthly recomputation and load forecasting;
- Package comparison must use the same calibre, same curve and scenarios; the baseline ranking can flip within ±20%;
- Load-shifting revenue = price gap × energy, but must pass the process, power and demand gates first;
- All numbers are grade-D synthetic data and cannot be used directly for real users.

### 8.8 Runnable instance: Jiangsu C&I storage

The methods above are packaged as a runnable "province + user + bill calibre" instance: [`instances/jiangsu-ci-storage-2026-11/`](instances/jiangsu-ci-storage-2026-11/README.md). Feed it a 12-month × 96-point load (`data/load_demo.csv`) plus `instance.json`, and it runs monthly bills, the three basic-charge methods, declaration recomputation and storage peak shaving in one pass:

- **Declaration and storage accounted separately**: first the saving from "recompute the declaration only", then the net saving from "storage shaving − degradation − O&M"; declaration optimization is never booked as storage revenue;
- **The declaration is an ex-post upper bound**: `D* = max(40% floor, A/1.05)` uses the month's actual peak; in practice it must be replaced by a load forecast;
- **Report payback honestly**: the demo uses 500 kW / 1,000 kWh and 12% shaving, yielding 70,100 CNY/year of storage net savings against 900,000 CNY capex, a simple payback of 12.84 years — the long payback is a strategy choice, not a calculation error.

Tariff, T&D, funds and demand parameters are all grade-D placeholders; the current Jiangsu documents are not closed in this library, so the whole table must be replaced before drawing conclusions.

---

## 9. Filing and Change Operations

### 9.1 Time windows

| Matter | Typical lead time | Note |
|---|---|---|
| Contracted-demand change | 5 working days | Applied monthly, effective next month |
| Charging-method change | 15 working days | Applied quarterly; some provinces limit the count |
| Installed-capacity increase | Per supply scheme | Involves design, construction and acceptance |
| Agency purchasing exit/entry | Per provincial rules | Must align with market contracts |

Lead times and the number of changes follow the provincial implementation rules; the table is a common calibre, not a nationwide statutory deadline.

### 9.2 Materials and calibres

- Application form, business licence, electricity account number;
- Maximum demand and load curves for the last 3–12 months;
- Transformer and high-voltage motor capacity list (for the 40% floor);
- Supply scheme and metering points for dual feeders;
- Reason and calculation sheet for the charging-method change.

### 9.3 Post-change review

- Check the declared value, charging method, overrun and power factor in the next bill;
- Track actual maximum demand for three consecutive months; if close to the 105% line, raise the value early;
- Lower the value when load falls, but never below the 40% floor;
- Keep the receipt and bill of every filing for dispute handling.

---

## 10. Engineering Review Checklist

### 10.1 P0: affects correctness

| Check | Pass criterion |
|---|---|
| Province and service area | Tariff, periods and power factor all from provincial documents |
| Voltage level and user category | Consistent with the bill |
| Price channel | Catalogue / agency / market never mixed |
| Billing period | Policy effective dates and price-change months handled |
| Units | kVA, kW, kWh, CNY/kWh never mixed |
| Basic-charge basis | Capacity or demand; declared value traceable |
| 105% and 40% floor | Rules consistent with the province |
| TOU periods | Cover 24 h, no overlap, consistent with policy |
| Power-factor base | Consistent with the provincial assessment |
| Dual feeders | Separate or aggregated per the rules |
| Package calibre | Energy only; common items added back |
| Line-loss calibre | Already inside the T&D price; not added twice |
| Tax-inclusive/exclusive | Calibre unified; tax rate and invoice type verified |

### 10.2 P1: affects maintainability

| Check | Pass criterion |
|---|---|
| Externalized parameters | Prices, periods and standards not hard-coded |
| Version management | Policy version and input snapshot saved per run |
| Scenario analysis | At least high / medium / low |
| Reproducible | Same inputs produce the same bill |
| Audit trail | Every number traces to a bill or document |
| Filing ledger | Declared value, effective month, receipts complete |

### 10.3 Red lines

- Never present a not-yet-effective or draft rule as executed;
- Never substitute another province's price table;
- Never hide the basic charge and assessments and report only a low energy price;
- Never promise a user "a certain amount of savings";
- Never tamper with load and demand data.

---

## 11. Code Map and Self-Test

| File | Purpose |
|---|---|
| `tools/bill.py` | Bill items, three basic-charge methods, power-factor adjustment |
| `tools/tariff.py` | Period-table validation, TOU cost, load shifting |
| `tools/demand.py` | Optimal declared value, three-method comparison, annual optimization |
| `tools/retail.py` | Fixed / TOU / market-linked package comparison |
| `tools/curves.py` | Synthetic load, TOU prices and market curves |
| `tools/selftest.py` | Locks all worked examples A–H in the text |

Run:

```bash
python skills/tariff-bill-optimization/tools/selftest.py
```

A green self-test means the worked examples match the code; when policy parameters change, modify `curves.py` or the call parameters first, then synchronize the numbers in the text.

---

## 12. Frequently Asked Questions

**Q1: A user asks "is 0.8 CNY/kWh expensive?" How to answer?**
Ask for the bill first: voltage level, two-part or single-part, basic-charge share, power factor, common items. 0.8 CNY/kWh may be energy 0.42 + common items 0.24 + basic charge 0.14; whether it is expensive depends on the structure and comparable users, not on one number.

**Q2: Capacity charging or demand charging — which is cheaper?**
Compute the three methods on the same load. With stable load and high transformer utilization, capacity is often cheaper; with an oversized transformer, contracted demand is cheaper. Declare "actual peak ÷ 1.05", subject to the 40% floor.

**Q3: Is a market-linked package always cheaper than a fixed price?**
No. It may be cheaper in the baseline, but a price rise reverses it. Compute the break-even rise: about 10.15% in this example. Above it, choose fixed or a capped package.

**Q4: How much is the surcharge at power factor 0.85?**
Under this simplified calibre, 2.5% of the energy-side subtotal (0.5% per 0.01 below). Provincial rules may use tiers; check the provincial measure. Fix reactive compensation before discussing tariffs.

**Q5: Can storage peak-shaving reduce the basic charge?**
Yes, but the demand cap must be written into the dispatch constraints, and the declared value and the 105% rule must be checked. Storage cannot correct demand "afterwards"; compute the post-clip maximum demand first, then set the declared value and installed capacity.

---

## 13. Sources and Maintenance

### 13.1 Main sources

| Type | Content |
|---|---|
| Knowledge notes | [Tariff system](../../knowledge/中国电价制度谱系-2026-11.md), [current policy and verification](../../knowledge/中国电价现行政策与查证-2026-11.md), [tariff history](../../knowledge/中国电价史-2026-11.md), [international comparison](../../knowledge/国际电价比较-方法与模板-2026-11.md) |
| Policy source texts | NDRC Pricing Department, provincial DRC/energy bureaus, grid agency-purchasing disclosures; document numbers and links in the policy list |
| Provincial samples | [Provincial market status table](../../knowledge/省级市场状态表-2026-11.md), [provincial policy list](../../knowledge/省级政策列表-2026-11.md) (grades B/C, to be verified) |
| Worked examples | All grade-D synthetic data generated by `tools/curves.py` |

### 13.2 Maintenance rules

- When tariff, periods, power factor or funds change, update the knowledge note first, then the `tools/` parameters and `selftest.py`, and finally the Chinese and English skill texts;
- Provincial values must carry document number, effective date and source grade;
- Drafts for comment must never be written as executed;
- Review provincial samples and agency-purchasing prices quarterly; re-check P0 items monthly and synchronize with the knowledge hub.

### 13.3 Disclaimer

This text and the tools are demonstrations only and constitute no investment advice, quotation commitment or legal opinion. Real user bill optimization must use the latest provincial documents, actual bills and load data, and be reviewed by qualified professionals.

- **Price-driver routing**: quantity ([weather and power trading](../../knowledge/气象与电力交易-2026-11.md)), price ([fuel and power trading](../../knowledge/燃料与电力交易-2026-11.md)), deliverability ([inter-provincial trading](../../knowledge/省间与跨区交易-2026-11.md) §5.5-5.6). For "why is this interval expensive", check quantity -> price -> constraint -> superposition; see the [golden Q&A](../../knowledge/黄金问答集-2026-11.md) section F (Q29-Q38) for regression questions.
