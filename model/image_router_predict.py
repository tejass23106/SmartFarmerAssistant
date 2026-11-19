import json
import os
import threading

import numpy as np
import tensorflow as tf


BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODEL_PATH = os.path.join(BASE, "model", "image_router_model.keras")
CLASS_PATH = os.path.join(BASE, "model", "image_router_class_names.json")

IMAGE_SIZE = (224, 224)

# Conservative preliminary routing thresholds.
MIN_CONFIDENCE = 0.85
MIN_MARGIN = 0.20

_model = None
_class_names = None
_lock = threading.Lock()


class ImageRouterError(Exception):
    pass


class RouterModelNotAvailable(ImageRouterError):
    pass


def _load_model():
    global _model, _class_names

    with _lock:
        if _model is not None:
            return _model, _class_names

        if not os.path.exists(MODEL_PATH) or not os.path.exists(CLASS_PATH):
            raise RouterModelNotAvailable(
                "Image detection model is unavailable."
            )

        try:
            with open(CLASS_PATH, encoding="utf-8") as file:
                _class_names = json.load(file)

            _model = tf.keras.models.load_model(
                MODEL_PATH,
                compile=False
            )

        except Exception as exc:
            raise RouterModelNotAvailable(
                "Could not load the image detection model."
            ) from exc

        return _model, _class_names


def predict_image_type(image_path):
    model, class_names = _load_model()

    try:
        image = tf.keras.utils.load_img(
            image_path,
            target_size=IMAGE_SIZE,
            color_mode="rgb"
        )

        image_array = tf.keras.utils.img_to_array(image)
        image_array = np.expand_dims(image_array, axis=0)

        probabilities = model.predict(image_array, verbose=0)[0]

        order = np.argsort(probabilities)[::-1]

        best_index = int(order[0])
        second_index = int(order[1])

        confidence = float(probabilities[best_index])
        second_confidence = float(probabilities[second_index])
        margin = confidence - second_confidence

        category = class_names[best_index]

        if confidence < MIN_CONFIDENCE or margin < MIN_MARGIN:
            raise ImageRouterError(
                "Image type is uncertain. Upload a clear image of a "
                "potato leaf, tomato leaf, or potato tuber."
            )

        return {
            "category": category,
            "confidence": confidence * 100,
            "margin": margin * 100
        }

    except ImageRouterError:
        raise

    except Exception as exc:
        raise ImageRouterError(
            "Could not analyse the uploaded image. Please try another image."
        ) from exc
