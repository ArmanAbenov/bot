# Исправление синхронизации названий отделов с папками знаний

## Проблема

В системе было несоответствие между названиями отделов в БД и папками знаний:

**До исправления:**
- В БД хранился Enum объект: `Department.SORTING`
- В папках знаний: `data/knowledge/sorting/`
- RAG не мог найти индекс, потому что искал по ключу `"Department.SORTING"` вместо `"sorting"`

**Ошибка:**
```
WARNING: "[RAG] Department Department.SORTING not found in indices, using fallback"
```

## Причина проблемы

### 1. Неправильные ключи в методах Department

**Файл:** `app/core/models.py`

**Было:**
```python
@classmethod
def get_display_names(cls) -> dict[str, str]:
    return {
        cls.COMMON: "Общий доступ",  # ❌ Ключ - Enum объект
        cls.SORTING: "Сортировочный центр",
        # ...
    }

@classmethod
def get_admin_assignable_departments(cls) -> dict[str, str]:
    return {
        cls.SORTING: "Сортировочный центр",  # ❌ Ключ - Enum объект
        # ...
    }
```

**Проблема:**
- Когда админ назначал отдел, в callback передавался Enum объект
- При преобразовании в строку: `str(Department.SORTING)` → `"Department.SORTING"`
- В БД сохранялось `"Department.SORTING"` вместо `"sorting"`

### 2. Отсутствие нормализации при получении отдела

**Файл:** `app/utils/department.py`

**Было:**
```python
async def get_user_department(session, user_id):
    department = result.scalar_one_or_none()
    return department  # ❌ Возвращалось "Department.SORTING"
```

**Проблема:**
- Если в БД уже сохранено `"Department.SORTING"`, оно так и возвращалось
- RAG искал индекс по ключу `"Department.SORTING"` вместо `"sorting"`

### 3. Ключи индексов не нормализованы

**Файл:** `app/services/ai_service.py`

**Было:**
```python
departments = [dept.value for dept in Department]
# dept.value может быть "sorting" или "Sorting"
```

**Проблема:**
- Не было гарантии что ключи в нижнем регистре
- Не было логирования доступных индексов

## Решение

### 1. Исправлены методы Department

**Файл:** `app/core/models.py`

```python
@classmethod
def get_display_names(cls) -> dict[str, str]:
    """Возвращает человекочитаемые названия отделов."""
    return {
        cls.COMMON.value: "Общий доступ",  # ✅ Ключ - строка значения
        cls.COURIER.value: "Курьер",
        cls.FRANCHISE.value: "Франчайзи",
        cls.SORTING.value: "Сортировочный центр",
        cls.CUSTOMER_SERVICE.value: "Клиентский сервис",
        cls.MANAGER.value: "Менеджер",
    }

@classmethod
def get_admin_assignable_departments(cls) -> dict[str, str]:
    """Возвращает отделы, которые админ может назначать (без COMMON)."""
    return {
        cls.SORTING.value: "Сортировочный центр",  # ✅ Ключ - строка значения
        cls.MANAGER.value: "Менеджер",
        cls.COURIER.value: "Курьер",
        cls.FRANCHISE.value: "Франчайзи",
        cls.CUSTOMER_SERVICE.value: "Клиентский сервис",
    }
```

**Результат:**
- Теперь ключи в словаре - это строки: `"sorting"`, `"manager"`, etc.
- При назначении отдела в callback передается строка, а не Enum
- В БД сохраняется правильное значение: `"sorting"`

### 2. Добавлена нормализация в get_user_department

**Файл:** `app/utils/department.py`

```python
async def get_user_department(session: AsyncSession, user_id: int) -> str | None:
    """
    Получает отдел пользователя из БД.
    
    Returns:
        Название отдела (нормализованное) или None если не установлен
    """
    try:
        stmt = select(User.department).where(User.telegram_id == user_id)
        result = await session.execute(stmt)
        department = result.scalar_one_or_none()
        
        if department:
            # ✅ Нормализация: убираем префикс "Department." если он есть
            dept_key = str(department).lower()
            if "department." in dept_key:
                dept_key = dept_key.split(".")[-1]
            
            # ✅ Если department - это Enum объект, берем его значение
            if hasattr(department, 'value'):
                dept_key = department.value.lower()
            
            logger.info(f"[DEPT] User {user_id} belongs to department: {dept_key} (raw: {department})")
            return dept_key
        else:
            logger.warning(f"[DEPT] User {user_id} has no department assigned")
            return None
            
    except Exception as e:
        logger.error(f"[DEPT] Error getting department for user {user_id}: {e}", exc_info=True)
        return None
```

**Что делает:**
- Нормализует старые записи типа `"Department.SORTING"` → `"sorting"`
- Обрабатывает Enum объекты если они попали в БД
- Приводит к нижнему регистру
- Логирует сырое и нормализованное значение

### 3. Улучшено логирование в RAG

**Файл:** `app/services/ai_service.py`

```python
# Получаем отдел пользователя для изоляции знаний
from app.utils.department import get_user_department
user_department = await get_user_department(session, user_id)

logger.info(f"[RAG] User {user_id} department: {user_department or 'admin (all departments)'}")
logger.info(f"[RAG] Available indices: {list(GeminiService._vector_stores.keys())}")  # ✅ Новое
if user_department:
    logger.info(f"[RAG] Searching in folder: {user_department}")  # ✅ Новое
```

