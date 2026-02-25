"""Хендлеры для администраторов."""
import hashlib
from pathlib import Path
from typing import Dict, Tuple

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup
from sqlalchemy import select

from app.bot.keyboards.main_menu import get_main_menu
from app.bot.keyboards.department import get_admin_department_keyboard, get_delivery_submenu_keyboard
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.models import Admin, Department
from app.services.ai_service import GeminiService
from app.services.admin_service import add_admin, get_all_admins, is_admin, remove_admin
from app.services.employee_service import (
    get_all_employees,
    get_employee_by_telegram_id,
    assign_department_to_employee,
    hash_user_id,
    format_user_info,
)
from app.utils.filters import IsAdmin
from app.utils.logger import logger
from app.utils.states import AdminState
from app.utils.department import get_department_display_name

router = Router(name="admin")

# Глобальное хранилище маппинга хешей на полные имена файлов
# Формат: {file_hash: (dept_name, filename)}
_file_hash_map: Dict[str, Tuple[str, str]] = {}


def generate_file_hash(dept_name: str, filename: str) -> str:
    """Генерирует короткий хеш для файла (10 символов)."""
    full_path = f"{dept_name}:{filename}"
    return hashlib.md5(full_path.encode()).hexdigest()[:10]


def register_file_hash(dept_name: str, filename: str) -> str:
    """Регистрирует файл в маппинге и возвращает его хеш."""
    file_hash = generate_file_hash(dept_name, filename)
    _file_hash_map[file_hash] = (dept_name, filename)
    logger.debug(f"Registered file hash: {file_hash} -> {dept_name}/{filename}")
    return file_hash


def get_file_by_hash(file_hash: str) -> Tuple[str, str] | None:
    """Получает dept_name и filename по хешу."""
    return _file_hash_map.get(file_hash)


