"""
DISASTER INTELLIGENCE PLATFORM
REAL-DATA LANDSLIDE ML TRAINING - V3 FAST NASA POWER

PURPOSE
-------
Train the Uttarakhand landslide susceptibility/event model using:

1. GSI landslide inventory -> positive landslide locations
2. Supplied 1-arc-second DEM GeoTIFFs -> terrain features
3. NASA POWER Daily Meteorology -> historical weather features

WHY THIS VERSION IS FAST
------------------------
The previous pipeline made one historical Open-Meteo request for every
positive and background coordinate. With thousands of points, that creates
thousands of requests and can trigger rate limits.

This version instead:

- derives a weather group from the real GSI district field;
- computes a real centroid from the inventory points in each group;
- makes ONE NASA POWER historical request per weather group;
- caches each group response locally;
- reuses that real historical weather series for every landslide/background
  point in the same group;
- keeps terrain extraction at the actual landslide/background coordinate;
- does NOT create synthetic rainfall, synthetic landslides, or fake weather.

The weather is therefore group-level historical meteorology, while the
terrain remains point-specific from the supplied GIS DEM.

IMPORTANT DATA INTERPRETATION
-----------------------------
- GSI inventory rows are positive inventory locations, not necessarily
  complete records of every landslide that ever occurred.
- Background rows are non-inventory/background samples, NOT confirmed
  "no landslide" observations.
- When GSI provides only a year and not an exact date, the model chooses the
  highest 3-day precipitation day within that same historical year. This is
  a year-level weather proxy, not an invented event date.
- NASA POWER is used only for historical training weather. Live prediction
  can continue to use the existing live-weather service separately.

MODEL OUTPUT
------------
0 = BACKGROUND
1 = LANDSLIDE
"""

import hashlib
import json
import math
import os
import re
import pickle
import time
import warnings
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import requests
import rasterio
from rasterio.windows import Window
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

warnings.filterwarnings("ignore")


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# IMPORTANT: this training script itself lives in
# backend/app/ml/data/landslide/
# so the local landslide data folders/files are relative to BASE_DIR.
DATA_DIR = BASE_DIR

INVENTORY_PATH = os.path.join(
    DATA_DIR,
    "gsi_landslide_inventory.csv",
)

DEM_DIR = os.path.join(DATA_DIR, "dem")

MODEL_PATH = os.path.join(BASE_DIR, "landslide_model.pkl")

CACHE_DIR = os.path.join(DATA_DIR, "weather_cache_nasa_power_v3")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DEM_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)


# ============================================================
# CONFIG
# ============================================================

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
NASA_POWER_COMMUNITY = "RE"
NASA_POWER_PARAMETERS = "T2M,T2MDEW,PRECTOTCORR"

# NASA POWER daily data starts in 1981 for this training route.
TRAINING_START_YEAR = 1981

MAX_POSITIVE_SAMPLES = 2500
NEGATIVE_MULTIPLIER = 1
RANDOM_STATE = 42

TERRAIN_WINDOW = 11

# 4 concurrent requests is plenty because this build normally needs only
# around a dozen district/group requests. It also avoids unnecessary burst
# pressure on the service.
WEATHER_MAX_WORKERS = 4

WEATHER_RETRIES = 4
WEATHER_TIMEOUT = 120
WEATHER_RETRY_DELAYS = [15, 30, 60, 120]

N_ESTIMATORS = 400


# ============================================================
# MODEL FEATURES
# ============================================================

