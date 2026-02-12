"""Сервис для хранения памяти диалога пользователя."""
from collections import deque
from typing import Deque, List

from app.utils.logger import logger


class DialogMemory:
    """Класс для хранения истории диалога пользователя."""
    
    def __init__(self, max_messages: int = 5) -> None:
        """
        Инициализация памяти диалога.
        
        Args:
            max_messages: Максимальное количество сообщений для хранения
        """
        self.max_messages = max_messages
        # Хранилище: user_id -> deque([(role, content), ...])
        self.memories: dict[int, Deque[tuple[str, str]]] = {}
    
    def add_message(self, user_id: int, role: str, content: str) -> None:
        """
        Добавляет сообщение в историю диалога пользователя.
        
        Args:
            user_id: ID пользователя Telegram
            role: Роль ('user' или 'assistant')
            content: Содержимое сообщения
        """
        if user_id not in self.memories:
            self.memories[user_id] = deque(maxlen=self.max_messages)
        
        self.memories[user_id].append((role, content))
        logger.debug(f"Added message to dialog memory for user {user_id}: {role}")
    
    def get_history(self, user_id: int) -> List[tuple[str, str]]:
        """
        Возвращает историю диалога пользователя.
        
        Args:
            user_id: ID пользователя Telegram
        
        Returns:
            Список кортежей (role, content)
        """
        if user_id not in self.memories:
            return []
        
        return list(self.memories[user_id])
    
    def get_history_text(self, user_id: int) -> str:
        """
        Возвращает историю диалога в виде текста для контекста.
        
        Args:
            user_id: ID пользователя Telegram
        
        Returns:
            Текстовая история диалога
        """
        history = self.get_history(user_id)
        if not history:
            return ""
        
        lines: List[str] = []
        for role, content in history:
            role_display = "Пользователь" if role == "user" else "Ассистент"
            lines.append(f"{role_display}: {content}")
        
        return "\n".join(lines)
    
    def clear_history(self, user_id: int) -> None:
        """
        Очищает историю диалога пользователя.
        
        Args:
            user_id: ID пользователя Telegram
        """
        if user_id in self.memories:
            self.memories[user_id].clear()
            logger.info(f"Cleared dialog memory for user {user_id}")
    
    def remove_user(self, user_id: int) -> None:
        """
        Удаляет пользователя из памяти.
        
        Args:
            user_id: ID пользователя Telegram
        """
        if user_id in self.memories:
            del self.memories[user_id]
            logger.info(f"Removed user {user_id} from dialog memory")


# Глобальный экземпляр для хранения памяти диалогов
dialog_memory = DialogMemory(max_messages=5)
