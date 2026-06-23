import os
import asyncio
import logging
import traceback
import json
from datetime import datetime
from threading import Thread

import httpx
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters, CommandHandler
import gspread
from google.oauth2.service_account import Credentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@sravugli")
ADMIN_CHAT_ID = int(os.environ["ADMIN_CHAT_ID"])
GOOGLE_CREDS_JSON = os.environ["GOOGLE_CREDS_JSON"]
SHEETS_ID = os.environ["SHEETS_ID"]
TABAKI_SHEET_ID = os.environ.get("TABAKI_SHEET_ID", "1VzCIqTP83rHaAa2LURq29yLbR-1R6PTn6_Wp1v6b4hc")
MIXES_SHEET_ID = os.environ.get("MIXES_SHEET_ID", "1q8Gw8l1BpK1Fuwal0HdLSdRTR5cCdtwaT8Ov4G8AWG0")
SESSIONS_SHEET_ID = os.environ.get("SESSIONS_SHEET_ID", "1N0w4iAhWtRF5h_19LfQBLhTW3dpr3Rp5uwyIXwLIAOU")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))
API_SECRET = os.environ.get("API_SECRET", "hookah2024secret")
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

SYSTEM_PROMPT = """Ты — кальянный ассистент. Пишешь посты для Telegram канала @sravugli в живом стиле от первого лица.

СТИЛЬ:
- От первого лица ("я поставил", "первые затяжки удивили")
- Живой язык, атмосфера момента
- Эмодзи умеренно: 🌿 🔥 💨 ⚗️ 🪨 ⏱
- Длина 150-300 слов
- Хэштеги в конце

СТРУКТУРА ПОСТА ПРО СЕССИЮ:
1. Зацепка / атмосфера (1-2 предложения)
2. Состав микса + оборудование (компактно)
3. Как шла сессия — начало / пик / конец
4. Финальный вывод + оценка
5. Хэштеги: #кальян #сессия + бренды + #sravugli

Пиши ТОЛЬКО текст поста, без вступлений и объяснений."""

flask_app = Flask(__name__)
CORS(flask_app)

def get_gc():
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds)

def get_sheet(sheet_id, worksheet_index=0):
    gc = get_gc()
    sh = gc.open_by_key(sheet_id)
    return sh.get_worksheet(worksheet_index)

def check_auth(req):
    secret = req.headers.get("X-API-Secret") or req.json.get("secret", "")
    return secret == API_SECRET

async def generate_post(description: str) -> str:
    """Вызываем Claude API для генерации поста"""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 1000,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": f"Напиши пост про сессию: {description}"}]
            },
            timeout=30
        )
        data = r.json()
        return data["content"][0]["text"]

async def save_post_to_sheet(text: str) -> str:
    """Сохраняем пост в таблицу"""
    ws = get_sheet(SHEETS_ID)
    rows = ws.get_all_values()
    next_id = f"P{len(rows):03d}"
    ws.append_row([next_id, text, "pending", datetime.now().strftime("%Y-%m-%d %H:%M"), ""])
    return next_id

# ─── Flask endpoints ───────────────────────────────────────────

@flask_app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "bot": "hookah-master"})

