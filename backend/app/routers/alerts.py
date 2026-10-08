from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.services.alerts.imd import fetch_imd_district_warnings
from app.services.alerts.sachet import fetch_sachet_alerts


router = APIRouter(prefix="", tags=["Official Alerts"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("")
async def get_official_alerts():
    alerts: list = []
    source_errors: list[dict] = []
    sources: dict[str, dict] = {}

    # ======================================================
    # IMD
    # ======================================================
    try:
        imd_alerts = await fetch_imd_district_warnings()

        if isinstance(imd_alerts, list):
            alerts.extend(imd_alerts)
            sources["IMD"] = {
                "status": "ok",
                "count": len(imd_alerts),
                "fetched_at": _now_iso(),
            }
        else:
            source_errors.append({
                "source": "IMD",
                "error": f"Unexpected IMD response type: {type(imd_alerts).__name__}",
            })
            sources["IMD"] = {
                "status": "error",
                "count": 0,
                "fetched_at": _now_iso(),
            }

    except Exception as exc:
        source_errors.append({"source": "IMD", "error": str(exc)})
        sources["IMD"] = {
            "status": "error",
            "count": 0,
            "fetched_at": _now_iso(),
        }

    # ======================================================
    # SACHET / NDMA
    # ======================================================
    try:
        sachet_result = await fetch_sachet_alerts()

        if isinstance(sachet_result, dict):
            sachet_alerts = sachet_result.get("alerts")
            raw_status = sachet_result.get("status")

            if raw_status == "error":
                sachet_status = "error"
                source_errors.append({
                    "source": "SACHET",
                    "error": sachet_result.get("message", "Unknown SACHET error"),
                })
            elif raw_status in ("updated", "not_modified"):
                sachet_status = "ok"
            else:
                sachet_status = "unknown"  # don't assume ok

            if not isinstance(sachet_alerts, list):
                sachet_alerts = []
                sachet_status = "error"
                source_errors.append({
                    "source": "SACHET",
                    "error": "Missing or invalid 'alerts' field in response",
                })

            alerts.extend(sachet_alerts)
            sources["SACHET"] = {
                "status": sachet_status,
                "count": len(sachet_alerts),
                "fetched_at": _now_iso(),
                "last_fetched": sachet_result.get("last_fetched"),
                "last_checked": sachet_result.get("last_checked"),
            }
        else:
            source_errors.append({
                "source": "SACHET",
                "error": f"Unexpected SACHET response type: {type(sachet_result).__name__}",
            })
            sources["SACHET"] = {
                "status": "error",
                "count": 0,
                "fetched_at": _now_iso(),
            }

    except Exception as exc:
        source_errors.append({"source": "SACHET", "error": str(exc)})
        sources["SACHET"] = {
            "status": "error",
            "count": 0,
            "fetched_at": _now_iso(),
        }

    # ======================================================
    # RESPONSE
    # ======================================================
    return {
        "alerts": alerts,
        "total_alerts": len(alerts),
        "last_updated": _now_iso(),
        "sources": sources,
        "source_errors": source_errors,
    }