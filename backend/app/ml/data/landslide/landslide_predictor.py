import os
import pickle
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

# Rasterio is optional at runtime. Render containers may not provide the
# native GEOS/PROJ/expat libraries required by the rasterio wheel.
# When rasterio is unavailable, the predictor uses the real Copernicus
# GLO-90 elevation fallback through Open-Meteo instead of failing startup.
try:
    import rasterio
    from rasterio.windows import Window
except (ImportError, OSError):
    rasterio = None
    Window = None


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_PATH = os.path.join(BASE_DIR, "landslide_model.pkl")

DEM_PATH = os.path.join(
    BASE_DIR,
    "dem",
    "uttarakhand_landslide_dem_1arcsec_merged.tif",
)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
LOCAL_TIMEZONE = "Asia/Kolkata"

# Keep the search local and real. We never invent an elevation value.
DEM_CENTER_SEARCH_RADII = (15, 50, 100, 250, 500, 1000)
TERRAIN_WINDOW = 11
TERRAIN_RADIUS = TERRAIN_WINDOW // 2

EXPECTED_FEATURES = [
    "latitude",
    "longitude",
    "elevation",
    "slope_deg",
    "aspect_sin",
    "aspect_cos",
    "curvature",
    "terrain_roughness",
    "tpi",
    "rain_1day",
    "rain_3day",
    "rain_7day",
    "rain_14day",
    "rain_30day",
    "precipitation_3day",
    "precipitation_7day",
    "temperature",
    "humidity",
]

OFFICIAL_MODEL_VERSION_PREFIX = "landslide-real-gis-v3"

_model_package = None
_ELEVATION_TERRAIN_CACHE = {}


# ============================================================
# MODEL
# ============================================================

def load_model():
    global _model_package

    if _model_package is not None:
        return _model_package

    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"Landslide model not found: {MODEL_PATH}"
        )

    with open(MODEL_PATH, "rb") as file:
        package = pickle.load(file)

    if not isinstance(package, dict):
        raise RuntimeError(
            "Invalid landslide model package: expected a dictionary."
        )

    if "model" not in package or "features" not in package:
        raise RuntimeError(
            "Invalid landslide model package: missing 'model' or 'features'."
        )

    features = list(package["features"])
    if features != EXPECTED_FEATURES:
        raise RuntimeError(
            "Landslide model feature mismatch.\n"
            f"Expected: {EXPECTED_FEATURES}\n"
            f"Loaded  : {features}"
        )

    version = str(package.get("version", ""))
    if not version.startswith(OFFICIAL_MODEL_VERSION_PREFIX):
        raise RuntimeError(
            f"Unexpected landslide model version: {version!r}"
        )

    model = package["model"]
    classes = list(getattr(model, "classes_", []))
    if 1 not in classes:
        raise RuntimeError(
            f"Landslide class 1 is missing from the trained model. Classes: {classes}"
        )

    _model_package = package
    return package


# ============================================================
# DEM
# ============================================================

def load_dem():
    if rasterio is None:
        raise RuntimeError(
            "Rasterio is unavailable in this runtime; using the real "
            "Copernicus GLO-90 elevation fallback instead."
        )

    if not os.path.exists(DEM_PATH):
        raise FileNotFoundError(
            "Landslide DEM not found: "
            f"{DEM_PATH}"
        )

    return rasterio.open(DEM_PATH)


def _is_valid_elevation(value, nodata):
    if value is None or not np.isfinite(value):
        return False
    if nodata is not None and np.isclose(value, nodata):
        return False
    return True


def _window_has_required_neighbors(array, center_row, center_col):
    h, w = array.shape
    if not (
        1 <= center_row < h - 1
        and 1 <= center_col < w - 1
    ):
        return False

    neighbors = [
        array[center_row, center_col],
        array[center_row, center_col - 1],
        array[center_row, center_col + 1],
        array[center_row - 1, center_col],
        array[center_row + 1, center_col],
    ]
    return all(np.isfinite(value) for value in neighbors)


