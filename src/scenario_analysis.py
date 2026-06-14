"""Run supply-cost scenarios and re-optimize market selection."""

from pathlib import Path

import pandas as pd


DATA_DIR = Path(r"C:\Users\ASUS\PycharmProjects\PythonProject")
BASE_FILE = DATA_DIR / "OptimalMarketSelection.csv"
DEMAND_FILE = DATA_DIR / "MonthlyFoodDemand.csv"
STANDARDIZED_PRICE_FILE = DATA_DIR / "FoodPrices_Standardized.csv"
CLEAN_PRICE_FILE = DATA_DIR / "FoodPrices_Clean.csv"
DISTANCE_FILE = DATA_DIR / "MarketCampDistance.csv"
RESULTS_FILE = DATA_DIR / "ScenarioResults.csv"
SUMMARY_FILE = DATA_DIR / "ScenarioSummary.csv"

COST_PER_TON_KM = 50.0
COMMODITY_MAPPING = {"Lentils": "Lentils (black)"}

SCENARIOS = [
    "Base case",
    "Transport cost -20%",
    "Transport cost +20%",
    "Transport cost +50%",
    "Tindouf price +20%",
    "Algiers route disruption",
    "Demand increase +15%",
]

RESULT_COLUMNS = [
    "scenario",
    "camp_id",
    "camp_name",
    "commodity",
    "selected_market",
    "purchase_cost",
    "transport_cost",
    "total_cost",
]


def load_market_options() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the base result and construct every feasible market option."""
    base = pd.read_csv(BASE_FILE)
    demand = pd.read_csv(DEMAND_FILE)
    distances = pd.read_csv(DISTANCE_FILE)
    price_file = (
        STANDARDIZED_PRICE_FILE
        if STANDARDIZED_PRICE_FILE.exists()
        else CLEAN_PRICE_FILE
    )
    prices = pd.read_csv(price_file)

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
    return base, options


def format_base_case(base: pd.DataFrame) -> pd.DataFrame:
    """Use the existing optimized costs unchanged for the base case."""
    result = base[
        [
            "camp_id",
            "camp_name",
            "commodity",
            "selected_market",
            "purchase_cost",
            "transport_cost",
            "total_cost",
        ]
    ].copy()
    result.insert(0, "scenario", "Base case")
    return result


def solve_scenario(options: pd.DataFrame, scenario: str) -> pd.DataFrame:
    """Apply scenario assumptions and select the cheapest feasible market."""
    adjusted = options.copy()
    demand_factor = 1.15 if scenario == "Demand increase +15%" else 1.0
    transport_factor = {
        "Transport cost -20%": 0.80,
        "Transport cost +20%": 1.20,
        "Transport cost +50%": 1.50,
    }.get(scenario, 1.0)

    if scenario == "Algiers route disruption":
        adjusted = adjusted[adjusted["market"].str.casefold() != "algiers"].copy()

    adjusted["scenario_price_per_kg"] = adjusted["price_per_kg"]
    if scenario == "Tindouf price +20%":
        tindouf = adjusted["market"].str.casefold() == "tindouf"
        adjusted.loc[tindouf, "scenario_price_per_kg"] *= 1.20

    adjusted["purchase_cost"] = (
        adjusted["demand_kg_month"]
        * demand_factor
        * adjusted["scenario_price_per_kg"]
    )
    adjusted["transport_cost"] = (
        adjusted["distance_km"]
        * adjusted["demand_ton_month"]
        * demand_factor
        * COST_PER_TON_KM
        * transport_factor
    )
    adjusted["total_cost"] = (
        adjusted["purchase_cost"] + adjusted["transport_cost"]
    )

    selected = (
        adjusted.dropna(subset=["total_cost"])
        .sort_values(
            ["camp_id", "commodity", "total_cost", "market"], kind="stable"
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
    result.insert(0, "scenario", scenario)
    return result[RESULT_COLUMNS]


def main() -> None:
    base, options = load_market_options()
    scenario_results = [format_base_case(base)]
    scenario_results.extend(
        solve_scenario(options, scenario) for scenario in SCENARIOS[1:]
    )

    results = pd.concat(scenario_results, ignore_index=True)
    results = results[RESULT_COLUMNS].sort_values(
        ["scenario", "camp_id", "commodity"], ignore_index=True
    )

    summary = (
        results.groupby("scenario", as_index=False, sort=False)[
            ["purchase_cost", "transport_cost", "total_cost"]
        ]
        .sum(min_count=1)
        .rename(
            columns={
                "purchase_cost": "total_purchase_cost",
                "transport_cost": "total_transport_cost",
                "total_cost": "total_system_cost",
            }
        )
    )
    summary["scenario"] = pd.Categorical(
        summary["scenario"], categories=SCENARIOS, ordered=True
    )
    summary = summary.sort_values("scenario").reset_index(drop=True)
    summary["scenario"] = summary["scenario"].astype(str)

    results.to_csv(RESULTS_FILE, index=False, float_format="%.6f")
    summary.to_csv(SUMMARY_FILE, index=False, float_format="%.6f")
    print(f"Created {RESULTS_FILE} with {len(results)} rows.")
    print(f"Created {SUMMARY_FILE} with {len(summary)} rows.")


if __name__ == "__main__":
    main()
