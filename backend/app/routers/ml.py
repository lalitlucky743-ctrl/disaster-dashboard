from fastapi import APIRouter
from pydantic import BaseModel
from ..ml.predictor import predict_risk
router = APIRouter()


class RiskInput(BaseModel):
    rainfall: float
    temperature: float
    humidity: float
    river_level: float
    previous_incidents: int


@router.post("/predict-risk")
def predict_disaster_risk(data: RiskInput):

    result = predict_risk(
        rainfall=data.rainfall,
        temperature=data.temperature,
        humidity=data.humidity,
        river_level=data.river_level,
        previous_incidents=data.previous_incidents,
    )

    return result