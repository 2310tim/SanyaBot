import os
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

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Нажми меня", callback_data="test_button"))
    bot.send_message(message.chat.id, "Нажми на кнопку:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, f"✅ Кнопка работает! Ты нажал: {call.data}")

if __name__ == "__main__":
    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False, use_reloader=False),
        daemon=True
    ).start()
    print("Бот запущен...")
    bot.polling(non_stop=True)
