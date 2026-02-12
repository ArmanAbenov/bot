"""Клавиатура главного меню."""
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from app.core.i18n import i18n


def get_main_menu(role: str | None = None, is_admin: bool = False, lang: str = "ru") -> ReplyKeyboardMarkup:
    """
    Возвращает клавиатуру главного меню в зависимости от роли.
    
    Args:
        role: Роль пользователя из таблицы users (employee, manager, admin)
        is_admin: Флаг, указывающий, является ли пользователь админом в таблице admins
        lang: Код языка (ru, kk, en, zh)
    
    Returns:
        ReplyKeyboardMarkup с кнопками главного меню
    """
    keyboard_buttons = [
        [KeyboardButton(text=i18n.get("main_menu_ask", lang))],
        [KeyboardButton(text=i18n.get("main_menu_settings", lang))],
    ]

    # Добавляем кнопки в зависимости от роли или статуса админа
    # Если пользователь есть в таблице admins, показываем кнопку админ-панели
    if is_admin or role == "admin":
        keyboard_buttons.append([KeyboardButton(text=i18n.get("main_menu_admin_panel", lang))])

    keyboard = ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True,
    )
    return keyboard
