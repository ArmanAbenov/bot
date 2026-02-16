"""Модели базы данных."""
from datetime import datetime
from enum import Enum
from typing import Union

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserRole(str, Enum):
    """Роли пользователей."""

    EMPLOYEE = "Employee"
    MANAGER = "Manager"
    ADMIN = "Admin"


class UserStatus(str, Enum):
    """Статусы пользователей."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    BLOCKED = "blocked"


class Department(str, Enum):
    """Отделы компании для multitenancy."""

    COMMON = "common"  # Общий доступ (по умолчанию для новых пользователей)
    COURIER = "delivery/courier"
    FRANCHISE = "delivery/franchise"
    SORTING = "sorting"
    CUSTOMER_SERVICE = "customer_service"
    MANAGER = "manager"
    
    @classmethod
    def get_display_names(cls) -> dict[str, str]:
        """Возвращает человекочитаемые названия отделов."""
        return {
            cls.COMMON.value: "Общий доступ",
            cls.COURIER.value: "Курьер",
            cls.FRANCHISE.value: "Франчайзи",
            cls.SORTING.value: "Сортировочный центр",
            cls.CUSTOMER_SERVICE.value: "Клиентский сервис",
            cls.MANAGER.value: "Менеджер",
        }
    
    @classmethod
    def get_admin_assignable_departments(cls) -> dict[str, str]:
        """Возвращает отделы, которые админ может назначать (без COMMON)."""
        return {
            cls.SORTING.value: "Сортировочный центр",
            cls.MANAGER.value: "Менеджер",
            cls.COURIER.value: "Курьер",
            cls.FRANCHISE.value: "Франчайзи",
            cls.CUSTOMER_SERVICE.value: "Клиентский сервис",
        }
    
    @classmethod
    def get_tree_structure(cls) -> dict:
        """Возвращает дерево выбора отделов для inline-кнопок."""
        return {
            "Доставка": {
                "Курьер": cls.COURIER,
                "Франчайзи": cls.FRANCHISE,
            },
            "Сортировочный центр": cls.SORTING,
            "Клиентский сервис": cls.CUSTOMER_SERVICE,
            "Менеджер": cls.MANAGER,
        }


class User(Base):
    """Модель пользователя."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    full_name: Mapped[Union[str, None]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="employee"
    )
    department: Mapped[Union[str, None]] = mapped_column(
        String(50), nullable=True, index=True
    )  # Отдел пользователя для multitenancy
    language: Mapped[str] = mapped_column(
        String(2), nullable=False, default="ru"
    )  # Язык интерфейса: ru, kk, en, zh
    registration_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<User(id={self.id}, telegram_id={self.telegram_id}, "
            f"full_name={self.full_name}, role={self.role})>"
        )


class OnboardingProgress(Base):
    """Модель прогресса онбординга."""

    __tablename__ = "onboarding_progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True
    )  # Foreign key to users.id
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    task_description: Mapped[Union[str, None]] = mapped_column(Text, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[Union[datetime, None]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<OnboardingProgress(id={self.id}, user_id={self.user_id}, "
            f"day={self.day_number}, task={self.task_name}, completed={self.completed})>"
        )


class ChatHistory(Base):
    """Модель истории диалогов с ботом."""

    __tablename__ = "chat_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True
    )  # Telegram user_id
    role: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "user" или "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<ChatHistory(id={self.id}, user_id={self.user_id}, "
            f"role={self.role}, timestamp={self.timestamp})>"
        )


class Admin(Base):
    """Модель администраторов бота."""

    __tablename__ = "admins"

    user_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, nullable=False
    )  # Telegram user_id (primary key)
    username: Mapped[str] = mapped_column(String(255), nullable=False)

    def __repr__(self) -> str:
        return f"<Admin(user_id={self.user_id}, username={self.username})>"
