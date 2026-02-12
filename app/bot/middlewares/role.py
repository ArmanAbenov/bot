"""Middleware для подтягивания роли пользователя из БД."""
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.models import User


class RoleMiddleware(BaseMiddleware):
    """Middleware для добавления роли пользователя в event data."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Добавляет роль пользователя в data для использования в хендлерах."""
        # Получаем ID пользователя из события
        user_id = None
        if isinstance(event, (Message, CallbackQuery)):
            if hasattr(event, "from_user") and event.from_user:
                user_id = event.from_user.id

        # Если ID есть, получаем роль из БД
        role = None
        if user_id:
            try:
                async with AsyncSessionLocal() as session:
                    stmt = select(User).where(User.telegram_id == user_id)
                    result = await session.execute(stmt)
                    user = result.scalar_one_or_none()
                    
                    if user:
                        role = user.role
            except Exception as e:
                # В случае ошибки продолжаем без роли
                from app.utils.logger import logger
                logger.error(f"Error getting user role in middleware: {e}")

        # Добавляем роль в data для использования в хендлерах
        data["role"] = role
        data["user_id"] = user_id

        return await handler(event, data)
