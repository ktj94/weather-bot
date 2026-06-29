# Telegram Weather Bot

A self-hosted Telegram weather bot that combines Open-Meteo forecasts with real-time KNMI station observations for locations in the Netherlands. Send a location or type a place name and get current conditions instantly.

Built with Python 3.12, python-telegram-bot, Open-Meteo, KNMI Open Data Platform, and Docker.

---

## Features

### Dual Weather Sources

**Open-Meteo** provides global coverage with temperature, feels-like temperature, humidity, wind speed and direction (Beaufort + km/h), cloud cover percentage and description, and sunrise/sunset times.

**KNMI** adds ground-truth observations from the nearest Dutch weather station, including temperature, humidity, wind, and cloud cover. KNMI data is best-effort: if no station is within 50 km or the data is unavailable, the bot still replies with Open-Meteo data.

### Location Input

Share your location directly from Telegram or type a place name. Reverse geocoding resolves coordinates to neighbourhood-level names (neighbourhood, suburb, quarter, road, city, country).

### KNMI Anonymous Key

The bot automatically fetches and caches the KNMI anonymous API key from their developer portal. When the key approaches its expiry date, it is refreshed transparently. If the portal is unavailable or the page format changes, the bot falls back to a manually configured `KNMI_API_KEY` environment variable.

### Caching

Open-Meteo responses are cached in memory for 5 minutes. Coordinates are rounded to 3 decimal places (~100 m granularity) before caching.

KNMI observation data (NetCDF files) is cached on disk and in memory with a 10-minute TTL based on the observation timestamp embedded in the filename, matching KNMI's 10-minute publication interval.

KNMI station metadata (coordinates, names) is cached on disk and refreshed weekly.

---

## Architecture

### Startup

The bot loads the KNMI station cache from disk immediately so it can start accepting messages. If the station cache is stale (older than 7 days) or missing, a background task downloads a fresh NetCDF file and rebuilds the cache. This retries hourly on failure.

### /start Command

The welcome message is sent immediately. A background task then checks whether the cached KNMI observations are stale by parsing the observation timestamp from the NetCDF filename. If the observation is older than 10 minutes, the task downloads the latest file. A guard flag prevents duplicate downloads if `/start` is sent repeatedly.

```
User sends /start
      │
      ├── Reply immediately with welcome message
      │
      └── Background: ensure_latest_knmi_data()
              │
              ├── Refresh already running?  → skip
              ├── Observation fresh?        → skip
              └── Observation stale?        → download latest .nc
```

### Location Request

Sharing a location or typing a place name reads directly from the cached data. The location handler never checks staleness and never triggers a download. If no cached data exists at all (first run or cache wiped), a single recovery download is performed.

```
User shares location
      │
      ├── Open-Meteo: fetch current weather
      ├── Geocoding: resolve coordinates to place name
      │
      └── KNMI (best-effort):
              ├── Find nearest station (Haversine)
              ├── Read observation from memory or disk cache
              └── If neither exists: one-time recovery download
```

### Staleness

Observation freshness is determined by the timestamp in the NetCDF filename, not the download time. For example, `KMDS__OPER_P___10M_OBS_L2_202606281020.nc` represents observations at 10:20 UTC. If the current time is 10:31 UTC, the observation is 11 minutes old and considered stale — even if the file was downloaded only 4 minutes ago.

---

## Example Response

```
📍 Centrum, Amsterdam, Netherlands
📌 52.3676, 4.9041

━━━ Open-Meteo ━━━
🌡 Temperature:  18.4°C
🥶 Feels Like:  16.9°C
💧 Humidity:    72%
💨 Wind:        SW
💨 Speed:       Bft 3 (14 km/h)
☁️ Cloud Cover: 35% (Partly cloudy)

🌅 Sunrise:     05:18
🌇 Sunset:      22:03

━━━ KNMI Station ━━━
🌡 Temperature:   18.1°C
💧 Humidity:     74%
💨 Wind:         SW
💨 Speed:        Bft 3 (15.1 km/h)
☁️ Cloud cover:  38% (Partly cloudy)
📡 Station:      Schiphol (8.2 km)
🕒 Updated:      12:20
```

