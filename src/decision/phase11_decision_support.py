from pathlib import Path

import numpy as np
import pandas as pd


# Find project root
ROOT = Path(__file__).resolve()

while not (ROOT / "Data" / "processed").exists():
    ROOT = ROOT.parent


DHRI_PATH = (
    ROOT
    / "Data"
    / "processed"
    / "dhri_scores.csv"
)

AWS_PATH = (
    ROOT
    / "Data"
    / "processed"
    / "aws_forecast_validation.csv"
)

# Load DHRI output
df = pd.read_csv(DHRI_PATH)

df["heatwave_probability"] = (
    df["heatwave_probability"].astype(float)
)

df["hotspot_score"] = (
    df["hotspot_score"].astype(float)
)

df["dhri_score"] = (
    df["dhri_score"].astype(float)
)


# Add AWS validation observations if available
if AWS_PATH.exists():
    aws = pd.read_csv(AWS_PATH)

    aws = aws[
        [
            "forecast_date",
            "latitude",
            "longitude",
            "observed_tmax",
            "absolute_error",
        ]
    ]

    df = df.merge(
        aws,
        on=[
            "forecast_date",
            "latitude",
            "longitude",
        ],
        how="left",
    )
else:
    df["observed_tmax"] = np.nan
    df["absolute_error"] = np.nan


def make_decision(row):
    probability = row["heatwave_probability"]
    severity = row["severity"]
    dhri = row["dhri_score"]

    if (
        dhri >= 75
        or (
            probability >= 0.90
            and severity in ["High", "Extreme"]
        )
    ):
        return "Issue Heatwave Warning"

    if (
        dhri >= 50
        or probability >= 0.50
        or severity in ["High", "Extreme"]
    ):
        return "Prepare Heatwave Advisory"

    if (
        dhri >= 25
        or probability >= 0.20
        or severity == "Moderate"
        or row["hotspot_score"] >= 50
    ):
        return "Watch"

    return "No Warning"


def action_for(decision):
    actions = {
        "Issue Heatwave Warning": (
            "Notify authorities, health agencies, farmers, "
            "and citizens."
        ),
        "Prepare Heatwave Advisory": (
            "Prepare targeted advisories and monitor observations."
        ),
        "Watch": (
            "Continue monitoring and prepare precautionary guidance."
        ),
        "No Warning": (
            "Continue routine monitoring."
        ),
    }

    return actions[decision]


df["decision"] = df.apply(
    make_decision,
    axis=1,
)

df["recommended_action"] = (
    df["decision"].map(action_for)
)

df["aws_status"] = np.select(
    [
        df["observed_tmax"].isna(),
        df["absolute_error"] <= 1.5,
    ],
    [
        "NOT_AVAILABLE",
        "OK",
    ],
    default="CHECK",
)

print("Phase 11 completed successfully.")
print("\nDecision counts:")
print(df["decision"].value_counts())

print("\nTop decisions:")
print(
    df[
        [
            "latitude",
            "longitude",
            "dhri_score",
            "severity",
            "decision",
        ]
    ]
    .sort_values("dhri_score", ascending=False)
    .head(10)
    .to_string(index=False)
)
