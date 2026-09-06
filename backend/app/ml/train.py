
"""
DISASTER INTELLIGENCE PLATFORM
================================
REAL-DATA FLOOD ML TRAINING - V3

REAL SOURCES
------------
1. India Flood Inventory (IFI)
   -> Real historical flood-event labels

2. Open-Meteo Historical Weather
   -> Real observed/modelled historical weather

IMPORTANT
---------
NO synthetic flood events.
NO fake rainfall.
NO artificial MEDIUM labels.

LABELS
------
2 = HIGH / documented flood event
0 = LOW / no documented flood event in IFI

IMPORTANT LIMITATION
--------------------
This is a FLOOD-EVENT classifier based on the
available IFI event inventory.

It is NOT a guaranteed physical flood forecast.

The model learns relationships between:
    historical weather
        +
documented flood occurrence
"""

import os
import time
import pickle
import warnings
from datetime import datetime, date, timedelta

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
    roc_auc_score,
)

warnings.filterwarnings("ignore")


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data"
)

WEATHER_CACHE_DIR = os.path.join(
    DATA_DIR,
    "weather_cache_v3"
)

FLOOD_FILE = os.path.join(
    DATA_DIR,
    "India_Flood_Inventory_v3.csv"
)

TRAINING_FILE = os.path.join(
    DATA_DIR,
    "real_disaster_training_data_v3.csv"
)

MODEL_FILE = os.path.join(
    BASE_DIR,
    "disaster_model.pkl"
)

os.makedirs(
    DATA_DIR,
    exist_ok=True
)

os.makedirs(
    WEATHER_CACHE_DIR,
    exist_ok=True
)


# ============================================================
# REAL FLOOD DATA SOURCE
# ============================================================

IFI_URL = (
    "https://zenodo.org/records/16994648/files/"
    "India_Flood_Inventory_v3.csv?download=1"
)


# ============================================================
# WEATHER SOURCE
# ============================================================

OPEN_METEO_ARCHIVE = (
    "https://archive-api.open-meteo.com/v1/archive"
)


# ============================================================
# TRAINING RANGE
# ============================================================

# Open-Meteo historical archive has much older data,
# but we intentionally use a modern period with the
# required variables.

TRAINING_START_YEAR = 2021

# Do NOT train on today's incomplete historical day.
TRAINING_END_DATE = (
    date.today() - timedelta(days=2)
)

TRAINING_END_YEAR = (
    TRAINING_END_DATE.year
)


# ============================================================
# DISTRICTS
# ============================================================

DISTRICTS = {

    "Almora": (
        29.5971,
        79.6591
    ),

    "Bageshwar": (
        29.8388,
        79.7711
    ),

    "Chamoli": (
        30.4028,
        79.3180
    ),

    "Champawat": (
        29.3350,
        80.0910
    ),

    "Dehradun": (
        30.3165,
        78.0322
    ),

    "Haridwar": (
        29.9457,
        78.1642
    ),

    "Nainital": (
        29.3919,
        79.4542
    ),

    "Pauri Garhwal": (
        30.1486,
        78.7814
    ),

    "Pithoragarh": (
        29.5829,
        80.2182
    ),

    "Rudraprayag": (
        30.2847,
        78.9811
    ),

    "Tehri Garhwal": (
        30.3780,
        78.4804
    ),

    "Udham Singh Nagar": (
        28.9760,
        79.4000
    ),

    "Uttarkashi": (
        30.7268,
        78.4354
    ),
}


# ============================================================
# DISTRICT ALIASES
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


# ============================================================
# FEATURES
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


# ============================================================
# NORMALIZE DISTRICT
# ============================================================

def normalize_district(value):

    if pd.isna(value):
        return None

    text = str(
        value
    ).strip().lower()

    text = (
        text
        .replace(",", "")
        .replace("-", " ")
        .replace("_", " ")
    )

    text = " ".join(
        text.split()
    )

    if text in DISTRICT_ALIASES:
        return DISTRICT_ALIASES[text]

    for alias, canonical in DISTRICT_ALIASES.items():

        if alias in text:
            return canonical

    return None


# ============================================================
# DOWNLOAD IFI
# ============================================================

