# dunnhumby — The Complete Journey

Analysis workspace for the dunnhumby "Complete Journey" retail dataset from Kaggle.

## Dataset

- Source: https://www.kaggle.com/datasets/frtgnn/dunnhumby-the-complete-journey/data
- Slug: `frtgnn/dunnhumby-the-complete-journey`

Tracks 2,500 households over two years across transactions, demographics, products, campaigns, coupons, and causal data.

## Get the data

The raw CSVs are not committed (see `.gitignore`). To pull them locally:

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
