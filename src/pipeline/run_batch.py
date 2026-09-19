import argparse
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]

load_dotenv(ROOT / ".env")

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "pipeline.log"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("climate_pipeline")


REQUIRED_FILES = [
    ROOT / "Data/processed/imd_temperature_2010_2025.parquet",
    ROOT / "models/temperature_forecasting_lgbm.joblib",
    ROOT / "models/temperature_forecasting_metadata.joblib",
    ROOT / "models/severity_metadata.joblib",
    ROOT / "models/severity_threshold_metadata.joblib",
    ROOT / "models/heatwave_xgb.joblib",
    ROOT / "models/heatwave_metadata.joblib",
]


SCRIPTS = {
    "severity": ROOT / "src/data/pipelines/phase7_severity.py",
    "hotspots": ROOT / "src/data/pipelines/phase8_hotspots.py",
    "dhri": ROOT / "src/data/pipelines/phase9_dhri.py",
    "database": ROOT / "src/db/phase13_store_postgres.py",
    "advisory": ROOT / "src/advisory/store_advisory.py",
    "aws_validation": ROOT / "src/validation/validate_aws_forecast.py",
}


GENERATED_FILES = [
    ROOT / "Data/processed/phase7_severity.parquet",
    ROOT / "Data/processed/hotspot_scores.csv",
    ROOT / "Data/processed/dhri_scores.csv",
    ROOT / "Data/processed/aws_forecast_validation.csv",
]


def check_inputs():
    missing = [str(path) for path in REQUIRED_FILES if not path.exists()]

    if missing:
        raise FileNotFoundError(
            "Missing required files:\n" + "\n".join(missing)
        )

    if not os.getenv("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is missing.")


def run_step(name, script, attempts=3):
    logger.info("Starting: %s", name)

    for attempt in range(1, attempts + 1):
        try:
            result = subprocess.run(
                [sys.executable, str(script)],
                cwd=ROOT,
                env=os.environ.copy(),
                text=True,
                capture_output=True,
                check=True,
            )

            if result.stdout:
                logger.info(result.stdout.strip())

            logger.info("Completed: %s", name)
            return

        except subprocess.CalledProcessError as error:
            logger.error(
                "%s failed on attempt %s/%s",
                name,
                attempt,
                attempts,
            )

            if error.stderr:
                logger.error(error.stderr.strip())

            if attempt < attempts:
                time.sleep(5 * attempt)

    raise RuntimeError(f"{name} failed after {attempts} attempts.")


def important_alert_exists():
    path = ROOT / "Data/processed/dhri_scores.csv"
    df = pd.read_csv(path)

    return (
        df["severity"].isin(["Moderate", "High", "Extreme"]).any()
        or (df["heatwave_probability"] >= 0.20).any()
        or (df["dhri_score"] >= 25).any()
        or (df["hotspot_score"] >= 50).any()
    )


def cleanup():
    for path in GENERATED_FILES:
        if path.exists():
            path.unlink()
            logger.info("Removed intermediate file: %s", path.name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Keep intermediate CSV and Parquet files.",
    )
    args = parser.parse_args()

    check_inputs()

    real_aws = ROOT / "Data/iot/aws_observations.csv"

    run_step("Phase 7 severity", SCRIPTS["severity"])
    run_step("Phase 8 hotspots", SCRIPTS["hotspots"])
    run_step("Phase 9 DHRI", SCRIPTS["dhri"])

    if real_aws.exists():
        run_step("AWS forecast validation", SCRIPTS["aws_validation"])
    else:
        logger.warning(
            "Real AWS file not found. AWS validation skipped."
        )

        old_validation = (
            ROOT / "Data/processed/aws_forecast_validation.csv"
        )

        if old_validation.exists():
            old_validation.unlink()

    run_step("PostgreSQL upsert", SCRIPTS["database"])

    if important_alert_exists():
        if not os.getenv("GEMINI_API_KEY"):
            raise RuntimeError(
                "GEMINI_API_KEY is required for important alerts."
            )

        run_step("Stakeholder Gemini advisories", SCRIPTS["advisory"])
    else:
        logger.info(
            "No important alert found. Gemini advisory skipped."
        )

    if not args.keep_artifacts:
        cleanup()

    logger.info("Production batch completed successfully.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Production batch failed.")
        raise SystemExit(1)