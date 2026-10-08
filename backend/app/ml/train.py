"""
DISASTER INTELLIGENCE PLATFORM
REAL-DATA FLOOD ML TRAINING - V6.3 PRESENTATION FAST

PURPOSE
-------
Train the Uttarakhand flood-event classifier quickly enough for a
presentation/demo while keeping the training data real.

REAL DATA SOURCES
-----------------
1. India Flood Inventory (IFI) -> documented flood-event labels
2. NASA POWER Daily API -> historical daily meteorology

The final model uses only distinct weather features. The legacy rain_sum
alias is ignored/removed before training.

WHY THIS VERSION IS FAST
------------------------
- Does NOT call Copernicus CDS/ERA5 during the presentation run.
- Uses NASA POWER point time-series: only 13 district requests.
- The 13 requests run with at most 5 concurrent workers.
- Each district is cached independently, so a restart never repeats
  a successfully downloaded district.
- Training uses 400 Random Forest trees instead of 800.

LABEL POLICY
------------
HIGH:
    Only dates documented as flood-event dates in IFI.

LOW:
    Historical dates in the training period that have no IFI flood
    event record. LOW is a background/non-event label, not proof that
    a flood was impossible.

NO:
    Synthetic flood labels
    Synthetic rainfall
    Artificial MEDIUM class
    Live weather used as training labels

MODEL OUTPUT
------------
0 = LOW
1 = HIGH

IMPORTANT
---------
The live prediction endpoint can continue to use Open-Meteo live
weather. The trained model package keeps the same feature names so the
existing predictor can consume it without a feature-name change.
"""

import concurrent.futures
import json
import os
import pickle
import random
import re
import sys
import time
import warnings
from collections import Counter
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

import numpy as np
import pandas as pd
import requests

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

warnings.filterwarnings("ignore")


# ============================================================
# VERSION
# ============================================================

VERSION = "real-data-v6.3-fast-nasa-power"


# ============================================================
# GENERAL CONFIGURATION
# ============================================================

# NASA POWER Daily API documented coverage starts at 1981-01-01.
# IFI has earlier records, but this fast presentation build uses the
# common overlap that can be retrieved quickly and consistently.
TRAINING_START_YEAR = 1981
IFI_END_YEAR = 2023

# Do not use dates beyond the IFI training horizon.
TRAINING_START_DATE = date(TRAINING_START_YEAR, 1, 1)
TRAINING_END_DATE = date(IFI_END_YEAR, 12, 31)

WEATHER_AVAILABLE_END = TRAINING_END_DATE

RANDOM_STATE = 42

# 400 trees is materially faster than the previous 800-tree build while
# remaining a normal Random Forest model for a presentation build.
N_ESTIMATORS = 400

BACKGROUND_PER_HIGH = 6
MAX_BACKGROUND_RATIO = 6


# ============================================================
# HISTORICAL WEATHER WINDOW
# ============================================================

RAIN_LOOKBACK_DAYS = 30


# ============================================================
# NASA POWER CONFIGURATION
# ============================================================

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
NASA_POWER_COMMUNITY = "RE"
NASA_POWER_PARAMETERS = "T2M,T2MDEW,PRECTOTCORR"
NASA_POWER_FORMAT = "JSON"

# NASA's public documentation recommends no more than five concurrent
# point requests in its multi-point example. Keep that limit here.
NASA_MAX_WORKERS = 5
NASA_TIMEOUT = 90
NASA_RETRIES = 3
NASA_RETRY_BASE_SECONDS = 8


# ============================================================
# DATA QUALITY
# ============================================================

MIN_TOTAL_FLOOD_DAYS = 12
MIN_FLOOD_DISTRICTS = 3
MIN_EVENTS = 5
MIN_VALIDATION_HIGH = 5
MIN_TEST_HIGH = 5


# ============================================================
# THRESHOLD
# ============================================================

THRESHOLD_MIN = 0.05
THRESHOLD_MAX = 0.90
THRESHOLD_STEP = 0.01
MIN_PREFERRED_RECALL = 0.60


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Separate fast cache: existing ERA5 V6.3 cache is never deleted and
# never read by this script.
WEATHER_CACHE_DIR = os.path.join(
    DATA_DIR,
    "weather_cache_v6_3_nasa_power_fast",
)

TRAINING_FILE = os.path.join(
    DATA_DIR,
    "real_disaster_training_data_v6_3.csv",
)

AUDIT_FILE = os.path.join(
    DATA_DIR,
    "training_audit_v6_3.csv",
)

RUN_METADATA_FILE = os.path.join(
    DATA_DIR,
    "training_run_v6_3.json",
)

PROGRESS_FILE = os.path.join(
    DATA_DIR,
    "training_progress_v6_3_fast.json",
)

MODEL_FILE = os.path.join(
    BASE_DIR,
    "disaster_model_v6_3.pkl",
)

FLOOD_FILE = os.path.join(
    DATA_DIR,
    "India_Flood_Inventory_v6_3.csv",
)

os.makedirs(WEATHER_CACHE_DIR, exist_ok=True)


# ============================================================
# IFI SOURCE
# ============================================================

IFI_URL = (
    "https://zenodo.org/records/16994648/files/"
    "India_Flood_Inventory_v3.csv?download=1"
)


# ============================================================
# UTTARAKHAND DISTRICTS
# ============================================================

