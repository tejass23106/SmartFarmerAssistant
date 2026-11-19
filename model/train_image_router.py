import os
import json
import numpy as np
import tensorflow as tf

from pathlib import Path
from sklearn.utils.class_weight import compute_class_weight
from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    classification_report,
    confusion_matrix
)
from tensorflow.keras import layers, models
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.callbacks import (
    EarlyStopping,
    ReduceLROnPlateau,
    ModelCheckpoint
)

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BASE = Path(__file__).resolve().parent.parent

DATASET = BASE / "datasets_processed" / "image_router_v1"
MODEL_DIR = BASE / "model"

MODEL_PATH = MODEL_DIR / "image_router_model.keras"
CLASS_PATH = MODEL_DIR / "image_router_class_names.json"
METRICS_PATH = MODEL_DIR / "image_router_metrics.json"
CONFUSION_PATH = MODEL_DIR / "image_router_confusion_matrix.png"

IMG_SIZE = (224, 224)
BATCH_SIZE = 32
EPOCHS = 15
SEED = 42

CLASS_NAMES = [
    "potato_leaf",
    "tomato_leaf",
    "potato_tuber"
]

tf.keras.utils.set_random_seed(SEED)

MODEL_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------
# CHECK DATASET
# --------------------------------------------------

for split in ("train", "val", "test"):
    for category in CLASS_NAMES:
        folder = DATASET / split / category

        if not folder.exists():
            raise FileNotFoundError(f"Missing folder: {folder}")

print("\nLoading image datasets...")

train_ds = tf.keras.utils.image_dataset_from_directory(
    DATASET / "train",
    class_names=CLASS_NAMES,
    image_size=IMG_SIZE,
    batch_size=BATCH_SIZE,
    label_mode="int",
    shuffle=True,
    seed=SEED
)

val_ds = tf.keras.utils.image_dataset_from_directory(
    DATASET / "val",
    class_names=CLASS_NAMES,
    image_size=IMG_SIZE,
    batch_size=BATCH_SIZE,
    label_mode="int",
    shuffle=False
)

test_ds = tf.keras.utils.image_dataset_from_directory(
    DATASET / "test",
    class_names=CLASS_NAMES,
    image_size=IMG_SIZE,
    batch_size=BATCH_SIZE,
    label_mode="int",
    shuffle=False
)

print("\nClass mapping:", train_ds.class_names)

# --------------------------------------------------
# CLASS WEIGHTS
# --------------------------------------------------

train_counts = np.array([
    len(list((DATASET / "train" / name).glob("*")))
    for name in CLASS_NAMES
])

weights = compute_class_weight(
    class_weight="balanced",
    classes=np.arange(len(CLASS_NAMES)),
    y=np.concatenate([
        np.full(count, index)
        for index, count in enumerate(train_counts)
    ])
)

class_weights = {
    index: float(weight)
    for index, weight in enumerate(weights)
}

print("\nTraining image counts:")
for name, count in zip(CLASS_NAMES, train_counts):
    print(f"{name}: {count}")

print("\nClass weights:", class_weights)

# --------------------------------------------------
# PERFORMANCE
# --------------------------------------------------

AUTOTUNE = tf.data.AUTOTUNE

train_ds = train_ds.prefetch(AUTOTUNE)
val_ds = val_ds.prefetch(AUTOTUNE)
test_ds = test_ds.prefetch(AUTOTUNE)

# --------------------------------------------------
# DATA AUGMENTATION
# --------------------------------------------------

augmentation = tf.keras.Sequential([
    layers.RandomFlip("horizontal"),
    layers.RandomRotation(0.08),
    layers.RandomZoom(0.12),
    layers.RandomContrast(0.10)
], name="data_augmentation")

# --------------------------------------------------
# MOBILENETV2 BASE MODEL
# --------------------------------------------------

base_model = MobileNetV2(
    input_shape=(224, 224, 3),
    include_top=False,
    weights="imagenet"
)

base_model.trainable = False

inputs = layers.Input(shape=(224, 224, 3))

x = augmentation(inputs)

# MobileNetV2 expects pixels normalized to [-1, 1].
x = layers.Rescaling(
    scale=1.0 / 127.5,
    offset=-1
)(x)

x = base_model(x, training=False)

x = layers.GlobalAveragePooling2D()(x)
x = layers.Dropout(0.35)(x)

