from fastapi import APIRouter
from pydantic import BaseModel

from ..ml.predictor import predict_risk


router = APIRouter()


class RiskInput(BaseModel):
    temperature: float
    humidity: float
    precipitation: float
    rain: float
    weather_code: int


@router.post("/predict-risk")
def predict_disaster_risk(data: RiskInput):

    result = predict_risk(
        temperature=data.temperature,
        humidity=data.humidity,
        precipitation=data.precipitation,
        rain=data.rain,
        weather_code=data.weather_code,
    )

    return result