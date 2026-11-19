"""Train a potato tuber disease classifier using MobileNetV2."""

import argparse
import json
import os
import sys

import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATASET_DIR = os.path.join(
    BASE, "datasets_processed", "potato_tuber_split"
)
OUT_DIR = os.path.join(BASE, "model")

MODEL_PATH = os.path.join(OUT_DIR, "potato_tuber_model.keras")
CLASSES_PATH = os.path.join(OUT_DIR, "potato_tuber_class_names.json")

IMG_SIZE = (224, 224)
BATCH_SIZE = 32
SEED = 42
IMG_EXTS = (".jpg", ".jpeg", ".png")

parser = argparse.ArgumentParser()
parser.add_argument("--epochs", type=int, default=8)
parser.add_argument("--fine-tune", type=int, default=5)
args = parser.parse_args()

if args.epochs < 1 or args.fine_tune < 0:
    sys.exit("Invalid epoch values.")

if not os.path.isdir(DATASET_DIR):
    sys.exit(f"Dataset not found: {DATASET_DIR}")

class_names = sorted([
    name for name in os.listdir(os.path.join(DATASET_DIR, "train"))
    if os.path.isdir(os.path.join(DATASET_DIR, "train", name))
])

if len(class_names) != 10:
    sys.exit(f"Expected 10 classes, found {len(class_names)}")

# Check that all splits contain the same classes.
for split in ("train", "val", "test"):
    split_dir = os.path.join(DATASET_DIR, split)
    if not os.path.isdir(split_dir):
        sys.exit(f"Missing split: {split}")

    found = sorted([
        name for name in os.listdir(split_dir)
        if os.path.isdir(os.path.join(split_dir, name))
    ])

    if found != class_names:
        sys.exit(f"Class mismatch in {split} directory.")

# Prevent accidental replacement of the existing tuber model.
if os.path.exists(MODEL_PATH):
    sys.exit(
        f"Tuber model already exists: {MODEL_PATH}\n"
        "Move or rename it before training again."
    )

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers

from sklearn.utils.class_weight import compute_class_weight
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix
)

print("\nPOTATO TUBER CLASSIFIER")
print("=" * 45)

# 1. Load separate training, validation and test datasets.
common = {
    "image_size": IMG_SIZE,
    "batch_size": BATCH_SIZE,
    "class_names": class_names,
    "label_mode": "int"
}

train_ds = keras.utils.image_dataset_from_directory(
    os.path.join(DATASET_DIR, "train"),
    shuffle=True,
    seed=SEED,
    **common
)

val_ds = keras.utils.image_dataset_from_directory(
    os.path.join(DATASET_DIR, "val"),
    shuffle=False,
    **common
)

test_ds = keras.utils.image_dataset_from_directory(
    os.path.join(DATASET_DIR, "test"),
    shuffle=False,
    **common
)

# 2. Calculate class weights from training data.
train_counts = []

for class_name in class_names:
    folder = os.path.join(DATASET_DIR, "train", class_name)
    count = sum(
        1 for file in os.listdir(folder)
        if file.lower().endswith(IMG_EXTS)
    )
    train_counts.append(count)

weights = compute_class_weight(
    class_weight="balanced",
    classes=np.arange(len(class_names)),
    y=np.concatenate([
        np.full(count, index)
        for index, count in enumerate(train_counts)
    ])
)

class_weights = {
    index: float(weight)
    for index, weight in enumerate(weights)
}

print("\nCLASS DISTRIBUTION:")
for name, count, weight in zip(class_names, train_counts, weights):
    print(f"{name}: {count} images | weight: {weight:.3f}")

# 3. Optimize data pipeline.
AUTOTUNE = tf.data.AUTOTUNE

train_ds = train_ds.prefetch(AUTOTUNE)
val_ds = val_ds.prefetch(AUTOTUNE)
test_ds = test_ds.prefetch(AUTOTUNE)

# 4. Data augmentation.
augmentation = keras.Sequential([
    layers.RandomFlip("horizontal"),
    layers.RandomRotation(0.10),
    layers.RandomZoom(0.10),
    layers.RandomContrast(0.10)
], name="tuber_augmentation")

# 5. MobileNetV2 transfer learning.
try:
    base = keras.applications.MobileNetV2(
        input_shape=IMG_SIZE + (3,),
        include_top=False,
        weights="imagenet"
    )
except Exception as exc:
    sys.exit(
        "Could not load pretrained MobileNetV2 weights. "
        "Check your internet connection.\n" + str(exc)
    )

base.trainable = False

inputs = keras.Input(shape=IMG_SIZE + (3,))

x = augmentation(inputs)
x = layers.Rescaling(
    1.0 / 127.5,
    offset=-1
)(x)

x = base(x, training=False)
x = layers.GlobalAveragePooling2D()(x)
x = layers.Dropout(0.35)(x)

outputs = layers.Dense(
    len(class_names),
    activation="softmax"
)(x)

model = keras.Model(inputs, outputs)

