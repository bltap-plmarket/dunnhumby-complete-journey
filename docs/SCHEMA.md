# dunnhumby — The Complete Journey: Schema & Power BI Modeling Handoff

> **Audience.** A peer analyst/engineer who will pick up this dataset in a new
> Claude Code session and continue the research. This document is the entire
> briefing — read top-to-bottom and you should be ready to build the Power BI
> model and start answering the research questions.
>
> **Status as of 2026-04-28.** Repo scaffolded, raw CSVs downloaded to
> `data/raw/` (gitignored), no Power BI work started yet.

---

## 1. How to use this document

1. Skim §2–§3 to orient yourself.
2. Reproduce the data load via §4 if you don't already have the CSVs.
3. Use §5–§7 as the column-level reference while modeling.
4. §8–§10 are the Power BI build plan: schema, joins, M/DAX patterns.
5. §11 maps the Kaggle research questions onto concrete model queries.
6. §12 lists open questions to confirm with the project owner before you
   commit to specific design choices.
7. §13 is the handoff checklist.

---

## 2. Dataset overview

The dunnhumby "Complete Journey" dataset captures **household-level retail
transactions over a ~2-year window for 2,500 frequent shoppers** at a single
retailer. Unlike most public retail data, it includes **all** of each
household's purchases (not just a single category), plus:

- Demographics for ~32% of households
- Direct-marketing campaign exposure history
- Coupon issuance and redemption events
- In-store promotional state (display, mailer) at product × store × week

This combination is unusually rich and lets you study the **causal effect of
direct marketing on household spend and engagement** — which is what the
research questions in §3 push toward.

**Source:** https://www.kaggle.com/datasets/frtgnn/dunnhumby-the-complete-journey
**License:** DbCL-1.0 (Database Contents License)
**Kaggle slug:** `frtgnn/dunnhumby-the-complete-journey`

### Time domain quirk

There are **no real dates**. All temporal columns are integers:
- `DAY` ∈ [1, 711] — sequential day index from start of observation
- `WEEK_NO` ∈ [1, 102] — sequential week index
- Campaign `START_DAY` / `END_DAY` use the same `DAY` index
- One campaign's `END_DAY = 719`, which exceeds the max transaction `DAY = 711` (campaign exposure extends past the observation window — see §7)

You will need to either (a) keep the day-integer space and build a synthetic
calendar, or (b) anchor `DAY = 1` to an arbitrary calendar date for cosmetics.
The dataset itself has no real-world date.

---

## 3. Research questions (from Kaggle)

Verbatim from the dataset page:

1. **How many customers are spending more over time? Less over time? Describe these customers.**
2. Of those customers who are spending more over time, **which categories are growing at a faster rate**?
3. Of those customers who are spending less over time, **with which categories are they becoming less engaged**?
4. **Which demographic factors** (e.g. household size, presence of children, income) appear to affect customer spend? Engagement with certain categories?
5. **Is there evidence to suggest that direct marketing improves overall engagement?**

§11 maps each to a specific modeling approach.

---

## 4. Get the data

Raw CSVs are gitignored. To reproduce locally:

```bash
# one-time: place your Kaggle API token at ~/.kaggle/kaggle.json
#   (token from https://www.kaggle.com/settings -> API -> Create New Token)
pip install --user kaggle
kaggle datasets download -d frtgnn/dunnhumby-the-complete-journey -p data/raw --unzip
```

Resulting tree:

```
data/raw/
├── campaign_desc.csv          540 B   (30 rows)
├── campaign_table.csv          94 KB  (7,208 rows)
├── causal_data.csv            664 MB  (36,786,524 rows)   <- huge, see §10
├── coupon.csv                 2.7 MB  (124,548 rows)
├── coupon_redempt.csv          53 KB  (2,318 rows)
├── hh_demographic.csv          44 KB  (801 rows)
├── product.csv                6.2 MB  (92,353 rows)
└── transaction_data.csv       136 MB  (2,595,732 rows)
```

---

## 5. File inventory & roles

| File | Rows | Role | Grain |
|---|---:|---|---|
| `transaction_data.csv` | 2,595,732 | **Fact (primary)** | One row per product line per basket |
| `causal_data.csv` | 36,786,524 | **Fact (promo state)** | One row per product × store × week |
| `coupon_redempt.csv` | 2,318 | **Fact (event)** | One row per coupon redemption |
| `campaign_table.csv` | 7,208 | **Factless fact / bridge** | One row per (household, campaign) sent |
| `coupon.csv` | 124,548 | **Bridge** | One row per (coupon, product, campaign) — M:N coupon ↔ product |
| `product.csv` | 92,353 | **Dimension** | One row per `PRODUCT_ID` |
| `hh_demographic.csv` | 801 | **Dimension extension** | One row per household with demographics (32% coverage) |
| `campaign_desc.csv` | 30 | **Dimension** | One row per campaign |

---

## 6. Per-table reference

For each table: full column list, semantics, sample values, distincts, and
notes for modeling.

### 6.1 `transaction_data.csv` — Fact_Transactions

