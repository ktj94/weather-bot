# Telegram Weather Bot

A lightweight, self-hosted Telegram bot that replies with current weather when you share your location.

## What you get

```
📍 Amsterdam, Nederland

🌡 Temperature: 18.4°C
💧 Humidity: 72%
💨 Wind: SW at 14.0 km/h
🌅 Sunrise: 05:18
🌇 Sunset: 22:03
```

## Stack

- Python 3.12
- [python-telegram-bot](https://python-telegram-bot.org/) (long polling)
- [Open-Meteo](https://open-meteo.com/) (free, no API key)
- [Nominatim](https://nominatim.openstreetmap.org/) (reverse geocoding)
- Docker + docker-compose

## Quick start

1. **Create your bot** — talk to [@BotFather](https://t.me/BotFather) on Telegram and grab your token.

2. **Configure**

   ```bash
   cp .env.example .env
   # Edit .env and paste your BOT_TOKEN
   ```

3. **Run**

   ```bash
   docker compose up -d --build
   ```

4. **Check logs**

   ```bash
   docker compose logs -f
   ```

5. **Send your location** in Telegram — the bot replies with the weather.

## Configuration

| Variable    | Description                         | Default              |
|-------------|-------------------------------------|----------------------|
| `BOT_TOKEN` | Telegram bot token from BotFather   | *(required)*         |
| `TZ`        | Timezone for sunrise/sunset times   | `Europe/Amsterdam`   |

## Project structure

```
weather-bot/
├── bot.py              # Entry point, handlers, polling loop
├── weather.py          # Open-Meteo API + in-memory cache
├── geocoding.py        # Nominatim reverse geocoding
├── utils.py            # Wind direction, message formatting
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## Notes

- Weather responses are cached for 5 minutes (coordinates rounded to 2 decimals).
- Reverse geocoding falls back to raw coordinates if Nominatim is unreachable.
- The container runs as a non-root user.
- `python -u` ensures unbuffered stdout so `docker logs` works immediately.
