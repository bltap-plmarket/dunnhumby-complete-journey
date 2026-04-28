# parquet_parking — Power BI ingestion-ready files

Pre-modeled, Parquet-formatted tables ready for Power BI. Built by
`scripts/build_parquet.py` from the raw CSVs in `data/raw/`. Re-run that
script anytime the raw data refreshes.

> **Story this dataset is set up to tell.** Five Kaggle-defined questions
> (see `docs/SCHEMA.md` §3 and §11): which households are spending more vs
> less over time, which categories shift with them, how demographics
> influence spend, and whether direct marketing actually moves the needle.
> The model below is shaped for those questions specifically.

## Machine-readable specs (point your skill at these)

| File | Purpose |
|---|---|
| `_model.json` | Tables, columns, types, relationships, hierarchies, measures — the canonical model spec for a build skill to consume. |
| `measures.dax` | All DAX measures as a single ready-to-paste file. |
| `storyboard.json` | Page-by-page dashboard layout: KPIs, visuals, fields, filters. One page per Kaggle research question. |
| `theme.json` | Power BI theme JSON (palette, fonts, good/bad colors). |

## Files in this folder

| File | Role | Rows | Size | Grain |
|---|---|---:|---:|---|
| `dim_date.parquet` | dimension | 711 | <1 MB | one row per `Day_Idx` (1..711) |
| `dim_household.parquet` | dimension (★ key slicer) | 2,500 | <1 MB | one row per household, with **HH_Trend baked in** |
| `dim_product.parquet` | dimension | 92,353 | <1 MB | one row per `PRODUCT_ID` |
| `dim_store.parquet` | dimension | 582 | <1 MB | one row per `STORE_ID` |
| `dim_campaign.parquet` | dimension | 30 | <1 MB | one row per `CAMPAIGN` |
| `dim_coupon.parquet` | dimension | 1,135 | <1 MB | one row per `COUPON_UPC` |
| `bridge_coupon_product.parquet` | bridge | 119,384 | <1 MB | M:N coupon ↔ product (incl. campaign) |
| `fact_transactions.parquet` | **primary fact** | 2,595,732 | 23 MB | one row per line item |
| `fact_causal_weekly.parquet` | fact | 2,049,187 | 6 MB | one row per (`PRODUCT_ID`, `WEEK_NO`) |
| `fact_coupon_redemption.parquet` | fact | 2,318 | <1 MB | one row per redemption |
| `fact_campaign_received.parquet` | factless fact | 7,208 | <1 MB | one row per (household, campaign) |

Total: ~30 MB. Loads into Power BI in seconds.

## Relationships to wire in Power BI

All single-direction (Dim → Fact), single-active.

| From | To | Key |
|---|---|---|
| `fact_transactions` | `dim_household` | `household_key` |
| `fact_transactions` | `dim_product` | `PRODUCT_ID` |
| `fact_transactions` | `dim_store` | `STORE_ID` |
| `fact_transactions` | `dim_date` | `DAY` ↔ `Day_Idx` |
| `fact_causal_weekly` | `dim_product` | `PRODUCT_ID` |
| `fact_causal_weekly` | `dim_date` | `WEEK_NO` |
| `fact_coupon_redemption` | `dim_household` | `household_key` |
| `fact_coupon_redemption` | `dim_coupon` | `COUPON_UPC` |
| `fact_coupon_redemption` | `dim_campaign` | `CAMPAIGN` |
| `fact_coupon_redemption` | `dim_date` | `DAY` ↔ `Day_Idx` |
| `fact_campaign_received` | `dim_household` | `household_key` |
| `fact_campaign_received` | `dim_campaign` | `CAMPAIGN` |
| `bridge_coupon_product` | `dim_coupon` | `COUPON_UPC` |
| `bridge_coupon_product` | `dim_product` | `PRODUCT_ID` |

Mark `dim_date` as the date table (Power BI → Modeling → Mark as date table → `AnchorDate`).

