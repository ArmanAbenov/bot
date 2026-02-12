"""Точка входа в приложение."""
import asyncio
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.admin_dept_handler import router as admin_dept_router
from app.bot.handlers.start import router as start_router
from app.bot.handlers.media import router as media_router
from app.bot.handlers.settings import router as settings_router
from app.bot.middlewares.role import RoleMiddleware
from app.bot.middlewares.i18n import I18nMiddleware
from app.core.config import settings
from app.core.database import init_db
from app.core.models import Admin, ChatHistory, OnboardingProgress, User  # Импортируем модели для регистрации
from app.utils.logger import logger

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))


async def main() -> None:
    """Основная функция запуска бота."""
    bot = None
    try:
        logger.info("Starting UQ-bot...")

        # Инициализация базы данных
        logger.info("Initializing database...")
        await init_db()
        logger.info("Database initialized successfully")

        # Создаем бота и диспетчер с FSM storage
        bot = Bot(
            token=settings.bot_token,
        )
        
        # Завершаем предыдущие сессии (если есть)
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Previous webhook deleted, dropped pending updates")
        except Exception as e:
            logger.warning(f"Could not delete webhook: {e}")
        
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)

        # Регистрируем middleware (важно регистрировать до роутеров!)
        dp.message.middleware(RoleMiddleware())
        dp.callback_query.middleware(RoleMiddleware())
        dp.message.middleware(I18nMiddleware())
        dp.callback_query.middleware(I18nMiddleware())

        # Регистрируем роутеры (порядок важен - более специфичные должны быть первыми)
        dp.include_router(media_router)          # Голосовые сообщения
        dp.include_router(admin_dept_router)     # Выбор отдела в админ-панели
        dp.include_router(admin_router)          # Админ-панель (перед start!)
        dp.include_router(settings_router)       # Настройки (перед start!)
        dp.include_router(start_router)          # Основные хендлеры

        logger.info("Bot is starting...")
        # Запускаем polling
        await dp.start_polling(bot)

    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)
        raise
    finally:
        if bot:
            await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
