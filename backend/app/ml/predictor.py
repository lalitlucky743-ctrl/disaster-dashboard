import os
import pickle
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests


# ============================================================
# PATHS / CONSTANTS
# ============================================================

BASE_DIR = os.path.dirname(__file__)

# IMPORTANT: V6.3 is the final trained model. Do NOT silently
# fall back to the old disaster_model.pkl.
MODEL_PATH = os.path.join(
    BASE_DIR,
    "disaster_model_v6_3.pkl",
)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
LOCAL_TIMEZONE = "Asia/Kolkata"

# Exact feature order stored in the V6.3 training package.
EXPECTED_FEATURES = [
    "temperature_2m_mean",
    "relative_humidity_2m_mean",
    "precipitation_sum",
    "rain_3day",
    "rain_7day",
    "rain_14day",
    "rain_30day",
    "rain_intensity_3day",
]

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
            f"V6.3 model not found: {MODEL_PATH}. "
            "Copy disaster_model_v6_3.pkl into app/ml/ first."
        )

    with open(MODEL_PATH, "rb") as file:
        package = pickle.load(file)

    if not isinstance(package, dict):
        raise RuntimeError("Invalid V6.3 model package: expected a dictionary.")

    if "model" not in package or "features" not in package:
        raise RuntimeError(
            "Invalid V6.3 model package: missing 'model' or 'features'."
        )

    features = list(package["features"])
    if features != EXPECTED_FEATURES:
        raise RuntimeError(
            "Incompatible model feature list.\n"
            f"Expected: {EXPECTED_FEATURES}\n"
            f"Loaded  : {features}"
        )

    version = str(package.get("version", ""))
    if not version.startswith("real-data-v6.3"):
        raise RuntimeError(
            f"Incompatible model version: {version!r}. "
            "Expected the V6.3 real-data model."
        )

    _model_package = package
    return _model_package


# ============================================================
# FETCH REAL LIVE WEATHER
# ============================================================

def fetch_live_weather(latitude, longitude):
    params = {
        "latitude": float(latitude),
        "longitude": float(longitude),
        "past_days": 35,
        "forecast_days": 1,

        # Current observations are for the dashboard/UI.
        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "precipitation,"
            "rain,"
            "weather_code"
        ),

        # Daily fields used for the ML features.
        # No daily max/min, rain_sum, or weather_code is needed by V6.3.
        "daily": (
            "temperature_2m_mean,"
            "relative_humidity_2m_mean,"
            "precipitation_sum"
        ),

        "timezone": LOCAL_TIMEZONE,
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
        raise RuntimeError("Open-Meteo daily weather data was not returned.")

    if "current" not in payload:
        raise RuntimeError("Open-Meteo current weather data was not returned.")

    return payload


# ============================================================
# BUILD COMPLETED DAILY DATA
# ============================================================

def build_daily_dataframe(payload):
    daily = payload.get("daily")
    if not daily:
        raise RuntimeError("Daily weather data is empty.")

    df = pd.DataFrame(daily)
    if df.empty:
        raise RuntimeError("Daily weather dataframe is empty.")

    required_columns = [
        "time",
        "temperature_2m_mean",
        "relative_humidity_2m_mean",
        "precipitation_sum",
    ]

    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise RuntimeError(
            "Open-Meteo missing required daily fields: " + ", ".join(missing)
        )

    df["date"] = (
        pd.to_datetime(df["time"], errors="coerce")
        .dt.normalize()
    )

    for column in required_columns[1:]:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    # Never convert missing values to zero or interpolate them.
    missing_real = [
        column
        for column in required_columns[1:]
        if df[column].isna().any()
    ]

    if missing_real:
        raise RuntimeError(
            "Open-Meteo contains unavailable real daily values in: "
            + ", ".join(missing_real)
            + ". Prediction stopped; no values were fabricated."
        )

    local_today = datetime.now(ZoneInfo(LOCAL_TIMEZONE)).date()

    # Only completed local-calendar daily observations may become
    # the ML feature row. Today is still in progress and is excluded.
    df = df[
        df["date"].dt.date < local_today
    ].copy()

    if df.empty:
        raise RuntimeError(
            "No completed daily weather observation is available for ML prediction."
        )

    df = (
        df.dropna(subset=["date"])
        .sort_values("date")
        .drop_duplicates(subset=["date"])
        .reset_index(drop=True)
    )

    if len(df) < 30:
        raise RuntimeError(
            f"Only {len(df)} completed daily observations are available; "
            "at least 30 are required for the V6.3 rain_30day feature."
        )

    # Strict continuity check. We do not silently bridge missing calendar days.
    expected_dates = pd.date_range(
        df["date"].min(),
        df["date"].max(),
        freq="D",
    )
    actual_dates = pd.DatetimeIndex(df["date"])

    if not actual_dates.equals(expected_dates):
        missing_dates = expected_dates.difference(actual_dates)
        preview = [stamp.date().isoformat() for stamp in missing_dates[:10]]
        raise RuntimeError(
            "Open-Meteo daily history contains missing calendar dates. "
            "Rainfall rolling features were not fabricated. Missing dates: "
            f"{preview}"
        )

    return df