**Grain:** one product line item within one basket within one trip.
**Distincts (full file):**
- 2,500 households
- 92,339 products (essentially every product master record — 99.98%)
- 582 stores
- 276,484 baskets
- 711 distinct days
- 102 distinct weeks
- `SALES_VALUE` ∈ [0, 840]
- `QUANTITY` ∈ [0, 89638] (extreme outliers exist — bulk/weighted items)

| Column | Type | Semantics | Notes |
|---|---|---|---|
| `household_key` | int | Anonymized household ID | FK → Dim_Household |
| `BASKET_ID` | int (large) | Anonymized basket / trip ID | Degenerate dim — keep on the fact for basket-level grouping; no separate Dim_Basket needed |
| `DAY` | int [1..711] | Day index of transaction | FK → Dim_Date |
| `PRODUCT_ID` | int | Anonymized product ID | FK → Dim_Product |
| `QUANTITY` | int | Units purchased | Can be very large for weighted products; consider an outlier flag |
| `SALES_VALUE` | decimal | Net amount paid by household for this line | Already net of all discounts (this is the receipt value) |
| `STORE_ID` | int | Anonymized store ID | FK → Dim_Store |
| `RETAIL_DISC` | decimal | Loyalty/retailer discount applied | Stored as **negative** in some rows ("-0.6"); take `ABS()` if you want a positive measure |
| `TRANS_TIME` | int (HHMM) | Time of transaction as a 4-digit clock value (e.g., `1631` = 16:31) | Useful for time-of-day analysis; parse to hour |
| `WEEK_NO` | int [1..102] | Week index | Redundant with `DAY` but useful as join key to Fact_Causal |
| `COUPON_DISC` | decimal | Coupon discount given to household | Negative-signed; `ABS()` for measure |
| `COUPON_MATCH_DISC` | decimal | Manufacturer match portion of coupon discount | Negative-signed |

**Derived "gross" sales** (often useful):
```
GROSS_SALES = SALES_VALUE + ABS(RETAIL_DISC) + ABS(COUPON_DISC) + ABS(COUPON_MATCH_DISC)
```

### 6.2 `causal_data.csv` — Fact_Causal (promotional state)

**Grain:** one row per (`PRODUCT_ID`, `STORE_ID`, `WEEK_NO`).
**Size:** 36.8M rows / 664 MB. **Pre-aggregate before loading** (see §10).

| Column | Type | Semantics | Notes |
|---|---|---|---|
| `PRODUCT_ID` | int | Product on promotion | FK → Dim_Product |
| `STORE_ID` | int | Store running the promo | FK → Dim_Store |
| `WEEK_NO` | int [1..102] | Week index | FK → Dim_Date (week grain) |
| `display` | code | In-store display state. Values observed: `0..9`, `A` | Categorical. `0` = no display. Higher numbers / letters = different placements. Treat as nominal. |
| `mailer` | code | Mailer/circular placement. Values observed: `0, A, C, D, F, H, J, L, P, X, Z` | Categorical. `0` = not in mailer. Letters = different mailer page/section codes. |

**Modeling note.** The dunnhumby docs (when discoverable) describe `display`
and `mailer` as categorical placement codes — they are **not** ordinal. Don't
sum them. Common simplifications:
- `OnDisplay = (display <> '0')`
- `InMailer = (mailer <> '0')`

### 6.3 `coupon_redempt.csv` — Fact_CouponRedemption

**Grain:** one row per redemption event.
**Distincts:** 434 households, 556 coupons, 30 campaigns, `DAY` ∈ [225, 704].

| Column | Type | Semantics | Notes |
|---|---|---|---|
| `household_key` | int | Household redeeming | FK → Dim_Household |
| `DAY` | int | Day of redemption | FK → Dim_Date |
| `COUPON_UPC` | int (large) | Coupon UPC | FK → Dim_Coupon |
| `CAMPAIGN` | int | Campaign the coupon belonged to | FK → Dim_Campaign |

Only a small subset of households ever redeem. Treat redemption as an event
funnel: received campaign → received coupon → redeemed.

### 6.4 `campaign_table.csv` — Fact_CampaignReceived (factless fact)

**Grain:** one row per (household, campaign) the household received.
**Distincts:** 1,584 households (63% of all 2,500), 30 campaigns.

| Column | Type | Semantics |
|---|---|---|
| `DESCRIPTION` | varchar | Campaign type ("TypeA"/"TypeB"/"TypeC"). Redundant with Dim_Campaign. |
| `household_key` | int | FK → Dim_Household |
| `CAMPAIGN` | int | FK → Dim_Campaign |

**Modeling note.** This is a **factless fact** (no measures — its purpose is
to mark which household × campaign pairs occurred). Use it for "households
that received Campaign N" filters and as the basis for the marketing-effect
analysis (§11.5).

### 6.5 `campaign_desc.csv` — Dim_Campaign

**Full table is small enough to inline (30 rows).** All campaigns:

