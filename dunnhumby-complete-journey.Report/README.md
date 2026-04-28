# Report — dunnhumby Complete Journey

Power BI report definition in [PBIP format](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-overview). Open `dunnhumby-complete-journey.pbip` from the repo root to edit this report in Power BI Desktop.

**Current state:** Scaffolded. The report shell, semantic model binding, and PLM brand theme are all configured. Dashboard pages are not yet built — use the storyboard below as the build guide.

---

## Opening the report

Open `dunnhumby-complete-journey.pbip` (repo root) in Power BI Desktop (June 2023 or later). The report binds to `../dunnhumby-complete-journey.SemanticModel` automatically. Refresh the model after updating the Parquet data source path.

Do not open `report.json` or `definition.pbir` directly — Power BI Desktop is the editor for these files.

---

## Theme

The **PLM-Complete-Journey** brand theme is applied and stored at:

```
StaticResources/SharedResources/BaseThemes/PLM-Complete-Journey.json
```

Key color assignments for this report:

| Use | Color | Hex |
|---|---|---|
| Growing households | PLM Citron | `#B3E207` |
| Declining households | PLM Scarlet | `#FF1800` |
| Flat households | PLM Steel | `#75A4F7` |
| Primary accent / KPI cards | PLM Cobalt | `#264DDF` |
| Header bars | PLM Navy | `#001F40` |
| Landmine / warning callouts | PLM Honey | `#FFB90B` |

To update the theme, edit `PLM-Complete-Journey.json` and reload the report in Power BI Desktop (View → Themes → Browse for themes).

---

## Dashboard pages (planned)

Five pages, one per Kaggle research question. Build in this order — each page depends on understanding the `HH_Trend` slicer introduced on Page 1.

| Page | Research question | Key visuals | Required filter |
|---|---|---|---|
| **1 — Spend Trends** | Which households spend more/less over time? | Headline KPIs, HH_Trend donut, Y1 vs Y2 scatter, weekly sales line | None |
| **2 — Category Winners & Losers** | Which categories grow/shrink with growing/declining households? | Commodity × cohort matrix, top-20 bar charts | `Has_Real_Category = TRUE` |
| **3 — Demographics** | Which demographic factors drive spend? | Spend by income, household composition, age; decomp tree | `HasDemographics = TRUE` |
| **4 — Marketing Impact** | Does direct marketing improve engagement? | Campaign funnel, exposed vs. unexposed, diff-in-diff lift | `Extends_Past_Observation = FALSE` |
| **5 — Promotion Effects** | Do display/mailer promotions drive sales lift? | Display/mailer lift bars, department matrix | `Has_Real_Category = TRUE` |

Full visual specifications (KPI cards, filters, field assignments) are in `data/parquet_parking/storyboard.json`.

> **Demographic page caveat:** Only 801 of 2,500 households have demographic records. Always keep the `HasDemographics = TRUE` filter active on Page 3 — without it, averages are computed over 2,500 households but only 801 contribute demographic data, producing misleading results.

> **Marketing page caveat:** The raw exposed vs. unexposed spend ratio (4.4×) reflects selection bias — campaign recipients were already high spenders before any campaign. The honest lift figure is +$0.33 per household per 28-day diff-in-diff window. Both numbers should appear on Page 4 with explicit labels. Source: `data/parquet_parking/agg_household_campaign_lift.parquet`.

---

## Pre-computed aggregates for heavy visuals

The `agg_*.parquet` files in `data/parquet_parking/` are pre-computed specifically to power the heavy Pages 2, 4, and 5 visuals without expensive DAX at query time. Load them as additional tables if needed:

| Parquet file | Powers |
|---|---|
| `agg_commodity_cohort_yoy.parquet` | Page 2 commodity × cohort matrix |
| `agg_dept_yoy_by_cohort.parquet` | Page 2 department-level summary |
| `agg_household_campaign_lift.parquet` | Page 4 diff-in-diff marketing lift |
| `agg_promo_sales_weekly.parquet` | Page 5 display/mailer sales lift |

---

## Files in this folder

| File | Description |
|---|---|
| `report.json` | Page and visual definitions (empty sections until pages are built) |
| `definition.pbir` | PBIP report metadata — binds to `../dunnhumby-complete-journey.SemanticModel` |
| `version.json` | Report format version |
| `StaticResources/SharedResources/BaseThemes/PLM-Complete-Journey.json` | PLM brand theme file |
| `.pbi/localSettings.json` | Local developer settings — not committed |
| `.platform` | Fabric platform metadata |