# ============================================================
# ADD REAL RAINFALL FEATURES
# ============================================================

def add_rainfall_features(df):
    df = df.copy()

    rainfall = pd.to_numeric(
        df["precipitation_sum"],
        errors="coerce",
    )

    if rainfall.isna().any():
        raise RuntimeError(
            "Cannot calculate rainfall features because real precipitation data is missing."
        )

    df["rain_3day"] = rainfall.rolling(
        window=3,
        min_periods=3,
    ).sum()

    df["rain_7day"] = rainfall.rolling(
        window=7,
        min_periods=7,
    ).sum()

    df["rain_14day"] = rainfall.rolling(
        window=14,
        min_periods=14,
    ).sum()

    df["rain_30day"] = rainfall.rolling(
        window=30,
        min_periods=30,
    ).sum()

    df["rain_intensity_3day"] = rainfall.rolling(
        window=3,
        min_periods=3,
    ).mean()

    latest = df.iloc[-1]
    required_rolling = [
        "rain_3day",
        "rain_7day",
        "rain_14day",
        "rain_30day",
        "rain_intensity_3day",
    ]

    missing = [
        column
        for column in required_rolling
        if pd.isna(latest[column])
    ]

    if missing:
        raise RuntimeError(
            "Insufficient real historical weather data for: "
            + ", ".join(missing)
        )

    return df


# ============================================================
# CURRENT HOURLY WEATHER FOR DASHBOARD
# ============================================================

def get_current_hourly_weather(payload):
    current = payload.get("current")
    if not current:
        raise RuntimeError("Open-Meteo current weather data is empty.")

    def number(column):
        value = current.get(column)
        if value is None or pd.isna(value):
            return None
        return float(value)

    weather_code = current.get("weather_code")

    return {
        "temperature": number("temperature_2m"),
        "humidity": number("relative_humidity_2m"),
        "precipitation": number("precipitation"),
        "rain": number("rain"),
        "weather_code": (
            int(weather_code)
            if weather_code is not None and not pd.isna(weather_code)
            else None
        ),
        "time": current.get("time"),
    }


# ============================================================
# CREATE EXACT V6.3 MODEL INPUT
# ============================================================

def create_model_input(daily_df, features):
    if list(features) != EXPECTED_FEATURES:
        raise RuntimeError(
            "Saved model feature list is incompatible with this predictor."
        )

    latest = daily_df.iloc[-1]
    values = {}

    for feature in features:
        if feature not in daily_df.columns:
            raise RuntimeError(
                f"Model requires feature '{feature}', but it is not available."
            )

        value = latest[feature]
        if pd.isna(value):
            raise RuntimeError(
                f"Real value unavailable for model feature: {feature}."
            )

        values[feature] = float(value)

    X = pd.DataFrame([values], columns=features)
    return X


# ============================================================
# RESOLVE TRAINED HIGH CLASS
# ============================================================

