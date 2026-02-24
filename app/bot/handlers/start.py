"""Хендлеры для команды /start."""
from sqlalchemy import select

from aiogram import Bot, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from app.bot.keyboards.main_menu import get_main_menu
from app.bot.keyboards.department import get_department_selection_keyboard, get_delivery_submenu_keyboard
from app.bot.keyboards.language import get_language_selection_keyboard
from app.core.config import settings
from app.core.i18n import I18nManager
from app.core.database import AsyncSessionLocal
from app.core.models import Department, User
from app.services.ai_service import GeminiService
from app.services.admin_service import is_admin
from app.bot.handlers.media import format_response_with_media
from app.utils.logger import logger
from app.utils.states import QuestionState, RegistrationState
from app.utils.department import set_user_department, get_department_display_name
from aiogram.types import CallbackQuery

router = Router(name="start")


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, role: str | None = None, i18n: I18nManager | None = None, lang: str = "ru") -> None:
    """Обработчик команды /start."""
    try:
        telegram_id = message.from_user.id
        full_name = (
            f"{message.from_user.first_name or ''} "
            f"{message.from_user.last_name or ''}"
        ).strip() or message.from_user.username or "Пользователь"

        logger.info(f"User {telegram_id} sent /start command")

        async with AsyncSessionLocal() as session:
            # Проверяем, является ли пользователь админом через таблицу admins
            user_is_admin = await is_admin(session, telegram_id)
            
            # Проверяем, существует ли пользователь
            stmt = select(User).where(User.telegram_id == telegram_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if user is None:
                # Новый пользователь
                logger.info(f"[START] New user {telegram_id} - checking admin status")
                
                # Если это админ - создаем сразу с верификацией
                if user_is_admin:
                    logger.info(f"[START] User {telegram_id} is admin - auto-verifying")
                    
                    # Создаем админа с автоматической верификацией
                    user = User(
                        telegram_id=telegram_id,
                        full_name=full_name,
                        role="admin",
                        department=None,  # Админ без отдела (God Mode)
                        language=None,  # Будет выбран в следующем шаге
                        is_verified=True,  # Админы верифицируются автоматически
                    )
                    session.add(user)
                    await session.commit()
                    await session.refresh(user)
                    
                    logger.info(f"[START] ✅ Admin {telegram_id} created with is_verified=True")
                    
                    # Переводим в состояние выбора языка
                    await state.set_state(RegistrationState.waiting_for_language)
                    await state.update_data(
                        telegram_id=telegram_id,
                        full_name=full_name,
                        is_admin=user_is_admin
                    )
                    
                    # Отправляем выбор языка
                    await message.answer(
                        "✅ Добро пожаловать, администратор!\n\n"
                        "Выберите язык / Тілді таңдаңыз / Choose language / 选择语言",
                        reply_markup=get_language_selection_keyboard()
                    )
                    logger.info(f"[START] Language selection shown to admin {telegram_id}")
                    return
                
                # Обычный пользователь - запрашиваем инвайт-код
                logger.info(f"[START] New user {telegram_id} - requesting invite code")
                
                # Переводим в состояние ожидания инвайт-кода
                await state.set_state(RegistrationState.waiting_for_invite_code)
                await state.update_data(
                    telegram_id=telegram_id,
                    full_name=full_name,
                    is_admin=user_is_admin
                )
                
                # Запрашиваем инвайт-код на всех языках
                invite_message = (
                    "🔐 Добро пожаловать в UQsoft!\n\n"
                    "Для доступа к системе введите ваш персональный инвайт-код.\n\n"
                    "───────────────────\n\n"
                    "🔐 UQsoft-ке қош келдіңіз!\n\n"
                    "Жүйеге қол жеткізу үшін жеке шақыру кодын енгізіңіз.\n\n"
                    "───────────────────\n\n"
                    "🔐 Welcome to UQsoft!\n\n"
                    "To access the system, enter your personal invite code.\n\n"
                    "───────────────────\n\n"
                    "🔐 欢迎来到UQsoft！\n\n"
                    "要访问系统，请输入您的个人邀请码。"
                )
                
                await message.answer(invite_message)
                logger.info(f"[START] Invite code requested from user {telegram_id}")
                return
            else:
                # Существующий пользователь - проверяем верификацию
                logger.info(f"Existing user: {telegram_id} ({full_name}), is_verified={user.is_verified}, is_admin={user_is_admin}")
                
                # Если это админ но не верифицирован - верифицируем автоматически
                if user_is_admin and not user.is_verified:
                    logger.info(f"[START] Admin {telegram_id} not verified - auto-verifying")
                    user.is_verified = True
                    await session.commit()
                    logger.info(f"[START] ✅ Admin {telegram_id} auto-verified")
                
                # Если пользователь не верифицирован и не админ - запрашиваем инвайт-код
                if not user.is_verified and not user_is_admin:
                    logger.info(f"[START] User {telegram_id} not verified - requesting invite code")
                    
                    # Переводим в состояние ожидания инвайт-кода
                    await state.set_state(RegistrationState.waiting_for_invite_code)
                    await state.update_data(
                        telegram_id=telegram_id,
                        full_name=full_name,
                        is_admin=user_is_admin
                    )
                    
                    # Запрашиваем инвайт-код
                    user_lang = user.language or "ru"
                    from app.core.i18n import i18n
                    
                    invite_message = (
                        "🔐 Добро пожаловать обратно!\n\n"
                        "Для доступа к системе введите ваш персональный инвайт-код.\n\n"
                        "Если у вас нет кода, обратитесь к администратору."
                    )
                    
                    await message.answer(invite_message)
                    logger.info(f"[START] Invite code re-requested from user {telegram_id}")
                    return
                
                # Обновляем имя, если изменилось
                if user.full_name != full_name:
                    user.full_name = full_name
                    await session.commit()

            # Устанавливаем role: если пользователь админ в таблице admins, то role = "admin"
            # независимо от роли в таблице users
            if user_is_admin:
                role = "admin"
                logger.info(f"User {telegram_id} is admin in admins table, setting role to admin")
            else:
                role = user.role

            # Получаем язык пользователя для локализации
            user_lang = user.language or "ru"
            
            # Отправляем приветствие с кнопками на языке пользователя
            role_display = i18n.get(f"role_{role}", user_lang)
            welcome_text = f"{i18n.get('welcome_text', user_lang)} {i18n.get('your_role', user_lang, role=role_display)}"
            
            await message.answer(
                welcome_text,
                reply_markup=get_main_menu(role=role, is_admin=user_is_admin, lang=user_lang),
            )
            logger.info(f"Sent welcome message to user {telegram_id} with role {role} and lang {user_lang}")

    except Exception as e:
        logger.error(f"Error in /start handler: {e}", exc_info=True)
        await message.answer(
            i18n.get("error_generic", lang) if i18n else "Произошла ошибка при обработке запроса. Попробуйте позже.",
            reply_markup=get_main_menu(role=role, lang=lang) if role else None,
        )
        logger.info(f"Sent error message to user {message.from_user.id}")


@router.message(lambda message: message.text in [
    "🔍 Спроси базу",
    "🔍 Базадан сұра",
    "🔍 Ask the base",
    "🔍 询问知识库"
])
async def handle_ask_base_button(
    message: Message,
    state: FSMContext,
    role: str | None = None,
    lang: str = "ru",
    i18n: I18nManager | None = None
) -> None:
    """Обработчик кнопки '🔍 Спроси базу' - переводит в состояние ожидания вопроса."""
    try:
        # Обрабатываем только зарегистрированных пользователей
        if role is None:
            await message.answer(
                i18n.get("error_user_not_registered", lang) if i18n else "Для использования этой функции необходимо зарегистрироваться."
            )
            return
        
        # Переводим пользователя в состояние ожидания вопроса
        await state.set_state(QuestionState.waiting_for_question)
        
        # Создаем клавиатуру с кнопкой "Назад"
        question_mode_keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=i18n.get("main_menu_back", lang))],
            ],
            resize_keyboard=True,
        )
        
        await message.answer(
            i18n.get("ask_question_prompt", lang),
            reply_markup=question_mode_keyboard
        )
        logger.info(f"User {message.from_user.id} entered question mode")
        
    except Exception as e:
        logger.error(f"Error in ask base button handler: {e}", exc_info=True)
        await message.answer(i18n.get("error_generic", lang) if i18n else "Произошла ошибка. Попробуйте позже.")


