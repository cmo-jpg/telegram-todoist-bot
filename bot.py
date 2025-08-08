import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TODOIST_TOKEN = os.getenv("TODOIST_TOKEN")
TODOIST_PROJECT_ID = os.getenv("TODOIST_PROJECT_ID")
BASE_URL = os.getenv("BASE_URL")  # типу https://yourapp.onrender.com

TODOIST_API_URL = "https://api.todoist.com/rest/v2/tasks"

def build_todoist_payload(text: str) -> dict:
    payload = {"content": text.strip()[:1000]}
    if ">>" in text:
        title, desc = text.split(">>", 1)
        payload["content"] = title.strip() or "Нове завдання"
        payload["description"] = desc.strip()
    lower = text.lower()
    if "due:" in lower:
        try:
            due_part = lower.split("due:", 1)[1].split()[0]
            payload["due_string"] = due_part
        except:
            pass
    for p in ("!p4", "!p3", "!p2", "!p1"):
        if p in lower:
            payload["priority"] = int(p[-1])
            break
    if TODOIST_PROJECT_ID:
        payload["project_id"] = TODOIST_PROJECT_ID
    return payload

def create_todoist_task(text: str) -> tuple[bool, str]:
    headers = {
        "Authorization": f"Bearer {TODOIST_TOKEN}",
        "Content-Type": "application/json",
        "X-Request-Id": os.urandom(16).hex(),
    }
    r = requests.post(TODOIST_API_URL, headers=headers, json=build_todoist_payload(text), timeout=10)
    if r.status_code in (200, 204):
        return True, "Завдання створено."
    if r.status_code == 409:
        return True, "Вже створено."
    return False, f"Помилка {r.status_code}: {r.text}"

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привіт! Надішли або перешли мені повідомлення — я створю задачу в Todoist.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    text = (msg.caption or msg.text or "").strip()
    if msg.forward_date:
        f_info = []
        if msg.forward_from_chat:
            f_info.append(f"from chat: {msg.forward_from_chat.title or msg.forward_from_chat.username}")
        if msg.forward_from:
            f_info.append(f"from user: @{msg.forward_from.username or msg.forward_from.full_name}")
        if f_info:
            text += f"\n\n>> Forwarded: {' | '.join(f_info)}"
    if not text:
        await msg.reply_text("Немає тексту для задачі.")
        return
    ok, info = create_todoist_task(text)
    await msg.reply_text(info)

async def on_startup(app):
    if BASE_URL:
        await app.bot.set_webhook(url=f"{BASE_URL}/webhook")

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.ALL & (~filters.COMMAND), handle_message))
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        webhook_url=f"{BASE_URL}/webhook",
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
        post_init=on_startup
    )

if __name__ == "__main__":
    main()
