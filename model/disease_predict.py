"""Disease prediction: loads the trained Keras model once and predicts from an image file."""
import json
import os
import threading

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE, "disease_model.keras")
CLASSES_PATH = os.path.join(BASE, "class_names.json")
IMG_SIZE = (224, 224)
LOW_CONFIDENCE = 60.0  # below this (%), the result is flagged as uncertain

_load_lock = threading.Lock()
_infer_lock = threading.Lock()
_model = None
_class_names = None


class ModelNotAvailable(Exception):
    """Model files are missing or could not be loaded."""


class PredictionError(Exception):
    """The image could not be processed or the prediction failed."""


def model_available():
    return os.path.exists(MODEL_PATH) and os.path.exists(CLASSES_PATH)


def parse_label(label):
    """'Tomato___Early_blight' -> ('Tomato', 'Early blight')."""
    if "___" in label:
        crop, disease = label.split("___", 1)
    elif "_" in label:
        crop, disease = label.split("_", 1)
    else:
        crop, disease = label, "Unknown"
    return crop.replace("_", " ").strip().title(), disease.replace("_", " ").strip().capitalize()


def _load():
    global _model, _class_names
    if _model is not None:
        return
    with _load_lock:
        if _model is not None:
            return
        if not model_available():
            raise ModelNotAvailable("The disease detection model has not been trained yet.")
        try:
            import tensorflow as tf
        except ImportError:
            raise ModelNotAvailable("TensorFlow is not installed on this server.")
        try:
            model = tf.keras.models.load_model(MODEL_PATH)
            with open(CLASSES_PATH, encoding="utf-8") as f:
                names = json.load(f)
        except Exception:
            raise ModelNotAvailable("The model file could not be loaded. Please retrain the model.")
        _class_names = names
        _model = model


def preprocess_image(path):
    """Read, convert to RGB, resize. Returns a (1, 224, 224, 3) float32 array in 0-255 range.
    (Pixel scaling for MobileNetV2 is part of the saved model itself.)"""
    import cv2
    try:
        data = np.fromfile(path, dtype=np.uint8)  # works with non-ASCII Windows paths
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        img = None
    if img is None:
        raise PredictionError("The image could not be read. Please upload a different photo.")
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, IMG_SIZE, interpolation=cv2.INTER_AREA)
    return np.expand_dims(img.astype("float32"), axis=0)


def predict_image(path, top_k=3):
    _load()
    x = preprocess_image(path)
    try:
        with _infer_lock:
            probs = _model.predict(x, verbose=0)[0]
    except Exception:
        raise PredictionError("Prediction failed. Please try again with another image.")

    order = np.argsort(probs)[::-1][:top_k]
    top = [{"label": _class_names[int(i)], "confidence": round(float(probs[i]) * 100, 1)} for i in order]
    best = top[0]
    crop, disease = parse_label(best["label"])
    return {
        "label": best["label"],
        "crop": crop,
        "disease": disease,
        "confidence": best["confidence"],
        "top": top,
        "low_confidence": best["confidence"] < LOW_CONFIDENCE,
    }


def supported_classes():
    """Human-readable names of the classes the trained model can recognise ([] when no model is trained)."""
    try:
        with open(CLASSES_PATH, encoding="utf-8") as f:
            return [" ".join(parse_label(n)) for n in json.load(f)]
    except (OSError, ValueError):
        return []
