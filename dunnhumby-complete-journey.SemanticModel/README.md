# Semantic Model — dunnhumby Complete Journey

Power BI semantic model in [PBIP format](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-overview). All tables, relationships, measures, and the product hierarchy are already configured — open `dunnhumby-complete-journey.pbip` from the repo root and refresh.

---

## Data source

All tables load from **Parquet files** in `data/parquet_parking/`. Before refreshing, update the data source path in Power BI Desktop:

**Home → Transform data → Data source settings → Change source**

Point it to the absolute path of your local `data/parquet_parking/` folder. The Parquet files are built by the ETL scripts — see `scripts/README.md` if you haven't run them yet.

---

## Tables loaded

### Dimensions

| Table | Rows | Key column | Description |
|---|---:|---|---|
| `dim_date` | 711 | `Day_Idx` | Synthetic calendar, DAY 1–711 anchored to 2020-01-01. Marked as date table on `AnchorDate`. |
| `dim_household` | 2,500 | `household_key` | All households with demographics left-joined, `HH_Trend` pre-classified, Y1/Y2 spend, basket metrics, and campaign/coupon flags. |
| `dim_product` | 92,353 | `PRODUCT_ID` | Product hierarchy (`DEPARTMENT → COMMODITY_DESC → SUB_COMMODITY_DESC → BRAND`) with `Has_Real_Category` and `Is_Private_Brand` flags. |
| `dim_store` | 582 | `STORE_ID` | Distinct stores. No attributes beyond ID. |
| `dim_campaign` | 30 | `CAMPAIGN` | Campaign type (TypeA/B/C), start/end day, duration, `Extends_Past_Observation` flag. |
| `dim_coupon` | 1,135 | `COUPON_UPC` | Coupons with eligible product count and redemption count. |

### Facts

| Table | Rows | Grain | Description |
|---|---:|---|---|
| `fact_transactions` | 2,595,732 | One row per product line item per basket | Primary sales fact. Discounts sign-corrected. `GROSS_SALES` and `TRANS_HOUR` derived. |
| `fact_causal_weekly` | ~2,049,187 | One row per (`PRODUCT_ID`, `WEEK_NO`) | Promotional state: display and mailer flags aggregated from the raw 36.8M-row causal CSV. |
| `fact_coupon_redemption` | 2,318 | One row per redemption event | Coupon redemption events by household, day, coupon, and campaign. |
| `fact_campaign_received` | 7,208 | One row per (household, campaign) | Factless fact marking which households received which campaigns. |

### Bridge

| Table | Rows | Description |
|---|---:|---|
| `bridge_coupon_product` | 119,384 | M:N relationship between coupons and products, including the campaign that issued each coupon. |

---

## Relationships

All relationships are single-direction (Dim → Fact) and single-active unless noted.

| From | Column | To | Column | Notes |
|---|---|---|---|---|
| `fact_transactions` | `household_key` | `dim_household` | `household_key` | |
| `fact_transactions` | `PRODUCT_ID` | `dim_product` | `PRODUCT_ID` | |
| `fact_transactions` | `STORE_ID` | `dim_store` | `STORE_ID` | |
| `fact_transactions` | `DAY` | `dim_date` | `Day_Idx` | |
| `fact_causal_weekly` | `PRODUCT_ID` | `dim_product` | `PRODUCT_ID` | |
| `fact_causal_weekly` | `WEEK_NO` | `dim_date` | `Week_No` | **Both-directions** — needed for promo-to-date filtering |
| `fact_coupon_redemption` | `household_key` | `dim_household` | `household_key` | |
| `fact_coupon_redemption` | `COUPON_UPC` | `dim_coupon` | `COUPON_UPC` | |
| `fact_coupon_redemption` | `CAMPAIGN` | `dim_campaign` | `CAMPAIGN` | |
| `fact_coupon_redemption` | `DAY` | `dim_date` | `Day_Idx` | |
| `fact_campaign_received` | `household_key` | `dim_household` | `household_key` | |
| `fact_campaign_received` | `CAMPAIGN` | `dim_campaign` | `CAMPAIGN` | |
| `bridge_coupon_product` | `COUPON_UPC` | `dim_coupon` | `COUPON_UPC` | |
| `bridge_coupon_product` | `PRODUCT_ID` | `dim_product` | `PRODUCT_ID` | |

---

## Key modeling decisions

**`HH_Trend` is pre-computed in `dim_household`.** Households are classified as `Growing`, `Declining`, `Flat`, `New`, `Lost`, or `Inactive` based on Year 1 vs Year 2 net sales (±5% threshold). This is the central slicer for research questions 1–3. The classification is done in the ETL script — not in DAX — to keep visual query times fast.

**Discount columns are sign-corrected.** In the source CSV, `RETAIL_DISC`, `COUPON_DISC`, and `COUPON_MATCH_DISC` are stored as negative numbers. They are flipped to positive in `fact_transactions` during ETL. DAX measures use `SUM` directly.

**`dim_date` is marked as the date table on `AnchorDate`.** `AnchorDate` is a real calendar date (DAY 1 = 2020-01-01) for Power BI date intelligence functions. The underlying integer `Day_Idx` (1–711) is the join key into the fact tables.

**`fact_causal_weekly` joins to `dim_date` on `WEEK_NO` / `Week_No` with both-directions filtering.** This allows date slicers to filter the causal table even though it has no direct date key — the week grain is sufficient for promo analysis.

**`dim_household` left-joins demographics.** Only 801 of 2,500 households have demographic records. The remaining 1,699 get `"(not surveyed)"` in all demographic columns. Always use the `HasDemographics = TRUE` filter when building demographic visuals to avoid computing averages over the full population.

---

## DAX measures

All 23 measures are defined in `model.bim` and documented in:
- `data/parquet_parking/measures.dax` — raw DAX expressions, ready to paste
- `data/parquet_parking/_measures.parquet` — machine-readable measure metadata

Measure families:
- **Headline** — Total Sales, Total Units, Total Baskets, Active Households, Avg Basket Value, Spend per Household
- **Year-over-Year** — Sales Y1, Sales Y2, YoY Growth %
- **Household Cohorts** — Households Growing, Households Declining
- **Marketing Impact** — Sales Exposed HH, Sales Unexposed HH, Households Receiving Any Campaign
- **Discounts & Gross** — Retail Discount, Coupon Discount, Gross Sales, Discount Rate

---

## Files in this folder

| File | Description |
|---|---|
| `model.bim` | Full model definition in TMDL JSON — tables, columns, measures, relationships, hierarchies |
| `definition.pbism` | PBIP model metadata and schema version |
| `diagramLayout.json` | Model diagram layout (table positions in the Relationships view) |
| `.pbi/cache.abf` | Local compiled model cache — **do not commit**, regenerated automatically by Power BI Desktop |
| `.pbi/localSettings.json` | Local developer settings — **not committed** |
| `.pbi/editorSettings.json` | Editor preferences |
| `.platform` | Fabric platform metadata |
