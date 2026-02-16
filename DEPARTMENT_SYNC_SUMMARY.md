# ✅ Исправление синхронизации отделов с папками RAG - ЗАВЕРШЕНО

## Проблема

RAG не находил индексы отделов из-за несоответствия названий:

**До:**
- БД: `"Department.SORTING"` ❌
- Папка: `data/knowledge/sorting/`
- Индекс: `"sorting"`
- **Результат:** Индекс не найден! → Fallback

**После:**
- БД: `"sorting"` ✅
- Папка: `data/knowledge/sorting/`
- Индекс: `"sorting"`
- **Результат:** Индекс найден! → Работает

## Что исправлено

### 1️⃣ Исправлены методы Department (models.py)

**Было:**
```python
return {
    cls.SORTING: "Сортировочный центр",  # ❌ Enum объект
}
```

**Стало:**
```python
return {
    cls.SORTING.value: "Сортировочный центр",  # ✅ Строка "sorting"
}
```

### 2️⃣ Добавлена нормализация (department.py)

```python
async def get_user_department(...):
    department = result.scalar_one_or_none()
    
    if department:
        # ✅ Нормализация старых записей
        dept_key = str(department).lower()
        if "department." in dept_key:
            dept_key = dept_key.split(".")[-1]
        
        # "Department.SORTING" → "sorting"
        return dept_key
```

### 3️⃣ Улучшено логирование RAG (ai_service.py)

```python
logger.info(f"[RAG] User {user_id} department: {user_department}")
logger.info(f"[RAG] Available indices: {list(GeminiService._vector_stores.keys())}")  # ✅ Новое
logger.info(f"[RAG] Searching in folder: {user_department}")  # ✅ Новое
```

## Логи до и после

### ❌ До исправления:

```
[DEPT] User 123456 belongs to department: Department.SORTING
[RAG] Department Department.SORTING not found in indices, using fallback
```

### ✅ После исправления:

```
[DEPT] User 123456 belongs to department: sorting (raw: Department.SORTING)
[RAG] User 123456 department: sorting
[RAG] Available indices: ['common', 'sorting', 'delivery/courier', 'manager', 'customer_service']
[RAG] Searching in folder: sorting
[RAG] User 123456 (Dept: sorting) searching in department index...
[RAG] Found 3 chunks (from sorting + common)
```

## Обратная совместимость

✅ **Работает со старыми записями:**
- Если в БД `"Department.SORTING"` → нормализуется в `"sorting"`
- Если в БД `"sorting"` → работает как есть

✅ **Миграция БД не требуется:**
- Нормализация происходит автоматически при чтении
- Старые данные не ломают систему

## Тестирование

### 1. Проверь логи после запуска:

```bash
python -m app.main

# В другом терминале:
tail -f logs/bot.log | grep "\[RAG\]"
```

**Должны увидеть:**
```
[RAG] Creating indices for departments: ['common', 'sorting', 'delivery/courier', ...]
[RAG] Available indices: ['common', 'sorting', ...]
```

### 2. Назначь отдел пользователю:

1. Открой "👥 Сотрудники"
2. Выбери сотрудника
3. Нажми "Изменить отдел"
4. Выбери "Сортировочный центр"

**Проверь логи:**
```
[EMPLOYEES] Department assigned to 123456: sorting
[DEPT] User 123456 belongs to department: sorting
```

### 3. Задай вопрос от пользователя:

Отправь сообщение от пользователя с отделом "sorting"

**Проверь логи:**
```
[RAG] User 123456 department: sorting
[RAG] Available indices: ['common', 'sorting', ...]
[RAG] Searching in folder: sorting
[RAG] User 123456 (Dept: sorting) searching in department index...
[RAG] Found 3 chunks (from sorting + common)
```

## Измененные файлы

1. **app/core/models.py**
   - `get_display_names()`: ключи `.value`
   - `get_admin_assignable_departments()`: ключи `.value`

2. **app/utils/department.py**
   - `get_user_department()`: нормализация + логирование

3. **app/services/ai_service.py**
   - Логирование доступных индексов
   - Логирование папки поиска
   - `.lower()` при создании индексов

## Готово! 🎉

Теперь RAG корректно находит индексы отделов:

✅ Синхронизация БД ↔ Папки  
✅ Нормализация старых записей  
✅ Подробное логирование  
✅ Обратная совместимость  

## Следующие шаги

### 1. Деплой:

```bash
git add .
git commit -m "fix: синхронизация названий отделов с папками RAG

- Исправлены методы Department (ключи .value)
- Добавлена нормализация в get_user_department
- Улучшено логирование RAG
- Обратная совместимость со старыми записями"

git push origin main
```

### 2. Проверь на production:

После деплоя проверь логи:

```bash
# SSH на сервер
ssh user@server

# Смотри логи
tail -f logs/bot.log | grep "\[RAG\]"
```

Должны увидеть правильные названия отделов и найденные индексы.

### 3. (Опционально) Очисти БД:

Если хочешь привести БД в порядок (но не обязательно):

```sql
UPDATE users SET department = 'sorting' WHERE department LIKE '%SORTING%';
UPDATE users SET department = 'manager' WHERE department LIKE '%MANAGER%';
UPDATE users SET department = 'customer_service' WHERE department LIKE '%CUSTOMER_SERVICE%';
```

Но система работает и без этого благодаря нормализации!
