"""Система миграций для базы данных."""
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.logger import logger


async def check_column_exists(session: AsyncSession, table_name: str, column_name: str) -> bool:
    """
    Проверяет существование колонки в таблице SQLite.
    
    Args:
        session: Асинхронная сессия БД
        table_name: Название таблицы
        column_name: Название колонки
    
    Returns:
        True если колонка существует, False иначе
    """
    try:
        # Получаем информацию о таблице
        query = text(f"PRAGMA table_info({table_name})")
        result = await session.execute(query)
        columns = result.fetchall()
        
        # Проверяем наличие колонки
        column_exists = any(col[1] == column_name for col in columns)
        return column_exists
    except Exception as e:
        logger.error(f"[MIGRATION] Error checking column {table_name}.{column_name}: {e}")
        return False


async def migrate_add_is_verified(session: AsyncSession) -> bool:
    """
    Добавляет поле is_verified в таблицу users.
    
    Args:
        session: Асинхронная сессия БД
    
    Returns:
        True если миграция успешна, False иначе
    """
    try:
        # Проверяем существование колонки
        exists = await check_column_exists(session, "users", "is_verified")
        
        if exists:
            logger.info("[MIGRATION] Column 'is_verified' already exists, skipping migration")
            return True
        
        logger.info("[MIGRATION] Adding 'is_verified' column to users table...")
        
        # Добавляем колонку
        await session.execute(text(
            "ALTER TABLE users ADD COLUMN is_verified BOOLEAN NOT NULL DEFAULT 0"
        ))
        
        # Устанавливаем всех существующих пользователей как верифицированных
        # (они уже в системе, не нужно их блокировать)
        await session.execute(text(
            "UPDATE users SET is_verified = 1"
        ))
        
        await session.commit()
        
        logger.info("[MIGRATION] ✅ Migration completed: is_verified column added")
        return True
        
    except Exception as e:
        logger.error(f"[MIGRATION] Error adding is_verified column: {e}", exc_info=True)
        await session.rollback()
        return False


async def run_migrations(session: AsyncSession) -> None:
    """
    Запускает все необходимые миграции.
    
    Args:
        session: Асинхронная сессия БД
    """
    try:
        logger.info("[MIGRATION] Running database migrations...")
        
        # Миграция: добавление is_verified
        await migrate_add_is_verified(session)
        
        logger.info("[MIGRATION] All migrations completed")
        
    except Exception as e:
        logger.error(f"[MIGRATION] Error running migrations: {e}", exc_info=True)