DISTRICTS = {
    "Almora": (29.5892, 79.6467),
    "Bageshwar": (29.8404, 79.7694),
    "Chamoli": (30.2937, 79.5603),
    "Champawat": (29.3209, 80.0088),
    "Dehradun": (30.3165, 78.0322),
    "Haridwar": (29.9457, 78.1642),
    "Nainital": (29.3919, 79.4542),
    "Pauri Garhwal": (29.8688, 78.8383),
    "Pithoragarh": (29.5829, 80.2182),
    "Rudraprayag": (30.2844, 78.9811),
    "Tehri Garhwal": (30.3012, 78.5661),
    "Udham Singh Nagar": (28.9610, 79.5154),
    "Uttarkashi": (30.7268, 78.4354),
}


# ============================================================
# DISTRICT ALIASES
# ============================================================

DISTRICT_ALIASES = {
    "almora": "Almora",
    "bageshwar": "Bageshwar",
    "chamoli": "Chamoli",
    "champawat": "Champawat",
    "dehradun": "Dehradun",
    "dehra dun": "Dehradun",
    "haridwar": "Haridwar",
    "hardwar": "Haridwar",
    "nainital": "Nainital",
    "pauri": "Pauri Garhwal",
    "pauri garhwal": "Pauri Garhwal",
    "garhwal": "Pauri Garhwal",
    "pithoragarh": "Pithoragarh",
    "rudraprayag": "Rudraprayag",
    "rudra prayag": "Rudraprayag",
    "tehri": "Tehri Garhwal",
    "tehri garhwal": "Tehri Garhwal",
    "udham singh nagar": "Udham Singh Nagar",
    "udam singh nagar": "Udham Singh Nagar",
    "udhamsinghnagar": "Udham Singh Nagar",
    "us nagar": "Udham Singh Nagar",
    "u s nagar": "Udham Singh Nagar",
    "uttarkashi": "Uttarkashi",
    "uttar kashi": "Uttarkashi",
    "uttar kashi kashi": "Uttarkashi",
}


# ============================================================
# FEATURES
# ============================================================

FEATURES = [
    "temperature_2m_mean",
    "relative_humidity_2m_mean",
    "precipitation_sum",
    "rain_3day",
    "rain_7day",
    "rain_14day",
    "rain_30day",
    "rain_intensity_3day",
]


# ============================================================
# LABELS
# ============================================================

DATASET_LOW = 0
DATASET_HIGH = 2
MODEL_LOW = 0
MODEL_HIGH = 1


# ============================================================
# PRINT HELPERS
# ============================================================

def header(text):
    print()
    print("=" * 80)
    print(text)
    print("=" * 80)


# ============================================================
# TEXT HELPERS
# ============================================================

def _clean_name(text):
    text = str(text).strip().lower()
    text = re.sub(r"[\-_.]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+district$", "", text).strip()
    return text


def _split_districts(value):
    if pd.isna(value):
        return []
    return [
        part
        for part in re.split(r"[,;/]|\band\b", str(value), flags=re.IGNORECASE)
        if part.strip()
    ]


def normalize_districts(value):
    found = []
    for part in _split_districts(value):
        name = DISTRICT_ALIASES.get(_clean_name(part))
        if name and name not in found:
            found.append(name)
    return found


def normalize_district(value):
    if pd.isna(value):
        return None

    text = _clean_name(value)
    if text in DISTRICT_ALIASES:
        return DISTRICT_ALIASES[text]

    for alias, canonical in DISTRICT_ALIASES.items():
        if alias in text:
            return canonical

    return None


# ============================================================
# HTTP SESSION
# ============================================================

def create_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Disaster-Intelligence-Platform/6.3-fast",
        "Accept": "application/json",
        "Connection": "keep-alive",
    })
    return session


# ============================================================
# PROGRESS
# ============================================================

def empty_progress():
    return {
        "version": VERSION,
        "completed_districts": [],
        "failed_districts": [],
        "last_update": None,
    }


