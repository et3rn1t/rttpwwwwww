import asyncio
from aiogram import F, Bot, Dispatcher, types, exceptions
from loguru import logger
from redis.asyncio import Redis
from aiogram.filters import Command
import pytz
from datetime import datetime

from .settings import settings
from .keyboards import link_markup, Callbacks

bot = Bot(token=settings.TOKEN.get_secret_value())
dp = Dispatcher()

redis = Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=(
        settings.REDIS_PASSWORD.get_secret_value() if settings.REDIS_PASSWORD else None
    ),
)

EX_TIME = 60 * 60 * 24 * 21

async def get_saved_user_id() -> int | None:
    """Получает сохраненный USER_ID из Redis"""
    try:
        user_id = await redis.get("admin_user_id")
        return int(user_id) if user_id else None
    except Exception:
        return None

async def save_user_id(user_id: int):
    """Сохраняет USER_ID в Redis"""
    await redis.set("admin_user_id", str(user_id), ex=EX_TIME)

async def set_message(message: types.Message):
    await redis.set(
        f"{message.chat.id}:{message.message_id}",
        message.model_dump_json(),
        ex=EX_TIME,
    )

@dp.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    
    # Сохраняем USER_ID в Redis
    await save_user_id(user_id)
    settings.USER_ID = user_id
    
    await message.answer(
        "👋 Привет! Я бот для мониторинга бизнес-чата\n\n"
        "💫 *Как настроить:*\n"
        "1. Зайди в: Настройки → Telegram для Бизнеса → Чат-боты\n"
        "2. Добавь моего бота\n"
        "3. Поставь разрешение на чтение сообщений\n\n"
        "📊 Теперь все удаленные и измененные сообщения будут приходить сюда!",
        parse_mode="Markdown"
    )
    logger.info(f"USER_ID установлен: {user_id}")

@dp.business_message()
async def handle_business_reply(message: types.Message):
    """Обрабатывает ответы на исчезающие сообщения"""
    if not settings.USER_ID:
        return
        
    # Проверяем, является ли это ответом на сообщение с эффектом
    if (message.reply_to_message and 
        hasattr(message.reply_to_message, 'message_effect_id') and 
        message.reply_to_message.message_effect_id):
        
        original_message = message.reply_to_message
        user = original_message.from_user
        user_info = f"@{user.username}" if user.username else f"{user.first_name} {user.last_name or ''}".strip()
        user_info = user_info or f"ID: {user.id}"
        
        # Определяем тип исчезающего контента
        effect_id = original_message.message_effect_id
        effect_type = "Исчезающее медиа"
        if effect_id == "video-message":
            effect_type = "Исчезающее видео"
        elif effect_id == "view-once":
            effect_type = "Одноразовое фото"
        elif effect_id == "view-once-v2":
            effect_type = "Одноразовое медиа"
        elif effect_id == "view_once":
            effect_type = "Одноразовый просмотр"
        elif effect_id == "once":
            effect_type = "Однократный просмотр"
        
        caption = (
            f"👀 *Ответ на {effect_type}*\n\n"
            f"👤 *Автор:*\n{user_info}\n\n"
            f"⏰ *Время отправки:*\n{format_moscow_time(original_message.date)}\n\n"
            f"💬 *Ваш ответ:*\n{message.text or '📷 Медиа'}\n\n"
            f"🎭 *Тип контента:* {effect_type}"
        )

        try:
            if original_message.photo:
                await bot.send_photo(
                    chat_id=settings.USER_ID,
                    photo=original_message.photo[-1].file_id,
                    caption=caption,
                    parse_mode="Markdown"
                )
            elif original_message.video:
                await bot.send_video(
                    chat_id=settings.USER_ID,
                    video=original_message.video.file_id,
                    caption=caption,
                    parse_mode="Markdown"
                )
            elif original_message.video_note:
                await bot.send_message(
                    chat_id=settings.USER_ID,
                    text=caption,
                    parse_mode="Markdown"
                )
                await bot.send_video_note(
                    chat_id=settings.USER_ID,
                    video_note=original_message.video_note.file_id
                )
            elif original_message.animation:
                await bot.send_animation(
                    chat_id=settings.USER_ID,
                    animation=original_message.animation.file_id,
                    caption=caption,
                    parse_mode="Markdown"
                )
            elif original_message.document:
                await bot.send_document(
                    chat_id=settings.USER_ID,
                    document=original_message.document.file_id,
                    caption=caption,
                    parse_mode="Markdown"
                )
            else:
                await bot.send_message(
                    chat_id=settings.USER_ID,
                    text=caption + "\n\n📁 *Неизвестный тип медиа*",
                    parse_mode="Markdown"
                )
                
        except Exception as e:
            logger.error(f"Ошибка отправки исчезающего медиа: {e}")
            fallback_text = f"❌ *Не удалось отправить {effect_type}*"
            await bot.send_message(
                chat_id=settings.USER_ID,
                text=fallback_text,
                parse_mode="Markdown"
            )
    
    # Всегда сохраняем сообщение
    await set_message(message)
