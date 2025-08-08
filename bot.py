import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

# ---- ENV ----
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TODOIST_TOKEN = os.getenv("TODOIST_TOKEN")
TODOIST_PROJECT_ID = os.getenv("TODOIST_PROJECT_ID")  # optional
BASE_URL = os.getenv("BASE_URL")  # e.g. https://yourapp.onrender.com

TODOIST_API_URL = "https://api.todoist.com/rest/v2/tasks"


# ---- Todoist helpers ----
def build_todoist_payload(text: str) -> dict:
    """
    Rules:
      - "Title >> description" -> description field
      - "due:today|tomorrow|monday|2025-08-10" -> due_string
      - "!p1..p4" -> priority (4 is highest in Todoist)
      - TODOIST_PROJECT_ID -> to a specific project, else Inbox
    """
    text = (text or "").strip()
    payload = {"content": text[:1000] or "Нове завдання"}

    # Split Title >> Description
    if ">>" in text:
        title, desc = text.split(">>", 1)
        payload["content"] = (title.strip() or "Нове завдання")[:1000]
        if desc.strip():
            payload["description"] = desc.strip()

    lower = text.lower()

    # due:...
    if "due:" in lower:
        try:
            due_part = lower.split("due:", 1)[1].split()[0]
            if due_part:
                payload["due_string"] = due_part
        except Exception:
            pass

    # priority !p4.. !p1
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
        "X-Request-Id": os.urandom(16).hex(),  # idempotency
    }
    payload = build_todoist_payload(text)
    try:
        r = requests.post(TODOIST_API_URL, headers=headers, json=payload, timeout=10)
        if r.status_code in (200, 204):
            return True, "Завдання створено."
        if r.status_code == 409:
            return True, "Вже створено (ідемпотентний запит)."
        return False, f"Помилка Todoist: {r.status_code} {r.text}"
    except Exception as e:
        return False, f"Помилка мережі: {e}"


# ---- Telegram handlers ----
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Надішліть або перешліть мені повідомлення — я створю задачу в Todoist.\n\n"
        "Швидкі правила:\n"
        "• 'Назва >> опис' — опис піде в Description.\n"
        "• 'due:today' або 'due:tomorrow' — дедлайн через due_string.\n"
        "• '!p1..p4' — пріоритет (4 найвищий)."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message

    # take caption first (for media), else text
    text = (msg.caption or msg.text or "").strip()

    # add info if forwarded
    if msg.forward_date:
        from_hint = []
        if msg.forward_from_chat:
            from_hint.append(
                f"from chat: {msg.forward_from_chat.title or msg.forward_from_chat.username}"
            )
        if msg.forward_from:
            from_hint.append(
                f"from user: @{msg.forward_from.username or msg.forward_from.full_name}"
            )
        if from_hint:
            hint = " | ".join(from_hint)
            text = (text + f"\n\n>> Forwarded: {hint}").strip()

    if not text:
        await msg.reply_text("Немає тексту/підпису, який можна перетворити на задачу.")
        return

    ok, info = create_todoist_task(text)
    await msg.reply_text(info)


def main():
    if not TELEGRAM_BOT_TOKEN or not TODOIST_TOKEN:
        raise RuntimeError("Не задані змінні TELEGRAM_BOT_TOKEN / TODOIST_TOKEN.")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.ALL & (~filters.COMMAND), handle_message))

    port = int(os.getenv("PORT", "8080"))
    on_render = os.getenv("PORT") is not None  # Render ставить PORT

    if on_render:
        # → режим webhook на Render
        # (опц.) можна гарантовано прибрати старий webhook і поставити новий:
        # але run_webhook з webhook_url це і так робить
     app.run_webhook(
    listen="0.0.0.0",
    port=int(os.getenv("PORT", "8080")),
    webhook_url=f"{BASE_URL}/webhook",
    url_path="webhook",             # ← ДОДАЛИ ЦЕ
    drop_pending_updates=True,
    allowed_updates=Update.ALL_TYPES,
        )
    else:
        # → локальний режим polling: спершу знімаємо webhook, щоб не було 409
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            app.bot.delete_webhook(drop_pending_updates=True)
        )
        app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
