"""Build metadata-as-parquet + pre-computed analytical aggregates.

Outputs (under data/parquet_parking/):

  Metadata (mirrors _model.json in tabular form for skills that prefer parquet):
    _measures.parquet          all DAX measures
    _tables.parquet            table-level metadata
    _columns.parquet           column-level metadata
    _relationships.parquet     relationships
    _hierarchies.parquet       hierarchies

  Pre-computed analytical aggregates (powers the heavy visuals):
    agg_commodity_cohort_yoy.parquet     commodity x HH_Trend x Y1/Y2 sales (Page 2)
    agg_household_campaign_lift.parquet  per-household pre/post spend per campaign (Page 4)
    agg_promo_sales_weekly.parquet       (PRODUCT_ID, WEEK_NO) sales joined to display/mailer state (Page 5)
    agg_dept_yoy_by_cohort.parquet       department x HH_Trend x Y1/Y2 sales (Page 2 secondary)

The intent: a Power BI build skill can either materialize the model from
_model.json + measures.dax, or load the metadata parquets directly. The
agg_*.parquet files give Page 2/4/5 visuals their data without requiring
DAX heroics on day one.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PQ   = ROOT / "data" / "parquet_parking"

PRE_WINDOW  = 28
POST_WINDOW = 28
OBSERVATION_END_DAY = 711


def step(msg: str) -> None:
    print(f"\n[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def write(df: pd.DataFrame, name: str) -> None:
    path = PQ / f"{name}.parquet"
    df.to_parquet(path, index=False, compression="zstd")
    print(f"   wrote {name}.parquet  rows={len(df):>7,}  size={path.stat().st_size/1e6:>6.2f} MB", flush=True)


# ---------------------------------------------------------------------------
# Metadata parquets (derived from _model.json)
# ---------------------------------------------------------------------------
def build_metadata_parquets() -> None:
    step("Building metadata parquets from _model.json")
    model = json.loads((PQ / "_model.json").read_text(encoding="utf-8"))

    # _tables.parquet
    tables = pd.DataFrame([
        {
            "table_name":   t["name"],
            "source_file":  t.get("source"),
            "kind":         t.get("kind"),
            "grain":        t.get("grain"),
            "primary_key":  t.get("primaryKey"),
            "row_count":    t.get("rowCount"),
            "is_storytelling_table": t.get("isStorytellingTable", False),
            "comment":      t.get("$comment", ""),
        }
        for t in model["tables"]
    ])
    write(tables, "_tables")

    # _columns.parquet
    cols = []
    for t in model["tables"]:
        for c in t.get("columns", []):
            cols.append({
                "table_name":  t["name"],
                "column_name": c["name"],
                "data_type":   c.get("type"),
                "description": c.get("description", ""),
            })
    write(pd.DataFrame(cols), "_columns")

    # _relationships.parquet
    rels = pd.DataFrame([
        {
            "from_table":  r["from"],
            "from_column": r["fromColumn"],
            "to_table":    r["to"],
            "to_column":   r["toColumn"],
            "cardinality": r["cardinality"],
            "cross_filter": r["crossFilter"],
            "comment":     r.get("$comment", ""),
        }
        for r in model["relationships"]
    ])
    write(rels, "_relationships")

    # _measures.parquet
    measures = pd.DataFrame([
        {
            "measure_name":  m["name"],
            "host_table":    m["table"],
            "expression":    m["expression"],
            "format_string": m.get("format", ""),
            "description":   m.get("description", ""),
            # Lightweight category tag for the skill to group measures in the field list.
            "category":      categorize_measure(m["name"]),
        }
        for m in model["measures"]
    ])
    write(measures, "_measures")

    # _hierarchies.parquet  (one row per level)
    hier = []
    for t in model["tables"]:
        for h in t.get("hierarchies", []):
            for level_idx, level in enumerate(h["levels"], start=1):
                hier.append({
                    "table_name":     t["name"],
                    "hierarchy_name": h["name"],
                    "level_order":    level_idx,
                    "level_column":   level,
                })
    write(pd.DataFrame(hier), "_hierarchies")


def categorize_measure(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ["y1", "y2", "yoy"]):                return "YoY"
    if any(k in n for k in ["lift", "exposed", "redeem", "redemption"]): return "Marketing"
    if any(k in n for k in ["display", "mailer"]):              return "Promotion"
    if any(k in n for k in ["growing", "declining", "trend"]):  return "Cohort"
    if "discount" in n:                                         return "Discount"
    return "Headline"


# ---------------------------------------------------------------------------
# Analytical aggregates
# ---------------------------------------------------------------------------
def build_commodity_cohort_yoy(ft: pd.DataFrame, hh: pd.DataFrame, dp: pd.DataFrame) -> None:
    step("Building agg_commodity_cohort_yoy")
    df = ft.merge(hh[["household_key", "HH_Trend"]], on="household_key", how="left")
    df = df.merge(dp[["PRODUCT_ID", "DEPARTMENT", "COMMODITY_DESC", "Has_Real_Category"]], on="PRODUCT_ID", how="left")
    df = df[df["Has_Real_Category"] == True]
    df["Year_Idx"] = ((df["DAY"] - 1) // 365) + 1

    grouped = (
        df.groupby(["COMMODITY_DESC", "DEPARTMENT", "HH_Trend", "Year_Idx"], as_index=False)
          .agg(Sales=("SALES_VALUE", "sum"),
               Units=("QUANTITY", "sum"),
               Households=("household_key", "nunique"))
    )

    pivoted = (
        grouped.pivot_table(
            index=["COMMODITY_DESC", "DEPARTMENT", "HH_Trend"],
            columns="Year_Idx",
            values=["Sales", "Units", "Households"],
            fill_value=0,
        )
    )
    pivoted.columns = [f"{m}_Y{int(y)}" for m, y in pivoted.columns]
    pivoted = pivoted.reset_index()
    pivoted["Sales_Delta"]     = pivoted["Sales_Y2"] - pivoted["Sales_Y1"]
    pivoted["Sales_Delta_Pct"] = (
        (pivoted["Sales_Y2"] - pivoted["Sales_Y1"])
        / pivoted["Sales_Y1"].where(pivoted["Sales_Y1"] > 0)
    )
    write(pivoted, "agg_commodity_cohort_yoy")


def build_dept_yoy_by_cohort(ft: pd.DataFrame, hh: pd.DataFrame, dp: pd.DataFrame) -> None:
    step("Building agg_dept_yoy_by_cohort")
    df = ft.merge(hh[["household_key", "HH_Trend"]], on="household_key", how="left")
    df = df.merge(dp[["PRODUCT_ID", "DEPARTMENT"]], on="PRODUCT_ID", how="left")
    df["Year_Idx"] = ((df["DAY"] - 1) // 365) + 1

    grouped = (
        df.groupby(["DEPARTMENT", "HH_Trend", "Year_Idx"], as_index=False)
          .agg(Sales=("SALES_VALUE", "sum"))
          .pivot_table(index=["DEPARTMENT", "HH_Trend"], columns="Year_Idx", values="Sales", fill_value=0)
    )
    grouped.columns = [f"Sales_Y{int(c)}" for c in grouped.columns]
    grouped = grouped.reset_index()
    grouped["Sales_Delta"]     = grouped["Sales_Y2"] - grouped["Sales_Y1"]
    grouped["Sales_Delta_Pct"] = (grouped["Sales_Y2"] - grouped["Sales_Y1"]) / grouped["Sales_Y1"].where(grouped["Sales_Y1"] > 0)
    write(grouped, "agg_dept_yoy_by_cohort")


def build_household_campaign_lift(ft: pd.DataFrame, hh: pd.DataFrame, dc: pd.DataFrame, fcr: pd.DataFrame) -> None:
    """For each (household, campaign), compute pre/post spend windows.

    This gives the dashboard an honest lift analysis without complex DAX:
        - exposed: household received this campaign (1)
        - exposed: household did NOT receive this campaign (0) -> control
        - pre_spend  = sum sales in [START_DAY - 28, START_DAY - 1]
        - post_spend = sum sales in [START_DAY,      START_DAY + 28 - 1]
        - has_complete_post_window: campaign window fits in observation
    """
    step("Building agg_household_campaign_lift")

    # Prep: per-household-day spend
    hh_day = ft.groupby(["household_key", "DAY"], as_index=False)["SALES_VALUE"].sum()

    # Cumulative spend at end of each day per household (sorted): allows fast window queries
    hh_day = hh_day.sort_values(["household_key", "DAY"])
    hh_day["cum"] = hh_day.groupby("household_key")["SALES_VALUE"].cumsum()

    def cum_at(household: int, day: int) -> float:
        """Cumulative spend for household up to and INCLUDING `day`."""
        row = hh_day_lookup.get(household)
        if row is None or len(row) == 0:
            return 0.0
        # row is a pd.Series indexed by DAY -> cum
        below = row[row.index <= day]
        return float(below.iloc[-1]) if len(below) else 0.0

    # Build per-household lookup of cumulative spend (pre-sorted)
    hh_day_lookup = {
        hk: grp.set_index("DAY")["cum"]
        for hk, grp in hh_day.groupby("household_key")
    }

    exposed_pairs = set(map(tuple, fcr[["household_key", "CAMPAIGN"]].values.tolist()))

    rows = []
    households = hh["household_key"].tolist()
    campaigns  = dc[["CAMPAIGN", "CAMPAIGN_TYPE", "START_DAY", "END_DAY", "Extends_Past_Observation"]].to_dict("records")

    for c in campaigns:
        cs = int(c["START_DAY"])
        pre_lo  = max(1, cs - PRE_WINDOW)
        pre_hi  = cs - 1
        post_lo = cs
        post_hi = min(OBSERVATION_END_DAY, cs + POST_WINDOW - 1)
        has_complete_post = (cs + POST_WINDOW - 1) <= OBSERVATION_END_DAY

        for hk in households:
            pre_cum_hi  = cum_at(hk, pre_hi)
            pre_cum_lo  = cum_at(hk, pre_lo - 1)
            post_cum_hi = cum_at(hk, post_hi)
            post_cum_lo = cum_at(hk, post_lo - 1)
            pre  = pre_cum_hi  - pre_cum_lo
            post = post_cum_hi - post_cum_lo
            rows.append({
                "household_key":              hk,
                "CAMPAIGN":                   int(c["CAMPAIGN"]),
                "CAMPAIGN_TYPE":              c["CAMPAIGN_TYPE"],
                "Exposed":                    (hk, int(c["CAMPAIGN"])) in exposed_pairs,
                "Pre_Spend":                  pre,
                "Post_Spend":                 post,
                "Spend_Delta":                post - pre,
                "Has_Complete_Post_Window":   has_complete_post,
                "Extends_Past_Observation":   bool(c["Extends_Past_Observation"]),
            })

    df = pd.DataFrame(rows)
    write(df, "agg_household_campaign_lift")


def build_promo_sales_weekly(ft: pd.DataFrame) -> None:
    """For Page 5: sales aggregated to (PRODUCT_ID, WEEK_NO) joined to display state."""
    step("Building agg_promo_sales_weekly")
    fc = pd.read_parquet(PQ / "fact_causal_weekly.parquet")
    sales = (
        ft.groupby(["PRODUCT_ID", "WEEK_NO"], as_index=False)
          .agg(Sales=("SALES_VALUE", "sum"),
               Units=("QUANTITY", "sum"),
               Baskets=("BASKET_ID", "nunique"))
    )
    merged = sales.merge(fc, on=["PRODUCT_ID", "WEEK_NO"], how="left")
    # Fill missing promo state with False/0 (product-week combos with sales but no causal record)
    merged["OnDisplay_AnyStore"] = merged["OnDisplay_AnyStore"].fillna(False)
    merged["InMailer_AnyStore"]  = merged["InMailer_AnyStore"].fillna(False)
    merged["Stores_OnDisplay"]   = merged["Stores_OnDisplay"].fillna(0).astype("int32")
    merged["Stores_InMailer"]    = merged["Stores_InMailer"].fillna(0).astype("int32")
    merged["Total_Stores"]       = merged["Total_Stores"].fillna(0).astype("int32")
    merged["DisplayShare"]       = merged["DisplayShare"].fillna(0)
    merged["MailerShare"]        = merged["MailerShare"].fillna(0)
    write(merged, "agg_promo_sales_weekly")


# ---------------------------------------------------------------------------
def main() -> int:
    t0 = time.time()
    print(f"Output: {PQ}")

    build_metadata_parquets()

    step("Loading source parquets for aggregations")
    ft = pd.read_parquet(PQ / "fact_transactions.parquet")
    hh = pd.read_parquet(PQ / "dim_household.parquet")
    dp = pd.read_parquet(PQ / "dim_product.parquet")
    dc = pd.read_parquet(PQ / "dim_campaign.parquet")
    fcr = pd.read_parquet(PQ / "fact_campaign_received.parquet")

    build_commodity_cohort_yoy(ft, hh, dp)
    build_dept_yoy_by_cohort(ft, hh, dp)
    build_household_campaign_lift(ft, hh, dc, fcr)
    build_promo_sales_weekly(ft)

    elapsed = time.time() - t0
    step(f"DONE in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
