import os
import sys
import base64
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("CROP_HEALTH_API_KEY")

if not API_KEY:
    print("API key missing in .env")
    sys.exit(1)

if len(sys.argv) < 2 or not os.path.isfile(sys.argv[1]):
    print("Usage: python test_crop_health.py <image_path>")
    sys.exit(1)

image_path = sys.argv[1]

with open(image_path, "rb") as f:
    encoded = base64.b64encode(f.read()).decode("ascii")

url = "https://crop.kindwise.com/api/v1/identification"

headers = {
    "Api-Key": API_KEY,
    "Content-Type": "application/json"
}

payload = {
    "images": [encoded]
}

params = {
    "details": "common_names,description,treatment,symptoms,severity",
    "language": "en"
}

try:
    response = requests.post(
        url,
        headers=headers,
        params=params,
        json=payload,
        timeout=90
    )

    if not response.ok:
        print("API Error:", response.status_code)
        print(response.text[:1500])
        sys.exit(1)

    data = response.json()
    result = data.get("result", {})

    print("\n========== CROP HEALTH ==========")

    print("\nCROP:")
    for item in result.get("crop", {}).get("suggestions", [])[:3]:
        print(f"{item['name']}: {item['probability'] * 100:.2f}%")

    print("\nDISEASES / PESTS:")
    for item in result.get("disease", {}).get("suggestions", [])[:5]:
        print(f"{item['name']}: {item['probability'] * 100:.2f}%")

    print("\n=================================")

    if not result.get("crop", {}).get("suggestions"):
        print("No crop identification returned.")

    if not result.get("disease", {}).get("suggestions"):
        print("No disease suggestions returned.")

except requests.RequestException as e:
    print("Connection error:", e)

except (KeyError, TypeError, ValueError) as e:
    print("Unexpected API response:", e)