# 6. Callbacks.
os.makedirs(OUT_DIR, exist_ok=True)

checkpoint = keras.callbacks.ModelCheckpoint(
    MODEL_PATH,
    monitor="val_loss",
    save_best_only=True,
    verbose=1
)

early_stopping = keras.callbacks.EarlyStopping(
    monitor="val_loss",
    patience=3,
    restore_best_weights=True,
    verbose=1
)

reduce_lr = keras.callbacks.ReduceLROnPlateau(
    monitor="val_loss",
    factor=0.3,
    patience=2,
    min_lr=1e-7,
    verbose=1
)

callbacks = [
    checkpoint,
    early_stopping,
    reduce_lr
]

# 7. Phase one: train classifier head.
print("\nPHASE 1: TRAINING CLASSIFIER HEAD")

model.compile(
    optimizer=keras.optimizers.Adam(learning_rate=1e-3),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"]
)

history = model.fit(
    train_ds,
    validation_data=val_ds,
    epochs=args.epochs,
    class_weight=class_weights,
    callbacks=callbacks
)

train_accuracy = list(history.history["accuracy"])
val_accuracy = list(history.history["val_accuracy"])

# 8. Phase two: fine-tune top MobileNetV2 layers.
if args.fine_tune > 0:
    print("\nPHASE 2: FINE-TUNING")

    base.trainable = True

    for layer in base.layers[:-30]:
        layer.trainable = False

    # Keep Batch Normalization layers frozen.
    for layer in base.layers:
        if isinstance(layer, layers.BatchNormalization):
            layer.trainable = False

    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=1e-5),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"]
    )

    history2 = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=args.fine_tune,
        class_weight=class_weights,
        callbacks=callbacks
    )

    train_accuracy += history2.history["accuracy"]
    val_accuracy += history2.history["val_accuracy"]

# 9. Load best validation checkpoint.
print("\nLOADING BEST MODEL")

model = keras.models.load_model(MODEL_PATH)

# Save class labels separately.
with open(CLASSES_PATH, "w", encoding="utf-8") as file:
    json.dump(class_names, file, indent=2)

# 10. Final evaluation on untouched test set.
print("\nFINAL TEST EVALUATION")

y_true = []
y_pred = []

for images, labels in test_ds:
    predictions = model(images, training=False).numpy()

    y_true.extend(labels.numpy().tolist())
    y_pred.extend(np.argmax(predictions, axis=1).tolist())

accuracy = accuracy_score(y_true, y_pred)

report_text = classification_report(
    y_true,
    y_pred,
    target_names=class_names,
    labels=list(range(len(class_names))),
    digits=3,
    zero_division=0
)

report = classification_report(
    y_true,
    y_pred,
    target_names=class_names,
    labels=list(range(len(class_names))),
    output_dict=True,
    zero_division=0
)

print("\nTEST ACCURACY: %.2f%%" % (accuracy * 100))
print(report_text)

# 11. Save evaluation metrics.
metrics = {
    "model": "MobileNetV2",
    "dataset": "potato_tuber_v1",
    "classes": class_names,
    "test_accuracy": float(accuracy),
    "report": report
}

with open(
    os.path.join(OUT_DIR, "potato_tuber_metrics.json"),
    "w",
    encoding="utf-8"
) as file:
    json.dump(metrics, file, indent=2)

# 12. Save training history.
plt.figure(figsize=(8, 5))
plt.plot(train_accuracy, label="Training accuracy")
plt.plot(val_accuracy, label="Validation accuracy")
plt.xlabel("Epoch")
plt.ylabel("Accuracy")
plt.title("Potato Tuber Model Training")
plt.legend()
plt.tight_layout()

plt.savefig(
    os.path.join(OUT_DIR, "potato_tuber_training_history.png"),
    dpi=150
)
plt.close()

# 13. Save confusion matrix.
cm = confusion_matrix(
    y_true,
    y_pred,
    labels=list(range(len(class_names)))
)

plt.figure(figsize=(11, 9))
plt.imshow(cm, cmap="Blues")
plt.colorbar()

plt.xticks(
    range(len(class_names)),
    class_names,
    rotation=45,
    ha="right",
    fontsize=8
)

plt.yticks(
    range(len(class_names)),
    class_names,
    fontsize=8
)

for i in range(cm.shape[0]):
    for j in range(cm.shape[1]):
        plt.text(
            j, i, cm[i, j],
            ha="center",
            va="center",
            fontsize=8
        )

plt.xlabel("Predicted")
plt.ylabel("Actual")
plt.title("Potato Tuber Confusion Matrix")
plt.tight_layout()

plt.savefig(
    os.path.join(OUT_DIR, "potato_tuber_confusion_matrix.png"),
    dpi=150
)
plt.close()

print("\nTRAINING COMPLETED")
print("Model:", MODEL_PATH)
print("Labels:", CLASSES_PATH)
print("Test accuracy: %.2f%%" % (accuracy * 100))
