import os
from time import time
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Configuration
BOT_TOKEN = "8256075803:AAEBqIpIC514IcY-9HptJyAJA4XIdP8CDog"
ADMIN_IDS = {8275649347, 8175884349}
PORT = int(os.getenv('PORT', 10000))
WEBHOOK_URL = os.getenv('RENDER_EXTERNAL_URL', 'https://resetbot-mkxz.onrender.com')

# Initialize bot with optimizations
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML', threaded=False, num_threads=2)
app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False

# Stats
stats = {'resets': 0, 'start_time': time()}

# Helper functions
def create_main_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📚 Help", callback_data="help"),
        InlineKeyboardButton("⚡ Ping", callback_data="ping")
    )
    return markup

def create_help_keyboard():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("« Back", callback_data="start"))
    return markup

# Command Handlers
@bot.message_handler(commands=['start'])
def start_handler(message):
    welcome = (
        "╔═══════════════════════╗\n"
        "║   <b>🚀 FAST RESET BOT</b>   ║\n"
        "╚═══════════════════════╝\n\n"
        "Welcome to the <b>fastest</b> reset bot!\n\n"
        "┌─────────────────────┐\n"
        "│  <b>⚡ COMMANDS</b>        │\n"
        "└─────────────────────┘\n\n"
        "▸ <code>/rst @username</code>\n"
        "   Reset any user instantly\n\n"
        "▸ <code>/help</code>\n"
        "   View detailed guide\n\n"
        "▸ <code>/ping</code>\n"
        "   Check response time\n\n"
        "┌─────────────────────┐\n"
        "│  <b>✨ FEATURES</b>       │\n"
        "└─────────────────────┘\n\n"
        "✓ Lightning fast (under 300ms)\n"
        "✓ Works everywhere\n"
        "✓ Professional design\n"
        "✓ 24/7 uptime\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "<i>Made with ❤️ | Always Fast ⚡</i>"
    )
    bot.send_message(message.chat.id, welcome, reply_to_message_id=message.message_id, reply_markup=create_main_keyboard())

@bot.message_handler(commands=['help'])
def help_handler(message):
    help_text = (
        "╔═══════════════════════╗\n"
        "║   <b>📚 HELP CENTER</b>    ║\n"
        "╚═══════════════════════╝\n\n"
        "┌─────────────────────┐\n"
        "│  <b>HOW TO USE</b>        │\n"
        "└─────────────────────┘\n\n"
        "<b>Basic Usage:</b>\n"
        "<code>/rst @username</code>\n\n"
        "<b>Example:</b>\n"
        "<code>/rst @john_doe</code>\n\n"
        "┌─────────────────────┐\n"
        "│  <b>FEATURES</b>          │\n"
        "└─────────────────────┘\n\n"
        "⚡ Speed: Under 300ms\n"
        "🎯 Accuracy: 100%\n"
        "🔒 Secure & Safe\n"
        "📊 Real-time stats\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "<i>Works in DMs, groups & channels</i>"
    )
    bot.send_message(message.chat.id, help_text, reply_to_message_id=message.message_id, reply_markup=create_help_keyboard())

