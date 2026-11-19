// EXAMPLE sketch: ESP32 + capacitive soil-moisture sensor posting readings to Smart Farmer Assistant.
// Not tested on hardware by the project author: calibrate AIR_VALUE / WATER_VALUE with your own sensor first.
// Create a device on the "Sensors" page of the app and paste its key below. Use https:// when the app is served over HTTPS.
#include <WiFi.h>
#include <HTTPClient.h>

const char* WIFI_SSID = "YOUR_WIFI";
const char* WIFI_PASS = "YOUR_PASSWORD";
const char* ENDPOINT  = "http://YOUR_SERVER_IP:5000/api/sensor-readings";
const char* DEVICE_KEY = "PASTE_DEVICE_KEY_HERE";
const int SENSOR_PIN = 34;          // analog input
const int AIR_VALUE = 3200;         // raw reading in dry air  (calibrate!)
const int WATER_VALUE = 1400;       // raw reading in water    (calibrate!)

void setup() {
  Serial.begin(115200);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
}

void loop() {
  int raw = analogRead(SENSOR_PIN);
  float moisture = constrain(map(raw, AIR_VALUE, WATER_VALUE, 0, 100), 0, 100);
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(ENDPOINT);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-Device-Key", DEVICE_KEY);
    String body = String("{\"soil_moisture\": ") + moisture + "}";
    int code = http.POST(body);
    Serial.println(code);
    http.end();
  }
  delay(15UL * 60UL * 1000UL);      // one reading every 15 minutes
}
