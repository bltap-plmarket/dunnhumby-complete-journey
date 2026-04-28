# Investigation Findings — narrative companion

> **What this is.** The numbers and observations gathered during the data
> profiling and ETL phase, written out so a Power BI build skill can use
> them as: validation targets, headline KPIs to feature, top-N priors for
> visuals, and warnings about pitfalls. Pairs with `investigation_findings.json`.
>
> **Generated:** 2026-04-28 from the parquet output of `scripts/build_parquet.py`.

---

## 1. The headline story (one paragraph)

Across 2 years and 2,500 households, **1,459 households (58%) grew their
spend year-over-year and 891 (36%) shrank**. Total revenue is **\$8.06M
net of discounts** (\$9.51M gross, ~15% discount rate). The retailer is
winning more households than it's losing — but the same high-volume staple
categories (Soft Drinks, Beef, Cheese, Fluid Milk) drive both the growth
and the decline. The story is **engagement divergence across the same
shelf**, not categories rising or falling on their own.

Marketing is murky: campaign-exposed households spend **4.4× more** than
unexposed ones, but this is almost certainly **selection bias** — campaigns
are sent to active customers, so the gap reflects who got picked, not what
the marketing did. The dashboard's marketing page must surface this
caveat or it will mislead.

---

## 2. Validation targets (post-load checks)

If a Power BI load doesn't match these, something broke.

| Table | Rows | Notes |
|---|---:|---|
| `fact_transactions` | 2,595,732 | 2,500 households · 92,339 products · 582 stores · 276,484 baskets |
| `fact_causal_weekly` | 2,049,187 | Pre-aggregated 18× from 36.8M source rows |
| `fact_coupon_redemption` | 2,318 | 434 households redeemed |
| `fact_campaign_received` | 7,208 | 1,584 households reached |
| `dim_household` | 2,500 | PK unique |
| `dim_product` | 92,353 | PK unique |
| `dim_date` | 711 | DAY 1..711 |
| `dim_store` | 582 | |
| `dim_campaign` | 30 | 19 TypeB · 6 TypeC · 5 TypeA |
| `dim_coupon` | 1,135 | 556 actually redeemed |
| `bridge_coupon_product` | 119,384 | M:N |

---

## 3. Headline KPIs (anchor card visuals to these)

| KPI | Value |
|---|---:|
| Total Sales (net) | **\$8,057,463** |
| Gross Sales | **\$9,506,002** |
| Discount Rate | **15.2%** |
| Active Households | **2,500** |
| Total Baskets | **276,484** |
| Avg Basket Value | **\$29.14** |
| Spend per Household | **\$3,223** |
| Households Growing | **1,459 (58.4%)** |
| Households Declining | **891 (35.6%)** |

These are the numbers a viewer should see in the first second of opening
the dashboard.

---

## 4. Household trend cohort (the central slicer)

`HH_Trend` is **already computed** in `dim_household`. Distribution:

| Trend | Households | Avg Y1 Spend | Avg Y2 Spend |
|---|---:|---:|---:|
| Growing | 1,459 | \$1,345 | \$2,227 |
| Declining | 891 | \$1,591 | \$1,008 |
| Flat | 126 | \$2,067 | \$2,083 |
| Lost | 21 | \$251 | \$0 |
| New | 3 | \$0 | \$465 |
| Inactive | 0 | — | — |

**Recommendation:** make this a tile slicer at the top of every page.
Every visual should naturally cross-filter on it.

---

## 5. Category winners & losers (Pages 2)

**Pre-computed for the storyboard.** Filtered to commodities with ≥\$5K Y1 spend.

### For the Growing cohort — top 5 by \$ delta:

| Commodity | Y1 | Y2 | Δ\$ | Δ% |
|---|---:|---:|---:|---:|
| COUPON/MISC ITEMS ⚠ | \$146,364 | \$282,172 | **+\$135,808** | +93% |
| BEEF | \$77,596 | \$122,724 | +\$45,128 | +58% |
| SOFT DRINKS | \$80,252 | \$121,835 | +\$41,583 | +52% |
| FLUID MILK PRODUCTS | \$51,244 | \$83,445 | +\$32,201 | +63% |
| CHEESE | \$47,674 | \$75,136 | +\$27,461 | +58% |

### For the Declining cohort — top 5 by \$ delta:

