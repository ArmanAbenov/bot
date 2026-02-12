"""Хендлеры для медиа-контента (голосовые сообщения, аудио)."""
import re
import tempfile
from pathlib import Path
from typing import List

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.keyboards.main_menu import get_main_menu
from app.core.database import AsyncSessionLocal
from app.services.ai_service import GeminiService
from app.utils.logger import logger
from app.utils.states import QuestionState

router = Router(name="media")


def create_media_keyboard(media_links: dict[str, List[str]]) -> InlineKeyboardMarkup | None:
    """
    Создает клавиатуру с кнопками для медиа-ссылок.
    
    Args:
        media_links: Словарь с типами ссылок и их значениями
    
    Returns:
        InlineKeyboardMarkup с кнопками или None, если ссылок нет
    """
    buttons: List[List[InlineKeyboardButton]] = []
    
    # Добавляем YouTube ссылки
    for youtube_url in media_links.get("youtube", [])[:3]:  # Максимум 3 ссылки
        video_id = re.search(r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})', youtube_url)
        if video_id:
            buttons.append([
                InlineKeyboardButton(
                    text=f"🎥 YouTube: {youtube_url.split('v=')[-1][:20]}...",
                    url=youtube_url
                )
            ])
    
    # Добавляем файлы
    for file_url in media_links.get("files", [])[:3]:  # Максимум 3 ссылки
        file_name = file_url.split("/")[-1][:30]
        buttons.append([
            InlineKeyboardButton(
                text=f"📄 {file_name}",
                url=file_url
            )
        ])
    
    # Добавляем изображения
    for image_url in media_links.get("images", [])[:2]:  # Максимум 2 изображения
        image_name = image_url.split("/")[-1][:30]
        buttons.append([
            InlineKeyboardButton(
                text=f"🖼️ {image_name}",
                url=image_url
            )
        ])
    
    if buttons:
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    return None


def format_response_with_media(response_text: str, media_links: dict[str, List[str]]) -> tuple[str, InlineKeyboardMarkup | None]:
    """
    Форматирует ответ с медиа-ссылками.
    
    Args:
        response_text: Текст ответа
        media_links: Словарь с медиа-ссылками
    
    Returns:
        Кортеж (форматированный текст, клавиатура с кнопками)
    """
    # Если есть YouTube ссылки, добавляем информацию в текст
    if media_links.get("youtube"):
        response_text += "\n\n🎥 Доступны видео по теме:"
    
    # Если есть файлы, добавляем информацию
    if media_links.get("files"):
        response_text += "\n📄 Доступны дополнительные файлы:"
    
    keyboard = create_media_keyboard(media_links)
    
    return response_text, keyboard