def get_flood_data():

    if os.path.exists(
        FLOOD_FILE
    ):

        print(
            "\nFlood dataset already exists."
        )

        return pd.read_csv(
            FLOOD_FILE
        )

    print(
        "\nDownloading India Flood Inventory..."
    )

    response = requests.get(
        IFI_URL,
        timeout=180
    )

    response.raise_for_status()

    with open(
        FLOOD_FILE,
        "wb"
    ) as file:

        file.write(
            response.content
        )

    print(
        "Flood dataset downloaded."
    )

    return pd.read_csv(
        FLOOD_FILE
    )


# ============================================================
# CACHE
# ============================================================

def cache_path(
    district,
    year
):

    safe_name = (
        district
        .replace(" ", "_")
    )

    return os.path.join(
        WEATHER_CACHE_DIR,
        f"{safe_name}_{year}.csv"
    )


# ============================================================
# VALIDATE CACHE
# ============================================================

def valid_cached_weather(
    path,
    year
):

    if not os.path.exists(path):
        return False

    try:

        df = pd.read_csv(
            path
        )

        if df.empty:
            return False

        required = [
            "date",
            "temperature_2m_mean",
            "temperature_2m_max",
            "temperature_2m_min",
            "relative_humidity_2m_mean",
            "precipitation_sum",
            "rain_sum",
            "weather_code",
        ]

        if not all(
            col in df.columns
            for col in required
        ):
            return False

        dates = pd.to_datetime(
            df["date"],
            errors="coerce"
        )

        if dates.isna().all():
            return False

        # Cache must actually belong to this year.
        if dates.dt.year.min() != year:
            return False

        return True

    except Exception:

        return False


# ============================================================
# FETCH ONE YEAR
# ============================================================

def fetch_weather_year(
    district,
    latitude,
    longitude,
    year,
    retries=3
):

    path = cache_path(
        district,
        year
    )

    # --------------------------------------------------------
    # Cache
    # --------------------------------------------------------

    if valid_cached_weather(
        path,
        year
    ):

        cached = pd.read_csv(
            path
        )

        print(
            f"    CACHE OK: {year} "
            f"({len(cached)} days)"
        )

        return cached

    # --------------------------------------------------------
    # Date range
    # --------------------------------------------------------

    start_date = (
        f"{year}-01-01"
    )

    if year == TRAINING_END_YEAR:

        end_date = (
            TRAINING_END_DATE
            .isoformat()
        )

    else:

        end_date = (
            f"{year}-12-31"
        )

    print(
        f"    FETCH: {start_date} "
        f"-> {end_date}"
    )

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

    for attempt in range(
        1,
        retries + 1
    ):

        try:

            response = requests.get(
                OPEN_METEO_ARCHIVE,
                params=params,
                timeout=120
            )

            response.raise_for_status()

            payload = (
                response.json()
            )

            if "daily" not in payload:
                raise RuntimeError(
                    "Daily weather data missing."
                )

            daily = payload[
                "daily"
            ]

            df = pd.DataFrame(
                daily
            )

            if df.empty:
                raise RuntimeError(
                    "Empty weather response."
                )

            df["date"] = (
                pd.to_datetime(
                    df["time"],
                    errors="coerce"
                )
                .dt.normalize()
            )

            df.drop(
                columns=["time"],
                inplace=True,
                errors="ignore"
            )

            df["district"] = district

            # ------------------------------------------------
            # Remove invalid dates
            # ------------------------------------------------

            df = df.dropna(
                subset=["date"]
            )

            # ------------------------------------------------
            # Numeric conversion
            # ------------------------------------------------

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

                df[col] = pd.to_numeric(
                    df[col],
                    errors="coerce"
                )

            # ------------------------------------------------
            # Save REAL API response
            # ------------------------------------------------

            df.to_csv(
                path,
                index=False
            )

            print(
                f"    OK: {len(df)} days"
            )

            return df

        except Exception as error:

            print(
                f"    Attempt "
                f"{attempt}/{retries} failed: "
                f"{error}"
            )

            if attempt < retries:

                time.sleep(
                    2 * attempt
                )

    print(
        f"    FAILED: {district} {year}"
    )

    return None


# ============================================================
# WEATHER RANGE
# ============================================================