# Добавьте в начало файла после импортов
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

def format_moscow_time(dt):
    """Форматирует время в московском часовом поясе (только время)"""
    if dt:
        moscow_dt = dt.astimezone(MOSCOW_TZ)
        return moscow_dt.strftime('%H:%M:%S')
    return "неизвестно"


@dp.edited_business_message()
async def edited_message(message: types.Message):
    if not settings.USER_ID:
        logger.warning("USER_ID не установлен. Пропускаем сообщение.")
        return
        
    model_dump = await redis.get(f"{message.chat.id}:{message.message_id}")
    await set_message(message)

    if not model_dump:
        return

    original_message = types.Message.model_validate_json(model_dump)
    if not original_message.from_user:
        return

    # Форматируем информацию о пользователе
    user = original_message.from_user
    user_info = f"@{user.username}" if user.username else f"{user.first_name} {user.last_name or ''}".strip()
    user_info = user_info or f"ID: {user.id}"
    
    caption = (
        f"✏️ *Изменено сообщение*\n\n"
        f"👤 *Пользователь:*\n{user_info}\n\n"
        f"⏰ *Время отправки:*\n{format_moscow_time(original_message.date)}\n\n"
        f"🕒 *Время изменения:*\n{format_moscow_time(message.edit_date)}"
    )

    # Отправляем медиа или текст
    try:
        if original_message.photo:
            await bot.send_photo(
                chat_id=settings.USER_ID,
                photo=original_message.photo[-1].file_id,
                caption=caption,
                parse_mode="Markdown"
            )
        elif original_message.video:
            await bot.send_video(
                chat_id=settings.USER_ID,
                video=original_message.video.file_id,
                caption=caption,
                parse_mode="Markdown"
            )
        elif original_message.document:
            await bot.send_document(
                chat_id=settings.USER_ID,
                document=original_message.document.file_id,
                caption=caption,
                parse_mode="Markdown"
            )
        elif original_message.animation:
            await bot.send_animation(
                chat_id=settings.USER_ID,
                animation=original_message.animation.file_id,
                caption=caption,
                parse_mode="Markdown"
            )
        elif original_message.sticker:
            await bot.send_sticker(
                chat_id=settings.USER_ID,
                sticker=original_message.sticker.file_id
            )
            await bot.send_message(
                chat_id=settings.USER_ID,
                text=caption,
                parse_mode="Markdown"
            )
        elif original_message.voice:
            await bot.send_voice(
                chat_id=settings.USER_ID,
                voice=original_message.voice.file_id,
                caption=caption,
                parse_mode="Markdown"
            )
        elif original_message.video_note:
            # Сначала отправляем текстовое описание
            await bot.send_message(
                chat_id=settings.USER_ID,
                text=caption + "\n\n⭕ *Видео-кружок*",
                parse_mode="Markdown"
            )
            # Затем отправляем сам кружок
            await bot.send_video_note(
                chat_id=settings.USER_ID,
                video_note=original_message.video_note.file_id
            )
        elif original_message.text:
            caption += f"\n\n💬 *Текст:*\n{original_message.text}"
            await bot.send_message(
                chat_id=settings.USER_ID,
                text=caption,
                parse_mode="Markdown"
            )
        elif original_message.caption:
            caption += f"\n\n💬 *Подпись:*\n{original_message.caption}"
            await bot.send_message(
                chat_id=settings.USER_ID,
                text=caption,
                parse_mode="Markdown"
            )
        else:
            await bot.send_message(
                chat_id=settings.USER_ID,
                text=caption + "\n\n📁 *Тип:* Медиафайл",
                parse_mode="Markdown"
            )
            
    except Exception as e:
        logger.error(f"Ошибка отправки медиа: {e}")
        # Fallback на текстовое уведомление
        fallback_text = caption + "\n\n❌ *Не удалось отправить медиафайл*"
        await bot.send_message(
            chat_id=settings.USER_ID,
            text=fallback_text,
            parse_mode="Markdown"
        )

