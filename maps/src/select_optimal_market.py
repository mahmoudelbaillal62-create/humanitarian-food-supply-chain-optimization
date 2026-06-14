"""Select the minimum landed-cost market for each camp and commodity."""

from pathlib import Path

import pandas as pd


DATA_DIR = Path(r"C:\Users\ASUS\PycharmProjects\PythonProject")
DEMAND_FILE = DATA_DIR / "MonthlyFoodDemand.csv"
STANDARDIZED_PRICE_FILE = DATA_DIR / "FoodPrices_Standardized.csv"
CLEAN_PRICE_FILE = DATA_DIR / "FoodPrices_Clean.csv"
DISTANCE_FILE = DATA_DIR / "MarketCampDistance.csv"
OUTPUT_FILE = DATA_DIR / "OptimalMarketSelection.csv"
COST_PER_TON_KM = 50.0

COMMODITY_MAPPING = {
    "Lentils": "Lentils (black)",
}

OUTPUT_COLUMNS = [
    "camp_id",
    "camp_name",
    "commodity",
    "selected_market",
    "distance_km",
    "price_per_kg",
    "purchase_cost",
    "transport_cost",
    "total_cost",
]


def main() -> None:
    price_file = (
        STANDARDIZED_PRICE_FILE
        if STANDARDIZED_PRICE_FILE.exists()
        else CLEAN_PRICE_FILE
    )

    demand = pd.read_csv(DEMAND_FILE)
    prices = pd.read_csv(price_file)
    distances = pd.read_csv(DISTANCE_FILE)

    demand["commodity"] = demand["commodity"].astype(str).str.strip()
    demand["price_commodity"] = demand["commodity"].replace(COMMODITY_MAPPING)
    demand["demand_kg_month"] = pd.to_numeric(
        demand["demand_kg_month"], errors="raise"
    )
    demand["demand_ton_month"] = pd.to_numeric(
        demand["demand_ton_month"], errors="raise"
    )

    prices["commodity"] = prices["commodity"].astype(str).str.strip()
    prices["price_per_kg"] = pd.to_numeric(
        prices["price_per_kg"], errors="coerce"
    )
    prices = prices.dropna(subset=["market", "commodity", "price_per_kg"])
    prices = prices[prices["price_per_kg"] >= 0].copy()

    distances["distance_km"] = pd.to_numeric(
        distances["distance_km"], errors="coerce"
    )
    distances = distances.dropna(
        subset=["market", "camp_id", "camp_name", "distance_km"]
    )

    # Keep one price and one distance for every relevant key.
    prices = (
        prices.sort_values(["market", "commodity", "price_per_kg"])
        .drop_duplicates(["market", "commodity"], keep="first")
        [["market", "commodity", "price_per_kg"]]
        .rename(columns={"commodity": "price_commodity"})
    )
    distances = distances.drop_duplicates(["market", "camp_id"], keep="first")

    # Every camp-commodity demand is evaluated against every market distance.
    options = demand.merge(
        distances[["market", "camp_id", "distance_km"]],
        on="camp_id",
        how="left",
        validate="many_to_many",
    ).merge(
        prices,
        on=["market", "price_commodity"],
        how="left",
        validate="many_to_one",
    )

    options["purchase_cost"] = (
        options["demand_kg_month"] * options["price_per_kg"]
    )
    options["transport_cost"] = (
        options["distance_km"]
        * options["demand_ton_month"]
        * COST_PER_TON_KM
    )
    options["total_cost"] = options["purchase_cost"] + options["transport_cost"]

    available = options.dropna(subset=["total_cost"]).copy()
    selected = (
        available.sort_values(
            ["camp_id", "commodity", "total_cost", "market"], kind="stable"
        )
        .drop_duplicates(["camp_id", "commodity"], keep="first")
        .rename(columns={"market": "selected_market"})
    )

    # Start from all demands so commodities with no market price still appear.
    result = demand[["camp_id", "camp_name", "commodity"]].merge(
        selected[
            [
                "camp_id",
                "commodity",
                "selected_market",
                "distance_km",
                "price_per_kg",
                "purchase_cost",
                "transport_cost",
                "total_cost",
            ]
        ],
        on=["camp_id", "commodity"],
        how="left",
        validate="one_to_one",
    )
    result["selected_market"] = result["selected_market"].fillna("Not available")
    result = result[OUTPUT_COLUMNS].sort_values(
        ["camp_id", "commodity"], ignore_index=True
    )

    result.to_csv(OUTPUT_FILE, index=False, float_format="%.6f")
    print(f"Created {OUTPUT_FILE} with {len(result)} rows.")


if __name__ == "__main__":
    main()
