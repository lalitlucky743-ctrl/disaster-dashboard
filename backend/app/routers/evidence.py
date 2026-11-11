
"""Read-only API for the latest official evidence report."""

from fastapi import APIRouter, HTTPException

from app.services.evidence.report_reader import (
    read_latest_evidence_report,
)

router = APIRouter()


@router.get("/latest")
def get_latest_evidence():
    try:
        return read_latest_evidence_report()

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="No evidence report is available yet.",
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail="The saved evidence report is currently unavailable.",
        ) from exc
