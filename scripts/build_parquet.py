"""Build prepped Parquet files from raw dunnhumby CSVs for Power BI ingestion.

Outputs (under data/parquet_parking/):

  Dimensions
    dim_date.parquet              711 rows, synthetic calendar
    dim_household.parquet         2,500 rows; demographics left-joined,
                                  HasDemographics flag, ReceivedAnyCampaign,
                                  RedeemedAnyCoupon, Spend_Y1/Y2, HH_Trend
    dim_product.parquet           ~92K rows; cleaned hierarchy + flags
    dim_store.parquet             distinct STORE_IDs
    dim_campaign.parquet          30 rows; type, days, week ranges, duration
    dim_coupon.parquet            distinct COUPON_UPCs

  Bridges
    bridge_coupon_product.parquet COUPON_UPC <-> PRODUCT_ID (incl. CAMPAIGN)

  Facts
    fact_transactions.parquet     line-item; sign-corrected discounts +
                                  derived gross_sales
    fact_causal_weekly.parquet    pre-aggregated (PRODUCT_ID, WEEK_NO)
                                  with OnDisplay/InMailer flags + store counts
    fact_coupon_redemption.parquet
    fact_campaign_received.parquet  factless

The model targets a constellation schema (see docs/SCHEMA.md). Each output
file is purpose-built so a Power BI author can load it directly and wire
relationships per docs/SCHEMA.md section 9.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "parquet_parking"
OUT.mkdir(parents=True, exist_ok=True)


def step(msg: str) -> None:
    print(f"\n[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def write(df: pd.DataFrame, name: str) -> None:
    path = OUT / f"{name}.parquet"
    df.to_parquet(path, index=False, compression="zstd")
    size_mb = path.stat().st_size / 1e6
    print(f"   wrote {name}.parquet  rows={len(df):>10,}  size={size_mb:>7.2f} MB", flush=True)


# ---------------------------------------------------------------------------
# 1. Dim_Date  (synthetic calendar over DAY 1..711)
# ---------------------------------------------------------------------------
def build_dim_date() -> None:
    step("Building dim_date")
    days = pd.DataFrame({"Day_Idx": range(1, 712)})
    days["Week_No"]    = ((days["Day_Idx"] - 1) // 7) + 1            # 1..102
    days["Year_Idx"]   = ((days["Day_Idx"] - 1) // 365) + 1          # 1 or 2
    days["Half_Idx"]   = ((days["Day_Idx"] - 1) // 182) + 1          # 1..4
    days["Quarter_Idx"]= ((days["Day_Idx"] - 1) // 91) + 1           # 1..8
    days["Month_Idx"]  = ((days["Day_Idx"] - 1) // 30) + 1           # 1..24
    days["DayOfWeek"]  = ((days["Day_Idx"] - 1) % 7) + 1             # 1..7

    # Anchor to a synthetic calendar (Day 1 = 2020-01-01) for nicer slicers.
    anchor = pd.Timestamp("2020-01-01")
    days["AnchorDate"] = anchor + pd.to_timedelta(days["Day_Idx"] - 1, unit="D")
    days["YearMonth"]  = days["AnchorDate"].dt.strftime("%Y-%m")
    days["YearLabel"]  = "Y" + days["Year_Idx"].astype(str)
    days["WeekLabel"]  = "W" + days["Week_No"].astype(str).str.zfill(3)

    write(days, "dim_date")


# ---------------------------------------------------------------------------
# 2. Dim_Product  (cleaned hierarchy + flag for usable categories)
# ---------------------------------------------------------------------------
def build_dim_product() -> None:
    step("Building dim_product")
    p = pd.read_csv(RAW / "product.csv")
    p["DEPARTMENT"]         = p["DEPARTMENT"].fillna("(unknown)").astype("string")
    p["BRAND"]              = p["BRAND"].fillna("(unknown)").astype("string")
    p["COMMODITY_DESC"]     = p["COMMODITY_DESC"].fillna("(unknown)").astype("string")
    p["SUB_COMMODITY_DESC"] = p["SUB_COMMODITY_DESC"].fillna("(unknown)").astype("string")
    p["CURR_SIZE_OF_PRODUCT"] = p["CURR_SIZE_OF_PRODUCT"].fillna("").str.strip().astype("string")

    placeholder_mask = (
        p["COMMODITY_DESC"].str.contains("NO COMMODITY", case=False, na=False)
        | p["SUB_COMMODITY_DESC"].str.contains("NO SUBCOMMODITY", case=False, na=False)
    )
    p["Has_Real_Category"] = ~placeholder_mask
    p["Is_Private_Brand"]  = (p["BRAND"] == "Private")

    write(p, "dim_product")


# ---------------------------------------------------------------------------
# 3. Dim_Campaign  (with derived weeks + duration)
# ---------------------------------------------------------------------------
def build_dim_campaign() -> None:
    step("Building dim_campaign")
    c = pd.read_csv(RAW / "campaign_desc.csv")
    c = c.rename(columns={"DESCRIPTION": "CAMPAIGN_TYPE"})
    c["Duration_Days"] = c["END_DAY"] - c["START_DAY"]
    c["Start_Week"]    = ((c["START_DAY"] - 1) // 7) + 1
    c["End_Week"]      = ((c["END_DAY"]   - 1) // 7) + 1
    c["Extends_Past_Observation"] = c["END_DAY"] > 711
    c = c.sort_values("START_DAY").reset_index(drop=True)
    write(c, "dim_campaign")


# ---------------------------------------------------------------------------
# 4. Bridge_CouponProduct  (M:N coupon <-> product, incl. campaign)
# ---------------------------------------------------------------------------
def build_bridge_coupon_product() -> None:
    step("Building bridge_coupon_product")
    cp = pd.read_csv(RAW / "coupon.csv")
    cp = cp[["COUPON_UPC", "PRODUCT_ID", "CAMPAIGN"]].drop_duplicates().reset_index(drop=True)
    write(cp, "bridge_coupon_product")


# ---------------------------------------------------------------------------
# 5. Dim_Coupon  (distinct coupons across coupon.csv + redemptions)
# ---------------------------------------------------------------------------
def build_dim_coupon() -> None:
    step("Building dim_coupon")
    cp_master = pd.read_csv(RAW / "coupon.csv", usecols=["COUPON_UPC", "CAMPAIGN"])
    rd        = pd.read_csv(RAW / "coupon_redempt.csv", usecols=["COUPON_UPC", "CAMPAIGN"])

    products_per_coupon = (
        pd.read_csv(RAW / "coupon.csv", usecols=["COUPON_UPC", "PRODUCT_ID"])
          .drop_duplicates()
          .groupby("COUPON_UPC", as_index=False)
          .size()
          .rename(columns={"size": "Eligible_Product_Count"})
    )

    redempt_counts = (
        rd.groupby("COUPON_UPC", as_index=False)
          .size()
          .rename(columns={"size": "Redemption_Count"})
    )

    all_coupons = pd.concat([cp_master, rd], ignore_index=True).drop_duplicates(subset=["COUPON_UPC"])
    dim = (
        all_coupons[["COUPON_UPC", "CAMPAIGN"]]
        .merge(products_per_coupon, on="COUPON_UPC", how="left")
        .merge(redempt_counts,      on="COUPON_UPC", how="left")
    )
    dim["Eligible_Product_Count"] = dim["Eligible_Product_Count"].fillna(0).astype("int64")
    dim["Redemption_Count"]       = dim["Redemption_Count"].fillna(0).astype("int64")
    dim["Was_Redeemed"]           = dim["Redemption_Count"] > 0
    write(dim, "dim_coupon")


# ---------------------------------------------------------------------------
# 6. Fact_Transactions  (sign-corrected discounts + derived gross_sales)
# ---------------------------------------------------------------------------
def build_fact_transactions() -> pd.DataFrame:
    step("Building fact_transactions (this reads 136 MB of CSV)")
    t = pd.read_csv(
        RAW / "transaction_data.csv",
        dtype={
            "household_key":       "int32",
            "BASKET_ID":           "int64",
            "DAY":                 "int16",
            "PRODUCT_ID":          "int32",
            "QUANTITY":            "int64",   # outliers up to 89638
            "SALES_VALUE":         "float64",
            "STORE_ID":            "int32",
            "RETAIL_DISC":         "float64",
            "TRANS_TIME":          "int16",
            "WEEK_NO":             "int8",
            "COUPON_DISC":         "float64",
            "COUPON_MATCH_DISC":   "float64",
        },
    )
    # Sign-correct: discounts in source are negative; flip to positive measures.
    for col in ("RETAIL_DISC", "COUPON_DISC", "COUPON_MATCH_DISC"):
        t[col] = t[col].abs()
    t["GROSS_SALES"] = t["SALES_VALUE"] + t["RETAIL_DISC"] + t["COUPON_DISC"] + t["COUPON_MATCH_DISC"]
    t["TOTAL_DISC"]  = t["RETAIL_DISC"] + t["COUPON_DISC"] + t["COUPON_MATCH_DISC"]

    # Time-of-day derived field (TRANS_TIME is HHMM as int).
    t["TRANS_HOUR"] = (t["TRANS_TIME"] // 100).astype("int8")

    write(t, "fact_transactions")
    return t


# ---------------------------------------------------------------------------
# 7. Dim_Store  (derived from transactions + causal)
# ---------------------------------------------------------------------------
def build_dim_store(fact_txn: pd.DataFrame) -> None:
    step("Building dim_store")
    txn_stores = pd.DataFrame({"STORE_ID": fact_txn["STORE_ID"].unique()})
    # also pull stores from causal (some may only appear there)
    causal_stores = pd.DataFrame({
        "STORE_ID": pacsv.read_csv(RAW / "causal_data.csv").column("STORE_ID").unique().to_pylist()
    })
    stores = pd.concat([txn_stores, causal_stores], ignore_index=True).drop_duplicates().sort_values("STORE_ID")
    stores = stores.reset_index(drop=True)
    stores["STORE_ID"] = stores["STORE_ID"].astype("int32")
    write(stores, "dim_store")


# ---------------------------------------------------------------------------
# 8. Fact_CampaignReceived  (factless fact; drop redundant DESCRIPTION)
# ---------------------------------------------------------------------------
def build_fact_campaign_received() -> None:
    step("Building fact_campaign_received")
    ct = pd.read_csv(RAW / "campaign_table.csv", usecols=["household_key", "CAMPAIGN"])
    ct = ct.drop_duplicates().reset_index(drop=True)
    write(ct, "fact_campaign_received")


# ---------------------------------------------------------------------------
# 9. Fact_CouponRedemption
# ---------------------------------------------------------------------------
def build_fact_coupon_redemption() -> None:
    step("Building fact_coupon_redemption")
    cr = pd.read_csv(RAW / "coupon_redempt.csv")
    write(cr, "fact_coupon_redemption")


# ---------------------------------------------------------------------------
# 10. Fact_Causal_Weekly  (36.8M rows -> ~few M; pyarrow streaming aggregate)
# ---------------------------------------------------------------------------
def build_fact_causal_weekly() -> None:
    step("Aggregating causal_data.csv (36.8M rows -> product x week)")
    tbl = pacsv.read_csv(RAW / "causal_data.csv")
    # Boolean flags: any non-zero code means "on display" / "in mailer"
    on_display = pc.not_equal(tbl.column("display"), pa.scalar("0"))
    in_mailer  = pc.not_equal(tbl.column("mailer"),  pa.scalar("0"))
    tbl = tbl.append_column("OnDisplay", on_display)
    tbl = tbl.append_column("InMailer",  in_mailer)

    # Aggregate to (PRODUCT_ID, WEEK_NO):
    #   OnDisplay_AnyStore = max(OnDisplay)   (i.e., OR)
    #   InMailer_AnyStore  = max(InMailer)
    #   Stores_OnDisplay   = sum(OnDisplay::int)
    #   Stores_InMailer    = sum(InMailer::int)
    #   Total_Stores       = count distinct STORE_ID per (product, week)
    df = tbl.to_pandas()
    df["OnDisplay_i"] = df["OnDisplay"].astype("int8")
    df["InMailer_i"]  = df["InMailer"].astype("int8")
    grouped = (
        df.groupby(["PRODUCT_ID", "WEEK_NO"], as_index=False)
          .agg(
              OnDisplay_AnyStore=("OnDisplay", "max"),
              InMailer_AnyStore =("InMailer",  "max"),
              Stores_OnDisplay  =("OnDisplay_i","sum"),
              Stores_InMailer   =("InMailer_i", "sum"),
              Total_Stores      =("STORE_ID",   "nunique"),
          )
    )
    grouped["PRODUCT_ID"]      = grouped["PRODUCT_ID"].astype("int32")
    grouped["WEEK_NO"]         = grouped["WEEK_NO"].astype("int8")
    grouped["Stores_OnDisplay"]= grouped["Stores_OnDisplay"].astype("int32")
    grouped["Stores_InMailer"] = grouped["Stores_InMailer"].astype("int32")
    grouped["Total_Stores"]    = grouped["Total_Stores"].astype("int32")
    grouped["DisplayShare"]    = grouped["Stores_OnDisplay"] / grouped["Total_Stores"]
    grouped["MailerShare"]     = grouped["Stores_InMailer"]  / grouped["Total_Stores"]
    write(grouped, "fact_causal_weekly")


# ---------------------------------------------------------------------------
# 11. Dim_Household
#     - All 2,500 households (from transactions)
#     - Demographics left-joined (~32% coverage) + HasDemographics flag
#     - ReceivedAnyCampaign, RedeemedAnyCoupon flags
#     - Y1/Y2 spend + HH_Trend classification (the dashboard's main slicer)
# ---------------------------------------------------------------------------
def build_dim_household(fact_txn: pd.DataFrame) -> None:
    step("Building dim_household with trend classification")
    households = pd.DataFrame({"household_key": sorted(fact_txn["household_key"].unique())})

    # Demographics (left join)
    demo = pd.read_csv(RAW / "hh_demographic.csv")
    households = households.merge(demo, on="household_key", how="left")
    households["HasDemographics"] = households["AGE_DESC"].notna()

    # Fill demographic blanks for slicer cleanliness.
    for col in ["AGE_DESC", "MARITAL_STATUS_CODE", "INCOME_DESC", "HOMEOWNER_DESC",
                "HH_COMP_DESC", "HOUSEHOLD_SIZE_DESC", "KID_CATEGORY_DESC"]:
        households[col] = households[col].fillna("(not surveyed)").astype("string")

    # ReceivedAnyCampaign
    camp_hh = pd.read_csv(RAW / "campaign_table.csv", usecols=["household_key"])["household_key"].unique()
    households["ReceivedAnyCampaign"] = households["household_key"].isin(camp_hh)

    # Campaign count
    camp_counts = (
        pd.read_csv(RAW / "campaign_table.csv", usecols=["household_key"])
          .groupby("household_key").size().rename("Campaign_Count")
    )
    households = households.merge(camp_counts, on="household_key", how="left")
    households["Campaign_Count"] = households["Campaign_Count"].fillna(0).astype("int16")

    # RedeemedAnyCoupon
    redempt_hh = pd.read_csv(RAW / "coupon_redempt.csv", usecols=["household_key"])["household_key"].unique()
    households["RedeemedAnyCoupon"] = households["household_key"].isin(redempt_hh)

    redempt_counts = (
        pd.read_csv(RAW / "coupon_redempt.csv", usecols=["household_key"])
          .groupby("household_key").size().rename("Redemption_Count")
    )
    households = households.merge(redempt_counts, on="household_key", how="left")
    households["Redemption_Count"] = households["Redemption_Count"].fillna(0).astype("int16")

    # Spend per year (Year 1 = DAY 1..365, Year 2 = DAY 366..711)
    fact_txn = fact_txn.assign(Year_Idx=((fact_txn["DAY"] - 1) // 365) + 1)
    yr_spend = (
        fact_txn.groupby(["household_key", "Year_Idx"], as_index=False)["SALES_VALUE"].sum()
                .pivot(index="household_key", columns="Year_Idx", values="SALES_VALUE")
                .rename(columns={1: "Spend_Y1", 2: "Spend_Y2"})
                .fillna(0.0)
                .reset_index()
    )
    households = households.merge(yr_spend, on="household_key", how="left")
    households["Spend_Y1"] = households["Spend_Y1"].fillna(0.0)
    households["Spend_Y2"] = households["Spend_Y2"].fillna(0.0)
    households["Spend_Total"]    = households["Spend_Y1"] + households["Spend_Y2"]
    households["Spend_Delta"]    = households["Spend_Y2"] - households["Spend_Y1"]
    households["Spend_Delta_Pct"] = (
        households["Spend_Delta"] / households["Spend_Y1"].where(households["Spend_Y1"] > 0)
    )

    def classify(row):
        if row["Spend_Y1"] == 0 and row["Spend_Y2"] == 0:
            return "Inactive"
        if row["Spend_Y1"] == 0:
            return "New"
        if row["Spend_Y2"] == 0:
            return "Lost"
        d = row["Spend_Delta_Pct"]
        if d > 0.05:
            return "Growing"
        if d < -0.05:
            return "Declining"
        return "Flat"

    households["HH_Trend"] = households.apply(classify, axis=1).astype("string")

    # Active basket count per household
    basket_counts = (
        fact_txn.groupby("household_key")["BASKET_ID"].nunique().rename("Basket_Count")
    )
    households = households.merge(basket_counts, on="household_key", how="left")
    households["Basket_Count"] = households["Basket_Count"].fillna(0).astype("int32")
    households["Avg_Basket_Value"] = households["Spend_Total"] / households["Basket_Count"].where(households["Basket_Count"] > 0)

    # Tenure: first/last day with a transaction
    day_range = fact_txn.groupby("household_key")["DAY"].agg(["min", "max"])
    day_range.columns = ["First_Day", "Last_Day"]
    households = households.merge(day_range, on="household_key", how="left")
    households["Active_Days"] = households["Last_Day"] - households["First_Day"] + 1

    write(households, "dim_household")


# ---------------------------------------------------------------------------
def main() -> int:
    t0 = time.time()
    print(f"Source: {RAW}")
    print(f"Output: {OUT}")

    # Order matters: fact_transactions feeds dim_store + dim_household.
    build_dim_date()
    build_dim_product()
    build_dim_campaign()
    build_bridge_coupon_product()
    build_dim_coupon()
    build_fact_campaign_received()
    build_fact_coupon_redemption()

    fact_txn = build_fact_transactions()
    build_dim_store(fact_txn)
    build_dim_household(fact_txn)

    # Free transactions before loading the 36M-row causal dataset.
    del fact_txn

    build_fact_causal_weekly()

    elapsed = time.time() - t0
    step(f"DONE in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
