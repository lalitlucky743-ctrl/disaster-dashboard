import os
import json
import pickle
import time
import random
from datetime import datetime

import numpy as np
import pandas as pd
import requests

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    accuracy_score,
    roc_auc_score,
)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(__file__)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data",
    "landslide",
)

INVENTORY_PATH = os.path.join(
    DATA_DIR,
    "gsi_landslide_inventory.csv",
)

MODEL_PATH = os.path.join(
    BASE_DIR,
    "landslide_model.pkl",
)

CACHE_DIR = os.path.join(
    DATA_DIR,
    "weather_cache",
)

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)


# ============================================================
# CONFIG
# ============================================================

OPEN_METEO_URL = (
    "https://archive-api.open-meteo.com/v1/archive"
)

OPEN_METEO_FORECAST_URL = (
    "https://api.open-meteo.com/v1/forecast"
)

START_DATE = "2021-01-01"

# Don't make training unnecessarily huge.
MAX_POSITIVE_SAMPLES = 2500
NEGATIVE_MULTIPLIER = 2

RANDOM_STATE = 42


# ============================================================
# EXPECTED FEATURES
# ============================================================

FEATURES = [
    "latitude",
    "longitude",
    "elevation",
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
# COLUMN DETECTION
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

    for candidate in candidates:
        key = normalize_column_name(candidate)

        if key in normalized:
            return normalized[key]

    # Partial matching
    for key, original in normalized.items():
        for candidate in candidates:
            candidate_key = normalize_column_name(candidate)

            if candidate_key in key or key in candidate_key:
                return original

    return None


# ============================================================
# LOAD GSI INVENTORY
# ============================================================

def load_gsi_inventory():
    if not os.path.exists(INVENTORY_PATH):
        raise FileNotFoundError(
            "\nGSI landslide inventory not found.\n"
            f"Expected file:\n{INVENTORY_PATH}\n\n"
            "Download the field-validated GSI landslide "
            "inventory and save it using that filename."
        )

    print("\nLoading GSI landslide inventory...")

    df = pd.read_csv(
        INVENTORY_PATH,
        low_memory=False,
    )

    if df.empty:
        raise RuntimeError(
            "GSI landslide inventory CSV is empty."
        )

    print(
        f"Loaded {len(df):,} inventory records."
    )

    return df


# ============================================================
# PREPARE GSI DATA
# ============================================================

def prepare_inventory(df):

    latitude_column = find_column(
        df,
        [
            "latitude",
            "lat",
            "latitude_deg",
            "y",
        ],
    )

    longitude_column = find_column(
        df,
        [
            "longitude",
            "lon",
            "long",
            "longitude_deg",
            "x",
        ],
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

    if latitude_column is None:
        raise RuntimeError(
            "Could not find latitude column in GSI CSV.\n"
            f"Available columns: {list(df.columns)}"
        )

    if longitude_column is None:
        raise RuntimeError(
            "Could not find longitude column in GSI CSV.\n"
            f"Available columns: {list(df.columns)}"
        )

    print(
        f"Latitude column : {latitude_column}"
    )

    print(
        f"Longitude column: {longitude_column}"
    )

    if date_column:
        print(
            f"Date column     : {date_column}"
        )
    else:
        print(
            "WARNING: No landslide date column found."
        )

    result = pd.DataFrame()

    result["latitude"] = pd.to_numeric(
        df[latitude_column],
        errors="coerce",
    )

    result["longitude"] = pd.to_numeric(
        df[longitude_column],
        errors="coerce",
    )

    if date_column:
        result["date"] = pd.to_datetime(
            df[date_column],
            errors="coerce",
        )
    else:
        result["date"] = pd.NaT

    # --------------------------------------------------------
    # Basic Uttarakhand geographic bounds
    # --------------------------------------------------------

    result = result[
        result["latitude"].between(
            28.5,
            31.5,
        )
        &
        result["longitude"].between(
            77.5,
            81.5,
        )
    ]

    result = result.dropna(
        subset=[
            "latitude",
            "longitude",
        ]
    )

    # Remove duplicate coordinates
    result = result.drop_duplicates(
        subset=[
            "latitude",
            "longitude",
        ]
    )

    result = result.reset_index(
        drop=True
    )

    print(
        f"Uttarakhand inventory points: "
        f"{len(result):,}"
    )

    if result.empty:
        raise RuntimeError(
            "No valid Uttarakhand landslide "
            "coordinates found in GSI inventory."
        )

    return result


# ============================================================
# OPEN-METEO HISTORICAL WEATHER
# ============================================================

def get_weather_cache_path(
    latitude,
    longitude,
):
    lat_key = f"{latitude:.4f}"
    lon_key = f"{longitude:.4f}"

    return os.path.join(
        CACHE_DIR,
        f"{lat_key}_{lon_key}.json",
    )


def fetch_historical_weather(
    latitude,
    longitude,
):

    cache_path = get_weather_cache_path(
        latitude,
        longitude,
    )

    if os.path.exists(cache_path):

        with open(
            cache_path,
            "r",
            encoding="utf-8",
        ) as f:

            return json.load(f)

    print(
        f"Fetching weather: "
        f"{latitude:.4f}, "
        f"{longitude:.4f}"
    )

    params = {
        "latitude": float(latitude),
        "longitude": float(longitude),
        "start_date": START_DATE,
        "end_date": (
            datetime.utcnow()
            .date()
            .isoformat()
        ),
        "daily": (
            "precipitation_sum,"
            "rain_sum,"
            "temperature_2m_mean,"
            "relative_humidity_2m_mean"
        ),
        "timezone": "Asia/Kolkata",
        "temperature_unit": "celsius",
        "precipitation_unit": "mm",
    }

    response = requests.get(
        OPEN_METEO_URL,
        params=params,
        timeout=60,
    )

    response.raise_for_status()

    payload = response.json()

    if "daily" not in payload:
        raise RuntimeError(
            "Open-Meteo historical daily data "
            "was not returned."
        )

    with open(
        cache_path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            payload,
            f,
        )

    # Be polite to API
    time.sleep(0.15)

    return payload


# ============================================================
# WEATHER DATAFRAME
# ============================================================

def weather_to_dataframe(payload):

    daily = payload.get("daily")

    if not daily:
        raise RuntimeError(
            "Historical daily weather is empty."
        )

    df = pd.DataFrame(daily)

    if df.empty:
        raise RuntimeError(
            "Historical weather dataframe is empty."
        )

    df["date"] = pd.to_datetime(
        df["time"],
        errors="coerce",
    )

    df = df.dropna(
        subset=["date"]
    )

    numeric_columns = [
        "precipitation_sum",
        "rain_sum",
        "temperature_2m_mean",
        "relative_humidity_2m_mean",
    ]

    for column in numeric_columns:

        if column not in df.columns:
            raise RuntimeError(
                f"Missing Open-Meteo field: "
                f"{column}"
            )

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df = df.dropna(
        subset=numeric_columns
    )

    df = (
        df
        .sort_values("date")
        .drop_duplicates("date")
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # Rolling rainfall
    # --------------------------------------------------------

    df["rain_1day"] = (
        df["rain_sum"]
    )

    df["rain_3day"] = (
        df["rain_sum"]
        .rolling(
            3,
            min_periods=3,
        )
        .sum()
    )

    df["rain_7day"] = (
        df["rain_sum"]
        .rolling(
            7,
            min_periods=7,
        )
        .sum()
    )

    df["rain_14day"] = (
        df["rain_sum"]
        .rolling(
            14,
            min_periods=14,
        )
        .sum()
    )

    df["rain_30day"] = (
        df["rain_sum"]
        .rolling(
            30,
            min_periods=30,
        )
        .sum()
    )

    df["precipitation_3day"] = (
        df["precipitation_sum"]
        .rolling(
            3,
            min_periods=3,
        )
        .sum()
    )

    df["precipitation_7day"] = (
        df["precipitation_sum"]
        .rolling(
            7,
            min_periods=7,
        )
        .sum()
    )

    return df


# ============================================================
# ELEVATION
# ============================================================

def fetch_elevation(
    latitude,
    longitude,
):

    params = {
        "latitude": float(latitude),
        "longitude": float(longitude),
        "current": "temperature_2m",
    }

    response = requests.get(
        OPEN_METEO_FORECAST_URL,
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
            "Elevation unavailable from "
            "Open-Meteo."
        )

    return float(elevation)


# ============================================================
# BUILD POSITIVE SAMPLES
# ============================================================

def build_positive_samples(
    inventory,
):

    samples = []

    if len(inventory) > MAX_POSITIVE_SAMPLES:

        inventory = inventory.sample(
            MAX_POSITIVE_SAMPLES,
            random_state=RANDOM_STATE,
        )

    for index, row in inventory.iterrows():

        latitude = float(
            row["latitude"]
        )

        longitude = float(
            row["longitude"]
        )

        try:

            weather_payload = (
                fetch_historical_weather(
                    latitude,
                    longitude,
                )
            )

            weather_df = (
                weather_to_dataframe(
                    weather_payload
                )
            )

            elevation = fetch_elevation(
                latitude,
                longitude,
            )

            # ------------------------------------------------
            # Use available historical days.
            #
            # Since GSI occurrence date may not be present
            # or may have inconsistent formatting, use
            # weather periods to construct susceptibility
            # samples at inventory locations.
            # ------------------------------------------------

            usable = weather_df.dropna(
                subset=[
                    "rain_3day",
                    "rain_7day",
                    "rain_14day",
                    "rain_30day",
                    "precipitation_3day",
                    "precipitation_7day",
                ]
            )

            if usable.empty:
                continue

            # Select representative high-rainfall conditions
            # around known landslide locations.
            recent = usable.tail(30)

            for _, weather in recent.iterrows():

                samples.append(
                    {
                        "latitude": latitude,
                        "longitude": longitude,
                        "elevation": elevation,

                        "rain_1day": float(
                            weather["rain_1day"]
                        ),

                        "rain_3day": float(
                            weather["rain_3day"]
                        ),

                        "rain_7day": float(
                            weather["rain_7day"]
                        ),

                        "rain_14day": float(
                            weather["rain_14day"]
                        ),

                        "rain_30day": float(
                            weather["rain_30day"]
                        ),

                        "precipitation_3day": float(
                            weather[
                                "precipitation_3day"
                            ]
                        ),

                        "precipitation_7day": float(
                            weather[
                                "precipitation_7day"
                            ]
                        ),

                        "temperature": float(
                            weather[
                                "temperature_2m_mean"
                            ]
                        ),

                        "humidity": float(
                            weather[
                                "relative_humidity_2m_mean"
                            ]
                        ),

                        "landslide": 1,
                    }
                )

        except Exception as exc:

            print(
                f"Skipping "
                f"{latitude:.4f}, "
                f"{longitude:.4f}: "
                f"{exc}"
            )

    return pd.DataFrame(samples)


# ============================================================
# BUILD NEGATIVE SAMPLES
# ============================================================

def generate_negative_locations(
    positive_df,
):

    rng = np.random.default_rng(
        RANDOM_STATE
    )

    number_of_locations = max(
        100,
        len(positive_df)
        // 30,
    )

    negative_locations = []

    positive_coords = set(
        zip(
            positive_df["latitude"].round(3),
            positive_df["longitude"].round(3),
        )
    )

    attempts = 0

    while (
        len(negative_locations)
        < number_of_locations
        and attempts < number_of_locations * 20
    ):

        attempts += 1

        latitude = rng.uniform(
            29.0,
            31.5,
        )

        longitude = rng.uniform(
            77.5,
            81.2,
        )

        key = (
            round(latitude, 3),
            round(longitude, 3),
        )

        if key in positive_coords:
            continue

        negative_locations.append(
            (
                latitude,
                longitude,
            )
        )

    return negative_locations


def build_negative_samples(
    positive_df,
):

    samples = []

    locations = (
        generate_negative_locations(
            positive_df
        )
    )

    print(
        f"\nGenerating "
        f"{len(locations):,} negative locations..."
    )

    for (
        latitude,
        longitude,
    ) in locations:

        try:

            weather_payload = (
                fetch_historical_weather(
                    latitude,
                    longitude,
                )
            )

            weather_df = (
                weather_to_dataframe(
                    weather_payload
                )
            )

            elevation = fetch_elevation(
                latitude,
                longitude,
            )

            usable = weather_df.dropna(
                subset=[
                    "rain_3day",
                    "rain_7day",
                    "rain_14day",
                    "rain_30day",
                    "precipitation_3day",
                    "precipitation_7day",
                ]
            )

            if usable.empty:
                continue

            # Same temporal sampling strategy
            recent = usable.tail(30)

            for _, weather in recent.iterrows():

                samples.append(
                    {
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
                            weather["rain_1day"]
                        ),

                        "rain_3day": float(
                            weather["rain_3day"]
                        ),

                        "rain_7day": float(
                            weather["rain_7day"]
                        ),

                        "rain_14day": float(
                            weather["rain_14day"]
                        ),

                        "rain_30day": float(
                            weather["rain_30day"]
                        ),

                        "precipitation_3day": float(
                            weather[
                                "precipitation_3day"
                            ]
                        ),

                        "precipitation_7day": float(
                            weather[
                                "precipitation_7day"
                            ]
                        ),

                        "temperature": float(
                            weather[
                                "temperature_2m_mean"
                            ]
                        ),

                        "humidity": float(
                            weather[
                                "relative_humidity_2m_mean"
                            ]
                        ),

                        "landslide": 0,
                    }
                )

        except Exception as exc:

            print(
                f"Skipping negative point "
                f"{latitude:.4f}, "
                f"{longitude:.4f}: "
                f"{exc}"
            )

    return pd.DataFrame(samples)


# ============================================================
# TRAIN MODEL
# ============================================================

def train():

    print("\n")
    print("=" * 70)
    print("LANDSLIDE ML TRAINING")
    print("=" * 70)

    inventory = load_gsi_inventory()

    inventory = prepare_inventory(
        inventory
    )

    print("\nBuilding positive samples...")

    positive_df = (
        build_positive_samples(
            inventory
        )
    )

    if positive_df.empty:
        raise RuntimeError(
            "No positive training samples "
            "could be generated."
        )

    print(
        f"Positive samples: "
        f"{len(positive_df):,}"
    )

    print("\nBuilding negative samples...")

    negative_df = (
        build_negative_samples(
            positive_df
        )
    )

    if negative_df.empty:
        raise RuntimeError(
            "No negative training samples "
            "could be generated."
        )

    print(
        f"Negative samples: "
        f"{len(negative_df):,}"
    )

    # --------------------------------------------------------
    # Combine
    # --------------------------------------------------------

    dataset = pd.concat(
        [
            positive_df,
            negative_df,
        ],
        ignore_index=True,
    )

    dataset = dataset.dropna(
        subset=FEATURES + ["landslide"]
    )

    dataset = dataset.drop_duplicates()

    print(
        f"\nFinal dataset: "
        f"{len(dataset):,}"
    )

    print(
        "\nClass distribution:"
    )

    print(
        dataset["landslide"]
        .value_counts()
    )

    if dataset["landslide"].nunique() < 2:
        raise RuntimeError(
            "Training dataset contains "
            "only one class."
        )

    # --------------------------------------------------------
    # X / y
    # --------------------------------------------------------

    X = dataset[
        FEATURES
    ].astype(float)

    y = dataset[
        "landslide"
    ].astype(int)

    # --------------------------------------------------------
    # Split
    # --------------------------------------------------------

    X_train, X_test, y_train, y_test = (
        train_test_split(
            X,
            y,
            test_size=0.20,
            random_state=RANDOM_STATE,
            stratify=y,
        )
    )

    print(
        f"\nTraining samples: "
        f"{len(X_train):,}"
    )

    print(
        f"Testing samples: "
        f"{len(X_test):,}"
    )

    # --------------------------------------------------------
    # Random Forest
    # --------------------------------------------------------

    model = RandomForestClassifier(
        n_estimators=500,
        max_depth=18,
        min_samples_leaf=2,
        min_samples_split=4,
        class_weight="balanced_subsample",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )

    print(
        "\nTraining RandomForest..."
    )

    model.fit(
        X_train,
        y_train,
    )

    # --------------------------------------------------------
    # Evaluation
    # --------------------------------------------------------

    predictions = model.predict(
        X_test
    )

    probabilities = (
        model.predict_proba(X_test)[:, 1]
    )

    accuracy = accuracy_score(
        y_test,
        predictions,
    )

    print(
        "\nAccuracy:",
        round(accuracy, 4),
    )

    try:

        auc = roc_auc_score(
            y_test,
            probabilities,
        )

        print(
            "ROC-AUC:",
            round(auc, 4),
        )

    except Exception:

        auc = None

    print(
        "\nClassification Report:"
    )

    print(
        classification_report(
            y_test,
            predictions,
            digits=4,
        )
    )

    print(
        "\nConfusion Matrix:"
    )

    print(
        confusion_matrix(
            y_test,
            predictions,
        )
    )

    # --------------------------------------------------------
    # Feature importance
    # --------------------------------------------------------

    importance = dict(
        zip(
            FEATURES,
            model.feature_importances_,
        )
    )

    print(
        "\nFeature Importance:"
    )

    for name, value in sorted(
        importance.items(),
        key=lambda item: item[1],
        reverse=True,
    ):

        print(
            f"{name:25s} "
            f"{value:.4f}"
        )

    # --------------------------------------------------------
    # Save model package
    # --------------------------------------------------------

    package = {
        "model": model,
        "features": FEATURES,
        "version": "landslide-real-data-v1",
        "model_type": "RandomForestClassifier",
        "target": "landslide_susceptibility",
        "source": (
            "GSI field-validated "
            "landslide inventory + "
            "Open-Meteo historical weather"
        ),
        "training_date": (
            datetime.utcnow()
            .isoformat()
            + "Z"
        ),
        "training_samples": int(
            len(X_train)
        ),
        "testing_samples": int(
            len(X_test)
        ),
        "accuracy": float(
            accuracy
        ),
        "roc_auc": (
            float(auc)
            if auc is not None
            else None
        ),
    }

    with open(
        MODEL_PATH,
        "wb",
    ) as f:

        pickle.dump(
            package,
            f,
        )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "MODEL SAVED:"
    )

    print(
        MODEL_PATH
    )

    print(
        "=" * 70
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    train()