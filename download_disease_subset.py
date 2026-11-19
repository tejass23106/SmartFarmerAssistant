from pathlib import Path
from datasets import load_dataset

# Project dataset directory
DATASET_DIR = Path(__file__).parent / "dataset"
MAX_IMAGES_PER_CLASS = 500

# Exact Hugging Face caption -> existing project folder
CLASS_MAP = {
    "Potato healthy": "Potato___Healthy",
    "Potato Late blight": "Potato___Late_blight",
    "Tomato Early blight": "Tomato___Early_blight",
    "Tomato healthy": "Tomato___Healthy",
    "Tomato Late blight": "Tomato___Late_blight",
}

def existing_image_count(folder):
    extensions = {".jpg", ".jpeg", ".png"}
    return sum(
        1 for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in extensions
    )

def main():
    folders = {}

    for caption, folder_name in CLASS_MAP.items():
        folder = DATASET_DIR / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        folders[caption] = folder

    counts = {
        caption: existing_image_count(folder)
        for caption, folder in folders.items()
    }

    print("Existing images:")
    for caption, count in counts.items():
        print(f"{caption}: {count}/{MAX_IMAGES_PER_CLASS}")

    if all(count >= MAX_IMAGES_PER_CLASS for count in counts.values()):
        print("\nAll five classes already have enough images.")
        return

    print("\nConnecting to PlantVillage dataset...")

    ds = load_dataset(
        "manoela/plantvillage",
        split="train",
        streaming=True
    )

    for index, row in enumerate(ds, start=1):
        caption = row.get("caption")

        if caption not in CLASS_MAP:
            continue

        if counts[caption] >= MAX_IMAGES_PER_CLASS:
            continue

        image = row.get("image")

        if image is None:
            continue

        try:
            image = image.convert("RGB")

            filename = f"{CLASS_MAP[caption]}_{counts[caption] + 1:04d}.jpg"
            output_path = folders[caption] / filename

            image.save(output_path, format="JPEG", quality=95)
            counts[caption] += 1

            print(
                f"[{index}] {caption}: "
                f"{counts[caption]}/{MAX_IMAGES_PER_CLASS}"
            )

        except Exception as error:
            print(f"Skipping an image: {error}")

        if all(count >= MAX_IMAGES_PER_CLASS for count in counts.values()):
            break

    print("\nDOWNLOAD SUMMARY")
    for caption, count in counts.items():
        print(f"{caption}: {count}/{MAX_IMAGES_PER_CLASS}")

    if all(count >= MAX_IMAGES_PER_CLASS for count in counts.values()):
        print("\nSUCCESS: All five classes have 500 images.")
    else:
        print("\nWARNING: Some classes have fewer than 500 images.")

if __name__ == "__main__":
    main()
