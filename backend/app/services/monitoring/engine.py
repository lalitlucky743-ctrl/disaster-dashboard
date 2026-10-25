
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import SessionLocal
from app.models import MonitoringRun
from app.services.alerts.imd import fetch_imd_district_warnings
from app.services.alerts.sachet import fetch_sachet_alerts
from app.services.alerts.normalizer import normalize_district
from app.ml.data.landslide.landslide_predictor import (
    predict_landslide_live as predict_production,
)

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 300

DISTRICTS = {
    "Almora": (29.5892, 79.6467),
    "Bageshwar": (29.8404, 79.7694),
    "Chamoli": (30.2937, 79.5603),
    "Champawat": (29.3209, 80.0088),
    "Dehradun": (30.3165, 78.0322),
    "Haridwar": (29.9457, 78.1642),
    "Nainital": (29.3919, 79.4542),
    "Pauri Garhwal": (29.8688, 78.8383),
    "Pithoragarh": (29.5829, 80.2182),
    "Rudraprayag": (30.2844, 78.9811),
    "Tehri Garhwal": (30.3012, 78.5661),
    "Udham Singh Nagar": (28.9610, 79.5154),
    "Uttarkashi": (30.7268, 78.4354),
}


def _now():
    return datetime.now(timezone.utc)


def _district_from_area(area):
    """Only match a district when its name is explicitly present."""
    if not area:
        return None

    text = re.sub(r"[^a-z0-9 ]+", " ", str(area).lower())
    text = re.sub(r"\s+", " ", text).strip()

    matches = []
    for district in DISTRICTS:
        name = district.lower()
        if re.search(rf"\b{re.escape(name)}\b", text):
            matches.append(district)

    # Avoid guessing if the area refers to multiple districts.
    return matches[0] if len(matches) == 1 else None


async def _fetch_official_sources():
    results = {
        "IMD": {"status": "error", "alerts": [], "error": None},
        "SACHET": {"status": "error", "alerts": [], "error": None},
    }

    try:
        alerts = await fetch_imd_district_warnings()
        results["IMD"] = {
            "status": "ok",
            "alerts": alerts,
            "error": None,
        }
    except Exception as exc:
        logger.exception("IMD monitoring fetch failed")
        results["IMD"]["error"] = str(exc)

    try:
        response = await fetch_sachet_alerts()

        if response.get("status") in ("updated", "not_modified"):
            results["SACHET"] = {
                "status": "ok",
                "alerts": response.get("alerts", []),
                "error": None,
            }
        else:
            results["SACHET"]["error"] = response.get(
                "message", "SACHET source returned an error"
            )
    except Exception as exc:
        logger.exception("SACHET monitoring fetch failed")
        results["SACHET"]["error"] = str(exc)

    return results


def _alert_district(alert, source):
    if source == "IMD":
        return normalize_district(alert.get("district"))

    return _district_from_area(alert.get("area"))


def _predict_safely(model_function, latitude, longitude):
    try:
        result = model_function(
            latitude=latitude,
            longitude=longitude,
        )

        if not isinstance(result, dict):
            raise ValueError("Model returned a non-dictionary result")

        score = result.get("risk_score")
        level = result.get("risk_level")
        version = result.get("model_version")

        if score is None or level is None or not version:
            raise ValueError(
                "Missing risk_score, risk_level, or model_version"
            )

        return {"status": "ok", "result": result}
    except Exception as exc:
        logger.exception("Landslide model prediction failed")
        return {"status": "error", "error": str(exc)}


async def _predict_candidate(latitude, longitude):
    def predict():
        from app.ml.landslide_predictor_v5_candidate import (
            predict_landslide_live,
        )

        return _predict_safely(
            predict_landslide_live, latitude, longitude
        )

    return await asyncio.to_thread(predict)


async def _predict_production(latitude, longitude):
    return await asyncio.to_thread(
        _predict_safely,
        predict_production,
        latitude,
        longitude,
    )


def _official_verification(district, sources):
    matched = []
    source_status = {}

    for source_name, source in sources.items():
        source_status[source_name] = source["status"]

        if source["status"] != "ok":
            continue

        for alert in source["alerts"]:
            matched_district = _alert_district(alert, source_name)

            if matched_district == district:
                matched.append({
                    "source": source_name,
                    "title": alert.get("title"),
                    "severity": alert.get("severity"),
                    "district": district,
                    "url": (
                        alert.get("official_url")
                        or alert.get("link")
                    ),
                })

    if matched:
        status = "verified"
    elif all(s["status"] == "ok" for s in sources.values()):
        status = "not_matched"
    else:
        status = "source_error"

    return {
        "status": status,
        "matched_alerts": matched,
        "sources": source_status,
    }


_run_lock = asyncio.Lock()


async def run_monitoring_cycle():
    # Prevent manual and scheduled runs from overlapping.
    if _run_lock.locked():
        return {
            "status": "already_running",
            "message": "A monitoring cycle is already in progress.",
        }

    async with _run_lock:
        started = _now()
        district_results = []
        overall_status = "complete"
        source_errors = []

        sources = await _fetch_official_sources()

        for name, source in sources.items():
            if source["status"] != "ok":
                source_errors.append({
                    "source": name,
                    "error": source["error"],
                })

        for district, (latitude, longitude) in DISTRICTS.items():
            production = await _predict_production(latitude, longitude)
            candidate = await _predict_candidate(latitude, longitude)

            official = _official_verification(district, sources)

            production_result = production.get("result")
            candidate_result = candidate.get("result")

            comparison = {
                "risk_levels_agree": None,
                "absolute_score_difference": None,
            }

            if production_result and candidate_result:
                try:
                    comparison["risk_levels_agree"] = (
                        str(production_result["risk_level"]).upper()
                        == str(candidate_result["risk_level"]).upper()
                    )
                    comparison["absolute_score_difference"] = round(
                        abs(
                            float(production_result["risk_score"])
                            - float(candidate_result["risk_score"])
                        ),
                        2,
                    )
                except (KeyError, TypeError, ValueError):
                    pass

            if production["status"] != "ok" or candidate["status"] != "ok":
                overall_status = "partial"

            district_results.append({
                "district": district,
                "coordinates": {
                    "latitude": latitude,
                    "longitude": longitude,
                },
                "production": production,
                "candidate_v5": candidate,
                "comparison": comparison,
                "official_verification": official,
            })

        if source_errors and overall_status == "complete":
            overall_status = "partial"

        finished = _now()

        payload = {
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "interval_seconds": INTERVAL_SECONDS,
            "district_count": len(DISTRICTS),
            "status": overall_status,
            "source_errors": source_errors,
            "results": district_results,
            "production_model_modified": False,
        }

        db = SessionLocal()
        try:
            row = MonitoringRun(
                started_at=started.replace(tzinfo=None),
                finished_at=finished.replace(tzinfo=None),
                status=overall_status,
                results_json=json.dumps(payload, default=str),
                error=None,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            payload["run_id"] = row.id
        except Exception:
            db.rollback()
            logger.exception("Could not save monitoring history")
            raise
        finally:
            db.close()

        return payload


def get_recent_runs(limit=10):
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(MonitoringRun)
            .order_by(MonitoringRun.id.desc())
            .limit(limit)
        ).all()

        return [
            {
                "run_id": row.id,
                "started_at": row.started_at.isoformat()
                if row.started_at else None,
                "finished_at": row.finished_at.isoformat()
                if row.finished_at else None,
                "status": row.status,
                "error": row.error,
                "results": json.loads(row.results_json),
            }
            for row in rows
        ]
    finally:
        db.close()
