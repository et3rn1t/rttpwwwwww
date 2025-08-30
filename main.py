from loguru import logger
from src.bot import dp, bot
from src.settings import settings

logger.info(f"Bot token: {settings.TOKEN.get_secret_value()[:10]}...")
logger.info(f"Target USER_ID: {settings.USER_ID}")

if __name__ == "__main__":
    logger.info("Starting...")
    dp.run_polling(
        bot,
        allowed_updates=[
            "callback_query",
            "business_message",
            "edited_business_message",
            "deleted_business_messages",
        ],
    )
