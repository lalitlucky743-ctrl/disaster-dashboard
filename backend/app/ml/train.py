
"""
DISASTER INTELLIGENCE PLATFORM
REAL DATA ML TRAINING - IMPROVED VERSION

Data sources:
1. India Flood Inventory (IFI) - real historical flood events
2. Open-Meteo Historical Weather - real historical weather

IMPORTANT:
- No synthetic flood events
- No artificial MEDIUM labels
- Actual flood dates = HIGH
- Other observed weather days = LOW
- Uses rolling rainfall features for better flood detection
"""

import os
import time
import pickle
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
import requests

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    precision_score,
    recall_score,
    f1_score,
)
from sklearn.model_selection import train_test_split

warnings.filterwarnings("ignore")


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

os.makedirs(DATA_DIR, exist_ok=True)

FLOOD_FILE = os.path.join(DATA_DIR, "India_Flood_Inventory_v3.csv")
WEATHER_CACHE_DIR = os.path.join(DATA_DIR, "weather_cache")
TRAINING_FILE = os.path.join(
    DATA_DIR,
    "real_disaster_training_data.csv"
)
MODEL_FILE = os.path.join(
    BASE_DIR,
    "disaster_model.pkl"
)

os.makedirs(WEATHER_CACHE_DIR, exist_ok=True)


# ============================================================
# DATA SOURCE
# ============================================================

IFI_URL = (
    "https://zenodo.org/records/16994648/files/"
    "India_Flood_Inventory_v3.csv?download=1"
)


# ============================================================
# UTTARAKHAND DISTRICTS
# ============================================================

DISTRICTS = {
    "Almora": (29.5971, 79.6591),
    "Bageshwar": (29.8388, 79.7711),
    "Chamoli": (30.4028, 79.3180),
    "Champawat": (29.3350, 80.0910),
    "Dehradun": (30.3165, 78.0322),
    "Haridwar": (29.9457, 78.1642),
    "Nainital": (29.3919, 79.4542),
    "Pauri Garhwal": (30.1486, 78.7814),
    "Pithoragarh": (29.5829, 80.2182),
    "Rudraprayag": (30.2847, 78.9811),
    "Tehri Garhwal": (30.3780, 78.4804),
    "Udham Singh Nagar": (28.9760, 79.4000),
    "Uttarkashi": (30.7268, 78.4354),
}


# ============================================================
# DISTRICT NAME NORMALIZATION
# ============================================================

DISTRICT_ALIASES = {
    "almora": "Almora",
    "almora district": "Almora",

    "bageshwar": "Bageshwar",
    "bageshwar district": "Bageshwar",

    "chamoli": "Chamoli",
    "chamoli district": "Chamoli",

    "champawat": "Champawat",
    "champawat district": "Champawat",

    "dehradun": "Dehradun",
    "dehradun district": "Dehradun",

    "haridwar": "Haridwar",
    "haridwar district": "Haridwar",

    "nainital": "Nainital",
    "nainital district": "Nainital",

    "pauri": "Pauri Garhwal",
    "pauri garhwal": "Pauri Garhwal",
    "pauri_garhwal": "Pauri Garhwal",
    "pauri district": "Pauri Garhwal",

    "pithoragarh": "Pithoragarh",
    "pithoragarh district": "Pithoragarh",

    "rudraprayag": "Rudraprayag",
    "rudraprayag district": "Rudraprayag",

    "tehri": "Tehri Garhwal",
    "tehri garhwal": "Tehri Garhwal",
    "tehri_garhwal": "Tehri Garhwal",

    "udham singh nagar": "Udham Singh Nagar",
    "udham singh nagar district": "Udham Singh Nagar",
    "u.s. nagar": "Udham Singh Nagar",
    "us nagar": "Udham Singh Nagar",

    "uttarkashi": "Uttarkashi",
    "uttarkashi district": "Uttarkashi",
}


def normalize_district(value):
    if pd.isna(value):
        return None

    text = str(value).strip().lower()

    text = (
        text.replace(",", "")
        .replace("-", " ")
        .replace("_", " ")
    )

    text = " ".join(text.split())

    if text in DISTRICT_ALIASES:
        return DISTRICT_ALIASES[text]

    # fallback partial matching
    for alias, canonical in DISTRICT_ALIASES.items():
        if alias in text:
            return canonical

    return None


