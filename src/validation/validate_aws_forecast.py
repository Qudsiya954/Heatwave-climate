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

real_aws_path = (
    ROOT
    / "Data"
    / "iot"
    / "aws_observations.csv"
)

demo_aws_path = (
    ROOT
    / "Data"
    / "iot"
    / "aws_observations_demo.csv"
)

output_path = (
    ROOT
    / "Data"
    / "processed"
    / "aws_forecast_validation.csv"
)


aws_path = (
    real_aws_path
    if real_aws_path.exists()
    else demo_aws_path
)

forecast = pd.read_parquet(forecast_path)
aws = pd.read_csv(aws_path)

forecast["forecast_date"] = pd.to_datetime(
    forecast["forecast_date"]
)

aws["observation_date"] = pd.to_datetime(
    aws["observation_date"]
)


# Average multiple sensors in the same grid cell
observed = (
    aws.groupby(
        [
            "observation_date",
            "latitude",
            "longitude",
        ]
    )
    .agg(
        observed_tmax=("observed_tmax", "mean"),
        sensor_count=("observed_tmax", "count"),
    )
    .reset_index()
)


result = forecast.merge(
    observed,
    left_on=[
        "forecast_date",
        "latitude",
        "longitude",
    ],
    right_on=[
        "observation_date",
        "latitude",
        "longitude",
    ],
    how="inner",
)


if result.empty:
    raise ValueError(
        "No matching AWS observations and forecasts found."
    )


result["error"] = (
    result["observed_tmax"]
    - result["predicted_tmax"]
)

result["absolute_error"] = result["error"].abs()

mae = result["absolute_error"].mean()

rmse = np.sqrt(
    (result["error"] ** 2).mean()
)

bias = result["error"].mean()

status = (
    "PASS"
    if mae <= 1.0
    else "REVIEW"
)

result.to_csv(output_path, index=False)

print("AWS forecast validation completed.")
print("Input:", aws_path)
print("Matched rows:", len(result))
print(f"MAE: {mae:.3f}°C")
print(f"RMSE: {rmse:.3f}°C")
print(f"Bias: {bias:.3f}°C")
print("Status:", status)
print("Saved to:", output_path)