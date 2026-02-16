"""Сервис для работы с администраторами."""
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Admin
from app.utils.logger import logger


async def add_admin(session: AsyncSession, user_id: int, username: str) -> Admin:
    """
    Добавляет администратора в базу данных.
    
    Args:
        session: Сессия базы данных
        user_id: Telegram ID пользователя
        username: Имя пользователя (username)
    
    Returns:
        Созданная или обновленная запись Admin
    """
    try:
        # Проверяем, существует ли уже такой админ
        stmt = select(Admin).where(Admin.user_id == user_id)
        result = await session.execute(stmt)
        existing_admin = result.scalar_one_or_none()
        
        if existing_admin:
            # Обновляем username, если админ уже существует
            existing_admin.username = username
            await session.commit()
            await session.refresh(existing_admin)
            logger.info(f"[ADMIN] Updated admin user_id={user_id}, username={username}")
            return existing_admin
        else:
            # Создаем нового админа
            admin = Admin(user_id=user_id, username=username)
            session.add(admin)
            await session.commit()
            await session.refresh(admin)
            logger.info(f"[ADMIN] Added admin user_id={user_id}, username={username}")
            return admin
    except Exception as e:
        await session.rollback()
        logger.error(f"[ADMIN] Error adding admin: {e}", exc_info=True)
        raise


async def is_admin(session: AsyncSession, user_id: int) -> bool:
    """
    Проверяет, является ли пользователь администратором.
    
    Args:
        session: Сессия базы данных
        user_id: Telegram ID пользователя
    
    Returns:
        True если пользователь является админом, False в противном случае
    """
    try:
        stmt = select(Admin).where(Admin.user_id == user_id)
        result = await session.execute(stmt)
        admin = result.scalar_one_or_none()
        
        is_admin_result = admin is not None
        logger.debug(f"[ADMIN] Checked admin status for user_id={user_id}: {is_admin_result}")
        return is_admin_result
    except Exception as e:
        logger.error(f"[ADMIN] Error checking admin status: {e}", exc_info=True)
        return False


async def get_all_admins(session: AsyncSession) -> List[Admin]:
    """
    Получает список всех администраторов.
    
    Args:
        session: Сессия базы данных
    
    Returns:
        Список всех администраторов
    """
    try:
        stmt = select(Admin).order_by(Admin.user_id)
        result = await session.execute(stmt)
        admins = result.scalars().all()
        
        logger.info(f"[ADMIN] Retrieved {len(admins)} admins")
        return list(admins)
    except Exception as e:
        logger.error(f"[ADMIN] Error retrieving admins: {e}", exc_info=True)
        return []


async def remove_admin(session: AsyncSession, user_id: int) -> bool:
    """
    Удаляет администратора из базы данных.
    
    Args:
        session: Сессия базы данных
        user_id: Telegram ID пользователя
    
    Returns:
        True если админ успешно удален, False если произошла ошибка
    """
    try:
        # Ищем админа
        stmt = select(Admin).where(Admin.user_id == user_id)
        result = await session.execute(stmt)
        admin = result.scalar_one_or_none()
        
        if not admin:
            logger.warning(f"[ADMIN] Admin with user_id={user_id} not found")
            return False
        
        # Удаляем админа
        await session.delete(admin)
        await session.commit()
        
        logger.info(f"[ADMIN] Removed admin user_id={user_id}, username={admin.username}")
        return True
    except Exception as e:
        await session.rollback()
        logger.error(f"[ADMIN] Error removing admin: {e}", exc_info=True)
        return False
