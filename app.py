import os
import random
import threading
from flask import Flask
import telebot
from telebot import types

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("Токен не найден")

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running"

@app.route('/health')
def health():
    return "OK", 200

bot = telebot.TeleBot(TOKEN)

# ===== ХРАНИЛИЩЕ ИГР =====
games = {}

# ===== ГЛАВНОЕ МЕНЮ =====
def main_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🤖 Чат с ИИ", callback_data="ai"),
        types.InlineKeyboardButton("🎮 Игры", callback_data="games"),
        types.InlineKeyboardButton(
            "➕ Добавить бота в чат",
            url=f"https://t.me/{bot.get_me().username}?startgroup=true"
        )
    )
    return markup

# ===== /start =====
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "👋 Здравствуйте!\n\nВыберите действие:",
        reply_markup=main_menu()
    )

# ===== КУБЫ =====
@bot.message_handler(commands=['cubs', 'кубики'])
def cubs_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if message.reply_to_message:
        opponent = message.reply_to_message.from_user
        if opponent.id == user_id:
            bot.send_message(chat_id, "Нельзя играть с самим собой.")
            return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Принять", callback_data=f"cubs_accept_{user_id}_{opponent.id}"))
        bot.send_message(
            chat_id,
            f"🎲 {message.from_user.first_name} вызывает {opponent.first_name} на дуэль кубов!\n\n"
            f"{opponent.first_name}, принимаешь вызов?",
            reply_markup=markup
        )
    else:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Принять", callback_data=f"cubs_accept_{user_id}_0"))
        bot.send_message(
            chat_id,
            f"🎲 {message.from_user.first_name} вызывает всех на дуэль кубов!\n\n"
            f"Кто примет вызов?",
            reply_markup=markup
        )

# ===== КРЕСТИКИ-НОЛИКИ =====
@bot.message_handler(commands=['tictactoe', 'крестики'])
def tictactoe_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if message.reply_to_message:
        opponent = message.reply_to_message.from_user
        if opponent.id == user_id:
            bot.send_message(chat_id, "Нельзя играть с самим собой.")
            return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Принять", callback_data=f"ttt_accept_{user_id}_{opponent.id}"))
        bot.send_message(
            chat_id,
            f"❌⭕ {message.from_user.first_name} вызывает {opponent.first_name} на крестики-нолики!\n\n"
            f"{opponent.first_name}, принимаешь вызов?",
            reply_markup=markup
        )
    else:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Принять", callback_data=f"ttt_accept_{user_id}_0"))
        bot.send_message(
            chat_id,
            f"❌⭕ {message.from_user.first_name} вызывает всех на крестики-нолики!\n\n"
            f"Кто примет вызов?",
            reply_markup=markup
        )

# ===== ТЕКСТ БЕЗ СЛЭША =====
@bot.message_handler(func=lambda message: message.text and message.text.lower() in ["кубы", "кубики", "крестики", "нолики", "крестики-нолики"])
def text_commands(message):
    text = message.text.lower()
    if text in ["кубы", "кубики"]:
        cubs_command(message)
    elif text in ["крестики", "нолики", "крестики-нолики"]:
        tictactoe_command(message)

