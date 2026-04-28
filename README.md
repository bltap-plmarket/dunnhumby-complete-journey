# dunnhumby — The Complete Journey

Analysis workspace for the dunnhumby "Complete Journey" retail dataset from Kaggle.

## Dataset

- Source: https://www.kaggle.com/datasets/frtgnn/dunnhumby-the-complete-journey/data
- Slug: `frtgnn/dunnhumby-the-complete-journey`

Tracks 2,500 households over two years across transactions, demographics, products, campaigns, coupons, and causal data.

## Get the data

The raw CSVs are not committed (see `.gitignore`). Two ways to get them:

**Option 1 — GitHub Release (no Kaggle account needed):**

Download `dunnhumby-complete-journey-data.zip` (~136 MB) from the
[v1.0-data release](https://github.com/bltap-plmarket/dunnhumby-complete-journey/releases/tag/v1.0-data)
and unzip into `data/raw/`.

**Option 2 — Kaggle CLI:**

```bash
# one-time: place your Kaggle API token at ~/.kaggle/kaggle.json
kaggle datasets download -d frtgnn/dunnhumby-the-complete-journey -p data/raw --unzip
```

## Layout

```
data/raw/        # CSVs from Kaggle (gitignored)
data/processed/  # derived/cleaned data (gitignored)
notebooks/       # exploratory notebooks
src/             # reusable code
```
