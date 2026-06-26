import logging
import os

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from geocoding import reverse_geocode, geocode_place
from knmi import ensure_station_cache, find_nearest_station, get_knmi_observation
from utils import format_weather_message
from weather import get_weather

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def on_startup(app: Application) -> None:
    """Load KNMI station cache (refresh if stale) before handling any messages."""
    await ensure_station_cache()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Send me your location and I'll reply with the current weather!"
    )


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lat = update.message.location.latitude
    lon = update.message.location.longitude

    try:
        location_name = await reverse_geocode(lat, lon)
        openmeteo_data = await get_weather(lat, lon)
    except Exception as e:
        logger.error("Open-Meteo/geocoding error: %s", e)
        await update.message.reply_text("⚠️ Could not fetch weather data. Please try again later.")
        return

    # KNMI is best-effort — failure never blocks the reply
    knmi_data = None
    station_name = None
    station_distance = None
    try:
        station_id, station_name, station_distance = find_nearest_station(lat, lon)
        knmi_data = await get_knmi_observation(station_id)
    except ValueError as e:
        logger.warning("KNMI station lookup: %s", e)
    except Exception as e:
        logger.error("KNMI observation error: %s", e)

    message = format_weather_message(
        location_name,
        lat,
        lon,
        openmeteo_data,
        knmi=knmi_data,
        station_name=station_name,
        station_distance_km=station_distance,
    )
    await update.message.reply_text(message)

async def handle_text_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.message.text.strip()

    try:
        location = await geocode_place(query)

        if not location:
            await update.message.reply_text("❌ Location not found.")
            return

        lat = location["lat"]
        lon = location["lon"]

        location_name = location["display_name"]

        openmeteo_data = await get_weather(lat, lon)

        knmi_data = None
        station_name = None
        station_distance = None

        try:
            station_id, station_name, station_distance = find_nearest_station(
                lat, lon
            )
            knmi_data = await get_knmi_observation(station_id)
        except Exception as e:
            logger.warning("KNMI lookup failed: %s", e)

        message = format_weather_message(
            location_name,
            lat,
            lon,
            openmeteo_data,
            knmi=knmi_data,
            station_name=station_name,
            station_distance_km=station_distance,
        )

        await update.message.reply_text(message)

    except Exception as e:
        logger.error("Error handling text location: %s", e)
        await update.message.reply_text(
            "⚠️ Could not fetch weather data."
        )

async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📍 Please share your location to get weather info.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Update %s caused error: %s", update, context.error)


def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is not set")

    app = (
        Application.builder()
        .token(token)
        .post_init(on_startup)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_location,))
    app.add_handler(MessageHandler(~filters.COMMAND, handle_unknown))
    app.add_error_handler(error_handler)

    logger.info("Bot starting…")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