---

## Project Structure

```
weather-bot/
├── bot.py               Telegram handlers, startup, /start
├── weather.py           Open-Meteo client with 5-min cache
├── knmi.py              KNMI integration: stations, NetCDF, observations
├── knmi_api_key.py      Anonymous KNMI API key: fetch, cache, expiry
├── geocoding.py         Nominatim forward and reverse geocoding
├── utils.py             Formatting, compass, Beaufort, cloud descriptions
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env
├── .env.example
└── README.md
```

### Cache Files (persisted in /data volume)

```
/data/
├── knmi_stations.json      Station metadata: WMO IDs, names, coordinates
├── latest.nc               Most recent KNMI NetCDF observation file
├── latest_nc_meta.json     {"filename": "...", "downloaded_at": "..."}
└── anonymous_key.json      {"key": "...", "expires": "2026-07-01"}
```

---

## Setup

### Create a Telegram Bot

Message [@BotFather](https://t.me/BotFather) on Telegram and use `/newbot` to create a bot. Copy the token.

### Create the Environment File

```bash
cp .env.example .env
```

Edit `.env`:

```env
BOT_TOKEN=your-telegram-bot-token
KNMI_API_KEY=your-knmi-anonymous-key
TZ=Europe/Amsterdam
```

`KNMI_API_KEY` is a fallback. Under normal operation, the bot fetches the anonymous key automatically from the KNMI developer portal and caches it in `/data/anonymous_key.json`. The environment variable is only used if the automatic fetch fails.

---

## Deployment

### Docker Compose

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

### Portainer Stack

Repository URL:

```
git@github.com:ktj94/weather-bot.git
```

Reference: `main`

Compose path: `docker-compose.yml`

Environment variables:

```env
BOT_TOKEN=your-telegram-bot-token
KNMI_API_KEY=your-knmi-anonymous-key
TZ=Europe/Amsterdam
```

---

## Data Sources

### Open-Meteo

[https://open-meteo.com](https://open-meteo.com)

Global weather forecasts. No API key required.

### KNMI Open Data Platform

[https://dataplatform.knmi.nl](https://dataplatform.knmi.nl)

Dataset: `10-minute-in-situ-meteorological-observations` version 1.0

Variables used: air temperature (`ta`), relative humidity (`rh`), wind speed (`ff`, m/s → km/h), wind direction (`dd`, degrees), total cloud cover (`n`, okta → %).

Authentication uses the anonymous API key published on the KNMI developer portal, refreshed automatically before expiry.

### OpenStreetMap Nominatim

[https://nominatim.openstreetmap.org](https://nominatim.openstreetmap.org)

Reverse and forward geocoding. The bot identifies the most specific location name available, prioritising neighbourhood over suburb over city.

---

## Technical Details

### Wind

Wind speed is displayed in both Beaufort scale (primary) and km/h (secondary). Wind direction is converted from degrees to an 8-point compass (N, NE, E, SE, S, SW, W, NW).

### Cloud Cover

KNMI reports cloud cover in oktas (0–8). The bot converts to percentage and adds a description: Clear (≤5%), Mostly clear (≤25%), Partly cloudy (≤50%), Mostly cloudy (≤75%), Overcast (>75%).

### Resource Usage

```
RAM:  50–100 MB
CPU:  near 0% while idle
```

Suitable for low-cost VPS, Raspberry Pi, Proxmox, or any Docker host.

---

## Stack

| Component           | Technology                |
|---------------------|---------------------------|
| Bot Framework       | python-telegram-bot 21.3  |
| Weather (global)    | Open-Meteo                |
| Weather (NL)        | KNMI Open Data Platform   |
| Geocoding           | Nominatim                 |
| NetCDF Parsing      | xarray + netCDF4          |
| HTTP Client         | httpx                     |
| Containerisation    | Docker + Docker Compose   |
| Runtime             | Python 3.12               |

---

## License

Private project.
