from pathlib import Path

import joblib
import numpy as np
import pandas as pd


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

MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "temperature_forecasting_lgbm.joblib"
)

FORECAST_METADATA_PATH = (
    PROJECT_ROOT
    / "models"
    / "temperature_forecasting_metadata.joblib"
)

SEVERITY_METADATA_PATH = (
    PROJECT_ROOT
    / "models"
    / "severity_metadata.joblib"
)


# Load data and models
df = pd.read_parquet(DATA_PATH)
df["date"] = pd.to_datetime(df["date"])

model = joblib.load(MODEL_PATH)
forecast_metadata = joblib.load(FORECAST_METADATA_PATH)
severity_metadata = joblib.load(SEVERITY_METADATA_PATH)

features = forecast_metadata["features"]
best_iteration = forecast_metadata["best_iteration"]

group_cols = ["latitude", "longitude"]

thresholds = severity_metadata["p95"].copy()
monthly_baseline = severity_metadata["monthly_baseline"].copy()


# Sort data
df = (
    df.sort_values(group_cols + ["date"])
      .reset_index(drop=True)
)


# Calendar features
df["month"] = df["date"].dt.month
df["day_of_year"] = df["date"].dt.dayofyear

df["month_sin"] = np.sin(
    2 * np.pi * df["day_of_year"] / 365.25
)

df["month_cos"] = np.cos(
    2 * np.pi * df["day_of_year"] / 365.25
)


# Lag features
for lag in [1, 2, 3, 7]:
    df[f"temp_lag_{lag}"] = (
        df.groupby(group_cols)["max_temperature"]
          .shift(lag)
    )


# Rolling features
df["temp_rolling_mean_3"] = (
    df.groupby(group_cols)["max_temperature"]
      .transform(
          lambda x: x.shift(1).rolling(3).mean()
      )
)

df["temp_rolling_mean_7"] = (
    df.groupby(group_cols)["max_temperature"]
      .transform(
          lambda x: x.shift(1).rolling(7).mean()
      )
)

df["temp_rolling_std_7"] = (
    df.groupby(group_cols)["max_temperature"]
      .transform(
          lambda x: x.shift(1).rolling(7).std()
      )
)


# Temperature changes
df["temperature_change_1d"] = (
    df["temp_lag_1"] - df["temp_lag_2"]
)

df["temperature_change_3d"] = (
    df["temp_lag_1"] - df["temp_lag_3"]
)


# Monthly baseline and anomaly
df = df.merge(
    monthly_baseline,
    on=group_cols + ["month"],
    how="left",
)

df["temperature_anomaly"] = (
    df["max_temperature"]
    - df["monthly_baseline"]
)

df["anomaly_lag_1"] = (
    df["temp_lag_1"]
    - df["monthly_baseline"]
)


# Get latest usable row for every grid cell
latest = (
    df.dropna(subset=features)
      .sort_values(group_cols + ["date"])
      .groupby(group_cols)
      .tail(1)
      .copy()
)


# Predict next-day maximum temperature
predicted_tmax = model.predict(
    latest[features],
    num_iteration=best_iteration,
)


result = latest[
    [
        "date",
        "latitude",
        "longitude",
        "max_temperature",
        "monthly_baseline",
    ]
].copy()

result = result.rename(
    columns={
        "date": "source_date",
        "max_temperature": "latest_tmax",
    }
)

result["forecast_date"] = (
    result["source_date"]
    + pd.Timedelta(days=1)
)

result["predicted_tmax"] = predicted_tmax


# Add location-specific thresholds
result = result.merge(
    thresholds,
    on=group_cols,
    how="left",
)


# Assign severity
temperature = result["predicted_tmax"]

result["severity_code"] = np.select(
    [
        temperature < result["p95_temperature"],

        temperature < result["p975_temperature"],

        temperature < result["p99_temperature"],
    ],
    [
        0,  # Normal
        1,  # Moderate
        2,  # High
    ],
    default=3,  # Extreme
)

result["severity"] = result["severity_code"].map(
    {
        0: "Normal",
        1: "Moderate",
        2: "High",
        3: "Extreme",
    }
)

result["predicted_heatwave"] = (
    result["predicted_tmax"]
    >= result["p95_temperature"]
).astype(int)


# Save only the outputs needed later
threshold_output = (
    PROJECT_ROOT
    / "models"
    / "severity_threshold_metadata.joblib"
)

forecast_output = (
    PROJECT_ROOT
    / "Data"
    / "processed"
    / "phase7_severity.parquet"
)


joblib.dump(
    {
        "thresholds": thresholds,
        "monthly_baseline": monthly_baseline,
        "severity_rules": {
            "Normal": "Tmax < P95",
            "Moderate": "P95 <= Tmax < P97.5",
            "High": "P97.5 <= Tmax < P99",
            "Extreme": "Tmax >= P99",
        },
    },
    threshold_output,
)

result.to_parquet(
    forecast_output,
    index=False,
)


# Validation output
print("Phase 7 completed successfully.")
print("Grid cells:", len(result))
print("Forecast date:", result["forecast_date"].min())
print("\nSeverity counts:")
print(result["severity"].value_counts())

print("\nSample predictions:")
print(
    result[
        [
            "latitude",
            "longitude",
            "predicted_tmax",
            "severity",
            "predicted_heatwave",
        ]
    ]
    .head(10)
    .to_string(index=False)
)