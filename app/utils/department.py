"""Утилиты для работы с отделами (multitenancy)."""
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Department, User
from app.utils.logger import logger


async def get_user_department(session: AsyncSession, user_id: int) -> str | None:
    """
    Получает отдел пользователя из БД.
    
    Args:
        session: Сессия БД
        user_id: Telegram ID пользователя
        
    Returns:
        Название отдела или None если не установлен
    """
    try:
        stmt = select(User.department).where(User.telegram_id == user_id)
        result = await session.execute(stmt)
        department = result.scalar_one_or_none()
        
        if department:
            logger.info(f"[DEPT] User {user_id} belongs to department: {department}")
        else:
            logger.warning(f"[DEPT] User {user_id} has no department assigned")
            
        return department
    except Exception as e:
        logger.error(f"[DEPT] Error getting department for user {user_id}: {e}", exc_info=True)
        return None


async def set_user_department(session: AsyncSession, user_id: int, department: str) -> bool:
    """
    Устанавливает отдел для пользователя.
    
    Args:
        session: Сессия БД
        user_id: Telegram ID пользователя
        department: Код отдела (Department enum value)
        
    Returns:
        True если успешно, False иначе
    """
    try:
        stmt = (
            update(User)
            .where(User.telegram_id == user_id)
            .values(department=department)
        )
        await session.execute(stmt)
        await session.commit()
        
        logger.info(f"[DEPT] User {user_id} assigned to department: {department}")
        return True
    except Exception as e:
        logger.error(f"[DEPT] Error setting department for user {user_id}: {e}", exc_info=True)
        await session.rollback()
        return False


def get_department_path(department: str) -> str:
    """
    Получает путь к папке отдела.
    
    Args:
        department: Код отдела
        
    Returns:
        Путь к папке относительно knowledge/
    """
    return department


def get_department_display_name(department: str) -> str:
    """
    Получает человекочитаемое название отдела.
    
    Args:
        department: Код отдела
        
    Returns:
        Отображаемое название
    """
    display_names = Department.get_display_names()
    
    # Находим по значению enum
    for dept_enum in Department:
        if dept_enum.value == department:
            return display_names.get(dept_enum, department)
    
    return department
