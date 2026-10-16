import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    referral_id = None

    if args and args[0].startswith("ref_"):
        try:
            referral_id = int(args[0][4:])
            if referral_id <= 0:
                referral_id = None
        except ValueError:
            referral_id = None

    if not WEBAPP_URL.startswith("https://"):
        await update.effective_message.reply_text(
            "Игра ещё настраивается. Администратору нужно задать WEBAPP_URL (HTTPS)."
        )
        return

    keyboard = [[
        InlineKeyboardButton(
            "🦁 Открыть ЗооМагнат",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )
    ]]

    message = (
        "Добро пожаловать в «ЗооМагнат»!\n\n"
        "Развивай зоопарк, покупай животных и зарабатывай игровые монеты. "
        "На первом этапе монеты игровые и не обмениваются на реальные деньги."
    )

    if referral_id is not None:
        message += "\n\n🎁 Ты перешёл по приглашению в ЗооМагнат!"

    await update.effective_message.reply_text(
        message,
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
