import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not WEBAPP_URL.startswith("https://"):
        await update.effective_message.reply_text(
            "Игра ещё настраивается. Администратору нужно задать WEBAPP_URL (HTTPS)."
        )
        return
    keyboard = [[InlineKeyboardButton("🦁 Открыть ЗооМагнат", web_app=WebAppInfo(url=WEBAPP_URL))]]
    await update.effective_message.reply_text(
        "Добро пожаловать в «ЗооМагнат»!\n\n"
        "Развивай зоопарк, покупай животных и зарабатывай игровые монеты. "
        "На первом этапе монеты игровые и не обмениваются на реальные деньги.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("Бот работает. Команда /start открывает игру.")

def main():
    if not BOT_TOKEN:
        raise RuntimeError("Не задан BOT_TOKEN")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("health", health))
    print("ЗооМагнат: бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
