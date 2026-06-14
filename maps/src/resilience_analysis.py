"""Compare supply-network resilience scenarios by optimized monthly cost."""

from pathlib import Path

import numpy as np
import pandas as pd


DATA_DIR = Path(r"C:\Users\ASUS\PycharmProjects\PythonProject")
MARKETS_FILE = DATA_DIR / "Markets.csv"
WAREHOUSES_FILE = DATA_DIR / "Warehouses.csv"
DEMAND_FILE = DATA_DIR / "MonthlyFoodDemand.csv"
STANDARDIZED_PRICE_FILE = DATA_DIR / "FoodPrices_Standardized.csv"
CLEAN_PRICE_FILE = DATA_DIR / "FoodPrices_Clean.csv"
DEMAND_POINTS_FILE = DATA_DIR / "DemandPoints_Final.csv"
OUTPUT_FILE = DATA_DIR / "ResilienceSummary.csv"

EARTH_RADIUS_KM = 6371.0088
COST_PER_TON_KM = 50.0
TINDOUF_WAREHOUSE = "Tindouf Central Warehouse"
COMMODITY_MAPPING = {"Lentils": "Lentils (black)"}

SCENARIOS = [
    "Scenario A: Current network",
    "Scenario B: No Algiers market",
    "Scenario C: No Tindouf market",
    "Scenario D: Only Tindouf Central Warehouse",
    "Scenario E: Demand +50%",
]


def haversine_km(
    longitude_1: pd.Series,
    latitude_1: pd.Series,
    longitude_2: pd.Series,
    latitude_2: pd.Series,
) -> np.ndarray:
    """Return row-wise Haversine distances in kilometres."""
    lon1 = np.radians(pd.to_numeric(longitude_1, errors="raise").to_numpy())
    lat1 = np.radians(pd.to_numeric(latitude_1, errors="raise").to_numpy())
    lon2 = np.radians(pd.to_numeric(longitude_2, errors="raise").to_numpy())
    lat2 = np.radians(pd.to_numeric(latitude_2, errors="raise").to_numpy())

    delta_lon = lon2 - lon1
    delta_lat = lat2 - lat1
    value = (
        np.sin(delta_lat / 2.0) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin(delta_lon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(value, 0.0, 1.0)))


def build_network_options() -> pd.DataFrame:
    """Build every feasible demand-market-warehouse routing option."""
    markets = pd.read_csv(MARKETS_FILE).rename(
        columns={
            "latitude": "market_latitude",
            "longitude": "market_longitude",
        }
    )
    warehouses = pd.read_csv(WAREHOUSES_FILE).rename(
        columns={
            "latitude": "warehouse_latitude",
            "longitude": "warehouse_longitude",
        }
    )
    demand = pd.read_csv(DEMAND_FILE)
    camps = pd.read_csv(
        DEMAND_POINTS_FILE,
        usecols=["camp_id", "xcoord", "ycoord"],
    ).rename(
        columns={"xcoord": "camp_longitude", "ycoord": "camp_latitude"}
    )
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

    options = demand.merge(camps, on="camp_id", how="left", validate="many_to_one")
    options = options.merge(markets, how="cross")
    options = options.merge(
        prices,
        on=["market", "price_commodity"],
        how="left",
        validate="many_to_one",
    )
    options = options.merge(warehouses, how="cross")

    options["market_to_warehouse_km"] = haversine_km(
        options["market_longitude"],
        options["market_latitude"],
        options["warehouse_longitude"],
        options["warehouse_latitude"],
    )
    options["warehouse_to_camp_km"] = haversine_km(
        options["warehouse_longitude"],
        options["warehouse_latitude"],
        options["camp_longitude"],
        options["camp_latitude"],
    )
    return options


def calculate_scenario(options: pd.DataFrame, scenario: str) -> dict[str, float | str]:
    """Apply one disruption, optimize each demand route, and total its costs."""
    scenario_options = options.copy()
    demand_factor = 1.50 if scenario == "Scenario E: Demand +50%" else 1.0

    if scenario == "Scenario B: No Algiers market":
        scenario_options = scenario_options[
            scenario_options["market"].str.casefold() != "algiers"
        ].copy()
    elif scenario == "Scenario C: No Tindouf market":
        scenario_options = scenario_options[
            scenario_options["market"].str.casefold() != "tindouf"
        ].copy()
    elif scenario == "Scenario D: Only Tindouf Central Warehouse":
        scenario_options = scenario_options[
            scenario_options["warehouse_name"] == TINDOUF_WAREHOUSE
        ].copy()

    scenario_options["purchase_cost"] = (
        scenario_options["demand_kg_month"]
        * demand_factor
        * scenario_options["price_per_kg"]
    )
    scenario_options["inbound_transport_cost"] = (
        scenario_options["market_to_warehouse_km"]
        * scenario_options["demand_ton_month"]
        * demand_factor
        * COST_PER_TON_KM
    )
    scenario_options["outbound_transport_cost"] = (
        scenario_options["warehouse_to_camp_km"]
        * scenario_options["demand_ton_month"]
        * demand_factor
        * COST_PER_TON_KM
    )
    scenario_options["transport_cost"] = (
        scenario_options["inbound_transport_cost"]
        + scenario_options["outbound_transport_cost"]
    )
    scenario_options["total_cost"] = (
        scenario_options["purchase_cost"] + scenario_options["transport_cost"]
    )

    selected = (
        scenario_options.dropna(subset=["total_cost"])
        .sort_values(
            ["camp_id", "commodity", "total_cost", "market", "warehouse_name"],
            kind="stable",
        )
        .drop_duplicates(["camp_id", "commodity"], keep="first")
    )

    total_purchase = selected["purchase_cost"].sum(min_count=1)
    total_transport = selected["transport_cost"].sum(min_count=1)
    return {
        "scenario": scenario,
        "total_purchase_cost": total_purchase,
        "total_transport_cost": total_transport,
        "total_system_cost": total_purchase + total_transport,
    }


def main() -> None:
    options = build_network_options()
    summary = pd.DataFrame(
        [calculate_scenario(options, scenario) for scenario in SCENARIOS]
    )
    summary.to_csv(OUTPUT_FILE, index=False, float_format="%.6f")
    print(f"Created {OUTPUT_FILE} with {len(summary)} scenarios.")


if __name__ == "__main__":
    main()
