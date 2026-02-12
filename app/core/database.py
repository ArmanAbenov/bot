"""Настройка базы данных SQLAlchemy."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from app.core.config import settings
from app.utils.logger import logger

# Создаем асинхронный движок для SQLite
engine = create_async_engine(
    settings.database_url,
    echo=False,  # Включить для отладки SQL запросов
    future=True,
    connect_args={"check_same_thread": False},  # Для SQLite в async режиме
)

# Создаем фабрику сессий
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Базовый класс для моделей
Base = declarative_base()


async def init_db() -> None:
    """Инициализация базы данных: создание всех таблиц и добавление главного админа."""
    async with engine.begin() as conn:
        # Включаем WAL режим для SQLite
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA synchronous=NORMAL"))
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)
    
    # Добавляем главного админа после создания таблиц
    # Импортируем модель локально, чтобы избежать циклических зависимостей
    from app.core.models import Admin
    
    async with AsyncSessionLocal() as session:
        try:
            MAIN_ADMIN_ID = 375693711
            MAIN_ADMIN_USERNAME = "Главный админ"
            
            # Проверяем, существует ли уже главный админ
            from sqlalchemy import select
            stmt = select(Admin).where(Admin.user_id == MAIN_ADMIN_ID)
            result = await session.execute(stmt)
            existing_admin = result.scalar_one_or_none()
            
            if existing_admin:
                # Обновляем username, если админ уже существует
                existing_admin.username = MAIN_ADMIN_USERNAME
                await session.commit()
                logger.info(f"[INIT_DB] Main admin {MAIN_ADMIN_ID} updated successfully")
            else:
                # Создаем нового админа
                admin = Admin(user_id=MAIN_ADMIN_ID, username=MAIN_ADMIN_USERNAME)
                session.add(admin)
                await session.commit()
                logger.info(f"[INIT_DB] Main admin {MAIN_ADMIN_ID} added successfully")
        except Exception as e:
            await session.rollback()
            logger.error(f"[INIT_DB] Error adding main admin: {e}", exc_info=True)
            # Не прерываем инициализацию, если не удалось добавить админа


async def get_db() -> AsyncSession:
    """Получение сессии БД."""
    async with AsyncSessionLocal() as session:
        return session
