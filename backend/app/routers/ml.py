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

# ============================================================
# LANDSLIDE MODEL COMPARISON — LOCAL TESTING
# Existing production and candidate endpoints remain unchanged.
# ============================================================

def _run_landslide_model_safely(model_function, latitude, longitude):
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
                "Model result is missing risk_score, risk_level, "
                "or model_version"
            )

        return {
            "status": "ok",
            "result": result,
        }

    except Exception as exc:
        print(f"❌ Model comparison prediction failed: {exc}")
        return {
            "status": "error",
            "error": str(exc),
        }


@router.post("/compare-landslide-models")
def compare_landslide_models(data: RiskInput):
    """
    Compare the existing production model with experimental V5.
    This endpoint does not replace either model.
    """

    production = _run_landslide_model_safely(
        predict_landslide_live,
        data.latitude,
        data.longitude,
    )

    # Lazy import keeps candidate-only dependencies isolated.
    try:
        from ..ml.landslide_predictor_v5_candidate import (
            predict_landslide_live as predict_v5_live,
        )

        candidate = _run_landslide_model_safely(
            predict_v5_live,
            data.latitude,
            data.longitude,
        )

        if candidate["status"] == "ok":
            version = str(
                candidate["result"].get("model_version", "")
            )

            expected_prefix = (
                "landslide-real-gis-v3.3-candidate-v5-extra-trees-no_coords14"
            )

            if not version.startswith(expected_prefix):
                candidate = {
                    "status": "error",
                    "error": (
                        "Unexpected candidate model version: "
                        f"{version or '<missing>'}"
                    ),
                }

    except Exception as exc:
        candidate = {
            "status": "error",
            "error": str(exc),
        }

    production_result = production.get("result")
    candidate_result = candidate.get("result")

    score_difference = None
    risk_levels_agree = None

    if production_result and candidate_result:
        try:
            production_score = float(
                production_result["risk_score"]
            )
            candidate_score = float(
                candidate_result["risk_score"]
            )

            score_difference = round(
                abs(production_score - candidate_score), 2
            )

            risk_levels_agree = (
                str(production_result["risk_level"]).upper()
                == str(candidate_result["risk_level"]).upper()
            )
        except (TypeError, ValueError, KeyError):
            pass

    if production_result and candidate_result:
        comparison_status = "complete"
    elif production_result or candidate_result:
        comparison_status = "partial"
    else:
        comparison_status = "failed"

    return {
        "comparison_status": comparison_status,
        "location": {
            "latitude": data.latitude,
            "longitude": data.longitude,
        },
        "production": production,
        "candidate_v5": candidate,
        "comparison": {
            "risk_levels_agree": risk_levels_agree,
            "absolute_score_difference": score_difference,
            "score_interpretation": (
                "Absolute difference between model-estimated scores; "
                "not a difference in calibrated real-world probabilities."
            ),
        },
        "official_verification": {
            "status": "not_run",
            "message": (
                "Official warning verification will be implemented "
                "as a separate step."
            ),
        },
        "production_model_modified": False,
    }