@router.message(
    StateFilter(QuestionState.waiting_for_question),
    lambda message: message.text and not message.text.startswith("/")
)
async def handle_question_in_fsm(
    message: Message,
    bot: Bot,
    state: FSMContext,
    role: str | None = None,
    lang: str = "ru",
    i18n: I18nManager | None = None
) -> None:
    """Обработчик вопроса пользователя в FSM состоянии ожидания вопроса."""
    try:
        # Обрабатываем только зарегистрированных пользователей
        if role is None:
            await state.clear()
            await message.answer(i18n.get("error_user_not_registered", lang) if i18n else "Ошибка: пользователь не зарегистрирован.")
            return
        
        telegram_id = message.from_user.id
        question = message.text.strip()
        
        logger.info(f"User {telegram_id} asked question: {question[:100]}...")
        
        # Показываем статус "Печатает..."
        await bot.send_chat_action(chat_id=telegram_id, action="typing")
        
        # Получаем ответ от Gemini с историей диалога
        try:
            async with AsyncSessionLocal() as session:
                answer = await GeminiService.get_answer(
                    prompt=question,
                    user_id=telegram_id,
                    session=session,
                )
            
            # Извлекаем медиа-ссылки из ответа
            media_links = GeminiService.extract_media_links(answer)
            
            # Форматируем ответ с медиа-кнопками
            formatted_response, media_keyboard = format_response_with_media(answer, media_links)
            
            # Создаем клавиатуру с кнопкой "Назад" для выхода из режима вопросов
            question_mode_keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text=i18n.get("main_menu_back", lang))],
                ],
                resize_keyboard=True,
            )
            
            # Отправляем ответ пользователю
            await message.answer(
                formatted_response,
                reply_markup=question_mode_keyboard if media_keyboard is None else None
            )
            
            # Если есть медиа-кнопки, отправляем их отдельным сообщением
            if media_keyboard:
                await message.answer(
                    i18n.get("media_links_title", lang),
                    reply_markup=media_keyboard
                )
                await message.answer(
                    i18n.get("ask_next_question", lang),
                    reply_markup=question_mode_keyboard
                )
            else:
                # Если медиа-кнопок нет, отправляем сообщение о следующем вопросе
                await message.answer(
                    i18n.get("ask_next_question", lang),
                    reply_markup=question_mode_keyboard
                )
            
            # Сохраняем состояние для возможности задать следующий вопрос
            await state.set_state(QuestionState.waiting_for_question)
            
            logger.info(f"Sent Gemini response to user {telegram_id}")
            
        except Exception as e:
            logger.error(f"Error getting answer from Gemini: {e}", exc_info=True)
            # При ошибке сохраняем состояние, чтобы пользователь мог попробовать еще раз
            await state.set_state(QuestionState.waiting_for_question)
            question_mode_keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text=i18n.get("main_menu_back", lang))],
                ],
                resize_keyboard=True,
            )
            await message.answer(
                i18n.get("error_ai_service", lang),
                reply_markup=question_mode_keyboard
            )
            
    except Exception as e:
        logger.error(f"Error in question handler: {e}", exc_info=True)
        # При критической ошибке сбрасываем состояние
        await state.clear()
        async with AsyncSessionLocal() as session:
            user_is_admin = await is_admin(session, message.from_user.id)
        await message.answer(
            i18n.get("error_generic", lang) if i18n else "Произошла ошибка при обработке вашего вопроса.",
            reply_markup=get_main_menu(role=role, is_admin=user_is_admin, lang=lang)
        )