## What's been done in ETL (so the report doesn't have to)

The dashboard story drove these decisions — the heavy lifting is already in the data:

### `dim_household` — the storyteller's main slicer

Every household has, baked in:

- **`HH_Trend`** — `Growing` / `Declining` / `Flat` / `New` / `Lost` / `Inactive`
  classification based on Y1 vs Y2 spend (±5% threshold). This is the
  **central slicer** for Q1–Q3.
- **`Spend_Y1`, `Spend_Y2`, `Spend_Total`, `Spend_Delta`, `Spend_Delta_Pct`** —
  pre-computed so visuals don't pay the DAX cost.
- **`Basket_Count`, `Avg_Basket_Value`, `First_Day`, `Last_Day`, `Active_Days`** —
  household tenure metrics.
- **`HasDemographics`** (boolean) — only 801/2,500 households have demos.
  Use this to keep demographic visuals honest. Demographic columns for the
  other 1,699 are filled with `(not surveyed)`.
- **`ReceivedAnyCampaign`** + **`Campaign_Count`** — direct-marketing exposure.
- **`RedeemedAnyCoupon`** + **`Redemption_Count`** — engagement funnel.
- All seven demographic columns: `AGE_DESC`, `MARITAL_STATUS_CODE`,
  `INCOME_DESC`, `HOMEOWNER_DESC`, `HH_COMP_DESC`, `HOUSEHOLD_SIZE_DESC`,
  `KID_CATEGORY_DESC`.

**HH_Trend distribution** in the data:
- Growing: **1,459** (58%) — the optimism story
- Declining: **891** (36%) — the churn-risk story
- Flat: **126** (5%)
- Lost: **21**, New: **3**, Inactive: **0**

### `dim_date` — synthetic but full-featured

- `Day_Idx` (1..711) — join key into facts.
- `Year_Idx` (1 or 2), `Half_Idx`, `Quarter_Idx`, `Month_Idx`, `Week_No`, `DayOfWeek`.
- `AnchorDate` — `DAY 1 = 2020-01-01`, used purely for nicer date-range slicers.
- `YearLabel` (`Y1`/`Y2`), `WeekLabel` (`W001`..`W102`), `YearMonth`.

### `fact_transactions` — already analysis-ready

- All discounts (`RETAIL_DISC`, `COUPON_DISC`, `COUPON_MATCH_DISC`)
  **sign-corrected to positive** measures.
- **`GROSS_SALES`** = `SALES_VALUE` + total discounts (the "before discount"
  figure for discount-rate visuals).
- **`TOTAL_DISC`** = sum of the three discount columns.
- **`TRANS_HOUR`** (0–23) derived from the `TRANS_TIME` HHMM int — useful
  for time-of-day patterns.
- Numeric columns down-cast (int8/16/32/float) for compact memory.

### `fact_causal_weekly` — 36.8M → 2.0M rows (18× reduction)

Original `causal_data.csv` is product × store × week. We collapse stores
into flags + share columns:

| Column | Meaning |
|---|---|
| `OnDisplay_AnyStore` (bool) | Was this product on a non-zero display in any store this week? |
| `InMailer_AnyStore` (bool) | Was this product in a non-zero mailer code in any store this week? |
| `Stores_OnDisplay` (int) | Number of stores carrying this product on display |
| `Stores_InMailer` (int) | Number of stores featuring this product in a mailer |
| `Total_Stores` (int) | Distinct stores carrying this product that week |
| `DisplayShare` (float 0..1) | `Stores_OnDisplay / Total_Stores` |
| `MailerShare` (float 0..1) | `Stores_InMailer / Total_Stores` |

This loses store-level promo variance — fine for the Kaggle questions which
are household × category × time. If you need per-store promo state later,
add it back from the raw CSV.

### `dim_product` — clean hierarchy + flags