| CAMPAIGN | TYPE | START_DAY | END_DAY | Duration |
|---:|---|---:|---:|---:|
| 26 | TypeA | 224 | 264 | 40 |
| 27 | TypeC | 237 | 300 | 63 |
| 28 | TypeB | 259 | 320 | 61 |
| 29 | TypeB | 281 | 334 | 53 |
| 30 | TypeA | 323 | 369 | 46 |
| 1  | TypeB | 346 | 383 | 37 |
| 2  | TypeB | 351 | 383 | 32 |
| 3  | TypeC | 356 | 412 | 56 |
| 4  | TypeB | 372 | 404 | 32 |
| 5  | TypeB | 377 | 411 | 34 |
| 6  | TypeC | 393 | 425 | 32 |
| 7  | TypeB | 398 | 432 | 34 |
| 8  | TypeA | 412 | 460 | 48 |
| 9  | TypeB | 435 | 467 | 32 |
| 10 | TypeB | 463 | 495 | 32 |
| 11 | TypeB | 477 | 523 | 46 |
| 12 | TypeB | 477 | 509 | 32 |
| 13 | TypeA | 504 | 551 | 47 |
| 14 | TypeC | 531 | 596 | 65 |
| 16 | TypeB | 561 | 593 | 32 |
| 17 | TypeB | 575 | 607 | 32 |
| 18 | TypeA | 587 | 642 | 55 |
| 19 | TypeB | 603 | 635 | 32 |
| 15 | TypeC | 547 | 708 | 161 |
| 20 | TypeC | 615 | 685 | 70 |
| 21 | TypeB | 624 | 656 | 32 |
| 22 | TypeB | 624 | 656 | 32 |
| 23 | TypeB | 646 | 684 | 38 |
| 25 | TypeB | 659 | 691 | 32 |
| 24 | TypeB | 659 | 719 | 60 |

**Type breakdown:** 19 TypeB, 6 TypeC, 5 TypeA.
**Window:** earliest start `DAY 224`, latest end `DAY 719`.
**TypeB pattern:** typically 32-day windows (often "blast" campaigns).
**TypeC pattern:** longer (32–161 days) — looks like sustained programs.
**TypeA pattern:** medium (40–55 days).

### 6.6 `coupon.csv` — Bridge_CouponProduct

**Grain:** (`COUPON_UPC`, `PRODUCT_ID`, `CAMPAIGN`) tuple.
**Distincts:** 1,135 coupons, 44,133 products covered, 30 campaigns.

| Column | Type | Semantics |
|---|---|---|
| `COUPON_UPC` | int (large) | Coupon barcode | FK → Dim_Coupon |
| `PRODUCT_ID` | int | Product the coupon applies to | FK → Dim_Product |
| `CAMPAIGN` | int | Campaign distributing the coupon | FK → Dim_Campaign |

**Many-to-many:** one coupon often applies to many products and one product
can be eligible for many coupons. In Power BI, this **must** be modeled as a
bridge table (you cannot create a direct M:N relationship between Dim_Coupon
and Dim_Product). See §10 for the bridge configuration.

### 6.7 `product.csv` — Dim_Product

**Grain:** one row per `PRODUCT_ID`.
**Distincts:** 92,353 products, 44 departments, 308 commodity descriptions, 2,383 sub-commodities, 6,476 manufacturers, 2 brand types.

| Column | Type | Semantics | Notes |
|---|---|---|---|
| `PRODUCT_ID` | int | Anonymized product ID | PK |
| `MANUFACTURER` | int | Anonymized manufacturer ID | Group by; not a label |
| `DEPARTMENT` | varchar | Top of category hierarchy (e.g., GROCERY, DRUG GM, PRODUCE) | 44 distinct |
| `BRAND` | varchar | "National" or "Private" | Useful for private-label penetration analysis |
| `COMMODITY_DESC` | varchar | Mid-level category (e.g., FRZN ICE) | 308 distinct |
| `SUB_COMMODITY_DESC` | varchar | Fine-grained category (e.g., ICE - CRUSHED/CUBED) | 2,383 distinct |
| `CURR_SIZE_OF_PRODUCT` | varchar | Pack size/UOM string (e.g., "22 LB", "12 OZ") | Free-text — DON'T treat as a clean numeric. Keep as label. |

**Hierarchy for Power BI:** `DEPARTMENT` → `COMMODITY_DESC` → `SUB_COMMODITY_DESC` → `BRAND` → `PRODUCT_ID`.

**Data quality:** Some rows have `COMMODITY_DESC = "NO COMMODITY DESCRIPTION"`
and `SUB_COMMODITY_DESC = "NO SUBCOMMODITY DESCRIPTION"` — typically in
non-merchandise departments (`MISC. TRANS.`, etc.). Decide whether to filter
these from category analyses.

### 6.8 `hh_demographic.csv` — Dim_Household_Demographics

**Grain:** one row per household with demographic info.
**Coverage:** 801 of 2,500 households (32.0%).

