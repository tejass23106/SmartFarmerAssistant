import os
import base64
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


API_URL = "https://api.plant.id/v3/identification"


class PlantHealthAPIError(Exception):
    pass


def analyze_plant_image(image_path):
    api_key = os.getenv("PLANT_HEALTH_API_KEY")

    if not api_key:
        raise PlantHealthAPIError(
            "Plant.id API key is missing. Check your .env file."
        )

    if not os.path.isfile(image_path):
        raise PlantHealthAPIError("Uploaded image was not found.")

    try:
        with open(image_path, "rb") as image:
            encoded = base64.b64encode(image.read()).decode("ascii")

        response = requests.post(
            API_URL,
            headers={
                "Api-Key": api_key,
                "Content-Type": "application/json"
            },
            json={
                "images": [encoded],
                "health": "all"
            },
            timeout=90
        )

        if not response.ok:
            raise PlantHealthAPIError(
                f"Plant.id API error ({response.status_code}): "
                f"{response.text[:500]}"
            )

        data = response.json()
        result = data.get("result", {})

        classification = (
            result.get("classification", {}).get("suggestions", [])
        )

        disease = result.get("disease", {}).get("suggestions", [])

        health = result.get("is_healthy", {})

        if not result:
            raise PlantHealthAPIError(
                "Plant.id returned an empty result."
            )

        return {
            "classification": classification[:5],
            "diseases": disease[:5],
            "healthy_probability": health.get("probability"),
            "api_access": True
        }

    except requests.RequestException as exc:
        raise PlantHealthAPIError(
            f"Could not connect to Plant.id: {exc}"
        ) from exc