from pathlib import Path

import joblib
import numpy as np
import pandas as pd


# Find project root
PROJECT_ROOT = Path(__file__).resolve()

while not (
    (PROJECT_ROOT / "Data" / "processed").exists()
    and (PROJECT_ROOT / "models").exists()
):
    PROJECT_ROOT = PROJECT_ROOT.parent


DATA_PATH = (
    PROJECT_ROOT
    / "Data"
    / "processed"
    / "imd_temperature_2010_2025.parquet"
)

PHASE7_PATH = (
    PROJECT_ROOT
    / "Data"
    / "processed"
    / "phase7_severity.parquet"
)

THRESHOLD_PATH = (
    PROJECT_ROOT
    / "models"
    / "severity_threshold_metadata.joblib"
)


# Load files
df = pd.read_parquet(DATA_PATH)
forecast = pd.read_parquet(PHASE7_PATH)
metadata = joblib.load(THRESHOLD_PATH)

thresholds = metadata["thresholds"]
monthly_baseline = metadata["monthly_baseline"]

groups = ["latitude", "longitude"]


# Prepare historical data
df["date"] = pd.to_datetime(df["date"])
df["month"] = df["date"].dt.month

df = df.dropna(subset=["max_temperature"])

df = df.merge(
    thresholds,
    on=groups,
    how="left",
)

df = df.merge(
    monthly_baseline,
    on=groups + ["month"],
    how="left",
)

df["anomaly"] = (
    df["max_temperature"]
    - df["monthly_baseline"]
)

df["heatwave"] = (
    df["max_temperature"]
    >= df["p95_temperature"]
).astype(int)

df["extreme"] = (
    df["max_temperature"]
    >= df["p99_temperature"]
).astype(int)

df["severity_code"] = np.select(
    [
        df["max_temperature"] < df["p95_temperature"],
        df["max_temperature"] < df["p975_temperature"],
        df["max_temperature"] < df["p99_temperature"],
    ],
    [0, 1, 2],
    default=3,
)

df["positive_anomaly"] = df["anomaly"].clip(lower=0)


# Aggregate location-level risk
hotspots = (
    df.groupby(groups)
      .agg(
          heatwave_frequency=("heatwave", "mean"),
          extreme_temperature_frequency=("extreme", "mean"),
          historical_mean_severity=("severity_code", "mean"),
          mean_positive_anomaly=("positive_anomaly", "mean"),
          observation_count=("max_temperature", "count"),
      )
      .reset_index()
)


# Normalize values between 0 and 1
def scale(series):
    if series.max() == series.min():
        return pd.Series(0.0, index=series.index)

    return (
        (series - series.min())
        / (series.max() - series.min())
    )


hotspots["hotspot_score"] = 100 * (
    0.30 * scale(hotspots["heatwave_frequency"])
    + 0.30 * scale(
        hotspots["extreme_temperature_frequency"]
    )
    + 0.25 * (
        hotspots["historical_mean_severity"] / 3
    )
    + 0.15 * scale(
        hotspots["mean_positive_anomaly"]
    )
)


hotspots["hotspot_level"] = pd.cut(
    hotspots["hotspot_score"],
    bins=[-np.inf, 25, 50, 75, np.inf],
    labels=["Low", "Moderate", "High", "Critical"],
)


# Add next-day forecast severity
hotspots = hotspots.merge(
    forecast[
        groups
        + [
            "forecast_date",
            "predicted_tmax",
            "severity",
        ]
    ],
    on=groups,
    how="left",
)


# Sort highest-risk locations first
hotspots = hotspots.sort_values(
    "hotspot_score",
    ascending=False,
)


# Save only the final hotspot output
output_path = (
    PROJECT_ROOT
    / "Data"
    / "processed"
    / "hotspot_scores.csv"
)

hotspots.to_csv(
    output_path,
    index=False,
)


print("Phase 8 completed successfully.")
print("Grid cells analysed:", len(hotspots))
print("\nTop 10 hotspot locations:")
print(
    hotspots.head(10).to_string(index=False)
)

print("\nSaved to:")
print(output_path)