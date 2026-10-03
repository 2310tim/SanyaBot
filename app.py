import os
import threading
from flask import Flask
import telebot
from telebot import types

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("Токен не найден")

# ===== FLASK ДЛЯ RENDER =====
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running"

@app.route('/health')
def health():
    return "OK", 200

# ===== TELEGRAM BOT =====
bot = telebot.TeleBot(TOKEN)

def main_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_ai = types.InlineKeyboardButton("🤖 Чат с ИИ", callback_data="ai")
    btn_games = types.InlineKeyboardButton("🎮 Игры", callback_data="games")
    btn_add = types.InlineKeyboardButton(
        "➕ Добавить бота в чат",
        url=f"https://t.me/{bot.get_me().username}?startgroup=true"
    )
    markup.add(btn_ai, btn_games, btn_add)
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "👋 Здравствуйте!\n\nВыберите действие:",
        reply_markup=main_menu()
    )

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    if call.data == "ai":
        bot.send_message(
            call.message.chat.id,
            "🤖 Режим ИИ. Напишите сообщение, и я отвечу.\n\n(Функция в разработке)"
        )
    elif call.data == "games":
        bot.send_message(
            call.message.chat.id,
            "🎮 Режим игр. Выберите игру:\n\n(Функции в разработке)"
        )

# ===== ЗАПУСК =====
if __name__ == "__main__":
    # Flask в отдельном потоке (для Render)
    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False, use_reloader=False),
        daemon=True
    ).start()
    
    print("Бот запущен...")
    bot.polling(none_stop=True)