| Column | Distincts | Sample values |
|---|---:|---|
| `AGE_DESC` | 6 | `19-24`, `25-34`, `35-44`, `45-54`, `55-64`, `65+` |
| `MARITAL_STATUS_CODE` | 3 | `A` (married), `B` (single), `U` (unknown) — confirm with project owner |
| `INCOME_DESC` | 12 | `Under 15K`, `15-24K`, `25-34K`, `35-49K`, `50-74K`, `75-99K`, `100-124K`, `125-149K`, `150-174K`, `175-199K`, `200-249K`, `250K+` |
| `HOMEOWNER_DESC` | 5 | `Homeowner`, `Renter`, `Probable Owner`, `Probable Renter`, `Unknown` |
| `HH_COMP_DESC` | 6 | `Single Female`, `Single Male`, `1 Adult Kids`, `2 Adults Kids`, `2 Adults No Kids`, `Unknown` |
| `HOUSEHOLD_SIZE_DESC` | 5 | `1`, `2`, `3`, `4`, `5+` |
| `KID_CATEGORY_DESC` | 4 | `None/Unknown`, `1`, `2`, `3+` |
| `household_key` | (PK) | int |

**Critical modeling decision.** Do **not** make a separate Dim_Household_Demo
table. Instead:
1. Build `Dim_Household` from `DISTINCT(household_key)` across the facts (gives all 2,500).
2. **Left-join** demographics into `Dim_Household` in Power Query.
3. Add `HasDemographics = (AGE_DESC IS NOT NULL)` as a flag.
4. For columns that can be missing, fill with `"(not surveyed)"` so PBI slicers don't drop blanks oddly.

Without this, demographic visuals will look like they're computed over the
full population when they're really computed over the 801-household subset.

---

## 7. Data quality & quirks (read before modeling)

| # | Observation | Implication |
|---|---|---|
| 1 | **No real dates.** All time is integer DAY/WEEK_NO. | Build a synthetic Dim_Date keyed on DAY 1..711. Optionally anchor to a fictitious start date (e.g., 2020-01-01). |
| 2 | **Demographics cover only 32% of households.** | Always show `HasDemographics = TRUE` slicer when computing demographic-segmented measures, or split visuals into "all households" vs "surveyed". |
| 3 | **Campaign window extends past observation window.** Campaign 24 ends `DAY 719` but transactions stop at `DAY 711`. | Pre-/post-campaign analyses for late campaigns will have truncated post-windows. Filter or note. |
| 4 | **Discounts are stored as negatives.** `RETAIL_DISC = -0.6` means \$0.60 was discounted. | Wrap in `ABS()` for display measures. |
| 5 | **`SALES_VALUE` is net of discounts.** | If you want gross, sum `SALES_VALUE + ABS(all discounts)`. |
| 6 | **Causal data is 36.8M rows.** | Pre-aggregate to product × week (drop store) or product × store × week with boolean flags. See §10.2. |
| 7 | **`QUANTITY` has extreme outliers** (max = 89,638). | Likely weighted bulk items where QUANTITY is in fractional units multiplied. Consider median/p95 alongside mean, or cap at p99 for displays. |
| 8 | **`coupon.csv` has duplicates by design** — same coupon × product pair can appear under different campaigns. | Confirm grain is (COUPON_UPC, PRODUCT_ID, CAMPAIGN) before dedupe. |
| 9 | **`campaign_table.csv` has a `DESCRIPTION` column that duplicates Dim_Campaign.** | Drop it during ETL — keep the one source of truth in Dim_Campaign. |
| 10 | **No store master.** `STORE_ID` is a bare integer with no attributes. | Dim_Store will only have `STORE_ID`. If geographic/format data is needed, sources outside this dataset are required. |
| 11 | **No basket master.** `BASKET_ID` is just an integer with no extra attributes; `DAY`, `STORE_ID`, `household_key` together identify the trip. | Treat as a degenerate dimension on Fact_Transactions. |
| 12 | **Some products have placeholder commodity descriptions** (`"NO COMMODITY DESCRIPTION"`). | Filter from category-level analyses or bucket as "Other". |
| 13 | **Display values include both digits and `'A'`** (10 categories: 0–9 + A). Mailer values are letter codes. | Treat as categorical — never sum or average. |
| 14 | **Campaign type counts are imbalanced** (TypeB = 19, TypeC = 6, TypeA = 5). | Be careful with simple "average effect by type" — TypeA/C samples are small. |

---

## 8. Constellation schema

Two primary fact tables sharing conformed dimensions → **constellation
(galaxy) schema**, not a single star.

