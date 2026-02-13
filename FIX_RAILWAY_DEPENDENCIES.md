# Исправление зависимостей для Railway

## Проблема
```
ModuleNotFoundError: No module named 'google.api_core'
```

## Причина
В `requirements.txt` была указана только библиотека `google-genai`, но код использует:
- `from google import genai`
- `from google.genai import types`
- `from google.api_core.exceptions import ResourceExhausted`

Для корректной работы нужны ВСЕ три библиотеки Google Gemini.

## Решение

### Добавлены зависимости:
```
google-genai>=0.3.0
google-generativeai>=0.8.0
google-api-core>=2.19.0
```

### Проверено наличие критичных библиотек:
- ✅ `aiogram>=3.14.0` - Telegram Bot API
- ✅ `pydantic-settings>=2.5.2` - для `config.py`
- ✅ `faiss-cpu==1.13.2` - векторная база данных
- ✅ `pymupdf==1.24.14` - чтение PDF файлов
- ✅ `python-docx==1.1.2` - чтение DOCX файлов
- ✅ `pydub>=0.25.1` - обработка аудио

### Удалены ненужные зависимости:
- ❌ `openai` - не используется (закомментирована)
- ❌ `langchain` - не используется (закомментирована)
- ❌ `langchain-openai` - не используется (закомментирована)

## Команды для коммита и деплоя

```powershell
# 1. Проверьте изменения
git diff requirements.txt

# 2. Закоммитьте исправление
git add requirements.txt

git commit -m "Fix: Add missing Google Gemini dependencies for Railway

- Added google-generativeai>=0.8.0
- Added google-api-core>=2.19.0
- Fixed ModuleNotFoundError on Railway deployment
- Removed unused OpenAI and LangChain dependencies"

# 3. Отправьте на GitHub (Railway автоматически задеплоит)
git push origin main
```

## Проверка после деплоя

Railway автоматически:
1. Обнаружит изменения в `requirements.txt`
2. Установит новые зависимости
3. Перезапустит бот

Проверьте логи в Railway Dashboard:
```
✅ Successfully installed google-api-core-2.19.0
✅ Bot started successfully
```

## Размер пакетов

Приблизительный размер установки:
- `google-genai`: ~5 MB
- `google-generativeai`: ~8 MB
- `google-api-core`: ~15 MB
- `faiss-cpu`: ~30 MB
- `pymupdf`: ~20 MB

**Общий размер зависимостей**: ~150-200 MB (в пределах лимитов Railway)

## Альтернативное решение (если Railway все еще падает)

Если Railway не хватает памяти, можно использовать только `google-generativeai`:

```txt
# Минимальный набор (вместо трех библиотек)
google-generativeai>=0.8.0
```

Но тогда нужно изменить импорты в `ai_service.py`:
```python
# Было:
from google import genai
from google.genai import types
from google.api_core.exceptions import ResourceExhausted

# Стало:
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from google.api_core.exceptions import ResourceExhausted
```

**Рекомендация**: Сначала попробуйте текущее решение (все 3 библиотеки).
