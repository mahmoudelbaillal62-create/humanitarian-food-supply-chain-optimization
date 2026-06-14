"""Select markets using financial cost and a weighted market risk penalty."""

from pathlib import Path

import pandas as pd


DATA_DIR = Path(r"C:\Users\ASUS\PycharmProjects\PythonProject")
STANDARDIZED_PRICE_FILE = DATA_DIR / "FoodPrices_Standardized.csv"
CLEAN_PRICE_FILE = DATA_DIR / "FoodPrices_Clean.csv"
DEMAND_FILE = DATA_DIR / "MonthlyFoodDemand.csv"
DISTANCE_FILE = DATA_DIR / "MarketCampDistance.csv"
OUTPUT_FILE = DATA_DIR / "ResilientMarketSelection.csv"

COST_PER_TON_KM = 50.0
RISK_COST_PER_SCORE_TON = 1000.0
LAMBDA_VALUES = [0.0, 5.0, 10.0, 25.0, 50.0, 100.0]

RISK_SCORES = {
    "Algiers": 5,
    "Tindouf": 3,
    "Laayoune": 2,
    "Smara": 1,
    "Aouserd": 1,
    "Boujdour": 1,
    "Dakhla": 1,
}

COMMODITY_MAPPING = {
    "Lentils": "Lentils (black)",
}

OUTPUT_COLUMNS = [
    "lambda",
    "camp_id",
    "camp_name",
    "commodity",
    "selected_market",
    "total_cost",
    "risk_cost",
    "objective",
]


def build_options() -> pd.DataFrame:
    """Construct every camp-commodity-market option and its base costs."""
    price_file = (
        STANDARDIZED_PRICE_FILE
        if STANDARDIZED_PRICE_FILE.exists()
        else CLEAN_PRICE_FILE
    )
    prices = pd.read_csv(price_file)
    demand = pd.read_csv(DEMAND_FILE)
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
    prices = (
        prices.dropna(subset=["market", "commodity", "price_per_kg"])
        .query("price_per_kg >= 0")
        .sort_values(["market", "commodity", "price_per_kg"])
        .drop_duplicates(["market", "commodity"], keep="first")
        [["market", "commodity", "price_per_kg"]]
        .rename(columns={"commodity": "price_commodity"})
    )

    distances["distance_km"] = pd.to_numeric(
        distances["distance_km"], errors="coerce"
    )
    distances = distances.dropna(subset=["market", "camp_id", "distance_km"])
    distances = distances.drop_duplicates(["market", "camp_id"], keep="first")

    unknown_markets = sorted(set(distances["market"]) - set(RISK_SCORES))
    if unknown_markets:
        raise ValueError(f"Risk scores are missing for markets: {unknown_markets}")

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

    options["risk_score"] = options["market"].map(RISK_SCORES)
    options["purchase_cost"] = (
        options["demand_kg_month"] * options["price_per_kg"]
    )
    options["transport_cost"] = (
        options["distance_km"]
        * options["demand_ton_month"]
        * COST_PER_TON_KM
    )
    options["total_cost"] = options["purchase_cost"] + options["transport_cost"]
    options["risk_cost"] = (
        options["risk_score"]
        * options["demand_ton_month"]
        * RISK_COST_PER_SCORE_TON
    )
    return options


def select_for_lambda(options: pd.DataFrame, lambda_value: float) -> pd.DataFrame:
    """Select the lowest risk-adjusted objective for every demand row."""
    evaluated = options.copy()
    evaluated["objective"] = (
        evaluated["total_cost"] + lambda_value * evaluated["risk_cost"]
    )

    selected = (
        evaluated.dropna(subset=["objective"])
        .sort_values(
            ["camp_id", "commodity", "objective", "market"], kind="stable"
        )
        .drop_duplicates(["camp_id", "commodity"], keep="first")
        .rename(columns={"market": "selected_market"})
    )

    all_demands = options[
        ["camp_id", "camp_name", "commodity"]
    ].drop_duplicates()
    result = all_demands.merge(
        selected[
            [
                "camp_id",
                "commodity",
                "selected_market",
                "total_cost",
                "risk_cost",
                "objective",
            ]
        ],
        on=["camp_id", "commodity"],
        how="left",
        validate="one_to_one",
    )
    result["selected_market"] = result["selected_market"].fillna("Not available")
    result.insert(0, "lambda", lambda_value)
    return result[OUTPUT_COLUMNS]


def main() -> None:
    options = build_options()
    results = pd.concat(
        [select_for_lambda(options, value) for value in LAMBDA_VALUES],
        ignore_index=True,
    )
    results = results.sort_values(
        ["lambda", "camp_id", "commodity"], ignore_index=True
    )
    results.to_csv(OUTPUT_FILE, index=False, float_format="%.6f")
    print(f"Created {OUTPUT_FILE} with {len(results)} rows.")


if __name__ == "__main__":
    main()
