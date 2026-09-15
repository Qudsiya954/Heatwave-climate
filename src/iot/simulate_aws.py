from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve()

while not (ROOT / "Data" / "processed").exists():
    ROOT = ROOT.parent


forecast_path = (
    ROOT
    / "Data"
    / "processed"
    / "phase7_severity.parquet"
)

output_path = (
    ROOT
    / "Data"
    / "iot"
    / "aws_observations_demo.csv"
)

forecast = pd.read_parquet(forecast_path)

rng = np.random.default_rng(42)

aws = forecast[
    [
        "forecast_date",
        "latitude",
        "longitude",
        "predicted_tmax",
    ]
].copy()

aws["sensor_id"] = [
    f"AWS-{i:04d}"
    for i in range(1, len(aws) + 1)
]

aws["observation_date"] = aws["forecast_date"]

aws["observed_tmax"] = (
    aws["predicted_tmax"]
    + rng.normal(0, 0.6, len(aws))
)

aws = aws[
    [
        "sensor_id",
        "observation_date",
        "latitude",
        "longitude",
        "observed_tmax",
    ]
]

output_path.parent.mkdir(exist_ok=True)

aws.to_csv(output_path, index=False)

print("Demo AWS observations created.")
print("Rows:", len(aws))
print("Saved to:", output_path)