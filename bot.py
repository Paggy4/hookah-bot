import os
import asyncio
import logging
import traceback
from telegram import Bot, Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CallbackQueryHandler, ContextTypes
import gspread
from google.oauth2.service_account import Credentials
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@sravugli")
ADMIN_CHAT_ID = int(os.environ["ADMIN_CHAT_ID"])
GOOGLE_CREDS_JSON = os.environ["GOOGLE_CREDS_JSON"]
SHEETS_ID = os.environ["SHEETS_ID"]
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))

def get_sheet():
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEETS_ID)
    try:
        ws = sh.worksheet("📤 На публикацию")
    except:
        ws = sh.add_worksheet("📤 На публикацию", rows=1000, cols=5)
        ws.append_row(["ID", "Текст поста", "Статус", "Дата добавления", "Message ID"])
    return ws

async def check_new_posts(app: Application):
    while True:
        try:
            ws = get_sheet()
            rows = ws.get_all_records()
            for i, row in enumerate(rows, start=2):
                if row.get("Статус") == "pending" and row.get("Текст поста"):
                    post_text = row["Текст поста"]
                    post_id = row.get("ID", f"P{i}")
                    keyboard = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("✅ Опубликовать", callback_data=f"pub:{i}"),
                            InlineKeyboardButton("❌ Отклонить", callback_data=f"rej:{i}"),
                        ],
                        [InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit:{i}")]
                    ])
                    preview = f"📝 *Новый пост для @sravugli*\n\n{post_text[:800]}{'...' if len(post_text) > 800 else ''}"
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
            logger.error(f"Ошибка при проверке постов: {e}\n{traceback.format_exc()}")
        await asyncio.sleep(CHECK_INTERVAL)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, row_str = query.data.split(":")
    row = int(row_str)
    try:
        ws = get_sheet()
        row_data = ws.row_values(row)
        post_text = row_data[1] if len(row_data) > 1 else ""
        if action == "pub":
            await context.bot.send_message(chat_id=CHANNEL_ID, text=post_text, parse_mode="HTML")
            ws.update_cell(row, 3, "published")
            await query.edit_message_text(f"✅ *Опубликовано в {CHANNEL_ID}*", parse_mode="Markdown")
        elif action == "rej":
            ws.update_cell(row, 3, "rejected")
            await query.edit_message_text("❌ *Пост отклонён*", parse_mode="Markdown")
        elif action == "edit":
            ws.update_cell(row, 3, "editing")
            await query.edit_message_text(
                f"✏️ *Отправлен на редактирование*\n\n[Открыть таблицу](https://docs.google.com/spreadsheets/d/{SHEETS_ID})",
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Ошибка кнопки: {e}\n{traceback.format_exc()}")
        await query.edit_message_text(f"❌ Ошибка: {e}")

async def post_init(app: Application):
    asyncio.create_task(check_new_posts(app))

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CallbackQueryHandler(button_handler))
    logger.info("Бот запущен!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
