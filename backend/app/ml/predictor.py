import os
import joblib
import numpy as np


MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "disaster_model.pkl",
)

model = joblib.load(MODEL_PATH)


def predict_risk(
    temperature: float,
    humidity: float,
    precipitation: float,
    rain: float,
    weather_code: int,
):

    features = np.array([[
        temperature,
        humidity,
        precipitation,
        rain,
        weather_code,
    ]])

    # ML model prediction
    prediction = model.predict(features)[0]

    # ML model probability
    probabilities = model.predict_proba(features)[0]

    confidence = float(max(probabilities))

    # Convert ML class into risk level
    if prediction == 2:
        risk_level = "HIGH"

    elif prediction == 1:
        risk_level = "MEDIUM"

    else:
        risk_level = "LOW"

    # Model confidence as risk score
    risk_score = round(confidence * 100)

    return {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "confidence": round(confidence, 2),
        "prediction": int(prediction),
    }