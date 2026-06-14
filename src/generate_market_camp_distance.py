"""Calculate Haversine distances between every market and camp demand point."""

from pathlib import Path

import numpy as np
import pandas as pd


DATA_DIR = Path(r"C:\Users\ASUS\PycharmProjects\PythonProject")
MARKETS_FILE = DATA_DIR / "Markets.csv"
DEMAND_POINTS_FILE = DATA_DIR / "DemandPoints_Final.csv"
OUTPUT_FILE = DATA_DIR / "MarketCampDistance.csv"
EARTH_RADIUS_KM = 6371.0088


def main() -> None:
    markets = pd.read_csv(
        MARKETS_FILE,
        usecols=["market", "latitude", "longitude"],
    )
    camps = pd.read_csv(
        DEMAND_POINTS_FILE,
        usecols=["camp_id", "camp-name", "xcoord", "ycoord"],
    ).rename(columns={"camp-name": "camp_name"})

    market_longitudes = np.radians(
        pd.to_numeric(markets["longitude"], errors="raise").to_numpy(dtype=float)
    )[:, None]
    market_latitudes = np.radians(
        pd.to_numeric(markets["latitude"], errors="raise").to_numpy(dtype=float)
    )[:, None]
    camp_longitudes = np.radians(
        pd.to_numeric(camps["xcoord"], errors="raise").to_numpy(dtype=float)
    )[None, :]
    camp_latitudes = np.radians(
        pd.to_numeric(camps["ycoord"], errors="raise").to_numpy(dtype=float)
    )[None, :]

    delta_longitude = camp_longitudes - market_longitudes
    delta_latitude = camp_latitudes - market_latitudes
    haversine = (
        np.sin(delta_latitude / 2.0) ** 2
        + np.cos(market_latitudes)
        * np.cos(camp_latitudes)
        * np.sin(delta_longitude / 2.0) ** 2
    )
    haversine = np.clip(haversine, 0.0, 1.0)
    distances = 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(haversine))

    result = pd.DataFrame(
        {
            "market": np.repeat(markets["market"].to_numpy(), len(camps)),
            "camp_id": np.tile(camps["camp_id"].to_numpy(), len(markets)),
            "camp_name": np.tile(camps["camp_name"].to_numpy(), len(markets)),
            "distance_km": distances.ravel(),
        }
    )
    result.to_csv(OUTPUT_FILE, index=False, float_format="%.6f")
    print(f"Created {OUTPUT_FILE} with {len(result)} rows.")


if __name__ == "__main__":
    main()
