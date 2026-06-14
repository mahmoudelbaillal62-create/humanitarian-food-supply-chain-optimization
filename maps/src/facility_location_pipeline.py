"""Build distance, SQL, and Gurobi facility-location outputs.

Requirements:
    pip install pandas numpy gurobipy

Gurobi also requires a valid license. Academic licenses are available from
https://www.gurobi.com/academia/academic-program-and-licenses/
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


EARTH_RADIUS_KM = 6371.0088
RATION_KG_PER_PERSON_MONTH = 14.21
COST_PER_TON_KM = 50.0
DEFAULT_DATA_DIR = Path(r"C:\Users\ASUS\PycharmProjects\PythonProject")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate distance, SQL, and facility-location outputs."
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--k-values", type=int, nargs="+", default=[3, 5, 7])
    parser.add_argument(
        "--skip-optimization",
        action="store_true",
        help="Generate distance and SQL outputs without running Gurobi.",
    )
    return parser.parse_args()


def load_data(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load and validate demand points and candidate locations."""
    demands = pd.read_csv(data_dir / "DemandPoints_Final.csv")
    candidates = pd.read_csv(data_dir / "CandidateLocations.csv")

    # The supplied demand file uses "camp-name"; normalize it to the project name.
    demands = demands.rename(columns={"camp-name": "camp_name"})

    demand_columns = [
        "demand_id",
        "camp_id",
        "camp_name",
        "population",
        "xcoord",
        "ycoord",
    ]
    candidate_columns = [
        "location_id",
        "camp_id",
        "location_name",
        "xcoord",
        "ycoord",
    ]

    missing_demand = set(demand_columns).difference(demands.columns)
    missing_candidate = set(candidate_columns).difference(candidates.columns)
    if missing_demand or missing_candidate:
        raise ValueError(
            f"Missing demand columns: {sorted(missing_demand)}; "
            f"missing candidate columns: {sorted(missing_candidate)}"
        )

    demands = demands[demand_columns].copy()
    candidates = candidates[candidate_columns].copy()

    integer_columns = [(demands, "demand_id"), (demands, "camp_id"),
                       (demands, "population"), (candidates, "location_id"),
                       (candidates, "camp_id")]
    for frame, column in integer_columns:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype("int64")

    for frame in (demands, candidates):
        frame["xcoord"] = pd.to_numeric(frame["xcoord"], errors="raise")
        frame["ycoord"] = pd.to_numeric(frame["ycoord"], errors="raise")
        if frame[["xcoord", "ycoord"]].isna().any().any():
            raise ValueError("Coordinates cannot be null.")

    if demands["demand_id"].duplicated().any():
        raise ValueError("demand_id values must be unique.")
    if candidates["location_id"].duplicated().any():
        raise ValueError("location_id values must be unique.")

    return demands.sort_values("demand_id"), candidates.sort_values("location_id")


def build_distance_matrix(
    demands: pd.DataFrame, candidates: pd.DataFrame
) -> pd.DataFrame:
    """Return every demand-candidate pair with Haversine distance in km."""
    demand_lat = np.radians(demands["ycoord"].to_numpy(dtype=float))[:, None]
    demand_lon = np.radians(demands["xcoord"].to_numpy(dtype=float))[:, None]
    candidate_lat = np.radians(candidates["ycoord"].to_numpy(dtype=float))[None, :]
    candidate_lon = np.radians(candidates["xcoord"].to_numpy(dtype=float))[None, :]

    delta_lat = candidate_lat - demand_lat
    delta_lon = candidate_lon - demand_lon
    haversine_a = (
        np.sin(delta_lat / 2.0) ** 2
        + np.cos(demand_lat)
        * np.cos(candidate_lat)
        * np.sin(delta_lon / 2.0) ** 2
    )
    haversine_a = np.clip(haversine_a, 0.0, 1.0)
    distances = 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(haversine_a))

    demand_rows = demands.loc[demands.index.repeat(len(candidates))].reset_index(drop=True)
    candidate_rows = pd.concat(
        [candidates.reset_index(drop=True)] * len(demands), ignore_index=True
    )

    return pd.DataFrame(
        {
            "demand_id": demand_rows["demand_id"],
            "camp_id": demand_rows["camp_id"],
            "camp_name": demand_rows["camp_name"],
            "population": demand_rows["population"],
            "location_id": candidate_rows["location_id"],
            "location_name": candidate_rows["location_name"],
            "candidate_camp_id": candidate_rows["camp_id"],
            "distance_km": distances.ravel(),
        }
    )


