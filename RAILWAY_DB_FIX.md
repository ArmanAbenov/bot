# 🔧 Исправление БД и Middleware для Railway

## 🐛 Проблемы

1. **Бот не запоминает выбор языка** - после перезапуска пользователь снова видит выбор языка
2. **БД теряется при деплое** - данные не сохраняются между перезапусками
3. **Недостаточное логирование** - сложно отследить где происходит сбой

## ✅ Исправления

### 1. **Конфигурация БД для Railway** (`app/core/config.py`)

**Было:**
```python
database_url: str = Field(
    default="sqlite+aiosqlite:///./data/uqsoft.db",
    alias="DATABASE_URL",
)
```

**Стало:**
```python
database_path: str = Field(
    default_factory=lambda: os.getenv(
        "DATABASE_PATH",
        "/app/persist/uqsoft.db" if os.path.exists("/app/persist") else "./data/uqsoft.db"
    ),
    alias="DATABASE_PATH",
)

@property
def database_url(self) -> str:
    """Формирует DATABASE_URL для SQLAlchemy из database_path."""
    # Создаем директорию для БД если её нет
    db_dir = os.path.dirname(self.database_path)
    os.makedirs(db_dir, exist_ok=True)
    
    return f"sqlite+aiosqlite:///{self.database_path}"
```

**Логирование:**
```python
logger.info(f"[CONFIG] Database path: {settings.database_path}")
logger.info(f"[CONFIG] Database URL: {settings.database_url}")
```

**Что это дает:**
- ✅ Автоматическое использование `/app/persist` на Railway (персистентный volume)
- ✅ Fallback на `./data/uqsoft.db` для локальной разработки
- ✅ Автоматическое создание директории для БД
- ✅ Логирование пути к БД при старте

### 2. **Улучшенное логирование в обработчиках языка** (`app/bot/handlers/start.py`)

#### handle_language_selection()
```python
logger.info(f"[LANGUAGE] User {telegram_id} selected language: {selected_lang}")
# После сохранения в БД:
logger.info(f"[LANGUAGE] ✅ Admin user created: {telegram_id} with language={selected_lang}, saved to DB")
logger.info(f"[LANGUAGE] User object: id={user.id}, telegram_id={user.telegram_id}, language={user.language}")
# После очистки FSM:
logger.info(f"[LANGUAGE] FSM cleared for user {telegram_id}")
```

#### handle_invite_code_after_language()
```python
logger.info(f"[INVITE] User {telegram_id} entered invite code: {invite_code}")
logger.info(f"[INVITE] ❌ Wrong invite code for user {telegram_id}: '{invite_code}' (expected: '{settings.invite_code}')")
# После сохранения:
logger.info(f"[INVITE] ✅ New user registered: {telegram_id} ({full_name}) with language={selected_lang}")
logger.info(f"[INVITE] User saved to DB: id={user.id}, telegram_id={user.telegram_id}, language={user.language}, role={user.role}")
```

#### handle_department_selection()
```python
logger.info(f"[DEPT] User {user_id} callback: {data}, lang={lang}")
logger.info(f"[DEPT] ✅ User {user_id} registered to department: {department_code}")
logger.info(f"[DEPT] User language: {lang}, clearing FSM state")
# После очистки FSM:
logger.info(f"[DEPT] FSM state cleared for user {user_id} - registration complete")
```

### 3. **Улучшенное логирование в Middleware**

#### RoleMiddleware (`app/bot/middlewares/role.py`)
```python
if user:
    role = user.role
    user_exists = True
    logger.debug(f"[MIDDLEWARE] User {user_id} found in DB: role={role}, lang={user.language}")
else:
    logger.debug(f"[MIDDLEWARE] User {user_id} NOT found in DB - new user")

# Добавлен флаг user_exists в data
data["user_exists"] = user_exists
```

#### I18nMiddleware (`app/bot/middlewares/i18n.py`)
```python
if language is None:
    logger.info(f"[I18N] User {user_id} not found in DB or language not set, using default: ru")
    return "ru"

logger.debug(f"[I18N] User {user_id} language from DB: {language}")
```

### 4. **Критичные state.clear() вызовы**

Убеждены, что FSM очищается в ВСЕХ точках завершения регистрации:

```python
# После выбора языка (админ):
await state.clear()
logger.info(f"[LANGUAGE] FSM cleared for user {telegram_id}")

# После выбора отдела (пользователь):
await state.clear()
logger.info(f"[DEPT] FSM state cleared for user {user_id} - registration complete")
```

## 📊 Что смотреть в логах Railway

### При старте бота:
```
[CONFIG] Database path: /app/persist/uqsoft.db
[CONFIG] Database URL: sqlite+aiosqlite:////app/persist/uqsoft.db
[INIT_DB] Main admin 375693711 added successfully
[RAG] Creating department-based vector indices...
```