def get_high_class(package):
    """
    Resolve the trained HIGH output class from the saved package.

    V6.3 training maps:
        LOW  -> 0
        HIGH -> 1

    Earlier versions in this project sometimes used dataset label 2
    before converting labels for RandomForest. The actual fitted model
    therefore uses its model-output classes, not the dataset labels.
    """

    model = package["model"]
    classes = [int(value) for value in getattr(model, "classes_", [])]

    if not classes:
        raise RuntimeError("Loaded model has no classes_.")

    mapping = package.get("model_output_classes", {})

    # Prefer explicit package metadata.
    if isinstance(mapping, dict):
        for key, label in mapping.items():
            if str(label).upper() == "HIGH":
                try:
                    candidate = int(key)
                except (TypeError, ValueError):
                    continue
                if candidate in classes:
                    return candidate

    # V6.3 fitted RandomForest convention.
    if 1 in classes and 0 in classes:
        return 1

    # Defensive compatibility with an older fitted model convention.
    if 2 in classes and 0 in classes:
        return 2

    raise RuntimeError(
        "Unable to identify the trained HIGH class from model.classes_="
        f"{classes}."
    )


# ============================================================
# RISK LEVEL FOR UI
# ============================================================

def probability_to_risk(probability):
    score = float(probability) * 100.0

    if score >= 80:
        return "CRITICAL"
    if score >= 60:
        return "HIGH"
    if score >= 30:
        return "MEDIUM"
    return "LOW"


# ============================================================
# NEW LIVE PREDICTION
# ============================================================

def predict_risk_live(latitude, longitude):
    package = load_model()
    model = package["model"]
    features = list(package["features"])

    # --------------------------------------------------------
    # REAL LIVE WEATHER
    # --------------------------------------------------------
    payload = fetch_live_weather(latitude, longitude)

    # --------------------------------------------------------
    # COMPLETED DAILY WEATHER ONLY
    # --------------------------------------------------------
    daily_df = build_daily_dataframe(payload)
    daily_df = add_rainfall_features(daily_df)

    # --------------------------------------------------------
    # EXACT 8-FEATURE V6.3 INPUT
    # --------------------------------------------------------
    X = create_model_input(daily_df, features)

    # --------------------------------------------------------
    # PROBABILITY
    # --------------------------------------------------------
    probabilities = model.predict_proba(X)[0]
    class_probabilities = dict(
        zip(model.classes_, probabilities)
    )

    high_class = get_high_class(package)
    high_probability = float(class_probabilities[high_class])

    # Use the threshold selected during validation instead of silently
    # reverting to RandomForest's default 0.50 decision boundary.
    threshold = float(package.get("threshold", 0.50))
    prediction = int(high_probability >= threshold)

    risk_score = round(high_probability * 100.0)
    risk_level = probability_to_risk(high_probability)

    # --------------------------------------------------------
    # CURRENT WEATHER FOR UI
    # --------------------------------------------------------
    current_weather = get_current_hourly_weather(payload)

    current_missing = [
        key
        for key in (
            "temperature",
            "humidity",
            "precipitation",
            "rain",
            "weather_code",
        )
        if current_weather.get(key) is None
    ]

    if current_missing:
        raise RuntimeError(
            "Open-Meteo current weather is missing real values: "
            + ", ".join(current_missing)
            + "."
        )

    latest = daily_df.iloc[-1]

    return {
        "data_policy": "real_data_only",
        "risk_level": risk_level,
        "risk_score": risk_score,
        "confidence": round(high_probability, 4),
        "prediction": prediction,
        "probabilities": {
            str(key): round(float(value), 4)
            for key, value in class_probabilities.items()
        },
        "weather": {
            "temperature": current_weather["temperature"],
            "humidity": current_weather["humidity"],
            "rain": current_weather["rain"],
            "precipitation": current_weather["precipitation"],
            "weather_code": current_weather["weather_code"],
            "daily_precipitation": round(
                float(latest["precipitation_sum"]),
                2,
            ),
            "rain_3day": round(float(latest["rain_3day"]), 2),
            "rain_7day": round(float(latest["rain_7day"]), 2),
            "rain_14day": round(float(latest["rain_14day"]), 2),
            "rain_30day": round(float(latest["rain_30day"]), 2),
            "rain_intensity_3day": round(
                float(latest["rain_intensity_3day"]),
                2,
            ),
        },
        "ml_features": {
            feature: round(float(latest[feature]), 4)
            for feature in features
        },
        "location": {
            "latitude": float(latitude),
            "longitude": float(longitude),
        },
        "source": "Open-Meteo live weather",
        "historical_training_source": "NASA POWER + India Flood Inventory",
        "completed_daily_data_only": True,
        "model_version": package.get("version", "unknown"),
        "decision_threshold": round(threshold, 4),
        "generated_at": datetime.now(ZoneInfo("UTC")).isoformat(),
    }


