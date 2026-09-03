
import os
import pickle
import pandas as pd


MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "disaster_model.pkl"
)


_model_package = None


def load_model():

    global _model_package

    if _model_package is not None:
        return _model_package

    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"Model not found: {MODEL_PATH}"
        )

    with open(
        MODEL_PATH,
        "rb"
    ) as f:

        _model_package = pickle.load(f)

    return _model_package


def predict_risk(
    temperature,
    humidity,
    precipitation,
    rain,
    weather_code,
    temperature_max=None,
    temperature_min=None,
    rain_3day=None,
    rain_7day=None,
    rain_14day=None,
    rain_30day=None,
    rain_intensity_3day=None,
):

    package = load_model()

    model = package["model"]
    features = package["features"]

    # --------------------------------------------------------
    # If optional values aren't available, use reasonable
    # current-day fallbacks.
    # --------------------------------------------------------

    if temperature_max is None:
        temperature_max = temperature

    if temperature_min is None:
        temperature_min = temperature

    if rain_3day is None:
        rain_3day = precipitation

    if rain_7day is None:
        rain_7day = precipitation

    if rain_14day is None:
        rain_14day = precipitation

    if rain_30day is None:
        rain_30day = precipitation

    if rain_intensity_3day is None:
        rain_intensity_3day = precipitation / 3

    data = {
        "temperature_2m_mean": [temperature],
        "temperature_2m_max": [temperature_max],
        "temperature_2m_min": [temperature_min],
        "relative_humidity_2m_mean": [humidity],
        "precipitation_sum": [precipitation],
        "rain_sum": [rain],
        "weather_code": [weather_code],
        "rain_3day": [rain_3day],
        "rain_7day": [rain_7day],
        "rain_14day": [rain_14day],
        "rain_30day": [rain_30day],
        "rain_intensity_3day": [
            rain_intensity_3day
        ],
    }

    X = pd.DataFrame(data)

    X = X[features]

    prediction = int(
        model.predict(X)[0]
    )

    probabilities = model.predict_proba(X)[0]

    class_probabilities = dict(
        zip(
            model.classes_,
            probabilities
        )
    )

    confidence = float(
        max(probabilities)
    )

    if prediction == 2:
        risk_level = "HIGH"
    else:
        risk_level = "LOW"

    risk_score = round(
        confidence * 100
    )

    return {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "confidence": round(
            confidence,
            4
        ),
        "prediction": prediction,
        "probabilities": {
            str(k): round(
                float(v),
                4
            )
            for k, v
            in class_probabilities.items()
        },
    }
