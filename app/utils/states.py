"""FSM состояния для бота."""
from aiogram.fsm.state import State, StatesGroup


class QuestionState(StatesGroup):
    """Состояние ожидания вопроса от пользователя."""
    
    waiting_for_question = State()


class AdminState(StatesGroup):
    """Состояния для админ-панели."""
    
    waiting_for_knowledge_text = State()  # Ожидание текста для добавления в базу знаний
    waiting_for_document = State()  # Ожидание документа для загрузки в базу знаний
    wait_for_new_admin_id = State()  # Ожидание ID нового админа (пересылка сообщения или ввод ID)
    waiting_for_department_choice = State()  # Ожидание выбора отдела для добавления знаний


class RegistrationState(StatesGroup):
    """Состояния для регистрации пользователя."""
    
    waiting_for_invite_code = State()  # Ожидание инвайт-кода
    waiting_for_language = State()  # Ожидание выбора языка
    waiting_for_department = State()  # Ожидание выбора отдела