def sql_string(value: object) -> str:
    """Convert a Python/pandas value to a SQL Server literal."""
    if pd.isna(value):
        return "NULL"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        if not math.isfinite(float(value)):
            return "NULL"
        return format(float(value), ".10f").rstrip("0").rstrip(".")
    return "N'" + str(value).replace("'", "''") + "'"


def write_insert_statements(
    path: Path, table_name: str, frame: pd.DataFrame, columns: Iterable[str]
) -> None:
    """Write batched SQL Server INSERT statements for one DataFrame."""
    columns = list(columns)
    with path.open("w", encoding="utf-8", newline="\n") as sql_file:
        sql_file.write(f"SET NOCOUNT ON;\nGO\n\n")
        for start in range(0, len(frame), 1000):
            batch = frame.iloc[start : start + 1000]
            sql_file.write(
                f"INSERT INTO dbo.{table_name} "
                f"({', '.join(f'[{column}]' for column in columns)})\nVALUES\n"
            )
            rows = [
                "(" + ", ".join(sql_string(row[column]) for column in columns) + ")"
                for _, row in batch.iterrows()
            ]
            sql_file.write(",\n".join(rows) + ";\nGO\n\n")


def write_sql_files(
    output_dir: Path,
    demands: pd.DataFrame,
    candidates: pd.DataFrame,
    distances: pd.DataFrame,
) -> None:
    """Create SQL Server DDL and INSERT scripts."""
    ddl = """IF OBJECT_ID(N'dbo.DistanceMatrix', N'U') IS NOT NULL DROP TABLE dbo.DistanceMatrix;
IF OBJECT_ID(N'dbo.CandidateLocations', N'U') IS NOT NULL DROP TABLE dbo.CandidateLocations;
IF OBJECT_ID(N'dbo.DemandPoints', N'U') IS NOT NULL DROP TABLE dbo.DemandPoints;
GO

CREATE TABLE dbo.DemandPoints (
    demand_id  INT            NOT NULL PRIMARY KEY,
    camp_id    INT            NOT NULL,
    camp_name  NVARCHAR(200)  NOT NULL,
    population INT            NOT NULL CHECK (population >= 0),
    xcoord     DECIMAL(12, 8) NOT NULL,
    ycoord     DECIMAL(12, 8) NOT NULL
);
GO

CREATE TABLE dbo.CandidateLocations (
    location_id   INT            NOT NULL PRIMARY KEY,
    camp_id       INT            NOT NULL,
    location_name NVARCHAR(200)  NOT NULL,
    xcoord        DECIMAL(12, 8) NOT NULL,
    ycoord        DECIMAL(12, 8) NOT NULL
);
GO

CREATE TABLE dbo.DistanceMatrix (
    demand_id        INT            NOT NULL,
    camp_id          INT            NOT NULL,
    camp_name        NVARCHAR(200)  NOT NULL,
    population       INT            NOT NULL,
    location_id      INT            NOT NULL,
    location_name    NVARCHAR(200)  NOT NULL,
    candidate_camp_id INT           NOT NULL,
    distance_km      DECIMAL(18, 6) NOT NULL CHECK (distance_km >= 0),
    CONSTRAINT PK_DistanceMatrix PRIMARY KEY (demand_id, location_id),
    CONSTRAINT FK_DistanceMatrix_Demand
        FOREIGN KEY (demand_id) REFERENCES dbo.DemandPoints(demand_id),
    CONSTRAINT FK_DistanceMatrix_Candidate
        FOREIGN KEY (location_id) REFERENCES dbo.CandidateLocations(location_id)
);
GO
"""
    (output_dir / "CreateTables.sql").write_text(ddl, encoding="utf-8")

    write_insert_statements(
        output_dir / "InsertDemandPoints.sql",
        "DemandPoints",
        demands,
        ["demand_id", "camp_id", "camp_name", "population", "xcoord", "ycoord"],
    )
    write_insert_statements(
        output_dir / "InsertCandidateLocations.sql",
        "CandidateLocations",
        candidates,
        ["location_id", "camp_id", "location_name", "xcoord", "ycoord"],
    )
    write_insert_statements(
        output_dir / "InsertDistanceMatrix.sql",
        "DistanceMatrix",
        distances,
        list(distances.columns),
    )


