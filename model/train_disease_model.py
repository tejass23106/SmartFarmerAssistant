"""Train the crop disease classifier (MobileNetV2 transfer learning).

Usage (from the project root):
    python model/train_disease_model.py
    python model/train_disease_model.py --epochs 3 --fine-tune 0     # quick test run

Outputs (in model/): disease_model.keras, class_names.json, metrics.json,
                     training_history.png, confusion_matrix.png
"""
import argparse
import json
import os
import sys

import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(BASE, "dataset")
OUT_DIR = os.path.join(BASE, "model")
MODEL_PATH = os.path.join(OUT_DIR, "disease_model.keras")
CLASSES_PATH = os.path.join(OUT_DIR, "class_names.json")
IMG_SIZE = (224, 224)
BATCH_SIZE = 32
SEED = 42
IMG_EXTS = (".jpg", ".jpeg", ".png")

parser = argparse.ArgumentParser()
parser.add_argument("--epochs", type=int, default=8, help="epochs with the base model frozen")
parser.add_argument("--fine-tune", type=int, default=5, help="extra epochs fine-tuning top layers (0 to skip)")
args = parser.parse_args()


def find_classes(directory):
    found = []
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        if os.path.isdir(path):
            count = sum(1 for f in os.listdir(path) if f.lower().endswith(IMG_EXTS))
            if count > 0:
                found.append((name, count))
    return found


# ---------- 1. Check dataset ----------
if not os.path.isdir(DATASET_DIR):
    sys.exit(f"Dataset folder not found: {DATASET_DIR}\nSee the dataset instructions in the README.")
classes = find_classes(DATASET_DIR)
if len(classes) < 2:
    sys.exit("Need at least 2 class folders containing .jpg/.jpeg/.png images inside dataset/.")
print("Classes found:")
for name, count in classes:
    flag = "  <-- very few images" if count < 50 else ""
    print(f"  {name}: {count}{flag}")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

class_names = [c[0] for c in classes]
counts = np.array([c[1] for c in classes], dtype=float)
class_weight = {i: float(counts.sum() / (len(counts) * counts[i])) for i in range(len(counts))}

# ---------- 2. Load data with 80/20 train/validation split ----------
common = dict(validation_split=0.2, seed=SEED, image_size=IMG_SIZE,
              batch_size=BATCH_SIZE, class_names=class_names)
train_ds = keras.utils.image_dataset_from_directory(DATASET_DIR, subset="training", **common)
val_ds = keras.utils.image_dataset_from_directory(DATASET_DIR, subset="validation", **common)
train_ds = train_ds.prefetch(tf.data.AUTOTUNE)
val_ds = val_ds.prefetch(tf.data.AUTOTUNE)

# ---------- 3. Build model: augmentation + MobileNetV2 + classifier head ----------
augment = keras.Sequential([
    layers.RandomFlip("horizontal_and_vertical"),
    layers.RandomRotation(0.15),
    layers.RandomZoom(0.15),
    layers.RandomContrast(0.1),
], name="augmentation")  # only active during training

try:
    base = keras.applications.MobileNetV2(input_shape=IMG_SIZE + (3,), include_top=False, weights="imagenet")
except Exception as exc:
    sys.exit("Could not download the pretrained MobileNetV2 weights (internet needed on first run).\n"
             f"Details: {exc}")
base.trainable = False

inputs = keras.Input(shape=IMG_SIZE + (3,))
x = augment(inputs)
x = layers.Rescaling(1.0 / 127.5, offset=-1)(x)   # MobileNetV2 expects pixels in [-1, 1]
x = base(x, training=False)
x = layers.GlobalAveragePooling2D()(x)
x = layers.Dropout(0.3)(x)
outputs = layers.Dense(len(class_names), activation="softmax")(x)
model = keras.Model(inputs, outputs)

# ---------- 4. Train (phase 1: head only) ----------
model.compile(optimizer=keras.optimizers.Adam(1e-3),
              loss="sparse_categorical_crossentropy", metrics=["accuracy"])
early = keras.callbacks.EarlyStopping(monitor="val_loss", patience=3, restore_best_weights=True)
history = model.fit(train_ds, validation_data=val_ds, epochs=args.epochs,
                    class_weight=class_weight, callbacks=[early])
acc = list(history.history["accuracy"])
val_acc = list(history.history["val_accuracy"])

# ---------- 4b. Phase 2: fine-tune top layers of the base ----------
if args.fine_tune > 0:
    base.trainable = True
    for layer in base.layers[:-30]:
        layer.trainable = False
    model.compile(optimizer=keras.optimizers.Adam(1e-5),
                  loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    h2 = model.fit(train_ds, validation_data=val_ds, epochs=args.fine_tune,
                   class_weight=class_weight, callbacks=[early])
    acc += h2.history["accuracy"]
    val_acc += h2.history["val_accuracy"]

# ---------- 5. Evaluate ----------
y_true, y_pred = [], []
for images, labels in val_ds:
    probs = model(images, training=False).numpy()
    y_true.extend(labels.numpy().tolist())
    y_pred.extend(np.argmax(probs, axis=1).tolist())

accuracy = accuracy_score(y_true, y_pred)
report = classification_report(y_true, y_pred, target_names=class_names, digits=3, output_dict=True,
                               labels=list(range(len(class_names))), zero_division=0)
print("\nValidation accuracy: %.2f%%" % (accuracy * 100))
print(classification_report(y_true, y_pred, target_names=class_names, digits=3,
                            labels=list(range(len(class_names))), zero_division=0))

# ---------- 6. Save model, labels, metrics, plots ----------
os.makedirs(OUT_DIR, exist_ok=True)
model.save(MODEL_PATH)
with open(CLASSES_PATH, "w", encoding="utf-8") as f:
    json.dump(class_names, f, indent=2)
with open(os.path.join(OUT_DIR, "metrics.json"), "w", encoding="utf-8") as f:
    json.dump({"validation_accuracy": accuracy, "classes": class_names, "report": report}, f, indent=2)

plt.figure(figsize=(6, 4))
plt.plot(acc, label="train accuracy")
plt.plot(val_acc, label="validation accuracy")
plt.xlabel("Epoch"); plt.ylabel("Accuracy"); plt.legend(); plt.title("Training history"); plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "training_history.png"), dpi=120)
plt.close()

cm = confusion_matrix(y_true, y_pred, labels=list(range(len(class_names))))
plt.figure(figsize=(7, 6))
plt.imshow(cm, cmap="Greens")
plt.xticks(range(len(class_names)), class_names, rotation=45, ha="right", fontsize=7)
plt.yticks(range(len(class_names)), class_names, fontsize=7)
for i in range(cm.shape[0]):
    for j in range(cm.shape[1]):
        plt.text(j, i, cm[i, j], ha="center", va="center", fontsize=8)
plt.xlabel("Predicted"); plt.ylabel("Actual"); plt.title("Confusion matrix"); plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "confusion_matrix.png"), dpi=120)
plt.close()

print("Saved:", MODEL_PATH)
