import os

import psycopg
from fastapi import FastAPI, HTTPException
from psycopg.rows import dict_row
from fastapi.middleware.cors import CORSMiddleware

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]

load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing.")

app = FastAPI(
    title="Climate Intelligence API",
    version="1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

COLUMNS = """
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
    advisory,
    stakeholder
"""


def add_flags(row):
    row = dict(row)

    dhri = float(row["dhri"] or 0)
    hotspot_score = float(row["hotspot_score"] or 0)

    row["hotspot"] = hotspot_score >= 50
    row["risk_level"] = (
        "Critical" if dhri >= 75
        else "High" if dhri >= 50
        else "Moderate" if dhri >= 25
        else "Low"
    )

    row["temperature"] = row["predicted_temperature"]

    return row


def fetch_rows(where="", params=(), limit=100):
    query = f"""
        SELECT {COLUMNS}
        FROM heatwave_alerts
        WHERE stakeholder = 'system'
        {where}
        ORDER BY dhri DESC
        LIMIT %s
    """

    with psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
    ) as connection:
        rows = connection.execute(
            query,
            (*params, limit),
        ).fetchall()

    return [add_flags(row) for row in rows]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/predict")
def predict(limit: int = 100):
    return fetch_rows(limit=limit)


@app.get("/forecast")
def forecast(limit: int = 100):
    return fetch_rows(limit=limit)


@app.get("/heatwave")
def heatwave(
    minimum_probability: float = 0.20,
    limit: int = 100,
):
    return fetch_rows(
        "AND heatwave_probability >= %s",
        (minimum_probability,),
        limit,
    )


@app.get("/severity")
def severity(
    level: str | None = None,
    limit: int = 100,
):
    if level:
        return fetch_rows(
            "AND severity = %s",
            (level,),
            limit,
        )

    return fetch_rows(limit=limit)


@app.get("/hotspots")
def hotspots(
    minimum_score: float = 50,
    limit: int = 100,
):
    return fetch_rows(
        "AND hotspot_score >= %s",
        (minimum_score,),
        limit,
    )


@app.get("/risk")
def risk(limit: int = 100):
    return fetch_rows(limit=limit)


@app.get("/advisory")
def advisory(limit: int = 10):
    query = f"""
        SELECT {COLUMNS}
        FROM heatwave_alerts
        WHERE stakeholder <> 'system'
          AND advisory IS NOT NULL
        ORDER BY forecast_date DESC, dhri DESC
        LIMIT %s
    """

    with psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
    ) as connection:
        rows = connection.execute(
            query,
            (limit,),
        ).fetchall()

    return [add_flags(row) for row in rows]

@app.get("/intelligence")
def intelligence(
    latitude: float | None = None,
    longitude: float | None = None,
):
    if latitude is not None and longitude is not None:
        rows = fetch_rows(
            "AND latitude = %s AND longitude = %s",
            (latitude, longitude),
            1,
        )
    else:
        rows = fetch_rows(limit=1)

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No intelligence record found.",
        )

    return rows[0]