from fastapi import APIRouter, Depends

from ..dependencies import get_current_user
from ..models import User


router = APIRouter()


# =========================================================
# DASHBOARD OVERVIEW
# =========================================================

@router.get("/overview")
def get_overview(
    current_user: User = Depends(get_current_user),
):
    return {
        "system_status": "operational",

        "active_threats": 4,

        "monitored_locations": 12,

        "critical_alerts": 2,

        "weather_risk": "Moderate",

        "overall_risk": "Moderate",

        "last_updated": "Live",

        "statistics": {
            "active_incidents": 4,
            "safe_zones": 18,
            "monitored_districts": 13,
            "response_units": 27,
        },

        "risk_breakdown": {
            "earthquake": "Low",
            "flood": "Moderate",
            "landslide": "High",
            "weather": "Moderate",
        },
    }


# =========================================================
# ACTIVE ALERTS
# =========================================================

@router.get("/alerts")
def get_alerts(
    current_user: User = Depends(get_current_user),
):
    return {
        "alerts": [
            {
                "id": 1,
                "type": "LANDSLIDE",
                "severity": "HIGH",
                "location": "Almora",
                "district": "Almora",
                "message": "Elevated landslide risk detected in hilly terrain.",
                "status": "ACTIVE",
                "timestamp": "Just now",
            },
            {
                "id": 2,
                "type": "HEAVY RAIN",
                "severity": "MEDIUM",
                "location": "Ranikhet",
                "district": "Almora",
                "message": "Heavy rainfall conditions expected.",
                "status": "ACTIVE",
                "timestamp": "8 min ago",
            },
            {
                "id": 3,
                "type": "FLOOD",
                "severity": "HIGH",
                "location": "Haldwani",
                "district": "Nainital",
                "message": "Water level monitoring indicates elevated flood risk.",
                "status": "ACTIVE",
                "timestamp": "14 min ago",
            },
            {
                "id": 4,
                "type": "EARTHQUAKE",
                "severity": "LOW",
                "location": "Pithoragarh",
                "district": "Pithoragarh",
                "message": "Minor seismic activity detected.",
                "status": "MONITORING",
                "timestamp": "22 min ago",
            },
        ],

        "total": 4,
    }


# =========================================================
# DISTRICTS
# =========================================================

@router.get("/districts")
def get_districts(
    current_user: User = Depends(get_current_user),
):
    return {
        "districts": [
            {
                "id": 1,
                "name": "Almora",
                "risk": "HIGH",
                "score": 78,
                "active_alerts": 2,
                "status": "Monitoring",
            },
            {
                "id": 2,
                "name": "Nainital",
                "risk": "MODERATE",
                "score": 61,
                "active_alerts": 1,
                "status": "Monitoring",
            },
            {
                "id": 3,
                "name": "Pithoragarh",
                "risk": "LOW",
                "score": 34,
                "active_alerts": 1,
                "status": "Stable",
            },
            {
                "id": 4,
                "name": "Bageshwar",
                "risk": "MODERATE",
                "score": 55,
                "active_alerts": 0,
                "status": "Stable",
            },
            {
                "id": 5,
                "name": "Chamoli",
                "risk": "HIGH",
                "score": 74,
                "active_alerts": 2,
                "status": "Monitoring",
            },
            {
                "id": 6,
                "name": "Rudraprayag",
                "risk": "HIGH",
                "score": 81,
                "active_alerts": 3,
                "status": "Monitoring",
            },
            {
                "id": 7,
                "name": "Uttarkashi",
                "risk": "MODERATE",
                "score": 58,
                "active_alerts": 1,
                "status": "Monitoring",
            },
            {
                "id": 8,
                "name": "Dehradun",
                "risk": "LOW",
                "score": 29,
                "active_alerts": 0,
                "status": "Stable",
            },
            {
                "id": 9,
                "name": "Haridwar",
                "risk": "MODERATE",
                "score": 49,
                "active_alerts": 1,
                "status": "Monitoring",
            },
            {
                "id": 10,
                "name": "Tehri Garhwal",
                "risk": "HIGH",
                "score": 72,
                "active_alerts": 2,
                "status": "Monitoring",
            },
            {
                "id": 11,
                "name": "Pauri Garhwal",
                "risk": "MODERATE",
                "score": 53,
                "active_alerts": 1,
                "status": "Monitoring",
            },
            {
                "id": 12,
                "name": "Champawat",
                "risk": "LOW",
                "score": 31,
                "active_alerts": 0,
                "status": "Stable",
            },
            {
                "id": 13,
                "name": "Udham Singh Nagar",
                "risk": "MODERATE",
                "score": 47,
                "active_alerts": 1,
                "status": "Monitoring",
            },
        ],

        "total": 13,
    }


# =========================================================
# SYSTEM STATUS
# =========================================================

@router.get("/system-status")
def get_system_status(
    current_user: User = Depends(get_current_user),
):
    return {
        "status": "operational",
        "api": "online",
        "database": "connected",
        "monitoring": "active",
        "ai_engine": "ready",
        "last_sync": "Live",
    }