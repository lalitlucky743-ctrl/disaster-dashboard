import os
import joblib
import numpy as np

from sklearn.ensemble import RandomForestClassifier


np.random.seed(42)


# -----------------------------------------
# Generate synthetic weather training data
# -----------------------------------------

data = []
labels = []


for _ in range(5000):

    temperature = np.random.uniform(5, 45)
    humidity = np.random.uniform(20, 100)
    precipitation = np.random.uniform(0, 100)
    rain = np.random.uniform(0, 100)
    weather_code = np.random.choice([
        0, 1, 2, 3,
        51, 53, 55,
        61, 63, 65,
        80, 81, 82,
        95, 96, 99
    ])

    # -----------------------------------------
    # Create training risk score
    # -----------------------------------------

    score = 0

    # Rainfall
    if rain >= 50:
        score += 45
    elif rain >= 20:
        score += 25
    elif rain >= 5:
        score += 10

    # Precipitation
    if precipitation >= 50:
        score += 25
    elif precipitation >= 20:
        score += 15
    elif precipitation >= 5:
        score += 5

    # Humidity
    if humidity >= 90:
        score += 20
    elif humidity >= 75:
        score += 10

    # Severe weather codes
    if weather_code in [65, 82, 95, 96, 99]:
        score += 30

    # Moderate rain
    if weather_code in [61, 63, 80, 81]:
        score += 10

    # Temperature isn't a primary flood factor,
    # but extreme temperature slightly increases risk.
    if temperature >= 40:
        score += 5

    # -----------------------------------------
    # Convert score into class
    # -----------------------------------------

    if score >= 70:
        risk = 2       # HIGH

    elif score >= 35:
        risk = 1       # MEDIUM

    else:
        risk = 0       # LOW

    data.append([
        temperature,
        humidity,
        precipitation,
        rain,
        weather_code,
    ])

    labels.append(risk)


# -----------------------------------------
# Train Random Forest
# -----------------------------------------

model = RandomForestClassifier(
    n_estimators=200,
    max_depth=12,
    random_state=42,
)

model.fit(data, labels)


# -----------------------------------------
# Save model
# -----------------------------------------

model_path = os.path.join(
    os.path.dirname(__file__),
    "disaster_model.pkl",
)

joblib.dump(model, model_path)


print("======================================")
print("Disaster ML model trained successfully")
print("======================================")
print(f"Model saved at: {model_path}")