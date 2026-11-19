import os
import sys
import base64
import requests
import json
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("PLANT_HEALTH_API_KEY")

if not API_KEY:
    print("Plant.id API key missing in .env")
    sys.exit(1)

if len(sys.argv) < 2 or not os.path.isfile(sys.argv[1]):
    print("Usage: python test_plant_health.py <image_path>")
    sys.exit(1)

image_path = sys.argv[1]

with open(image_path, "rb") as f:
    encoded = base64.b64encode(f.read()).decode("ascii")

url = "https://api.plant.id/v3/identification"

headers = {
    "Api-Key": API_KEY,
    "Content-Type": "application/json"
}

payload = {
    "images": [encoded],
    "health": "all"
}

try:
    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=90
    )

    print("HTTP Status:", response.status_code)

    if not response.ok:
        print(response.text[:2000])
        sys.exit(1)

    data = response.json()

    print("\n========== PLANT.HEALTH RESULTS ==========")

    result = data.get("result", {})

    print("\nPLANT IDENTIFICATION:")

    for item in result.get("classification", {}).get("suggestions", [])[:5]:
        print(
            f"{item.get('name')}: "
            f"{item.get('probability', 0) * 100:.2f}%"
        )

    print("\nHEALTH ASSESSMENT:")

    health = result.get("is_healthy", {})
    print("Healthy probability:", health.get("probability"))

    disease = result.get("disease", {})

    for item in disease.get("suggestions", [])[:5]:
        print(
            f"{item.get('name')}: "
            f"{item.get('probability', 0) * 100:.2f}%"
        )

    print("\n==========================================")

    if not result:
        print(json.dumps(data, indent=2)[:5000])

except requests.RequestException as error:
    print("Connection error:", error)