async def check_admin_access(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором через БД."""
    try:
        async with AsyncSessionLocal() as session:
            return await is_admin(session, user_id)
    except Exception as e:
        logger.error(f"Error checking admin access for {user_id}: {e}", exc_info=True)
        return False


async def get_main_menu_for_user(user_id: int, role: str | None = None, lang: str = "ru") -> ReplyKeyboardMarkup:
    """
    Возвращает главное меню с учетом статуса админа в БД.
    
    Args:
        user_id: Telegram ID пользователя
        role: Роль пользователя из таблицы users
        lang: Код языка пользователя
    
    Returns:
        ReplyKeyboardMarkup с правильной клавиатурой
    """
    async with AsyncSessionLocal() as session:
        user_is_admin = await is_admin(session, user_id)
    return get_main_menu(role=role, is_admin=user_is_admin, lang=lang)


def get_admin_menu(lang: str = "ru") -> ReplyKeyboardMarkup:
    """
    Возвращает клавиатуру админ-панели.
    
    Args:
        lang: Код языка (ru, kk, en, zh)
    
    Returns:
        ReplyKeyboardMarkup с локализованными кнопками
    """
    from app.core.i18n import i18n
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=i18n.get("admin_add_knowledge", lang))],
            [KeyboardButton(text=i18n.get("admin_add_file", lang))],
            [KeyboardButton(text=i18n.get("admin_manage_knowledge", lang))],
            [KeyboardButton(text=i18n.get("admin_manage_employees", lang))],
            [KeyboardButton(text=i18n.get("admin_manage_admins", lang))],
            [KeyboardButton(text=i18n.get("admin_invite_code", lang))],
            [KeyboardButton(text=i18n.get("main_menu_back", lang))],
        ],
        resize_keyboard=True,
    )
    return keyboard


def create_knowledge_files_keyboard(files: list[str]) -> InlineKeyboardMarkup:
    """Создает inline-клавиатуру со списком файлов и кнопками удаления.
    
    УСТАРЕЛО: Эта функция используется в старом коде управления знаниями.
    Новая иерархическая система использует хеши для callback_data.
    """
    buttons: list[list[InlineKeyboardButton]] = []
    
    for filename in files:
        # Регистрируем файл и получаем короткий хеш
        # Используем dept_name="legacy" для обратной совместимости
        file_hash = register_file_hash("legacy", filename)
        
        # Обрезаем длинное имя файла для отображения
        display_name = filename if len(filename) <= 30 else filename[:27] + "..."
        
        buttons.append([
            InlineKeyboardButton(
                text=f"📄 {display_name}",
                callback_data=f"view_file:{file_hash}"
            ),
            InlineKeyboardButton(
                text="❌ Удалить",
                callback_data=f"delete_file:{file_hash}"
            )
        ])
    
    # Кнопка обновления списка
    buttons.append([
        InlineKeyboardButton(
            text="🔄 Обновить список",
            callback_data="refresh_knowledge_files"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(lambda message: message.text in [
    "👑 Админ-панель",
    "👑 Әкімші панелі",
    "👑 Admin Panel",
    "👑 管理面板"
])
async def handle_admin_panel(message: Message, role: str | None = None, lang: str = "ru", i18n = None) -> None:
    """Открывает админ-панель."""
    try:
        from app.core.i18n import i18n as i18n_manager
        if i18n is None:
            i18n = i18n_manager
            
        # Проверяем, что пользователь — админ через БД
        async with AsyncSessionLocal() as session:
            user_is_admin = await is_admin(session, message.from_user.id)
            if not user_is_admin:
                await message.answer(i18n.get("admin_no_access", lang))
                return
        
        await message.answer(
            i18n.get("admin_welcome", lang),
            reply_markup=get_admin_menu(lang)
        )
        logger.info(f"Admin {message.from_user.id} opened admin panel")
        
    except Exception as e:
        logger.error(f"Error in admin panel handler: {e}", exc_info=True)
        # Проверяем, является ли пользователь админом через БД
        async with AsyncSessionLocal() as session:
            user_is_admin = await is_admin(session, message.from_user.id)
        await message.answer(i18n.get("admin_error", lang), reply_markup=get_main_menu(role=role, is_admin=user_is_admin, lang=lang))


@router.message(lambda message: message.text in [
    "◀️ Назад в меню",
    "◀️ Мәзірге оралу",
    "◀️ Back to menu",
    "◀️ 返回菜单"
])
async def handle_back_to_menu(message: Message, state: FSMContext, role: str | None = None, lang: str = "ru", i18n = None) -> None:
    """Возврат в главное меню."""
    try:
        from app.core.i18n import i18n as i18n_manager
        if i18n is None:
            i18n = i18n_manager
            
        await state.clear()
        
        # Проверяем, является ли пользователь админом через БД
        async with AsyncSessionLocal() as session:
            user_is_admin = await is_admin(session, message.from_user.id)
        
        await message.answer(
            i18n.get("admin_main_menu", lang),
            reply_markup=get_main_menu(role=role, is_admin=user_is_admin, lang=lang)
        )
    except Exception as e:
        logger.error(f"Error in back to menu handler: {e}", exc_info=True)
        await state.clear()
        async with AsyncSessionLocal() as session:
            user_is_admin = await is_admin(session, message.from_user.id)
        await message.answer(
            "Главное меню:" if lang == "ru" else "Main menu:",
            reply_markup=get_main_menu(role=role, is_admin=user_is_admin, lang=lang)
        )


@router.message(lambda message: message.text in [
    "🔑 Инвайт-код",
    "🔑 Шақыру коды",
    "🔑 Invite Code",
    "🔑 邀请码"
])
async def handle_invite_code_button(message: Message, role: str | None = None, lang: str = "ru") -> None:
    """Показывает инвайт-код (кнопка)."""
    try:
        if not await check_admin_access(message.from_user.id):
            from app.core.i18n import i18n
            await message.answer(i18n.get("admin_no_access_short", lang))
            return
        
        invite_code = settings.invite_code
        await message.answer(
            f"🔑 Текущий инвайт-код: `{invite_code}`\n\n"
            "Поделись этим кодом с новыми сотрудниками для регистрации.",
            parse_mode="Markdown",
            reply_markup=get_admin_menu(lang)
        )
        logger.info(f"Admin {message.from_user.id} requested invite code")
        
    except Exception as e:
        logger.error(f"Error in invite code button handler: {e}", exc_info=True)
        from app.core.i18n import i18n
        await message.answer(i18n.get("admin_error", lang), reply_markup=get_admin_menu(lang))


@router.message(lambda message: message.text in [
    "📝 Добавить знание",
    "📝 Білім қосу",
    "📝 Add Knowledge",
    "📝 添加知识"
])
async def handle_add_knowledge_button(message: Message, state: FSMContext, role: str | None = None, lang: str = "ru") -> None:
    """Начинает процесс добавления знания в базу."""
    try:
        if not await check_admin_access(message.from_user.id):
            from app.core.i18n import i18n
            await message.answer(i18n.get("admin_no_access_short", lang))
            return
        
        # Переводим в состояние ожидания текста
        await state.set_state(AdminState.waiting_for_knowledge_text)
        
        await message.answer(
            "📝 Добавление знания в базу\n\n"
            "Отправьте текст или голосовое сообщение, которое нужно добавить в базу знаний.\n\n"
            "AI автоматически:\n"
            "• Распознает речь (если голосовое)\n"
            "• Придумает название файла\n"
            "• Структурирует текст\n"
            "• Сохранит в базу знаний\n\n"
            "Для отмены нажмите /cancel",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="/cancel")]],
                resize_keyboard=True,
            )
        )
        logger.info(f"Admin {message.from_user.id} started adding knowledge")
        
    except Exception as e:
        logger.error(f"Error in add knowledge button handler: {e}", exc_info=True)
        from app.core.i18n import i18n
        await message.answer(i18n.get("admin_error", lang), reply_markup=get_admin_menu(lang))


@router.message(Command("cancel"), StateFilter(AdminState.waiting_for_knowledge_text))
async def handle_cancel_add_knowledge(message: Message, state: FSMContext, role: str | None = None, lang: str = "ru") -> None:
    """Отмена добавления знания."""
    await state.clear()
    # Проверяем доступ через БД
    user_is_admin = await check_admin_access(message.from_user.id)
    from app.core.i18n import i18n
    await message.answer(
        i18n.get("admin_cancel_knowledge", lang),
        reply_markup=get_admin_menu(lang) if user_is_admin else await get_main_menu_for_user(message.from_user.id, role, lang)
    )
    logger.info(f"Admin {message.from_user.id} cancelled adding knowledge")


@router.message(StateFilter(AdminState.waiting_for_knowledge_text), F.voice)
async def handle_knowledge_voice(
    message: Message,
    bot: Bot,
    state: FSMContext,
    role: str | None = None,
    lang: str = "ru"
) -> None:
    """Обрабатывает голосовое сообщение для добавления в базу знаний."""
    try:
        if not await check_admin_access(message.from_user.id):
            await state.clear()
            await message.answer("У вас нет доступа.")
            return
        
        if not message.voice:
            return
        
        telegram_id = message.from_user.id
        voice = message.voice
        
        logger.info(f"Admin {telegram_id} sent voice message (duration: {voice.duration}s, size: {voice.file_size} bytes)")
        
        # Показываем статус
        await bot.send_chat_action(chat_id=telegram_id, action="typing")
        await message.answer("🎙️ Анализирую аудио...")
        
        try:
            import tempfile
            
            # Создаем временный файл для .ogg
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp_audio:
                temp_audio_path = Path(temp_audio.name)
            
            try:
                # Скачиваем голосовое сообщение
                logger.info(f"[VOICE] Downloading voice file_id={voice.file_id}...")
                file_info = await bot.get_file(voice.file_id)
                await bot.download_file(
                    file_path=file_info.file_path,
                    destination=temp_audio_path
                )
                logger.info(f"[VOICE] Voice file downloaded to {temp_audio_path} ({temp_audio_path.stat().st_size} bytes)")
                
                # Обрабатываем аудио через Gemini
                await message.answer("⏳ Структурирую знание с помощью AI...")
                filename, structured_text = await GeminiService.process_knowledge_audio(temp_audio_path)
                
                # Сохраняем данные в state для последующего использования
                await state.update_data(
                    filename=filename,
                    structured_text=structured_text,
                    content_type="voice"
                )
                
                # Переводим в состояние выбора отдела
                await state.set_state(AdminState.waiting_for_department_choice)
                
                # Показываем клавиатуру выбора отдела
                await message.answer(
                    f"✅ AI обработал голосовое сообщение!\n\n"
                    f"📄 Файл: {filename}.txt\n"
                    f"📊 Размер: {len(structured_text)} символов\n\n"
                    f"📂 В какой отдел добавить это знание?",
                    reply_markup=get_admin_department_keyboard()
                )
                
            finally:
                # Удаляем временный файл
                if temp_audio_path.exists():
                    temp_audio_path.unlink()
                    logger.info(f"[VOICE] Deleted temp audio file: {temp_audio_path}")
                    
        except Exception as e:
            logger.error(f"Error processing voice knowledge: {e}", exc_info=True)
            await message.answer(
                f"❌ Ошибка при обработке голосового сообщения:\n{str(e)}\n\n"
                "Попробуйте еще раз или нажмите /cancel для отмены.",
            )
            
    except Exception as e:
        logger.error(f"Error in voice knowledge handler: {e}", exc_info=True)
        await state.clear()
        # Проверяем доступ через БД
        user_is_admin = await check_admin_access(message.from_user.id)
        await message.answer(
            "Произошла ошибка при обработке голосового сообщения.",
            reply_markup=get_admin_menu(lang) if user_is_admin else await get_main_menu_for_user(message.from_user.id, role, lang)
        )


@router.message(StateFilter(AdminState.waiting_for_knowledge_text), F.text)
async def handle_knowledge_text(
    message: Message,
    bot: Bot,
    state: FSMContext,
    role: str | None = None,
    lang: str = "ru"
) -> None:
    """Обрабатывает текст для добавления в базу знаний."""
    try:
        if not await check_admin_access(message.from_user.id):
            await state.clear()
            await message.answer("У вас нет доступа.")
            return
        
        raw_text = message.text.strip()
        
        if raw_text.startswith("/"):
            # Это команда, пропускаем
            return
        
        if len(raw_text) < 10:
            await message.answer(
                "⚠️ Текст слишком короткий. Отправьте более содержательный текст.",
            )
            return
        
        telegram_id = message.from_user.id
        logger.info(f"Admin {telegram_id} sent knowledge text (length: {len(raw_text)} chars)")
        
        # Показываем статус
        await bot.send_chat_action(chat_id=telegram_id, action="typing")
        await message.answer("⏳ Обрабатываю текст с помощью AI...")
        
        try:
            # Обрабатываем текст через Gemini
            filename, structured_text = GeminiService.process_knowledge_text(raw_text)
            
            # Сохраняем данные в state для последующего использования
            await state.update_data(
                filename=filename,
                structured_text=structured_text,
                content_type="text"
            )
            
            # Переводим в состояние выбора отдела
            await state.set_state(AdminState.waiting_for_department_choice)
            
            # Показываем клавиатуру выбора отдела
            await message.answer(
                f"✅ AI обработал текст!\n\n"
                f"📄 Файл: {filename}.txt\n"
                f"📊 Размер: {len(structured_text)} символов\n\n"
                f"📂 В какой отдел добавить это знание?",
                reply_markup=get_admin_department_keyboard()
            )
            
        except Exception as e:
            logger.error(f"Error processing knowledge text: {e}", exc_info=True)
            await message.answer(
                f"❌ Ошибка при обработке текста:\n{str(e)}\n\n"
                "Попробуйте еще раз или нажмите /cancel для отмены.",
            )
            
    except Exception as e:
        logger.error(f"Error in knowledge text handler: {e}", exc_info=True)
        await state.clear()
        # Проверяем доступ через БД
        user_is_admin = await check_admin_access(message.from_user.id)
        await message.answer(
            "Произошла ошибка при обработке текста.",
            reply_markup=get_admin_menu(lang) if user_is_admin else await get_main_menu_for_user(message.from_user.id, role, lang)
        )


@router.message(lambda message: message.text in [
    "📥 Добавить файл",
    "📥 Файл қосу",
    "📥 Add File",
    "📥 添加文件"
])
async def handle_add_file_button(message: Message, state: FSMContext, role: str | None = None, lang: str = "ru") -> None:
    """Начинает процесс загрузки файла в базу знаний."""
    try:
        if not await check_admin_access(message.from_user.id):
            from app.core.i18n import i18n
            await message.answer(i18n.get("admin_no_access_short", lang))
            return
        
        # Переводим в состояние ожидания документа
        await state.set_state(AdminState.waiting_for_document)
        
        await message.answer(
            "📥 Загрузка файла в базу знаний\n\n"
            "Отправьте файл с расширением:\n"
            "• .pdf\n"
            "• .txt\n"
            "• .docx\n\n"
            "Файл будет сохранен с оригинальным именем в папку data/knowledge/\n\n"
            "Для отмены нажмите /cancel",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="/cancel")]],
                resize_keyboard=True,
            )
        )
        logger.info(f"Admin {message.from_user.id} started adding file")
        
    except Exception as e:
        logger.error(f"Error in add file button handler: {e}", exc_info=True)
        from app.core.i18n import i18n
        await message.answer(i18n.get("admin_error", lang), reply_markup=get_admin_menu(lang))


@router.message(Command("cancel"), StateFilter(AdminState.waiting_for_document))
async def handle_cancel_add_file(message: Message, state: FSMContext, role: str | None = None, lang: str = "ru") -> None:
    """Отмена загрузки файла."""
    await state.clear()
    # Проверяем доступ через БД
    user_is_admin = await check_admin_access(message.from_user.id)
    from app.core.i18n import i18n
    await message.answer(
        i18n.get("admin_cancel_file", lang),
        reply_markup=get_admin_menu(lang) if user_is_admin else await get_main_menu_for_user(message.from_user.id, role, lang)
    )
    logger.info(f"Admin {message.from_user.id} cancelled adding file")


@router.message(StateFilter(AdminState.waiting_for_document), F.document)
async def handle_document_upload(
    message: Message,
    bot: Bot,
    state: FSMContext,
    role: str | None = None,
    lang: str = "ru"
) -> None:
    """Обрабатывает загрузку документа в базу знаний."""
    try:
        if not await check_admin_access(message.from_user.id):
            await state.clear()
            await message.answer("У вас нет доступа.")
            return
        
        if not message.document:
            await message.answer(
                "⚠️ Пожалуйста, отправьте файл как документ (не как фото)."
            )
            return
        
        document = message.document
        filename = document.file_name
        
        if not filename:
            await message.answer(
                "⚠️ Файл не имеет имени. Пожалуйста, отправьте файл с именем."
            )
            return
        
        # Проверяем расширение файла
        allowed_extensions = {".pdf", ".txt", ".docx"}
        file_ext = Path(filename).suffix.lower()
        
        if file_ext not in allowed_extensions:
            await message.answer(
                f"⚠️ Неподдерживаемый формат файла: {file_ext}\n\n"
                f"Поддерживаемые форматы: {', '.join(allowed_extensions)}\n"
                "Пожалуйста, отправьте файл с правильным расширением."
            )
            return
        
        telegram_id = message.from_user.id
        logger.info(f"Admin {telegram_id} sent file: {filename} (size: {document.file_size} bytes)")
        
        # Показываем статус
        await bot.send_chat_action(chat_id=telegram_id, action="upload_document")
        
        try:
            # Сохраняем данные в state для последующего использования
            await state.update_data(
                filename=filename,
                file_id=document.file_id,
                file_size=document.file_size,
                content_type="document"
            )
            
            # Переводим в состояние выбора отдела
            await state.set_state(AdminState.waiting_for_department_choice)
            
            # Показываем клавиатуру выбора отдела
            await message.answer(
                f"✅ Файл получен!\n\n"
                f"📄 Имя: {filename}\n"
                f"📊 Размер: {document.file_size} байт\n\n"
                f"📂 В какой отдел добавить этот файл?",
                reply_markup=get_admin_department_keyboard()
            )
            
        except Exception as e:
            logger.error(f"Error processing file upload: {e}", exc_info=True)
            await message.answer(
                f"❌ Ошибка при загрузке файла:\n{str(e)}\n\n"
                "Попробуйте еще раз или нажмите /cancel для отмены.",
            )
            
    except Exception as e:
        logger.error(f"Error in document upload handler: {e}", exc_info=True)
        await state.clear()
        # Проверяем доступ через БД
        user_is_admin = await check_admin_access(message.from_user.id)
        await message.answer(
            "Произошла ошибка при обработке файла.",
            reply_markup=get_admin_menu(lang) if user_is_admin else await get_main_menu_for_user(message.from_user.id, role, lang)
        )


@router.message(lambda message: message.text in [
    "📚 Управление базой знаний",
    "📚 Білім базасын басқару",
    "📚 Manage Knowledge Base",
    "📚 管理知识库"
])
async def handle_manage_knowledge(message: Message, role: str | None = None, lang: str = "ru") -> None:
    """Показывает список отделов с кнопками для навигации."""
    try:
        if not await check_admin_access(message.from_user.id):
            from app.core.i18n import i18n
            await message.answer(i18n.get("admin_no_access_short", lang))
            return
        
        from app.core.i18n import i18n
        
        # Получаем статистику по отделам
        stats = GeminiService.get_knowledge_stats()
        
        if not stats:
            await message.answer(
                i18n.get("kb_empty", lang),
                reply_markup=get_admin_menu(lang)
            )
            return
        
        # Маппинг для локализации названий отделов
        dept_names = {
            "common": i18n.get("kb_dept_common", lang),
            "delivery": i18n.get("department_delivery", lang),
            "sorting": i18n.get("department_sorting", lang),
            "manager": i18n.get("department_manager", lang),
            "customer_service": i18n.get("department_customer_service", lang),
        }
        
        # Создаем inline-клавиатуру с отделами
        buttons: list[list[InlineKeyboardButton]] = []
        
        for dept_key in sorted(stats.keys()):
            count = stats[dept_key]
            dept_display = dept_names.get(dept_key, dept_key.replace("_", " ").title())
            
            # Кнопка с названием отдела и количеством файлов
            buttons.append([
                InlineKeyboardButton(
                    text=f"📂 {dept_display} ({count})",
                    callback_data=f"kb_dept:{dept_key}"
                )
            ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        text = i18n.get("kb_select_department", lang)
        total_files = sum(stats.values())
        text += f"\n\n📊 {i18n.get('kb_total', lang)}: {total_files} {i18n.get('kb_documents', lang)}"
        
        await message.answer(text, reply_markup=keyboard)
        logger.info(f"Admin {message.from_user.id} opened knowledge base management")
        
    except Exception as e:
        logger.error(f"Error in manage knowledge handler: {e}", exc_info=True)
        from app.core.i18n import i18n
        await message.answer(i18n.get("admin_error", lang), reply_markup=get_admin_menu(lang))


@router.callback_query(F.data.startswith("delete_file:"))
async def handle_delete_file(callback: CallbackQuery, role: str | None = None) -> None:
    """Обрабатывает удаление файла из базы знаний (legacy код)."""
    try:
        if not await check_admin_access(callback.from_user.id):
            await callback.answer("У вас нет доступа.", show_alert=True)
            return
        
        # Извлекаем file_hash из callback_data
        file_hash = callback.data.replace("delete_file:", "")
        
        # Получаем filename по хешу
        file_data = get_file_by_hash(file_hash)
        
        if not file_data:
            await callback.answer("Ошибка: файл не найден в маппинге.", show_alert=True)
            logger.error(f"File hash not found for legacy delete: {file_hash}")
            return
        
        dept_name, filename = file_data
        
        logger.info(f"Admin {callback.from_user.id} requested deletion of file: {filename}")
        
        try:
            # Удаляем файл
            GeminiService.delete_knowledge_file(filename)
            
            # Удаляем из маппинга
            if file_hash in _file_hash_map:
                del _file_hash_map[file_hash]
            
            # Обновляем векторный индекс в памяти
            try:
                logger.info("[RAG] Reloading indices after file deletion...")
                await GeminiService.reload_indices()
                logger.info("[RAG] Indices reloaded successfully")
            except Exception as e:
                logger.error(f"[RAG] Error reloading indices: {e}", exc_info=True)
            
            # Обновляем список файлов
            files = GeminiService.get_knowledge_files()
            
            # Создаем клавиатуру с предложениями
            action_buttons = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="📥 Загрузить файл",
                            callback_data="admin_add_file_after_delete"
                        ),
                        InlineKeyboardButton(
                            text="◀️ Вернуться в меню",
                            callback_data="admin_back_to_menu"
                        )
                    ]
                ]
            )
            
            if not files:
                await callback.message.edit_text(
                    "📚 База знаний пуста.\n\n"
                    f"✅ Файл {filename} успешно удален.\n\n"
                    "Что хотите сделать дальше?",
                    reply_markup=action_buttons
                )
                await callback.answer(f"✅ Файл {filename} удален. База знаний пуста.")
            else:
                text = "📚 Управление базой знаний\n\n"
                text += f"✅ Файл {filename} успешно удален.\n\n"
                text += f"Осталось файлов: {len(files)}\n\n"
                text += "Выберите файл для удаления:"
                
                keyboard = create_knowledge_files_keyboard(files)
                keyboard.inline_keyboard.extend(action_buttons.inline_keyboard)
                
                await callback.message.edit_text(text, reply_markup=keyboard)
                await callback.answer(f"✅ Файл {filename} успешно удален")
            
            logger.info(f"Admin {callback.from_user.id} deleted file: {filename}")
            
        except Exception as e:
            logger.error(f"Error deleting file {filename}: {e}", exc_info=True)
            await callback.answer(f"❌ Ошибка при удалении файла: {str(e)}", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error in delete file handler: {e}", exc_info=True)
        await callback.answer("Произошла ошибка при удалении файла.", show_alert=True)


@router.callback_query(F.data == "refresh_knowledge_files")
async def handle_refresh_knowledge_files(callback: CallbackQuery, role: str | None = None) -> None:
    """Обновляет список файлов базы знаний."""
    try:
        if not await check_admin_access(callback.from_user.id):
            await callback.answer("У вас нет доступа.", show_alert=True)
            return
        
        files = GeminiService.get_knowledge_files()
        
        if not files:
            await callback.message.edit_text(
                "📚 База знаний пуста.\n\n"
                "Используйте '📝 Добавить знание' для добавления новых файлов."
            )
            await callback.answer("Список обновлен. База знаний пуста.")
            return
        
        text = "📚 Управление базой знаний\n\n"
        text += f"Всего файлов: {len(files)}\n\n"
        text += "Выберите файл для удаления:"
        
        keyboard = create_knowledge_files_keyboard(files)
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer("✅ Список файлов обновлен")
        
        logger.info(f"Admin {callback.from_user.id} refreshed knowledge files list")
        
    except Exception as e:
        logger.error(f"Error in refresh knowledge files handler: {e}", exc_info=True)
        await callback.answer("Произошла ошибка при обновлении списка.", show_alert=True)


@router.callback_query(F.data.startswith("view_file:"))
async def handle_view_file(callback: CallbackQuery, role: str | None = None) -> None:
    """Показывает информацию о файле (legacy код - заглушка для будущего расширения)."""
    file_hash = callback.data.replace("view_file:", "")
    
    # Получаем filename по хешу
    file_data = get_file_by_hash(file_hash)
    
    if not file_data:
        await callback.answer("Файл не найден в маппинге.", show_alert=True)
        return
    
    _, filename = file_data
    await callback.answer(f"Файл: {filename}", show_alert=True)


@router.callback_query(F.data == "admin_add_file_after_delete")
async def handle_add_file_after_delete(callback: CallbackQuery, state: FSMContext, role: str | None = None) -> None:
    """Переводит админа в режим загрузки файла после удаления."""
    try:
        if not await check_admin_access(callback.from_user.id):
            await callback.answer("У вас нет доступа.", show_alert=True)
            return
        
        # Переводим в состояние ожидания документа
        await state.set_state(AdminState.waiting_for_document)
        
        await callback.message.edit_text(
            "📥 Загрузка файла в базу знаний\n\n"
            "Отправьте файл с расширением:\n"
            "• .pdf\n"
            "• .txt\n"
            "• .docx\n\n"
            "Файл будет сохранен с оригинальным именем в папку data/knowledge/\n\n"
            "Для отмены нажмите /cancel"
        )
        await callback.answer("✅ Готов к загрузке файла")
        logger.info(f"Admin {callback.from_user.id} started adding file after delete")
        
    except Exception as e:
        logger.error(f"Error in add file after delete handler: {e}", exc_info=True)
        await callback.answer("Произошла ошибка.", show_alert=True)


@router.callback_query(F.data == "admin_back_to_menu")
async def handle_back_to_menu_from_delete(callback: CallbackQuery, role: str | None = None) -> None:
    """Возвращает админа в меню после удаления файла."""
    try:
        if not await check_admin_access(callback.from_user.id):
            await callback.answer("У вас нет доступа.", show_alert=True)
            return
        
        await callback.message.edit_text(
            "⚙️ Админ-панель\n\n"
            "Выберите действие:"
        )
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=get_admin_menu("ru")
        )
        await callback.answer("✅ Возврат в меню")
        logger.info(f"Admin {callback.from_user.id} returned to admin menu")
        
    except Exception as e:
        logger.error(f"Error in back to menu handler: {e}", exc_info=True)
        await callback.answer("Произошла ошибка.", show_alert=True)


@router.message(Command("generate_invite"), IsAdmin())
async def cmd_generate_invite(message: Message) -> None:
    """Генерация инвайт-кода для администратора (команда)."""
    try:
        invite_code = settings.invite_code
        await message.answer(
            f"🔑 Текущий инвайт-код: `{invite_code}`\n\n"
            "Поделись этим кодом с новыми сотрудниками для регистрации.",
            parse_mode="Markdown"
        )
        logger.info(f"Admin {message.from_user.id} requested invite code via command")
    except Exception as e:
        logger.error(f"Error in /generate_invite handler: {e}", exc_info=True)
        await message.answer("Произошла ошибка при генерации инвайт-кода.")


@router.message(Command("reload"))
async def cmd_reload_indices(message: Message) -> None:
    """Команда для ручной перезагрузки RAG индексов."""
    try:
        if not await check_admin_access(message.from_user.id):
            await message.answer("❌ У вас нет доступа к этой команде.")
            return
        
        await message.answer("🔄 Начинаю перезагрузку индексов RAG...")
        logger.info(f"[RELOAD] Admin {message.from_user.id} triggered manual index reload")
        
        # Перезагружаем индексы
        await GeminiService.reload_indices()
        
        # Получаем статистику после перезагрузки
        stats_text = f"✅ Индексы успешно перезагружены!\n\n"
        stats_text += f"📊 Загружено отделов: {len(GeminiService._vector_stores)}\n"
        
        for dept_name, store in GeminiService._vector_stores.items():
            if store and store.index:
                chunk_count = store.index.ntotal if hasattr(store.index, 'ntotal') else len(store.chunks)
                stats_text += f"  • {dept_name}: {chunk_count} чанков\n"
        
        await message.answer(stats_text)
        logger.info(f"[RELOAD] Index reload completed successfully for admin {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"[RELOAD] Error reloading indices: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка при перезагрузке индексов:\n{str(e)}")


@router.message(lambda message: message.text in [
    "👥 Админы",
    "👥 Әкімшілер",
    "👥 Admins",
    "👥 管理员"
])
async def handle_admins_button(message: Message, role: str | None = None, lang: str = "ru") -> None:
    """Показывает список администраторов с кнопками управления."""
    try:
        # Проверяем доступ через БД
        async with AsyncSessionLocal() as session:
            user_is_admin = await is_admin(session, message.from_user.id)
            if not user_is_admin:
                await message.answer("У вас нет доступа.")
                return
            
            # Получаем список всех админов
            admins = await get_all_admins(session)
        
        # ID главного админа, которого нельзя удалить
        MAIN_ADMIN_ID = 375693711
        current_user_id = message.from_user.id
        
        if not admins:
            text = "👥 Управление администраторами\n\n"
            text += "Список администраторов пуст."
            buttons: list[list[InlineKeyboardButton]] = []
        else:
            text = "👥 Управление администраторами\n\n"
            text += f"Всего админов: {len(admins)}\n\n"
            text += "Выберите администратора для управления:"
            
            # Создаем кнопки для каждого админа
            buttons: list[list[InlineKeyboardButton]] = []
            
            for admin in admins:
                # Определяем защищен ли админ от удаления
                is_main_admin = admin.user_id == MAIN_ADMIN_ID
                is_self = admin.user_id == current_user_id
                
                # Формируем текст кнопки
                admin_label = f"{admin.username}"
                if is_main_admin:
                    admin_label += " 👑"
                if is_self:
                    admin_label += " (Вы)"
                
                # Если админ не защищен - добавляем кнопку удаления
                if not is_main_admin and not is_self:
                    buttons.append([
                        InlineKeyboardButton(
                            text=f"👤 {admin_label}",
                            callback_data=f"admin_info:{admin.user_id}"
                        ),
                        InlineKeyboardButton(
                            text="❌",
                            callback_data=f"admin_remove:{admin.user_id}"
                        )
                    ])
                else:
                    # Только информационная кнопка (без удаления)
                    buttons.append([
                        InlineKeyboardButton(
                            text=f"👤 {admin_label}",
                            callback_data=f"admin_info:{admin.user_id}"
                        )
                    ])
        
        # Кнопка добавления нового админа
        buttons.append([
            InlineKeyboardButton(
                text="➕ Добавить админа",
                callback_data="admin_add_new"
            )
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await message.answer(text, reply_markup=keyboard)
        logger.info(f"Admin {message.from_user.id} opened admins management")
        
    except Exception as e:
        logger.error(f"Error in admins button handler: {e}", exc_info=True)
        await message.answer("Произошла ошибка при загрузке списка админов.", reply_markup=get_admin_menu(lang))


@router.callback_query(F.data.startswith("admin_info:"))
async def handle_admin_info_callback(callback: CallbackQuery, lang: str = "ru") -> None:
    """Показывает информацию об администраторе."""
    try:
        # Проверяем доступ через БД
        async with AsyncSessionLocal() as session:
            user_is_admin = await is_admin(session, callback.from_user.id)
            if not user_is_admin:
                await callback.answer("У вас нет доступа.", show_alert=True)
                return
            
            # Извлекаем user_id из callback_data
            admin_user_id = int(callback.data.replace("admin_info:", ""))
            
            # Получаем информацию об админе
            stmt = select(Admin).where(Admin.user_id == admin_user_id)
            result = await session.execute(stmt)
            admin = result.scalar_one_or_none()
            
            if not admin:
                await callback.answer("Администратор не найден.", show_alert=True)
                return
            
            # Формируем информацию
            MAIN_ADMIN_ID = 375693711
            is_main_admin = admin.user_id == MAIN_ADMIN_ID
            is_self = admin.user_id == callback.from_user.id
            
            text = f"👤 Информация об администраторе\n\n"
            text += f"ID: {admin.user_id}\n"
            text += f"Имя: {admin.username}\n"
            
            if is_main_admin:
                text += f"\n👑 Главный администратор\n"
                text += f"Этот аккаунт защищен от удаления."
            elif is_self:
                text += f"\n🔒 Это ваш аккаунт\n"
                text += f"Вы не можете удалить сами себя."
            
            # Создаем кнопки
            buttons: list[list[InlineKeyboardButton]] = []
            
            # Кнопка удаления (если админ не защищен)
            if not is_main_admin and not is_self:
                buttons.append([
                    InlineKeyboardButton(
                        text="❌ Удалить администратора",
                        callback_data=f"admin_remove:{admin_user_id}"
                    )
                ])
            
            # Кнопка возврата
            buttons.append([
                InlineKeyboardButton(
                    text="◀️ Назад к списку",
                    callback_data="admin_list"
                )
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            await callback.message.edit_text(text, reply_markup=keyboard)
            await callback.answer()
            
            logger.info(f"Admin {callback.from_user.id} viewed info for admin {admin_user_id}")
            
    except Exception as e:
        logger.error(f"Error in admin_info callback: {e}", exc_info=True)
        await callback.answer("Произошла ошибка.", show_alert=True)


@router.callback_query(F.data.startswith("admin_remove:"))
async def handle_admin_remove_callback(callback: CallbackQuery, lang: str = "ru") -> None:
    """Удаляет администратора после подтверждения."""
    try:
        # Проверяем доступ через БД
        async with AsyncSessionLocal() as session:
            user_is_admin = await is_admin(session, callback.from_user.id)
            if not user_is_admin:
                await callback.answer("У вас нет доступа.", show_alert=True)
                return
            
            # Извлекаем user_id из callback_data
            admin_user_id = int(callback.data.replace("admin_remove:", ""))
            
            # Безопасность: проверяем защиту
            MAIN_ADMIN_ID = 375693711
            current_user_id = callback.from_user.id
            
            if admin_user_id == MAIN_ADMIN_ID:
                await callback.answer("❌ Главного администратора нельзя удалить!", show_alert=True)
                return
            
            if admin_user_id == current_user_id:
                await callback.answer("❌ Вы не можете удалить сами себя!", show_alert=True)
                return
            
            # Получаем информацию об админе перед удалением
            stmt = select(Admin).where(Admin.user_id == admin_user_id)
            result = await session.execute(stmt)
            admin = result.scalar_one_or_none()
            
            if not admin:
                await callback.answer("Администратор не найден.", show_alert=True)
                return
            
            admin_username = admin.username
            
            # Удаляем админа
            success = await remove_admin(session, admin_user_id)
            
            if success:
                # Отправляем уведомление самому пользователю (опционально)
                try:
                    bot = callback.bot
                    notification_text = (
                        "⚠️ Уведомление\n\n"
                        "Ваши права администратора были отозваны.\n"
                        "Теперь у вас роль обычного сотрудника."
                    )
                    await bot.send_message(admin_user_id, notification_text)
                    logger.info(f"Sent notification to user {admin_user_id} about admin rights removal")
                except Exception as notify_error:
                    logger.warning(f"Failed to send notification to {admin_user_id}: {notify_error}")
                
                # Обновляем список админов
                admins = await get_all_admins(session)
                
                text = "✅ Права администратора успешно отозваны!\n\n"
                text += f"👤 Пользователь: {admin_username} (ID: {admin_user_id})\n\n"
                text += f"📊 Осталось администраторов: {len(admins)}"
                
                # Создаем кнопки
                buttons = [
                    [InlineKeyboardButton(
                        text="◀️ Назад к списку",
                        callback_data="admin_list"
                    )]
                ]
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
                
                await callback.message.edit_text(text, reply_markup=keyboard)
                await callback.answer(f"✅ Админ {admin_username} удален", show_alert=False)
                
                logger.info(
                    f"Admin {callback.from_user.id} removed admin rights from user {admin_user_id} ({admin_username})"
                )
            else:
                await callback.answer("❌ Ошибка при удалении администратора.", show_alert=True)
                
    except Exception as e:
        logger.error(f"Error in admin_remove callback: {e}", exc_info=True)
        await callback.answer("Произошла ошибка.", show_alert=True)


@router.callback_query(F.data == "admin_list")
async def handle_admin_list_callback(callback: CallbackQuery, lang: str = "ru") -> None:
    """Возвращает к списку администраторов."""
    try:
        # Проверяем доступ через БД
        async with AsyncSessionLocal() as session:
            user_is_admin = await is_admin(session, callback.from_user.id)
            if not user_is_admin:
                await callback.answer("У вас нет доступа.", show_alert=True)
                return
            
            # Получаем список всех админов
            admins = await get_all_admins(session)
        
        # ID главного админа, которого нельзя удалить
        MAIN_ADMIN_ID = 375693711
        current_user_id = callback.from_user.id
        
        if not admins:
            text = "👥 Управление администраторами\n\n"
            text += "Список администраторов пуст."
            buttons: list[list[InlineKeyboardButton]] = []
        else:
            text = "👥 Управление администраторами\n\n"
            text += f"Всего админов: {len(admins)}\n\n"
            text += "Выберите администратора для управления:"
            
            # Создаем кнопки для каждого админа
            buttons: list[list[InlineKeyboardButton]] = []
            
            for admin in admins:
                # Определяем защищен ли админ от удаления
                is_main_admin = admin.user_id == MAIN_ADMIN_ID
                is_self = admin.user_id == current_user_id
                
                # Формируем текст кнопки
                admin_label = f"{admin.username}"
                if is_main_admin:
                    admin_label += " 👑"
                if is_self:
                    admin_label += " (Вы)"
                
                # Если админ не защищен - добавляем кнопку удаления
                if not is_main_admin and not is_self:
                    buttons.append([
                        InlineKeyboardButton(
                            text=f"👤 {admin_label}",
                            callback_data=f"admin_info:{admin.user_id}"
                        ),
                        InlineKeyboardButton(
                            text="❌",
                            callback_data=f"admin_remove:{admin.user_id}"
                        )
                    ])
                else:
                    # Только информационная кнопка (без удаления)
                    buttons.append([
                        InlineKeyboardButton(
                            text=f"👤 {admin_label}",
                            callback_data=f"admin_info:{admin.user_id}"
                        )
                    ])
        
        # Кнопка добавления нового админа
        buttons.append([
            InlineKeyboardButton(
                text="➕ Добавить админа",
                callback_data="admin_add_new"
            )
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
        
        logger.info(f"Admin {callback.from_user.id} returned to admins list")
        
    except Exception as e:
        logger.error(f"Error in admin_list callback: {e}", exc_info=True)
        await callback.answer("Произошла ошибка.", show_alert=True)


@router.callback_query(F.data == "admin_add_new")
async def handle_add_new_admin_callback(callback: CallbackQuery, state: FSMContext, role: str | None = None) -> None:
    """Начинает процесс добавления нового админа."""
    try:
        # Проверяем доступ через БД
        async with AsyncSessionLocal() as session:
            user_is_admin = await is_admin(session, callback.from_user.id)
            if not user_is_admin:
                await callback.answer("У вас нет доступа.", show_alert=True)
                return
        
        # Переводим в состояние ожидания ID админа
        await state.set_state(AdminState.wait_for_new_admin_id)
        
        await callback.message.edit_text(
            "➕ Добавление нового администратора\n\n"
            "Отправьте одно из следующего:\n"
            "• Пересланное сообщение от пользователя, которого хотите сделать админом\n"
            "• Или введите Telegram ID пользователя (число)\n\n"
            "Для отмены нажмите /cancel"
        )
        await callback.answer("✅ Готов к добавлению админа")
        logger.info(f"Admin {callback.from_user.id} started adding new admin")
        
    except Exception as e:
        logger.error(f"Error in add new admin callback handler: {e}", exc_info=True)
        await callback.answer("Произошла ошибка.", show_alert=True)


@router.message(Command("cancel"), StateFilter(AdminState.wait_for_new_admin_id))
async def handle_cancel_add_admin(message: Message, state: FSMContext, role: str | None = None, lang: str = "ru") -> None:
    """Отмена добавления админа."""
    await state.clear()
    # Проверяем доступ через БД
    user_is_admin = await check_admin_access(message.from_user.id)
    from app.core.i18n import i18n
    await message.answer(
        i18n.get("admin_cancel_admin", lang),
        reply_markup=get_admin_menu(lang) if user_is_admin else await get_main_menu_for_user(message.from_user.id, role, lang)
    )
    logger.info(f"Admin {message.from_user.id} cancelled adding admin")


@router.message(StateFilter(AdminState.wait_for_new_admin_id))
async def handle_new_admin_id(
    message: Message,
    state: FSMContext,
    role: str | None = None,
    lang: str = "ru"
) -> None:
    """Обрабатывает ID нового админа (пересылка сообщения или ввод ID)."""
    try:
        # Проверяем доступ через БД
        async with AsyncSessionLocal() as session:
            user_is_admin = await is_admin(session, message.from_user.id)
            if not user_is_admin:
                await state.clear()
                await message.answer("У вас нет доступа.")
                return
            
            new_admin_id: int | None = None
            new_admin_username: str = "Пользователь"
            
            # Проверяем, переслано ли сообщение
            if message.forward_from:
                new_admin_id = message.forward_from.id
                new_admin_username = (
                    message.forward_from.username or
                    f"{message.forward_from.first_name or ''} {message.forward_from.last_name or ''}".strip() or
                    "Пользователь"
                )
            elif message.text and message.text.strip().isdigit():
                # Пользователь ввел ID вручную
                new_admin_id = int(message.text.strip())
                new_admin_username = f"ID_{new_admin_id}"
            else:
                await message.answer(
                    "⚠️ Пожалуйста, отправьте пересланное сообщение от пользователя "
                    "или введите его Telegram ID (число).\n\n"
                    "Для отмены нажмите /cancel"
                )
                return
            
            if new_admin_id is None:
                await message.answer(
                    "⚠️ Не удалось определить ID пользователя.\n\n"
                    "Попробуйте переслать сообщение от пользователя или ввести его ID вручную.\n\n"
                    "Для отмены нажмите /cancel"
                )
                return
            
            # Проверяем, не является ли пользователь уже админом
            is_already_admin = await is_admin(session, new_admin_id)
            if is_already_admin:
                await message.answer(
                    f"ℹ️ Пользователь с ID {new_admin_id} уже является администратором.",
                    reply_markup=get_admin_menu(lang)
                )
                await state.clear()
                return
            
            # Добавляем нового админа
            try:
                await add_admin(session, new_admin_id, new_admin_username)
                await state.clear()
                
                await message.answer(
                    f"✅ Пользователь {new_admin_username} (ID: {new_admin_id}) теперь имеет доступ к админ-панели.",
                    reply_markup=get_admin_menu(lang)
                )
                logger.info(f"Admin {message.from_user.id} added new admin: {new_admin_id} ({new_admin_username})")
                
            except Exception as e:
                logger.error(f"Error adding admin {new_admin_id}: {e}", exc_info=True)
                await message.answer(
                    f"❌ Ошибка при добавлении админа:\n{str(e)}\n\n"
                    "Попробуйте еще раз или нажмите /cancel для отмены.",
                )
        
    except Exception as e:
        logger.error(f"Error in new admin id handler: {e}", exc_info=True)
        await state.clear()
        # Проверяем доступ через БД
        user_is_admin = await check_admin_access(message.from_user.id)
        from app.core.i18n import i18n
        await message.answer(
            i18n.get("admin_processing_error", lang),
            reply_markup=get_admin_menu(lang) if user_is_admin else await get_main_menu_for_user(message.from_user.id, role, lang)
        )


@router.callback_query(F.data.startswith("support_reply:"))
async def handle_support_reply_callback(
    callback: CallbackQuery,
    state: FSMContext,
    lang: str = "ru",
) -> None:
    """
    Обрабатывает нажатие на кнопку 'Ответить' под жалобой.
    Переводит админа в состояние ожидания текста ответа.
    """
    try:
        if not await check_admin_access(callback.from_user.id):
            await callback.answer("У вас нет доступа.", show_alert=True)
            return

        try:
            _, target_id_str = callback.data.split(":", 1)
            target_user_id = int(target_id_str)
        except Exception:
            await callback.answer("Ошибка формата данных для ответа.", show_alert=True)
            return

        await state.set_state(AdminState.waiting_for_support_reply)
        await state.update_data(support_target_user_id=target_user_id)

        await callback.message.answer(
            f"✉️ Введите ответ для пользователя (ID: {target_user_id}).\n\n"
            "Ваше следующее сообщение будет отправлено ему в личные сообщения."
        )
        await callback.answer()
        logger.info(
            f"Admin {callback.from_user.id} started reply to support complaint from user {target_user_id}"
        )
    except Exception as e:
        logger.error(f"Error in support_reply callback handler: {e}", exc_info=True)
        await callback.answer("Произошла ошибка при подготовке ответа.", show_alert=True)


@router.message(StateFilter(AdminState.waiting_for_support_reply))
async def handle_support_reply_message(
    message: Message,
    state: FSMContext,
    bot: Bot,
    lang: str = "ru",
) -> None:
    """
    Получает текст ответа от админа и отправляет его пользователю.
    """
    try:
        if not await check_admin_access(message.from_user.id):
            await message.answer("У вас нет доступа.")
            await state.clear()
            return

        data = await state.get_data()
        target_user_id = data.get("support_target_user_id")

        if not target_user_id:
            await message.answer(
                "Не удалось определить, кому отправить ответ. Попробуйте снова через кнопку 'Ответить'."
            )
            await state.clear()
            return

        reply_text = (message.text or "").strip()
        if not reply_text:
            await message.answer("Пожалуйста, отправьте текст ответа.")
            return

        # Отправляем ответ пользователю
        try:
            await bot.send_message(
                chat_id=target_user_id,
                text=f"📩 Ответ от администратора:\n\n{reply_text}",
            )
        except Exception as e:
            logger.error(f"Failed to send support reply to user {target_user_id}: {e}", exc_info=True)
            await message.answer("Не удалось отправить ответ пользователю.")
            await state.clear()
            return

        await message.answer("✅ Ответ отправлен пользователю.")
        logger.info(
            f"Admin {message.from_user.id} sent support reply to user {target_user_id}"
        )
        await state.clear()
    except Exception as e:
        logger.error(f"Error in support reply message handler: {e}", exc_info=True)
        await state.clear()
        await message.answer("Произошла ошибка при отправке ответа пользователю.")


# ============================================================================
# CALLBACK HANDLERS ДЛЯ ИЕРАРХИЧЕСКОГО МЕНЮ БАЗЫ ЗНАНИЙ
# ============================================================================

@router.callback_query(F.data.startswith("kb_dept:"))
async def handle_kb_department_callback(callback: CallbackQuery, lang: str = "ru") -> None:
    """Показывает список файлов в выбранном отделе."""
    try:
        # Проверяем доступ
        if not await check_admin_access(callback.from_user.id):
            await callback.answer("У вас нет доступа.", show_alert=True)
            return
        
        from app.core.i18n import i18n
        
        # Извлекаем название отдела из callback_data
        dept_name = callback.data.replace("kb_dept:", "")
        
        logger.info(f"Admin {callback.from_user.id} viewing files in department: {dept_name}")
        
        # Получаем список файлов в отделе
        files = GeminiService.get_department_files(dept_name)
        
        # Маппинг для локализации названий отделов
        dept_names = {
            "common": i18n.get("kb_dept_common", lang),
            "delivery": i18n.get("department_delivery", lang),
            "sorting": i18n.get("department_sorting", lang),
            "manager": i18n.get("department_manager", lang),
            "customer_service": i18n.get("department_customer_service", lang),
        }
        
        dept_display = dept_names.get(dept_name, dept_name.replace("_", " ").title())
        
        if not files:
            # Нет файлов в отделе
            text = i18n.get("kb_no_files_in_dept", lang)
            
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text=i18n.get("back_to_depts", lang),
                        callback_data="kb_view"
                    )]
                ]
            )
            
            await callback.message.edit_text(text, reply_markup=keyboard)
            await callback.answer()
            return
        
        # Формируем текст и клавиатуру
        text = i18n.get("kb_files_in_dept", lang).format(dept=dept_display)
        text += f"\n\n📊 {i18n.get('kb_total', lang)}: {len(files)} {i18n.get('kb_documents', lang)}"
        
        buttons: list[list[InlineKeyboardButton]] = []
        
        for file_info in files:
            filename = file_info['name']
            
            # Регистрируем файл и получаем короткий хеш
            file_hash = register_file_hash(dept_name, filename)
            
            # Обрезаем длинное имя файла для отображения
            display_name = filename if len(filename) <= 30 else filename[:27] + "..."
            
            # Кнопка для каждого файла с коротким хешем
            buttons.append([
                InlineKeyboardButton(
                    text=f"📄 {display_name} ({file_info['size']})",
                    callback_data=f"kb_file:{file_hash}"
                )
            ])
        
        # Кнопка "Назад к отделам"
        buttons.append([
            InlineKeyboardButton(
                text=i18n.get("back_to_depts", lang),
                callback_data="kb_view"
            )
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in kb_department callback handler: {e}", exc_info=True)
        await callback.answer("Произошла ошибка.", show_alert=True)


@router.callback_query(F.data == "kb_view")
async def handle_kb_view_callback(callback: CallbackQuery, lang: str = "ru") -> None:
    """Возвращает к списку отделов."""
    try:
        # Проверяем доступ
        if not await check_admin_access(callback.from_user.id):
            await callback.answer("У вас нет доступа.", show_alert=True)
            return
        
        from app.core.i18n import i18n
        
        # Получаем статистику по отделам
        stats = GeminiService.get_knowledge_stats()
        
        if not stats:
            text = i18n.get("kb_empty", lang)
            await callback.message.edit_text(text)
            await callback.answer()
            return
        
        # Маппинг для локализации названий отделов
        dept_names = {
            "common": i18n.get("kb_dept_common", lang),
            "delivery": i18n.get("department_delivery", lang),
            "sorting": i18n.get("department_sorting", lang),
            "manager": i18n.get("department_manager", lang),
            "customer_service": i18n.get("department_customer_service", lang),
        }
        
        # Создаем inline-клавиатуру с отделами
        buttons: list[list[InlineKeyboardButton]] = []
        
        for dept_key in sorted(stats.keys()):
            count = stats[dept_key]
            dept_display = dept_names.get(dept_key, dept_key.replace("_", " ").title())
            
            buttons.append([
                InlineKeyboardButton(
                    text=f"📂 {dept_display} ({count})",
                    callback_data=f"kb_dept:{dept_key}"
                )
            ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        text = i18n.get("kb_select_department", lang)
        total_files = sum(stats.values())
        text += f"\n\n📊 {i18n.get('kb_total', lang)}: {total_files} {i18n.get('kb_documents', lang)}"
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in kb_view callback handler: {e}", exc_info=True)
        await callback.answer("Произошла ошибка.", show_alert=True)


@router.callback_query(F.data.startswith("kb_file:"))
async def handle_kb_file_callback(callback: CallbackQuery, lang: str = "ru") -> None:
    """Показывает информацию о файле и кнопку удаления."""
    try:
        # Проверяем доступ
        if not await check_admin_access(callback.from_user.id):
            await callback.answer("У вас нет доступа.", show_alert=True)
            return
        
        from app.core.i18n import i18n
        
        # Парсим callback_data: kb_file:{file_hash}
        file_hash = callback.data.replace("kb_file:", "")
        
        # Получаем dept_name и filename по хешу
        file_data = get_file_by_hash(file_hash)
        
        if not file_data:
            await callback.answer("Ошибка: файл не найден в маппинге.", show_alert=True)
            logger.error(f"File hash not found in mapping: {file_hash}")
            return
        
        dept_name, filename = file_data
        
        logger.info(f"Admin {callback.from_user.id} viewing file: {dept_name}/{filename}")
        
        # Получаем информацию о файле
        files = GeminiService.get_department_files(dept_name)
        file_info = None
        for f in files:
            if f["name"] == filename:
                file_info = f
                break
        
        if not file_info:
            await callback.answer("Файл не найден.", show_alert=True)
            return
        
        # Маппинг для локализации названий отделов
        dept_names = {
            "common": i18n.get("kb_dept_common", lang),
            "delivery": i18n.get("department_delivery", lang),
            "sorting": i18n.get("department_sorting", lang),
            "manager": i18n.get("department_manager", lang),
            "customer_service": i18n.get("department_customer_service", lang),
        }
        
        dept_display = dept_names.get(dept_name, dept_name.replace("_", " ").title())
        
        # Формируем текст с информацией о файле
        text = i18n.get("kb_file_info", lang).format(
            filename=filename,
            size=file_info["size"],
            dept=dept_display
        )
        
        # Создаем клавиатуру с кнопками (используем file_hash)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="📥 Скачать",
                    callback_data=f"kb_download:{file_hash}"
                )],
                [InlineKeyboardButton(
                    text=i18n.get("kb_delete_button", lang),
                    callback_data=f"kb_del:{file_hash}"
                )],
                [InlineKeyboardButton(
                    text=i18n.get("back_to_files", lang),
                    callback_data=f"kb_dept:{dept_name}"
                )],
                [InlineKeyboardButton(
                    text=i18n.get("back_to_depts", lang),
                    callback_data="kb_view"
                )]
            ]
        )
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in kb_file callback handler: {e}", exc_info=True)
        await callback.answer("Произошла ошибка.", show_alert=True)


@router.callback_query(F.data.startswith("kb_download:"))
async def handle_kb_download_callback(callback: CallbackQuery, lang: str = "ru") -> None:
    """Отправляет файл из базы знаний администратору."""
    try:
        # Проверяем доступ (только админы)
        if not await check_admin_access(callback.from_user.id):
            await callback.answer("❌ У вас нет доступа к скачиванию файлов.", show_alert=True)
            return
        
        from app.core.i18n import i18n
        
        # Парсим callback_data: kb_download:{file_hash}
        file_hash = callback.data.replace("kb_download:", "")
        
        # Получаем dept_name и filename по хешу
        file_data = get_file_by_hash(file_hash)
        
        if not file_data:
            await callback.answer("Ошибка: файл не найден в маппинге.", show_alert=True)
            logger.error(f"File hash not found for download: {file_hash}")
            return
        
        dept_name, filename = file_data
        
        logger.info(f"Admin {callback.from_user.id} downloading file: {dept_name}/{filename}")
        
        # Формируем путь к файлу
        knowledge_path = Path("data/knowledge")
        file_path = knowledge_path / dept_name / filename
        
        # Проверяем существование файла
        if not file_path.exists() or not file_path.is_file():
            logger.error(f"File not found on disk: {file_path}")
            await callback.answer("❌ Ошибка: файл не найден на сервере.", show_alert=True)
            return
        
        # Проверяем что файл действительно в knowledge директории (защита от path traversal)
        try:
            file_path_resolved = file_path.resolve()
            knowledge_path_resolved = knowledge_path.resolve()
            if not str(file_path_resolved).startswith(str(knowledge_path_resolved)):
                logger.error(f"Security: Path traversal attempt blocked: {file_path}")
                await callback.answer("❌ Ошибка: недопустимый путь к файлу.", show_alert=True)
                return
        except Exception as path_error:
            logger.error(f"Error resolving path: {path_error}", exc_info=True)
            await callback.answer("❌ Ошибка при проверке пути к файлу.", show_alert=True)
            return
        
        # Отправляем статус
        await callback.answer("⏳ Подготавливаю файл...")
        
        try:
            # Создаем FSInputFile для отправки
            document = FSInputFile(file_path)
            
            # Отправляем файл пользователю
            await callback.message.answer_document(
                document=document,
                caption=f"📄 Файл из базы знаний\n\n"
                        f"📂 Отдел: {dept_name}\n"
                        f"📝 Имя файла: {filename}"
            )
            
            logger.info(f"Admin {callback.from_user.id} successfully downloaded file: {dept_name}/{filename}")
            
            # Подтверждение
            await callback.answer("✅ Файл отправлен", show_alert=False)
            
        except Exception as send_error:
            logger.error(f"Error sending file {file_path}: {send_error}", exc_info=True)
            await callback.answer(f"❌ Ошибка при отправке файла: {str(send_error)}", show_alert=True)
        
    except Exception as e:
        logger.error(f"Error in kb_download callback handler: {e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка при скачивании.", show_alert=True)


@router.callback_query(F.data.startswith("kb_del:"))
async def handle_kb_delete_callback(callback: CallbackQuery, lang: str = "ru") -> None:
    """Удаляет файл из базы знаний и обновляет индекс."""
    try:
        # Проверяем доступ
        if not await check_admin_access(callback.from_user.id):
            await callback.answer("У вас нет доступа.", show_alert=True)
            return
        
        from app.core.i18n import i18n
        
        # Парсим callback_data: kb_del:{file_hash}
        file_hash = callback.data.replace("kb_del:", "")
        
        # Получаем dept_name и filename по хешу
        file_data = get_file_by_hash(file_hash)
        
        if not file_data:
            await callback.answer("Ошибка: файл не найден в маппинге.", show_alert=True)
            logger.error(f"File hash not found for deletion: {file_hash}")
            return
        
        dept_name, filename = file_data
        
        logger.info(f"Admin {callback.from_user.id} deleting file: {dept_name}/{filename}")
        
        # Показываем статус удаления
        await callback.message.edit_text(i18n.get("kb_deleting", lang))
        
        try:
            # Удаляем файл и обновляем индекс
            success = GeminiService.delete_document(dept_name, filename)
            
            if success:
                # Удаляем запись из маппинга
                if file_hash in _file_hash_map:
                    del _file_hash_map[file_hash]
                    logger.debug(f"Removed file hash from mapping: {file_hash}")
                
                # Файл успешно удален
                text = i18n.get("file_deleted", lang)
                
                # Возвращаемся к списку файлов отдела
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(
                            text=i18n.get("back_to_files", lang),
                            callback_data=f"kb_dept:{dept_name}"
                        )],
                        [InlineKeyboardButton(
                            text=i18n.get("back_to_depts", lang),
                            callback_data="kb_view"
                        )]
                    ]
                )
                
                await callback.message.edit_text(text, reply_markup=keyboard)
                await callback.answer(f"✅ {filename} удален", show_alert=False)
                
                logger.info(f"Admin {callback.from_user.id} deleted file successfully: {dept_name}/{filename}")
            else:
                await callback.answer("Не удалось удалить файл.", show_alert=True)
                
        except FileNotFoundError as e:
            logger.error(f"File not found: {e}")
            await callback.answer(f"Файл не найден: {filename}", show_alert=True)
            # Возвращаемся к списку файлов
            await callback.message.edit_text(
                "❌ Файл не найден.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(
                            text=i18n.get("back_to_files", lang),
                            callback_data=f"kb_dept:{dept_name}"
                        )]
                    ]
                )
            )
        except Exception as delete_error:
            logger.error(f"Error deleting file: {delete_error}", exc_info=True)
            await callback.answer(f"Ошибка при удалении: {str(delete_error)}", show_alert=True)
            # Возвращаемся к списку файлов
            await callback.message.edit_text(
                f"❌ Ошибка при удалении файла:\n{str(delete_error)}",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(
                            text=i18n.get("back_to_files", lang),
                            callback_data=f"kb_dept:{dept_name}"
                        )]
                    ]
                )
            )
        
    except Exception as e:
        logger.error(f"Error in kb_delete callback handler: {e}", exc_info=True)
        await callback.answer("Произошла ошибка.", show_alert=True)


# ===================================================================================
# Управление сотрудниками (Employee Management)
# ===================================================================================

@router.message(lambda message: message.text in [
    "👥 Сотрудники",
    "👥 Қызметкерлер",
    "👥 Employees",
    "👥 员工"
])
async def handle_manage_employees(message: Message, lang: str = "ru") -> None:
    """Показывает список всех зарегистрированных сотрудников."""
    try:
        if not await check_admin_access(message.from_user.id):
            await message.answer(
                i18n.get("admin_no_access", lang),
                reply_markup=get_main_menu(role=None, is_admin=False, lang=lang)
            )
            return
        
        from app.core.i18n import i18n
        
        async with AsyncSessionLocal() as session:
            employees = await get_all_employees(session)
            
            if not employees:
                await message.answer(
                    i18n.get("employees_list_empty", lang),
                    reply_markup=get_admin_menu(lang)
                )
                return
            
            # Создаем inline-кнопки для каждого сотрудника
            buttons: list[list[InlineKeyboardButton]] = []
            
            for user in employees:
                # Используем хеш для callback_data (избегаем BUTTON_DATA_INVALID)
                user_hash = hash_user_id(user.telegram_id)
                
                # Формируем текст кнопки
                dept_names = Department.get_display_names()
                dept_display = dept_names.get(user.department, user.department or "Не назначен")
                button_text = f"{user.full_name or 'Без имени'} ({dept_display[:15]})"
                
                buttons.append([
                    InlineKeyboardButton(
                        text=button_text,
                        callback_data=f"emp_view:{user.telegram_id}"
                    )
                ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            text = f"{i18n.get('employees_list_header', lang)}\n\n"
            text += f"Всего зарегистрировано: {len(employees)}"
            
            await message.answer(text, reply_markup=keyboard)
            
            logger.info(f"Admin {message.from_user.id} viewed employee list ({len(employees)} users)")
            
    except Exception as e:
        logger.error(f"Error in manage_employees handler: {e}", exc_info=True)
        await message.answer(
            i18n.get("admin_error", lang),
            reply_markup=get_admin_menu(lang)
        )


@router.callback_query(F.data.startswith("emp_view:"))
async def handle_employee_view_callback(callback: CallbackQuery, lang: str = "ru") -> None:
    """Показывает детальную информацию о сотруднике."""
    try:
        if not await check_admin_access(callback.from_user.id):
            await callback.answer(i18n.get("admin_no_access_short", lang), show_alert=True)
            return
        
        from app.core.i18n import i18n
        
        # Извлекаем telegram_id из callback_data
        telegram_id = int(callback.data.replace("emp_view:", ""))
        
        async with AsyncSessionLocal() as session:
            user = await get_employee_by_telegram_id(session, telegram_id)
            
            if not user:
                await callback.answer("Пользователь не найден.", show_alert=True)
                return
            
            # Форматируем информацию о пользователе
            user_info_text = format_user_info(user, lang)
            
            # Создаем кнопки управления
            buttons = [
                [InlineKeyboardButton(
                    text=i18n.get("employee_change_department", lang),
                    callback_data=f"emp_assign:{telegram_id}"
                )],
                [InlineKeyboardButton(
                    text=i18n.get("employee_back_to_list", lang),
                    callback_data="emp_list"
                )]
            ]
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            await callback.message.edit_text(user_info_text, reply_markup=keyboard)
            await callback.answer()
            
            logger.info(f"Admin {callback.from_user.id} viewed employee {telegram_id} details")
            
    except Exception as e:
        logger.error(f"Error in employee_view callback: {e}", exc_info=True)
        await callback.answer("Произошла ошибка.", show_alert=True)


@router.callback_query(F.data == "emp_list")
async def handle_employee_list_callback(callback: CallbackQuery, lang: str = "ru") -> None:
    """Возвращает к списку сотрудников."""
    try:
        if not await check_admin_access(callback.from_user.id):
            await callback.answer(i18n.get("admin_no_access_short", lang), show_alert=True)
            return
        
        from app.core.i18n import i18n
        
        async with AsyncSessionLocal() as session:
            employees = await get_all_employees(session)
            
            if not employees:
                await callback.message.edit_text(i18n.get("employees_list_empty", lang))
                await callback.answer()
                return
            
            # Создаем inline-кнопки для каждого сотрудника
            buttons: list[list[InlineKeyboardButton]] = []
            
            for user in employees:
                dept_names = Department.get_display_names()
                dept_display = dept_names.get(user.department, user.department or "Не назначен")
                button_text = f"{user.full_name or 'Без имени'} ({dept_display[:15]})"
                
                buttons.append([
                    InlineKeyboardButton(
                        text=button_text,
                        callback_data=f"emp_view:{user.telegram_id}"
                    )
                ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            text = f"{i18n.get('employees_list_header', lang)}\n\n"
            text += f"Всего зарегистрировано: {len(employees)}"
            
            await callback.message.edit_text(text, reply_markup=keyboard)
            await callback.answer()
            
    except Exception as e:
        logger.error(f"Error in employee_list callback: {e}", exc_info=True)
        await callback.answer("Произошла ошибка.", show_alert=True)


@router.callback_query(F.data.startswith("emp_assign:"))
async def handle_employee_assign_callback(callback: CallbackQuery, lang: str = "ru") -> None:
    """Показывает список отделов для назначения."""
    try:
        if not await check_admin_access(callback.from_user.id):
            await callback.answer(i18n.get("admin_no_access_short", lang), show_alert=True)
            return
        
        from app.core.i18n import i18n
        
        # Извлекаем telegram_id из callback_data
        telegram_id = int(callback.data.replace("emp_assign:", ""))
        
        async with AsyncSessionLocal() as session:
            user = await get_employee_by_telegram_id(session, telegram_id)
            
            if not user:
                await callback.answer("Пользователь не найден.", show_alert=True)
                return
            
            # Получаем список отделов (без COMMON - его нельзя назначить вручную)
            assignable_depts = Department.get_admin_assignable_departments()
            
            # Создаем кнопки для каждого отдела
            buttons: list[list[InlineKeyboardButton]] = []
            
            for dept_code, dept_name in assignable_depts.items():
                buttons.append([
                    InlineKeyboardButton(
                        text=dept_name,
                        callback_data=f"emp_set:{telegram_id}:{dept_code}"
                    )
                ])
            
            # Кнопка "Назад"
            buttons.append([
                InlineKeyboardButton(
                    text=i18n.get("button_back", lang),
                    callback_data=f"emp_view:{telegram_id}"
                )
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            
            text = i18n.get("employee_select_department", lang, name=user.full_name or "пользователю")
            
            await callback.message.edit_text(text, reply_markup=keyboard)
            await callback.answer()
            
            logger.info(f"Admin {callback.from_user.id} selecting department for employee {telegram_id}")
            
    except Exception as e:
        logger.error(f"Error in employee_assign callback: {e}", exc_info=True)
        await callback.answer("Произошла ошибка.", show_alert=True)


@router.callback_query(F.data.startswith("emp_set:"))
async def handle_employee_set_department_callback(callback: CallbackQuery, lang: str = "ru") -> None:
    """Назначает отдел сотруднику и отправляет уведомление."""
    try:
        if not await check_admin_access(callback.from_user.id):
            await callback.answer(i18n.get("admin_no_access_short", lang), show_alert=True)
            return
        
        from app.core.i18n import i18n
        
        # Парсим callback_data: emp_set:{telegram_id}:{department}
        parts = callback.data.split(":")
        telegram_id = int(parts[1])
        department_code = parts[2]
        
        # Статус обновления
        await callback.message.edit_text("⏳ Назначаем отдел...")
        
        async with AsyncSessionLocal() as session:
            # Получаем пользователя для уведомления
            user = await get_employee_by_telegram_id(session, telegram_id)
            
            if not user:
                await callback.answer("Пользователь не найден.", show_alert=True)
                return
            
            user_lang = user.language or "ru"
            
            # Назначаем отдел
            success = await assign_department_to_employee(session, telegram_id, department_code)
            
            if success:
                # Получаем название отдела
                dept_names = Department.get_display_names()
                department_name = dept_names.get(department_code, department_code)
                
                # Отправляем уведомление пользователю
                try:
                    bot = callback.bot
                    notification_text = (
                        f"{i18n.get('employee_notification_title', user_lang)}\n\n"
                        f"{i18n.get('employee_notification_assigned', user_lang, department=department_name)}"
                    )
                    await bot.send_message(telegram_id, notification_text)
                    logger.info(f"Notification sent to user {telegram_id} about department assignment")
                except Exception as notify_error:
                    logger.warning(f"Failed to send notification to {telegram_id}: {notify_error}")
                
                # Показываем информацию о пользователе с обновленным отделом
                await session.refresh(user)  # Обновляем данные
                user_info_text = format_user_info(user, lang)
                user_info_text += f"\n\n{i18n.get('employee_department_assigned', lang)}"
                
                buttons = [
                    [InlineKeyboardButton(
                        text=i18n.get("employee_change_department", lang),
                        callback_data=f"emp_assign:{telegram_id}"
                    )],
                    [InlineKeyboardButton(
                        text=i18n.get("employee_back_to_list", lang),
                        callback_data="emp_list"
                    )]
                ]
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
                
                await callback.message.edit_text(user_info_text, reply_markup=keyboard)
                await callback.answer(f"✅ Отдел '{department_name}' назначен", show_alert=False)
                
                logger.info(
                    f"Admin {callback.from_user.id} assigned department '{department_code}' "
                    f"to employee {telegram_id}"
                )
            else:
                await callback.message.edit_text(i18n.get("employee_department_error", lang))
                await callback.answer("Ошибка при назначении отдела.", show_alert=True)
                
    except Exception as e:
        logger.error(f"Error in employee_set_department callback: {e}", exc_info=True)
        await callback.answer("Произошла ошибка.", show_alert=True)