```
                            ┌──────────────────┐
                            │     Dim_Date     │
                            │  DAY, WEEK_NO,   │
                            │  Year_Idx, Month │
                            │  WeekOfYear,...  │
                            └────────┬─────────┘
            DAY/WEEK_NO              │              DAY/WEEK_NO
   ┌────────────────────┬────────────┴──────────┬────────────────────┐
   │                    │                       │                    │
   ▼                    ▼                       ▼                    ▼
┌────────────┐  ┌──────────────────────┐  ┌─────────────┐  ┌──────────────────┐
│ Dim_HHold  │  │  Fact_Transactions   │  │  Dim_Store  │  │  Fact_Causal     │
│ + demo     │──│  grain: line item    │──│  STORE_ID   │──│  product×store×wk│
│ household_ │  │  Σ SALES_VALUE,      │  │             │  │  display, mailer │
│   key (PK) │  │    QUANTITY, DISCs   │  └─────────────┘  └────────┬─────────┘
└──────┬─────┘  └──────────┬───────────┘                            │
       │                   │ PRODUCT_ID                             │
       │                   ▼                                        │
       │        ┌──────────────────────┐                            │
       │        │     Dim_Product      │◄───────────────────────────┘
       │        │  DEPT→COMM→SUB,      │           PRODUCT_ID
       │        │  BRAND, MANUF, SIZE  │
       │        └──────────────────────┘
       │
       │        ┌──────────────────────┐
       ├───────▶│ Fact_CampaignRecv'd  │   (factless fact:
       │        │  household × campaign│    "got the campaign")
       │        └──────────┬───────────┘
       │                   │
       │                   ▼
       │        ┌──────────────────────┐
       │        │    Dim_Campaign      │
       │        │  CAMPAIGN, TYPE,     │
       │        │  START_DAY, END_DAY  │
       │        └──────────┬───────────┘
       │                   │
       │                   ▼
       │        ┌──────────────────────┐
       └───────▶│ Fact_CouponRedeem    │
                │  household × coupon  │
                │  × campaign × day    │
                └──────────┬───────────┘
                           │ COUPON_UPC
                           ▼
                ┌──────────────────────┐
                │     Dim_Coupon       │
                │     COUPON_UPC       │
                └──────────┬───────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │ Bridge_CouponProduct │  (M:N coupon ↔ product)
                │ COUPON_UPC, PROD_ID  │
                │ + CAMPAIGN           │
                └──────────────────────┘
```

### Tables in the model

**Facts**
- `Fact_Transactions` (line-item grain)
- `Fact_Causal` (week-grain promo state) — pre-aggregated; see §10.2
- `Fact_CouponRedemption` (event)
- `Fact_CampaignReceived` (factless)

**Dimensions**
- `Dim_Household` (2,500 rows; left-joined demographics)
- `Dim_Product` (~92K rows; hierarchy)
- `Dim_Store` (582 rows; STORE_ID only)
- `Dim_Date` (~711 rows; synthetic)
- `Dim_Campaign` (30 rows; with type, start, end)
- `Dim_Coupon` (~1,135 rows)

**Bridges**
- `Bridge_CouponProduct` (M:N between coupon and product)

---

## 9. Join keys & cardinality

All relationships are **single-direction** (Dim → Fact) **single-active**
unless noted.

| From | To | Key | Cardinality | Notes |
|---|---|---|---|---|
| Fact_Transactions | Dim_Household | `household_key` | M:1 | |
| Fact_Transactions | Dim_Product | `PRODUCT_ID` | M:1 | |
| Fact_Transactions | Dim_Store | `STORE_ID` | M:1 | |
| Fact_Transactions | Dim_Date | `DAY` | M:1 | Mark Dim_Date as date table |
| Fact_Causal | Dim_Product | `PRODUCT_ID` | M:1 | |
| Fact_Causal | Dim_Store | `STORE_ID` | M:1 | |
| Fact_Causal | Dim_Date | `WEEK_NO` | M:1 | Use a separate `WEEK_NO` column on Dim_Date or build a Dim_Week |
| Fact_CouponRedemption | Dim_Household | `household_key` | M:1 | |
| Fact_CouponRedemption | Dim_Coupon | `COUPON_UPC` | M:1 | |
| Fact_CouponRedemption | Dim_Campaign | `CAMPAIGN` | M:1 | |
| Fact_CouponRedemption | Dim_Date | `DAY` | M:1 | |
| Fact_CampaignReceived | Dim_Household | `household_key` | M:1 | |
| Fact_CampaignReceived | Dim_Campaign | `CAMPAIGN` | M:1 | |
| Bridge_CouponProduct | Dim_Coupon | `COUPON_UPC` | M:1 | |
| Bridge_CouponProduct | Dim_Product | `PRODUCT_ID` | M:1 | |

**Bidirectional?** Only enable bidirectional filtering on Bridge_CouponProduct
if you specifically need to filter Dim_Product from a Dim_Coupon selection.
Default to single-direction to keep the model predictable.

**Inactive relationships?** None required for v1. If you build a "campaign
exposure period" intelligence (filtering transactions to campaign windows),
that's a calculated approach in DAX (`CALCULATE` with a date-range filter),
not a relationship.

---

## 10. Power BI build plan

### 10.1 Build Dim_Date

There are no real dates, so generate it. Options:

**Option A — pure synthetic (recommended for fidelity):**
```
Dim_Date =
ADDCOLUMNS (
    GENERATESERIES ( 1, 711 ),
    "Day_Idx",     [Value],
    "Week_No",     INT( ([Value] - 1) / 7 ) + 1,
    "Year_Idx",    INT( ([Value] - 1) / 365 ) + 1,
    "Month_Idx",   INT( ([Value] - 1) / 30 ) + 1,
    "DayOfWeek",   MOD ( [Value] - 1, 7 ) + 1
)
```

**Option B — anchored to a fictitious calendar (better for date slicers):**
Anchor `DAY 1 = 2020-01-01`, then build a normal calendar table with
`DATEADD`. Mark as date table. Use `Day_Idx` as the join key into facts.