@dp.deleted_business_messages()
async def deleted_message(business_messages: types.BusinessMessagesDeleted):
    if not settings.USER_ID:
        logger.warning("USER_ID не установлен. Пропускаем удаление.")
        return
        
    pipe = redis.pipeline()
    for message_id in business_messages.message_ids:
        pipe.get(f"{business_messages.chat.id}:{message_id}")
    messages_data = await pipe.execute()

    keys_to_delete = []
    for message_id, model_dump in zip(business_messages.message_ids, messages_data):
        if not model_dump:
            continue

        original_message = types.Message.model_validate_json(model_dump)
        if not original_message.from_user:
            continue

        # Форматируем информацию о пользователе
        user = original_message.from_user
        user_info = f"@{user.username}" if user.username else f"{user.first_name} {user.last_name or ''}".strip()
        user_info = user_info or f"ID: {user.id}"
        
        caption = (
            f"🗑️ *Удалено сообщение*\n\n"
            f"👤 *Пользователь:*\n{user_info}\n\n"
            f"⏰ *Время отправки:*\n{format_moscow_time(original_message.date)}\n\n"
            f"🕒 *Время удаления:*\n{format_moscow_time(datetime.now())}"
        )

        # Отправляем медиа или текст
        try:
            if original_message.photo:
                await bot.send_photo(
                    chat_id=settings.USER_ID,
                    photo=original_message.photo[-1].file_id,
                    caption=caption,
                    parse_mode="Markdown"
                )
            elif original_message.video:
                await bot.send_video(
                    chat_id=settings.USER_ID,
                    video=original_message.video.file_id,
                    caption=caption,
                    parse_mode="Markdown"
                )
            elif original_message.document:
                await bot.send_document(
                    chat_id=settings.USER_ID,
                    document=original_message.document.file_id,
                    caption=caption,
                    parse_mode="Markdown"
                )
            elif original_message.animation:
                await bot.send_animation(
                    chat_id=settings.USER_ID,
                    animation=original_message.animation.file_id,
                    caption=caption,
                    parse_mode="Markdown"
                )
            elif original_message.sticker:
                await bot.send_sticker(
                    chat_id=settings.USER_ID,
                    sticker=original_message.sticker.file_id
                )
                await bot.send_message(
                    chat_id=settings.USER_ID,
                    text=caption,
                    parse_mode="Markdown"
                )
            elif original_message.voice:
                # Для голосовых сообщений отправляем только текстовое уведомление
                caption += f"\n\n🎤 *Голосовое сообщение* (длительность: {original_message.voice.duration} сек.)"
                await bot.send_message(
                    chat_id=settings.USER_ID,
                    text=caption,
                    parse_mode="Markdown"
                )
            elif original_message.video_note:
                # Сначала отправляем текстовое описание
                await bot.send_message(
                    chat_id=settings.USER_ID,
                    text=caption + "\n\n⭕ *Видео-кружок*",
                    parse_mode="Markdown"
                )
                # Затем отправляем сам кружок как обычное видео
                await bot.send_video(
                    chat_id=settings.USER_ID,
                    video=original_message.video_note.file_id
                )
            elif original_message.text:
                caption += f"\n\n💬 *Текст:*\n{original_message.text}"
                await bot.send_message(
                    chat_id=settings.USER_ID,
                    text=caption,
                    parse_mode="Markdown"
                )
            elif original_message.caption:
                caption += f"\n\n💬 *Подпись:*\n{original_message.caption}"
                await bot.send_message(
                    chat_id=settings.USER_ID,
                    text=caption,
                    parse_mode="Markdown"
                )
            else:
                await bot.send_message(
                    chat_id=settings.USER_ID,
                    text=caption + "\n\n📁 *Тип:* Медиафайл",
                    parse_mode="Markdown"
                )
                
        except Exception as e:
            logger.error(f"Ошибка отправки медиа: {e}")
            # Fallback на текстовое уведомление
            fallback_text = caption + "\n\n❌ *Не удалось отправить медиафайл*"
            await bot.send_message(
                chat_id=settings.USER_ID,
                text=fallback_text,
                parse_mode="Markdown"
            )
        finally:
            await asyncio.sleep(0.1)

        keys_to_delete.append(f"{business_messages.chat.id}:{message_id}")

    if keys_to_delete:
        await redis.delete(*keys_to_delete)

@dp.callback_query(F.data == Callbacks.EMPTY)
async def empty(query: types.CallbackQuery):
    await query.answer()

@dp.callback_query(F.data == Callbacks.CLOSE)
async def close(query: types.CallbackQuery):
    await query.answer()
    if isinstance(query.message, types.Message):
        await query.message.delete()

async def main():
    # Инициализация Redis подключения
    try:
        await redis.ping()
        logger.info("Успешное подключение к Redis")
        
        # Пытаемся загрузить сохраненный USER_ID
        saved_user_id = await get_saved_user_id()
        if saved_user_id:
            settings.USER_ID = saved_user_id
            logger.info(f"Загружен сохраненный USER_ID: {saved_user_id}")
        else:
            logger.warning("Сохраненный USER_ID не найден. Ожидаем команду /start")
            
    except Exception as e:
        logger.error(f"Ошибка подключения к Redis: {e}")
        return

    # Запуск бота
    logger.info("Бот запущен и начал поллинг")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())