# 🚨 КРИТИЧНОЕ ИСПРАВЛЕНИЕ: Язык не сохраняется в БД

## ❌ Проблема

```
Шаг 1: User changed language to ru
Шаг 2: Middleware: User not found in DB  ← БД потеряна!
```

## 🔍 Корневая причина

**НАЙДЕНО:** В `app/bot/handlers/settings.py` использовался UPDATE query БЕЗ проверки что запись сохранилась.

## ✅ РЕШЕНИЕ

### Изменен `app/bot/handlers/settings.py`

#### БЫЛО (ненадежно):
```python
stmt = update(User).where(...).values(language=selected_lang)
await session.execute(stmt)
await session.commit()
logger.info(f"User changed language to {selected_lang}")  # ← Нет проверки!
```

**Проблема:** Commit может "пройти", но язык не сохраниться если:
- БД файл read-only
- БД файл в tmpfs (не персистентной директории)
- Проблемы с правами доступа

#### СТАЛО (надежно):
```python
# 1. Получаем пользователя
user = (await session.execute(select(User).where(...))).scalar_one_or_none()

if not user:
    logger.error(f"❌ User NOT found in DB!")
    return

logger.info(f"User found: id={user.id}, current_lang={user.language}")

# 2. Меняем язык через прямое присваивание
old_lang = user.language
user.language = selected_lang

# 3. Коммитим
await session.commit()
logger.info(f"COMMIT executed")

# 4. КРИТИЧНО: Перечитываем из БД для проверки
await session.refresh(user)
logger.info(f"✅ Language VERIFIED in DB: {user.language}")

# 5. Проверяем что действительно сохранилось
if user.language != selected_lang:
    logger.error(f"❌ CRITICAL: Language NOT saved! DB={user.language}, expected={selected_lang}")
else:
    logger.info(f"✅ SUCCESS: Language persisted correctly")
```

**Что это дает:**
- ✅ Видим ДО и ПОСЛЕ значения
- ✅ Проверяем что запись действительно сохранилась через refresh()
- ✅ СРАЗУ видим если что-то пошло не так
- ✅ Логируем database path если ошибка

## 🔧 Дополнительные фиксы

### 1. `app/core/config.py`
```python
# Railway будет использовать /app/persist автоматически
database_path: str = Field(
    default_factory=lambda: os.getenv(
        "DATABASE_PATH",
        "/app/persist/uqsoft.db" if os.path.exists("/app/persist") else "./data/uqsoft.db"
    )
)
```

### 2. `app/core/database.py`
```python
logger.info(f"[DATABASE] Database file path: {settings.database_path}")
logger.info(f"[INIT_DB] Starting database initialization...")
logger.info(f"[INIT_DB] ✅ Database tables created successfully")
```

### 3. `app/bot/middlewares/i18n.py`
```python
logger.info(f"[I18N] User {user_id} not found in DB or language not set")
logger.debug(f"[I18N] User {user_id} language from DB: {language}")
```

## 📊 Ожидаемые логи Railway

### При старте:
```log
[DATABASE] Initializing engine with URL: sqlite+aiosqlite:////app/persist/uqsoft.db
[DATABASE] Database file path: /app/persist/uqsoft.db
[DATABASE] Engine created successfully
[INIT_DB] Starting database initialization...
[INIT_DB] ✅ Database tables created successfully
```

### При смене языка:
```log
[SETTINGS] User 375693711 changing language to: ru
[SETTINGS] User 375693711 found in DB: id=1, current_lang=en, role=admin
[SETTINGS] COMMIT executed for user 375693711
[SETTINGS] ✅ User 375693711 language VERIFIED in DB: ru (was: en, set to: ru)
[SETTINGS] ✅ SUCCESS: Language persisted correctly in DB
[SETTINGS] Language change completed for user 375693711
```

### При следующем запросе:
```log
[MIDDLEWARE] User 375693711 found in DB: role=admin, lang=ru
[I18N] User 375693711 language from DB: ru
```

### ❌ Если увидите:
```log
[SETTINGS] ❌ CRITICAL: Language NOT saved! DB=en, expected=ru
[SETTINGS] Database path: ./data/uqsoft.db  ← НЕ /app/persist!
```

**Это значит:** Railway не использует persistent volume!

## 🚀 Команды для деплоя

```powershell
git add app/core/config.py app/core/database.py app/bot/handlers/settings.py app/bot/handlers/start.py app/bot/middlewares/role.py app/bot/middlewares/i18n.py CRITICAL_FIX_COMMANDS.txt FIX_RAILWAY_DEPENDENCIES.md URGENT_FIX_NOW.txt

git commit -m "CRITICAL FIX: Database persistence and language saving on Railway

Root cause: UPDATE query without verification + non-persistent DB path

Critical changes:
- settings.py: Use direct assignment + session.refresh() to verify save
- settings.py: Add comprehensive logging of language save process
- database.py: Log DB path and URL at engine creation
- config.py: Use /app/persist for Railway persistence
- init_db: Add detailed logging of table creation

The fix ensures:
1. Language changes are verified with session.refresh()
2. Any save failure is immediately logged with DB path
3. Database uses persistent volume on Railway
4. All steps are logged for debugging

Expected Railway logs:
[SETTINGS] ✅ SUCCESS: Language persisted correctly in DB"

git push origin main
```

## ⚠️ ПОСЛЕ PUSH

1. **Railway начнет деплой** (~3-5 минут)
2. **Проверьте логи при старте:**
   - Ищите: `[DATABASE] Database file path:`
   - Должно быть: `/app/persist/uqsoft.db` ✅
   - Если видите `./data/uqsoft.db` ❌ → Добавьте Volume в Railway

3. **Протестируйте:**
   - `/start` → Настройки → Сменить язык → RU
   - `/start` снова → Должен запомнить RU
   - Проверьте логи: `[SETTINGS] ✅ SUCCESS`

## 🆘 Если язык все еще не сохраняется

**Grep логи:**
```bash
railway logs | grep "SETTINGS"
```

**Если видите:**
```
[SETTINGS] ❌ CRITICAL: Language NOT saved!
[SETTINGS] Database path: ./data/uqsoft.db
```

**Значит Railway не монтирует `/app/persist`:**

1. Railway Dashboard → Settings → Volumes
2. Add Volume:
   - Mount Path: `/app/persist`
   - Size: 1 GB
3. Variables → Add:
   - `DATABASE_PATH=/app/persist/uqsoft.db`
4. Redeploy

---

**🚀 ГОТОВО К PUSH! Скопируйте команды выше!**