# ============================================================
# DOWNLOAD FLOOD DATA
# ============================================================

def get_flood_data():

    if os.path.exists(FLOOD_FILE):
        print("Flood dataset already exists.")
        return pd.read_csv(FLOOD_FILE)

    print("Downloading India Flood Inventory...")

    response = requests.get(
        IFI_URL,
        timeout=120
    )

    response.raise_for_status()

    with open(FLOOD_FILE, "wb") as f:
        f.write(response.content)

    print("Flood dataset downloaded.")

    return pd.read_csv(FLOOD_FILE)


# ============================================================
# WEATHER CACHE
# ============================================================

def cache_path(district, year):
    safe_name = district.replace(" ", "_")
    return os.path.join(
        WEATHER_CACHE_DIR,
        f"{safe_name}_{year}.csv"
    )


# ============================================================
# FETCH ONE YEAR WEATHER
# ============================================================

def fetch_weather_year(
    district,
    latitude,
    longitude,
    year,
    retries=3
):

    path = cache_path(district, year)

    # --------------------------------------------------------
    # USE CACHE
    # --------------------------------------------------------

    if os.path.exists(path):

        try:
            cached = pd.read_csv(path)

            if not cached.empty:
                print(
                    f"    CACHE: {year} "
                    f"({len(cached)} days)"
                )
                return cached

        except Exception:
            pass

    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"

    url = "https://archive-api.open-meteo.com/v1/archive"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
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
    }

    for attempt in range(1, retries + 1):

        try:

            response = requests.get(
                url,
                params=params,
                timeout=60
            )

            response.raise_for_status()

            data = response.json()

            if "daily" not in data:
                raise ValueError(
                    "Daily weather data missing"
                )

            daily = data["daily"]

            df = pd.DataFrame(daily)

            if df.empty:
                raise ValueError(
                    "Empty weather response"
                )

            df["date"] = pd.to_datetime(
                df["time"]
            ).dt.date

            df["district"] = district

            df.drop(
                columns=["time"],
                inplace=True,
                errors="ignore"
            )

            df.to_csv(
                path,
                index=False
            )

            print(
                f"    OK: {len(df)} days"
            )

            return df

        except Exception as e:

            print(
                f"    Attempt {attempt}/{retries} "
                f"failed: {e}"
            )

            if attempt < retries:
                time.sleep(2 * attempt)

    print(
        f"    Skipping weather year {year}"
    )

    return None


# ============================================================
# WEATHER RANGE
# ============================================================

def get_weather_range(
    district,
    latitude,
    longitude,
    start_year,
    end_year
):

    all_weather = []

    print(
        f"Weather period: "
        f"{start_year} -> {end_year}"
    )

    for year in range(start_year, end_year + 1):

        print(
            f"  Weather year {year}: "
            f"{year}-01-01 -> {year}-12-31"
        )

        df = fetch_weather_year(
            district,
            latitude,
            longitude,
            year
        )

        if df is not None:
            all_weather.append(df)

        # small pause to avoid hammering API
        time.sleep(0.25)

    if not all_weather:
        return pd.DataFrame()

    weather = pd.concat(
        all_weather,
        ignore_index=True
    )

    weather["date"] = pd.to_datetime(
        weather["date"]
    )

    weather.sort_values(
        "date",
        inplace=True
    )

    weather.reset_index(
        drop=True,
        inplace=True
    )

    # --------------------------------------------------------
    # CLEAN NUMERIC COLUMNS
    # --------------------------------------------------------

    numeric_columns = [
        "temperature_2m_mean",
        "temperature_2m_max",
        "temperature_2m_min",
        "relative_humidity_2m_mean",
        "precipitation_sum",
        "rain_sum",
        "weather_code",
    ]

    for col in numeric_columns:

        if col in weather.columns:
            weather[col] = pd.to_numeric(
                weather[col],
                errors="coerce"
            )

    # --------------------------------------------------------
    # REAL WEATHER-DERIVED FEATURES
    # --------------------------------------------------------

    weather["rain_3day"] = (
        weather["precipitation_sum"]
        .rolling(3, min_periods=1)
        .sum()
    )

    weather["rain_7day"] = (
        weather["precipitation_sum"]
        .rolling(7, min_periods=1)
        .sum()
    )

    weather["rain_14day"] = (
        weather["precipitation_sum"]
        .rolling(14, min_periods=1)
        .sum()
    )

    weather["rain_30day"] = (
        weather["precipitation_sum"]
        .rolling(30, min_periods=1)
        .sum()
    )

    weather["rain_intensity_3day"] = (
        weather["precipitation_sum"]
        .rolling(3, min_periods=1)
        .mean()
    )

    print(
        f"Historical weather days: "
        f"{len(weather)}"
    )

    return weather