Either way, **expose both `DAY` and `WEEK_NO`** so you can join Fact_Causal
(week grain) and Fact_Transactions (day grain) to the same date table.

### 10.2 Pre-aggregate Fact_Causal

36.8M rows is loadable but slow. Choose one:

| Strategy | Result rows (approx) | Loses |
|---|---:|---|
| Keep raw | 36.8M | nothing |
| Aggregate to (product × week) — collapse stores | ~9.4M | store-level promo variance |
| Aggregate to (product × store × week) with boolean flags only | 36.8M but narrower | display/mailer category detail |
| Aggregate to "any promo this week" per product | ~few hundred K | per-mailer / per-display detail |

**Recommended starting point:** `(PRODUCT_ID, WEEK_NO)` rolled up with
`OnDisplay_AnyStore = MAX(display <> '0')`, `InMailer_AnyStore = MAX(mailer
<> '0')`, plus `StoresOnDisplay`, `StoresInMailer` counts. Drops to single-
digit millions of rows and keeps the headline signal.

Power Query M sketch:
```m
let
    src = Csv.Document(File.Contents("...causal_data.csv"), [Delimiter=",", Encoding=65001]),
    promoted = Table.PromoteHeaders(src),
    typed = Table.TransformColumnTypes(promoted, {
        {"PRODUCT_ID", Int64.Type}, {"STORE_ID", Int64.Type},
        {"WEEK_NO", Int64.Type}, {"display", type text}, {"mailer", type text}
    }),
    flagged = Table.AddColumn(typed, "OnDisplay", each [display] <> "0", Logical.Type),
    flagged2 = Table.AddColumn(flagged, "InMailer", each [mailer] <> "0", Logical.Type),
    grouped = Table.Group(flagged2, {"PRODUCT_ID", "WEEK_NO"}, {
        {"OnDisplay_AnyStore", each List.AnyTrue([OnDisplay]), Logical.Type},
        {"InMailer_AnyStore",  each List.AnyTrue([InMailer]),  Logical.Type},
        {"StoresOnDisplay",    each List.Count(List.Select([OnDisplay], each _ = true)), Int64.Type},
        {"StoresInMailer",     each List.Count(List.Select([InMailer],  each _ = true)), Int64.Type}
    })
in
    grouped
```

### 10.3 Build Dim_Household with left-joined demographics

```m
let
    txn = #"transaction_data",
    households = Table.Distinct( Table.SelectColumns(txn, {"household_key"}) ),
    demo = #"hh_demographic",
    joined = Table.NestedJoin(households, "household_key", demo, "household_key", "demo", JoinKind.LeftOuter),
    expanded = Table.ExpandTableColumn(joined, "demo",
        {"AGE_DESC","MARITAL_STATUS_CODE","INCOME_DESC","HOMEOWNER_DESC","HH_COMP_DESC","HOUSEHOLD_SIZE_DESC","KID_CATEGORY_DESC"}),
    flagged = Table.AddColumn(expanded, "HasDemographics", each [AGE_DESC] <> null, Logical.Type)
in
    flagged
```

### 10.4 Sign-correct the discount columns

In Power Query, transform `RETAIL_DISC`, `COUPON_DISC`, `COUPON_MATCH_DISC`
to absolute values, **OR** keep them as-is and write DAX measures that use
`ABS`. Document whichever you pick — don't mix.

### 10.5 Recommended core measures (DAX)

```dax
-- Headline measures
Total Sales            := SUM ( Fact_Transactions[SALES_VALUE] )
Total Units            := SUM ( Fact_Transactions[QUANTITY] )
Total Baskets          := DISTINCTCOUNT ( Fact_Transactions[BASKET_ID] )
Active Households      := DISTINCTCOUNT ( Fact_Transactions[household_key] )
Avg Basket Value       := DIVIDE ( [Total Sales], [Total Baskets] )
Spend per Household    := DIVIDE ( [Total Sales], [Active Households] )

-- Discounts (assuming you DID NOT abs() in Power Query)
Retail Discount        := SUMX ( Fact_Transactions, ABS ( Fact_Transactions[RETAIL_DISC] ) )
Coupon Discount        := SUMX ( Fact_Transactions, ABS ( Fact_Transactions[COUPON_DISC] ) )
Gross Sales            := [Total Sales] + [Retail Discount] + [Coupon Discount]
                          + SUMX ( Fact_Transactions, ABS ( Fact_Transactions[COUPON_MATCH_DISC] ) )
Discount Rate          := DIVIDE ( [Gross Sales] - [Total Sales], [Gross Sales] )

-- Year-over-year (using synthetic Year_Idx)
Sales Y1 := CALCULATE ( [Total Sales], Dim_Date[Year_Idx] = 1 )
Sales Y2 := CALCULATE ( [Total Sales], Dim_Date[Year_Idx] = 2 )
Spend Δ% := DIVIDE ( [Sales Y2] - [Sales Y1], [Sales Y1] )

-- Marketing exposure
Households Receiving Any Campaign :=
    CALCULATE ( DISTINCTCOUNT ( Fact_CampaignReceived[household_key] ) )

Sales | Received Campaign :=
    CALCULATE (
        [Total Sales],
        TREATAS (
            VALUES ( Fact_CampaignReceived[household_key] ),
            Dim_Household[household_key]
        )
    )
```