- Hierarchy: `DEPARTMENT` → `COMMODITY_DESC` → `SUB_COMMODITY_DESC` → `BRAND` → `PRODUCT_ID`.
- `Has_Real_Category` (bool) — `false` for placeholder rows like
  `NO COMMODITY DESCRIPTION`. Use it as a default filter on category
  analyses to avoid noise.
- `Is_Private_Brand` (bool) — convenience flag for private-label vs
  national-brand cuts.

### `dim_campaign` — enriched

- `CAMPAIGN_TYPE` (renamed from `DESCRIPTION`).
- `Duration_Days`, `Start_Week`, `End_Week`.
- `Extends_Past_Observation` (bool) — `true` for Campaign 24 (`END_DAY 719`
  > observation end `DAY 711`); flag those when computing post-campaign lift.

### `dim_coupon` — enriched

- `Eligible_Product_Count` — how many products this coupon could be used on.
- `Redemption_Count` — how often it was redeemed in the dataset.
- `Was_Redeemed` (bool) — convenience flag.

## Suggested measures to add (DAX)

Already documented in `docs/SCHEMA.md` §10.5 — the most useful ones with
this prepped data:

```dax
-- Already-aggregated household counts by trend
Households Growing   := CALCULATE(DISTINCTCOUNT(dim_household[household_key]), dim_household[HH_Trend]="Growing")
Households Declining := CALCULATE(DISTINCTCOUNT(dim_household[household_key]), dim_household[HH_Trend]="Declining")

-- Spend
Total Sales          := SUM(fact_transactions[SALES_VALUE])
Gross Sales          := SUM(fact_transactions[GROSS_SALES])
Discount Rate        := DIVIDE([Gross Sales] - [Total Sales], [Gross Sales])

-- Year split via Dim_Date
Sales Y1             := CALCULATE([Total Sales], dim_date[Year_Idx]=1)
Sales Y2             := CALCULATE([Total Sales], dim_date[Year_Idx]=2)
YoY Growth %         := DIVIDE([Sales Y2]-[Sales Y1], [Sales Y1])

-- Marketing
Sales | Exposed HH   :=
    CALCULATE([Total Sales],
              TREATAS(VALUES(fact_campaign_received[household_key]), dim_household[household_key]))

Sales | Unexposed HH :=
    CALCULATE([Total Sales],
              EXCEPT(VALUES(dim_household[household_key]),
                     VALUES(fact_campaign_received[household_key])))
```

## Suggested dashboard pages (one per research question)

1. **Spend trends** — header KPIs (Y1 vs Y2 totals, YoY %, household
   counts by `HH_Trend`); scatter of `Spend_Y1` vs `Spend_Y2` colored by
   `HH_Trend`; line chart of weekly sales.
2. **Category winners & losers** — matrix: `COMMODITY_DESC` × `HH_Trend`
   showing Y1 vs Y2 spend; top-20 fastest-growing and fastest-declining
   commodities filtered to `Has_Real_Category = true`.
3. **Demographic profile** — filtered to `HasDemographics = true`. Spend
   per household by `INCOME_DESC`, `AGE_DESC`, `HH_COMP_DESC`. Decomp tree
   from `Total Sales` down through demographic dimensions and into
   `DEPARTMENT`.
4. **Marketing impact** — campaign-level lift comparing `ReceivedAnyCampaign`
   = TRUE vs FALSE; coupon redemption funnel; per-campaign pre/post spend
   lift filtered to `Extends_Past_Observation = false`.
5. **Promotion effects (causal)** — sales lift on weeks where
   `OnDisplay_AnyStore` = TRUE / `InMailer_AnyStore` = TRUE, by `DEPARTMENT`.

## To rebuild from scratch

```bash
# from repo root, with raw CSVs already in data/raw/
python scripts/build_parquet.py
```

Takes ~15 seconds on a typical laptop. Outputs are deterministic — same
inputs produce identical Parquet files.
