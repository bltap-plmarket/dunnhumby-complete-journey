# dunnhumby — The Complete Journey

Analysis workspace for the dunnhumby "Complete Journey" retail dataset. Tracks 2,500 households over ~2 years of retail transactions, with demographics, marketing campaigns, coupons, and in-store promotional data.

**Goal:** Answer the five Kaggle research questions about household spending trends, category shifts, demographic drivers, and direct-marketing effectiveness — delivered as a pre-modeled, Power BI-ready dataset.

## Dataset

- **Source:** [Kaggle — frtgnn/dunnhumby-the-complete-journey](https://www.kaggle.com/datasets/frtgnn/dunnhumby-the-complete-journey/data)
- **License:** DbCL-1.0 (Database Contents License)
- **Coverage:** 2,500 households · ~2-year window · 2.6M transactions · 30 marketing campaigns

### Research questions

1. How many customers are spending **more over time**? Less? Describe these customers.
2. Of households spending more, **which categories** are growing fastest?
3. Of households spending less, **which categories** are they disengaging from?
4. Which **demographic factors** (household size, income, children) drive spend and category engagement?
5. Is there evidence that **direct marketing improves overall engagement**?

See `docs/SCHEMA.md` §3 and §11 for the full analysis approach and DAX patterns.

---

## Get the data

Raw CSVs are gitignored. Two ways to download them:

**Option 1 — GitHub Release (no Kaggle account needed):**

Download `dunnhumby-complete-journey-data.zip` (~136 MB) from the
[v1.0-data release](https://github.com/bltap-plmarket/dunnhumby-complete-journey/releases/tag/v1.0-data)
and unzip into `data/raw/`.

**Option 2 — Kaggle CLI:**

```bash
pip install --user kaggle          # one-time
# Place your API token at ~/.kaggle/kaggle.json
# (from https://www.kaggle.com/settings → API → Create New Token)
kaggle datasets download -d frtgnn/dunnhumby-the-complete-journey -p data/raw --unzip
```

---

## Quick start

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Build core Parquet tables (dims + facts)
#    Reads: data/raw/  →  Writes: data/parquet_parking/
python scripts/build_parquet.py

# 3. Build metadata parquets + pre-computed analytical aggregates
#    Reads: data/parquet_parking/  →  Writes: more files to data/parquet_parking/
python scripts/build_aux_parquet.py
```

Both scripts are deterministic — re-running them is safe and produces identical output.

See `scripts/README.md` for runtime details, full output inventory, and dependency order.

---

## Load into Power BI

1. Open Power BI Desktop → **Get Data → Parquet** (or use the Folder connector).
2. Load all `*.parquet` files from `data/parquet_parking/`.
3. Wire relationships per `data/parquet_parking/README.md` (or `docs/SCHEMA.md` §9).
4. Mark `dim_date` as the date table, key column: `AnchorDate`.
5. Paste DAX measures from `data/parquet_parking/measures.dax`.
6. Apply the theme from `data/parquet_parking/theme.json`.

The storyboard (`data/parquet_parking/storyboard.json`) maps each research question to a dashboard page layout.

---

## Repository layout

```
dunnhumby-complete-journey/
├── data/
│   ├── raw/                         # CSVs from Kaggle (gitignored)
│   ├── processed/                   # intermediate outputs (gitignored)
│   └── parquet_parking/             # Power BI-ready Parquet files + model spec
│       ├── README.md                # ingestion guide + full table inventory
│       ├── _model.json              # canonical model spec (tables, columns, relationships, measures)
│       ├── measures.dax             # all DAX measures, ready to paste into Power BI
│       ├── storyboard.json          # page-by-page dashboard layout
│       ├── theme.json               # Power BI theme (colors, fonts)
│       ├── investigation_findings.md    # narrative findings with headline numbers
│       ├── investigation_findings.json  # validation targets + KPI priors
│       ├── dim_*.parquet            # dimension tables (date, household, product, store, campaign, coupon)
│       ├── fact_*.parquet           # fact tables (transactions, causal, redemption, campaign received)
│       ├── bridge_*.parquet         # M:N bridge tables (coupon ↔ product)
│       ├── agg_*.parquet            # pre-computed analytical aggregates (pages 2, 4, 5)
│       └── _*.parquet               # metadata parquets (_tables, _columns, _relationships, _measures, _hierarchies)
├── docs/
│   └── SCHEMA.md                    # full schema reference, data quality notes, Power BI build plan
├── scripts/
│   ├── README.md                    # ETL pipeline documentation
│   ├── build_parquet.py             # builds dims + facts from raw CSVs (~15–30 s)
│   └── build_aux_parquet.py         # builds metadata parquets + analytical aggregates (~2–5 min)
├── requirements.txt
└── README.md
```

---

## Documentation map

| Document | What it covers |
|---|---|
| `docs/SCHEMA.md` | Full per-table column reference, data quality quirks, constellation schema diagram, Power BI build plan (Dim_Date, Fact_Causal pre-agg, Dim_Household), DAX patterns, research question mapping |
| `data/parquet_parking/README.md` | Parquet file inventory, relationships to wire in Power BI, ETL decisions baked into each table |
| `scripts/README.md` | How to run the ETL scripts, what each produces, runtime estimates, dependency order |

---

## Prerequisites

- **Python 3.9+**
- **Packages:** `pandas >= 2.0`, `pyarrow >= 14.0` (see `requirements.txt`)
- **Power BI Desktop** for the report layer
- **Disk space:** ~700 MB for raw CSVs; ~50 MB for Parquet outputs
