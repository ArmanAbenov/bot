"""Клавиатуры для выбора отдела."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.models import Department


def get_department_selection_keyboard(context: str = "registration") -> InlineKeyboardMarkup:
    """
    Создает inline-клавиатуру для выбора отдела.
    
    Args:
        context: Контекст использования ('registration' или 'admin_knowledge')
        
    Returns:
        Inline-клавиатура с деревом отделов
    """
    buttons = []
    
    # Кнопка "Доставка" - будет раскрываться в sub-menu
    buttons.append([
        InlineKeyboardButton(
            text="📦 Доставка",
            callback_data=f"dept_{context}_delivery_menu"
        )
    ])
    
    # Кнопка "Сортировочный центр"
    buttons.append([
        InlineKeyboardButton(
            text="📊 Сортировочный центр",
            callback_data=f"dept_{context}_{Department.SORTING.value}"
        )
    ])
    
    # Кнопка "Клиентский сервис"
    buttons.append([
        InlineKeyboardButton(
            text="💬 Клиентский сервис",
            callback_data=f"dept_{context}_{Department.CUSTOMER_SERVICE.value}"
        )
    ])
    
    # Кнопка "Менеджер"
    buttons.append([
        InlineKeyboardButton(
            text="👔 Менеджер",
            callback_data=f"dept_{context}_{Department.MANAGER.value}"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_delivery_submenu_keyboard(context: str = "registration") -> InlineKeyboardMarkup:
    """
    Создает sub-menu для выбора типа доставки.
    
    Args:
        context: Контекст использования ('registration' или 'admin_knowledge')
        
    Returns:
        Inline-клавиатура с типами доставки
    """
    buttons = [
        [
            InlineKeyboardButton(
                text="🚴 Курьер",
                callback_data=f"dept_{context}_{Department.COURIER.value}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🏢 Франчайзи",
                callback_data=f"dept_{context}_{Department.FRANCHISE.value}"
            )
        ],
        [
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=f"dept_{context}_back"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_department_keyboard() -> InlineKeyboardMarkup:
    """
    Создает клавиатуру выбора отдела для админа при добавлении знаний.
    Включает опцию 'common' для общих знаний.
    
    Returns:
        Inline-клавиатура с отделами + опция 'Общие для всех'
    """
    buttons = []
    
    # Кнопка "Общие для всех"
    buttons.append([
        InlineKeyboardButton(
            text="🌐 Общие для всех отделов",
            callback_data="dept_admin_knowledge_common"
        )
    ])
    
    # Кнопка "Доставка"
    buttons.append([
        InlineKeyboardButton(
            text="📦 Доставка",
            callback_data="dept_admin_knowledge_delivery_menu"
        )
    ])
    
    # Кнопка "Сортировочный центр"
    buttons.append([
        InlineKeyboardButton(
            text="📊 Сортировочный центр",
            callback_data=f"dept_admin_knowledge_{Department.SORTING.value}"
        )
    ])
    
    # Кнопка "Клиентский сервис"
    buttons.append([
        InlineKeyboardButton(
            text="💬 Клиентский сервис",
            callback_data=f"dept_admin_knowledge_{Department.CUSTOMER_SERVICE.value}"
        )
    ])
    
    # Кнопка "Менеджер"
    buttons.append([
        InlineKeyboardButton(
            text="👔 Менеджер",
            callback_data=f"dept_admin_knowledge_{Department.MANAGER.value}"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)