@router.message(
    StateFilter(QuestionState.waiting_for_question),
    lambda message: message.text in [
        "◀️ Назад в меню",
        "◀️ Мәзірге оралу",
        "◀️ Back to menu",
        "◀️ 返回菜单"
    ]
)
async def handle_back_from_questions(
    message: Message,
    state: FSMContext,
    role: str | None = None,
    lang: str = "ru",
    i18n: I18nManager | None = None
) -> None:
    """Выход из режима вопросов и возврат в главное меню."""
    try:
        await state.clear()
        # Проверяем, является ли пользователь админом через БД
        async with AsyncSessionLocal() as session:
            user_is_admin = await is_admin(session, message.from_user.id)
        
        await message.answer(
            i18n.get("back_to_menu", lang),
            reply_markup=get_main_menu(role=role, is_admin=user_is_admin, lang=lang)
        )
        logger.info(f"User {message.from_user.id} exited question mode")
    except Exception as e:
        logger.error(f"Error in back from questions handler: {e}", exc_info=True)
        await state.clear()
        await message.answer(
            i18n.get("error_generic", lang) if i18n else "Произошла ошибка.",
            reply_markup=get_main_menu(role=role, lang=lang)
        )


@router.message(StateFilter(RegistrationState.waiting_for_invite_code))
async def handle_invite_code_input(message: Message, state: FSMContext) -> None:
    """Обработчик ввода инвайт-кода при первичной регистрации."""
    try:
        # Получаем данные из FSM
        data = await state.get_data()
        telegram_id = data.get("telegram_id")
        full_name = data.get("full_name")
        is_admin = data.get("is_admin", False)
        
        invite_code = message.text.strip()
        
        logger.info(f"[INVITE] User {telegram_id} entered invite code: {invite_code}")
        
        # Проверяем инвайт-код
        if invite_code != settings.invite_code:
            # Неверный код
            error_message = (
                "❌ Код не найден.\n\n"
                "Проверьте правильность кода или обратитесь к администратору.\n\n"
                "───────────────────\n\n"
                "❌ Код табылмады.\n\n"
                "Кодтың дұрыстығын тексеріңіз немесе әкімшіге жүгініңіз.\n\n"
                "───────────────────\n\n"
                "❌ Code not found.\n\n"
                "Check the code or contact the administrator.\n\n"
                "───────────────────\n\n"
                "❌ 未找到代码。\n\n"
                "请检查代码或联系管理员。"
            )
            await message.answer(error_message)
            logger.info(f"[INVITE] ❌ Wrong invite code for user {telegram_id}: '{invite_code}' (expected: '{settings.invite_code}')")
            return
        
        # Верный код - создаем пользователя в БД
        logger.info(f"[INVITE] ✅ Correct invite code for user {telegram_id}")
        
        async with AsyncSessionLocal() as session:
            # Проверяем существует ли уже пользователь
            stmt = select(User).where(User.telegram_id == telegram_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if user is None:
                # Создаем нового пользователя
                user = User(
                    telegram_id=telegram_id,
                    full_name=full_name,
                    role="admin" if is_admin else "employee",
                    department=None if is_admin else "common",
                    language=None,  # Будет выбран в следующем шаге
                    is_verified=True,  # Верифицирован!
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                logger.info(f"[INVITE] ✅ User {telegram_id} created with is_verified=True")
            else:
                # Пользователь существует - обновляем верификацию
                user.is_verified = True
                await session.commit()
                logger.info(f"[INVITE] ✅ User {telegram_id} verified (is_verified=True)")
        
        # Переводим в состояние выбора языка
        await state.set_state(RegistrationState.waiting_for_language)
        await state.update_data(
            telegram_id=telegram_id,
            full_name=full_name,
            is_admin=is_admin
        )
        
        # Отправляем выбор языка
        success_message = (
            "✅ Код принят!\n\n"
            "Выберите язык / Тілді таңдаңыз / Choose language / 选择语言"
        )
        await message.answer(
            success_message,
            reply_markup=get_language_selection_keyboard()
        )
        logger.info(f"[INVITE] Language selection shown to verified user {telegram_id}")
        
    except Exception as e:
        logger.error(f"[INVITE] Error processing invite code: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при обработке кода. Попробуйте еще раз или обратитесь к администратору.\n\n"
            "❌ An error occurred. Please try again or contact the administrator."
        )


@router.callback_query(lambda c: c.data and c.data.startswith("lang_"), StateFilter(RegistrationState.waiting_for_language))
async def handle_language_selection(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработчик выбора языка при регистрации (пользователь УЖЕ создан в БД при /start)."""
    try:
        # Получаем выбранный язык из callback_data (формат: lang_ru, lang_kk и т.д.)
        selected_lang = callback.data.replace("lang_", "")
        
        if selected_lang not in ["ru", "kk", "en", "zh"]:
            await callback.answer("Ошибка: неверный язык / Error: invalid language")
            return
        
        # Получаем данные из FSM
        data = await state.get_data()
        telegram_id = data.get("telegram_id")
        is_admin = data.get("is_admin", False)
        
        logger.info(f"[LANGUAGE] User {telegram_id} selected language: {selected_lang}, is_admin={is_admin}")
        
        # Инициализируем i18n для использования
        from app.core.i18n import i18n
        
        async with AsyncSessionLocal() as session:
            # КРИТИЧНО: Пользователь УЖЕ существует в БД (создан при /start)
            # Просто ОБНОВЛЯЕМ язык
            stmt = select(User).where(User.telegram_id == telegram_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                logger.error(f"[LANGUAGE] ❌ CRITICAL: User {telegram_id} NOT found in DB after /start!")
                await callback.answer("Ошибка: пользователь не найден. Попробуйте /start снова.", show_alert=True)
                return
            
            logger.info(f"[LANGUAGE] User {telegram_id} found in DB: id={user.id}, current_lang={user.language}, role={user.role}")
            
            # Обновляем язык
            old_lang = user.language
            user.language = selected_lang
            await session.commit()
            
            logger.info(f"[LANGUAGE] COMMIT executed for user {telegram_id}")
            
            # КРИТИЧНО: Проверяем что сохранилось
            await session.refresh(user)
            logger.info(f"[LANGUAGE] ✅ User {telegram_id} language VERIFIED in DB: {user.language} (was: {old_lang}, set to: {selected_lang})")
            
            if user.language != selected_lang:
                logger.error(f"[LANGUAGE] ❌ CRITICAL: Language NOT saved! DB={user.language}, expected={selected_lang}")
                logger.error(f"[LANGUAGE] Database path: {settings.database_path}")
            else:
                logger.info(f"[LANGUAGE] ✅ SUCCESS: Language persisted correctly in DB")
            
            if is_admin:
                # Админ - завершаем регистрацию
                role_display = i18n.get("role_admin", selected_lang)
                welcome_text = f"{i18n.get('welcome_text', selected_lang)} {i18n.get('your_role', selected_lang, role=role_display)}"
                
                await callback.message.edit_text(i18n.get("settings_language_changed", selected_lang))
                await callback.message.answer(
                    welcome_text,
                    reply_markup=get_main_menu(role="admin", is_admin=True, lang=selected_lang),
                )
                
                # Очищаем FSM
                await state.clear()
                logger.info(f"[LANGUAGE] FSM cleared for admin {telegram_id} - registration complete")
                await callback.answer()
            else:
                # Обычный пользователь - сохраняем язык и запрашиваем инвайт-код
                await state.update_data(selected_language=selected_lang)
                await callback.message.edit_text(i18n.get("registration_invite_code", selected_lang))
                await callback.answer()
                
                logger.info(f"[LANGUAGE] User {telegram_id} - waiting for invite code (language saved: {selected_lang})")
                
    except Exception as e:
        logger.error(f"[LANGUAGE] Error in language selection handler: {e}", exc_info=True)
        await callback.answer("Произошла ошибка / Error occurred")


@router.message(
    lambda message: message.text and not message.text.startswith("/"),
    StateFilter(RegistrationState.waiting_for_language)
)
async def handle_invite_code_after_language(
    message: Message, state: FSMContext
) -> None:
    """Обработчик инвайт-кода после выбора языка (пользователь УЖЕ существует в БД)."""
    try:
        from app.core.i18n import i18n
        
        # Получаем данные из FSM
        data = await state.get_data()
        telegram_id = data.get("telegram_id")
        selected_lang = data.get("selected_language", "ru")
        
        invite_code = message.text.strip()
        
        logger.info(f"[INVITE] User {telegram_id} entered invite code: {invite_code}")

        # Проверяем инвайт-код
        if invite_code != settings.invite_code:
            await message.answer(i18n.get("registration_wrong_invite", selected_lang))
            logger.info(f"[INVITE] ❌ Wrong invite code for user {telegram_id}: '{invite_code}' (expected: '{settings.invite_code}')")
            return

        # КРИТИЧНО: Пользователь УЖЕ создан в БД при /start
        # Просто проверяем что язык сохранен
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.telegram_id == telegram_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                logger.error(f"[INVITE] ❌ CRITICAL: User {telegram_id} NOT found in DB!")
                await message.answer("Ошибка: пользователь не найден. Попробуйте /start снова.")
                return
            
            logger.info(f"[INVITE] User {telegram_id} found in DB: id={user.id}, role={user.role}, language={user.language}")
            logger.info(f"[INVITE] ✅ Invite code correct, user can proceed to department selection")

            # Переводим в состояние выбора отдела
            await state.set_state(RegistrationState.waiting_for_department)
            await state.update_data(user_id=telegram_id, language=selected_lang)
            
            # Отправляем клавиатуру выбора отдела на выбранном языке
            await message.answer(
                i18n.get("registration_choose_department", selected_lang),
                reply_markup=get_department_selection_keyboard(context="registration")
            )
            logger.info(f"[INVITE] User {telegram_id} moved to department selection")

    except Exception as e:
        logger.error(f"[INVITE] Error in invite code handler: {e}", exc_info=True)
        await message.answer("Произошла ошибка при обработке инвайт-кода.")


@router.message(lambda message: message.text and not message.text.startswith("/"), StateFilter(None))
async def handle_invite_code(
    message: Message, state: FSMContext, role: str | None = None, user_id: int | None = None
) -> None:
    """Обработчик инвайт-кода для регистрации новых пользователей (старая версия для обратной совместимости)."""
    try:
        # Если пользователь уже зарегистрирован, игнорируем
        if role is not None:
            return

        telegram_id = user_id or message.from_user.id
        
        # Если админ, не требуем инвайт-код (он уже зарегистрируется через /start)
        if telegram_id in settings.admin_ids:
            return
        
        # Этот хендлер больше не должен срабатывать для новых пользователей,
        # так как они проходят через выбор языка
        # Оставляем для обратной совместимости
        
    except Exception as e:
        logger.error(f"Error in invite code handler: {e}", exc_info=True)
        await message.answer("Произошла ошибка при обработке инвайт-кода.")


@router.callback_query(lambda c: c.data and c.data.startswith("dept_registration_"), StateFilter(RegistrationState.waiting_for_department))
async def handle_department_selection(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора отдела при регистрации."""
    try:
        from app.core.i18n import i18n
        
        data = callback.data
        user_id = callback.from_user.id
        
        # Получаем язык из FSM data
        fsm_data = await state.get_data()
        lang = fsm_data.get("language", "ru")
        
        logger.info(f"[DEPT] User {user_id} callback: {data}, lang={lang}")
        
        # Показываем sub-menu для доставки
        if data == "dept_registration_delivery_menu":
            await callback.message.edit_text(
                i18n.get("department_choose_delivery_type", lang),
                reply_markup=get_delivery_submenu_keyboard(context="registration")
            )
            await callback.answer()
            return
        
        # Кнопка "Назад"
        if data == "dept_registration_back":
            await callback.message.edit_text(
                i18n.get("registration_choose_department", lang),
                reply_markup=get_department_selection_keyboard(context="registration")
            )
            await callback.answer()
            return
        
        # Извлекаем код отдела из callback_data
        # Формат: dept_registration_{department_code}
        department_code = data.replace("dept_registration_", "")
        
        # Проверяем, что это валидный отдел
        valid_departments = [dept.value for dept in Department]
        if department_code not in valid_departments:
            await callback.answer(i18n.get("error_invalid_department", lang))
            return
        
        # Сохраняем отдел в БД
        async with AsyncSessionLocal() as session:
            success = await set_user_department(session, user_id, department_code)
            
            if success:
                display_name = get_department_display_name(department_code)
                
                logger.info(f"[DEPT] ✅ User {user_id} registered to department: {department_code}")
                logger.info(f"[DEPT] User language: {lang}, clearing FSM state")
                
                # Удаляем клавиатуру и отправляем welcome message
                await callback.message.edit_text(
                    i18n.get("registration_completed", lang, department=display_name)
                )
                
                # Отправляем главное меню на выбранном языке
                await callback.message.answer(
                    i18n.get("registration_use_buttons", lang),
                    reply_markup=get_main_menu(role="employee", lang=lang)
                )
                
                # Очищаем FSM - КРИТИЧНО для завершения регистрации
                await state.clear()
                logger.info(f"[DEPT] FSM state cleared for user {user_id} - registration complete")
                
                await callback.answer(i18n.get("registration_completed", lang, department=display_name)[:64])
            else:
                logger.error(f"[DEPT] ❌ Failed to save department for user {user_id}")
                await callback.answer(i18n.get("error_saving_department", lang))
                
    except Exception as e:
        logger.error(f"[DEPT] Error in department selection: {e}", exc_info=True)
        await callback.answer("Произошла ошибка. Попробуйте позже.")