def load_progress():
    if not os.path.exists(PROGRESS_FILE):
        return empty_progress()

    try:
        with open(PROGRESS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if data.get("version") != VERSION:
            return empty_progress()

        return data
    except Exception:
        return empty_progress()


def save_progress(progress):
    progress["last_update"] = datetime.now().isoformat()
    temp_path = PROGRESS_FILE + ".tmp"

    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(progress, file, indent=2)

    os.replace(temp_path, PROGRESS_FILE)


# ============================================================
# IFI DOWNLOAD
# ============================================================

def download_ifi():
    if os.path.exists(FLOOD_FILE):
        print("\nUsing existing IFI file:")
        print(FLOOD_FILE)
        return pd.read_csv(FLOOD_FILE)

    header("DOWNLOADING IFI DATA")
    session = create_session()

    response = session.get(
        IFI_URL,
        timeout=180,
    )
    response.raise_for_status()

    with open(FLOOD_FILE, "wb") as file:
        file.write(response.content)

    print("IFI download complete.")
    return pd.read_csv(FLOOD_FILE)


# ============================================================
# IFI DATE PREPARATION
# ============================================================

def _parse_ifi_date(series):
    parsed = pd.to_datetime(
        series,
        format="%d-%m-%Y %H:%M",
        errors="coerce",
    )
    fallback = pd.to_datetime(
        series,
        dayfirst=True,
        errors="coerce",
    )
    return parsed.fillna(fallback).dt.normalize()


def prepare_flood_data(df):
    header("PREPARING IFI FLOOD DATA")

    for column in ["Start Date", "End Date", "Districts", "State"]:
        if column not in df.columns:
            raise RuntimeError(f"Missing IFI column: {column}")

    df = df.copy()

    df["start_date"] = _parse_ifi_date(df["Start Date"])
    df["end_date"] = _parse_ifi_date(df["End Date"]).fillna(df["start_date"])

    invalid = df["end_date"] < df["start_date"]
    df.loc[invalid, "end_date"] = df.loc[invalid, "start_date"]

    # Uttarakhand events only.
    is_uk = df["State"].astype(str).str.contains(
        "uttarakhand|uttaranchal",
        case=False,
        na=False,
    )
    df = df[is_uk].copy()

    print(f"IFI rows with State = Uttarakhand: {len(df)}")

    no_district = (
        df["Districts"].isna()
        | (df["Districts"].astype(str).str.strip() == "")
    )
    print(f"Rows with no district listed: {int(no_district.sum())}")

    unmatched = Counter()
    for value in df["Districts"].dropna():
        for part in _split_districts(value):
            cleaned = _clean_name(part)
            if cleaned and cleaned not in DISTRICT_ALIASES:
                unmatched[cleaned] += 1

    if unmatched:
        print("\nUnmatched district names (top 20):")
        for name, count in unmatched.most_common(20):
            print(f"  {name}: {count}")

    df["district"] = df["Districts"].apply(normalize_districts)
    df = df.explode("district")
    df = df.dropna(subset=["start_date", "end_date", "district"])
    df = df[df["district"].isin(DISTRICTS.keys())].copy()

    # Only the period for which the fast weather source is available and
    # the IFI labels are still within the dataset's historical coverage.
    df = df[df["end_date"] >= pd.Timestamp(TRAINING_START_DATE)].copy()
    df = df[df["start_date"] <= pd.Timestamp(TRAINING_END_DATE)].copy()

    df["start_date"] = df["start_date"].clip(
        lower=pd.Timestamp(TRAINING_START_DATE),
        upper=pd.Timestamp(TRAINING_END_DATE),
    )
    df["end_date"] = df["end_date"].clip(
        lower=pd.Timestamp(TRAINING_START_DATE),
        upper=pd.Timestamp(TRAINING_END_DATE),
    )

    df = df.sort_values(
        ["start_date", "end_date", "district"]
    ).reset_index(drop=True)

    print(f"\nMatched IFI rows in {TRAINING_START_YEAR}-{IFI_END_YEAR}: {len(df)}")
    print("\nDistrict distribution:")
    print(df["district"].value_counts().to_string())

    missing_districts = [
        district
        for district in DISTRICTS
        if district not in set(df["district"].dropna().unique())
    ]
    if missing_districts:
        print("\nWARNING: no matched IFI records for:")
        print(missing_districts)
    else:
        print("\nIFI district coverage check: all 13 districts matched.")

    if df.empty:
        raise RuntimeError("No Uttarakhand IFI records found in the fast training period.")

    return df


# ============================================================
# NASA POWER CACHE
# ============================================================

def weather_cache_path(district):
    safe = re.sub(r"[^A-Za-z0-9]+", "_", district).strip("_").lower()
    return os.path.join(
        WEATHER_CACHE_DIR,
        f"{safe}_{TRAINING_START_YEAR}_{IFI_END_YEAR}.json",
    )


def valid_weather_cache(district):
    path = weather_cache_path(district)

    if not os.path.exists(path):
        return False

    try:
        with open(path, "r", encoding="utf-8") as file:
            payload = json.load(file)

        if payload.get("version") != VERSION:
            return False

        if payload.get("district") != district:
            return False

        records = payload.get("records", [])
        if not records:
            return False

        required = {
            "district",
            "date",
            "temperature_2m_mean",
            "relative_humidity_2m_mean",
            "precipitation_sum",
        }

        if not required.issubset(records[0]):
            return False

        dates = pd.to_datetime(
            [record.get("date") for record in records],
            errors="coerce",
        )

        if dates.isna().all():
            return False

        expected_last = pd.Timestamp(TRAINING_END_DATE)
        if dates.max() < expected_last:
            return False

        return True
    except Exception:
        return False


def save_weather_cache(district, weather):
    output = weather.copy()
    output["date"] = pd.to_datetime(output["date"]).dt.strftime("%Y-%m-%d")

    payload = {
        "version": VERSION,
        "district": district,
        "latitude": DISTRICTS[district][0],
        "longitude": DISTRICTS[district][1],
        "source": "NASA POWER Daily API",
        "parameters": ["T2M", "T2MDEW", "PRECTOTCORR"],
        "start": TRAINING_START_DATE.isoformat(),
        "end": TRAINING_END_DATE.isoformat(),
        "created_at": datetime.now().isoformat(),
        "records": output.to_dict(orient="records"),
    }

    path = weather_cache_path(district)
    temp_path = path + ".tmp"

    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, separators=(",", ":"))

    os.replace(temp_path, path)


def load_weather_cache(district):
    path = weather_cache_path(district)
    with open(path, "r", encoding="utf-8") as file:
        payload = json.load(file)

    df = pd.DataFrame(payload["records"])
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()

    for column in [
        "temperature_2m_mean",
        "relative_humidity_2m_mean",
        "precipitation_sum",
    ]:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    # Compatibility with caches created by the earlier fast build.
    # The legacy rain_sum field was only a duplicate alias of precipitation_sum
    # and is never used by the final model.
    if "rain_sum" in df.columns:
        df = df.drop(columns=["rain_sum"])

    return df


# ============================================================
# NASA POWER RESPONSE PARSER
# ============================================================

def _extract_power_parameter_block(payload):
    properties = payload.get("properties", {})
    parameters = properties.get("parameter", {})

    if not isinstance(parameters, dict):
        raise RuntimeError("NASA POWER response has no parameter object.")

    return parameters


