"""Train the crop recommendation model.

Dataset: 'Crop Recommendation Dataset' (Kaggle) saved as dataset/Crop_recommendation.csv
Columns: N, P, K, temperature, humidity, ph, rainfall, label
Run:  python model/train_crop_model.py
"""
import os
import sys

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE, "dataset", "Crop_recommendation.csv")
MODEL_PATH = os.path.join(BASE, "model", "crop_model.pkl")
FEATURES = ["N", "P", "K", "temperature", "humidity", "ph", "rainfall"]

if not os.path.exists(CSV_PATH):
    sys.exit(f"Dataset not found at {CSV_PATH}\n"
             "Download 'Crop_recommendation.csv' and place it in the dataset/ folder.\n"
             "(The app still works without it using the rule-based fallback.)")

df = pd.read_csv(CSV_PATH).dropna()
X = df[FEATURES].values
y = df["label"].astype(str).values

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y)

model = RandomForestClassifier(n_estimators=200, random_state=42)
model.fit(X_train, y_train)

pred = model.predict(X_test)
print("Accuracy:", round(accuracy_score(y_test, pred) * 100, 2), "%")
print(classification_report(y_test, pred))

joblib.dump(model, MODEL_PATH)
print("Saved model to", MODEL_PATH)
