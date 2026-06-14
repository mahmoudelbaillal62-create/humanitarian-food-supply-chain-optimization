"""Calculate monthly transport and total landed food costs."""

from pathlib import Path

import pandas as pd


DATA_DIR = Path(r"C:\Users\ASUS\PycharmProjects\PythonProject")
PURCHASE_COST_FILE = DATA_DIR / "FoodPurchaseCost.csv"
DISTANCE_FILE = DATA_DIR / "MarketCampDistance.csv"
OUTPUT_FILE = DATA_DIR / "TotalLandedCost.csv"
COST_PER_TON_KM = 50.0


def main() -> None:
    purchase_cost = pd.read_csv(PURCHASE_COST_FILE)
    distances = pd.read_csv(DISTANCE_FILE)

    market_column = (
        "selected_market"
        if "selected_market" in purchase_cost.columns
        else "market"
    )
    required_purchase_columns = {
        "camp_id",
        "camp_name",
        "commodity",
        market_column,
        "price_per_kg",
        "demand_kg_month",
        "monthly_purchase_cost",
    }
    required_distance_columns = {"market", "camp_name", "distance_km"}

    missing_purchase = required_purchase_columns.difference(purchase_cost.columns)
    missing_distance = required_distance_columns.difference(distances.columns)
    if missing_purchase or missing_distance:
        raise ValueError(
            f"Missing purchase columns: {sorted(missing_purchase)}; "
            f"missing distance columns: {sorted(missing_distance)}"
        )

    purchase_cost = purchase_cost.rename(columns={market_column: "market"})
    purchase_cost["demand_kg_month"] = pd.to_numeric(
        purchase_cost["demand_kg_month"], errors="coerce"
    )
    purchase_cost["price_per_kg"] = pd.to_numeric(
        purchase_cost["price_per_kg"], errors="coerce"
    )
    purchase_cost["monthly_purchase_cost"] = pd.to_numeric(
        purchase_cost["monthly_purchase_cost"], errors="coerce"
    )
    distances["distance_km"] = pd.to_numeric(
        distances["distance_km"], errors="coerce"
    )

    duplicate_distances = distances.duplicated(["market", "camp_name"], keep=False)
    if duplicate_distances.any():
        duplicates = distances.loc[
            duplicate_distances, ["market", "camp_name"]
        ].drop_duplicates()
        raise ValueError(
            "MarketCampDistance.csv has duplicate market-camp pairs: "
            + duplicates.to_dict(orient="records").__str__()
        )

    landed_cost = purchase_cost.merge(
        distances[["market", "camp_name", "distance_km"]],
        on=["market", "camp_name"],
        how="left",
        validate="many_to_one",
    )

    demand_ton_month = landed_cost["demand_kg_month"] / 1000.0
    landed_cost["transport_cost"] = (
        landed_cost["distance_km"] * demand_ton_month * COST_PER_TON_KM
    )
    landed_cost["total_landed_cost"] = (
        landed_cost["monthly_purchase_cost"] + landed_cost["transport_cost"]
    )

    output = landed_cost[
        [
            "camp_id",
            "camp_name",
            "commodity",
            "market",
            "distance_km",
            "price_per_kg",
            "monthly_purchase_cost",
            "transport_cost",
            "total_landed_cost",
        ]
    ].sort_values(["camp_id", "commodity"], ignore_index=True)

    output.to_csv(OUTPUT_FILE, index=False, float_format="%.6f")
    print(f"Created {OUTPUT_FILE} with {len(output)} rows.")


if __name__ == "__main__":
    main()