def _parse_power_json(district, payload):
    parameters = _extract_power_parameter_block(payload)

    def get_parameter(name):
        value = parameters.get(name)
        if value is None:
            normalized = {
                re.sub(r"[^a-z0-9]", "", str(key).lower()): key
                for key in parameters
            }
            candidate_key = re.sub(r"[^a-z0-9]", "", name.lower())
            original = normalized.get(candidate_key)
            if original is not None:
                value = parameters[original]

        if not isinstance(value, dict):
            raise RuntimeError(
                f"NASA POWER response missing parameter {name}. "
                f"Available: {list(parameters)}"
            )
        return value

    temp_map = get_parameter("T2M")
    dew_map = get_parameter("T2MDEW")
    rain_map = get_parameter("PRECTOTCORR")

    all_dates = sorted(
        set(temp_map) & set(dew_map) & set(rain_map)
    )

    if not all_dates:
        raise RuntimeError(f"NASA POWER returned no overlapping dates for {district}.")

    rows = []

    # NASA POWER daily T2M and T2MDEW are in degrees C for the daily
    # meteorological product; precipitation is daily accumulated mm/day.
    # RH is derived only from these real retrieved temperature values.
    a = 17.625
    b = 243.04

    for stamp in all_dates:
        temp = float(temp_map[stamp]) if temp_map[stamp] is not None else np.nan
        dew = float(dew_map[stamp]) if dew_map[stamp] is not None else np.nan
        precip = float(rain_map[stamp]) if rain_map[stamp] is not None else np.nan

        # POWER uses -999 as its standard missing-data sentinel in many
        # formatted responses.
        if temp <= -998 or dew <= -998 or precip <= -998:
            temp = np.nan if temp <= -998 else temp
            dew = np.nan if dew <= -998 else dew
            precip = np.nan if precip <= -998 else precip

        if np.isfinite(temp) and np.isfinite(dew):
            gamma_t = (a * temp) / (b + temp)
            gamma_td = (a * dew) / (b + dew)
            rh = 100.0 * np.exp(gamma_td - gamma_t)
            rh = float(np.clip(rh, 0.0, 100.0))
        else:
            rh = np.nan

        rows.append({
            "district": district,
            "date": pd.to_datetime(stamp, format="%Y%m%d", errors="coerce"),
            "temperature_2m_mean": temp,
            "relative_humidity_2m_mean": rh,
            "precipitation_sum": precip,
        })

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["date"]).copy()
    df = df[
        (df["date"] >= pd.Timestamp(TRAINING_START_DATE))
        & (df["date"] <= pd.Timestamp(TRAINING_END_DATE))
    ].copy()

    df = (
        df.sort_values("date")
        .drop_duplicates(["district", "date"])
        .reset_index(drop=True)
    )

    if len(df) < 300:
        raise RuntimeError(
            f"NASA POWER returned too few daily rows for {district}: {len(df)}"
        )

    return df


# ============================================================
# NASA POWER REQUEST
# ============================================================

def _build_power_url(district):
    lat, lon = DISTRICTS[district]
    params = {
        "parameters": NASA_POWER_PARAMETERS,
        "community": NASA_POWER_COMMUNITY,
        "longitude": f"{lon:.4f}",
        "latitude": f"{lat:.4f}",
        "start": TRAINING_START_DATE.strftime("%Y%m%d"),
        "end": TRAINING_END_DATE.strftime("%Y%m%d"),
        "format": NASA_POWER_FORMAT,
    }
    return f"{NASA_POWER_URL}?{urlencode(params)}"


def fetch_nasa_power_district(district):
    if valid_weather_cache(district):
        print(f"CACHE HIT: {district}")
        return load_weather_cache(district)

    url = _build_power_url(district)
    last_error = None

    for attempt in range(1, NASA_RETRIES + 1):
        try:
            print(f"NASA POWER request: {district} ({attempt}/{NASA_RETRIES})")

            session = create_session()
            response = session.get(
                url,
                timeout=NASA_TIMEOUT,
                verify=True,
            )

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait = min(float(retry_after), 60.0)
                    except ValueError:
                        wait = NASA_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
                else:
                    wait = NASA_RETRY_BASE_SECONDS * (2 ** (attempt - 1))

                print(f"RATE LIMITED: {district} -> waiting {wait:.0f}s")
                time.sleep(wait)
                continue

            response.raise_for_status()
            payload = response.json()
            weather = _parse_power_json(district, payload)
            save_weather_cache(district, weather)

            print(f"COMPLETE: {district} | rows={len(weather)}")
            return weather

        except Exception as error:
            last_error = error

            if attempt >= NASA_RETRIES:
                break

            wait = NASA_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
            print(f"NASA POWER retry for {district}: {error}")
            print(f"Waiting {wait}s...")
            time.sleep(wait)

    raise RuntimeError(f"NASA POWER failed for {district}: {last_error}")


# ============================================================
# FETCH ALL WEATHER
# ============================================================