| Commodity | Y1 | Y2 | Δ\$ |
|---|---:|---:|---:|
| COUPON/MISC ITEMS ⚠ | \$96,669 | \$62,610 | -\$34,059 |
| SOFT DRINKS | \$65,384 | \$39,117 | -\$26,267 |
| BEEF | \$56,147 | \$34,648 | -\$21,499 |
| CHEESE | \$33,577 | \$20,233 | -\$13,345 |
| FLUID MILK PRODUCTS | \$35,515 | \$22,729 | -\$12,787 |

**Critical observation.** The same five commodities appear at the top of
both lists. This is the actual insight: it's not that some categories are
booming and others dying — it's that the **same categories diverge between
engaged and disengaged households**. The dashboard narrative should
emphasize the divergence, not call out individual commodities as winners
or losers in isolation.

⚠ "COUPON/MISC ITEMS" looks suspect — it's the #1 commodity by total
sales (\$640K) and also moves the most in both directions. It may not be
a true product category (could be a placeholder for coupon ledger
entries). Investigate before featuring.

---

## 6. Demographic spend (Page 3)

Coverage: **801 of 2,500 households (32%)** have demographics. **Filter
`HasDemographics = TRUE` on every demographic visual** or the cuts
are computed over households with no demographic data.

### Avg total spend per household by income bracket:

| Income | n | Avg Spend |
|---|---:|---:|
| Under 15K | 61 | \$5,560 |
| 15-24K | 74 | \$4,097 |
| 25-34K | 77 | \$4,938 |
| 35-49K | 172 | \$4,802 |
| 50-74K | 192 | \$5,702 |
| 75-99K | 96 | \$5,823 |
| 100-124K | 34 | \$5,928 |
| 125-149K | 38 | \$7,912 |
| 150-174K | 30 | \$8,395 |
| 175-199K | 11 | \$8,548 |
| 200-249K | **5** | \$5,726 ⚠ |
| 250K+ | 11 | \$10,790 |

**Pattern:** spend rises with income, with a clear inflection above
\$125K and the highest bracket (\$250K+) at \$10,790 per household. The
dip at 200-249K is **n=5** — sample too small; hide or footnote.

The custom income sort order is in `storyboard.json`.

### Other demographic distributions (within 801 surveyed):

- **Age** (top): 45-54 (288), 35-44 (194), 25-34 (142)
- **Household composition** (top): 2 Adults No Kids (255), 2 Adults Kids (187), Single Female (144)
- **Household size**: mostly 1 or 2 (255 and 318)
- **Kids**: 70% have None/Unknown
- **Homeowner**: 504 owners, 233 unknown, 42 renters

---

## 7. Marketing impact (Page 4) — handle with care

### The proper lift number (diff-in-diff) is +\$0.33

Computed from `agg_household_campaign_lift.parquet` — for each (household,
campaign), pre-window = 28 days before `START_DAY`, post-window = 28 days
from `START_DAY`. Restricted to campaigns with a complete post-window in
the observation period.

| Cohort | Avg Pre Spend | Avg Post Spend | Avg Δ |
|---|---:|---:|---:|
| Exposed (received this campaign) | \$267 | \$268 | **\$2** |
| Unexposed control | \$127 | \$128 | **\$1** |
| **Diff-in-diff** | | | **+\$0.33** |

**The honest answer to Q5: direct marketing produced essentially zero
short-term spend lift in this dataset.** The 4.4× ratio between exposed
and unexposed *cohorts* (next sub-section) is almost entirely selection
bias — campaigns are sent to households who were already buying more.

The dashboard should lead with this diff-in-diff number, not the raw
ratio.

### Cohort-level (selection-confounded) numbers


| Metric | Value |
|---|---:|
| Households reached by ANY campaign | **1,584 of 2,500 (63.4%)** |
| Households who redeemed ANY coupon | **434 of 2,500 (17.4%)** |
| Redemption rate among reached HH | **27.4%** |

### Exposed vs unexposed avg total spend:

| Cohort | n | Avg Y1 | Avg Y2 | Avg Total |
|---|---:|---:|---:|---:|
| Exposed | 1,584 | \$2,050 | \$2,442 | **\$4,492** |
| Unexposed | 916 | \$435 | \$594 | **\$1,029** |
| Ratio | | | | **4.37×** |