FEATURES = [
    "latitude",
    "longitude",

    # DEM / terrain
    "elevation",
    "slope_deg",
    "aspect_sin",
    "aspect_cos",
    "curvature",
    "terrain_roughness",
    "tpi",

    # Historical weather
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


# ============================================================
# DISTRICT / WEATHER GROUP NORMALIZATION
# ============================================================

OFFICIAL_DISTRICTS = [
    "Udham Singh Nagar",
    "Pauri Garhwal",
    "Tehri Garhwal",
    "Pithoragarh",
    "Rudraprayag",
    "Uttarkashi",
    "Bageshwar",
    "Champawat",
    "Dehradun",
    "Haridwar",
    "Nainital",
    "Almora",
    "Chamoli",
]

OFFICIAL_DISTRICTS = sorted(
    OFFICIAL_DISTRICTS,
    key=len,
    reverse=True,
)


def normalize_text(value):
    return " ".join(str(value).strip().split())


def weather_group_for_district(value):
    """
    Convert GSI's district/locality field to a stable weather group.

    Examples:
        'Almora Forest' -> 'Almora'
        'Pauri Garhwal Pokhra Road' -> 'Pauri Garhwal'
        'Garhwal Devaprayag' -> 'Garhwal'
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "Unknown"

    text = normalize_text(value)
    lower = text.lower()

    if lower in {"", "nan", "none", "null"}:
        return "Unknown"

    for district in OFFICIAL_DISTRICTS:
        d = district.lower()
        if lower == d or lower.startswith(d + " "):
            return district

    if lower == "garhwal" or lower.startswith("garhwal "):
        return "Garhwal"

    # Keep any other unexpected real label as its own group. This avoids
    # silently forcing it into a district where we do not have evidence.
    return text if text else "Unknown"


# ============================================================
# DEM MANAGEMENT
# ============================================================

DEM_DATASETS = []
TERRAIN_CACHE = {}


def file_hash(path):
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_dem_tiles():
    global DEM_DATASETS

    tif_files = sorted(
        os.path.join(DEM_DIR, name)
        for name in os.listdir(DEM_DIR)
        if name.lower().endswith(".tif")
    )

    if not tif_files:
        raise FileNotFoundError(
            "\nNo DEM TIFF files found.\n"
            f"Expected folder:\n{DEM_DIR}\n"
        )

    # Only hash files that have the same byte size. This preserves exact
    # duplicate detection while avoiding an unnecessary full-file hash for
    # obviously different files.
    size_groups = {}
    for path in tif_files:
        size_groups.setdefault(os.path.getsize(path), []).append(path)

    seen_hashes = set()
    unique_files = []

    for size, paths in size_groups.items():
        for path in paths:
            digest = file_hash(path)
            if digest in seen_hashes:
                print(f"[DUPLICATE] Ignoring: {os.path.basename(path)}")
                continue
            seen_hashes.add(digest)
            unique_files.append(path)

    unique_files.sort()

    print("\n" + "=" * 70)
    print("GIS DEM DATA")
    print("=" * 70)
    print(f"TIFF files found : {len(tif_files)}")
    print(f"Unique DEM files : {len(unique_files)}")

    for path in unique_files:
        src = rasterio.open(path)
        DEM_DATASETS.append(src)

        print(f"\n{os.path.basename(path)}")
        print(f"  CRS       : {src.crs}")
        print(f"  Size      : {src.width} x {src.height}")
        print(f"  Resolution: {src.res}")
        print(f"  Bounds    : {src.bounds}")
        print(f"  NoData    : {src.nodata}")

    if not DEM_DATASETS:
        raise RuntimeError("No usable DEM datasets found.")


def close_dem_tiles():
    global DEM_DATASETS
    for src in DEM_DATASETS:
        try:
            src.close()
        except Exception:
            pass
    DEM_DATASETS = []


def find_dem_tile(latitude, longitude):
    for src in DEM_DATASETS:
        bounds = src.bounds
        if (
            bounds.left <= longitude <= bounds.right
            and bounds.bottom <= latitude <= bounds.top
        ):
            return src
    return None


# ============================================================
# TERRAIN FEATURES
# ============================================================

def extract_terrain_features(latitude, longitude):
    """Extract real terrain features from the supplied DEM."""

    cache_key = (round(float(latitude), 6), round(float(longitude), 6))
    cached = TERRAIN_CACHE.get(cache_key)
    if cached is not None:
        return cached.copy()

    src = find_dem_tile(latitude, longitude)
    if src is None:
        return None

    try:
        row, col = src.index(longitude, latitude)
        half = TERRAIN_WINDOW // 2

        window = Window(
            col - half,
            row - half,
            TERRAIN_WINDOW,
            TERRAIN_WINDOW,
        )

        elevation = src.read(
            1,
            window=window,
            boundless=True,
            fill_value=src.nodata,
        ).astype(np.float32)

        nodata = src.nodata
        if nodata is not None:
            elevation[elevation == nodata] = np.nan

        if np.isnan(elevation).all():
            return None

        center = TERRAIN_WINDOW // 2
        center_elevation = elevation[center, center]

        if not np.isfinite(center_elevation):
            return None

        lat_rad = np.radians(float(latitude))
        meters_per_degree_lat = 111320.0
        meters_per_degree_lon = 111320.0 * np.cos(lat_rad)

        dx = abs(src.transform.a) * meters_per_degree_lon
        dy = abs(src.transform.e) * meters_per_degree_lat

        if dx <= 0 or dy <= 0:
            return None

        z_left = elevation[center, center - 1]
        z_right = elevation[center, center + 1]
        z_up = elevation[center - 1, center]
        z_down = elevation[center + 1, center]

        if not np.all(
            np.isfinite([z_left, z_right, z_up, z_down])
        ):
            return None

        dzdx = (z_right - z_left) / (2.0 * dx)
        dzdy = (z_down - z_up) / (2.0 * dy)

        slope_rad = np.arctan(np.sqrt(dzdx**2 + dzdy**2))
        slope_deg = np.degrees(slope_rad)

        aspect_rad = np.arctan2(dzdy, -dzdx)
        aspect_deg = (np.degrees(aspect_rad) + 360.0) % 360.0

        aspect_sin = np.sin(np.radians(aspect_deg))
        aspect_cos = np.cos(np.radians(aspect_deg))

        zxx = (
            z_right - 2.0 * center_elevation + z_left
        ) / (dx**2)
        zyy = (
            z_down - 2.0 * center_elevation + z_up
        ) / (dy**2)
        curvature = zxx + zyy

        valid_values = elevation[np.isfinite(elevation)]
        if len(valid_values) == 0:
            return None

        terrain_roughness = float(np.std(valid_values))
        local_mean = float(np.mean(valid_values))
        tpi = float(center_elevation - local_mean)

        result = {
            "elevation": float(center_elevation),
            "slope_deg": float(slope_deg),
            "aspect_sin": float(aspect_sin),
            "aspect_cos": float(aspect_cos),
            "curvature": float(curvature),
            "terrain_roughness": terrain_roughness,
            "tpi": tpi,
        }

        TERRAIN_CACHE[cache_key] = result.copy()
        return result

    except Exception as exc:
        print(
            f"DEM extraction failed at {latitude:.5f}, "
            f"{longitude:.5f}: {exc}"
        )
        return None


# ============================================================
# COLUMN NORMALIZATION
# ============================================================

def normalize_column_name(value):
    return (
        str(value)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
        .replace("(", "")
        .replace(")", "")
        .replace(".", "")
    )


def find_column(df, candidates):
    normalized = {
        normalize_column_name(col): col
        for col in df.columns
    }

    normalized_candidates = [
        normalize_column_name(candidate)
        for candidate in candidates
    ]

    for key in normalized_candidates:
        if key in normalized:
            return normalized[key]

    for key, original in normalized.items():
        for candidate_key in normalized_candidates:
            if candidate_key in key or key in candidate_key:
                return original

    return None


# ============================================================
# LOAD + PREPARE GSI
# ============================================================

def load_gsi_inventory():
    if not os.path.exists(INVENTORY_PATH):
        raise FileNotFoundError(
            "\nGSI landslide inventory not found.\n"
            f"Expected:\n{INVENTORY_PATH}\n"
        )

    print("\nLoading GSI landslide inventory...")
    df = pd.read_csv(INVENTORY_PATH, low_memory=False)

    if df.empty:
        raise RuntimeError("GSI inventory CSV is empty.")

    print(f"Inventory records: {len(df):,}")
    return df


def extract_last_year(value):
    # GSI history normally ends with the documented event year.
    # Restrict extraction to the trailing year so years embedded in slide
    # identifiers / map-sheet codes are never mistaken for event years.
    match = re.search(r"\b((?:19|20)\d{2})\s*$", str(value))
    return int(match.group(1)) if match else None


def prepare_inventory(df):
    latitude_column = find_column(
        df, ["latitude", "lat", "latitude_deg", "y"]
    )
    longitude_column = find_column(
        df, ["longitude", "lon", "long", "longitude_deg", "x"]
    )
    date_column = find_column(
        df,
        [
            "date",
            "event_date",
            "landslide_date",
            "occurrence_date",
            "landslide_occurrence_date",
            "start_date",
        ],
    )
    district_column = find_column(df, ["district"])
    raw_record_column = find_column(df, ["raw_record", "history"])

    if latitude_column is None or longitude_column is None:
        raise RuntimeError(
            "Latitude/longitude columns were not found. "
            f"Available columns: {list(df.columns)}"
        )

    if district_column is None:
        raise RuntimeError(
            "District column is required so weather can be fetched once "
            "per real GSI district/group."
        )

    result = pd.DataFrame()
    result["latitude"] = pd.to_numeric(
        df[latitude_column], errors="coerce"
    )
    result["longitude"] = pd.to_numeric(
        df[longitude_column], errors="coerce"
    )
    result["district_raw"] = df[district_column].astype(str)

    if date_column:
        result["date"] = pd.to_datetime(
            df[date_column], errors="coerce"
        )
    else:
        result["date"] = pd.NaT

    result["event_year"] = pd.NA

    if raw_record_column is not None:
        raw_text = df[raw_record_column].astype(str)
        result["event_year"] = raw_text.map(extract_last_year)

    actual_date_mask = result["date"].notna()
    result.loc[actual_date_mask, "event_year"] = (
        result.loc[actual_date_mask, "date"].dt.year
    )

    result["event_year"] = pd.to_numeric(
        result["event_year"], errors="coerce"
    ).astype("Int64")

    # Uttarakhand geographic bounds.
    result = result[
        result["latitude"].between(28.5, 31.5)
        & result["longitude"].between(77.5, 81.5)
    ].copy()

    result = result.dropna(subset=["latitude", "longitude"])
    result = result.drop_duplicates(subset=["latitude", "longitude"])
    result = result.reset_index(drop=True)

    result["weather_group"] = result["district_raw"].map(
        weather_group_for_district
    )

    if len(result) > MAX_POSITIVE_SAMPLES:
        print(
            f"\nLimiting inventory to {MAX_POSITIVE_SAMPLES:,} "
            "real GSI points for the presentation build."
        )
        result = result.sample(
            MAX_POSITIVE_SAMPLES,
            random_state=RANDOM_STATE,
        ).reset_index(drop=True)

    print(f"\nValid Uttarakhand GSI points: {len(result):,}")
    print("\nWeather groups:")
    print(result["weather_group"].value_counts().to_string())

    if result.empty:
        raise RuntimeError("No valid Uttarakhand GSI coordinates found.")

    return result


# ============================================================
# WEATHER CACHE / NASA POWER
# ============================================================

def weather_cache_path(group):
    safe = "".join(
        char if char.isalnum() else "_"
        for char in group
    ).strip("_")
    return os.path.join(CACHE_DIR, f"{safe}.json")


def get_training_end_date(max_event_year):
    yesterday = date.today() - timedelta(days=2)
    requested_year = int(max_event_year) if pd.notna(max_event_year) else yesterday.year - 1
    requested_end = date(requested_year, 12, 31)
    return min(yesterday, requested_end)


def fetch_nasa_group(group, latitude, longitude, start_date, end_date):
    cache_path = weather_cache_path(group)

    # Cache metadata contains the exact coordinate and date span used, so a
    # future change does not accidentally reuse an incompatible cache.
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)

            meta = cached.get("_meta", {})
            payload = cached.get("payload")
            if (
                isinstance(payload, dict)
                and meta.get("latitude") == round(float(latitude), 6)
                and meta.get("longitude") == round(float(longitude), 6)
                and meta.get("start") == start_date
                and meta.get("end") == end_date
                and isinstance(payload.get("properties"), dict)
            ):
                print(f"[CACHE HIT] NASA POWER: {group}")
                return payload
        except Exception as exc:
            print(f"Cache read failed for {group}: {exc}")

    params = {
        "parameters": NASA_POWER_PARAMETERS,
        "community": NASA_POWER_COMMUNITY,
        "longitude": float(longitude),
        "latitude": float(latitude),
        "start": start_date.replace("-", ""),
        "end": end_date.replace("-", ""),
        "format": "JSON",
    }

    for attempt in range(1, WEATHER_RETRIES + 1):
        print(
            f"[NASA POWER] {group}: {start_date} -> {end_date} "
            f"(attempt {attempt})"
        )
        try:
            response = requests.get(
                NASA_POWER_URL,
                params=params,
                timeout=WEATHER_TIMEOUT,
            )

            if response.status_code == 429:
                raise RuntimeError("HTTP 429 rate limit")

            response.raise_for_status()
            payload = response.json()

            properties = payload.get("properties", {})
            parameter_block = properties.get("parameter", {})
            if not parameter_block:
                raise RuntimeError(
                    "NASA POWER response did not contain parameter data."
                )

            envelope = {
                "_meta": {
                    "group": group,
                    "latitude": round(float(latitude), 6),
                    "longitude": round(float(longitude), 6),
                    "start": start_date,
                    "end": end_date,
                    "parameters": NASA_POWER_PARAMETERS,
                    "source": "NASA POWER Daily API",
                },
                "payload": payload,
            }

            temp_path = cache_path + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(envelope, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, cache_path)

            return payload

        except Exception as exc:
            if attempt >= WEATHER_RETRIES:
                raise RuntimeError(
                    f"NASA POWER failed for {group} after "
                    f"{WEATHER_RETRIES} attempts: {exc}"
                ) from exc

            delay = WEATHER_RETRY_DELAYS[attempt - 1]
            print(f"NASA POWER retry in {delay}s: {exc}")
            time.sleep(delay)

    raise RuntimeError(f"NASA POWER failed for group: {group}")


def payload_to_weather_dataframe(payload):
    parameters = payload.get("properties", {}).get("parameter", {})

    required = ["T2M", "T2MDEW", "PRECTOTCORR"]
    missing = [name for name in required if name not in parameters]
    if missing:
        raise RuntimeError(
            f"NASA POWER missing parameters: {missing}"
        )

    dates = sorted(
        set(parameters["T2M"])
        & set(parameters["T2MDEW"])
        & set(parameters["PRECTOTCORR"])
    )

    rows = []
    for key in dates:
        try:
            rows.append(
                {
                    "date": pd.to_datetime(key, format="%Y%m%d"),
                    "temperature": float(parameters["T2M"][key]),
                    "dewpoint": float(parameters["T2MDEW"][key]),
                    "precipitation": float(
                        parameters["PRECTOTCORR"][key]
                    ),
                }
            )
        except (TypeError, ValueError):
            continue

    weather = pd.DataFrame(rows)
    if weather.empty:
        raise RuntimeError("NASA POWER weather dataframe is empty.")

    # NASA POWER uses -999 as a missing-value sentinel in many products.
    weather = weather.replace([-999, -999.0], np.nan)
    weather = weather.dropna(
        subset=["temperature", "dewpoint", "precipitation"]
    )
    weather = (
        weather.sort_values("date")
        .drop_duplicates("date")
        .reset_index(drop=True)
    )

    # Magnus-formula approximation from temperature + dew point.
    # This is a deterministic derived feature, not synthetic humidity.
    def saturation_vapor_pressure(temp_c):
        return np.exp((17.625 * temp_c) / (243.04 + temp_c))

    es = saturation_vapor_pressure(weather["temperature"])
    ea = saturation_vapor_pressure(weather["dewpoint"])
    weather["humidity"] = (100.0 * ea / es).clip(0.0, 100.0)

    rain = weather["precipitation"].clip(lower=0.0)
    weather["rain_1day"] = rain
    weather["rain_3day"] = rain.rolling(3, min_periods=3).sum()
    weather["rain_7day"] = rain.rolling(7, min_periods=7).sum()
    weather["rain_14day"] = rain.rolling(14, min_periods=14).sum()
    weather["rain_30day"] = rain.rolling(30, min_periods=30).sum()
    weather["precipitation_3day"] = weather["rain_3day"]
    weather["precipitation_7day"] = weather["rain_7day"]

    return weather.dropna(
        subset=[
            "rain_3day",
            "rain_7day",
            "rain_14day",
            "rain_30day",
            "precipitation_3day",
            "precipitation_7day",
            "temperature",
            "humidity",
        ]
    ).reset_index(drop=True)


def build_weather_groups(inventory):
    grouped = (
        inventory.groupby("weather_group")[["latitude", "longitude"]]
        .mean()
        .reset_index()
    )

    return {
        row["weather_group"]: {
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
        }
        for _, row in grouped.iterrows()
    }


def load_all_group_weather(inventory):
    max_event_year = pd.to_numeric(
        inventory["event_year"], errors="coerce"
    ).max()
    end_date = get_training_end_date(max_event_year)

    if end_date < date(TRAINING_START_YEAR, 1, 1):
        raise RuntimeError(
            "No overlap exists between the GSI event years and "
            "the NASA POWER training period starting in 1981."
        )

    start_date = date(TRAINING_START_YEAR, 1, 1)
    start_text = start_date.isoformat()
    end_text = end_date.isoformat()

    centers = build_weather_groups(inventory)
    print("\n" + "=" * 70)
    print("NASA POWER WEATHER PLAN")
    print("=" * 70)
    print(f"Weather start : {start_text}")
    print(f"Weather end   : {end_text}")
    print(f"Weather groups: {len(centers)}")
    print("ONE historical request per group; cached afterwards.")

    weather = {}

    # The group count is small. Keep a bounded worker pool for speed without
    # generating a large request burst.
    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=WEATHER_MAX_WORKERS) as executor:
        futures = {
            executor.submit(
                fetch_nasa_group,
                group,
                coords["latitude"],
                coords["longitude"],
                start_text,
                end_text,
            ): group
            for group, coords in centers.items()
        }

        for future in as_completed(futures):
            group = futures[future]
            payload = future.result()
            weather[group] = payload_to_weather_dataframe(payload)
            print(
                f"[READY] {group}: {len(weather[group]):,} daily rows"
            )

    return weather, centers, start_text, end_text


# ============================================================
# WEATHER ROW SELECTION
# ============================================================

def choose_weather_rows(weather_df, event_date=None, event_year=None):
    usable = weather_df.dropna(
        subset=[
            "rain_3day",
            "rain_7day",
            "rain_14day",
            "rain_30day",
            "precipitation_3day",
            "precipitation_7day",
        ]
    ).copy()

    if usable.empty:
        return usable

    if event_date is not None and pd.notna(event_date):
        event_date = pd.Timestamp(event_date)
        exact = usable[usable["date"] == event_date]
        if not exact.empty:
            return exact.head(1)

        usable["date_distance"] = (
            usable["date"] - event_date
        ).abs().dt.days
        closest = usable.sort_values("date_distance").head(1)
        return closest.drop(columns=["date_distance"])

    if event_year is not None and pd.notna(event_year):
        year = int(event_year)
        return usable[usable["date"].dt.year == year].copy()

    return pd.DataFrame()


# ============================================================
# SAMPLE BUILDER
# ============================================================

def weather_values(weather):
    return {
        "rain_1day": float(weather["rain_1day"]),
        "rain_3day": float(weather["rain_3day"]),
        "rain_7day": float(weather["rain_7day"]),
        "rain_14day": float(weather["rain_14day"]),
        "rain_30day": float(weather["rain_30day"]),
        "precipitation_3day": float(weather["precipitation_3day"]),
        "precipitation_7day": float(weather["precipitation_7day"]),
        "temperature": float(weather["temperature"]),
        "humidity": float(weather["humidity"]),
    }


def build_positive_samples(inventory, weather_by_group):
    samples = []
    skipped = 0

    print("\nBuilding positive samples from real GSI inventory...")

    for index, row in inventory.iterrows():
        latitude = float(row["latitude"])
        longitude = float(row["longitude"])
        group = row["weather_group"]
        terrain = extract_terrain_features(latitude, longitude)

        if terrain is None:
            skipped += 1
            continue

        weather_df = weather_by_group.get(group)
        if weather_df is None or weather_df.empty:
            skipped += 1
            continue

        selected_rows = choose_weather_rows(
            weather_df,
            event_date=row["date"],
            event_year=row["event_year"],
        )

        if selected_rows.empty:
            skipped += 1
            continue

        # For year-only records, select the wettest 3-day condition inside
        # that same documented year. This avoids inventing a specific date.
        if pd.isna(row["date"]) and pd.notna(row["event_year"]):
            selected_rows = (
                selected_rows.sort_values("rain_3day", ascending=False)
                .head(1)
            )

        weather = selected_rows.iloc[0]

        samples.append(
            {
                "latitude": latitude,
                "longitude": longitude,
                **terrain,
                **weather_values(weather),
                "event_year": (
                    int(row["event_year"])
                    if pd.notna(row["event_year"])
                    else None
                ),
                "weather_group": group,
                "landslide": 1,
            }
        )

    result = pd.DataFrame(samples)
    print(f"Positive samples created: {len(result):,}")
    print(f"Positive samples skipped : {skipped:,}")

    if not result.empty:
        print("\nPositive samples by weather group:")
        print(result["weather_group"].value_counts().to_string())

    return result


def generate_negative_locations(positive_df, weather_centers):
    rng = np.random.default_rng(RANDOM_STATE)

    target = max(
        100,
        int(
            positive_df[["latitude", "longitude"]]
            .drop_duplicates()
            .shape[0]
            * NEGATIVE_MULTIPLIER
        ),
    )

    lat_min = float(positive_df["latitude"].min())
    lat_max = float(positive_df["latitude"].max())
    lon_min = float(positive_df["longitude"].min())
    lon_max = float(positive_df["longitude"].max())

    # Slightly pad the real inventory envelope, while keeping the existing
    # broad Uttarakhand bounds.
    lat_min = max(29.0, lat_min - 0.10)
    lat_max = min(31.5, lat_max + 0.10)
    lon_min = max(77.5, lon_min - 0.10)
    lon_max = min(81.2, lon_max + 0.10)

    positive_coords = set(
        zip(
            positive_df["latitude"].round(4),
            positive_df["longitude"].round(4),
        )
    )

    group_names = list(weather_centers)
    negative_locations = []
    attempts = 0
    max_attempts = max(target * 30, 3000)

    while len(negative_locations) < target and attempts < max_attempts:
        attempts += 1

        latitude = rng.uniform(lat_min, lat_max)
        longitude = rng.uniform(lon_min, lon_max)
        key = (round(latitude, 4), round(longitude, 4))

        if key in positive_coords:
            continue

        if find_dem_tile(latitude, longitude) is None:
            continue

        # Assign each background point to the nearest real weather-group
        # centroid. No synthetic weather location is created.
        nearest_group = min(
            group_names,
            key=lambda name: (
                (latitude - weather_centers[name]["latitude"]) ** 2
                + (
                    math.cos(math.radians(latitude))
                    * (
                        longitude
                        - weather_centers[name]["longitude"]
                    )
                )
                ** 2
            ),
        )

        negative_locations.append(
            (latitude, longitude, nearest_group)
        )

    return negative_locations


def build_negative_samples(positive_df, weather_by_group, weather_centers):
    samples = []
    locations = generate_negative_locations(
        positive_df,
        weather_centers,
    )

    print(f"\nBackground locations: {len(locations):,}")

    positive_years = (
        pd.to_numeric(
            positive_df.get("event_year", pd.Series(dtype=float)),
            errors="coerce",
        )
        .dropna()
        .astype(int)
        .tolist()
    )
    positive_years = list(dict.fromkeys(positive_years))

    if not positive_years:
        print("No documented event years; background rows cannot be matched.")
        return pd.DataFrame()

    for index, (latitude, longitude, group) in enumerate(locations):
        terrain = extract_terrain_features(latitude, longitude)
        if terrain is None:
            continue

        weather_df = weather_by_group.get(group)
        if weather_df is None or weather_df.empty:
            continue

        target_year = positive_years[index % len(positive_years)]
        selected_rows = choose_weather_rows(
            weather_df,
            event_date=None,
            event_year=target_year,
        )

        if selected_rows.empty:
            continue

        weather = (
            selected_rows.sort_values(
                "rain_3day",
                ascending=False,
            )
            .iloc[0]
        )

        samples.append(
            {
                "latitude": float(latitude),
                "longitude": float(longitude),
                **terrain,
                **weather_values(weather),
                "event_year": int(target_year),
                "weather_group": group,
                "landslide": 0,
            }
        )

    result = pd.DataFrame(samples)
    print(f"Background samples created: {len(result):,}")
    return result


# ============================================================
# TRAINING / EVALUATION
# ============================================================

def train_model(dataset):
    X = dataset[FEATURES].astype(float)
    y = dataset["landslide"].astype(int)

    if y.nunique() < 2:
        raise RuntimeError("Dataset contains only one class.")

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=RANDOM_STATE,
        stratify=y,
    )

    print(f"\nTraining rows: {len(X_train):,}")
    print(f"Testing rows : {len(X_test):,}")

    model = RandomForestClassifier(
        n_estimators=N_ESTIMATORS,
        max_depth=18,
        min_samples_leaf=2,
        min_samples_split=4,
        class_weight="balanced_subsample",
        random_state=RANDOM_STATE,
        n_jobs=-1,
        oob_score=True,
        bootstrap=True,
    )

    print(f"\nTraining RandomForest ({N_ESTIMATORS} trees)...")
    started = time.perf_counter()
    model.fit(X_train, y_train)
    fit_seconds = time.perf_counter() - started
    print(f"Model fit time: {fit_seconds:.2f} seconds")

    predictions = model.predict(X_test)
    probabilities = model.predict_proba(X_test)[:, 1]

    accuracy = accuracy_score(y_test, predictions)
    auc = None
    if y_test.nunique() == 2:
        auc = roc_auc_score(y_test, probabilities)

    print(f"\nAccuracy: {accuracy:.4f}")
    if auc is not None:
        print(f"ROC-AUC:  {auc:.4f}")

    print("\nClassification Report:")
    print(classification_report(y_test, predictions, digits=4))

    print("\nConfusion Matrix:")
    print(confusion_matrix(y_test, predictions))

    importance = (
        pd.Series(model.feature_importances_, index=FEATURES)
        .sort_values(ascending=False)
    )

    print("\nFeature Importance:")
    print(importance.to_string())

    metrics = {
        "accuracy": float(accuracy),
        "roc_auc": float(auc) if auc is not None else None,
        "oob_accuracy": float(model.oob_score_),
        "fit_seconds": float(fit_seconds),
    }

    return model, metrics, importance.to_dict()


# ============================================================
# MAIN
# ============================================================

def train():
    overall_start = time.perf_counter()

    print("\n" + "=" * 70)
    print("REAL GIS + GSI LANDSLIDE ML TRAINING - V3 FAST NASA POWER")
    print("=" * 70)
    print("Real GSI inventory + real DEM + NASA POWER historical weather")
    print("No synthetic labels. No synthetic rainfall. No current-weather fallback.")

    load_dem_tiles()

    try:
        inventory = prepare_inventory(load_gsi_inventory())

        weather_by_group, weather_centers, weather_start, weather_end = (
            load_all_group_weather(inventory)
        )

        positive_df = build_positive_samples(
            inventory,
            weather_by_group,
        )

        if positive_df.empty:
            raise RuntimeError("No positive samples could be created.")

        negative_df = build_negative_samples(
            positive_df,
            weather_by_group,
            weather_centers,
        )

        if negative_df.empty:
            raise RuntimeError("No background samples could be created.")

        dataset = pd.concat(
            [positive_df, negative_df],
            ignore_index=True,
        )

        dataset = dataset.replace([np.inf, -np.inf], np.nan)
        dataset = dataset.dropna(subset=FEATURES + ["landslide"])
        dataset = dataset.drop_duplicates().reset_index(drop=True)

        print("\n" + "=" * 70)
        print("FINAL TRAINING DATASET")
        print("=" * 70)
        print(f"Rows: {len(dataset):,}")
        print("\nClass distribution:")
        print(dataset["landslide"].value_counts().sort_index().to_string())

        dataset_path = os.path.join(
            DATA_DIR,
            "landslide_training_dataset_v3_fast.csv",
        )
        dataset.to_csv(dataset_path, index=False)
        print(f"\nTraining dataset saved:\n{dataset_path}")

        model, metrics, feature_importance = train_model(dataset)

        package = {
            "model": model,
            "features": FEATURES,
            "version": "landslide-real-gis-v3-fast-nasa-power",
            "model_type": "RandomForestClassifier",
            "target": "landslide_susceptibility",
            "sources": [
                "GSI landslide inventory",
                "1 arc-second DEM GeoTIFF",
                "NASA POWER Daily Meteorology",
            ],
            "historical_weather_source": "NASA POWER",
            "historical_weather_parameters": [
                "T2M",
                "T2MDEW",
                "PRECTOTCORR",
            ],
            "weather_spatial_strategy": (
                "Real GSI weather-group centroid; one historical API request per group"
            ),
            "weather_training_start": weather_start,
            "weather_training_end": weather_end,
            "weather_group_count": int(len(weather_centers)),
            "weather_groups": weather_centers,
            "terrain_features": [
                "elevation",
                "slope_deg",
                "aspect_sin",
                "aspect_cos",
                "curvature",
                "terrain_roughness",
                "tpi",
            ],
            "weather_features": [
                "rain_1day",
                "rain_3day",
                "rain_7day",
                "rain_14day",
                "rain_30day",
                "precipitation_3day",
                "precipitation_7day",
                "temperature",
                "humidity",
            ],
            "training_date": datetime.utcnow().isoformat() + "Z",
            "total_samples": int(len(dataset)),
            "positive_samples": int((dataset["landslide"] == 1).sum()),
            "background_samples": int((dataset["landslide"] == 0).sum()),
            "training_samples": int(round(len(dataset) * 0.80)),
            "testing_samples": int(len(dataset) - round(len(dataset) * 0.80)),
            "n_estimators": N_ESTIMATORS,
            "metrics": metrics,
            "accuracy": metrics["accuracy"],
            "roc_auc": metrics["roc_auc"],
            "feature_importance": feature_importance,
            "notes": (
                "Fast real-data landslide model. Positive locations come from the "
                "GSI inventory. Background locations are non-inventory/background "
                "samples, not confirmed negatives. Terrain is extracted at each "
                "actual point from the supplied DEM. Historical weather comes from "
                "NASA POWER at a centroid computed from the real GSI weather group. "
                "No synthetic rainfall, no synthetic landslide labels, and no live "
                "weather fallback are used during training."
            ),
        }

        temp_model_path = MODEL_PATH + ".tmp"
        print("\nSaving landslide model...")
        with open(temp_model_path, "wb") as f:
            pickle.dump(
                package,
                f,
                protocol=pickle.HIGHEST_PROTOCOL,
            )
            f.flush()
            os.fsync(f.fileno())

        if os.path.getsize(temp_model_path) <= 0:
            raise RuntimeError("Temporary landslide model is empty.")

        os.replace(temp_model_path, MODEL_PATH)

        if os.path.getsize(MODEL_PATH) <= 0:
            raise RuntimeError("Final landslide model is empty.")

        elapsed = time.perf_counter() - overall_start

        print("\n" + "=" * 70)
        print("LANDSLIDE MODEL SAVED SUCCESSFULLY")
        print("=" * 70)
        print(f"Path           : {MODEL_PATH}")
        print(f"Model size     : {os.path.getsize(MODEL_PATH):,} bytes")
        print(f"Weather groups : {len(weather_centers)}")
        print(f"Total runtime  : {elapsed / 60.0:.2f} minutes")
        print("Weather source : NASA POWER")
        print("GIS source     : supplied GSI + DEM")
        print("=" * 70)

    finally:
        close_dem_tiles()


if __name__ == "__main__":
    train()
