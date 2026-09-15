import json
import os
from pathlib import Path

import pandas as pd
from google import genai


STAKEHOLDER = "Health Agency"
# Options:
# Citizen
# Farmer
# Health Agency
# Local Authority


ROOT = Path(__file__).resolve()

while not (ROOT / "Data" / "processed").exists():
    ROOT = ROOT.parent


DHRI_PATH = (
    ROOT
    / "Data"
    / "processed"
    / "dhri_scores.csv"
)


df = pd.read_csv(DHRI_PATH)

# Select the highest-risk current location
row = (
    df.sort_values("dhri_score", ascending=False)
      .iloc[0]
)


probability = float(row["heatwave_probability"])
severity = str(row["severity"])
dhri = float(row["dhri_score"])
hotspot_score = float(row["hotspot_score"])


def get_decision():
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
        or hotspot_score >= 50
    ):
        return "Watch"

    return "No Warning"


decision = get_decision()

alert = {
    "location": {
        "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]),
    },
    "forecast_date": str(row["forecast_date"]),
    "predicted_tmax_c": round(
        float(row["predicted_tmax"]),
        2,
    ),
    "severity": severity,
    "heatwave_probability": round(
        probability * 100,
        2,
    ),
    "historical_hotspot_score": round(
        hotspot_score,
        2,
    ),
    "dhri_score": round(dhri, 2),
    "risk_level": str(row["risk_level"]),
    "decision": decision,
}


stakeholder_guidance = {
    "Citizen": (
        "Give practical advice about outdoor exposure, hydration, "
        "shade, and vulnerable people."
    ),
    "Farmer": (
        "Give advice about field work timing, irrigation, livestock, "
        "and crop protection."
    ),
    "Health Agency": (
        "Focus on vulnerable populations, heat illness preparation, "
        "health monitoring, and medical readiness."
    ),
    "Local Authority": (
        "Focus on public alerts, cooling centres, water supply, "
        "field teams, and emergency coordination."
    ),
}


prompt = f"""
You are a climate-risk advisory assistant.

The structured decision below is authoritative.
Do not change the decision.
Do not invent weather values.
Do not give medical diagnosis.
Use Celsius.

Generate a short advisory for the stakeholder: {STAKEHOLDER}

Stakeholder guidance:
{stakeholder_guidance[STAKEHOLDER]}

Structured alert:
{json.dumps(alert, indent=2)}

Write:
1. A short headline.
2. Two or three practical actions.
3. One sentence explaining the urgency.

Use clear, simple English.
"""


api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError(
        "GEMINI_API_KEY is not set."
    )


client = genai.Client(api_key=api_key)

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt,
)


print("Phase 12 completed successfully.")
print("\nStructured alert:")
print(json.dumps(alert, indent=2))

print("\nGemini advisory:")
print(response.text)