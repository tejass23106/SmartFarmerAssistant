"""Potato tuber disease prediction using the separately trained MobileNetV2 model."""
import json
import os
import threading

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE, "potato_tuber_model.keras")
CLASSES_PATH = os.path.join(BASE, "potato_tuber_class_names.json")
IMG_SIZE = (224, 224)
LOW_CONFIDENCE = 60.0

_load_lock = threading.Lock()
_infer_lock = threading.Lock()
_model = None
_class_names = None


class TuberModelNotAvailable(Exception):
    pass


class TuberPredictionError(Exception):
    pass


def model_available():
    return os.path.exists(MODEL_PATH) and os.path.exists(CLASSES_PATH)


def _load():
    global _model, _class_names

    if _model is not None:
        return

    with _load_lock:
        if _model is not None:
            return

        if not model_available():
            raise TuberModelNotAvailable("Potato tuber model files are missing.")

        try:
            import tensorflow as tf
            model = tf.keras.models.load_model(MODEL_PATH)

            with open(CLASSES_PATH, encoding="utf-8") as f:
                names = json.load(f)

            if len(names) != 10:
                raise ValueError("Unexpected potato tuber class count.")

            _model = model
            _class_names = names

        except Exception as exc:
            raise TuberModelNotAvailable(
                f"Could not load potato tuber model: {exc}"
            ) from exc


def predict_potato_tuber(path, top_k=3):
    import cv2

    _load()

    try:
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)

        if img is None:
            raise ValueError("Unreadable image")

        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, IMG_SIZE, interpolation=cv2.INTER_AREA)
        x = np.expand_dims(img.astype("float32"), axis=0)

        with _infer_lock:
            probs = _model.predict(x, verbose=0)[0]

    except Exception as exc:
        raise TuberPredictionError(
            "Could not analyse this image. Please try another photo."
        ) from exc

    order = np.argsort(probs)[::-1][:top_k]
    top = [
        {
            "label": _class_names[int(i)],
            "confidence": round(float(probs[i]) * 100, 1)
        }
        for i in order
    ]

    best = top[0]
    disease = best["label"]

    if disease == "Healthy Potatoes":
        disease = "Healthy"
    elif disease == "Miscellaneous":
        disease = "Other / Unclassified"

    return {
        "label": best["label"],
        "crop": "Potato",
        "disease": disease,
        "confidence": best["confidence"],
        "top": top,
        "low_confidence": best["confidence"] < LOW_CONFIDENCE,
        "plant_part": "Tuber",
    }
