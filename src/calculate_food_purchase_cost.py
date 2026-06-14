"""Calculate monthly and annual food purchase costs at cheapest markets."""

from pathlib import Path

import pandas as pd


DATA_DIR = Path(r"C:\Users\ASUS\PycharmProjects\PythonProject")
DEMAND_FILE = DATA_DIR / "MonthlyFoodDemand.csv"
PRICE_FILE = DATA_DIR / "FoodPrices_Clean.csv"
OUTPUT_FILE = DATA_DIR / "FoodPurchaseCost.csv"

COMMODITY_MAPPING = {
    "Lentils": "Lentils (black)",
}


def main() -> None:
    demand = pd.read_csv(DEMAND_FILE)
    prices = pd.read_csv(PRICE_FILE)

    demand_columns = {
        "camp_id",
        "camp_name",
        "commodity",
        "demand_kg_month",
    }
    price_columns = {"commodity", "market", "price_per_kg"}

    missing_demand_columns = demand_columns.difference(demand.columns)
    missing_price_columns = price_columns.difference(prices.columns)
    if missing_demand_columns or missing_price_columns:
        raise ValueError(
            f"Missing demand columns: {sorted(missing_demand_columns)}; "
            f"missing price columns: {sorted(missing_price_columns)}"
        )

    demand["commodity"] = demand["commodity"].astype(str).str.strip()
    demand["price_commodity"] = demand["commodity"].replace(COMMODITY_MAPPING)
    prices["commodity"] = prices["commodity"].astype(str).str.strip()
    demand["demand_kg_month"] = pd.to_numeric(
        demand["demand_kg_month"], errors="raise"
    )
    prices["price_per_kg"] = pd.to_numeric(
        prices["price_per_kg"], errors="raise"
    )

    prices = prices.dropna(subset=["commodity", "market", "price_per_kg"])
    prices = prices[prices["price_per_kg"] >= 0].copy()

    cheapest_prices = (
        prices.sort_values(
            ["commodity", "price_per_kg", "market"], kind="stable"
        )
        .drop_duplicates(subset="commodity", keep="first")
        [["commodity", "market", "price_per_kg"]]
        .rename(
            columns={
                "commodity": "price_commodity",
                "market": "selected_market",
            }
        )
    )

    purchase_cost = demand.merge(
        cheapest_prices,
        on="price_commodity",
        how="left",
        validate="many_to_one",
    )
    purchase_cost["monthly_purchase_cost"] = (
        purchase_cost["demand_kg_month"] * purchase_cost["price_per_kg"]
    )
    purchase_cost["annual_purchase_cost"] = (
        purchase_cost["monthly_purchase_cost"] * 12
    )
    unavailable = purchase_cost["price_per_kg"].isna()
    purchase_cost.loc[unavailable, "selected_market"] = "Not available"
    purchase_cost["notes"] = ""
    purchase_cost.loc[unavailable, "notes"] = "Price not available"

    purchase_cost = purchase_cost[
        [
            "camp_id",
            "camp_name",
            "commodity",
            "selected_market",
            "price_per_kg",
            "demand_kg_month",
            "monthly_purchase_cost",
            "annual_purchase_cost",
            "notes",
        ]
    ].sort_values(["camp_id", "commodity"], ignore_index=True)

    purchase_cost.to_csv(OUTPUT_FILE, index=False, float_format="%.6f")
    print(f"Created {OUTPUT_FILE} with {len(purchase_cost)} rows.")


if __name__ == "__main__":
    main()