outputs = layers.Dense(
    len(CLASS_NAMES),
    activation="softmax"
)(x)

model = models.Model(inputs, outputs)

model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"]
)

model.summary()

# --------------------------------------------------
# CALLBACKS
# --------------------------------------------------

callbacks = [
    ModelCheckpoint(
        filepath=str(MODEL_PATH),
        monitor="val_loss",
        save_best_only=True,
        verbose=1
    ),

    EarlyStopping(
        monitor="val_loss",
        patience=4,
        restore_best_weights=True,
        verbose=1
    ),

    ReduceLROnPlateau(
        monitor="val_loss",
        factor=0.3,
        patience=2,
        min_lr=1e-6,
        verbose=1
    )
]

# --------------------------------------------------
# TRAIN
# --------------------------------------------------

print("\nStarting router training...\n")

history = model.fit(
    train_ds,
    validation_data=val_ds,
    epochs=EPOCHS,
    class_weight=class_weights,
    callbacks=callbacks
)

# --------------------------------------------------
# LOAD BEST MODEL
# --------------------------------------------------

print("\nLoading best saved model...")

model = tf.keras.models.load_model(MODEL_PATH)

# --------------------------------------------------
# TEST EVALUATION
# --------------------------------------------------

print("\nEvaluating on independent test dataset...")

y_true = np.concatenate([
    labels.numpy()
    for _, labels in test_ds
])

probabilities = model.predict(test_ds, verbose=1)
y_pred = np.argmax(probabilities, axis=1)

accuracy = accuracy_score(y_true, y_pred)

precision, recall, f1, _ = precision_recall_fscore_support(
    y_true,
    y_pred,
    labels=np.arange(len(CLASS_NAMES)),
    average="macro",
    zero_division=0
)

report = classification_report(
    y_true,
    y_pred,
    labels=np.arange(len(CLASS_NAMES)),
    target_names=CLASS_NAMES,
    zero_division=0,
    output_dict=True
)

cm = confusion_matrix(
    y_true,
    y_pred,
    labels=np.arange(len(CLASS_NAMES))
)

print("\nCLASSIFICATION REPORT")
print(classification_report(
    y_true,
    y_pred,
    labels=np.arange(len(CLASS_NAMES)),
    target_names=CLASS_NAMES,
    zero_division=0
))

print("\nTEST RESULTS")
print(f"Accuracy : {accuracy * 100:.2f}%")
print(f"Precision: {precision * 100:.2f}%")
print(f"Recall   : {recall * 100:.2f}%")
print(f"Macro F1 : {f1 * 100:.2f}%")

# --------------------------------------------------
# SAVE RESULTS
# --------------------------------------------------

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.figure(figsize=(8, 6))
plt.imshow(cm, interpolation="nearest")
plt.title("Image Router Confusion Matrix")
plt.colorbar()

plt.xticks(
    np.arange(len(CLASS_NAMES)),
    CLASS_NAMES,
    rotation=25,
    ha="right"
)

plt.yticks(np.arange(len(CLASS_NAMES)), CLASS_NAMES)
plt.xlabel("Predicted")
plt.ylabel("Actual")

for i in range(cm.shape[0]):
    for j in range(cm.shape[1]):
        plt.text(j, i, str(cm[i, j]), ha="center", va="center")

plt.tight_layout()
plt.savefig(CONFUSION_PATH, dpi=150)
plt.close()

with open(CLASS_PATH, "w", encoding="utf-8") as file:
    json.dump(CLASS_NAMES, file, indent=4)

metrics = {
    "accuracy": float(accuracy),
    "macro_precision": float(precision),
    "macro_recall": float(recall),
    "macro_f1": float(f1),
    "class_names": CLASS_NAMES,
    "class_counts": {
        name: int(count)
        for name, count in zip(CLASS_NAMES, train_counts)
    },
    "classification_report": report,
    "confusion_matrix": cm.tolist()
}

with open(METRICS_PATH, "w", encoding="utf-8") as file:
    json.dump(metrics, file, indent=4)

print("\nROUTER TRAINING COMPLETED")
print(f"Model: {MODEL_PATH}")
print(f"Classes: {CLASS_PATH}")
print(f"Metrics: {METRICS_PATH}")
print(f"Confusion matrix: {CONFUSION_PATH}")
