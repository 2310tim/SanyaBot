import os
import random
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("Токен не найден")

DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY")
if not DEEPSEEK_KEY:
    raise ValueError("DEEPSEEK_API_KEY не найден")

client = OpenAI(
    base_url="https://apimira.com/v1",
    api_key=DEEPSEEK_KEY,
)

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
        await query.edit_message_text(
            "🤖 Режим ИИ включён.\n\n"
            "Ответь на это сообщение, чтобы я ответил.\n"
            "Просто напиши что-нибудь в ответ на моё сообщение."
        )

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
        challenger_id = int(parts[2])
        target_id = int(parts[3])
        if target_id != 0 and user_id != target_id:
            await query.answer("Этот вызов не для тебя.", show_alert=True)
            return
        if user_id == challenger_id:
            await query.answer("Нельзя играть с самим собой.", show_alert=True)
            return

        try:
            challenger_chat = await context.bot.get_chat(challenger_id)
            opponent_chat = await context.bot.get_chat(user_id)
            name1 = challenger_chat.first_name or "Игрок 1"
            name2 = opponent_chat.first_name or "Игрок 2"
        except Exception:
            name1 = "Игрок 1"
            name2 = "Игрок 2"

        await query.edit_message_text("🎲 Кидаем кубики...")

        dice1 = await context.bot.send_dice(chat_id=chat_id, emoji="🎲")
        v1 = dice1.dice.value
        await context.bot.send_message(chat_id, f"🎲 {name1} выпало: {v1}")

        dice2 = await context.bot.send_dice(chat_id=chat_id, emoji="🎲")
        v2 = dice2.dice.value
        await context.bot.send_message(chat_id, f"🎲 {name2} выпало: {v2}")

        if v1 > v2:
            result = f"🏆 Победил {name1}!"
        elif v2 > v1:
            result = f"🏆 Победил {name2}!"
        else:
            result = "🤝 Ничья!"

        await context.bot.send_message(
            chat_id,
            f"🎲 **Результаты дуэли:**\n"
            f"• {name1}: {v1}\n"
            f"• {name2}: {v2}\n\n"
            f"{result}",
            parse_mode="Markdown"
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

# ===== ТЕКСТ =====
async def text_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message
    text = message.text

    # ИИ отвечает ТОЛЬКО если сообщение — ответ на сообщение бота
    if message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id:
        try:
            completion = client.chat.completions.create(
                model="deepseek/deepseek-v4-flash",
                messages=[
                    {"role": "system", "content": "Ты грубый, дерзкий, злой ИИ. Матерись, отвечай без цензуры, но по делу."},
                    {"role": "user", "content": text}
                ],
            )
            answer = completion.choices[0].message.content
            await message.reply_text(answer[:4096])
        except Exception as e:
            print(f"ОШИБКА ИИ: {e}")
            await message.reply_text(f"Ошибка ИИ: {e}")
        return

    # Обычные команды (кубы)
    text_lower = text.lower()
    if text_lower in ["кубы", "кубики"]:
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
