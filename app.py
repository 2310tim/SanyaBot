import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("Токен не найден")

games = {}

# ===== МЕНЮ =====
def main_menu(username):
    keyboard = [
        [InlineKeyboardButton("🤖 Чат с ИИ", callback_data="ai")],
        [InlineKeyboardButton("🎮 Игры", callback_data="games")],
        [InlineKeyboardButton("➕ Добавить бота в чат", url=f"https://t.me/{username}?startgroup=true")],
    ]
    return InlineKeyboardMarkup(keyboard)

def games_menu():
    keyboard = [
        [InlineKeyboardButton("🎲 Кубы", callback_data="cubs_start")],
    ]
    return InlineKeyboardMarkup(keyboard)

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Здравствуйте!\n\nВыберите действие:",
        reply_markup=main_menu(context.bot.username)
    )

# ===== CALLBACK =====
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    print(f"CALLBACK: {query.data}")
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if data == "ai":
        await query.edit_message_text("🤖 Режим ИИ.\n\n(Функция в разработке)")

    elif data == "games":
        if update.effective_chat.type == "private":
            await query.edit_message_text(
                "❌ Игры доступны только в чате!\n\nДобавь бота в чат.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Добавить бота в чат", url=f"https://t.me/{context.bot.username}?startgroup=true")]
                ])
            )
        else:
            await query.edit_message_text("🎮 Выберите игру:", reply_markup=games_menu())

    elif data == "cubs_start":
        await query.edit_message_text(
            "🎲 Напишите /cubs в ответ на сообщение человека, чтобы вызвать его.\n"
            "Или просто /cubs, чтобы вызвать всех в чате."
        )

    elif data.startswith("cubs_accept_"):
        parts = data.split("_")
        challenger = int(parts[2])
        target = int(parts[3])
        if target != 0 and user_id != target:
            await query.answer("Этот вызов не для тебя.", show_alert=True)
            return
        if user_id == challenger:
            await query.answer("Нельзя играть с самим собой.", show_alert=True)
            return

        await query.edit_message_text(
            f"🎲 Дуэль кубов!\n\n{query.from_user.first_name}, кидай кубик!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎲 Кинуть кубик", callback_data=f"cubs_roll_{challenger}_{user_id}")]
            ])
        )

    elif data.startswith("cubs_roll_"):
        parts = data.split("_")
        challenger = int(parts[2])
        opponent = int(parts[3])

        if user_id not in [challenger, opponent]:
            await query.answer("Ты не участник этой игры.", show_alert=True)
            return

        # Отправляем кубик от имени бота
        dice_msg = await context.bot.send_dice(chat_id=chat_id, emoji="🎲")
        value = dice_msg.dice.value

        # Сохраняем результат
        if "cubs_results" not in games:
            games["cubs_results"] = {}

        games["cubs_results"][user_id] = value

        # Проверяем, оба ли кинули
        if challenger in games["cubs_results"] and opponent in games["cubs_results"]:
            v1 = games["cubs_results"][challenger]
            v2 = games["cubs_results"][opponent]
            if v1 > v2:
                result = "🏆 Победил первый игрок!"
            elif v2 > v1:
                result = "🏆 Победил второй игрок!"
            else:
                result = "🤝 Ничья!"
            await context.bot.send_message(
                chat_id,
                f"🎲 Результаты:\nИгрок 1: {v1}\nИгрок 2: {v2}\n\n{result}"
            )
            del games["cubs_results"]
        else:
            await context.bot.send_message(
                chat_id,
                f"🎲 Выпало: {value}\n\nЖдём второго игрока..."
            )

# ===== КОМАНДЫ =====
async def cubs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "❌ Игры доступны только в чате!\n\nДобавь бота в чат.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Добавить бота в чат", url=f"https://t.me/{context.bot.username}?startgroup=true")]
            ])
        )
        return
    user_id = update.effective_user.id
    message = update.message
    if message.reply_to_message:
        opponent = message.reply_to_message.from_user
        if opponent.id == user_id:
            await message.reply_text("Нельзя играть с самим собой.")
            return
        await message.reply_text(
            f"🎲 {message.from_user.first_name} вызывает {opponent.first_name} на дуэль кубов!\n\n{opponent.first_name}, принимаешь вызов?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Принять", callback_data=f"cubs_accept_{user_id}_{opponent.id}")]
            ])
        )
    else:
        await message.reply_text(
            f"🎲 {message.from_user.first_name} вызывает всех на дуэль кубов!\n\nКто примет вызов?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Принять", callback_data=f"cubs_accept_{user_id}_0")]
            ])
        )

async def text_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if text in ["кубы", "кубики"]:
        await cubs_command(update, context)

# ===== ЗАПУСК (WEBHOOK) =====
def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cubs", cubs_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_commands))

    PORT = int(os.environ.get("PORT", 8443))
    WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://sanyabot-gdx4.onrender.com")

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="/webhook",
        webhook_url=f"{WEBHOOK_URL}/webhook",
        drop_pending_updates=True,
    )

if __name__ == "__main__":
    main()
