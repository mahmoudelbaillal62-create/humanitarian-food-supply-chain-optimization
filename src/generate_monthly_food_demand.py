from pathlib import Path

import pandas as pd


DATA_DIR = Path(r"C:\Users\ASUS\PycharmProjects\PythonProject")
INPUT_FILE = DATA_DIR / "DemandPoints_Final.csv"
OUTPUT_FILE = DATA_DIR / "MonthlyFoodDemand.csv"

MONTHLY_RATIONS_KG = {
    "Wheat flour": 8.00,
    "Rice": 2.00,
    "Lentils": 2.00,
    "Barley": 1.00,
    "Sugar": 0.75,
    "Oil": 0.46,
}


def main() -> None:
    demand_points = pd.read_csv(
        INPUT_FILE,
        usecols=["camp_id", "camp-name", "population"],
    ).rename(columns={"camp-name": "camp_name"})

    demand_points["population"] = pd.to_numeric(
        demand_points["population"], errors="raise"
    )

    rations = pd.DataFrame(
        MONTHLY_RATIONS_KG.items(),
        columns=["commodity", "ration_kg_per_person_month"],
    )

    monthly_demand = demand_points.merge(rations, how="cross")
    monthly_demand["demand_kg_month"] = (
        monthly_demand["population"]
        * monthly_demand["ration_kg_per_person_month"]
    )
    monthly_demand["demand_ton_month"] = (
        monthly_demand["demand_kg_month"] / 1000
    )

    monthly_demand = monthly_demand[
        [
            "camp_id",
            "camp_name",
            "commodity",
            "ration_kg_per_person_month",
            "population",
            "demand_kg_month",
            "demand_ton_month",
        ]
    ]

    monthly_demand.to_csv(OUTPUT_FILE, index=False)


if __name__ == "__main__":
    main()