def fetch_weather():
    header("V6.3 FAST HISTORICAL WEATHER - NASA POWER")

    print(f"Period: {TRAINING_START_DATE} -> {TRAINING_END_DATE}")
    print(f"Districts: {len(DISTRICTS)}")
    print(f"Max concurrent requests: {NASA_MAX_WORKERS}")
    print("Existing ERA5 V6.3 cache is NOT deleted and is NOT read.")
    print(f"New cache: {WEATHER_CACHE_DIR}")

    progress = load_progress()
    completed = set(progress.get("completed_districts", []))
    frames = []

    cached = []
    missing = []

    for district in DISTRICTS:
        if valid_weather_cache(district):
            cached.append(district)
            completed.add(district)
            frames.append(load_weather_cache(district))
        else:
            missing.append(district)

    progress["completed_districts"] = sorted(completed)
    save_progress(progress)

    print(f"\nCached districts: {len(cached)}")
    print(cached if cached else "None")

    print(f"\nMissing districts: {len(missing)}")
    print(missing if missing else "None")

    if missing:
        print("\nDownloading missing districts in parallel (max 5 at once)...")

        successful = []
        failures = []

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=NASA_MAX_WORKERS
        ) as executor:
            future_map = {
                executor.submit(fetch_nasa_power_district, district): district
                for district in missing
            }

            for future in concurrent.futures.as_completed(future_map):
                district = future_map[future]

                try:
                    weather = future.result()
                    frames.append(weather)
                    successful.append(district)
                    completed.add(district)
                except Exception as error:
                    failures.append((district, str(error)))

                progress["completed_districts"] = sorted(completed)
                progress["failed_districts"] = sorted(
                    {name for name, _ in failures}
                )
                save_progress(progress)

        if failures:
            print("\nFailed districts:")
            for district, error in failures:
                print(f"  {district}: {error}")
            raise RuntimeError("Fast weather download did not finish for all districts.")

        print(f"\nDownloaded this run: {len(successful)} districts")

    if len(frames) != len(DISTRICTS):
        raise RuntimeError(
            f"Expected weather for {len(DISTRICTS)} districts but loaded {len(frames)}."
        )

    weather = pd.concat(frames, ignore_index=True)
    weather["date"] = pd.to_datetime(weather["date"], errors="coerce").dt.normalize()

    required = {
        "district",
        "date",
        "temperature_2m_mean",
        "relative_humidity_2m_mean",
        "precipitation_sum",
    }
    if not required.issubset(weather.columns):
        raise RuntimeError(
            f"Weather data missing columns: {sorted(required - set(weather.columns))}"
        )

    weather = (
        weather.dropna(subset=["district", "date"])
        .sort_values(["district", "date"])
        .drop_duplicates(["district", "date"])
        .reset_index(drop=True)
    )

    missing_districts = set(DISTRICTS) - set(weather["district"].unique())
    if missing_districts:
        raise RuntimeError(
            f"Missing weather districts: {sorted(missing_districts)}"
        )

    print(f"\nTotal weather rows: {len(weather)}")
    return weather


# ============================================================
# EVENT DATES
# ============================================================

def expand_event_dates(events):
    dates = set()

    for _, event in events.iterrows():
        current = max(
            event["start_date"],
            pd.Timestamp(TRAINING_START_DATE),
        )
        end = min(
            event["end_date"],
            pd.Timestamp(TRAINING_END_DATE),
        )

        while current <= end:
            dates.add(current.normalize())
            current += timedelta(days=1)

    return dates


# ============================================================
# RAIN FEATURES
# ============================================================

def add_rain_features(weather):
    pieces = []

    for district, group in weather.groupby("district"):
        group = (
            group.sort_values("date")
            .set_index("date")
        )

        full_range = pd.date_range(
            group.index.min(),
            group.index.max(),
            freq="D",
        )
        group = group.reindex(full_range)
        group["district"] = district

        precip = pd.to_numeric(
            group["precipitation_sum"],
            errors="coerce",
        )

        group["rain_3day"] = precip.rolling(
            3, min_periods=3
        ).sum()
        group["rain_7day"] = precip.rolling(
            7, min_periods=7
        ).sum()
        group["rain_14day"] = precip.rolling(
            14, min_periods=14
        ).sum()
        group["rain_30day"] = precip.rolling(
            30, min_periods=30
        ).sum()
        group["rain_intensity_3day"] = precip.rolling(
            3, min_periods=3
        ).mean()

        group.index.name = "date"
        pieces.append(group.reset_index())

    df = pd.concat(pieces, ignore_index=True)

    # Reindexed gap rows are never allowed to become training data.
    df = df.dropna(subset=["precipitation_sum"]).reset_index(drop=True)
    return df


# ============================================================
# BUILD DATASET
# ============================================================

def build_dataset(flood_df, weather):
    header("BUILDING V6.3 FAST DATASET")

    weather = add_rain_features(weather)
    weather = weather[
        (weather["date"] >= pd.Timestamp(TRAINING_START_DATE))
        & (weather["date"] <= pd.Timestamp(TRAINING_END_DATE))
    ].copy()

    parts = []
    audits = []

    for district in DISTRICTS:
        print(f"\nProcessing: {district}")

        events = flood_df[
            flood_df["district"] == district
        ].copy()

        district_weather = weather[
            weather["district"] == district
        ].copy()

        if district_weather.empty:
            print("No weather data.")
            continue

        flood_dates = expand_event_dates(events)

        district_weather["risk"] = (
            district_weather["date"]
            .isin(flood_dates)
            .astype(int)
            .map({0: DATASET_LOW, 1: DATASET_HIGH})
        )

        high = district_weather[
            district_weather["risk"] == DATASET_HIGH
        ].copy()
        low = district_weather[
            district_weather["risk"] == DATASET_LOW
        ].copy()

        high = high.dropna(subset=FEATURES)
        low = low.dropna(subset=FEATURES)

        desired_low = max(len(high) * BACKGROUND_PER_HIGH, 60)
        maximum_low = min(
            desired_low,
            len(low),
            len(high) * MAX_BACKGROUND_RATIO,
        )
        maximum_low = int(maximum_low)

        if len(low) > maximum_low and maximum_low > 0:
            low = low.sort_values("date")
            positions = np.linspace(
                0,
                len(low) - 1,
                num=maximum_low,
                dtype=int,
            )
            low = low.iloc[np.unique(positions)].copy()

        print(f"IFI events: {len(events)}")
        print(f"Flood days: {len(flood_dates)}")
        print(f"HIGH rows: {len(high)}")
        print(f"LOW rows: {len(low)}")

        audits.append({
            "district": district,
            "ifi_events": len(events),
            "flood_days": len(flood_dates),
            "high_rows": len(high),
            "low_rows": len(low),
            "weather_rows": len(district_weather),
            "weather_start": str(district_weather["date"].min().date()),
            "weather_end": str(district_weather["date"].max().date()),
        })

        if high.empty or low.empty:
            continue

        parts.append(
            pd.concat([high, low], ignore_index=True)
        )

    if not parts:
        raise RuntimeError("No usable training data.")

    dataset = pd.concat(parts, ignore_index=True)
    dataset["date"] = pd.to_datetime(dataset["date"], errors="coerce").dt.normalize()

    dataset = (
        dataset.drop_duplicates(["district", "date"])
        .sort_values(["date", "district"])
        .reset_index(drop=True)
    )

    pd.DataFrame(audits).to_csv(AUDIT_FILE, index=False)
    dataset.to_csv(TRAINING_FILE, index=False)

    print(f"\nDataset saved: {TRAINING_FILE}")
    return dataset