**This 4.37× ratio is NOT a clean lift number.** The retailer's targeting
selects active customers — exposed households were already higher-spend
*before* the campaign. The dashboard should:

1. Lead with the **funnel** (2,500 → 1,584 reached → 434 redeemed) which
   is descriptive, not causal.
2. Display the spend ratio with an explicit "selection bias" caveat in
   the visual subtitle.
3. For a more honest lift estimate, build a per-household pre/post
   comparison around campaign windows (DAX pattern in `measures.dax` /
   `docs/SCHEMA.md` §11.5). That's a v2 feature.

### Campaign portfolio:
- 30 campaigns total (19 TypeB, 6 TypeC, 5 TypeA)
- Earliest start: DAY 224; latest end: DAY 719
- **Campaign 24 ends DAY 719 > observation end DAY 711** — drop from
  post-campaign analyses (`Extends_Past_Observation = TRUE` flag).
- TypeA and TypeC have small samples (5 and 6) — be careful averaging
  by type.

---

## 8. Department spend concentration

| Department | Sales | Share |
|---|---:|---:|
| GROCERY | \$4,093,814 | **51%** |
| DRUG GM | \$1,055,358 | 13% |
| PRODUCE | \$557,452 | 7% |
| MEAT | \$548,787 | 7% |
| KIOSK-GAS | \$544,222 | 7% |
| MEAT-PCKGD | \$412,437 | 5% |
| DELI | \$260,867 | 3% |

The top 3 departments are 71% of total sales. KIOSK-GAS at 7% is notable
— gas-station purchases are a meaningful slice. Consider whether they
should be featured separately or grouped with non-merchandise.

---

## 9. Promotion footprint (Page 5)

- **2.05M product × week combinations** in `fact_causal_weekly`.
- `display` codes: `0,1,2,3,4,5,6,7,9,A` (treat as nominal).
- `mailer` codes: `0,A,C,D,F,H,J,L,P,X,Z` (treat as nominal).
- Use `OnDisplay_AnyStore` and `InMailer_AnyStore` booleans for clean
  visuals — they collapse the codes into a usable Yes/No signal.
- `DisplayShare` and `MailerShare` (0..1) work for "promo intensity"
  visuals like a scatter plot of share vs sales.

---

## 10. Known data-quality landmines

These are baked into the parquet output so the report doesn't trip on them:

| Issue | Resolution |
|---|---|
| Discounts negative in source | ABS() applied; columns positive in `fact_transactions` |
| QUANTITY max is 89,638 | Cap at p99 for visuals — bulk/weighted items |
| 32% demographic coverage | Use `HasDemographics = TRUE` filter on demographic visuals |
| Campaign 24 extends past observation | Use `Extends_Past_Observation = FALSE` filter |
| Placeholder categories ("NO COMMODITY DESCRIPTION") | `Has_Real_Category = FALSE` flag — filter on category visuals |
| Small TypeA/C campaign samples | Don't average without showing N |
| Marketing 4.4× ratio is selection bias | Visual subtitle must caveat |
| "COUPON/MISC ITEMS" suspicious | Investigate; may not be merchandise |
| 200-249K income n=5 | Hide or footnote |

---

## 11. Five things to feature on Page 1 (the opening view)

If a viewer only sees one page, these are the takeaways to land:

1. **\$8M total revenue, ~15% off net of discounts** (gross to net story).
2. **1,459 households grew, 891 declined** (the engagement-divergence headline).
3. **Y2 vs Y1 trajectory line** (helps identify seasonality vs trend).
4. **Scatter of HH_Spend_Y1 vs HH_Spend_Y2 colored by HH_Trend** (this is
   the single most informative visual in the dashboard — shows the cohorts
   in one chart).
5. **A ranked table of the 25 households with the largest \$ spend deltas**
   — anchors abstract trends to concrete examples.

---

## 12. Final guidance for the build skill

- **Start with the storyboard** (`storyboard.json`). It's been tuned to
  the Kaggle research questions and pre-filtered for known landmines.
- **Use the validation targets** as load checks. Mismatch = bug.
- **Don't reinvent measures.** They're in `measures.dax` and `_model.json`.
- **Keep the marketing page humble.** Show the funnel, label the ratio
  as confounded, and offer a pre/post lift visual as a stretch goal.
- **Honor the demographic filter.** It's the single easiest mistake to
  make and the one that will produce the most-wrong visuals.