def solve_facility_location(
    demands: pd.DataFrame,
    candidates: pd.DataFrame,
    distances: pd.DataFrame,
    k: int,
) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    """Solve the uncapacitated p-median model for exactly k facilities."""
    try:
        import gurobipy as gp
        from gurobipy import GRB
    except ImportError as exc:
        raise RuntimeError(
            "Gurobi is required for optimization. Install it with "
            "'pip install gurobipy' and configure a valid Gurobi license."
        ) from exc

    if not 1 <= k <= len(candidates):
        raise ValueError(f"K must be between 1 and {len(candidates)}; received {k}.")

    demand_ids = demands["demand_id"].tolist()
    location_ids = candidates["location_id"].tolist()
    population = demands.set_index("demand_id")["population"].to_dict()
    distance = distances.set_index(["demand_id", "location_id"])[
        "distance_km"
    ].to_dict()

    model = gp.Model(f"facility_location_k_{k}")
    model.Params.OutputFlag = 0
    x = model.addVars(demand_ids, location_ids, vtype=GRB.BINARY, name="x")
    y = model.addVars(location_ids, vtype=GRB.BINARY, name="y")

    model.setObjective(
        gp.quicksum(
            population[i] * distance[i, j] * x[i, j]
            for i in demand_ids
            for j in location_ids
        ),
        GRB.MINIMIZE,
    )

    model.addConstrs(
        (gp.quicksum(x[i, j] for j in location_ids) == 1 for i in demand_ids),
        name="assign_once",
    )
    model.addConstrs(
        (x[i, j] <= y[j] for i in demand_ids for j in location_ids),
        name="assign_only_to_open",
    )
    model.addConstr(gp.quicksum(y[j] for j in location_ids) == k, name="open_k")
    model.optimize()

    if model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"Gurobi did not find an optimal solution for K={k}.")

    selected_ids = [j for j in location_ids if y[j].X > 0.5]
    selected = candidates[candidates["location_id"].isin(selected_ids)].copy()
    selected.insert(0, "K", k)

    demand_lookup = demands.set_index("demand_id")
    candidate_lookup = candidates.set_index("location_id")
    assignment_rows = []
    for i in demand_ids:
        assigned_j = next(j for j in location_ids if x[i, j].X > 0.5)
        assignment_rows.append(
            {
                "K": k,
                "demand_id": i,
                "camp_id": demand_lookup.at[i, "camp_id"],
                "camp_name": demand_lookup.at[i, "camp_name"],
                "population": population[i],
                "location_id": assigned_j,
                "location_name": candidate_lookup.at[assigned_j, "location_name"],
                "candidate_camp_id": candidate_lookup.at[assigned_j, "camp_id"],
                "distance_km": distance[i, assigned_j],
                "weighted_distance": population[i] * distance[i, assigned_j],
                "monthly_food_tons": (
                    population[i] * RATION_KG_PER_PERSON_MONTH / 1000.0
                ),
                "transport_cost": (
                    distance[i, assigned_j]
                    * (population[i] * RATION_KG_PER_PERSON_MONTH / 1000.0)
                    * COST_PER_TON_KM
                ),
            }
        )

    return selected, pd.DataFrame(assignment_rows), float(model.ObjVal)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    demands, candidates = load_data(args.data_dir)
    distances = build_distance_matrix(demands, candidates)
    distances.to_csv(
        args.output_dir / "DistanceMatrix.csv", index=False, float_format="%.6f"
    )
    write_sql_files(args.output_dir, demands, candidates, distances)

    if args.skip_optimization:
        print("Generated DistanceMatrix.csv and SQL scripts; optimization skipped.")
        return

    all_selected = []
    all_assignments = []
    objectives = []
    transport_summaries = []
    for k in args.k_values:
        selected, assignments, objective = solve_facility_location(
            demands, candidates, distances, k
        )
        selected.to_csv(args.output_dir / f"SelectedFacilities_K{k}.csv", index=False)
        assignments.to_csv(
            args.output_dir / f"assignments_K{k}.csv",
            index=False,
            float_format="%.6f",
        )
        all_selected.append(selected)
        all_assignments.append(assignments)
        objectives.append({"K": k, "objective_value": objective})
        transport_summaries.append(
            {
                "K": k,
                "total_weighted_distance": assignments["weighted_distance"].sum(),
                "total_monthly_transport_cost": assignments["transport_cost"].sum(),
            }
        )
        print(f"K={k}: objective={objective:,.6f}; facilities={selected['location_id'].tolist()}")

    pd.concat(all_selected, ignore_index=True).to_csv(
        args.output_dir / "SelectedFacilities_All.csv", index=False
    )
    pd.concat(all_assignments, ignore_index=True).to_csv(
        args.output_dir / "DemandAssignments_All.csv", index=False, float_format="%.6f"
    )
    pd.DataFrame(objectives).to_csv(
        args.output_dir / "ObjectiveValues.csv", index=False, float_format="%.6f"
    )
    pd.DataFrame(transport_summaries).to_csv(
        args.output_dir / "transport_cost_summary.csv",
        index=False,
        float_format="%.6f",
    )


if __name__ == "__main__":
    main()
