import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("Токен не найден")

games = {}

# ===== МЕНЮ =====
def main_menu():
    keyboard = [
        [InlineKeyboardButton("🤖 Чат с ИИ", callback_data="ai")],
        [InlineKeyboardButton("🎮 Игры", callback_data="games")],
    ]
    return InlineKeyboardMarkup(keyboard)

def games_menu():
    keyboard = [
        [InlineKeyboardButton("🎲 Кубы", callback_data="cubs_start")],
        [InlineKeyboardButton("❌⭕ Крестики-нолики", callback_data="ttt_start")],
    ]
    return InlineKeyboardMarkup(keyboard)

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Здравствуйте!\n\nВыберите действие:",
        reply_markup=main_menu()
    )

# ===== CALLBACK =====
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if data == "ai":
        await query.edit_message_text(
            "🤖 Режим ИИ. Напишите сообщение, и я отвечу.\n\n(Функция в разработке)"
        )

    elif data == "games":
        if update.effective_chat.type == "private":
            await query.edit_message_text(
                "❌ Игры доступны только в чате!\n\n"
                "Добавь бота в чат и играй с друзьями.",
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
        import random
        roll1 = random.randint(1, 6)
        roll2 = random.randint(1, 6)
        if roll1 > roll2:
            result = f"🏆 Победил {query.from_user.first_name}!"
        elif roll2 > roll1:
            result = f"🏆 Победил {query.from_user.first_name}!"
        else:
            result = "🤝 Ничья!"
        await query.edit_message_text(
            f"🎲 Дуэль кубов!\n\n{query.from_user.first_name}: {roll1}\nСоперник: {roll2}\n\n{result}"
        )

    elif data == "ttt_start":
        await query.edit_message_text(
            "❌⭕ Напишите /tictactoe в ответ на сообщение человека, чтобы вызвать его.\n"
            "Или просто /tictactoe, чтобы вызвать всех в чате."
        )

    elif data.startswith("ttt_accept_"):
        parts = data.split("_")
        challenger = int(parts[2])
        target = int(parts[3])
        if target != 0 and user_id != target:
            await query.answer("Этот вызов не для тебя.", show_alert=True)
            return
        if user_id == challenger:
            await query.answer("Нельзя играть с самим собой.", show_alert=True)
            return

        import random
        game_id = str(random.randint(100000, 999999))
        games[game_id] = {
            "board": [" "] * 9,
            "turn": challenger,
            "player1": challenger,
            "player2": user_id,
            "chat_id": chat_id,
            "message_id": query.message.message_id
        }

        await query.edit_message_text(
            f"❌⭕ Игра началась!\n\nХод {query.from_user.first_name} (❌)",
            reply_markup=ttt_board(game_id)
        )

    elif data.startswith("ttt_move_"):
        parts = data.split("_")
        game_id = parts[2]
        cell = int(parts[3])

        game = games.get(game_id)
        if not game:
            await query.answer("Игра не найдена.", show_alert=True)
            return

        if user_id != game["turn"]:
            await query.answer("Сейчас не твой ход.", show_alert=True)
            return

        if game["board"][cell] != " ":
            await query.answer("Клетка занята.", show_alert=True)
            return

        symbol = "❌" if user_id == game["player1"] else "⭕"
        game["board"][cell] = symbol

        if check_winner(game["board"]):
            await query.edit_message_text(
                f"❌⭕ Игра окончена!\n\nПобедил {query.from_user.first_name}!"
            )
            del games[game_id]
            return

        if " " not in game["board"]:
            await query.edit_message_text("❌⭕ Игра окончена!\n\nНичья!")
            del games[game_id]
            return

        game["turn"] = game["player2"] if game["turn"] == game["player1"] else game["player1"]

        await query.edit_message_reply_markup(reply_markup=ttt_board(game_id))

def ttt_board(game_id):
    game = games.get(game_id)
    if not game:
        return None
    board = game["board"]
    keyboard = []
    row = []
    for i in range(9):
        cell = board[i] if board[i] != " " else "⬜"
        row.append(InlineKeyboardButton(cell, callback_data=f"ttt_move_{game_id}_{i}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    return InlineKeyboardMarkup(keyboard)

def check_winner(board):
    wins = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]
    for combo in wins:
        if board[combo[0]] == board[combo[1]] == board[combo[2]] != " ":
            return True
    return False

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

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    message = update.message

    if message.reply_to_message:
        opponent = message.reply_to_message.from_user
        if opponent.id == user_id:
            await message.reply_text("Нельзя играть с самим собой.")
            return
        await message.reply_text(
            f"🎲 {message.from_user.first_name} вызывает {opponent.first_name} на дуэль кубов!\n\n"
            f"{opponent.first_name}, принимаешь вызов?",
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

async def tictactoe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "❌ Игры доступны только в чате!\n\nДобавь бота в чат.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Добавить бота в чат", url=f"https://t.me/{context.bot.username}?startgroup=true")]
            ])
        )
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    message = update.message

    if message.reply_to_message:
        opponent = message.reply_to_message.from_user
        if opponent.id == user_id:
            await message.reply_text("Нельзя играть с самим собой.")
            return
        await message.reply_text(
            f"❌⭕ {message.from_user.first_name} вызывает {opponent.first_name} на крестики-нолики!\n\n"
            f"{opponent.first_name}, принимаешь вызов?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Принять", callback_data=f"ttt_accept_{user_id}_{opponent.id}")]
            ])
        )
    else:
        await message.reply_text(
            f"❌⭕ {message.from_user.first_name} вызывает всех на крестики-нолики!\n\nКто примет вызов?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Принять", callback_data=f"ttt_accept_{user_id}_0")]
            ])
        )

# ===== ТЕКСТ БЕЗ СЛЭША =====
async def text_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if text in ["кубы", "кубики"]:
        await cubs_command(update, context)
    elif text in ["крестики", "нолики", "крестики-нолики"]:
        await tictactoe_command(update, context)

# ===== ЗАПУСК (WEBHOOK) =====
def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cubs", cubs_command))
    application.add_handler(CommandHandler("tictactoe", tictactoe_command))
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
