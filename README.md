# Telegram Weather Bot

A lightweight, self-hosted Telegram weather bot that provides current weather conditions based on a shared Telegram location.

Built with:

* Python 3.12
* python-telegram-bot
* Open-Meteo
* OpenStreetMap Nominatim
* Docker
* Docker Compose

---

## Features

### Current Weather

* Temperature
* Feels-like temperature
* Humidity
* Cloud cover percentage
* Cloud cover description
* Wind direction (compass)
* Wind speed in Beaufort and km/h
* Sunrise
* Sunset

### Location Handling

* Share your location directly from Telegram
* High-precision reverse geocoding
* Neighbourhood/suburb-level location names when available

### Performance

* 5-minute in-memory weather cache
* Coordinate cache precision of approximately 100 meters
* Lightweight resource usage

### Deployment

* Dockerized
* Long polling
* No database required
* Suitable for VPS, Raspberry Pi, Proxmox, Docker, Portainer, and Kubernetes

---

## Example Response

```text
📍 Centrum, Amsterdam, Netherlands

🌡 Temperature: 18.4°C
🥶 Feels Like: 16.9°C

☁️ Cloud Cover: 35% (Partly cloudy)
💧 Humidity: 72%

💨 Wind: SW
💨 Speed: Bft 3 (14 km/h)

🌅 Sunrise: 05:18
🌇 Sunset: 22:03
```

---

## Stack

| Component         | Technology          |
| ----------------- | ------------------- |
| Bot Framework     | python-telegram-bot |
| Weather Provider  | Open-Meteo          |
| Reverse Geocoding | Nominatim           |
| Containerization  | Docker              |
| Deployment        | Docker Compose      |
| Runtime           | Python 3.12         |

---

## Project Structure

```text
weather-bot/
├── bot.py
├── weather.py
├── geocoding.py
├── utils.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env
├── .env.example
└── README.md
```

---

## Setup

### Create Telegram Bot

Message:

https://t.me/BotFather

Create a bot using:

```text
/newbot
```

Copy the bot token.

---

### Create Environment File

Create:

```bash
cp .env.example .env
```

Edit:

```env
BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
TZ=Europe/Amsterdam
```

---

## Local Docker Deployment

Build and start:

```bash
docker compose up -d --build
```

View logs:

```bash
docker compose logs -f
```

Stop:

```bash
docker compose down
```

---

## Portainer Deployment

### Stack Repository

Repository URL:

```text
git@github.com:ktj94/weather-bot.git
```

Reference:

```text
main
```

Compose Path:

```text
docker-compose.yml
```

Environment Variables:

```env
BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
TZ=Europe/Amsterdam
```

Deploy the stack.

---

## Weather Data Source

This project uses Open-Meteo:

https://open-meteo.com

No API key required.

---

## Reverse Geocoding

Location names are obtained from OpenStreetMap Nominatim:

https://nominatim.openstreetmap.org

The bot prioritizes:

1. Neighbourhood
2. Suburb
3. Quarter
4. Road
5. City
6. Country

to provide the most specific location possible.

---

## Wind Scale

Wind speed is shown using:

* Beaufort Scale (primary)
* km/h (secondary)

Example:

```text
💨 Speed: Bft 5 (34 km/h)
```

---

## Caching

Weather responses are cached for 5 minutes.

Coordinates are rounded to 3 decimal places before caching, providing approximately 100-meter cache granularity.

---


## Resource Usage

Typical usage:

```text
RAM: 50–100 MB
CPU: Near 0% while idle
```

Suitable for low-cost VPS deployments.

---

## License

Private project.