### При регистрации админа:
```
[LANGUAGE] User 375693711 selected language: ru
[LANGUAGE] ✅ Admin user created: 375693711 with language=ru, saved to DB
[LANGUAGE] User object: id=1, telegram_id=375693711, language=ru
[LANGUAGE] FSM cleared for user 375693711
```

### При регистрации пользователя:
```
[LANGUAGE] User 123456789 selected language: en
[INVITE] User 123456789 entered invite code: UQ2026
[INVITE] ✅ New user registered: 123456789 (John Doe) with language=en
[INVITE] User saved to DB: id=2, telegram_id=123456789, language=en, role=employee
[DEPT] User 123456789 callback: dept_registration_sorting, lang=en
[DEPT] ✅ User 123456789 registered to department: sorting
[DEPT] User language: en, clearing FSM state
[DEPT] FSM state cleared for user 123456789 - registration complete
```

### При следующем /start (зарегистрированный пользователь):
```
[MIDDLEWARE] User 123456789 found in DB: role=employee, lang=en
[I18N] User 123456789 language from DB: en
User 123456789 sent /start command
Existing user: 123456789 (John Doe)
Sent welcome message to user 123456789 with role employee and lang en
```

**Если НЕ видите эти логи - значит:**
- ❌ БД не сохраняется (проблема с `/app/persist`)
- ❌ FSM не очищается (пользователь застрял в регистрации)
- ❌ Middleware не подтягивает данные из БД

## 🚀 Переменные окружения для Railway

Добавьте в Railway Dashboard → Variables:

```env
# Путь к БД (Railway автоматически монтирует /app/persist)
DATABASE_PATH=/app/persist/uqsoft.db

# Остальные переменные
BOT_TOKEN=your_bot_token
GEMINI_API_KEY=your_gemini_key
INVITE_CODE=UQ2026
ADMIN_IDS=375693711
```

## 🔍 Диагностика проблем

### Проблема: Язык не сохраняется

**Проверьте в логах:**
```bash
grep "LANGUAGE" railway_logs.txt
```

**Ожидаемый вывод:**
```
[LANGUAGE] User 123 selected language: ru
[LANGUAGE] ✅ Admin user created: 123 with language=ru, saved to DB
[LANGUAGE] FSM cleared for user 123
```

**Если нет "saved to DB"** → ошибка при commit в БД

### Проблема: БД теряется при перезапуске

**Проверьте путь к БД:**
```bash
grep "CONFIG" railway_logs.txt
```

**Ожидаемый вывод:**
```
[CONFIG] Database path: /app/persist/uqsoft.db
```

**Если видите `./data/uqsoft.db`** → Railway не смонтировал `/app/persist`

**Решение:**
1. Railway Dashboard → Settings → Volumes
2. Добавьте volume: `/app/persist`
3. Redeploy

### Проблема: Пользователь застрял в регистрации

**Проверьте FSM:**
```bash
grep "FSM" railway_logs.txt
```

**Должны видеть:**
```
[DEPT] FSM state cleared for user 123 - registration complete
```

**Если не видите** → `state.clear()` не вызывается

## 📝 Команды для коммита

```powershell
# Добавьте все изменения
git add app/core/config.py app/bot/handlers/start.py app/bot/middlewares/role.py app/bot/middlewares/i18n.py

# Коммит с описанием всех фиксов
git commit -m "Fix: Database persistence and language saving on Railway

Critical fixes:
- Use /app/persist for Railway database persistence
- Auto-create database directory
- Add comprehensive logging to language/invite handlers
- Add logging to middlewares (role, i18n)
- Ensure state.clear() called after registration
- Add user_exists flag to middleware data

Railway logs will now show:
- [CONFIG] Database path and URL
- [LANGUAGE] Language selection and save
- [INVITE] Invite code validation
- [DEPT] Department selection
- [MIDDLEWARE] User lookup results
- [I18N] Language retrieval from DB"

# Push на GitHub (Railway автоматически задеплоит)
git push origin main
```

## ✅ Финальный чеклист

После деплоя проверьте:

- [ ] В логах видно `[CONFIG] Database path: /app/persist/uqsoft.db`
- [ ] При выборе языка видно `[LANGUAGE] ✅ Admin user created`
- [ ] После регистрации видно `[DEPT] FSM state cleared`
- [ ] При повторном /start НЕТ выбора языка
- [ ] В логах видно `[MIDDLEWARE] User X found in DB`
- [ ] В логах видно `[I18N] User X language from DB: ru`

## 🆘 Если проблемы остались

**Добавьте в Railway временно:**
```env
LOG_LEVEL=DEBUG
```

Это включит все DEBUG логи (включая middleware).

**Экспортируйте полные логи:**
```bash
railway logs > full_logs.txt
```

И пришлите мне фрагмент с регистрацией пользователя.