# ============================================================
# PREPARE FLOOD DATA
# ============================================================

def prepare_flood_data(df):

    print("\nFlood dataset columns:")
    print(df.columns.tolist())

    print(
        f"\nNumber of flood records: "
        f"{len(df)}"
    )

    date_column = "Start Date"
    district_column = "Districts"

    print(
        f"\nUsing date column: {date_column}"
    )

    print(
        f"Using district column: {district_column}"
    )

    df[date_column] = pd.to_datetime(
        df[date_column],
        errors="coerce"
    )

    df["normalized_district"] = (
        df[district_column]
        .apply(normalize_district)
    )

    df = df.dropna(
        subset=[date_column]
    ).copy()

    df["flood_date"] = (
        df[date_column]
        .dt.normalize()
    )

    valid_years = df[
        "flood_date"
    ].dt.year

    print(
        f"\nFlood records cover "
        f"{valid_years.min()} - "
        f"{valid_years.max()}"
    )

    return df


# ============================================================
# CREATE DATASET
# ============================================================

def create_training_dataset(flood_df):

    training_parts = []

    for district, (
        latitude,
        longitude
    ) in DISTRICTS.items():

        print("\n================================")
        print(f"DISTRICT: {district}")
        print("================================")

        district_floods = flood_df[
            flood_df["normalized_district"]
            == district
        ].copy()

        if district_floods.empty:

            print(
                "No matching flood records found."
            )

            continue

        flood_dates = set(
            district_floods[
                "flood_date"
            ].dt.normalize()
        )

        print(
            f"Actual flood records: "
            f"{len(district_floods)}"
        )

        print(
            f"Unique flood days: "
            f"{len(flood_dates)}"
        )

        start_year = int(
            district_floods[
                "flood_date"
            ].dt.year.min()
        )

        end_year = int(
            district_floods[
                "flood_date"
            ].dt.year.max()
        )

        # ----------------------------------------------------
        # Open-Meteo archive availability starts from 1940,
        # but our model uses the available period from IFI.
        # ----------------------------------------------------

        weather = get_weather_range(
            district,
            latitude,
            longitude,
            start_year,
            end_year
        )

        if weather.empty:
            print(
                "No weather data available."
            )
            continue

        weather["risk"] = (
            weather["date"]
            .dt.normalize()
            .isin(flood_dates)
            .astype(int)
            * 2
        )

        # ----------------------------------------------------
        # Keep ACTUAL flood days
        # ----------------------------------------------------

        flood_samples = weather[
            weather["risk"] == 2
        ].copy()

        # ----------------------------------------------------
        # Real non-flood days
        #
        # We sample actual observed days, not synthetic data.
        # Maximum 20 LOW days per district to reduce imbalance.
        # ----------------------------------------------------

        non_flood = weather[
            weather["risk"] == 0
        ].copy()

        if len(non_flood) > 20:

            non_flood = non_flood.sample(
                n=20,
                random_state=42
            )

        print(
            f"Actual flood days used: "
            f"{len(flood_samples)}"
        )

        print(
            f"Real non-flood days used: "
            f"{len(non_flood)}"
        )

        district_data = pd.concat(
            [
                flood_samples,
                non_flood
            ],
            ignore_index=True
        )

        district_data[
            "district"
        ] = district

        training_parts.append(
            district_data
        )

    if not training_parts:
        raise RuntimeError(
            "No training data was created."
        )

    dataset = pd.concat(
        training_parts,
        ignore_index=True
    )

    return dataset


# ============================================================
# FEATURE PREPARATION
# ============================================================

FEATURES = [
    "temperature_2m_mean",
    "temperature_2m_max",
    "temperature_2m_min",
    "relative_humidity_2m_mean",
    "precipitation_sum",
    "rain_sum",
    "weather_code",
    "rain_3day",
    "rain_7day",
    "rain_14day",
    "rain_30day",
    "rain_intensity_3day",
]


