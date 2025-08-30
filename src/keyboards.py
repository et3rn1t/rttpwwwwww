from enum import StrEnum
from aiogram.utils.keyboard import InlineKeyboardBuilder


class Callbacks(StrEnum):
    EMPTY = "empty"
    CLOSE = "close"


def link_markup(title: str, user_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text=title, callback_data=Callbacks.EMPTY)
    builder.button(text="Кто удалил? 👤", url=f"tg://user?id={user_id}")
    builder.button(text="Закрыть ❌", callback_data=Callbacks.CLOSE)
    return builder.adjust(3).as_markup()