def get_weather_range(
    district,
    latitude,
    longitude
):

    frames = []

    print(
        f"\nWeather range: "
        f"{TRAINING_START_YEAR}"
        f" -> "
        f"{TRAINING_END_YEAR}"
    )

    for year in range(
        TRAINING_START_YEAR,
        TRAINING_END_YEAR + 1
    ):

        df = fetch_weather_year(
            district,
            latitude,
            longitude,
            year
        )

        if df is not None:

            frames.append(
                df
            )

        time.sleep(
            0.30
        )

    if not frames:

        return pd.DataFrame()

    weather = pd.concat(
        frames,
        ignore_index=True
    )

    weather["date"] = (
        pd.to_datetime(
            weather["date"],
            errors="coerce"
        )
        .dt.normalize()
    )

    weather = weather.dropna(
        subset=["date"]
    )

    weather = (
        weather
        .sort_values("date")
        .drop_duplicates(
            subset=["date"]
        )
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # REAL WEATHER FEATURES
    # --------------------------------------------------------

    rainfall = pd.to_numeric(
        weather["precipitation_sum"],
        errors="coerce"
    )

    weather["rain_3day"] = (
        rainfall
        .rolling(
            3,
            min_periods=1
        )
        .sum()
    )

    weather["rain_7day"] = (
        rainfall
        .rolling(
            7,
            min_periods=1
        )
        .sum()
    )

    weather["rain_14day"] = (
        rainfall
        .rolling(
            14,
            min_periods=1
        )
        .sum()
    )

    weather["rain_30day"] = (
        rainfall
        .rolling(
            30,
            min_periods=1
        )
        .sum()
    )

    weather["rain_intensity_3day"] = (
        rainfall
        .rolling(
            3,
            min_periods=1
        )
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

def prepare_flood_data(
    df
):

    print(
        "\nFlood dataset columns:"
    )

    print(
        df.columns.tolist()
    )

    print(
        f"\nFlood records: "
        f"{len(df)}"
    )

    date_column = "Start Date"
    district_column = "Districts"

    if date_column not in df.columns:
        raise RuntimeError(
            f"Missing column: {date_column}"
        )

    if district_column not in df.columns:
        raise RuntimeError(
            f"Missing column: {district_column}"
        )

    df = df.copy()

    df[date_column] = (
        pd.to_datetime(
            df[date_column],
            errors="coerce"
        )
    )

    df["normalized_district"] = (
        df[district_column]
        .apply(
            normalize_district
        )
    )

    df = df.dropna(
        subset=[
            date_column,
            "normalized_district"
        ]
    )

    df["flood_date"] = (
        df[date_column]
        .dt.normalize()
    )

    valid_years = (
        df["flood_date"]
        .dt.year
    )

    print(
        f"\nIFI records cover: "
        f"{valid_years.min()} "
        f"- "
        f"{valid_years.max()}"
    )

    return df


# ============================================================
# CREATE DATASET
# ============================================================

def create_training_dataset(
    flood_df
):

    training_parts = []

    for district, (
        latitude,
        longitude
    ) in DISTRICTS.items():

        print(
            "\n"
            + "=" * 60
        )

        print(
            f"DISTRICT: {district}"
        )

        print(
            "=" * 60
        )

        district_floods = (
            flood_df[
                flood_df[
                    "normalized_district"
                ]
                == district
            ]
            .copy()
        )

        # ----------------------------------------------------
        # No flood records for district
        # ----------------------------------------------------

        if district_floods.empty:

            print(
                "No IFI flood records "
                "for this district."
            )

            continue

        flood_dates = set(
            district_floods[
                "flood_date"
            ]
        )

        print(
            f"Unique documented flood days: "
            f"{len(flood_dates)}"
        )

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # Weather is NOT restricted to IFI's maximum year.
        #
        # We fetch from 2021 to latest available date.
        # ----------------------------------------------------

        weather = get_weather_range(
            district,
            latitude,
            longitude
        )

        if weather.empty:

            print(
                "No weather data."
            )

            continue

        # ----------------------------------------------------
        # Only use dates for which weather exists.
        # ----------------------------------------------------

        weather["risk"] = (
            weather["date"]
            .isin(flood_dates)
            .astype(int)
            * 2
        )

        # ----------------------------------------------------
        # Actual documented flood days
        # ----------------------------------------------------

        flood_samples = (
            weather[
                weather["risk"] == 2
            ]
            .copy()
        )

        # ----------------------------------------------------
        # REAL non-flood days
        #
        # Do NOT randomly keep only 20.
        #
        # Instead:
        # - exclude flood days
        # - balance using deterministic sampling
        # - retain a large representative set
        # ----------------------------------------------------

        non_flood = (
            weather[
                weather["risk"] == 0
            ]
            .copy()
        )

        # ----------------------------------------------------
        # Balance ratio
        #
        # Keep at most 4 LOW observations per flood day.
        #
        # These are still REAL observed weather days.
        # ----------------------------------------------------

        max_non_flood = max(
            len(flood_samples) * 4,
            100
        )

        if len(non_flood) > max_non_flood:

            non_flood = (
                non_flood
                .sample(
                    n=max_non_flood,
                    random_state=42
                )
                .sort_values("date")
            )

        print(
            f"Flood samples: "
            f"{len(flood_samples)}"
        )

        print(
            f"Real non-flood samples: "
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

    dataset = (
        dataset
        .sort_values(
            ["date", "district"]
        )
        .reset_index(
            drop=True
        )
    )

    return dataset


# ============================================================
# PREPARE FEATURES
# ============================================================

def prepare_features(
    dataset
):

    df = dataset.copy()

    for feature in FEATURES:

        if feature not in df.columns:

            raise RuntimeError(
                f"Missing feature: "
                f"{feature}"
            )

        df[feature] = pd.to_numeric(
            df[feature],
            errors="coerce"
        )

    df = df.dropna(
        subset=FEATURES + ["risk"]
    ).copy()

    df["risk"] = (
        df["risk"]
        .astype(int)
    )

    return df


# ============================================================
# TRAIN MODEL
# ============================================================

def train_model(
    dataset
):

    print(
        "\n"
        + "=" * 60
    )

    print(
        "REAL DATA MODEL TRAINING"
    )

    print(
        "=" * 60
    )

    dataset = dataset.sort_values(
        "date"
    ).reset_index(
        drop=True
    )

    X = dataset[
        FEATURES
    ]

    y = dataset[
        "risk"
    ]

    print(
        f"Total samples: "
        f"{len(dataset)}"
    )

    print(
        "\nClass distribution:"
    )

    print(
        y.value_counts()
        .sort_index()
    )

    if y.nunique() < 2:

        raise RuntimeError(
            "Training requires both "
            "LOW and HIGH classes."
        )

    # --------------------------------------------------------
    # TIME-BASED SPLIT
    #
    # First 80% = train
    # Last 20% = test
    #
    # This prevents future weather from entering training.
    # --------------------------------------------------------

    split_index = int(
        len(dataset) * 0.80
    )

    train_df = dataset.iloc[
        :split_index
    ]

    test_df = dataset.iloc[
        split_index:
    ]

    X_train = train_df[
        FEATURES
    ]

    y_train = train_df[
        "risk"
    ]

    X_test = test_df[
        FEATURES
    ]

    y_test = test_df[
        "risk"
    ]

    if y_train.nunique() < 2:

        raise RuntimeError(
            "Training split contains "
            "only one class. "
            "More historical flood data "
            "is required."
        )

    if y_test.nunique() < 2:

        print(
            "\nWARNING:"
            " Test period contains only "
            "one class."
        )

    # --------------------------------------------------------
    # MODEL
    # --------------------------------------------------------

    model = RandomForestClassifier(

        n_estimators=700,

        max_depth=20,

        min_samples_leaf=2,

        min_samples_split=4,

        class_weight=(
            "balanced_subsample"
        ),

        random_state=42,

        n_jobs=-1,

        max_features="sqrt",
    )

    print(
        "\nTraining Random Forest..."
    )

    model.fit(
        X_train,
        y_train
    )

    predictions = model.predict(
        X_test
    )

    # --------------------------------------------------------
    # PROBABILITY
    # --------------------------------------------------------

    probabilities = (
        model.predict_proba(
            X_test
        )
    )

    high_index = list(
        model.classes_
    ).index(2)

    high_probability = (
        probabilities[:, high_index]
    )

    # --------------------------------------------------------
    # EVALUATION
    # --------------------------------------------------------

    print(
        "\n"
        + "=" * 60
    )

    print(
        "MODEL EVALUATION"
    )

    print(
        "=" * 60
    )

    accuracy = accuracy_score(
        y_test,
        predictions
    )

    print(
        f"Accuracy: "
        f"{accuracy:.4f}"
    )

    print(
        "\nClassification report:"
    )

    print(
        classification_report(
            y_test,
            predictions,
            labels=[0, 2],
            target_names=[
                "LOW",
                "HIGH"
            ],
            zero_division=0
        )
    )

    cm = confusion_matrix(
        y_test,
        predictions,
        labels=[0, 2]
    )

    print(
        "Confusion Matrix:"
    )

    print(
        "              LOW   HIGH"
    )

    print(
        f"Actual LOW   "
        f"{cm[0][0]:>4} "
        f"{cm[0][1]:>6}"
    )

    print(
        f"Actual HIGH  "
        f"{cm[1][0]:>4} "
        f"{cm[1][1]:>6}"
    )

    precision = precision_score(
        y_test,
        predictions,
        pos_label=2,
        zero_division=0
    )

    recall = recall_score(
        y_test,
        predictions,
        pos_label=2,
        zero_division=0
    )

    f1 = f1_score(
        y_test,
        predictions,
        pos_label=2,
        zero_division=0
    )

    print(
        "\nFLOOD / HIGH METRICS"
    )

    print(
        f"Precision: {precision:.4f}"
    )

    print(
        f"Recall:    {recall:.4f}"
    )

    print(
        f"F1 Score:  {f1:.4f}"
    )

    # ROC-AUC only if test contains both classes
    if y_test.nunique() == 2:

        try:

            auc = roc_auc_score(
                (y_test == 2).astype(int),
                high_probability
            )

            print(
                f"ROC-AUC:   {auc:.4f}"
            )

        except Exception:

            pass

    # --------------------------------------------------------
    # FEATURE IMPORTANCE
    # --------------------------------------------------------

    print(
        "\nFeature importance:"
    )

    importance = (
        pd.Series(
            model.feature_importances_,
            index=FEATURES
        )
        .sort_values(
            ascending=False
        )
    )

    for feature, value in (
        importance.items()
    ):

        print(
            f"{feature:<30}"
            f"{value:.4f}"
        )

    # --------------------------------------------------------
    # SAVE MODEL
    # --------------------------------------------------------

    model_package = {

        "model": model,

        "features": FEATURES,

        "classes": {
            0: "LOW",
            2: "HIGH"
        },

        "version": "real-data-v3",

        "trained_at": (
            datetime.now()
            .isoformat()
        ),

        "training_start": (
            f"{TRAINING_START_YEAR}-01-01"
        ),

        "training_end": (
            TRAINING_END_DATE
            .isoformat()
        ),

        "data_source": [
            "India Flood Inventory (IFI)",
            "Open-Meteo Historical Weather"
        ],

        "notes": (
            "No synthetic flood events. "
            "No synthetic weather. "
            "Flood labels originate from IFI."
        )
    }

    with open(
        MODEL_FILE,
        "wb"
    ) as file:

        pickle.dump(
            model_package,
            file
        )

    print(
        "\n"
        + "=" * 60
    )

    print(
        "MODEL TRAINED SUCCESSFULLY"
    )

    print(
        "=" * 60
    )

    print(
        f"\nSaved:"
        f"\n{MODEL_FILE}"
    )

    return model


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n"
        + "=" * 70
    )

    print(
        "DISASTER INTELLIGENCE PLATFORM"
    )

    print(
        "REAL DATA TRAINING V3"
    )

    print(
        "=" * 70
    )

    print(
        f"\nTraining period:"
        f"\n{TRAINING_START_YEAR}-01-01"
        f" -> "
        f"{TRAINING_END_DATE}"
    )

    # --------------------------------------------------------
    # Flood data
    # --------------------------------------------------------

    flood_df = get_flood_data()

    flood_df = prepare_flood_data(
        flood_df
    )

    # --------------------------------------------------------
    # Training dataset
    # --------------------------------------------------------

    dataset = (
        create_training_dataset(
            flood_df
        )
    )

    # --------------------------------------------------------
    # Save raw training dataset
    # --------------------------------------------------------

    dataset.to_csv(
        TRAINING_FILE,
        index=False
    )

    print(
        "\nTraining dataset saved:"
    )

    print(
        TRAINING_FILE
    )

    # --------------------------------------------------------
    # Clean features
    # --------------------------------------------------------

    dataset = prepare_features(
        dataset
    )

    # --------------------------------------------------------
    # Train
    # --------------------------------------------------------

    train_model(
        dataset
    )


if __name__ == "__main__":

    main()