# ============================================================
# BACKWARD-COMPATIBLE FUNCTION
# ============================================================

def predict_risk(
    temperature,
    humidity,
    precipitation,
    rain=None,
    weather_code=None,
    temperature_max=None,
    temperature_min=None,
    rain_3day=None,
    rain_7day=None,
    rain_14day=None,
    rain_30day=None,
    rain_intensity_3day=None,
):
    """
    Compatibility wrapper for an existing endpoint.

    V6.3 does NOT use:
        rain
        weather_code
        temperature_max
        temperature_min

    It DOES require the five rolling rainfall features because these
    cannot be reconstructed honestly from one current-weather reading.
    """

    package = load_model()
    model = package["model"]
    features = list(package["features"])

    required = {
        "temperature": temperature,
        "humidity": humidity,
        "precipitation": precipitation,
        "rain_3day": rain_3day,
        "rain_7day": rain_7day,
        "rain_14day": rain_14day,
        "rain_30day": rain_30day,
        "rain_intensity_3day": rain_intensity_3day,
    }

    missing = [
        key
        for key, value in required.items()
        if value is None
    ]

    if missing:
        raise ValueError(
            "Real V6.3 ML input missing: "
            + ", ".join(missing)
            + ". Fetch completed daily weather history first; "
            "do not use fallback or fabricated rainfall values."
        )

    values = {
        "temperature_2m_mean": float(temperature),
        "relative_humidity_2m_mean": float(humidity),
        "precipitation_sum": float(precipitation),
        "rain_3day": float(rain_3day),
        "rain_7day": float(rain_7day),
        "rain_14day": float(rain_14day),
        "rain_30day": float(rain_30day),
        "rain_intensity_3day": float(rain_intensity_3day),
    }

    X = pd.DataFrame([values], columns=features)

    probabilities = model.predict_proba(X)[0]
    class_probabilities = dict(
        zip(model.classes_, probabilities)
    )

    high_class = get_high_class(package)
    high_probability = float(class_probabilities[high_class])
    threshold = float(package.get("threshold", 0.50))

    prediction = int(high_probability >= threshold)
    risk_score = round(high_probability * 100.0)
    risk_level = probability_to_risk(high_probability)

    return {
        "data_policy": "real_data_only",
        "risk_level": risk_level,
        "risk_score": risk_score,
        "confidence": round(high_probability, 4),
        "prediction": prediction,
        "probabilities": {
            str(key): round(float(value), 4)
            for key, value in class_probabilities.items()
        },
        "model_version": package.get("version", "unknown"),
        "decision_threshold": round(threshold, 4),
    }


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("V6.3 LIVE ALMORA WEATHER + FLOOD RISK TEST")
    print("=" * 70)

    result = predict_risk_live(
        latitude=29.5971,
        longitude=79.6591,
    )

    print("\nRisk Level:", result["risk_level"])
    print("Risk Score:", result["risk_score"])
    print("Flood Probability:", result["confidence"])
    print("Decision Threshold:", result["decision_threshold"])
    print("\nCurrent Weather:")
    print(result["weather"])
    print("\nML Features:")
    print(result["ml_features"])
    print("\nProbabilities:")
    print(result["probabilities"])