@flask_app.route("/add_post", methods=["POST"])
def add_post():
    if not check_auth(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400
    try:
        ws = get_sheet(SHEETS_ID)
        rows = ws.get_all_values()
        next_id = f"P{len(rows):03d}"
        ws.append_row([next_id, text, "pending", datetime.now().strftime("%Y-%m-%d %H:%M"), ""])
        return jsonify({"status": "ok", "post_id": next_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@flask_app.route("/add_session", methods=["POST"])
def add_session():
    if not check_auth(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    try:
        ws = get_sheet(SESSIONS_SHEET_ID)
        rows = ws.get_all_values()
        next_id = f"S{len(rows):03d}"
        ws.append_row([next_id, data.get("date", datetime.now().strftime("%Y-%m-%d")),
            data.get("mix_id",""), data.get("hookah",""), data.get("bowl",""),
            data.get("hmd",""), data.get("coals",""), data.get("coals_count",""),
            data.get("heat_time",""), data.get("duration",""), data.get("draft",""),
            data.get("smoke",""), data.get("taste",""), data.get("rating",""),
            data.get("tg_post",""), data.get("notes","")])
        return jsonify({"status": "ok", "session_id": next_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@flask_app.route("/update_tobacco", methods=["POST"])
def update_tobacco():
    if not check_auth(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    tobacco_id = data.get("id", "").upper()
    remainder = data.get("remainder", "")
    try:
        ws = get_sheet(TABAKI_SHEET_ID)
        rows = ws.get_all_values()
        for i, row in enumerate(rows, start=1):
            if row and row[0].upper() == tobacco_id:
                ws.update_cell(i, 8, remainder)
                return jsonify({"status": "ok", "updated": tobacco_id})
        return jsonify({"error": f"Табак {tobacco_id} не найден"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─── Telegram handlers ─────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 *Кальянный мастер*\n\n"
        "Команды:\n"
        "*/пост* [описание] — написать пост про сессию\n"
        "*/помощь* — справка\n\n"
        "Пример:\n"
        "`/пост догма орбикидз + element wildberry, lotus, 3 угля кокоурт, грел 12 мин, тяга отличная, 80 мин, оценка 9`",
        parse_mode="Markdown"
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *Как пользоваться:*\n\n"
        "1. Напиши */пост* и опиши сессию в свободной форме\n"
        "2. Бот сгенерирует пост через Claude AI\n"
        "3. Нажми ✅ чтобы опубликовать в @sravugli\n"
        "4. Или ❌ чтобы отклонить\n\n"
        "Описание может быть любым — что курил, угли, время, ощущения, оценка.",
        parse_mode="Markdown"
    )

async def cmd_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Генерируем пост через Claude и отправляем на подтверждение"""
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    description = " ".join(context.args)
    if not description:
        await update.message.reply_text(
            "Напиши описание сессии после команды.\n\n"
            "Пример: `/пост догма орбикидз, lotus, 3 кокоурт, 12 мин нагрев, 80 мин, оценка 9`",
            parse_mode="Markdown"
        )
        return

    msg = await update.message.reply_text("⏳ Генерирую пост...")

    try:
        post_text = await generate_post(description)
        post_id = await asyncio.get_event_loop().run_in_executor(None, lambda: asyncio.run(save_post_to_sheet(post_text)))

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Опубликовать", callback_data=f"direct_pub:{post_text[:100]}"),
                InlineKeyboardButton("❌ Отклонить", callback_data="direct_rej"),
            ]
        ])

        await msg.edit_text(
            f"📝 *Готовый пост:*\n\n{post_text}",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка cmd_post: {e}\n{traceback.format_exc()}")
        await msg.edit_text(f"❌ Ошибка генерации: {e}")

async def check_new_posts(app):
    while True:
        try:
            ws = get_sheet(SHEETS_ID)
            rows = ws.get_all_records()
            for i, row in enumerate(rows, start=2):
                if row.get("Статус") == "pending" and row.get("Текст поста"):
                    post_text = str(row["Текст поста"])
                    post_id = row.get("ID", f"P{i}")
                    keyboard = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("✅ Опубликовать", callback_data=f"pub:{i}"),
                            InlineKeyboardButton("❌ Отклонить", callback_data=f"rej:{i}"),
                        ],
                        [InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit:{i}")]
                    ])
                    preview = f"📝 *Новый пост для @sravugli*\n\n{post_text[:800]}"
                    msg = await app.bot.send_message(
                        chat_id=ADMIN_CHAT_ID, text=preview,
                        reply_markup=keyboard, parse_mode="Markdown"
                    )
                    ws.update_cell(i, 3, "waiting_approval")
                    ws.update_cell(i, 5, str(msg.message_id))
        except Exception as e:
            logger.error(f"Ошибка check_new_posts: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("direct_pub:"):
        # Публикуем напрямую (из /пост команды)
        try:
            ws = get_sheet(SHEETS_ID)
            rows = ws.get_all_records()
            # Берём последний pending пост
            post_text = None
            row_idx = None
            for i, row in enumerate(rows, start=2):
                if row.get("Статус") in ["pending", "waiting_approval"]:
                    post_text = str(row["Текст поста"])
                    row_idx = i
            if post_text:
                await context.bot.send_message(chat_id=CHANNEL_ID, text=post_text)
                if row_idx:
                    ws.update_cell(row_idx, 3, "published")
                await query.edit_message_text("✅ *Опубликовано в @sravugli!*", parse_mode="Markdown")
            else:
                await query.edit_message_text("❌ Пост не найден в таблице")
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}")

    elif data == "direct_rej":
        await query.edit_message_text("❌ *Пост отклонён*", parse_mode="Markdown")

    elif data.startswith("pub:"):
        row = int(data.split(":")[1])
        try:
            ws = get_sheet(SHEETS_ID)
            row_data = ws.row_values(row)
            post_text = row_data[1] if len(row_data) > 1 else ""
            await context.bot.send_message(chat_id=CHANNEL_ID, text=post_text)
            ws.update_cell(row, 3, "published")
            await query.edit_message_text("✅ *Опубликовано в @sravugli!*", parse_mode="Markdown")
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}")

    elif data.startswith("rej:"):
        row = int(data.split(":")[1])
        try:
            ws = get_sheet(SHEETS_ID)
            ws.update_cell(row, 3, "rejected")
            await query.edit_message_text("❌ *Пост отклонён*", parse_mode="Markdown")
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}")

    elif data.startswith("edit:"):
        row = int(data.split(":")[1])
        try:
            ws = get_sheet(SHEETS_ID)
            ws.update_cell(row, 3, "editing")
            await query.edit_message_text(
                f"✏️ *На редактировании*\n\n[Открыть таблицу](https://docs.google.com/spreadsheets/d/{SHEETS_ID})",
                parse_mode="Markdown"
            )
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}")

async def post_init(app):
    asyncio.create_task(check_new_posts(app))

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port, debug=False)

def main():
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask API запущен")

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("помощь", cmd_help))
    app.add_handler(CommandHandler("пост", cmd_post))
    app.add_handler(CallbackQueryHandler(button_handler))
    logger.info("Бот запущен!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
