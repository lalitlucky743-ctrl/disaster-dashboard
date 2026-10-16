from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..ml.predictor import predict_risk_live
from ..ml.data.landslide.landslide_predictor import predict_landslide_live


router = APIRouter()


# ============================================================
# INPUT
# ============================================================

class RiskInput(BaseModel):
    latitude: float
    longitude: float


# ============================================================
# FLOOD ML — EXISTING PRODUCTION ROUTE (UNCHANGED)
# ============================================================

@router.post("/predict-risk")
def predict_disaster_risk(data: RiskInput):
    try:
        result = predict_risk_live(
            latitude=data.latitude,
            longitude=data.longitude,
        )
        return result
    except Exception as e:
        print(f"❌ Flood ML failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Flood ML failed: {str(e)}",
        )


# ============================================================
# LANDSLIDE ML — EXISTING PRODUCTION ROUTE (UNCHANGED)
# ============================================================

@router.post("/predict-landslide")
def predict_landslide_risk(data: RiskInput):
    try:
        result = predict_landslide_live(
            latitude=data.latitude,
            longitude=data.longitude,
        )
        return result
    except Exception as e:
        print(f"❌ Landslide ML failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Landslide ML failed: {str(e)}",
        )


# ============================================================
# LANDSLIDE V5 — CANDIDATE-ONLY TEST ROUTE
# Production predictor/model are NOT replaced.
# ============================================================

@router.post("/predict-landslide-v5-candidate")
def predict_landslide_v5_candidate(data: RiskInput):
    try:
        # Lazy import: a missing candidate file/dependency must not prevent
        # the API from starting or break the existing production routes.
        from ..ml.landslide_predictor_v5_candidate import (
            predict_landslide_live as predict_landslide_v5_live,
        )

        result = predict_landslide_v5_live(
            latitude=data.latitude,
            longitude=data.longitude,
        )

        model_version = str(result.get("model_version", ""))
        expected_prefix = "landslide-real-gis-v3.3-candidate-v5-extra-trees-no_coords14"
        if not model_version.startswith(expected_prefix):
            raise RuntimeError(
                "Candidate endpoint returned an unexpected model version: "
                f"{model_version or '<missing>'}"
            )

        result["endpoint_mode"] = "candidate_only"
        result["production_model_modified"] = False
        result["note"] = (
            "Experimental V5 candidate result. The score is a model-estimated "
            "susceptibility score, not a calibrated real-world landslide probability. "
            "This endpoint does not replace the production landslide model."
        )
        return result

    except Exception as e:
        print(f"❌ Landslide V5 candidate test failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Landslide V5 candidate test failed: {str(e)}",
        )
