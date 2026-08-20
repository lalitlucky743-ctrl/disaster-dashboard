import httpx

from fastapi import APIRouter, HTTPException, Query

from ..ml.predictor import predict_risk


router = APIRouter()


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def get_weather_description(weather_code: int) -> str:
    """
    Convert Open-Meteo WMO weather code into readable text.
    """

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
    Fetch live weather data from Open-Meteo
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


    # -----------------------------------------
    # Fetch live weather
    # -----------------------------------------

    try:

        async with httpx.AsyncClient(
            timeout=10.0
        ) as client:

            response = await client.get(
                OPEN_METEO_URL,
                params=params,
            )

            response.raise_for_status()

            data = response.json()


    except httpx.TimeoutException:

        raise HTTPException(
            status_code=504,
            detail="Weather service timed out"
        )


    except httpx.HTTPError as error:

        raise HTTPException(
            status_code=502,
            detail=f"Weather service error: {str(error)}"
        )


    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch weather: {str(error)}"
        )


    current = data.get(
        "current",
        {}
    )


    # -----------------------------------------
    # Extract current weather
    # -----------------------------------------

    temperature = current.get(
        "temperature_2m",
        0
    )

    humidity = current.get(
        "relative_humidity_2m",
        0
    )

    precipitation = current.get(
        "precipitation",
        0
    )

    rain = current.get(
        "rain",
        0
    )

    weather_code = current.get(
        "weather_code",
        0
    )


    # -----------------------------------------
    # ML DISASTER RISK PREDICTION
    # -----------------------------------------

    try:

        risk_prediction = predict_risk(
            temperature=float(temperature or 0),
            humidity=float(humidity or 0),
            precipitation=float(
                precipitation or 0
            ),
            rain=float(rain or 0),
            weather_code=int(
                weather_code or 0
            ),
        )

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=f"ML prediction failed: {str(error)}"
        )


    # -----------------------------------------
    # Weather response + ML prediction
    # -----------------------------------------

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

            "feels_like": current.get(
                "apparent_temperature"
            ),

            "humidity": humidity,

            "precipitation": precipitation,

            "rain": rain,

            "wind_speed": current.get(
                "wind_speed_10m"
            ),

            "wind_direction": current.get(
                "wind_direction_10m"
            ),

            "pressure": current.get(
                "surface_pressure"
            ),

            "weather_code": weather_code,

            "condition": get_weather_description(
                weather_code
            ),
        },

        # -------------------------------------
        # ML Prediction
        # -------------------------------------

        "disaster_risk": {

            "risk_level": risk_prediction[
                "risk_level"
            ],

            "risk_score": risk_prediction[
                "risk_score"
            ],

            "confidence": risk_prediction[
                "confidence"
            ],

            "model": "Random Forest",

            "source": "Live Open-Meteo Weather Data",
        },

        "source": "Open-Meteo",
    }