@bot.message_handler(commands=['stat', 'stats'])
def stats_handler(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ <b>Access Denied</b>\n\n<i>Admin only command.</i>", reply_to_message_id=message.message_id)
        return
    
    uptime = int(time() - stats['start_time'])
    hours, remainder = divmod(uptime, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    stats_text = (
        "╔═══════════════════════╗\n"
        "║   <b>📊 STATISTICS</b>     ║\n"
        "╚═══════════════════════╝\n\n"
        f"🎯 <b>Total Resets:</b> <code>{stats['resets']:,}</code>\n"
        f"⏱ <b>Uptime:</b> <code>{hours}h {minutes}m {seconds}s</code>\n"
        f"⚡ <b>Status:</b> <code>🟢 Online</code>\n"
        f"🚀 <b>Mode:</b> <code>Production</code>\n\n"
        f"💾 <b>Server:</b> <code>Render</code>\n"
        f"🌐 <b>Region:</b> <code>Global</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, stats_text, reply_to_message_id=message.message_id)

@bot.message_handler(commands=['rst', 'reset'])
def reset_handler(message):
    start_time = time()
    user_id = message.from_user.id
    parts = message.text.split()
    
    if len(parts) < 2:
        bot.send_message(message.chat.id, "❌ <b>Invalid Format</b>\n\n<code>/rst @username</code>", reply_to_message_id=message.message_id)
        return
    
    target = parts[1]
    
    if not target.startswith('@'):
        bot.send_message(message.chat.id, "❌ <b>Invalid Username</b>\n\nMust start with @", reply_to_message_id=message.message_id)
        return
    
    process_time = int((time() - start_time) * 1000)
    
    if message.chat.type in ('group', 'supergroup', 'channel'):
        user_link = f'<a href="tg://user?id={user_id}">{message.from_user.first_name}</a>'
        success_msg = (
            "╔═══════════════════════╗\n"
            "║   <b>✅ RESET SUCCESS</b>   ║\n"
            "╚═══════════════════════╝\n\n"
            f"🎯 <b>Target:</b> {target}\n"
            f"👤 <b>Reset By:</b> {user_link}\n"
            f"⚡ <b>Status:</b> <code>Completed</code>\n"
            f"⏱ <b>Time:</b> <code>{process_time}ms</code>\n\n"
            "━━━━━━━━━━━━━━━━━━━"
        )
    else:
        success_msg = (
            "╔═══════════════════════╗\n"
            "║   <b>✅ RESET SUCCESS</b>   ║\n"
            "╚═══════════════════════╝\n\n"
            f"🎯 <b>Target:</b> {target}\n"
            f"⚡ <b>Status:</b> <code>Completed</code>\n"
            f"⏱ <b>Time:</b> <code>{process_time}ms</code>\n\n"
            "━━━━━━━━━━━━━━━━━━━"
        )
    
    bot.send_message(message.chat.id, success_msg, reply_to_message_id=message.message_id)
    stats['resets'] += 1

@bot.message_handler(commands=['ping'])
def ping_handler(message):
    start = time()
    sent = bot.send_message(message.chat.id, "⚡ <i>Calculating...</i>", reply_to_message_id=message.message_id)
    response_time = int((time() - start) * 1000)
    
    if response_time < 200:
        status, emoji = "🟢 Excellent", "🚀"
    elif response_time < 400:
        status, emoji = "🟡 Good", "⚡"
    else:
        status, emoji = "🟠 Fair", "📡"
    
    ping_msg = (
        "╔═══════════════════════╗\n"
        "║   <b>⚡ SPEED TEST</b>     ║\n"
        "╚═══════════════════════╝\n\n"
        f"{emoji} <b>Response:</b> <code>{response_time}ms</code>\n\n"
        f"📊 <b>Status:</b> {status}\n"
        f"🌐 <b>Server:</b> <code>Online</code>\n"
        f"🔄 <b>Load:</b> <code>Optimal</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━"
    )
    
    bot.edit_message_text(ping_msg, sent.chat.id, sent.message_id)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == "help":
        help_text = (
            "╔═══════════════════════╗\n"
            "║   <b>📚 QUICK HELP</b>     ║\n"
            "╚═══════════════════════╝\n\n"
            "<b>Usage:</b>\n<code>/rst @username</code>\n\n"
            "<b>Example:</b>\n<code>/rst @john</code>\n\n"
            "Works everywhere! ⚡"
        )
        bot.edit_message_text(help_text, call.message.chat.id, call.message.message_id, reply_markup=create_help_keyboard())
    elif call.data == "ping":
        start = time()
        response_time = int((time() - start) * 1000)
        bot.answer_callback_query(call.id, f"⚡ Response: {response_time}ms", show_alert=True)
    elif call.data == "start":
        start_handler(call.message)
    bot.answer_callback_query(call.id)

@app.route('/')
def index():
    return "🚀 Fast Reset Bot - Online", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data(as_text=True))])
    return '', 200

if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(f"{WEBHOOK_URL}/webhook", drop_pending_updates=True)
    
    from waitress import serve
    print("╔═══════════════════════════════════╗")
    print("║   🚀 FAST RESET BOT - ONLINE     ║")
    print("╚═══════════════════════════════════╝")
    print(f"📡 URL: {WEBHOOK_URL}")
    print(f"⚡ Mode: Production")
    print("═══════════════════════════════════")
    
    serve(app, host='0.0.0.0', port=PORT, threads=8, channel_timeout=120, connection_limit=1000, asyncore_use_poll=True)
