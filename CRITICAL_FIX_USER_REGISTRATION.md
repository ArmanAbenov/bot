# 🚨 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Регистрация пользователя в БД

## Проблема
**Симптом:** При `/start` бот показывал выбор языка, но пользователь НЕ СОЗДАВАЛСЯ в БД. При попытке сменить язык получали ошибку: `"User NOT found in DB! Cannot change language."`

**Корневая причина:** Логика регистрации откладывала создание пользователя в БД до момента:
- Для админов: после выбора языка
- Для сотрудников: после ввода инвайт-кода

Это создавало "окно", когда пользователь был в процессе регистрации, но отсутствовал в БД.

---

## Решение

### Изменение 1: `app/bot/handlers/start.py` - Функция `cmd_start()`

**Было:** При обнаружении нового пользователя только показывался выбор языка.

**Стало:** **СРАЗУ создаем пользователя в БД** с временными значениями:
```python
user = User(
    telegram_id=telegram_id,
    full_name=full_name,
    role="admin" if user_is_admin else "employee",
    department=None,  # Будет выбран позже
    language=None,     # Будет выбран в следующем шаге
)
session.add(user)
await session.commit()
await session.refresh(user)
```

**Логирование:**
```
[START] New user {telegram_id} - creating in DB immediately
[START] ✅ User {telegram_id} CREATED in DB: id={user.id}, role={user.role}, language={user.language}
[START] Database path: {settings.database_path}
```

---

### Изменение 2: `app/bot/handlers/start.py` - Функция `handle_language_selection()`

**Было:** Создавал нового пользователя при выборе языка (для админов) или сохранял язык в FSM (для сотрудников).

**Стало:** **ОБНОВЛЯЕТ существующего пользователя**, который УЖЕ был создан при `/start`:
```python
stmt = select(User).where(User.telegram_id == telegram_id)
result = await session.execute(stmt)
user = result.scalar_one_or_none()

if not user:
    logger.error(f"[LANGUAGE] ❌ CRITICAL: User {telegram_id} NOT found in DB after /start!")
    await callback.answer("Ошибка: пользователь не найден. Попробуйте /start снова.", show_alert=True)
    return

# Обновляем язык
user.language = selected_lang
await session.commit()
await session.refresh(user)
```

**Логирование:**
```
[LANGUAGE] User {telegram_id} found in DB: id={user.id}, current_lang={user.language}, role={user.role}
[LANGUAGE] COMMIT executed for user {telegram_id}
[LANGUAGE] ✅ User {telegram_id} language VERIFIED in DB: {user.language}
[LANGUAGE] ✅ SUCCESS: Language persisted correctly in DB
```

---

### Изменение 3: `app/bot/handlers/start.py` - Функция `handle_invite_code_after_language()`

**Было:** Создавал нового пользователя после проверки инвайт-кода.

**Стало:** **Только проверяет что пользователь существует**, не создает нового:
```python
stmt = select(User).where(User.telegram_id == telegram_id)
result = await session.execute(stmt)
user = result.scalar_one_or_none()

if not user:
    logger.error(f"[INVITE] ❌ CRITICAL: User {telegram_id} NOT found in DB!")
    await message.answer("Ошибка: пользователь не найден. Попробуйте /start снова.")
    return

logger.info(f"[INVITE] ✅ Invite code correct, user can proceed to department selection")
```

---

### Изменение 4: `app/utils/department.py` - Функция `set_user_department()`

**Было:** Использовал `UPDATE` запрос без проверки.

**Стало:** **Находит пользователя, обновляет через прямое присваивание, проверяет с `refresh()`**:
```python
# Находим пользователя
stmt_select = select(User).where(User.telegram_id == user_id)
result = await session.execute(stmt_select)
user = result.scalar_one_or_none()

if not user:
    logger.error(f"[DEPT] ❌ CRITICAL: User {user_id} NOT found in DB!")
    return False

# Обновляем отдел
user.department = department
await session.commit()

# КРИТИЧНО: Проверяем что сохранилось
await session.refresh(user)
logger.info(f"[DEPT] ✅ User {user_id} department VERIFIED in DB: {user.department}")
```

**Логирование:**
```
[DEPT] User {user_id} found: id={user.id}, current_dept={user.department}, language={user.language}
[DEPT] COMMIT executed for user {user_id}
[DEPT] ✅ User {user_id} department VERIFIED in DB: {user.department}
[DEPT] ✅ SUCCESS: Department persisted correctly in DB
```

---

## Ожидаемый поток логов на Railway

### Новый пользователь (не админ):

1. **Команда `/start`:**
```
[START] New user {telegram_id} - creating in DB immediately
[START] ✅ User {telegram_id} CREATED in DB: id=1, role=employee, language=None
[START] Database path: /app/persist/uqsoft.db
[START] Language selection shown to user {telegram_id}
```

2. **Выбор языка:**
```
[LANGUAGE] User {telegram_id} selected language: ru, is_admin=False
[LANGUAGE] User {telegram_id} found in DB: id=1, current_lang=None, role=employee
[LANGUAGE] COMMIT executed for user {telegram_id}
[LANGUAGE] ✅ User {telegram_id} language VERIFIED in DB: ru (was: None, set to: ru)
[LANGUAGE] ✅ SUCCESS: Language persisted correctly in DB
[LANGUAGE] User {telegram_id} - waiting for invite code (language saved: ru)
```

