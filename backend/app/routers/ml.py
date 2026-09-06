
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..ml.predictor import predict_risk_live


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
