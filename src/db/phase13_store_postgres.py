import os
from pathlib import Path

import pandas as pd
import psycopg


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

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is missing."
    )


df = pd.read_csv(DHRI_PATH)

if AWS_PATH.exists():
    aws = pd.read_csv(AWS_PATH)

    aws = aws[
        [
            "forecast_date",
            "latitude",
            "longitude",
            "observed_tmax",
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
    df["observed_tmax"] = None


def make_decision(row):
    if (
        row["dhri_score"] >= 75
        or (
            row["heatwave_probability"] >= 0.90
            and row["severity"] in ["High", "Extreme"]
        )
    ):
        return "Issue Heatwave Warning"

    if (
        row["dhri_score"] >= 50
        or row["heatwave_probability"] >= 0.50
        or row["severity"] in ["High", "Extreme"]
    ):
        return "Prepare Heatwave Advisory"

    if (
        row["dhri_score"] >= 25
        or row["heatwave_probability"] >= 0.20
        or row["severity"] == "Moderate"
        or row["hotspot_score"] >= 50
    ):
        return "Watch"

    return "No Warning"


df["decision"] = df.apply(
    make_decision,
    axis=1,
)


create_table_sql = """
CREATE TABLE IF NOT EXISTS heatwave_alerts (
    id BIGSERIAL PRIMARY KEY,
    forecast_date DATE NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    actual_temperature DOUBLE PRECISION,
    predicted_temperature DOUBLE PRECISION,
    heatwave_probability DOUBLE PRECISION,
    severity TEXT,
    hotspot_score DOUBLE PRECISION,
    dhri DOUBLE PRECISION,
    decision TEXT,
    stakeholder TEXT NOT NULL DEFAULT 'system',
    advisory TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (
        forecast_date,
        latitude,
        longitude,
        stakeholder
    )
);
"""


insert_sql = """
INSERT INTO heatwave_alerts (
    forecast_date,
    latitude,
    longitude,
    actual_temperature,
    predicted_temperature,
    heatwave_probability,
    severity,
    hotspot_score,
    dhri,
    decision,
    stakeholder,
    advisory
)
VALUES (
    %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s
)
ON CONFLICT (
    forecast_date,
    latitude,
    longitude,
    stakeholder
)
DO UPDATE SET
    actual_temperature = EXCLUDED.actual_temperature,
    predicted_temperature = EXCLUDED.predicted_temperature,
    heatwave_probability = EXCLUDED.heatwave_probability,
    severity = EXCLUDED.severity,
    hotspot_score = EXCLUDED.hotspot_score,
    dhri = EXCLUDED.dhri,
    decision = EXCLUDED.decision,
    created_at = NOW();
"""


rows = []

for _, row in df.iterrows():
    rows.append(
        (
            row["forecast_date"],
            row["latitude"],
            row["longitude"],
            row.get("observed_tmax"),
            row["predicted_tmax"],
            row["heatwave_probability"],
            row["severity"],
            row["hotspot_score"],
            row["dhri_score"],
            row["decision"],
            "system",
            None,
        )
    )


with psycopg.connect(DATABASE_URL) as connection:
    with connection.cursor() as cursor:
        cursor.execute(create_table_sql)
        cursor.executemany(insert_sql, rows)


print("Phase 13 completed successfully.")
print("Rows stored:", len(rows))
print("Table: heatwave_alerts")