def _find_real_dem_center(dem, row, col):
    """
    Find the nearest DEM pixel whose center and four immediate
    neighbours are all real/finite.

    The supplied 1-arcsec DEM can contain NoData holes. Search
    progressively through larger windows without ever inventing
    elevation values.
    """
    nodata = dem.nodata

    for radius in DEM_CENTER_SEARCH_RADII:
        row_start = max(0, row - radius)
        row_stop = min(dem.height, row + radius + 1)
        col_start = max(0, col - radius)
        col_stop = min(dem.width, col + radius + 1)

        if row_start >= row_stop or col_start >= col_stop:
            continue

        arr = dem.read(
            1,
            window=Window(
                col_start,
                row_start,
                col_stop - col_start,
                row_stop - row_start,
            ),
        ).astype(np.float64)

        if nodata is not None:
            arr[np.isclose(arr, nodata)] = np.nan

        finite = np.isfinite(arr)
        if arr.shape[0] < 3 or arr.shape[1] < 3:
            continue

        usable = np.zeros_like(finite, dtype=bool)
        usable[1:-1, 1:-1] = (
            finite[1:-1, 1:-1]
            & finite[:-2, 1:-1]
            & finite[2:, 1:-1]
            & finite[1:-1, :-2]
            & finite[1:-1, 2:]
        )

        candidates = np.argwhere(usable)
        if candidates.size == 0:
            continue

        absolute_rows = candidates[:, 0] + row_start
        absolute_cols = candidates[:, 1] + col_start
        distance_sq = (
            (absolute_rows - row).astype(np.int64) ** 2
            + (absolute_cols - col).astype(np.int64) ** 2
        )

        best = int(np.argmin(distance_sq))
        return int(absolute_rows[best]), int(absolute_cols[best])

    return None


def _terrain_from_grid(elevations, dx, dy, center_index, source_name, sampled_latitude, sampled_longitude):
    """Build terrain features from a real elevation grid."""
    elevation = np.asarray(elevations, dtype=np.float64)
    center = center_index

    if elevation.ndim != 2 or elevation.shape[0] < 3 or elevation.shape[1] < 3:
        raise RuntimeError("Terrain grid is too small for derivatives.")

    center_elevation = elevation[center, center]
    z_left = elevation[center, center - 1]
    z_right = elevation[center, center + 1]
    z_up = elevation[center - 1, center]
    z_down = elevation[center + 1, center]

    required = [center_elevation, z_left, z_right, z_up, z_down]
    if not all(np.isfinite(value) for value in required):
        raise RuntimeError("Real elevation neighbours are unavailable for terrain derivatives.")

    if dx <= 0 or dy <= 0:
        raise RuntimeError("Invalid terrain grid resolution.")

    dzdx = (z_right - z_left) / (2.0 * dx)
    dzdy = (z_down - z_up) / (2.0 * dy)

    slope_rad = np.arctan(np.sqrt(dzdx ** 2 + dzdy ** 2))
    slope_deg = float(np.degrees(slope_rad))

    aspect_rad = np.arctan2(dzdy, -dzdx)
    aspect_sin = float(np.sin(aspect_rad))
    aspect_cos = float(np.cos(aspect_rad))

    zxx = (z_right - 2.0 * center_elevation + z_left) / (dx ** 2)
    zyy = (z_down - 2.0 * center_elevation + z_up) / (dy ** 2)
    curvature = float(zxx + zyy)

    valid_values = elevation[np.isfinite(elevation)]
    if valid_values.size == 0:
        raise RuntimeError("No real elevation values are available in terrain grid.")

    terrain_roughness = float(np.std(valid_values))
    tpi = float(center_elevation - np.mean(valid_values))

    values = {
        "elevation": float(center_elevation),
        "slope_deg": slope_deg,
        "aspect_sin": aspect_sin,
        "aspect_cos": aspect_cos,
        "curvature": curvature,
        "terrain_roughness": terrain_roughness,
        "tpi": tpi,
    }

    for name, value in values.items():
        if not np.isfinite(value):
            raise RuntimeError(f"Invalid terrain feature: {name}={value}")

    return {
        **values,
        "dem_sampling": {
            "requested_latitude": float(sampled_latitude),
            "requested_longitude": float(sampled_longitude),
            "sampled_latitude": float(sampled_latitude),
            "sampled_longitude": float(sampled_longitude),
            "used_nearest_valid_pixel": False,
            "sampling_distance_meters": 0.0,
            "terrain_source": source_name,
        },
    }


