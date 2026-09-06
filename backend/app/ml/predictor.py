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
    "disaster_model.pkl"
)

OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast"
)


_model_package = None


# ============================================================
# MODEL LOADER
# ============================================================

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


# ============================================================
# FETCH REAL LIVE WEATHER
# ============================================================

def fetch_live_weather(
    latitude,
    longitude
):

    params = {

        "latitude": float(latitude),
        "longitude": float(longitude),

        # ----------------------------------------------------
        # Real recent weather history.
        # 35 days are required for 30-day rainfall.
        # ----------------------------------------------------

        "past_days": 35,

        "forecast_days": 1,

        # ----------------------------------------------------
        # HOURLY = current/live rainfall
        # ----------------------------------------------------

        "hourly": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "precipitation,"
            "rain,"
            "weather_code"
        ),

        # ----------------------------------------------------
        # DAILY = ML features
        # ----------------------------------------------------

        "daily": (
            "temperature_2m_mean,"
            "temperature_2m_max,"
            "temperature_2m_min,"
            "relative_humidity_2m_mean,"
            "precipitation_sum,"
            "rain_sum,"
            "weather_code"
        ),

        "timezone": "Asia/Kolkata",

        "temperature_unit": "celsius",

        "precipitation_unit": "mm",
    }

    response = requests.get(
        OPEN_METEO_URL,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    payload = response.json()

    if "daily" not in payload:
        raise RuntimeError(
            "Open-Meteo daily weather data "
            "was not returned."
        )

    if "hourly" not in payload:
        raise RuntimeError(
            "Open-Meteo hourly weather data "
            "was not returned."
        )

    return payload


# ============================================================
# BUILD DAILY DATA
# ============================================================

def build_daily_dataframe(
    payload
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
            "Daily weather dataframe is empty."
        )

    # --------------------------------------------------------
    # Date
    # --------------------------------------------------------

    df["date"] = (
        pd.to_datetime(
            df["time"],
            errors="coerce"
        )
        .dt.normalize()
    )

    # --------------------------------------------------------
    # Required model columns
    # --------------------------------------------------------

    required_columns = [

        "temperature_2m_mean",
        "temperature_2m_max",
        "temperature_2m_min",

        "relative_humidity_2m_mean",

        "precipitation_sum",
        "rain_sum",

        "weather_code",
    ]

    for column in required_columns:

        if column not in df.columns:

            raise RuntimeError(
                f"Open-Meteo missing required "
                f"field: {column}"
            )

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # DO NOT turn missing rainfall into zero.
    # --------------------------------------------------------

    if df[
        "precipitation_sum"
    ].isna().all():

        raise RuntimeError(
            "Real precipitation data is "
            "unavailable. Prediction stopped."
        )

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    df = (
        df
        .dropna(subset=["date"])
        .sort_values("date")
        .drop_duplicates(
            subset=["date"]
        )
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # Small API gaps can be interpolated.
    #
    # We NEVER create missing rainfall
    # from today's rainfall.
    # --------------------------------------------------------

    interpolation_columns = [

        "temperature_2m_mean",
        "temperature_2m_max",
        "temperature_2m_min",

        "relative_humidity_2m_mean",

        "precipitation_sum",
        "rain_sum",

        "weather_code",
    ]

    for column in interpolation_columns:

        df[column] = (
            df[column]
            .interpolate(
                limit=2,
                limit_direction="both"
            )
        )

    # --------------------------------------------------------
    # Verify data
    # --------------------------------------------------------

    for column in interpolation_columns:

        if df[column].isna().any():

            raise RuntimeError(
                f"Live weather contains "
                f"unavailable values in: {column}"
            )

    return df


# ============================================================
# ADD REAL RAINFALL FEATURES
# ============================================================

def add_rainfall_features(
    df
):

    df = df.copy()

    rainfall = pd.to_numeric(
        df[
            "precipitation_sum"
        ],
        errors="coerce"
    )

    if rainfall.isna().any():

        raise RuntimeError(
            "Cannot calculate rainfall "
            "features because real "
            "precipitation data is missing."
        )

    # --------------------------------------------------------
    # Actual rolling rainfall
    # --------------------------------------------------------

    df["rain_3day"] = (
        rainfall
        .rolling(
            window=3,
            min_periods=3
        )
        .sum()
    )

    df["rain_7day"] = (
        rainfall
        .rolling(
            window=7,
            min_periods=7
        )
        .sum()
    )

    df["rain_14day"] = (
        rainfall
        .rolling(
            window=14,
            min_periods=14
        )
        .sum()
    )

    df["rain_30day"] = (
        rainfall
        .rolling(
            window=30,
            min_periods=30
        )
        .sum()
    )

    df["rain_intensity_3day"] = (
        rainfall
        .rolling(
            window=3,
            min_periods=3
        )
        .mean()
    )

    # --------------------------------------------------------
    # 30 days are REQUIRED.
    #
    # If Open-Meteo doesn't provide enough real data,
    # STOP instead of inventing values.
    # --------------------------------------------------------

    latest = df.iloc[-1]

    required_rolling = [

        "rain_3day",
        "rain_7day",
        "rain_14day",
        "rain_30day",
        "rain_intensity_3day",
    ]

    for column in required_rolling:

        if pd.isna(
            latest[column]
        ):

            raise RuntimeError(
                f"Insufficient real historical "
                f"weather data for {column}."
            )

    return df


# ============================================================
# CURRENT HOURLY WEATHER
# ============================================================

def get_current_hourly_weather(
    payload
):

    hourly = payload.get(
        "hourly"
    )

    if not hourly:
        raise RuntimeError(
            "Hourly weather data is empty."
        )

    hourly_df = pd.DataFrame(
        hourly
    )

    if hourly_df.empty:
        raise RuntimeError(
            "Hourly weather dataframe is empty."
        )

    hourly_df["time"] = (
        pd.to_datetime(
            hourly_df["time"],
            errors="coerce"
        )
    )

    hourly_df = (
        hourly_df
        .dropna(subset=["time"])
        .sort_values("time")
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # Find latest available observation
    # --------------------------------------------------------

    latest = hourly_df.iloc[-1]

    def number(
        column
    ):

        value = latest.get(
            column
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

        "weather_code": (
            int(
                latest[
                    "weather_code"
                ]
            )
            if (
                "weather_code" in latest
                and not pd.isna(
                    latest[
                        "weather_code"
                    ]
                )
            )
            else None
        ),

        "time": (
            latest["time"]
            .isoformat()
        ),
    }


# ============================================================
# CREATE MODEL INPUT
# ============================================================

def create_model_input(
    daily_df,
    features
):

    latest = daily_df.iloc[-1]

    values = {}

    for feature in features:

        if feature not in daily_df.columns:

            raise RuntimeError(
                f"Model requires feature "
                f"'{feature}', but it is "
                f"not available."
            )

        value = latest[
            feature
        ]

        if pd.isna(value):

            raise RuntimeError(
                f"Real value unavailable "
                f"for model feature: {feature}"
            )

        values[
            feature
        ] = float(value)

    X = pd.DataFrame(
        [values]
    )

    # Exact model order
    X = X[
        features
    ]

    return X


# ============================================================
# RISK LEVEL FROM PROBABILITY
# ============================================================

def probability_to_risk(
    probability
):

    score = (
        float(probability)
        * 100
    )

    if score >= 80:
        return "CRITICAL"

    if score >= 60:
        return "HIGH"

    if score >= 30:
        return "MEDIUM"

    return "LOW"


# ============================================================
# NEW LIVE PREDICT FUNCTION
# ============================================================

def predict_risk_live(
    latitude,
    longitude
):

    package = load_model()

    model = package[
        "model"
    ]

    features = package[
        "features"
    ]

    # --------------------------------------------------------
    # Fetch REAL weather
    # --------------------------------------------------------

    payload = fetch_live_weather(
        latitude,
        longitude
    )

    # --------------------------------------------------------
    # Daily weather
    # --------------------------------------------------------

    daily_df = (
        build_daily_dataframe(
            payload
        )
    )

    # --------------------------------------------------------
    # Real rolling rainfall
    # --------------------------------------------------------

    daily_df = (
        add_rainfall_features(
            daily_df
        )
    )

    # --------------------------------------------------------
    # Exact ML input
    # --------------------------------------------------------

    X = create_model_input(
        daily_df,
        features
    )

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
            probabilities
        )
    )

    # --------------------------------------------------------
    # Probability of actual HIGH class
    # --------------------------------------------------------

    high_probability = 0.0

    if 2 in class_probabilities:

        high_probability = float(
            class_probabilities[2]
        )

    # --------------------------------------------------------
    # Risk score
    # --------------------------------------------------------

    risk_score = round(
        high_probability * 100
    )

    risk_level = (
        probability_to_risk(
            high_probability
        )
    )

    # --------------------------------------------------------
    # Current hourly weather
    # --------------------------------------------------------

    current_weather = (
        get_current_hourly_weather(
            payload
        )
    )

    # --------------------------------------------------------
    # Latest daily data
    # --------------------------------------------------------

    latest = daily_df.iloc[-1]

    # --------------------------------------------------------
    # Return
    # --------------------------------------------------------

    return {

        "risk_level": risk_level,

        "risk_score": risk_score,

        "confidence": round(
            high_probability,
            4
        ),

        "prediction": prediction,

        "probabilities": {

            str(key): round(
                float(value),
                4
            )

            for key, value
            in class_probabilities.items()
        },

        # ----------------------------------------------------
        # REAL CURRENT WEATHER
        # ----------------------------------------------------

        "weather": {

            "temperature": (
                current_weather[
                    "temperature"
                ]
            ),

            "humidity": (
                current_weather[
                    "humidity"
                ]
            ),

            "rain": (
                current_weather[
                    "rain"
                ]
            ),

            "precipitation": (
                current_weather[
                    "precipitation"
                ]
            ),

            "weather_code": (
                current_weather[
                    "weather_code"
                ]
            ),

            # ------------------------------------------------
            # REAL DAILY / ROLLING RAIN
            # ------------------------------------------------

            "daily_precipitation": round(
                float(
                    latest[
                        "precipitation_sum"
                    ]
                ),
                2
            ),

            "daily_rain": round(
                float(
                    latest[
                        "rain_sum"
                    ]
                ),
                2
            ),

            "rain_3day": round(
                float(
                    latest[
                        "rain_3day"
                    ]
                ),
                2
            ),

            "rain_7day": round(
                float(
                    latest[
                        "rain_7day"
                    ]
                ),
                2
            ),

            "rain_14day": round(
                float(
                    latest[
                        "rain_14day"
                    ]
                ),
                2
            ),

            "rain_30day": round(
                float(
                    latest[
                        "rain_30day"
                    ]
                ),
                2
            ),

            "rain_intensity_3day": round(
                float(
                    latest[
                        "rain_intensity_3day"
                    ]
                ),
                2
            ),

            "temperature_max": round(
                float(
                    latest[
                        "temperature_2m_max"
                    ]
                ),
                2
            ),

            "temperature_min": round(
                float(
                    latest[
                        "temperature_2m_min"
                    ]
                ),
                2
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
            "Open-Meteo live weather"
        ),

        "model_version": (
            package.get(
                "version",
                "unknown"
            )
        ),

        "generated_at": (
            datetime.utcnow()
            .isoformat()
            + "Z"
        ),
    }


# ============================================================
# BACKWARD-COMPATIBLE FUNCTION
# ============================================================

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

    """
    BACKWARD COMPATIBILITY

    Existing FastAPI code may already call:

        predict_risk(
            temperature,
            humidity,
            precipitation,
            rain,
            weather_code,
            ...
        )

    We keep that API working.

    IMPORTANT:
    This function does NOT invent missing rolling rainfall.

    If rolling rainfall is missing, it raises an error
    instead of silently using today's rainfall.
    """

    package = load_model()

    model = package[
        "model"
    ]

    features = package[
        "features"
    ]

    # --------------------------------------------------------
    # NO FAKE FALLBACKS
    # --------------------------------------------------------

    required_values = {

        "temperature": temperature,

        "humidity": humidity,

        "precipitation": precipitation,

        "rain": rain,

        "weather_code": weather_code,

        "temperature_max": temperature_max,

        "temperature_min": temperature_min,

        "rain_3day": rain_3day,

        "rain_7day": rain_7day,

        "rain_14day": rain_14day,

        "rain_30day": rain_30day,

        "rain_intensity_3day": (
            rain_intensity_3day
        ),
    }

    missing = [
        key
        for key, value
        in required_values.items()
        if value is None
    ]

    if missing:

        raise ValueError(
            "Real ML input missing: "
            + ", ".join(missing)
            + ". "
            "Do not use fake rainfall "
            "fallbacks. Fetch live weather "
            "history first."
        )

    # --------------------------------------------------------
    # Build exact feature dataframe
    # --------------------------------------------------------

    data = {

        "temperature_2m_mean": [
            float(temperature)
        ],

        "temperature_2m_max": [
            float(temperature_max)
        ],

        "temperature_2m_min": [
            float(temperature_min)
        ],

        "relative_humidity_2m_mean": [
            float(humidity)
        ],

        "precipitation_sum": [
            float(precipitation)
        ],

        "rain_sum": [
            float(rain)
        ],

        "weather_code": [
            float(weather_code)
        ],

        "rain_3day": [
            float(rain_3day)
        ],

        "rain_7day": [
            float(rain_7day)
        ],

        "rain_14day": [
            float(rain_14day)
        ],

        "rain_30day": [
            float(rain_30day)
        ],

        "rain_intensity_3day": [
            float(rain_intensity_3day)
        ],
    }

    X = pd.DataFrame(
        data
    )

    # Exact trained order
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
            probabilities
        )
    )

    # --------------------------------------------------------
    # HIGH probability
    # --------------------------------------------------------

    high_probability = 0.0

    if 2 in class_probabilities:

        high_probability = float(
            class_probabilities[2]
        )

    risk_score = round(
        high_probability * 100
    )

    risk_level = (
        probability_to_risk(
            high_probability
        )
    )

    # --------------------------------------------------------
    # Response
    # --------------------------------------------------------

    return {

        "risk_level": risk_level,

        "risk_score": risk_score,

        "confidence": round(
            high_probability,
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


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # ALMORA
    # --------------------------------------------------------

    print(
        "\n"
        + "=" * 65
    )

    print(
        "LIVE ALMORA WEATHER + FLOOD RISK"
    )

    print(
        "=" * 65
    )

    result = predict_risk_live(
        latitude=29.5971,
        longitude=79.6591
    )

    print(
        "\nRisk Level:",
        result["risk_level"]
    )

    print(
        "Risk Score:",
        result["risk_score"]
    )

    print(
        "Flood Probability:",
        result["confidence"]
    )

    print(
        "\nCurrent Weather:"
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