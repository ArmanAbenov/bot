"""Миграция для добавления поля language в таблицу users."""
import asyncio
from sqlalchemy import text

from app.core.database import AsyncSessionLocal, engine
from app.utils.logger import logger


async def migrate_add_language_column() -> None:
    """Добавляет колонку language в таблицу users, если её нет."""
    try:
        async with engine.begin() as conn:
            # Проверяем, существует ли колонка language
            check_query = text(
                "SELECT COUNT(*) as count FROM pragma_table_info('users') "
                "WHERE name='language'"
            )
            result = await conn.execute(check_query)
            row = result.fetchone()
            
            if row and row[0] == 0:
                # Колонка не существует, добавляем её
                logger.info("Adding 'language' column to 'users' table...")
                add_column_query = text(
                    "ALTER TABLE users ADD COLUMN language VARCHAR(2) NOT NULL DEFAULT 'ru'"
                )
                await conn.execute(add_column_query)
                logger.info("Column 'language' added successfully with default value 'ru'")
            else:
                logger.info("Column 'language' already exists in 'users' table")
                
    except Exception as e:
        logger.error(f"Error during migration: {e}", exc_info=True)
        raise


async def main() -> None:
    """Точка входа для миграции."""
    logger.info("Starting migration: add language column")
    await migrate_add_language_column()
    logger.info("Migration completed successfully")


if __name__ == "__main__":
    asyncio.run(main())