def _fetch_copernicus_glo90_terrain(latitude, longitude):
    """
    Real-data fallback for DEM NoData holes.

    Open-Meteo's Elevation API provides point elevations from the
    Copernicus DEM GLO-90. We request a 5x5 real-elevation grid so that
    slope/aspect/curvature/roughness/TPI can still be derived without
    inventing an elevation value. The result is cached per location.
    """
    latitude = float(latitude)
    longitude = float(longitude)

    # Keep fallback terrain stable for repeated dashboard polling.
    cache_key = (round(latitude, 5), round(longitude, 5))
    cached = _ELEVATION_TERRAIN_CACHE.get(cache_key)
    if cached is not None:
        return cached.copy()

    grid_radius = 2
    grid_size = 2 * grid_radius + 1
    spacing_m = 90.0

    meters_per_degree_lat = 111320.0
    meters_per_degree_lon = 111320.0 * np.cos(np.radians(latitude))
    if meters_per_degree_lon <= 0:
        raise RuntimeError("Invalid longitude scale for elevation fallback.")

    lat_step = spacing_m / meters_per_degree_lat
    lon_step = spacing_m / meters_per_degree_lon

    points = []
    point_coords = []
    for r in range(-grid_radius, grid_radius + 1):
        for c in range(-grid_radius, grid_radius + 1):
            point_lat = latitude + (r * lat_step)
            point_lon = longitude + (c * lon_step)
            point_coords.append((r, c))
            points.append((point_lat, point_lon))

    params = {
        "latitude": ",".join(f"{lat:.6f}" for lat, _ in points),
        "longitude": ",".join(f"{lon:.6f}" for _, lon in points),
    }

    response = requests.get(
        OPEN_METEO_ELEVATION_URL,
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    elevations = payload.get("elevation")
    if not isinstance(elevations, list) or len(elevations) != len(points):
        raise RuntimeError("Copernicus GLO-90 elevation fallback returned an unexpected response.")

    grid = np.full((grid_size, grid_size), np.nan, dtype=np.float64)
    for (r, c), value in zip(point_coords, elevations):
        if value is not None:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                numeric = np.nan
            if np.isfinite(numeric):
                grid[r + grid_radius, c + grid_radius] = numeric

    center = grid_radius
    required = [
        grid[center, center],
        grid[center, center - 1],
        grid[center, center + 1],
        grid[center - 1, center],
        grid[center + 1, center],
    ]
    if not all(np.isfinite(value) for value in required):
        raise RuntimeError("Copernicus GLO-90 fallback did not return valid centre/neighbour elevations.")

    result = _terrain_from_grid(
        grid,
        dx=spacing_m,
        dy=spacing_m,
        center_index=center,
        source_name="Copernicus DEM GLO-90 via Open-Meteo Elevation API",
        sampled_latitude=latitude,
        sampled_longitude=longitude,
    )

    _ELEVATION_TERRAIN_CACHE[cache_key] = result.copy()
    return result


def extract_dem_features(latitude, longitude):
    """Extract real terrain features, using supplied DEM first and GLO-90 as a real-data fallback."""
    latitude = float(latitude)
    longitude = float(longitude)

    # Render may not have rasterio's native shared libraries, and the DEM is
    # intentionally not required in the deployment image. In either case,
    # use the real Copernicus GLO-90 point/grid fallback. No synthetic terrain
    # values are introduced.
    if rasterio is None or not os.path.exists(DEM_PATH):
        return _fetch_copernicus_glo90_terrain(latitude, longitude)

    with load_dem() as dem:
        row, col = dem.index(longitude, latitude)

        if not (0 <= row < dem.height and 0 <= col < dem.width):
            raise ValueError("Requested location is outside the available DEM coverage.")

        original_row, original_col = row, col
        found = _find_real_dem_center(dem, row, col)

        if found is None:
            # The local supplied DEM has a NoData hole around this location.
            # Fall back only to another real DEM source; never synthesize.
            return _fetch_copernicus_glo90_terrain(latitude, longitude)

        row, col = found
        used_nearest_valid_pixel = (row != original_row or col != original_col)

        row_start = max(0, row - TERRAIN_RADIUS)
        row_stop = min(dem.height, row + TERRAIN_RADIUS + 1)
        col_start = max(0, col - TERRAIN_RADIUS)
        col_stop = min(dem.width, col + TERRAIN_RADIUS + 1)

        window = dem.read(
            1,
            window=Window(
                col_start,
                row_start,
                col_stop - col_start,
                row_stop - row_start,
            ),
        ).astype(np.float64)

        nodata = dem.nodata
        if nodata is not None:
            window[np.isclose(window, nodata)] = np.nan

        center_row = row - row_start
        center_col = col - col_start

        if not (1 <= center_row < window.shape[0] - 1 and 1 <= center_col < window.shape[1] - 1):
            raise RuntimeError("Insufficient DEM neighbourhood around sampled terrain center.")

        elevation = float(window[center_row, center_col])
        if not np.isfinite(elevation):
            raise RuntimeError("DEM elevation is unavailable at the selected real DEM pixel.")

        z_left = window[center_row, center_col - 1]
        z_right = window[center_row, center_col + 1]
        z_up = window[center_row - 1, center_col]
        z_down = window[center_row + 1, center_col]
        if not all(np.isfinite(value) for value in [z_left, z_right, z_up, z_down]):
            # A valid centre may still sit inside a partially voided 11x11 window.
            # Use the real GLO-90 fallback rather than fabricating missing neighbours.
            return _fetch_copernicus_glo90_terrain(latitude, longitude)

        transform = dem.transform
        dx_degree = abs(float(transform.a))
        dy_degree = abs(float(transform.e))
        if dx_degree <= 0 or dy_degree <= 0:
            raise RuntimeError("Invalid DEM resolution.")

        lat_rad = np.radians(latitude)
        meters_per_degree_lat = 111320.0
        meters_per_degree_lon = 111320.0 * np.cos(lat_rad)
        dx = dx_degree * meters_per_degree_lon
        dy = dy_degree * meters_per_degree_lat
        if dx <= 0 or dy <= 0:
            raise RuntimeError("Invalid DEM metre resolution.")

        dzdx = (z_right - z_left) / (2.0 * dx)
        dzdy = (z_down - z_up) / (2.0 * dy)
        slope_rad = np.arctan(np.sqrt(dzdx ** 2 + dzdy ** 2))
        slope_deg = float(np.degrees(slope_rad))

        aspect_rad = np.arctan2(dzdy, -dzdx)
        aspect_sin = float(np.sin(aspect_rad))
        aspect_cos = float(np.cos(aspect_rad))

        zxx = (z_right - 2.0 * elevation + z_left) / (dx ** 2)
        zyy = (z_down - 2.0 * elevation + z_up) / (dy ** 2)
        curvature = float(zxx + zyy)

        valid_values = window[np.isfinite(window)]
        if valid_values.size == 0:
            raise RuntimeError("No valid DEM values available in terrain window.")

        terrain_roughness = float(np.std(valid_values))
        tpi = float(elevation - np.mean(valid_values))

        features = {
            "elevation": elevation,
            "slope_deg": slope_deg,
            "aspect_sin": aspect_sin,
            "aspect_cos": aspect_cos,
            "curvature": curvature,
            "terrain_roughness": terrain_roughness,
            "tpi": tpi,
        }

        for name, value in features.items():
            if not np.isfinite(value):
                raise RuntimeError(f"Invalid DEM terrain feature: {name}={value}")

        sampled_lon, sampled_lat = dem.xy(row, col)
        sampled_lat_diff = float(sampled_lat) - latitude
        sampled_lon_diff = float(sampled_lon) - longitude
        sampling_distance_m = float(
            np.sqrt(
                (sampled_lat_diff * meters_per_degree_lat) ** 2
                + (sampled_lon_diff * meters_per_degree_lon) ** 2
            )
        )

        return {
            **features,
            "dem_sampling": {
                "requested_latitude": latitude,
                "requested_longitude": longitude,
                "sampled_latitude": float(sampled_lat),
                "sampled_longitude": float(sampled_lon),
                "used_nearest_valid_pixel": used_nearest_valid_pixel,
                "sampling_distance_meters": round(sampling_distance_m, 2),
                "terrain_source": "Supplied 1-arcsec DEM",
            },
        }


# ============================================================
# LIVE WEATHER
# ============================================================

def fetch_live_weather(latitude, longitude):
    params = {
        "latitude": float(latitude),
        "longitude": float(longitude),
        "past_days": 35,
        "forecast_days": 1,
        "daily": (
            "temperature_2m_mean,"
            "relative_humidity_2m_mean,"
            "precipitation_sum"
        ),
        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "precipitation,"
            "rain"
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
        raise RuntimeError("Live daily weather data was not returned.")

    return payload


# ============================================================
# DAILY WEATHER FEATURES
# ============================================================

def build_daily_dataframe(payload):
    daily = payload.get("daily")
    if not daily:
        raise RuntimeError("Daily weather data is empty.")

    df = pd.DataFrame(daily)
    if df.empty:
        raise RuntimeError("Daily weather dataframe is empty.")

    df["date"] = pd.to_datetime(df["time"], errors="coerce").dt.normalize()

    required_columns = [
        "precipitation_sum",
        "temperature_2m_mean",
        "relative_humidity_2m_mean",
    ]

    for column in required_columns:
        if column not in df.columns:
            raise RuntimeError(f"Missing live field: {column}")
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = (
        df.dropna(subset=["date"])
        .sort_values("date")
        .drop_duplicates("date")
        .reset_index(drop=True)
    )

    if df.empty:
        raise RuntimeError("No valid daily weather records returned.")

    # Training used NASA POWER PRECTOTCORR as the precipitation/rain basis.
    # For live prediction, use Open-Meteo precipitation_sum consistently.
    rainfall = df["precipitation_sum"]
    if rainfall.isna().all():
        raise RuntimeError("Real precipitation data unavailable.")

    df["rain_1day"] = rainfall
    df["rain_3day"] = rainfall.rolling(3, min_periods=3).sum()
    df["rain_7day"] = rainfall.rolling(7, min_periods=7).sum()
    df["rain_14day"] = rainfall.rolling(14, min_periods=14).sum()
    df["rain_30day"] = rainfall.rolling(30, min_periods=30).sum()
    df["precipitation_3day"] = rainfall.rolling(3, min_periods=3).sum()
    df["precipitation_7day"] = rainfall.rolling(7, min_periods=7).sum()

    # IMPORTANT: never use the future forecast day for ML features.
    today_local = pd.Timestamp(
        datetime.now(ZoneInfo(LOCAL_TIMEZONE)).date()
    )
    completed = df[df["date"] < today_local].copy()

    if completed.empty:
        raise RuntimeError("No completed daily weather observation is available.")

    latest = completed.iloc[-1]

    required_rolling = [
        "rain_3day",
        "rain_7day",
        "rain_14day",
        "rain_30day",
        "precipitation_3day",
        "precipitation_7day",
    ]

    for column in required_rolling:
        if pd.isna(latest[column]):
            raise RuntimeError(
                "Insufficient real completed-day rainfall history for "
                f"{column}."
            )

    return df, latest


# ============================================================
# CURRENT WEATHER
# ============================================================

def get_current_weather(payload):
    current = payload.get("current")
    if not current:
        raise RuntimeError("Current weather unavailable.")

    def number(name):
        value = current.get(name)
        if value is None or pd.isna(value):
            return None
        return float(value)

    return {
        "temperature": number("temperature_2m"),
        "humidity": number("relative_humidity_2m"),
        "precipitation": number("precipitation"),
        "rain": number("rain"),
        "time": current.get("time"),
    }


# ============================================================
# RISK LEVEL
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
# LIVE LANDSLIDE PREDICTION
# ============================================================

def predict_landslide_live(latitude, longitude):
    latitude = float(latitude)
    longitude = float(longitude)

    package = load_model()
    model = package["model"]
    features = list(package["features"])

    payload = fetch_live_weather(latitude, longitude)
    _, latest = build_daily_dataframe(payload)

    terrain = extract_dem_features(latitude, longitude)

    values = {
        "latitude": latitude,
        "longitude": longitude,
        "elevation": terrain["elevation"],
        "slope_deg": terrain["slope_deg"],
        "aspect_sin": terrain["aspect_sin"],
        "aspect_cos": terrain["aspect_cos"],
        "curvature": terrain["curvature"],
        "terrain_roughness": terrain["terrain_roughness"],
        "tpi": terrain["tpi"],
        "rain_1day": float(latest["rain_1day"]),
        "rain_3day": float(latest["rain_3day"]),
        "rain_7day": float(latest["rain_7day"]),
        "rain_14day": float(latest["rain_14day"]),
        "rain_30day": float(latest["rain_30day"]),
        "precipitation_3day": float(latest["precipitation_3day"]),
        "precipitation_7day": float(latest["precipitation_7day"]),
        "temperature": float(latest["temperature_2m_mean"]),
        "humidity": float(latest["relative_humidity_2m_mean"]),
    }

    missing_features = [
        feature for feature in features if feature not in values
    ]
    if missing_features:
        raise RuntimeError(
            "Landslide model expects features not provided by predictor: "
            + ", ".join(missing_features)
        )

    invalid_features = []
    for feature in features:
        try:
            numeric = float(values[feature])
        except (TypeError, ValueError):
            invalid_features.append(f"{feature}={values[feature]!r}")
            continue
        if not np.isfinite(numeric):
            invalid_features.append(f"{feature}={numeric}")

    if invalid_features:
        raise RuntimeError(
            "Invalid ML feature values: "
            + ", ".join(invalid_features)
        )

    X = pd.DataFrame([
        {feature: values[feature] for feature in features}
    ])

    prediction = int(model.predict(X)[0])
    probabilities = model.predict_proba(X)[0]
    class_probabilities = {
        int(cls): float(prob)
        for cls, prob in zip(model.classes_, probabilities)
    }

    landslide_probability = class_probabilities.get(1)
    if landslide_probability is None:
        raise RuntimeError("Trained model returned no LANDSLIDE probability for class 1.")

    risk_score = round(landslide_probability * 100.0)
    risk_level = probability_to_risk(landslide_probability)
    current = get_current_weather(payload)

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    return {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "confidence": round(landslide_probability, 4),
        "landslide_probability": round(landslide_probability, 4),
        "prediction": prediction,
        "probabilities": {
            str(key): round(value, 4)
            for key, value in class_probabilities.items()
        },
        "weather": {
            "temperature": current["temperature"],
            "humidity": current["humidity"],
            "rain": current["rain"],
            "precipitation": current["precipitation"],
            "completed_day": str(latest["date"].date()),
            "rain_1day": round(float(latest["rain_1day"]), 2),
            "rain_3day": round(float(latest["rain_3day"]), 2),
            "rain_7day": round(float(latest["rain_7day"]), 2),
            "rain_14day": round(float(latest["rain_14day"]), 2),
            "rain_30day": round(float(latest["rain_30day"]), 2),
            "precipitation_3day": round(float(latest["precipitation_3day"]), 2),
            "precipitation_7day": round(float(latest["precipitation_7day"]), 2),
        },
        "terrain": {
            "elevation": round(terrain["elevation"], 2),
            "slope_deg": round(terrain["slope_deg"], 4),
            "aspect_sin": round(terrain["aspect_sin"], 4),
            "aspect_cos": round(terrain["aspect_cos"], 4),
            "curvature": round(terrain["curvature"], 8),
            "terrain_roughness": round(terrain["terrain_roughness"], 4),
            "tpi": round(terrain["tpi"], 4),
        },
        "dem_sampling": terrain["dem_sampling"],
        "location": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "source": (
            "GSI landslide model + supplied DEM (with real Copernicus GLO-90 fallback) + "
            "Open-Meteo live weather"
        ),
        "training_weather_source": "NASA POWER Daily Meteorology",
        "live_weather_source": "Open-Meteo",
        "model_version": package.get("version", "unknown"),
        "completed_daily_data_only": True,
        "real_data_only": True,
        "generated_at": generated_at,
    }


# ============================================================
# LOCAL TEST
# ============================================================

if __name__ == "__main__":
    result = predict_landslide_live(
        latitude=29.5971,
        longitude=79.6591,
    )
    print(result)
