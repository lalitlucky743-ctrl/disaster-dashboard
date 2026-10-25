
from fastapi import APIRouter, HTTPException, Query

from app.services.monitoring.engine import (
    get_recent_runs,
    run_monitoring_cycle,
)
from app.services.monitoring.scheduler import monitoring_is_running

router = APIRouter(tags=["Automatic Monitoring"])


@router.get("/status")
def monitoring_status():
    history = get_recent_runs(limit=1)

    return {
        "scheduler_running": monitoring_is_running(),
        "interval_seconds": 300,
        "district_count": 13,
        "last_run": history[0] if history else None,
    }


@router.get("/history")
def monitoring_history(
    limit: int = Query(default=10, ge=1, le=100),
):
    return {
        "runs": get_recent_runs(limit=limit),
    }


@router.post("/run-once")
async def monitoring_run_once():
    try:
        return await run_monitoring_cycle()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Monitoring cycle failed: {exc}",
        ) from exc
