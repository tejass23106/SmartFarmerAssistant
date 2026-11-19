import os
import random
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LEAF_DIR = ROOT / "dataset"
TUBER_DIR = ROOT / "datasets_processed" / "potato_tuber_split"
OUTPUT = ROOT / "datasets_processed" / "image_router_v1"

SEED = 42
EXTENSIONS = {".jpg", ".jpeg", ".png"}

random.seed(SEED)

def images_in(folder):
    return [
        p for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in EXTENSIONS
    ]

def place_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)

def split_images(files):
    files = list(files)
    random.shuffle(files)

    n = len(files)
    train_end = int(n * 0.70)
    val_end = int(n * 0.85)

    return {
        "train": files[:train_end],
        "val": files[train_end:val_end],
        "test": files[val_end:]
    }

if not LEAF_DIR.exists():
    raise SystemExit(f"Leaf dataset missing: {LEAF_DIR}")

if not TUBER_DIR.exists():
    raise SystemExit(f"Tuber split missing: {TUBER_DIR}")

# Recreate only the generated router dataset.
if OUTPUT.exists():
    shutil.rmtree(OUTPUT)

categories = {
    "potato_leaf": [],
    "tomato_leaf": [],
    "potato_tuber": []
}

for folder in LEAF_DIR.iterdir():
    if not folder.is_dir():
        continue

    if folder.name.startswith("Potato___"):
        categories["potato_leaf"].extend(images_in(folder))

    elif folder.name.startswith("Tomato___"):
        categories["tomato_leaf"].extend(images_in(folder))

for category in ("potato_leaf", "tomato_leaf"):
    if not categories[category]:
        raise SystemExit(f"No images found for {category}")

    splits = split_images(categories[category])

    for split, files in splits.items():
        for index, source in enumerate(files):
            destination = (
                OUTPUT / split / category /
                f"{index:06d}{source.suffix.lower()}"
            )
            place_file(source, destination)

# Preserve the existing tuber split.
for split in ("train", "val", "test"):
    split_dir = TUBER_DIR / split

    for source in images_in(split_dir):
        relative = source.relative_to(split_dir)
        destination = OUTPUT / split / "potato_tuber" / relative
        place_file(source, destination)

print("\nIMAGE ROUTER DATASET CREATED")

for split in ("train", "val", "test"):
    print(f"\n{split.upper()}")

    for category in categories:
        folder = OUTPUT / split / category
        count = len(images_in(folder)) if folder.exists() else 0
        print(f"{category}: {count}")

print(f"\nDataset location: {OUTPUT}")
