"""Сервис для управления сотрудниками в админ-панели."""
import hashlib
from datetime import datetime
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import User
from app.utils.logger import logger


async def get_all_employees(session: AsyncSession) -> List[User]:
    """
    Получает список всех зарегистрированных пользователей.
    
    Args:
        session: Сессия базы данных
        
    Returns:
        Список пользователей
    """
    try:
        stmt = select(User).order_by(User.registration_date.desc())
        result = await session.execute(stmt)
        users = result.scalars().all()
        
        logger.info(f"[EMPLOYEES] Found {len(users)} registered users")
        return list(users)
    except Exception as e:
        logger.error(f"[EMPLOYEES] Error getting all employees: {e}", exc_info=True)
        return []


async def get_employee_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    """
    Получает пользователя по Telegram ID.
    
    Args:
        session: Сессия базы данных
        telegram_id: Telegram ID пользователя
        
    Returns:
        User или None если не найден
    """
    try:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            logger.info(f"[EMPLOYEES] Found user: {telegram_id} ({user.full_name})")
        else:
            logger.warning(f"[EMPLOYEES] User {telegram_id} not found")
            
        return user
    except Exception as e:
        logger.error(f"[EMPLOYEES] Error getting employee {telegram_id}: {e}", exc_info=True)
        return None


async def assign_department_to_employee(
    session: AsyncSession,
    telegram_id: int,
    department: str
) -> bool:
    """
    Назначает отдел сотруднику.
    
    Args:
        session: Сессия базы данных
        telegram_id: Telegram ID пользователя
        department: Код отдела (значение из Department enum)
        
    Returns:
        True если успешно, False иначе
    """
    try:
        # Находим пользователя
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(f"[EMPLOYEES] User {telegram_id} not found for department assignment")
            return False
        
        old_dept = user.department
        user.department = department
        await session.commit()
        
        logger.info(f"[EMPLOYEES] COMMIT executed for user {telegram_id}")
        
        # Проверяем что сохранилось
        await session.refresh(user)
        logger.info(
            f"[EMPLOYEES] ✅ Department assigned to {telegram_id} ({user.full_name}): "
            f"{department} (was: {old_dept})"
        )
        
        if user.department != department:
            logger.error(
                f"[EMPLOYEES] ❌ CRITICAL: Department NOT saved! "
                f"DB={user.department}, expected={department}"
            )
            return False
        
        return True
    except Exception as e:
        logger.error(
            f"[EMPLOYEES] Error assigning department to {telegram_id}: {e}",
            exc_info=True
        )
        await session.rollback()
        return False


def hash_user_id(telegram_id: int) -> str:
    """
    Создает короткий хеш для Telegram ID (для использования в callback_data).
    
    Args:
        telegram_id: Telegram ID пользователя
        
    Returns:
        Короткий хеш (8 символов)
    """
    hash_obj = hashlib.sha256(str(telegram_id).encode())
    return hash_obj.hexdigest()[:8]


def format_user_info(user: User, lang: str = "ru") -> str:
    """
    Форматирует информацию о пользователе для отображения.
    
    Args:
        user: Объект пользователя
        lang: Язык локализации
        
    Returns:
        Отформатированная строка с информацией
    """
    from app.core.i18n import i18n
    from app.core.models import Department
    
    # Получаем человекочитаемое название отдела
    dept_display_names = Department.get_display_names()
    department_name = dept_display_names.get(user.department, user.department or "Не назначен")
    
    # Форматируем дату
    reg_date = user.registration_date.strftime("%d.%m.%Y %H:%M") if user.registration_date else "Неизвестно"
    
    # Получаем роль на нужном языке
    role_mapping = {
        "admin": "Администратор",
        "employee": "Сотрудник",
        "manager": "Менеджер"
    }
    role_display = role_mapping.get(user.role, user.role)
    
    # Получаем язык пользователя
    language_mapping = {
        "ru": "Русский",
        "kk": "Қазақша",
        "en": "English",
        "zh": "中文"
    }
    language_display = language_mapping.get(user.language, user.language or "Не выбран")
    
    # Формируем текст
    lines = [
        i18n.get("employee_info_header", lang),
        "",
        i18n.get("employee_info_name", lang, name=user.full_name or "Неизвестно"),
        i18n.get("employee_info_id", lang, id=user.telegram_id),
        i18n.get("employee_info_role", lang, role=role_display),
        i18n.get("employee_info_department", lang, department=department_name),
        i18n.get("employee_info_language", lang, language=language_display),
        i18n.get("employee_info_registered", lang, date=reg_date),
    ]
    
    return "\n".join(lines)
