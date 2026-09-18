import os
import pickle
from datetime import datetime

import numpy as np
import pandas as pd
import requests


# ============================================================
# PATHS
# ============================================================

MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "landslide_model.pkl",
)

OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast"
)

_model_package = None


# ============================================================
# MODEL
# ============================================================

def load_model():

    global _model_package

    if _model_package is not None:
        return _model_package

    if not os.path.exists(
        MODEL_PATH
    ):
        raise FileNotFoundError(
            f"Landslide model not found: "
            f"{MODEL_PATH}"
        )

    with open(
        MODEL_PATH,
        "rb",
    ) as f:

        _model_package = pickle.load(f)

    return _model_package


# ============================================================
# LIVE WEATHER
# ============================================================

def fetch_live_weather(
    latitude,
    longitude,
):

    params = {

        "latitude": float(
            latitude
        ),

        "longitude": float(
            longitude
        ),

        # 30 days needed for rolling rainfall
        "past_days": 35,

        "forecast_days": 1,

        "hourly": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "precipitation,"
            "rain"
        ),

        "daily": (
            "temperature_2m_mean,"
            "relative_humidity_2m_mean,"
            "precipitation_sum,"
            "rain_sum"
        ),

        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "precipitation,"
            "rain"
        ),

        "timezone": "Asia/Kolkata",

        "temperature_unit": "celsius",

        "precipitation_unit": "mm",
    }

    response = requests.get(
        OPEN_METEO_URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    payload = response.json()

    if "daily" not in payload:
        raise RuntimeError(
            "Live daily weather data "
            "was not returned."
        )

    return payload


# ============================================================
# ELEVATION
# ============================================================

def fetch_elevation(
    latitude,
    longitude,
):

    params = {
        "latitude": float(
            latitude
        ),
        "longitude": float(
            longitude
        ),
        "current": "temperature_2m",
    }

    response = requests.get(
        OPEN_METEO_URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    payload = response.json()

    elevation = payload.get(
        "elevation"
    )

    if elevation is None:
        raise RuntimeError(
            "Live elevation unavailable."
        )

    return float(elevation)


# ============================================================
# DAILY DATA
# ============================================================

def build_daily_dataframe(
    payload,
):

    daily = payload.get(
        "daily"
    )

    if not daily:
        raise RuntimeError(
            "Daily weather data is empty."
        )

    df = pd.DataFrame(
        daily
    )

    if df.empty:
        raise RuntimeError(
            "Daily weather dataframe "
            "is empty."
        )

    df["date"] = pd.to_datetime(
        df["time"],
        errors="coerce",
    )

    columns = [
        "precipitation_sum",
        "rain_sum",
        "temperature_2m_mean",
        "relative_humidity_2m_mean",
    ]

    for column in columns:

        if column not in df.columns:
            raise RuntimeError(
                f"Missing live field: "
                f"{column}"
            )

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df = (
        df
        .dropna(subset=["date"])
        .sort_values("date")
        .drop_duplicates("date")
        .reset_index(drop=True)
    )

    if df[
        "rain_sum"
    ].isna().all():

        raise RuntimeError(
            "Real rainfall data unavailable."
        )

    # --------------------------------------------------------
    # Rolling rainfall
    # --------------------------------------------------------

    rainfall = df[
        "rain_sum"
    ]

    precipitation = df[
        "precipitation_sum"
    ]

    df["rain_1day"] = rainfall

    df["rain_3day"] = (
        rainfall
        .rolling(
            3,
            min_periods=3,
        )
        .sum()
    )

    df["rain_7day"] = (
        rainfall
        .rolling(
            7,
            min_periods=7,
        )
        .sum()
    )

    df["rain_14day"] = (
        rainfall
        .rolling(
            14,
            min_periods=14,
        )
        .sum()
    )

    df["rain_30day"] = (
        rainfall
        .rolling(
            30,
            min_periods=30,
        )
        .sum()
    )

    df["precipitation_3day"] = (
        precipitation
        .rolling(
            3,
            min_periods=3,
        )
        .sum()
    )

    df["precipitation_7day"] = (
        precipitation
        .rolling(
            7,
            min_periods=7,
        )
        .sum()
    )

    latest = df.iloc[-1]

    required = [
        "rain_3day",
        "rain_7day",
        "rain_14day",
        "rain_30day",
        "precipitation_3day",
        "precipitation_7day",
    ]

    for column in required:

        if pd.isna(
            latest[column]
        ):

            raise RuntimeError(
                "Insufficient real "
                f"historical rainfall for "
                f"{column}."
            )

    return df


# ============================================================
# CURRENT WEATHER
# ============================================================

def get_current_weather(
    payload,
):

    current = payload.get(
        "current"
    )

    if not current:
        raise RuntimeError(
            "Current weather unavailable."
        )

    def number(
        name,
    ):

        value = current.get(
            name
        )

        if value is None:
            return None

        if pd.isna(value):
            return None

        return float(value)

    return {
        "temperature": number(
            "temperature_2m"
        ),
        "humidity": number(
            "relative_humidity_2m"
        ),
        "precipitation": number(
            "precipitation"
        ),
        "rain": number(
            "rain"
        ),
        "time": current.get(
            "time"
        ),
    }


# ============================================================
# RISK LEVEL
# ============================================================

def probability_to_risk(
    probability,
):

    score = float(
        probability
    ) * 100.0

    if score >= 80:
        return "CRITICAL"

    if score >= 60:
        return "HIGH"

    if score >= 30:
        return "MEDIUM"

    return "LOW"


# ============================================================
# LIVE LANDSLIDE PREDICTION
# ============================================================

def predict_landslide_live(
    latitude,
    longitude,
):

    package = load_model()

    model = package[
        "model"
    ]

    features = package[
        "features"
    ]

    # --------------------------------------------------------
    # Live weather
    # --------------------------------------------------------

    payload = fetch_live_weather(
        latitude,
        longitude,
    )

    # --------------------------------------------------------
    # Historical rainfall features
    # --------------------------------------------------------

    daily_df = (
        build_daily_dataframe(
            payload
        )
    )

    latest = daily_df.iloc[-1]

    # --------------------------------------------------------
    # Elevation
    # --------------------------------------------------------

    elevation = fetch_elevation(
        latitude,
        longitude,
    )

    # --------------------------------------------------------
    # Exact ML input
    # --------------------------------------------------------

    values = {

        "latitude": float(
            latitude
        ),

        "longitude": float(
            longitude
        ),

        "elevation": float(
            elevation
        ),

        "rain_1day": float(
            latest["rain_1day"]
        ),

        "rain_3day": float(
            latest["rain_3day"]
        ),

        "rain_7day": float(
            latest["rain_7day"]
        ),

        "rain_14day": float(
            latest["rain_14day"]
        ),

        "rain_30day": float(
            latest["rain_30day"]
        ),

        "precipitation_3day": float(
            latest[
                "precipitation_3day"
            ]
        ),

        "precipitation_7day": float(
            latest[
                "precipitation_7day"
            ]
        ),

        "temperature": float(
            latest[
                "temperature_2m_mean"
            ]
        ),

        "humidity": float(
            latest[
                "relative_humidity_2m_mean"
            ]
        ),
    }

    X = pd.DataFrame(
        [values]
    )

    X = X[
        features
    ]

    # --------------------------------------------------------
    # Prediction
    # --------------------------------------------------------

    prediction = int(
        model.predict(X)[0]
    )

    probabilities = (
        model.predict_proba(X)[0]
    )

    class_probabilities = dict(
        zip(
            model.classes_,
            probabilities,
        )
    )

    landslide_probability = float(
        class_probabilities.get(
            1,
            0.0,
        )
    )

    risk_score = round(
        landslide_probability * 100
    )

    risk_level = (
        probability_to_risk(
            landslide_probability
        )
    )

    current = (
        get_current_weather(
            payload
        )
    )

    # --------------------------------------------------------
    # Response
    # --------------------------------------------------------

    return {

        "risk_level": risk_level,

        "risk_score": risk_score,

        "confidence": round(
            landslide_probability,
            4,
        ),

        "prediction": prediction,

        "probabilities": {
            str(key): round(
                float(value),
                4,
            )
            for key, value
            in class_probabilities.items()
        },

        "weather": {

            "temperature": (
                current["temperature"]
            ),

            "humidity": (
                current["humidity"]
            ),

            "rain": (
                current["rain"]
            ),

            "precipitation": (
                current["precipitation"]
            ),

            "rain_1day": round(
                float(
                    latest["rain_1day"]
                ),
                2,
            ),

            "rain_3day": round(
                float(
                    latest["rain_3day"]
                ),
                2,
            ),

            "rain_7day": round(
                float(
                    latest["rain_7day"]
                ),
                2,
            ),

            "rain_14day": round(
                float(
                    latest["rain_14day"]
                ),
                2,
            ),

            "rain_30day": round(
                float(
                    latest["rain_30day"]
                ),
                2,
            ),

            "precipitation_3day": round(
                float(
                    latest[
                        "precipitation_3day"
                    ]
                ),
                2,
            ),

            "precipitation_7day": round(
                float(
                    latest[
                        "precipitation_7day"
                    ]
                ),
                2,
            ),

            "elevation": round(
                elevation,
                2,
            ),
        },

        "location": {

            "latitude": float(
                latitude
            ),

            "longitude": float(
                longitude
            ),
        },

        "source": (
            "GSI landslide inventory "
            "+ Open-Meteo live weather"
        ),

        "model_version": (
            package.get(
                "version",
                "unknown",
            )
        ),

        "generated_at": (
            datetime.utcnow()
            .isoformat()
            + "Z"
        ),
    }


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":

    result = (
        predict_landslide_live(
            latitude=29.5971,
            longitude=79.6591,
        )
    )

    print("\n")
    print("=" * 60)
    print("LIVE LANDSLIDE RISK")
    print("=" * 60)

    print(
        "\nRisk:",
        result["risk_level"],
    )

    print(
        "Score:",
        result["risk_score"],
    )

    print(
        "Confidence:",
        result["confidence"],
    )

    print(
        "\nWeather:"
    )

    print(
        result["weather"]
    )

    print(
        "\nProbabilities:"
    )

    print(
        result["probabilities"]
    )