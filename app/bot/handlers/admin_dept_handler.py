"""Callback обработчики для выбора отдела при добавлении знаний."""
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot.keyboards.department import get_admin_department_keyboard, get_delivery_submenu_keyboard
from app.bot.handlers.admin import get_admin_menu, check_admin_access
from app.core.models import Department
from app.services.ai_service import GeminiService
from app.utils.logger import logger
from app.utils.states import AdminState
from app.utils.department import get_department_display_name

router = Router(name="admin_department_choice")


@router.callback_query(
    F.data.startswith("dept_admin_knowledge_"),
    AdminState.waiting_for_department_choice
)
async def handle_department_choice_for_knowledge(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext
) -> None:
    """Обрабатывает выбор отдела для сохранения знания."""
    try:
        # КРИТИЧНО: Первым делом отвечаем на callback, чтобы избежать "query is too old"
        await callback.answer("⏳ Обрабатываю...")
        
        if not await check_admin_access(callback.from_user.id):
            await callback.message.answer("У вас нет доступа.")
            await state.clear()
            return
        
        callback_data = callback.data
        logger.info(f"[DEPT_CHOICE] Admin {callback.from_user.id} callback: {callback_data}")
        
        # Обработка submenu "Доставка"
        if callback_data == "dept_admin_knowledge_delivery_menu":
            await callback.message.edit_text(
                "📦 Выберите тип доставки:",
                reply_markup=get_delivery_submenu_keyboard(context="admin_knowledge")
            )
            await callback.answer()
            return
        
        # Обработка "Назад"
        if callback_data == "dept_admin_knowledge_back":
            await callback.message.edit_text(
                "📂 В какой отдел добавить это знание?",
                reply_markup=get_admin_department_keyboard()
            )
            await callback.answer()
            return
        
        # Извлекаем department из callback_data
        department_value = callback_data.replace("dept_admin_knowledge_", "")
        
        # Получаем данные из state
        data = await state.get_data()
        content_type = data.get("content_type")
        
        if not content_type:
            await callback.answer("Ошибка: данные не найдены", show_alert=True)
            await state.clear()
            return
        
        # Определяем папку назначения
        if department_value == "common":
            target_dir = Path("data/knowledge/common")
            dept_display = "Общие для всех"
        else:
            target_dir = Path(f"data/knowledge/{department_value}")
            dept_display = get_department_display_name(department_value)
        
        # Создаем директорию если не существует
        target_dir.mkdir(parents=True, exist_ok=True)
        
        telegram_id = callback.from_user.id
        
        # Обработка в зависимости от типа контента
        if content_type in ["voice", "text"]:
            # Для голосовых и текстовых знаний
            filename = data.get("filename")
            structured_text = data.get("structured_text")
            
            if not filename or not structured_text:
                await callback.answer("Ошибка: данные некорректны", show_alert=True)
                await state.clear()
                return
            
            # Формируем путь к файлу
            file_path = target_dir / f"{filename}.txt"
            
            # Проверяем, не существует ли файл с таким именем
            counter = 1
            original_filename = filename
            while file_path.exists():
                filename = f"{original_filename}_{counter}"
                file_path = target_dir / f"{filename}.txt"
                counter += 1
            
            # Сохраняем файл
            file_path.write_text(structured_text, encoding="utf-8")
            
            logger.info(f"[DEPT_CHOICE] Admin {telegram_id} saved {content_type} knowledge to {file_path}")
            
            success_message = (
                f"✅ Знание успешно добавлено!\n\n"
                f"📄 Файл: {filename}.txt\n"
                f"📊 Размер: {len(structured_text)} символов\n"
                f"📂 Отдел: {dept_display}\n"
                f"💾 Путь: {file_path.relative_to(Path('data'))}"
            )
        
        elif content_type == "document":
            # Для файлов (документов)
            filename = data.get("filename")
            file_id = data.get("file_id")
            file_size = data.get("file_size", 0)
            
            if not filename or not file_id:
                await callback.answer("Ошибка: данные файла некорректны", show_alert=True)
                await state.clear()
                return
            
            # Формируем путь к файлу
            file_path = target_dir / filename
            
            # Проверяем, не существует ли файл с таким именем
            counter = 1
            original_filename = filename
            while file_path.exists():
                name_part = Path(original_filename).stem
                ext_part = Path(original_filename).suffix
                filename = f"{name_part}_{counter}{ext_part}"
                file_path = target_dir / filename
                counter += 1
            
            if filename != original_filename:
                logger.info(f"File {original_filename} renamed to {filename} (duplicate)")
            
            # Получаем информацию о файле и скачиваем
            file_info = await bot.get_file(file_id)
            await bot.download_file(
                file_path=file_info.file_path,
                destination=file_path
            )
            
            logger.info(f"[DEPT_CHOICE] Admin {telegram_id} saved document to {file_path}")
            
            success_message = (
                f"✅ Файл успешно добавлен!\n\n"
                f"📄 Имя: {filename}\n"
                f"📊 Размер: {file_size} байт\n"
                f"📂 Отдел: {dept_display}\n"
                f"💾 Путь: {file_path.relative_to(Path('data'))}"
            )
        
        else:
            await callback.answer("Неизвестный тип контента", show_alert=True)
            await state.clear()
            return
        
        # Обновляем векторные индексы АСИНХРОННО (ТОЧЕЧНО для конкретного отдела)
        try:
            await callback.message.edit_text("⏳ Начинаю индексацию. Пожалуйста, подождите...")
            
            # Определяем департамент для точечного обновления
            target_department = department_value if department_value != "common" else None
            
            if target_department:
                # Точечное обновление ТОЛЬКО для выбранного отдела
                logger.info(f"[RAG] 🎯 Точечное обновление индекса для отдела: {target_department}")
                import asyncio
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, GeminiService.rebuild_index_for_department, target_department)
                logger.info(f"[RAG] ✅ Index updated for {target_department}")
            else:
                # Файл добавлен в common - обновляем ВСЕ индексы
                logger.info("[RAG] Файл добавлен в common/ - обновляем все индексы...")
                import asyncio
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, GeminiService._create_department_indices)
                logger.info("[RAG] ✅ All department indices updated")
        except Exception as e:
            logger.error(f"[RAG] Error updating vector index: {e}", exc_info=True)
            success_message += "\n\n⚠️ Внимание: Ошибка обновления индекса. Перезапустите бота."
        
        # Сбрасываем состояние
        await state.clear()
        
        # Отправляем сообщение об успехе
        await callback.message.edit_text(success_message)
        await callback.message.answer(
            "Что дальше?",
            reply_markup=get_admin_menu()
        )
        
    except Exception as e:
        logger.error(f"[DEPT_CHOICE] Error in department choice handler: {e}", exc_info=True)
        await callback.answer("Произошла ошибка при сохранении", show_alert=True)
        await state.clear()
        try:
            await callback.message.answer(
                "❌ Произошла ошибка при сохранении знания.",
                reply_markup=get_admin_menu()
            )
        except:
            pass