### 10.6 Performance checklist

- Mark `Dim_Date` as a date table.
- Set every fact-side join column to `Don't summarize` and hide it from report view.
- Hide `BASKET_ID`, `STORE_ID`, etc. on facts but expose them via the dim where useful.
- Disable auto date/time in PBI options (it generates hidden date hierarchies you don't want).
- Keep all relationships single-direction.

---

## 11. Mapping research questions → analyses

### 11.1 Q1: Customers spending more / less over time

**Approach:** Compute per-household sales for Year 1 vs Year 2 (using
`Year_Idx`). Classify each household into `Growing`, `Declining`, or `Flat`
based on a Δ% threshold (e.g., ±5%).

```dax
HH Spend Y1 := CALCULATE ( [Total Sales], Dim_Date[Year_Idx] = 1 )
HH Spend Y2 := CALCULATE ( [Total Sales], Dim_Date[Year_Idx] = 2 )
HH Spend Δ% := DIVIDE ( [HH Spend Y2] - [HH Spend Y1], [HH Spend Y1] )

HH Trend :=
    SWITCH (
        TRUE (),
        [HH Spend Y1] = 0, "New (no Y1)",
        [HH Spend Y2] = 0, "Lost (no Y2)",
        [HH Spend Δ%] >  0.05, "Growing",
        [HH Spend Δ%] < -0.05, "Declining",
        "Flat"
    )
```

**Visuals:** stacked bar of household-counts by trend; scatter of Y1 spend
vs Y2 spend with trend coloring; cohort sizes over the 711 days.

**"Describe these customers"** = cross-tab `HH Trend` against
demographics (filter `HasDemographics = TRUE`).

### 11.2 Q2: Which categories grow for "Growing" households

**Approach:** Filter Fact_Transactions to households where `HH Trend =
"Growing"`, then compute sales by `COMMODITY_DESC` for Y1 vs Y2 and rank by
Δ%.

DAX pattern:
```dax
Cat Δ% (Growing HH) :=
    VAR GrowingHH =
        FILTER ( Dim_Household, [HH Trend] = "Growing" )
    RETURN
        CALCULATE (
            DIVIDE ( [Sales Y2] - [Sales Y1], [Sales Y1] ),
            KEEPFILTERS ( GrowingHH )
        )
```

**Visual:** Top 20 commodities by `Cat Δ% (Growing HH)`, alongside total
spend in each so small-volume noise is visible.

### 11.3 Q3: Which categories decline for "Declining" households

Mirror of §11.2 with `HH Trend = "Declining"`. Look at categories with the
**most negative** Δ% and the **largest absolute spend loss** ($) — the
two rankings will differ and tell different stories.

### 11.4 Q4: Demographic factors driving spend

**Approach:** Restrict to `HasDemographics = TRUE` (801 households). For each
demographic dimension, compute spend metrics and category mix, then look for
significant differences.

Suggested visuals:
- Avg spend per HH by `INCOME_DESC` (bar)
- Avg basket size by `HOUSEHOLD_SIZE_DESC` (bar)
- % spend by `DEPARTMENT` for `HH_COMP_DESC` (matrix → highlights category preferences)
- Decomposition tree: Total Sales → INCOME_DESC → HH_COMP_DESC → DEPARTMENT

**Statistical caveat.** With 801 households, some demographic cells are
small. Always show counts alongside means so the peer/audience can judge
whether differences are noise.

### 11.5 Q5: Does direct marketing improve engagement?

**Approach options (pick one to start; layer the others later):**

**(a) Cross-sectional — exposed vs unexposed.**
Compare avg spend / basket count for households in Fact_CampaignReceived
(1,584) vs not (916). Strong confounding risk: campaign recipients were
likely targeted because they're high-value. Caveat your findings.

**(b) Pre/post per campaign.**
For each campaign with a defined `START_DAY..END_DAY`, compare per-household
spend in the N days **before** vs **during/after** the campaign window for
exposed households. Use unexposed households as a control to net out
seasonality.

DAX sketch (compute per exposed HH):
```dax
PreCampaign Window := 28           -- days before campaign starts
PostCampaign Window := 28          -- days after campaign starts

Sales Pre :=
    VAR cs = SELECTEDVALUE ( Dim_Campaign[START_DAY] )
    RETURN
        CALCULATE (
            [Total Sales],
            ALL ( Dim_Date ),
            Dim_Date[Day_Idx] >= cs - [PreCampaign Window],
            Dim_Date[Day_Idx] <  cs
        )

Sales Post :=
    VAR cs = SELECTEDVALUE ( Dim_Campaign[START_DAY] )
    RETURN
        CALCULATE (
            [Total Sales],
            ALL ( Dim_Date ),
            Dim_Date[Day_Idx] >= cs,
            Dim_Date[Day_Idx] <  cs + [PostCampaign Window]
        )

Lift :=
    DIVIDE ( [Sales Post] - [Sales Pre], [Sales Pre] )
```

Chart `Lift` faceted by campaign type (TypeA/B/C). Compare to the same
calculation on unexposed households — that gives a proxy difference-in-
differences.

**(c) Coupon redemption funnel.**
Of households that received a campaign, how many received an eligible
coupon, and how many redeemed it? Sales lift ratio: redeemed-coupon
households vs received-but-didn't-redeem.

**Important caveats:**
- TypeA/C have small samples (5 and 6 campaigns). Aggregate findings by type
  cautiously.
- Some campaigns extend past the observation window — drop or trim those.
- Targeting bias is real; don't claim causation from observational data.

---

## 12. Open questions for the project owner

Confirm before locking design:

1. Do we want to anchor `DAY 1` to a real (fictitious) calendar date (better
   slicers) or stay in pure day-integer space (more honest to source)?
2. Are we modeling at line-item grain in Fact_Transactions, or pre-rolling
   to basket-grain? (Line item is more flexible; basket is faster.)
3. For Fact_Causal, can we drop store-level detail (collapse to product ×
   week)? Saves 4× rows and the headline analyses don't need it.
4. Confirm the meaning of `MARITAL_STATUS_CODE` letters (`A`/`B`/`U`) — the
   dataset doesn't include a code book. Common interpretations: `A` =
   married/partnered, `B` = single, `U` = unknown.
5. For the marketing-effect analysis, what window length pre/post is the
   right default? (28 days = one cycle is a common starting point; 14 / 56
   are alternatives.)
6. Should we treat coupon redemption as a separate fact, or fold it into
   Fact_Transactions via the `COUPON_DISC > 0` flag? (Different grain — keep
   separate unless there's a reason.)

---

## 13. Handoff checklist (for the next session)

- [ ] Read this document end to end.
- [ ] Confirm raw CSVs are in `data/raw/` (run §4 if not).
- [ ] Decide on the open questions in §12.
- [ ] Build Dim_Date per §10.1.
- [ ] Pre-aggregate Fact_Causal per §10.2.
- [ ] Build Dim_Household with left-joined demographics and `HasDemographics` flag (§10.3).
- [ ] Decide & apply the discount sign convention (§10.4).
- [ ] Wire up the relationships per §9 — single-direction, single-active.
- [ ] Add the core measures from §10.5.
- [ ] Build a v1 dashboard covering Q1–Q5 from §11. Don't try to nail all five questions in one page; aim for one tab per question.
- [ ] Note any data-quality findings beyond §7 in a new section here.

When questions come up, log them in §12 (don't lose them in chat). When
decisions get made, capture them in this document so a future session can
pick up without re-deriving the reasoning.

---

## Appendix A: Quick reference — column → table

| Column | Lives in | Joins to |
|---|---|---|
| `household_key` | Fact_Transactions, Fact_CampaignReceived, Fact_CouponRedemption, Dim_Household, hh_demographic | Dim_Household |
| `BASKET_ID` | Fact_Transactions | (degenerate) |
| `DAY` | Fact_Transactions, Fact_CouponRedemption, Dim_Campaign (as START_DAY/END_DAY) | Dim_Date |
| `WEEK_NO` | Fact_Transactions, Fact_Causal | Dim_Date |
| `PRODUCT_ID` | Fact_Transactions, Fact_Causal, Bridge_CouponProduct, Dim_Product | Dim_Product |
| `STORE_ID` | Fact_Transactions, Fact_Causal | Dim_Store |
| `CAMPAIGN` | Fact_CampaignReceived, Fact_CouponRedemption, Bridge_CouponProduct, Dim_Campaign | Dim_Campaign |
| `COUPON_UPC` | Fact_CouponRedemption, Bridge_CouponProduct, Dim_Coupon | Dim_Coupon |

## Appendix B: Source files at-a-glance

```
campaign_desc.csv        DESCRIPTION, CAMPAIGN, START_DAY, END_DAY
campaign_table.csv       DESCRIPTION, household_key, CAMPAIGN
causal_data.csv          PRODUCT_ID, STORE_ID, WEEK_NO, display, mailer
coupon.csv               COUPON_UPC, PRODUCT_ID, CAMPAIGN
coupon_redempt.csv       household_key, DAY, COUPON_UPC, CAMPAIGN
hh_demographic.csv       AGE_DESC, MARITAL_STATUS_CODE, INCOME_DESC,
                         HOMEOWNER_DESC, HH_COMP_DESC, HOUSEHOLD_SIZE_DESC,
                         KID_CATEGORY_DESC, household_key
product.csv              PRODUCT_ID, MANUFACTURER, DEPARTMENT, BRAND,
                         COMMODITY_DESC, SUB_COMMODITY_DESC, CURR_SIZE_OF_PRODUCT
transaction_data.csv     household_key, BASKET_ID, DAY, PRODUCT_ID, QUANTITY,
                         SALES_VALUE, STORE_ID, RETAIL_DISC, TRANS_TIME, WEEK_NO,
                         COUPON_DISC, COUPON_MATCH_DISC
```