@router.message(StateFilter(QuestionState.waiting_for_question), F.voice)
async def handle_voice_in_fsm(
    message: Message,
    bot: Bot,
    state: FSMContext,
    role: str | None = None
) -> None:
    """Обработчик голосовых сообщений в FSM состоянии ожидания вопроса."""
    try:
        # Обрабатываем только зарегистрированных пользователей
        if role is None:
            await state.clear()
            await message.answer("Ошибка: пользователь не зарегистрирован.")
            return
        
        telegram_id = message.from_user.id
        voice = message.voice
        
        logger.info(
            f"[VOICE] User {telegram_id} sent voice message "
            f"(duration: {voice.duration}s, file_id: {voice.file_id}, file_size: {voice.file_size} bytes)"
        )
        
        # Показываем статус "Печатает..."
        await bot.send_chat_action(chat_id=telegram_id, action="typing")
        
        # Создаем временную директорию для файлов
        temp_dir = Path(tempfile.gettempdir()) / "uq_bot_voice"
        temp_dir.mkdir(exist_ok=True)
        
        try:
            # Этап 1: Получаем информацию о файле
            logger.info(f"[VOICE] Step 1: Getting file info for file_id: {voice.file_id}")
            file_info = await bot.get_file(voice.file_id)
            logger.info(f"[VOICE] File info received: path={file_info.file_path}, size={file_info.file_size}")
            
            # Этап 2: Скачиваем файл во временную папку
            temp_file_path = temp_dir / f"voice_{telegram_id}_{voice.file_id}.ogg"
            logger.info(f"[VOICE] Step 2: Downloading file to temporary path: {temp_file_path}")
            
            await bot.download_file(
                file_path=file_info.file_path,
                destination=temp_file_path
            )
            
            # Проверяем, что файл скачался
            if not temp_file_path.exists():
                raise FileNotFoundError(f"Файл не был скачан: {temp_file_path}")
            
            file_size = temp_file_path.stat().st_size
            logger.info(f"[VOICE] File downloaded successfully: size={file_size} bytes, path={temp_file_path}")
            
            # Читаем файл в байты
            with open(temp_file_path, "rb") as f:
                audio_data = f.read()
            
            logger.info(f"[VOICE] Step 3: File read into memory: {len(audio_data)} bytes")
            
            # Определяем MIME тип (Telegram обычно отправляет .ogg в формате opus)
            mime_type = "audio/ogg"
            logger.info(f"[VOICE] Step 4: Preparing to send to Gemini with mime_type={mime_type}")
            
            # Получаем ответ от Gemini с RAG поиском
            async with AsyncSessionLocal() as session:
                response_text = await GeminiService.get_answer_from_audio_with_rag(
                    audio_file_path=str(temp_file_path),
                    audio_bytes=audio_data,
                    audio_mime_type=mime_type,
                    user_id=telegram_id,
                    session=session
                )
            
            logger.info(f"[VOICE] Step 5: Received response from Gemini (length: {len(response_text)} chars)")
            
            # Извлекаем медиа-ссылки из ответа
            media_links = GeminiService.extract_media_links(response_text)
            
            # Форматируем ответ с медиа-кнопками
            formatted_response, media_keyboard = format_response_with_media(response_text, media_links)
            
            # Отправляем ответ пользователю
            await message.answer(
                formatted_response,
                reply_markup=get_main_menu(role=role) if media_keyboard is None else None
            )
            
            # Если есть медиа-кнопки, отправляем их отдельным сообщением
            if media_keyboard:
                await message.answer(
                    "📎 Полезные ссылки по теме:",
                    reply_markup=media_keyboard
                )
                await message.answer(
                    "Вы можете задать следующий вопрос или вернуться в меню.",
                    reply_markup=get_main_menu(role=role)
                )
            
            # Сбрасываем состояние после ответа
            await state.clear()
            
            logger.info(f"[VOICE] Step 6: Successfully sent response to user {telegram_id}")
            
        except Exception as e:
            logger.error(
                f"[VOICE] ERROR processing voice message for user {telegram_id}: {type(e).__name__}: {e}",
                exc_info=True
            )
            logger.error(f"[VOICE] Error details - file_id: {voice.file_id}, file_path: {file_info.file_path if 'file_info' in locals() else 'N/A'}")
            await state.clear()
            await message.answer(
                "Извините, произошла ошибка при обработке голосового сообщения. "
                "Попробуйте отправить текст или обратитесь к администратору.",
                reply_markup=get_main_menu(role=role)
            )
        finally:
            # Очищаем временный файл
            if 'temp_file_path' in locals() and temp_file_path.exists():
                try:
                    temp_file_path.unlink()
                    logger.info(f"[VOICE] Cleaned up temporary file: {temp_file_path}")
                except Exception as cleanup_error:
                    logger.warning(f"[VOICE] Failed to cleanup temp file {temp_file_path}: {cleanup_error}")
            
    except Exception as e:
        logger.error(
            f"[VOICE] FATAL ERROR in voice handler for user {message.from_user.id}: {type(e).__name__}: {e}",
            exc_info=True
        )
        await state.clear()
        await message.answer(
            "Произошла ошибка при обработке голосового сообщения.",
            reply_markup=get_main_menu(role=role) if role else None
        )


