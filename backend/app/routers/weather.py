
import asyncio

from fastapi import APIRouter, HTTPException, Query

from ..ml.predictor import predict_risk
from ..services.weather.client import fetch_json, OpenMeteoUnavailable


router = APIRouter()

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def get_weather_description(weather_code: int) -> str:
    descriptions = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        56: "Light freezing drizzle",
        57: "Dense freezing drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        66: "Light freezing rain",
        67: "Heavy freezing rain",
        71: "Slight snowfall",
        73: "Moderate snowfall",
        75: "Heavy snowfall",
        77: "Snow grains",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        85: "Slight snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }

    return descriptions.get(
        weather_code,
        "Unknown weather condition"
    )


@router.get("")
async def get_weather(
    latitude: float = Query(
        ...,
        description="Latitude of the location"
    ),
    longitude: float = Query(
        ...,
        description="Longitude of the location"
    ),
):
    """
    Fetch weather using the shared Open-Meteo client
    and generate ML-based disaster risk.
    """

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "apparent_temperature,"
            "precipitation,"
            "rain,"
            "weather_code,"
            "wind_speed_10m,"
            "wind_direction_10m,"
            "surface_pressure"
        ),
        "hourly": (
            "temperature_2m,"
            "precipitation_probability,"
            "precipitation,"
            "rain,"
            "weather_code"
        ),
        "forecast_days": 1,
        "timezone": "auto",
    }

    # Fetch through shared cache/client.
    try:
        data, weather_metadata = await asyncio.to_thread(
            fetch_json,
            OPEN_METEO_URL,
            params,
        )

    except OpenMeteoUnavailable as error:
        raise HTTPException(
            status_code=503,
            detail=f"Weather service temporarily unavailable: {error}"
        )

    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Weather service error: {error}"
        )

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=502,
            detail="Weather provider returned an invalid response."
        )

    current = data.get("current")

    if not isinstance(current, dict):
        raise HTTPException(
            status_code=502,
            detail="Weather response does not contain current conditions."
        )

    # Extract current weather.
    temperature = current.get("temperature_2m")
    humidity = current.get("relative_humidity_2m")
    precipitation = current.get("precipitation")
    rain = current.get("rain")
    weather_code = current.get("weather_code")

    if any(
        value is None
        for value in (
            temperature,
            humidity,
            precipitation,
            rain,
            weather_code,
        )
    ):
        raise HTTPException(
            status_code=502,
            detail="Weather response is missing required current values."
        )

    try:
        risk_prediction = predict_risk(
            temperature=float(temperature),
            humidity=float(humidity),
            precipitation=float(precipitation),
            rain=float(rain),
            weather_code=int(weather_code),
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"ML prediction failed: {error}"
        )

    weather_source = weather_metadata.get("source", "live")

    return {
        "status": "success",

        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": data.get("timezone"),
        },

        "current": {
            "temperature": temperature,
            "temperature_unit": "°C",
            "feels_like": current.get("apparent_temperature"),
            "humidity": humidity,
            "precipitation": precipitation,
            "rain": rain,
            "wind_speed": current.get("wind_speed_10m"),
            "wind_direction": current.get("wind_direction_10m"),
            "pressure": current.get("surface_pressure"),
            "weather_code": weather_code,
            "condition": get_weather_description(int(weather_code)),
        },

        "disaster_risk": {
            "risk_level": risk_prediction["risk_level"],
            "risk_score": risk_prediction["risk_score"],
            "confidence": risk_prediction["confidence"],
            "model": "Random Forest",
            "source": f"Open-Meteo ({weather_source})",
        },

        "source": "Open-Meteo",
        "weather_data_status": weather_source,
    }
