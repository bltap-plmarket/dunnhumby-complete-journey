# scripts — ETL Pipeline

Two scripts build the Power BI-ready Parquet files from the raw CSVs. Run them in order: `build_parquet.py` first, then `build_aux_parquet.py`.

## Prerequisites

```bash
pip install -r requirements.txt    # from repo root
```

Raw CSVs must be in `data/raw/`. See the root `README.md` for download instructions.

---

## `build_parquet.py` — Core dims + facts

Reads raw CSVs from `data/raw/`, writes Parquet to `data/parquet_parking/`.

```bash
python scripts/build_parquet.py
```

**Runtime:** ~15–30 seconds on a typical laptop. The bottleneck is reading and aggregating `causal_data.csv` (664 MB, 36.8M rows).

### Outputs

| File | Rows | Description |
|---|---:|---|
| `dim_date.parquet` | 711 | Synthetic calendar (DAY 1–711) anchored to 2020-01-01 for date slicers |
| `dim_household.parquet` | 2,500 | Households with demographics left-joined, `HH_Trend`, Y1/Y2 spend pre-computed |
| `dim_product.parquet` | 92,353 | Products with cleaned hierarchy and `Has_Real_Category` / `Is_Private_Brand` flags |
| `dim_store.parquet` | 582 | Distinct store IDs (derived from transactions + causal data) |
| `dim_campaign.parquet` | 30 | Campaigns with type, duration, week range, `Extends_Past_Observation` flag |
| `dim_coupon.parquet` | 1,135 | Coupons with `Eligible_Product_Count`, `Redemption_Count`, `Was_Redeemed` |
| `bridge_coupon_product.parquet` | 119,384 | M:N coupon ↔ product bridge (includes `CAMPAIGN`) |
| `fact_transactions.parquet` | 2,595,732 | Line items; discounts sign-corrected, `GROSS_SALES` and `TRANS_HOUR` derived |
| `fact_causal_weekly.parquet` | ~2,049,187 | 36.8M causal rows aggregated to product × week with display/mailer flags |
| `fact_coupon_redemption.parquet` | 2,318 | Coupon redemption events |
| `fact_campaign_received.parquet` | 7,208 | Factless fact: which households received which campaigns |

### Key ETL decisions

- **Discount sign correction.** `RETAIL_DISC`, `COUPON_DISC`, `COUPON_MATCH_DISC` are stored as negatives in the source. This script flips them to positive so DAX measures can use `SUM` directly.
- **`GROSS_SALES` derived.** `SALES_VALUE + RETAIL_DISC + COUPON_DISC + COUPON_MATCH_DISC` (all post-correction).
- **`TRANS_HOUR` derived.** Integer `TRANS_TIME` (HHMM format) divided by 100 gives 0–23 hour of day.
- **Causal aggregation.** `causal_data.csv` is product × store × week (36.8M rows). Collapsed to product × week by adding boolean flags (`OnDisplay_AnyStore`, `InMailer_AnyStore`) and store-count columns (`Stores_OnDisplay`, `Stores_InMailer`, `Total_Stores`, `DisplayShare`, `MailerShare`). 18× row reduction; adequate for household-level analyses.
- **`HH_Trend` classification.** Each household is classified as `Growing`, `Declining`, `Flat`, `New`, `Lost`, or `Inactive` using a ±5% Y1-vs-Y2 spend threshold. Pre-computed in `dim_household` so visuals don't pay the DAX cost.
- **Demographic fill.** Households without demographics (68% of the 2,500) get `"(not surveyed)"` in all demographic columns so Power BI slicers don't drop blanks.

---

## `build_aux_parquet.py` — Metadata + analytical aggregates

Reads the Parquet files produced by `build_parquet.py` plus the checked-in `_model.json`, writes additional files to `data/parquet_parking/`.

**Requires:** `build_parquet.py` must be run first.

```bash
python scripts/build_aux_parquet.py
```

**Runtime:** 2–5 minutes. The bottleneck is `agg_household_campaign_lift` which iterates over 2,500 households × 30 campaigns to compute pre/post spend windows.

### Outputs — metadata parquets

These mirror the checked-in `_model.json` in tabular form for tools that prefer Parquet over JSON.

| File | Rows | Description |
|---|---:|---|
| `_tables.parquet` | 11 | Per-table metadata (kind, grain, primary key, row count) |
| `_columns.parquet` | 91 | Per-column metadata (table, name, type, description) |
| `_relationships.parquet` | 14 | Relationship list (from/to, cardinality, cross-filter direction) |
| `_measures.parquet` | 23 | All DAX measures with name, expression, format string, and category tag |
| `_hierarchies.parquet` | 8 | Hierarchy levels (table, hierarchy, level order, column) |

### Outputs — analytical aggregates

Pre-computed to avoid slow DAX at visual query time. Each file powers a specific dashboard page.

| File | Rows | Powers | Why pre-aggregate |
|---|---:|---|---|
| `agg_commodity_cohort_yoy.parquet` | 1,326 | Page 2 — commodity × HH_Trend × Y1/Y2 | Avoids a per-visual join of 2.6M transactions to dim_household + dim_product |
| `agg_dept_yoy_by_cohort.parquet` | 146 | Page 2 secondary — department-level view | Lighter version of the commodity aggregate for summary visuals |
| `agg_household_campaign_lift.parquet` | 75,000 | Page 4 — diff-in-diff marketing lift | Proper pre/post window logic per campaign is non-trivial in DAX; pre-computing yields honest lift. **Headline: +$0.33 diff-in-diff lift per HH per 28-day window — the raw 4.4× exposed/unexposed ratio is almost entirely selection bias.** |
| `agg_promo_sales_weekly.parquet` | 1,076,830 | Page 5 — promo display/mailer effects | Pre-merges the 2.6M transaction table with the 2.0M causal table |

---

## Dependency order

```
data/raw/  (CSVs from Kaggle)
     │
     ▼
build_parquet.py
     │
     ▼
data/parquet_parking/  (dims + facts + bridge)
     │                   ▲
     │              _model.json  (checked into repo)
     ▼
build_aux_parquet.py
     │
     ▼
data/parquet_parking/  (+ metadata parquets + analytical aggregates)
```
