
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..ml.predictor import predict_risk_live
from ..ml.landslide_predictor import predict_landslide_live

router = APIRouter()


class RiskInput(BaseModel):
    latitude: float
    longitude: float


@router.post("/predict-risk")
def predict_disaster_risk(data: RiskInput):

    try:
        result = predict_risk_live(
            latitude=data.latitude,
            longitude=data.longitude,
        )

        return result

    except Exception as e:
        print(f"❌ Live ML prediction failed: {e}")

        raise HTTPException(
            status_code=500,
            detail=f"Live ML prediction failed: {str(e)}"
        )

        # ============================================================
# FLOOD
# ============================================================

class RiskInput(BaseModel):
    latitude: float
    longitude: float


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
# LANDSLIDE
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
