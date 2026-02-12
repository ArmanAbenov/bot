"""Фильтры для хендлеров."""
from typing import Union

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from app.core.config import settings


class IsAdmin(BaseFilter):
    """Фильтр для проверки, является ли пользователь администратором."""

    async def __call__(
        self, obj: Union[Message, CallbackQuery]
    ) -> bool:
        """Проверяет, находится ли ID пользователя в списке администраторов."""
        user_id = obj.from_user.id if hasattr(obj, "from_user") else None
        
        if user_id is None:
            return False
            
        # Проверяем по ID из конфига
        if user_id in settings.admin_ids:
            return True
            
        # Дополнительно проверяем роль в БД (если нужно)
        # Это можно добавить позже, если нужно синхронизировать с БД
        
        return False
