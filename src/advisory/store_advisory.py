import os
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv
from google import genai


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing.")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing.")


DATA_PATH = ROOT / "Data" / "processed" / "dhri_scores.csv"
STAKEHOLDER_GUIDANCE = {
    "Citizen": "Give simple public safety actions for residents.",
    "Farmer": "Give practical advice about field work, crops, livestock, and water.",
    "Health Agency": "Give actions for health monitoring, hospitals, and vulnerable groups.",
    "Local Authority": "Give actions for alerts, cooling centres, water, and emergency response.",
}


df = pd.read_csv(DATA_PATH)
actionable = df[
    (df["severity"].isin(["Moderate", "High", "Extreme"]))
    | (df["hotspot_score"] >= 50)
]

row = (
    actionable.sort_values("dhri_score", ascending=False).iloc[0]
    if not actionable.empty
    else df.sort_values("dhri_score", ascending=False).iloc[0]
)

probability = float(row["heatwave_probability"])
severity = str(row["severity"])
dhri = float(row["dhri_score"])
hotspot_score = float(row["hotspot_score"])

if dhri >= 75 or (
    probability >= 0.90 and severity in ["High", "Extreme"]
):
    decision = "Issue Heatwave Warning"
elif dhri >= 50 or probability >= 0.50 or severity in ["High", "Extreme"]:
    decision = "Prepare Heatwave Advisory"
elif (
    dhri >= 25
    or probability >= 0.20
    or severity == "Moderate"
    or hotspot_score >= 50
):
    decision = "Watch"
else:
    decision = "No Warning"


client = genai.Client(api_key=GEMINI_API_KEY)

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
    decision = EXCLUDED.decision,
    advisory = EXCLUDED.advisory,
    created_at = NOW();
"""


stored = 0

with psycopg.connect(DATABASE_URL) as connection:
    for stakeholder, guidance in STAKEHOLDER_GUIDANCE.items():
        prompt = f"""
Create a short heatwave advisory for the stakeholder: {stakeholder}.
{guidance}

Structured information:
Location: latitude {row["latitude"]}, longitude {row["longitude"]}
Forecast date: {row["forecast_date"]}
Predicted Tmax: {row["predicted_tmax"]:.1f}°C
Severity: {severity}
Heatwave probability: {probability * 100:.2f}%
DHRI: {dhri:.2f}
Decision: {decision}

Do not invent weather values.
Use simple English.
Give one headline and three practical actions.
If risk is low, clearly say that no heatwave warning is required.
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        advisory = (response.text or "").strip()

        connection.execute(
            insert_sql,
            (
                pd.to_datetime(row["forecast_date"]).date(),
                row["latitude"],
                row["longitude"],
                None,
                row["predicted_tmax"],
                probability,
                severity,
                hotspot_score,
                dhri,
                decision,
                stakeholder,
                advisory,
            ),
        )

        stored += 1
        print("Stored:", stakeholder)


print("All stakeholder advisories stored successfully.")
print("Advisories stored:", stored)
print("Decision:", decision)
