# dunnhumby — The Complete Journey

Analysis workspace for the dunnhumby "Complete Journey" retail dataset. Tracks 2,500 households over ~2 years of retail transactions, with demographics, marketing campaigns, coupons, and in-store promotional data.

**Goal:** Answer the five Kaggle research questions about household spending trends, category shifts, demographic drivers, and direct-marketing effectiveness — delivered as a Power BI dashboard.

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

### Step 1 — Build the Parquet files

```bash
# Install Python dependencies
pip install -r requirements.txt

# Build core dims + facts from raw CSVs (~15–30 s)
python scripts/build_parquet.py

# Build metadata parquets + pre-computed aggregates (~2–5 min)
python scripts/build_aux_parquet.py
```

See `scripts/README.md` for full details.

### Step 2 — Open in Power BI

1. Open **`dunnhumby-complete-journey.pbip`** in Power BI Desktop (version June 2023 or later).
2. When prompted, update the data source path to your local `data/parquet_parking/` folder.
3. **Refresh** the model — all relationships, measures, and the PLM theme are already wired.

> **Why `.pbip` instead of `.pbix`?** The PBIP format stores the report and semantic model as plain-text JSON/Parquet files, making the project version-control friendly. See `dunnhumby-complete-journey.SemanticModel/README.md` for what's already configured.

---

## Repository layout

```
dunnhumby-complete-journey/
│
├── dunnhumby-complete-journey.pbip          # Power BI project entry point — open this
├── dunnhumby-complete-journey.Report/       # Power BI report definition (PBIP format)
│   ├── README.md                            # Report structure + current state
│   ├── report.json                          # Page and visual definitions
│   ├── definition.pbir                      # Report metadata
│   └── StaticResources/SharedResources/
│       └── BaseThemes/PLM-Complete-Journey.json  # PLM brand theme
│
├── dunnhumby-complete-journey.SemanticModel/ # Power BI semantic model (PBIP format)
│   ├── README.md                            # Model structure, tables, relationships
│   ├── model.bim                            # Full model definition (tables, measures, relationships)
│   └── definition.pbism                     # Model metadata
│
├── data/
│   ├── raw/                                 # CSVs from Kaggle (gitignored)
│   ├── processed/                           # Intermediate outputs (gitignored)
│   └── parquet_parking/                     # Power BI-ready Parquet files + model spec
│       ├── README.md                        # Ingestion guide + full table inventory
│       ├── _model.json                      # Canonical model spec (tables, columns, relationships, measures)
│       ├── measures.dax                     # All DAX measures, ready to paste
│       ├── storyboard.json                  # Page-by-page dashboard layout
│       ├── theme.json                       # Power BI theme (PLM brand colors, fonts)
│       ├── investigation_findings.md        # Narrative findings with headline numbers
│       ├── investigation_findings.json      # Validation targets + KPI priors
│       ├── dim_*.parquet                    # Dimension tables
│       ├── fact_*.parquet                   # Fact tables
│       ├── bridge_*.parquet                 # M:N bridge tables
│       ├── agg_*.parquet                    # Pre-computed analytical aggregates
│       └── _*.parquet                       # Metadata parquets (_tables, _columns, etc.)
│
├── annotation/                              # Annotated explainer video project
│   ├── README.md                            # Overview + execution instructions
│   ├── PICKUP-PROMPT.md                     # Paste into a new session to resume
│   ├── spec.md                              # Approved feature spec + user stories
│   ├── plan.md                              # Technical approach + slide design
│   ├── tasks.md                             # 19 atomic tasks across 7 phases
│   └── traceability.yaml                    # FR-001–FR-008 mapped to tasks
│
├── docs/
│   └── SCHEMA.md                            # Full schema reference + Power BI build plan
│
├── scripts/
│   ├── README.md                            # ETL pipeline documentation
│   ├── build_parquet.py                     # Builds dims + facts from raw CSVs
│   └── build_aux_parquet.py                 # Builds metadata parquets + aggregates
│
├── .planning/                               # Internal planning specs (dream-studio)
├── .sessions/                               # Session handoff and recap notes
├── requirements.txt
└── README.md
```

---

## Documentation map

| Document | What it covers |
|---|---|
| `dunnhumby-complete-journey.SemanticModel/README.md` | Semantic model structure — tables loaded, all relationships, measures, data source config |
| `dunnhumby-complete-journey.Report/README.md` | Report structure — current page state, theme applied, storyboard reference |
| `docs/SCHEMA.md` | Full per-table column reference, data quality quirks, constellation schema diagram, Power BI build plan, DAX patterns, research question mapping |
| `data/parquet_parking/README.md` | Parquet file inventory, ETL decisions baked into each table |
| `scripts/README.md` | How to run the ETL scripts, what each produces, runtime estimates |
| `annotation/README.md` | Annotated video plan — executive and analyst explainer for the dashboard |

---

## Prerequisites

- **Python 3.9+** with `pandas >= 2.0` and `pyarrow >= 14.0` (see `requirements.txt`)
- **Power BI Desktop** June 2023 or later (PBIP format support required)
- **Disk space:** ~700 MB for raw CSVs; ~50 MB for Parquet outputs
