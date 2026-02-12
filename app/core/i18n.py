"""Система интернационализации (i18n) для бота."""
import json
from pathlib import Path
from typing import Dict, Optional

from app.utils.logger import logger


class I18nManager:
    """Класс-синглтон для управления локализацией."""

    _instance: Optional["I18nManager"] = None
    _translations: Dict[str, Dict[str, str]] = {}
    _default_lang: str = "ru"
    _supported_languages: list[str] = ["ru", "kk", "en", "zh"]

    def __new__(cls) -> "I18nManager":
        """Создает единственный экземпляр класса (паттерн Singleton)."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Инициализирует менеджер локализации."""
        # Загружаем переводы только при первой инициализации
        if not self._translations:
            self._load_translations()

    def _load_translations(self) -> None:
        """Загружает все JSON-файлы с переводами."""
        locales_dir = Path(__file__).parent / "locales"
        
        if not locales_dir.exists():
            logger.error(f"Locales directory not found: {locales_dir}")
            raise FileNotFoundError(f"Locales directory not found: {locales_dir}")

        for lang_code in self._supported_languages:
            locale_file = locales_dir / f"{lang_code}.json"
            
            if not locale_file.exists():
                logger.warning(f"Locale file not found: {locale_file}")
                continue
            
            try:
                with open(locale_file, "r", encoding="utf-8") as f:
                    self._translations[lang_code] = json.load(f)
                logger.info(f"✅ Loaded translations for language: {lang_code}")
            except Exception as e:
                logger.error(f"Error loading locale file {locale_file}: {e}", exc_info=True)
                raise

        if not self._translations:
            raise ValueError("No translations loaded! Check locales directory.")

    def get(self, key: str, lang: str = "ru", **kwargs) -> str:
        """
        Получает переведенную строку по ключу и языку.

        Args:
            key: Ключ строки в словаре
            lang: Код языка (ru, kk, en, zh)
            **kwargs: Параметры для форматирования строки (например, {role}, {department})

        Returns:
            Переведенная и отформатированная строка
        """
        # Если язык не поддерживается, используем дефолтный
        if lang not in self._supported_languages:
            logger.warning(f"Unsupported language: {lang}, using default: {self._default_lang}")
            lang = self._default_lang

        # Получаем словарь для языка
        lang_dict = self._translations.get(lang)
        
        if lang_dict is None:
            logger.error(f"Translations not found for language: {lang}")
            # Fallback на дефолтный язык
            lang_dict = self._translations.get(self._default_lang, {})

        # Получаем строку по ключу
        text = lang_dict.get(key)
        
        if text is None:
            logger.warning(f"Translation key not found: '{key}' for language: {lang}")
            # Fallback на дефолтный язык
            default_dict = self._translations.get(self._default_lang, {})
            text = default_dict.get(key, f"[Missing: {key}]")

        # Форматируем строку с параметрами
        try:
            if kwargs:
                text = text.format(**kwargs)
        except KeyError as e:
            logger.error(f"Formatting error for key '{key}': {e}")
        
        return text

    def get_supported_languages(self) -> list[str]:
        """Возвращает список поддерживаемых языков."""
        return self._supported_languages.copy()

    def reload(self) -> None:
        """Перезагружает все переводы (для разработки)."""
        self._translations.clear()
        self._load_translations()
        logger.info("Translations reloaded")


# Глобальный экземпляр менеджера локализации
i18n = I18nManager()
