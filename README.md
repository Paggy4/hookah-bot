# Hookah Master Bot

Бот для публикации постов в Telegram канал @sravugli.

## Как работает
1. Клод пишет пост в Google Sheets (лист "На публикацию", статус "pending")
2. Бот каждые 60 сек проверяет таблицу
3. Присылает тебе пост с кнопками ✅ ❌ ✏️
4. Жмёшь ✅ → пост летит в канал

## Деплой на Railway

1. Загрузи этот код на GitHub
2. Зайди на railway.app → New Project → Deploy from GitHub
3. Добавь переменные окружения (Variables):
   - BOT_TOKEN
   - CHANNEL_ID
   - ADMIN_CHAT_ID
   - GOOGLE_CREDS_JSON
   - SHEETS_ID
