"""Конфигурация приложения."""
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

# Загружаем переменные окружения из .env
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)


class Settings(BaseSettings):
    """Настройки приложения."""

    bot_token: str = Field(..., alias="BOT_TOKEN")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    # OpenAI API key оставлен для обратной совместимости (если используется в других местах)
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/uqsoft.db",
        alias="DATABASE_URL",
    )
    # ID администраторов (можно указать через переменную окружения или использовать дефолтные)
    # Формат: "375693711,123456789" или просто одно число
    # Используем str для избежания автоматического JSON парсинга
    admin_ids_raw: str | None = Field(
        default=None,
        alias="ADMIN_IDS",
    )
    # Статичный инвайт-код для регистрации новых пользователей
    invite_code: str = Field(
        default="UQ2026",
        alias="INVITE_CODE",
    )

    @property
    def admin_ids(self) -> List[int]:
        """Возвращает список ID администраторов."""
        if self.admin_ids_raw is None:
            return [375693711]
        
        if isinstance(self.admin_ids_raw, str):
            # Парсим строку через запятую
            ids = [int(id_.strip()) for id_ in self.admin_ids_raw.split(",") if id_.strip()]
            return ids if ids else [375693711]
        
        return [375693711]

    class Config:
        """Конфигурация Pydantic."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Глобальный экземпляр настроек
settings = Settings()
