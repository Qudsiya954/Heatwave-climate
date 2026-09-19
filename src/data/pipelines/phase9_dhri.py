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

HOTSPOT_PATH = (
    PROJECT_ROOT
    / "Data"
    / "processed"
    / "hotspot_scores.csv"
)

THRESHOLD_PATH = (
    PROJECT_ROOT
    / "models"
    / "severity_threshold_metadata.joblib"
)

HEATWAVE_MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "heatwave_xgb.joblib"
)

HEATWAVE_METADATA_PATH = (
    PROJECT_ROOT
    / "models"
    / "heatwave_metadata.joblib"
)


groups = ["latitude", "longitude"]


# Load files
raw = pd.read_parquet(DATA_PATH)
phase7 = pd.read_parquet(PHASE7_PATH)
hotspots = pd.read_csv(HOTSPOT_PATH)

threshold_metadata = joblib.load(THRESHOLD_PATH)
heatwave_model = joblib.load(HEATWAVE_MODEL_PATH)
heatwave_metadata = joblib.load(HEATWAVE_METADATA_PATH)

thresholds = threshold_metadata["thresholds"]
monthly_baseline = threshold_metadata["monthly_baseline"]
heatwave_features = heatwave_metadata["features"]

raw["date"] = pd.to_datetime(raw["date"])

raw = (
    raw.sort_values(groups + ["date"])
       .reset_index(drop=True)
)


# Rebuild XGBoost features
raw["month"] = raw["date"].dt.month
raw["day_of_year"] = raw["date"].dt.dayofyear

raw["month_sin"] = np.sin(
    2 * np.pi * raw["day_of_year"] / 365.25
)

raw["month_cos"] = np.cos(
    2 * np.pi * raw["day_of_year"] / 365.25
)

for lag in [1, 2, 3, 7]:
    raw[f"temp_lag_{lag}"] = (
        raw.groupby(groups)["max_temperature"]
           .shift(lag)
    )

raw["temp_rolling_mean_3"] = (
    raw.groupby(groups)["max_temperature"]
       .transform(
           lambda x: x.shift(1).rolling(3).mean()
       )
)

raw["temp_rolling_mean_7"] = (
    raw.groupby(groups)["max_temperature"]
       .transform(
           lambda x: x.shift(1).rolling(7).mean()
       )
)

raw["temp_rolling_std_7"] = (
    raw.groupby(groups)["max_temperature"]
       .transform(
           lambda x: x.shift(1).rolling(7).std()
       )
)

raw["temperature_change_1d"] = (
    raw["temp_lag_1"] - raw["temp_lag_2"]
)

raw["temperature_change_3d"] = (
    raw["temp_lag_1"] - raw["temp_lag_3"]
)

raw = raw.merge(
    monthly_baseline,
    on=groups + ["month"],
    how="left",
)

raw = raw.merge(
    thresholds,
    on=groups,
    how="left",
)

raw["anomaly_lag_1"] = (
    raw["temp_lag_1"]
    - raw["monthly_baseline"]
)


# Current extreme-heat persistence
raw["extreme_heat"] = (
    raw["max_temperature"]
    > raw["p95_temperature"]
)

raw["not_extreme"] = (
    ~raw["extreme_heat"]
).astype(int)

raw["streak_group"] = (
    raw.groupby(groups)["not_extreme"]
       .cumsum()
)

raw["extreme_heat_streak"] = (
    raw.groupby(groups + ["streak_group"])["extreme_heat"]
       .transform("sum")
)

raw.loc[
    ~raw["extreme_heat"],
    "extreme_heat_streak"
] = 0


# Get latest usable row per grid cell
latest = (
    raw.dropna(subset=heatwave_features)
       .sort_values(groups + ["date"])
       .groupby(groups)
       .tail(1)
       .copy()
)

latest["heatwave_probability"] = (
    heatwave_model
    .predict_proba(latest[heatwave_features])[:, 1]
)


# Combine Phase 7, Phase 8, and XGBoost results
result = phase7.merge(
    hotspots[groups + ["hotspot_score"]],
    on=groups,
    how="left",
)

result = result.merge(
    latest[
        groups
        + [
            "extreme_heat_streak",
            "heatwave_probability",
        ]
    ],
    on=groups,
    how="left",
)


# DHRI components
result["temperature_component"] = (
    (
        result["predicted_tmax"]
        - result["p95_temperature"]
    )
    / (
        result["p99_temperature"]
        - result["p95_temperature"]
    )
).clip(0, 1)

result["hotspot_component"] = (
    result["hotspot_score"] / 100
)

result["forecast_anomaly"] = (
    result["predicted_tmax"]
    - result["monthly_baseline"]
)


def scale(series):
    if series.max() == series.min():
        return pd.Series(0.0, index=series.index)

    return (
        (series - series.min())
        / (series.max() - series.min())
    )


result["anomaly_component"] = scale(
    result["forecast_anomaly"].clip(lower=0)
)

result["persistence_component"] = scale(
    result["extreme_heat_streak"].clip(lower=0)
)


# Final DHRI score
result["dhri_score"] = 100 * (
    0.30 * result["temperature_component"]
    + 0.25 * result["heatwave_probability"]
    + 0.20 * result["hotspot_component"]
    + 0.15 * result["anomaly_component"]
    + 0.10 * result["persistence_component"]
)

result["risk_level"] = pd.cut(
    result["dhri_score"],
    bins=[-np.inf, 25, 50, 75, np.inf],
    labels=[
        "Low",
        "Moderate",
        "High",
        "Critical",
    ],
)


# Save only the final DHRI output
output_path = (
    PROJECT_ROOT
    / "Data"
    / "processed"
    / "dhri_scores.csv"
)

result[
    [
        "latitude",
        "longitude",
        "forecast_date",
        "predicted_tmax",
        "severity",
        "heatwave_probability",
        "hotspot_score",
        "forecast_anomaly",
        "dhri_score",
        "risk_level",
    ]
].sort_values(
    "dhri_score",
    ascending=False,
).to_csv(
    output_path,
    index=False,
)


print("Phase 9 completed successfully.")
print("Grid cells:", len(result))
print("\nTop 10 DHRI locations:")
print(
    result[
        [
            "latitude",
            "longitude",
            "dhri_score",
            "risk_level",
            "predicted_tmax",
            "severity",
            "heatwave_probability",
            "hotspot_score",
        ]
    ]
    .sort_values("dhri_score", ascending=False)
    .head(10)
    .to_string(index=False)
)

print("\nSaved to:")
print(output_path)