3. **Ввод инвайт-кода:**
```
[INVITE] User {telegram_id} entered invite code: XXX
[INVITE] User {telegram_id} found in DB: id=1, role=employee, language=ru
[INVITE] ✅ Invite code correct, user can proceed to department selection
[INVITE] User {telegram_id} moved to department selection
```

4. **Выбор отдела:**
```
[DEPT] User {telegram_id} found: id=1, current_dept=None, language=ru
[DEPT] COMMIT executed for user {telegram_id}
[DEPT] ✅ User {telegram_id} department VERIFIED in DB: sorting (was: None, set to: sorting)
[DEPT] ✅ SUCCESS: Department persisted correctly in DB
[DEPT] ✅ User {telegram_id} registered to department: sorting
[DEPT] User language: ru, clearing FSM state
```

### Новый пользователь (админ):

1. **Команда `/start`:**
```
[START] New user {telegram_id} - creating in DB immediately
[START] ✅ User {telegram_id} CREATED in DB: id=2, role=admin, language=None
[START] Database path: /app/persist/uqsoft.db
[START] Language selection shown to user {telegram_id}
```

2. **Выбор языка (регистрация завершена):**
```
[LANGUAGE] User {telegram_id} selected language: ru, is_admin=True
[LANGUAGE] User {telegram_id} found in DB: id=2, current_lang=None, role=admin
[LANGUAGE] COMMIT executed for user {telegram_id}
[LANGUAGE] ✅ User {telegram_id} language VERIFIED in DB: ru (was: None, set to: ru)
[LANGUAGE] ✅ SUCCESS: Language persisted correctly in DB
[LANGUAGE] FSM cleared for admin {telegram_id} - registration complete
```

---

## Конфигурация Railway

### 1. Environment Variables (уже настроены):
```bash
DATABASE_PATH=/app/persist/uqsoft.db
TELEGRAM_BOT_TOKEN=your_token
GEMINI_API_KEY=your_key
ADMIN_IDS=123456789,987654321
INVITE_CODE=your_invite_code
```

### 2. Persistent Volume (уже создан):
- Mount Path: `/app/persist`
- БД будет: `/app/persist/uqsoft.db`

---

## Git команды для деплоя

```powershell
# 1. Проверка статуса
git status

# 2. Добавление всех изменений
git add app/bot/handlers/start.py app/utils/department.py

# 3. Коммит
git commit -m "CRITICAL FIX: Create user in DB immediately on /start

- User is now created in DB on /start with language=None and department=None
- Language selection handler updates existing user instead of creating new one
- Invite code handler verifies user exists without creating duplicate
- Department selection uses direct assignment + session.refresh() for verification
- Added extensive [START], [LANGUAGE], [INVITE], [DEPT] logging for Railway
- Fixes 'User NOT found in DB! Cannot change language' error"

# 4. Push на Railway (автодеплой)
git push origin main
```

---

## Проверка после деплоя

1. **Сразу после push смотри логи Railway:**
```bash
# Через Railway CLI:
railway logs

# Или в Railway Dashboard -> Deployments -> View logs
```

2. **Проверь запуск бота:**
```
[CONFIG] Database path: /app/persist/uqsoft.db
[CONFIG] Database URL: sqlite+aiosqlite:////app/persist/uqsoft.db
[DATABASE] Creating engine with URL: sqlite+aiosqlite:////app/persist/uqsoft.db
[DATABASE] Database path resolved: /app/persist/uqsoft.db
```

3. **Тестируй через Telegram:**
   - Отправь `/start` новым пользователем (не из ADMIN_IDS)
   - Выбери язык
   - Введи инвайт-код
   - Выбери отдел
   - Задай вопрос

4. **Должны увидеть в логах:**
```
[START] ✅ User {telegram_id} CREATED in DB
[LANGUAGE] ✅ SUCCESS: Language persisted correctly in DB
[INVITE] ✅ Invite code correct
[DEPT] ✅ SUCCESS: Department persisted correctly in DB
```

---

## Что НЕ должно происходить после фикса

❌ `User NOT found in DB! Cannot change language.`
❌ `User not found in DB` (в middleware после выбора языка)
❌ Повторный запрос выбора языка после рестарта бота
❌ Потеря выбранного языка/отдела после редеплоя

---

## Если все равно не работает

1. **Проверь что БД создается:**
```bash
railway shell
ls -la /app/persist/
cat /app/persist/uqsoft.db  # Должен быть файл, не пустой
```

2. **Проверь логи SQLAlchemy:**
   - Ищи `CREATE TABLE users` (при первом запуске)
   - Ищи `INSERT INTO users` (при /start)
   - Ищи `UPDATE users SET language` (при выборе языка)

3. **Если БД все равно пустая:**
   - Убедись что `/app/persist` - это правильный mount path в Railway
   - Проверь что `DATABASE_PATH` установлен правильно в env variables

---

## Файлы изменены:
1. `app/bot/handlers/start.py` - Создание user при /start, обновление при выборе языка/инвайт-кода
2. `app/utils/department.py` - Рефакторинг `set_user_department()` с проверкой

## Время деплоя: ~2-3 минуты
## Даунтайм: 0 (Rolling deployment)

🚀 **КРИТИЧНО: Пушьте сейчас! Этот фикс решает основную проблему регистрации.**