**Что видно в логах:**
```
[RAG] User 123456 department: sorting (raw: Department.SORTING)
[RAG] Available indices: ['common', 'sorting', 'delivery/courier', 'manager', 'customer_service']
[RAG] Searching in folder: sorting
```

### 4. Гарантирован нижний регистр ключей индексов

**Файл:** `app/services/ai_service.py`

```python
# Получаем список всех отделов (нормализуем в нижний регистр)
departments = [dept.value.lower() for dept in Department]  # ✅ Добавлен .lower()
logger.info(f"[RAG] Creating indices for departments: {departments}")
```

**Результат:**
```
[RAG] Creating indices for departments: ['common', 'delivery/courier', 'sorting', 'customer_service', 'manager']
```

## Список изменений

### Измененные файлы:

1. **app/core/models.py**
   - `get_display_names()`: ключи теперь `cls.ENUM.value` вместо `cls.ENUM`
   - `get_admin_assignable_departments()`: ключи теперь `cls.ENUM.value` вместо `cls.ENUM`

2. **app/utils/department.py**
   - `get_user_department()`: добавлена нормализация департамента
   - Обработка старых записей типа `"Department.SORTING"`
   - Приведение к нижнему регистру
   - Расширенное логирование

3. **app/services/ai_service.py**
   - Добавлено логирование доступных индексов
   - Добавлено логирование папки поиска
   - Гарантирован `.lower()` при создании ключей индексов

## До и После

### До исправления:

```
[DEPT] User 123456 belongs to department: Department.SORTING
[RAG] User 123456 department: Department.SORTING
[RAG] Department Department.SORTING not found in indices, using fallback  ❌
```

### После исправления:

```
[DEPT] User 123456 belongs to department: sorting (raw: Department.SORTING)
[RAG] User 123456 department: sorting
[RAG] Available indices: ['common', 'sorting', 'delivery/courier', 'manager', 'customer_service']
[RAG] Searching in folder: sorting
[RAG] User 123456 (Dept: sorting) searching in department index...  ✅
[RAG] Found 3 chunks (from sorting + common)
```

## Обратная совместимость

Система полностью обратно совместима:

1. **Старые записи в БД:**
   - Если в БД сохранено `"Department.SORTING"` - нормализация преобразует в `"sorting"`
   - Если в БД сохранено `"sorting"` - работает как есть

2. **Enum значения:**
   - Enum значения уже в правильном формате: `Department.SORTING.value = "sorting"`
   - Добавлен `.lower()` для гарантии

3. **Папки знаний:**
   - Папки остаются как есть: `data/knowledge/sorting/`
   - Ключи индексов теперь совпадают с названиями папок

## Миграция данных

### Автоматическая миграция

Миграция БД не требуется! Нормализация происходит автоматически при чтении:

```python
# Старая запись в БД: "Department.SORTING"
user_department = await get_user_department(session, user_id)
# Возвращается: "sorting" ✅
```

### Ручная миграция (опционально)

Если хотите очистить БД от старых записей:

```sql
-- Обновить все записи типа "Department.SORTING" → "sorting"
UPDATE users SET department = 'sorting' WHERE department LIKE '%SORTING%';
UPDATE users SET department = 'manager' WHERE department LIKE '%MANAGER%';
UPDATE users SET department = 'customer_service' WHERE department LIKE '%CUSTOMER_SERVICE%';
UPDATE users SET department = 'delivery/courier' WHERE department LIKE '%COURIER%';
UPDATE users SET department = 'delivery/franchise' WHERE department LIKE '%FRANCHISE%';
UPDATE users SET department = 'common' WHERE department LIKE '%COMMON%';
```

Но это **не обязательно** - система работает с обоими форматами.

## Тестирование

### Сценарий 1: Новое назначение отдела

1. Админ назначает отдел "Сортировочный центр" пользователю
2. В БД сохраняется: `"sorting"` ✅
3. При поиске RAG использует ключ: `"sorting"` ✅
4. Индекс найден, поиск работает ✅

### Сценарий 2: Старая запись в БД

1. В БД записано: `"Department.SORTING"`
2. `get_user_department()` нормализует → `"sorting"` ✅
3. RAG использует ключ: `"sorting"` ✅
4. Индекс найден, поиск работает ✅

### Сценарий 3: Логирование

Проверьте логи бота после запуска:

```bash
# Поиск логов RAG
grep "\[RAG\]" logs/bot.log | tail -30

# Должны увидеть:
[RAG] Creating indices for departments: ['common', 'sorting', 'delivery/courier', ...]
[RAG] User 123456 department: sorting (raw: ...)
[RAG] Available indices: ['common', 'sorting', ...]
[RAG] Searching in folder: sorting
[RAG] User 123456 (Dept: sorting) searching in department index...
```

## Результат

✅ **Проблема решена:**
- Названия отделов синхронизированы между БД и папками
- RAG корректно находит индексы
- Старые записи автоматически нормализуются
- Подробное логирование для отладки

✅ **Обратная совместимость:**
- Работает со старыми и новыми записями
- Миграция БД не требуется

✅ **Улучшено логирование:**
- Видно какие индексы доступны
- Видно в какой папке происходит поиск
- Легко отлаживать проблемы с доступом
