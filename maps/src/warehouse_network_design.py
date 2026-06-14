"""Select the lowest-cost warehouse route for each camp and commodity."""

from pathlib import Path

import numpy as np
import pandas as pd


DATA_DIR = Path(r"C:\Users\ASUS\PycharmProjects\PythonProject")
MARKETS_FILE = DATA_DIR / "Markets.csv"
WAREHOUSES_FILE = DATA_DIR / "Warehouses.csv"
SELECTION_FILE = DATA_DIR / "OptimalMarketSelection.csv"
DEMAND_POINTS_FILE = DATA_DIR / "DemandPoints_Final.csv"
RESULTS_FILE = DATA_DIR / "WarehouseNetworkResults.csv"
SUMMARY_FILE = DATA_DIR / "WarehouseNetworkSummary.csv"

EARTH_RADIUS_KM = 6371.0088
COST_PER_TON_KM = 50.0

RESULT_COLUMNS = [
    "camp_id",
    "camp_name",
    "commodity",
    "selected_market",
    "selected_warehouse",
    "market_to_warehouse_km",
    "warehouse_to_camp_km",
    "purchase_cost",
    "inbound_transport_cost",
    "outbound_transport_cost",
    "total_cost",
]


def haversine_km(
    longitude_1: pd.Series,
    latitude_1: pd.Series,
    longitude_2: pd.Series,
    latitude_2: pd.Series,
) -> np.ndarray:
    """Calculate row-wise Haversine distance in kilometres."""
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
    value = np.clip(value, 0.0, 1.0)
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(value))


def main() -> None:
    markets = pd.read_csv(MARKETS_FILE)
    warehouses = pd.read_csv(WAREHOUSES_FILE)
    selections = pd.read_csv(SELECTION_FILE)
    camps = pd.read_csv(
        DEMAND_POINTS_FILE,
        usecols=["camp_id", "camp-name", "xcoord", "ycoord"],
    ).rename(
        columns={
            "camp-name": "demand_camp_name",
            "xcoord": "camp_longitude",
            "ycoord": "camp_latitude",
        }
    )

    markets = markets.rename(
        columns={
            "latitude": "market_latitude",
            "longitude": "market_longitude",
        }
    )
    warehouses = warehouses.rename(
        columns={
            "latitude": "warehouse_latitude",
            "longitude": "warehouse_longitude",
        }
    )

    selections["purchase_cost"] = pd.to_numeric(
        selections["purchase_cost"], errors="coerce"
    )
    selections["price_per_kg"] = pd.to_numeric(
        selections["price_per_kg"], errors="coerce"
    )
    selections["demand_ton_month"] = (
        selections["purchase_cost"] / selections["price_per_kg"] / 1000.0
    )

    # Cross join each camp-commodity selection with every warehouse.
    options = selections.merge(markets, left_on="selected_market", right_on="market", how="left")
    options = options.merge(camps, on="camp_id", how="left", validate="many_to_one")
    options = options.merge(warehouses, how="cross")

    valid_coordinates = options[
        [
            "market_longitude",
            "market_latitude",
            "warehouse_longitude",
            "warehouse_latitude",
            "camp_longitude",
            "camp_latitude",
        ]
    ].notna().all(axis=1)

    options["market_to_warehouse_km"] = np.nan
    options["warehouse_to_camp_km"] = np.nan
    options.loc[valid_coordinates, "market_to_warehouse_km"] = haversine_km(
        options.loc[valid_coordinates, "market_longitude"],
        options.loc[valid_coordinates, "market_latitude"],
        options.loc[valid_coordinates, "warehouse_longitude"],
        options.loc[valid_coordinates, "warehouse_latitude"],
    )
    options.loc[valid_coordinates, "warehouse_to_camp_km"] = haversine_km(
        options.loc[valid_coordinates, "warehouse_longitude"],
        options.loc[valid_coordinates, "warehouse_latitude"],
        options.loc[valid_coordinates, "camp_longitude"],
        options.loc[valid_coordinates, "camp_latitude"],
    )

    options["inbound_transport_cost"] = (
        options["market_to_warehouse_km"]
        * options["demand_ton_month"]
        * COST_PER_TON_KM
    )
    options["outbound_transport_cost"] = (
        options["warehouse_to_camp_km"]
        * options["demand_ton_month"]
        * COST_PER_TON_KM
    )
    options["total_cost"] = (
        options["purchase_cost"]
        + options["inbound_transport_cost"]
        + options["outbound_transport_cost"]
    )

    available = (
        options.dropna(subset=["total_cost"])
        .sort_values(
            ["camp_id", "commodity", "total_cost", "warehouse_name"],
            kind="stable",
        )
        .drop_duplicates(["camp_id", "commodity"], keep="first")
        .rename(columns={"warehouse_name": "selected_warehouse"})
    )

    # Preserve unavailable commodity rows, including Barley.
    results = selections[["camp_id", "camp_name", "commodity", "selected_market"]].merge(
        available[
            [
                "camp_id",
                "commodity",
                "selected_warehouse",
                "market_to_warehouse_km",
                "warehouse_to_camp_km",
                "purchase_cost",
                "inbound_transport_cost",
                "outbound_transport_cost",
                "total_cost",
            ]
        ],
        on=["camp_id", "commodity"],
        how="left",
        validate="one_to_one",
    )
    results["selected_warehouse"] = results["selected_warehouse"].fillna(
        "Not available"
    )
    results = results[RESULT_COLUMNS].sort_values(
        ["camp_id", "commodity"], ignore_index=True
    )

    summary = pd.DataFrame(
        [
            {
                "total_purchase_cost": results["purchase_cost"].sum(min_count=1),
                "total_inbound_transport_cost": results[
                    "inbound_transport_cost"
                ].sum(min_count=1),
                "total_outbound_transport_cost": results[
                    "outbound_transport_cost"
                ].sum(min_count=1),
                "total_system_cost": results["total_cost"].sum(min_count=1),
            }
        ]
    )

    results.to_csv(RESULTS_FILE, index=False, float_format="%.6f")
    summary.to_csv(SUMMARY_FILE, index=False, float_format="%.6f")
    print(f"Created {RESULTS_FILE} with {len(results)} rows.")
    print(f"Created {SUMMARY_FILE}.")


if __name__ == "__main__":
    main()
