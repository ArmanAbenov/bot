"""Сервис для работы с историей диалогов."""
from typing import List

from sqlalchemy import select, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import ChatHistory
from app.utils.logger import logger


async def save_message(
    session: AsyncSession,
    user_id: int,
    role: str,
    content: str,
) -> ChatHistory:
    """
    Сохраняет сообщение в историю диалога.
    
    Args:
        session: Сессия базы данных
        user_id: Telegram ID пользователя
        role: Роль отправителя ("user" или "assistant")
        content: Текст сообщения
    
    Returns:
        Созданная запись ChatHistory
    """
    try:
        chat_message = ChatHistory(
            user_id=user_id,
            role=role,
            content=content,
        )
        session.add(chat_message)
        await session.commit()
        await session.refresh(chat_message)
        
        logger.info(f"[CHAT_HISTORY] Saved {role} message for user_id={user_id} (length: {len(content)})")
        return chat_message
    except Exception as e:
        await session.rollback()
        logger.error(f"[CHAT_HISTORY] Error saving message: {e}", exc_info=True)
        raise


async def get_recent_messages(
    session: AsyncSession,
    user_id: int,
    limit: int = 10,
) -> List[ChatHistory]:
    """
    Получает последние N сообщений для пользователя.
    
    Args:
        session: Сессия базы данных
        user_id: Telegram ID пользователя
        limit: Максимальное количество сообщений (по умолчанию 10)
    
    Returns:
        Список сообщений ChatHistory, отсортированных по времени (старые первыми)
    """
    try:
        stmt = (
            select(ChatHistory)
            .where(ChatHistory.user_id == user_id)
            .order_by(desc(ChatHistory.timestamp))
            .limit(limit)
        )
        result = await session.execute(stmt)
        messages = result.scalars().all()
        
        # Возвращаем в хронологическом порядке (старые первыми)
        messages.reverse()
        
        logger.info(f"[CHAT_HISTORY] Retrieved {len(messages)} messages for user_id={user_id}")
        return messages
    except Exception as e:
        logger.error(f"[CHAT_HISTORY] Error retrieving messages: {e}", exc_info=True)
        return []


async def clear_user_history(
    session: AsyncSession,
    user_id: int,
) -> int:
    """
    Очищает всю историю диалога для пользователя.
    
    Args:
        session: Сессия базы данных
        user_id: Telegram ID пользователя
    
    Returns:
        Количество удаленных записей
    """
    try:
        stmt = delete(ChatHistory).where(ChatHistory.user_id == user_id)
        result = await session.execute(stmt)
        await session.commit()
        
        deleted_count = result.rowcount
        logger.info(f"[CHAT_HISTORY] Cleared {deleted_count} messages for user_id={user_id}")
        return deleted_count
    except Exception as e:
        await session.rollback()
        logger.error(f"[CHAT_HISTORY] Error clearing history: {e}", exc_info=True)
        raise


def format_history_for_prompt(messages: List[ChatHistory]) -> str:
    """
    Форматирует историю сообщений для включения в промпт.
    
    Args:
        messages: Список сообщений ChatHistory
    
    Returns:
        Отформатированная строка истории диалога
    """
    if not messages:
        return ""
    
    history_lines: List[str] = []
    for msg in messages:
        role_label = "Пользователь" if msg.role == "user" else "Ассистент"
        history_lines.append(f"{role_label}: {msg.content}")
    
    return "\n".join(history_lines)
