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
from utils import format_weather_message
from weather import get_weather

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Send me your location or type a place name and I'll reply with the current weather!"
    )


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lat = update.message.location.latitude
    lon = update.message.location.longitude

    try:
        location_name = await reverse_geocode(lat, lon)
        weather_data = await get_weather(lat, lon)
        location_name = f"{location_name}\n📌 {lat:.4f}, {lon:.4f}"
        message = format_weather_message(location_name, weather_data)
        await update.message.reply_text(message)
    except Exception as e:
        logger.error("Error handling location: %s", e)
        await update.message.reply_text(
            "⚠️ Could not fetch weather data. Please try again later."
        )


async def handle_text_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    query = update.message.text.strip()

    try:
        location = await geocode_place(query)

        if not location:
            await update.message.reply_text(
                "❌ Location not found."
            )
            return

        lat = location["lat"]
        lon = location["lon"]

        weather_data = await get_weather(lat, lon)

        location_name = (
            f"{location['display_name']}\n"
            f"📌 {lat:.4f}, {lon:.4f}"
        )

        message = format_weather_message(
            location_name,
            weather_data,
        )

        await update.message.reply_text(message)

    except Exception as e:
        logger.error(
            "Error handling text location: %s",
            e,
        )

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

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_location))
    app.add_handler(MessageHandler(filters.ALL, handle_unknown))
    app.add_error_handler(error_handler)

    logger.info("Bot starting…")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
