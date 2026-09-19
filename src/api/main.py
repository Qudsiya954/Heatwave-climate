import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

import psycopg
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
JWT_SECRET = os.getenv("JWT_SECRET")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing.")

if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET is missing. Add it to the root .env file.")


app = FastAPI(
    title="Climate Intelligence API",
    version="1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://heatwave-climate-git-main-qudsiyas954-5358s-projects.vercel.app",
],
    allow_origin_regex=r"https://.*\.vercel\.app",
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

password_hasher = PasswordHasher()
bearer_scheme = HTTPBearer(auto_error=False)


class RegisterRequest(BaseModel):
    full_name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


def unauthorized(detail="Invalid or expired token."):
    return HTTPException(
        status_code=401,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def encode_part(value):
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def decode_part(value):
    padding = "=" * (-len(value) % 4)
    return json.loads(base64.urlsafe_b64decode(value + padding))


def create_token(user):
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "exp": int(time.time()) + 60 * 60 * 24,
    }

    unsigned = encode_part(header) + "." + encode_part(payload)
    signature = hmac.new(
        JWT_SECRET.encode(),
        unsigned.encode(),
        hashlib.sha256,
    ).digest()

    return unsigned + "." + base64.urlsafe_b64encode(
        signature
    ).rstrip(b"=").decode()


def read_token(token):
    try:
        header, payload, signature = token.split(".")
        unsigned = header + "." + payload
        expected = hmac.new(
            JWT_SECRET.encode(),
            unsigned.encode(),
            hashlib.sha256,
        ).digest()
        actual = base64.urlsafe_b64decode(
            signature + "=" * (-len(signature) % 4)
        )

        if not hmac.compare_digest(expected, actual):
            raise unauthorized()

        data = decode_part(payload)

        if int(data["exp"]) < int(time.time()):
            raise unauthorized("Token expired.")

        return data
    except HTTPException:
        raise
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise unauthorized()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
):
    if not credentials:
        raise unauthorized("Login is required.")

    payload = read_token(credentials.credentials)

    with psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
    ) as connection:
        user = connection.execute(
            """
            SELECT id, full_name, email, role, created_at
            FROM users
            WHERE id = %s
            """,
            (int(payload["sub"]),),
        ).fetchone()

    if not user:
        raise unauthorized("User no longer exists.")

    return dict(user)


def auth_response(user):
    return {
        "access_token": create_token(user),
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "full_name": user["full_name"],
            "email": user["email"],
            "role": user["role"],
        },
    }


@app.post("/auth/register")
def register(request: RegisterRequest):
    full_name = request.full_name.strip()
    email = request.email.strip().lower()

    if len(full_name) < 2:
        raise HTTPException(
            status_code=400,
            detail="Full name is required.",
        )

    if "@" not in email:
        raise HTTPException(
            status_code=400,
            detail="Enter a valid email address.",
        )

    if len(request.password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least 8 characters.",
        )

    try:
        with psycopg.connect(
            DATABASE_URL,
            row_factory=dict_row,
        ) as connection:
            user = connection.execute(
                """
                INSERT INTO users (full_name, email, password_hash)
                VALUES (%s, %s, %s)
                RETURNING id, full_name, email, role
                """,
                (
                    full_name,
                    email,
                    password_hasher.hash(request.password),
                ),
            ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists.",
        )

    return auth_response(user)


@app.post("/auth/login")
def login(request: LoginRequest):
    email = request.email.strip().lower()

    with psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
    ) as connection:
        user = connection.execute(
            """
            SELECT id, full_name, email, role, password_hash
            FROM users
            WHERE email = %s
            """,
            (email,),
        ).fetchone()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password.",
        )

    try:
        password_hasher.verify(user["password_hash"], request.password)
    except (VerifyMismatchError, VerificationError):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password.",
        )

    return auth_response(user)


@app.get("/auth/me")
def me(user=Depends(get_current_user)):
    return user


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
def predict(limit: int = 100, user=Depends(get_current_user)):
    return fetch_rows(limit=limit)


@app.get("/forecast")
def forecast(limit: int = 100, user=Depends(get_current_user)):
    return fetch_rows(limit=limit)


@app.get("/heatwave")
def heatwave(
    minimum_probability: float = 0.20,
    limit: int = 100,
    user=Depends(get_current_user),
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
    user=Depends(get_current_user),
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
    user=Depends(get_current_user),
):
    return fetch_rows(
        "AND hotspot_score >= %s",
        (minimum_score,),
        limit,
    )


@app.get("/risk")
def risk(limit: int = 100, user=Depends(get_current_user)):
    return fetch_rows(limit=limit)


@app.get("/advisory")
def advisory(
    limit: int = 50,
    user=Depends(get_current_user),
):
    query = f"""
        SELECT {COLUMNS}
        FROM heatwave_alerts
        WHERE stakeholder <> 'system'
          AND advisory IS NOT NULL
        ORDER BY forecast_date DESC, dhri DESC, stakeholder
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
    user=Depends(get_current_user),
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
