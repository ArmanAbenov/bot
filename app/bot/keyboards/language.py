"""Клавиатуры для выбора языка."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_language_selection_keyboard() -> InlineKeyboardMarkup:
    """
    Создает inline-клавиатуру для выбора языка.

    Returns:
        InlineKeyboardMarkup с кнопками языков
    """
    keyboard = [
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton(text="🇰🇿 Қазақша", callback_data="lang_kk"),
        ],
        [
            InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
            InlineKeyboardButton(text="🇨🇳 中文", callback_data="lang_zh"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
