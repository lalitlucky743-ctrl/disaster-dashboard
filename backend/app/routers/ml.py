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
# FLOOD ML
# ============================================================

@router.post("/predict-risk")
def predict_disaster_risk(
    data: RiskInput,
):

    try:

        result = predict_risk_live(
            latitude=data.latitude,
            longitude=data.longitude,
        )

        return result

    except Exception as e:

        print(
            f"❌ Flood ML failed: {e}"
        )

        raise HTTPException(
            status_code=500,
            detail=(
                f"Flood ML failed: {str(e)}"
            ),
        )


# ============================================================
# LANDSLIDE ML
# ============================================================

@router.post("/predict-landslide")
def predict_landslide_risk(
    data: RiskInput,
):

    try:

        result = predict_landslide_live(
            latitude=data.latitude,
            longitude=data.longitude,
        )

        return result

    except Exception as e:

        print(
            f"❌ Landslide ML failed: {e}"
        )

        raise HTTPException(
            status_code=500,
            detail=(
                f"Landslide ML failed: {str(e)}"
            ),
        )