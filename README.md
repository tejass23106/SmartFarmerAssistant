# 🌱 Smart Farmer Assistant

An AI-powered agriculture assistance platform designed to help farmers make smarter farming decisions through crop recommendations, plant disease detection, weather insights, market prices and intelligent farming tools.

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0-black?logo=flask)
![Database](https://img.shields.io/badge/Database-Turso-blue)
![Deployment](https://img.shields.io/badge/Deployment-Vercel-black?logo=vercel)
![Status](https://img.shields.io/badge/Status-Active-brightgreen)

---

## 🚀 Live Demo

**Live Application:** https://smart-farmer-assistant.vercel.app/  

## ✨ Features

### 🌾 Farmer Features

- **Crop Recommendation** – Get crop suggestions using soil-test values or quick farming inputs.
- **Plant Disease Detection** – Analyze plant images using the Plant.id API.
- **Weather Information** – View current weather conditions and forecasts.
- **Smart Irrigation** – Get irrigation recommendations and water-management guidance.
- **Fertilizer Recommendations** – Receive fertilizer guidance based on soil nutrient information.
- **Market Prices** – Explore agricultural market prices using the data.gov.in API.
- **AI Farming Assistant** – Get AI-powered farming assistance using Google Gemini.
- **Farming Calendar** – Organize crop activities, stages and reminders.
- **Government Schemes** – Explore agricultural schemes and eligibility information.
- **Disease Reports** – Submit and track plant disease reports.
- **Farm Management** – Maintain farm details and farming history.
- **Notifications** – Receive updates about farming activities and reports.

### 🛠️ Administrator Features

- Admin dashboard with application statistics.
- Farmer account management.
- Disease report management.
- Crop and disease information management.
- Farming advisory management.
- Government scheme management.
- PDF and Excel report exports.

### 🌐 Additional Features

- English, Kannada and Hindi language support.
- Responsive web interface.
- User authentication and role-based access.
- Sensor integration support for ESP32 and Arduino.
- Secure API key handling through environment variables.

---

## 🧰 Tech Stack

| Category | Technologies |
|---|---|
| Frontend | HTML5, CSS3, Bootstrap 5, JavaScript |
| Backend | Python, Flask |
| Database | Turso, SQLite |
| AI Integration | Google Gemini API |
| Plant Analysis | Plant.id API |
| Weather | Open-Meteo API |
| Market Data | data.gov.in API |
| PDF Export | ReportLab |
| Excel Export | OpenPyXL |
| Deployment | Vercel |
| Version Control | Git, GitHub |

---

## ⚙️ Local Installation

### 1. Clone the repository

```bash
git clone https://github.com/tejass23106/SmartFarmerAssistant.git
cd SmartFarmerAssistant
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it on Windows:

```powershell
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root.

Add the following variables:

```env
SECRET_KEY=your_secret_key

ADMIN_EMAIL=your_admin_email
ADMIN_PASSWORD=your_admin_password

GEMINI_API_KEY=your_gemini_api_key
PLANT_HEALTH_API_KEY=your_plant_health_api_key
MARKET_API_KEY=your_market_api_key

TURSO_DATABASE_URL=your_turso_database_url
TURSO_AUTH_TOKEN=your_turso_auth_token
```

Never commit your `.env` file or expose API keys publicly.

### 5. Run the application

```bash
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

---

## 🌐 Deployment

The application is configured for deployment on **Vercel**.

### Deployment Configuration

| Setting | Value |
|---|---|
| Platform | Vercel |
| Framework | Flask |
| Runtime | Python 3.12 |
| Database | Turso |
| Repository | GitHub |

### Required Environment Variables

Configure these variables in your Vercel project:

- `SECRET_KEY`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`
- `GEMINI_API_KEY`
- `PLANT_HEALTH_API_KEY`
- `MARKET_API_KEY`
- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN`

Make sure the variables are configured for the Production environment.

---

## 🗄️ Database

The project supports:

- **SQLite** for local development.
- **Turso** for remote database hosting.

Turso provides persistent database storage for the deployed application.

Database initialization and schema migrations are handled by the project's database utilities.

---

## 📌 Project Status

| Component | Status |
|---|---|
| Flask Application | Implemented |
| Farmer Authentication | Implemented |
| Admin Dashboard | Implemented |
| Crop Recommendation | Implemented |
| Plant Disease Detection API | Integrated |
| Weather Integration | Implemented |
| Market Price API | Integrated |
| Gemini AI Assistant | Integrated |
| Turso Database | Integrated |
| PDF and Excel Export | Implemented |
| Vercel Deployment | Testing |

---

## ⚠️ Known Limitations

- Crop recommendations are advisory suggestions and should be validated against local agricultural conditions.
- Plant disease detection depends on the external Plant.id API and image quality.
- Weather and market information depend on external API availability.
- AI-generated farming guidance may require verification by agricultural experts.
- Uploaded files on serverless deployments may require external persistent storage.
- Sensor functionality requires compatible hardware and configuration.

---

## 🔐 Security

- Password hashing.
- Role-based access control.
- CSRF protection.
- Environment-based secret management.
- Server-side API key handling.
- Input validation and upload restrictions.
- Secure session configuration.

---

## 📄 Disclaimer

Smart Farmer Assistant is an educational agriculture-support project. Its recommendations are intended for informational purposes and should not replace professional agricultural advice.

---

## 👨‍💻 Developer

**Tejas Kumar S**

Repository: [SmartFarmerAssistant](https://github.com/tejass23106/SmartFarmerAssistant)