def prepare_features(dataset):

    df = dataset.copy()

    for feature in FEATURES:

        df[feature] = pd.to_numeric(
            df[feature],
            errors="coerce"
        )

    df = df.dropna(
        subset=FEATURES + ["risk"]
    ).copy()

    X = df[FEATURES]
    y = df["risk"].astype(int)

    return X, y, df


# ============================================================
# TRAIN MODEL
# ============================================================

def train_model(X, y):

    print("\n================================")
    print("REAL DATA MODEL TRAINING")
    print("================================")

    print(
        f"Total samples: {len(X)}"
    )

    print("\nClass distribution:")
    print(
        y.value_counts()
        .sort_index()
    )

    if y.nunique() < 2:
        raise RuntimeError(
            "Training requires at least "
            "two classes."
        )

    # --------------------------------------------------------
    # Stratified split
    # --------------------------------------------------------

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=42,
        stratify=y
    )

    model = RandomForestClassifier(
        n_estimators=500,
        max_depth=18,
        min_samples_leaf=2,
        min_samples_split=4,
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1,
    )

    model.fit(
        X_train,
        y_train
    )

    predictions = model.predict(
        X_test
    )

    # --------------------------------------------------------
    # Evaluation
    # --------------------------------------------------------

    print("\n================================")
    print("MODEL EVALUATION")
    print("================================")

    accuracy = accuracy_score(
        y_test,
        predictions
    )

    print(
        f"Accuracy: {accuracy:.4f}"
    )

    print("\nClassification report:")

    print(
        classification_report(
            y_test,
            predictions,
            labels=[0, 2],
            target_names=["LOW", "HIGH"],
            zero_division=0
        )
    )

    print("Confusion matrix:")

    cm = confusion_matrix(
        y_test,
        predictions,
        labels=[0, 2]
    )

    print(
        "             Pred LOW   Pred HIGH"
    )
    print(
        f"Actual LOW      {cm[0][0]:>4}        {cm[0][1]:>4}"
    )
    print(
        f"Actual HIGH     {cm[1][0]:>4}        {cm[1][1]:>4}"
    )

    # --------------------------------------------------------
    # Explicit flood metrics
    # --------------------------------------------------------

    high_precision = precision_score(
        y_test,
        predictions,
        pos_label=2,
        zero_division=0
    )

    high_recall = recall_score(
        y_test,
        predictions,
        pos_label=2,
        zero_division=0
    )

    high_f1 = f1_score(
        y_test,
        predictions,
        pos_label=2,
        zero_division=0
    )

    print("\nHIGH / FLOOD METRICS:")
    print(
        f"Precision: {high_precision:.4f}"
    )
    print(
        f"Recall:    {high_recall:.4f}"
    )
    print(
        f"F1 Score:  {high_f1:.4f}"
    )

    # --------------------------------------------------------
    # Feature importance
    # --------------------------------------------------------

    print("\nFeature importance:")

    importance = pd.Series(
        model.feature_importances_,
        index=FEATURES
    ).sort_values(
        ascending=False
    )

    for feature, value in importance.items():

        print(
            f"{feature}: {value:.4f}"
        )

    # --------------------------------------------------------
    # Save model
    # --------------------------------------------------------

    model_package = {
        "model": model,
        "features": FEATURES,
        "classes": {
            0: "LOW",
            2: "HIGH"
        },
        "version": "real-data-v2",
        "trained_at": datetime.now().isoformat(),
    }

    with open(
        MODEL_FILE,
        "wb"
    ) as f:

        pickle.dump(
            model_package,
            f
        )

    print("\n================================")
    print("REAL DATA DISASTER MODEL TRAINED")
    print("================================")

    print(
        f"Model saved at:\n{MODEL_FILE}"
    )

    return model


# ============================================================
# MAIN
# ============================================================

def main():

    print("==========================================")
    print("DISASTER INTELLIGENCE PLATFORM")
    print("IMPROVED REAL DATA ML TRAINING")
    print("==========================================")

    flood_df = get_flood_data()

    flood_df = prepare_flood_data(
        flood_df
    )

    dataset = create_training_dataset(
        flood_df
    )

    # Save complete training dataset
    dataset.to_csv(
        TRAINING_FILE,
        index=False
    )

    print("\nTraining dataset saved:")
    print(TRAINING_FILE)

    X, y, cleaned_dataset = prepare_features(
        dataset
    )

    train_model(
        X,
        y
    )


if __name__ == "__main__":
    main()
