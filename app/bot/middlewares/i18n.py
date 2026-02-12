"""Middleware для автоматической подстановки языка пользователя."""
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.i18n import i18n
from app.core.models import User
from app.utils.logger import logger


class I18nMiddleware(BaseMiddleware):
    """Middleware для автоматической подстановки языка пользователя в хендлеры."""

    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any],
    ) -> Any:
        """
        Обрабатывает каждый апдейт и добавляет язык пользователя в data.

        Args:
            handler: Следующий обработчик в цепочке
            event: Событие (Message или CallbackQuery)
            data: Словарь с данными для хендлера

        Returns:
            Результат выполнения следующего обработчика
        """
        try:
            # Получаем user_id из события
            user_id: int
            if isinstance(event, Message):
                user_id = event.from_user.id
            elif isinstance(event, CallbackQuery):
                user_id = event.from_user.id
            else:
                # Если тип события не поддерживается, используем дефолтный язык
                logger.warning(f"Unsupported event type for I18nMiddleware: {type(event)}")
                data["lang"] = "ru"
                data["i18n"] = i18n
                return await handler(event, data)

            # Получаем язык пользователя из БД
            user_lang = await self._get_user_language(user_id)
            
            # Добавляем язык и i18n в data для хендлера
            data["lang"] = user_lang
            data["i18n"] = i18n
            
            logger.debug(f"I18nMiddleware: user_id={user_id}, lang={user_lang}")

        except Exception as e:
            logger.error(f"Error in I18nMiddleware: {e}", exc_info=True)
            # В случае ошибки используем дефолтный язык
            data["lang"] = "ru"
            data["i18n"] = i18n

        # Вызываем следующий обработчик
        return await handler(event, data)

    async def _get_user_language(self, user_id: int) -> str:
        """
        Получает язык пользователя из БД.

        Args:
            user_id: Telegram ID пользователя

        Returns:
            Код языка (ru, kk, en, zh)
        """
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(User.language).where(User.telegram_id == user_id)
                result = await session.execute(stmt)
                language = result.scalar_one_or_none()
                
                # Если пользователь не найден или язык не задан, используем дефолтный
                if language is None:
                    logger.debug(f"User {user_id} not found or language not set, using default: ru")
                    return "ru"
                
                return language
                
        except Exception as e:
            logger.error(f"Error getting user language for user_id={user_id}: {e}", exc_info=True)
            return "ru"