# ===== ОБРАБОТКА КНОПОК =====
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    data = call.data
    chat_id = call.message.chat.id

    # ---- КУБЫ: ПРИНЯТИЕ ----
    if data.startswith("cubs_accept_"):
        parts = data.split("_")
        challenger = int(parts[2])
        target = int(parts[3])

        if target != 0 and call.from_user.id != target:
            bot.answer_callback_query(call.id, "Этот вызов не для тебя.")
            return

        opponent = call.from_user.id
        if opponent == challenger:
            bot.answer_callback_query(call.id, "Нельзя играть с самим собой.")
            return

        roll1 = random.randint(1, 6)
        roll2 = random.randint(1, 6)

        if roll1 > roll2:
            result = f"🏆 Победил {call.from_user.first_name}!"
        elif roll2 > roll1:
            result = f"🏆 Победил {call.from_user.first_name}!"
        else:
            result = "🤝 Ничья!"

        bot.edit_message_text(
            f"🎲 Дуэль кубов!\n\n"
            f"{call.from_user.first_name}: {roll1}\n"
            f"Соперник: {roll2}\n\n"
            f"{result}",
            chat_id,
            call.message.message_id
        )

    # ---- КРЕСТИКИ-НОЛИКИ: ПРИНЯТИЕ ----
    elif data.startswith("ttt_accept_"):
        parts = data.split("_")
        challenger = int(parts[2])
        target = int(parts[3])

        if target != 0 and call.from_user.id != target:
            bot.answer_callback_query(call.id, "Этот вызов не для тебя.")
            return

        opponent = call.from_user.id
        if opponent == challenger:
            bot.answer_callback_query(call.id, "Нельзя играть с самим собой.")
            return

        game_id = f"{chat_id}_{challenger}_{opponent}"
        games[game_id] = {
            "board": [" "] * 9,
            "turn": challenger,
            "player1": challenger,
            "player2": opponent,
            "chat_id": chat_id
        }

        bot.edit_message_text(
            f"❌⭕ Игра началась!\n\n"
            f"Ход {call.from_user.first_name} (❌)",
            chat_id,
            call.message.message_id,
            reply_markup=ttt_board(game_id)
        )

# ===== ДОСКА =====
def ttt_board(game_id):
    game = games.get(game_id)
    if not game:
        return None

    board = game["board"]
    markup = types.InlineKeyboardMarkup(row_width=3)

    buttons = []
    for i in range(9):
        cell = board[i] if board[i] != " " else "⬜"
        buttons.append(types.InlineKeyboardButton(cell, callback_data=f"ttt_move_{game_id}_{i}"))

    markup.add(*buttons)
    return markup

# ===== ХОД В КРЕСТИКАХ-НОЛИКАХ =====
@bot.callback_query_handler(func=lambda call: call.data.startswith("ttt_move_"))
def ttt_move(call):
    data = call.data
    parts = data.split("_")
    game_id = parts[2] + "_" + parts[3] + "_" + parts[4]
    cell = int(parts[5])

    game = games.get(game_id)
    if not game:
        bot.answer_callback_query(call.id, "Игра не найдена.")
        return

    if call.from_user.id != game["turn"]:
        bot.answer_callback_query(call.id, "Сейчас не твой ход.")
        return

    if game["board"][cell] != " ":
        bot.answer_callback_query(call.id, "Клетка занята.")
        return

    symbol = "❌" if call.from_user.id == game["player1"] else "⭕"
    game["board"][cell] = symbol

    winner = check_winner(game["board"])
    if winner:
        bot.edit_message_text(
            f"❌⭕ Игра окончена!\n\nПобедил {call.from_user.first_name}!",
            game["chat_id"],
            call.message.message_id
        )
        del games[game_id]
        return

    if " " not in game["board"]:
        bot.edit_message_text(
            "❌⭕ Игра окончена!\n\nНичья!",
            game["chat_id"],
            call.message.message_id
        )
        del games[game_id]
        return

    game["turn"] = game["player2"] if game["turn"] == game["player1"] else game["player1"]

    bot.edit_message_reply_markup(
        game["chat_id"],
        call.message.message_id,
        reply_markup=ttt_board(game_id)
    )

# ===== ПРОВЕРКА ПОБЕДИТЕЛЯ =====
def check_winner(board):
    wins = [
        [0, 1, 2], [3, 4, 5], [6, 7, 8],
        [0, 3, 6], [1, 4, 7], [2, 5, 8],
        [0, 4, 8], [2, 4, 6]
    ]
    for combo in wins:
        if board[combo[0]] == board[combo[1]] == board[combo[2]] != " ":
            return True
    return False

# ===== ЗАПУСК =====
if __name__ == "__main__":
    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False, use_reloader=False),
        daemon=True
    ).start()

    print("Бот запущен...")
    bot.polling(none_stop=True)
