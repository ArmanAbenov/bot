"""Настройка логирования."""
import logging
import sys
from pathlib import Path

# Создаем директорию для логов
log_dir = Path(__file__).parent.parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

# Настройка формата логов
log_format = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Логгер для приложения
logger = logging.getLogger("uqbot")
logger.setLevel(logging.INFO)

# Консольный handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(log_format)

# Файловый handler
file_handler = logging.FileHandler(log_dir / "uqbot.log", encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(log_format)

# Добавляем handlers
logger.addHandler(console_handler)
logger.addHandler(file_handler)
