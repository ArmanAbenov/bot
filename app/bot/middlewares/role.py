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
        user_exists = False
        is_verified = False
        if user_id:
            try:
                async with AsyncSessionLocal() as session:
                    stmt = select(User).where(User.telegram_id == user_id)
                    result = await session.execute(stmt)
                    user = result.scalar_one_or_none()
                    
                    if user:
                        role = user.role
                        user_exists = True
                        is_verified = user.is_verified
                        from app.utils.logger import logger
                        logger.debug(f"[MIDDLEWARE] User {user_id} found in DB: role={role}, lang={user.language}, is_verified={is_verified}")
                    else:
                        from app.utils.logger import logger
                        logger.debug(f"[MIDDLEWARE] User {user_id} NOT found in DB - new user")
            except Exception as e:
                # В случае ошибки продолжаем без роли
                from app.utils.logger import logger
                logger.error(f"[MIDDLEWARE] Error getting user role: {e}")

        # Добавляем роль и верификацию в data для использования в хендлерах
        data["role"] = role
        data["user_id"] = user_id
        data["user_exists"] = user_exists
        data["is_verified"] = is_verified
        
        # Защита: если пользователь не верифицирован, блокируем доступ ко всем хендлерам
        # КРОМЕ: /start, callback выбора языка, обработчика инвайт-кода
        if user_exists and not is_verified:
            from app.utils.logger import logger
            
            # Разрешенные команды и callback для неверифицированных пользователей
            is_start_command = isinstance(event, Message) and event.text and event.text.startswith("/start")
            is_lang_callback = isinstance(event, CallbackQuery) and event.data and event.data.startswith("lang_")
            is_in_registration_flow = False
            
            # Проверяем состояние FSM - если в процессе регистрации, пропускаем
            if "state" in data:
                from aiogram.fsm.context import FSMContext
                state_obj: FSMContext = data["state"]
                current_state = await state_obj.get_state()
                if current_state and "RegistrationState" in str(current_state):
                    is_in_registration_flow = True
            
            # Если это НЕ разрешенная операция - блокируем
            if not (is_start_command or is_lang_callback or is_in_registration_flow):
                logger.warning(f"[SECURITY] User {user_id} not verified, blocking access")
                
                if isinstance(event, Message):
                    await event.answer(
                        "⚠️ Доступ запрещен.\n\n"
                        "Для использования бота введите инвайт-код.\n\n"
                        "Напишите команду /start для начала регистрации."
                    )
                elif isinstance(event, CallbackQuery):
                    await event.answer("⚠️ Доступ запрещен. Пройдите регистрацию.", show_alert=True)
                
                return  # Блокируем выполнение хендлера

        return await handler(event, data)
