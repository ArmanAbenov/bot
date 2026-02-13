"""Хендлеры для раздела настроек."""
from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select, update

from app.bot.keyboards.language import get_language_selection_keyboard
from app.bot.keyboards.main_menu import get_main_menu
from app.core.database import AsyncSessionLocal
from app.core.i18n import I18nManager, i18n
from app.core.models import User
from app.services.admin_service import is_admin
from app.utils.logger import logger

router = Router(name="settings")


@router.message(lambda message: message.text in [
    "⚙️ Настройки",
    "⚙️ Баптаулар",
    "⚙️ Settings",
    "⚙️ 设置"
])
async def handle_settings_button(
    message: Message,
    role: str | None = None,
    lang: str = "ru",
    i18n: I18nManager | None = None
) -> None:
    """Обработчик кнопки 'Настройки'."""
    try:
        if role is None:
            await message.answer(
                i18n.get("error_user_not_registered", lang) if i18n else "Для использования этой функции необходимо зарегистрироваться."
            )
            return
        
        # Создаем inline-клавиатуру с кнопкой смены языка
        settings_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text=i18n.get("settings_change_language", lang),
                    callback_data="settings_change_language"
                )],
            ]
        )
        
        await message.answer(
            i18n.get("settings_title", lang),
            reply_markup=settings_keyboard
        )
        logger.info(f"User {message.from_user.id} opened settings")
        
    except Exception as e:
        logger.error(f"Error in settings button handler: {e}", exc_info=True)
        await message.answer(i18n.get("error_generic", lang) if i18n else "Произошла ошибка.")


@router.callback_query(lambda c: c.data == "settings_change_language")
async def handle_change_language_button(callback: CallbackQuery, lang: str = "ru", i18n: I18nManager | None = None) -> None:
    """Обработчик кнопки 'Сменить язык'."""
    try:
        await callback.message.edit_text(
            i18n.get("choose_language", lang),
            reply_markup=get_language_selection_keyboard()
        )
        await callback.answer()
        logger.info(f"User {callback.from_user.id} requested language change")
        
    except Exception as e:
        logger.error(f"Error in change language button handler: {e}", exc_info=True)
        await callback.answer("Произошла ошибка / Error occurred")


@router.callback_query(lambda c: c.data and c.data.startswith("lang_"))
async def handle_language_change(callback: CallbackQuery, role: str | None = None) -> None:
    """Обработчик смены языка в настройках (для СУЩЕСТВУЮЩИХ пользователей)."""
    try:
        # Получаем выбранный язык из callback_data (формат: lang_ru, lang_kk и т.д.)
        selected_lang = callback.data.replace("lang_", "")
        
        if selected_lang not in ["ru", "kk", "en", "zh"]:
            await callback.answer("Ошибка: неверный язык / Error: invalid language")
            return
        
        telegram_id = callback.from_user.id
        
        logger.info(f"[SETTINGS] User {telegram_id} changing language to: {selected_lang}")
        
        # Обновляем язык в БД - ИСПОЛЬЗУЕМ МЕТОД С REFRESH ВМЕСТО UPDATE
        async with AsyncSessionLocal() as session:
            # Получаем пользователя
            stmt = select(User).where(User.telegram_id == telegram_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                logger.error(f"[SETTINGS] ❌ User {telegram_id} NOT found in DB! Cannot change language.")
                await callback.answer("Ошибка: пользователь не найден в БД.", show_alert=True)
                return
            
            logger.info(f"[SETTINGS] User {telegram_id} found in DB: id={user.id}, current_lang={user.language}, role={user.role}")
            
            # Меняем язык через прямое присваивание (лучше чем UPDATE)
            old_lang = user.language
            user.language = selected_lang
            
            # Коммитим изменения
            await session.commit()
            logger.info(f"[SETTINGS] COMMIT executed for user {telegram_id}")
            
            # КРИТИЧНО: Перечитываем из БД для проверки
            await session.refresh(user)
            logger.info(f"[SETTINGS] ✅ User {telegram_id} language VERIFIED in DB: {user.language} (was: {old_lang}, set to: {selected_lang})")
            
            if user.language != selected_lang:
                logger.error(f"[SETTINGS] ❌ CRITICAL: Language NOT saved! DB={user.language}, expected={selected_lang}")
                logger.error(f"[SETTINGS] Database path: {settings.database_path}")
                logger.error(f"[SETTINGS] Database URL: {settings.database_url}")
            else:
                logger.info(f"[SETTINGS] ✅ SUCCESS: Language persisted correctly in DB")
            
            # Проверяем, является ли пользователь админом
            user_is_admin = await is_admin(session, telegram_id)
        
        # Отправляем подтверждение на новом языке
        await callback.message.edit_text(i18n.get("settings_language_changed", selected_lang))
        
        # Отправляем обновленное главное меню с новым языком
        role_display = i18n.get(f"role_{role}", selected_lang) if role else ""
        welcome_text = f"{i18n.get('welcome_text', selected_lang)} {i18n.get('your_role', selected_lang, role=role_display)}"
        
        await callback.message.answer(
            welcome_text,
            reply_markup=get_main_menu(role=role, is_admin=user_is_admin, lang=selected_lang)
        )
        
        await callback.answer()
        logger.info(f"[SETTINGS] Language change completed for user {telegram_id}")
        
    except Exception as e:
        logger.error(f"[SETTINGS] Error in language change handler: {e}", exc_info=True)
        await callback.answer("Произошла ошибка / Error occurred")