# ============================================================
# PREPARE DATASET
# ============================================================

def prepare_dataset(dataset):
    df = dataset.copy()

    # Remove the legacy duplicate precipitation alias from old/intermediate
    # datasets before writing the final training CSV or fitting the model.
    if "rain_sum" in df.columns:
        df = df.drop(columns=["rain_sum"])

    for feature in FEATURES:
        df[feature] = pd.to_numeric(df[feature], errors="coerce")

    df["risk"] = pd.to_numeric(df["risk"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    df = df.dropna(
        subset=FEATURES + ["risk", "date"]
    )

    df["risk"] = df["risk"].astype(int)
    df = df[df["risk"].isin([DATASET_LOW, DATASET_HIGH])].copy()

    return df


# ============================================================
# DATA QUALITY
# ============================================================

def validate_dataset(dataset, flood_df):
    header("V6.3 FAST DATA QUALITY")

    high = dataset[dataset["risk"] == DATASET_HIGH]
    low = dataset[dataset["risk"] == DATASET_LOW]

    events = len(
        flood_df[["district", "start_date", "end_date"]]
        .drop_duplicates()
    )

    print(f"Total rows: {len(dataset)}")
    print(f"HIGH rows: {len(high)}")
    print(f"LOW rows: {len(low)}")
    print(f"HIGH districts: {high['district'].nunique()}")
    print(f"IFI events: {events}")

    if len(high) < MIN_TOTAL_FLOOD_DAYS:
        raise RuntimeError("Too few HIGH samples.")

    if high["district"].nunique() < MIN_FLOOD_DISTRICTS:
        raise RuntimeError("Too few HIGH districts.")

    if events < MIN_EVENTS:
        raise RuntimeError("Too few IFI events.")

    if low.empty:
        raise RuntimeError("No LOW samples.")

    duplicates = dataset.duplicated(["district", "date"]).sum()
    if duplicates:
        raise RuntimeError(f"{duplicates} duplicate rows.")

    if "rain_sum" in FEATURES:
        raise RuntimeError("Invalid feature configuration: rain_sum duplicates precipitation_sum.")

    print("\nDATA QUALITY PASSED")


# ============================================================
# CHRONOLOGICAL SPLIT
# ============================================================

def split_data(dataset):
    header("CHRONOLOGICAL SPLIT")

    df = (
        dataset.sort_values(["date", "district"])
        .reset_index(drop=True)
    )

    dates = (
        df["date"]
        .drop_duplicates()
        .sort_values()
        .reset_index(drop=True)
    )

    if len(dates) < 60:
        raise RuntimeError("Too few unique dates.")

    train_index = max(1, int(len(dates) * 0.65))
    validation_index = max(
        train_index + 1,
        int(len(dates) * 0.825),
    )

    if validation_index >= len(dates):
        validation_index = len(dates) - 1

    train_end = dates.iloc[train_index - 1]
    validation_end = dates.iloc[validation_index - 1]

    train = df[df["date"] <= train_end].copy()
    validation = df[
        (df["date"] > train_end)
        & (df["date"] <= validation_end)
    ].copy()
    test = df[df["date"] > validation_end].copy()

    train_high = int((train["risk"] == DATASET_HIGH).sum())
    validation_high = int((validation["risk"] == DATASET_HIGH).sum())
    test_high = int((test["risk"] == DATASET_HIGH).sum())

    print(f"\nTRAIN: {train['date'].min()} -> {train['date'].max()} | rows={len(train)} | HIGH={train_high}")
    print(f"VALIDATION: {validation['date'].min()} -> {validation['date'].max()} | rows={len(validation)} | HIGH={validation_high}")
    print(f"TEST: {test['date'].min()} -> {test['date'].max()} | rows={len(test)} | HIGH={test_high}")

    if train["risk"].nunique() < 2:
        raise RuntimeError("Training has only one class.")
    if train_high < 5:
        raise RuntimeError("Too few training HIGH samples.")
    if validation_high < MIN_VALIDATION_HIGH:
        raise RuntimeError("Too few validation HIGH samples.")
    if test_high < MIN_TEST_HIGH:
        raise RuntimeError("Too few test HIGH samples.")

    return train, validation, test


# ============================================================
# PROBABILITY / THRESHOLD
# ============================================================

def get_high_probability(model, X):
    probabilities = model.predict_proba(X)
    classes = list(model.classes_)

    if MODEL_HIGH not in classes:
        raise RuntimeError("Model does not contain HIGH class.")

    return probabilities[:, classes.index(MODEL_HIGH)]


def select_threshold(y, probabilities):
    header("VALIDATION THRESHOLD")

    rows = []

    for threshold in np.arange(
        THRESHOLD_MIN,
        THRESHOLD_MAX + 0.0001,
        THRESHOLD_STEP,
    ):
        predictions = (probabilities >= threshold).astype(int)

        rows.append({
            "threshold": threshold,
            "precision": precision_score(
                y, predictions, zero_division=0
            ),
            "recall": recall_score(
                y, predictions, zero_division=0
            ),
            "f1": f1_score(
                y, predictions, zero_division=0
            ),
        })

    scores = pd.DataFrame(rows)
    preferred = scores[scores["recall"] >= MIN_PREFERRED_RECALL]

    if not preferred.empty:
        best = (
            preferred.sort_values(
                ["f1", "precision", "threshold"],
                ascending=[False, False, True],
            ).iloc[0]
        )
    else:
        best = (
            scores.sort_values(
                ["f1", "recall", "precision"],
                ascending=[False, False, False],
            ).iloc[0]
        )

    threshold = float(best["threshold"])

    print(f"Selected threshold: {threshold:.2f}")
    print(f"Precision: {best['precision']:.4f}")
    print(f"Recall: {best['recall']:.4f}")
    print(f"F1: {best['f1']:.4f}")

    return threshold


# ============================================================
# EVALUATION
# ============================================================

def evaluate(name, model, dataset, threshold):
    header(name)

    X = dataset[FEATURES]
    y = (dataset["risk"] == DATASET_HIGH).astype(int)

    probabilities = get_high_probability(model, X)
    predictions = (probabilities >= threshold).astype(int)

    accuracy = accuracy_score(y, predictions)
    precision = precision_score(y, predictions, zero_division=0)
    recall = recall_score(y, predictions, zero_division=0)
    f1 = f1_score(y, predictions, zero_division=0)

    try:
        roc_auc = roc_auc_score(y, probabilities)
    except Exception:
        roc_auc = None

    try:
        pr_auc = average_precision_score(y, probabilities)
    except Exception:
        pr_auc = None

    print(f"Accuracy : {accuracy:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall   : {recall:.4f}")
    print(f"F1       : {f1:.4f}")
    print(f"PR-AUC   : {pr_auc}")
    print(f"ROC-AUC  : {roc_auc}")

    print("\nClassification Report:")
    print(
        classification_report(
            y,
            predictions,
            target_names=["LOW", "HIGH"],
            zero_division=0,
        )
    )

    cm = confusion_matrix(y, predictions, labels=[0, 1])
    print("Confusion Matrix:")
    print(cm)

    return {
        "accuracy": float(accuracy),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "pr_auc": None if pr_auc is None else float(pr_auc),
        "roc_auc": None if roc_auc is None else float(roc_auc),
        "threshold": float(threshold),
        "samples": int(len(dataset)),
        "high_samples": int(y.sum()),
        "low_samples": int((y == 0).sum()),
        "confusion_matrix": cm.tolist(),
    }


# ============================================================
# TRAIN MODEL
# ============================================================

def train_model(train, validation, test):
    header("TRAINING V6.3 FAST RANDOM FOREST")

    X_train = train[FEATURES]
    y_train = (
        train["risk"] == DATASET_HIGH
    ).astype(int)

    X_validation = validation[FEATURES]
    y_validation = (
        validation["risk"] == DATASET_HIGH
    ).astype(int)

    print(f"Training rows: {len(train)}")
    print(f"Validation rows: {len(validation)}")
    print(f"Test rows: {len(test)}")
    print(f"Random Forest trees: {N_ESTIMATORS}")

    model = RandomForestClassifier(
        n_estimators=N_ESTIMATORS,
        max_depth=14,
        min_samples_split=4,
        min_samples_leaf=2,
        max_features="sqrt",
        class_weight="balanced_subsample",
        bootstrap=True,
        oob_score=True,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )

    print("\nFitting model...")
    model.fit(X_train, y_train)

    probabilities = get_high_probability(model, X_validation)
    threshold = select_threshold(y_validation, probabilities)

    validation_metrics = evaluate(
        "V6.3 FAST VALIDATION",
        model,
        validation,
        threshold,
    )

    test_metrics = evaluate(
        "V6.3 FAST FINAL TEST",
        model,
        test,
        threshold,
    )

    print(f"\nOOB Accuracy: {model.oob_score_:.4f}")

    importance = (
        pd.Series(
            model.feature_importances_,
            index=FEATURES,
        )
        .sort_values(ascending=False)
    )

    print("\nFEATURE IMPORTANCE:")
    print(importance.to_string())

    package = {
        "model": model,
        "features": FEATURES,
        "version": VERSION,
        "threshold": threshold,
        "model_output_classes": {
            0: "LOW",
            1: "HIGH",
        },
        "dataset_classes": {
            0: "LOW",
            2: "HIGH",
        },
        "trained_at": datetime.now().isoformat(),
        "training_start": train["date"].min().date().isoformat(),
        "training_end": train["date"].max().date().isoformat(),
        "validation_start": validation["date"].min().date().isoformat(),
        "validation_end": validation["date"].max().date().isoformat(),
        "test_start": test["date"].min().date().isoformat(),
        "test_end": test["date"].max().date().isoformat(),
        "data_sources": [
            "India Flood Inventory",
            "NASA POWER Daily Meteorology",
        ],
        "historical_weather_model": "NASA POWER",
        "weather_parameters": ["T2M", "T2MDEW", "PRECTOTCORR"],
        "training_config": {
            "n_estimators": N_ESTIMATORS,
            "max_depth": 14,
            "min_samples_split": 4,
            "min_samples_leaf": 2,
            "max_features": "sqrt",
            "class_weight": "balanced_subsample",
            "random_state": RANDOM_STATE,
        },
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "oob_accuracy": float(model.oob_score_),
        "feature_importance": {
            str(key): float(value)
            for key, value in importance.items()
        },
        "notes": (
            "Fast real-data flood-event classifier. HIGH is only a documented "
            "IFI flood-event date. LOW means no documented IFI event in the "
            "training inventory and is not proof that flooding was impossible. "
            "Historical weather comes from NASA POWER Daily Meteorology. "
            "No synthetic labels, no synthetic rainfall, no artificial MEDIUM "
            "class, and live weather is not used as a training label. The live "
            "prediction endpoint should remain responsible for current weather."
        ),
        "presentation_fast_build": True,
        "distinct_precipitation_features_only": True,
        "district_aliases_fixed": [
            "udam singh nagar -> Udham Singh Nagar",
            "uttar kashi kashi -> Uttarkashi",
        ],
        "previous_era5_cache_reused": False,
        "previous_era5_cache_deleted": False,
    }

    with open(MODEL_FILE, "wb") as file:
        pickle.dump(
            package,
            file,
            protocol=pickle.HIGHEST_PROTOCOL,
        )

    print("\n" + "=" * 80)
    print("V6.3 FAST MODEL SAVED")
    print("=" * 80)
    print(MODEL_FILE)

    return model, threshold, test_metrics


# ============================================================
# MAIN
# ============================================================

def main():
    started = time.perf_counter()

    header("DISASTER INTELLIGENCE PLATFORM - V6.3 PRESENTATION FAST")

    print("\nREAL-DATA FAST BUILD")
    print("Historical labels : India Flood Inventory")
    print("Historical weather: NASA POWER Daily API")
    print(f"Training period   : {TRAINING_START_YEAR}-{IFI_END_YEAR}")
    print(f"Districts         : {len(DISTRICTS)}")
    print(f"RF estimators     : {N_ESTIMATORS}")
    print("\nImportant: existing ERA5 V6.3 cache is preserved and not read.")

    # --------------------------------------------------------
    # IFI
    # --------------------------------------------------------
    flood_df = download_ifi()
    flood_df = prepare_flood_data(flood_df)

    # --------------------------------------------------------
    # WEATHER
    # --------------------------------------------------------
    weather = fetch_weather()

    # --------------------------------------------------------
    # DATASET
    # --------------------------------------------------------
    dataset = build_dataset(flood_df, weather)
    dataset = prepare_dataset(dataset)

    dataset.to_csv(TRAINING_FILE, index=False)

    # --------------------------------------------------------
    # QUALITY
    # --------------------------------------------------------
    validate_dataset(dataset, flood_df)

    # --------------------------------------------------------
    # SPLIT
    # --------------------------------------------------------
    train, validation, test = split_data(dataset)

    # --------------------------------------------------------
    # TRAIN
    # --------------------------------------------------------
    model, threshold, metrics = train_model(
        train,
        validation,
        test,
    )

    # --------------------------------------------------------
    # METADATA
    # --------------------------------------------------------
    elapsed = time.perf_counter() - started

    metadata = {
        "version": VERSION,
        "completed_at": datetime.now().isoformat(),
        "elapsed_seconds": float(elapsed),
        "elapsed_minutes": float(elapsed / 60.0),
        "weather_start": TRAINING_START_DATE.isoformat(),
        "weather_end": TRAINING_END_DATE.isoformat(),
        "dataset_rows": int(len(dataset)),
        "high_rows": int((dataset["risk"] == DATASET_HIGH).sum()),
        "low_rows": int((dataset["risk"] == DATASET_LOW).sum()),
        "threshold": float(threshold),
        "test_metrics": metrics,
        "live_weather_used_as_label": False,
        "synthetic_labels_used": False,
        "synthetic_rainfall_used": False,
        "artificial_medium_class_used": False,
        "district_count": len(DISTRICTS),
        "districts": list(DISTRICTS.keys()),
        "feature_count": len(FEATURES),
        "features": FEATURES,
        "ifi_coverage_used": f"{TRAINING_START_YEAR}-{IFI_END_YEAR}",
        "historical_weather_model": "NASA POWER",
        "historical_weather_parameters": [
            "T2M",
            "T2MDEW",
            "PRECTOTCORR",
        ],
        "label_definition": (
            "HIGH = documented IFI flood-event date. LOW = historical date "
            "with no IFI event record; this is a non-event/background label, "
            "not proof that flooding was impossible."
        ),
        "presentation_fast_build": True,
        "distinct_precipitation_features_only": True,
        "district_aliases_fixed": [
            "udam singh nagar -> Udham Singh Nagar",
            "uttar kashi kashi -> Uttarkashi",
        ],
        "previous_era5_cache_reused": False,
        "previous_era5_cache_deleted": False,
    }

    with open(RUN_METADATA_FILE, "w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=2)

    print("\n" + "=" * 80)
    print("V6.3 FAST TRAINING COMPLETED")
    print("=" * 80)
    print(f"Elapsed time: {elapsed / 60.0:.2f} minutes")
    print("\nGenerated:")
    print(TRAINING_FILE)
    print(MODEL_FILE)
    print(WEATHER_CACHE_DIR)
    print(AUDIT_FILE)
    print(RUN_METADATA_FILE)
    print(PROGRESS_FILE)
    print("\nMODEL LABELS:")
    print("0 = LOW")
    print("1 = HIGH")
    print("\nNOTE:")
    print("Live/current weather should remain handled separately by the prediction endpoint.")


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nTraining stopped by user.")
        print("Fast-training progress remains saved.")
        sys.exit(1)
    except Exception as error:
        print("\n" + "=" * 80)
        print("V6.3 FAST TRAINING STOPPED")
        print("=" * 80)
        print(str(error))
        print("\nSuccessfully cached districts remain safe.")
        sys.exit(1)
