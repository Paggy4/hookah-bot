import os
import asyncio
import logging
import traceback
import json
from datetime import datetime
from threading import Thread

from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CallbackQueryHandler, ContextTypes
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

# Flask app
flask_app = Flask(__name__)

# Telegram app (global)
tg_app = None

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

# ─── Flask endpoints ───────────────────────────────────────────

@flask_app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "bot": "hookah-master"})

@flask_app.route("/add_post", methods=["POST"])
def add_post():
    """Добавить пост в очередь публикации"""
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
        ws.append_row([
            next_id,
            text,
            "pending",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            ""
        ])
        logger.info(f"Пост {next_id} добавлен в очередь")
        return jsonify({"status": "ok", "post_id": next_id, "message": "Пост добавлен. Бот пришлёт на подтверждение через ~60 сек."})
    except Exception as e:
        logger.error(f"Ошибка add_post: {e}")
        return jsonify({"error": str(e)}), 500

@flask_app.route("/add_session", methods=["POST"])
def add_session():
    """Записать сессию"""
    if not check_auth(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    try:
        ws = get_sheet(SESSIONS_SHEET_ID)
        rows = ws.get_all_values()
        next_id = f"S{len(rows):03d}"
        ws.append_row([
            next_id,
            data.get("date", datetime.now().strftime("%Y-%m-%d")),
            data.get("mix_id", ""),
            data.get("hookah", ""),
            data.get("bowl", ""),
            data.get("hmd", ""),
            data.get("coals", ""),
            data.get("coals_count", ""),
            data.get("heat_time", ""),
            data.get("duration", ""),
            data.get("draft", ""),
            data.get("smoke", ""),
            data.get("taste", ""),
            data.get("rating", ""),
            data.get("tg_post", ""),
            data.get("notes", "")
        ])
        return jsonify({"status": "ok", "session_id": next_id})
    except Exception as e:
        logger.error(f"Ошибка add_session: {e}")
        return jsonify({"error": str(e)}), 500

@flask_app.route("/update_tobacco", methods=["POST"])
def update_tobacco():
    """Обновить остаток табака по ID"""
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
                return jsonify({"status": "ok", "updated": tobacco_id, "remainder": remainder})
        return jsonify({"error": f"Табак {tobacco_id} не найден"}), 404
    except Exception as e:
        logger.error(f"Ошибка update_tobacco: {e}")
        return jsonify({"error": str(e)}), 500

@flask_app.route("/add_mix", methods=["POST"])
def add_mix():
    """Добавить новый микс"""
    if not check_auth(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    try:
        ws = get_sheet(MIXES_SHEET_ID)
        rows = ws.get_all_values()
        next_id = f"M{len(rows):03d}"
        ws.append_row([
            next_id,
            data.get("name", ""),
            data.get("t1_id", ""), data.get("t1_pct", ""),
            data.get("t2_id", ""), data.get("t2_pct", ""),
            data.get("t3_id", ""), data.get("t3_pct", ""),
            data.get("t4_id", ""), data.get("t4_pct", ""),
            data.get("rating", ""),
            data.get("tags", ""),
            data.get("description", "")
        ])
        return jsonify({"status": "ok", "mix_id": next_id})
    except Exception as e:
        logger.error(f"Ошибка add_mix: {e}")
        return jsonify({"error": str(e)}), 500

# ─── Telegram polling ──────────────────────────────────────────

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
                        chat_id=ADMIN_CHAT_ID,
                        text=preview,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                    ws.update_cell(i, 3, "waiting_approval")
                    ws.update_cell(i, 5, str(msg.message_id))
                    logger.info(f"Пост {post_id} отправлен на подтверждение")
        except Exception as e:
            logger.error(f"Ошибка check_new_posts: {e}\n{traceback.format_exc()}")
        await asyncio.sleep(CHECK_INTERVAL)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, row_str = query.data.split(":")
    row = int(row_str)
    try:
        ws = get_sheet(SHEETS_ID)
        row_data = ws.row_values(row)
        post_text = row_data[1] if len(row_data) > 1 else ""
        if action == "pub":
            await context.bot.send_message(chat_id=CHANNEL_ID, text=post_text)
            ws.update_cell(row, 3, "published")
            await query.edit_message_text("✅ *Опубликовано в @sravugli!*", parse_mode="Markdown")
        elif action == "rej":
            ws.update_cell(row, 3, "rejected")
            await query.edit_message_text("❌ *Пост отклонён*", parse_mode="Markdown")
        elif action == "edit":
            ws.update_cell(row, 3, "editing")
            await query.edit_message_text(
                f"✏️ *На редактировании*\n\n[Открыть таблицу](https://docs.google.com/spreadsheets/d/{SHEETS_ID})",
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Ошибка button_handler: {e}")
        await query.edit_message_text(f"❌ Ошибка: {e}")

async def post_init(app):
    asyncio.create_task(check_new_posts(app))

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port, debug=False)

def main():
    # Запускаем Flask в отдельном потоке
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask API запущен")

    # Запускаем Telegram бота
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CallbackQueryHandler(button_handler))
    logger.info("Бот запущен!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
