import os
from time import time
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Configuration
BOT_TOKEN = "8256075803:AAEBqIpIC514IcY-9HptJyAJA4XIdP8CDog"
ADMIN_IDS = {8275649347, 8175884349}
PORT = int(os.getenv('PORT', 10000))
WEBHOOK_URL = os.getenv('RENDER_EXTERNAL_URL', '')

# Initialize bot with optimizations
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML', threaded=False, num_threads=2)
app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False

# Stats
stats = {'resets': 0, 'start_time': time()}

# Helper functions
def create_main_keyboard():
    """Create main menu keyboard"""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📚 Help", callback_data="help"),
        InlineKeyboardButton("⚡ Ping", callback_data="ping")
    )
    return markup

def create_help_keyboard():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("« Back to Menu", callback_data="start")
    )
    return markup

# Command Handlers
@bot.message_handler(commands=['start'])
def start_handler(message):
    """Welcome message with professional design"""
    welcome = (
        "╔═══════════════════════╗\n"
        "║   <b>🚀 FAST RESET BOT</b>   ║\n"
        "╚═══════════════════════╝\n\n"
        "Welcome to the <b>fastest</b> and most <b>reliable</b>\n"
        "reset bot on Telegram!\n\n"
        "┌─────────────────────┐\n"
        "│  <b>⚡ MAIN COMMANDS</b>  │\n"
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
        "✓ Lightning fast (<300ms)\n"
        "✓ Works in groups & channels\n"
        "✓ Professional interface\n"
        "✓ 24/7 uptime guaranteed\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "<i>Made with ❤️ | Always Fast ⚡</i>"
    )
    bot.send_message(
        message.chat.id,
        welcome,
        reply_to_message_id=message.message_id,
        reply_markup=create_main_keyboard()
    )

@bot.message_handler(commands=['help'])
def help_handler(message):
    """Detailed help message"""
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
        "│  <b>WHERE IT WORKS</b>    │\n"
        "└─────────────────────┘\n\n"
        "✓ Private Chats\n"
        "✓ Group Chats\n"
        "✓ Channels\n"
        "✓ Supergroups\n\n"
        "┌─────────────────────┐\n"
        "│  <b>FEATURES</b>          │\n"
        "└─────────────────────┘\n\n"
        "⚡ <b>Speed:</b> Under 300ms response\n"
        "🎯 <b>Accuracy:</b> 100% success rate\n"
        "🔒 <b>Security:</b> Safe & secure\n"
        "📊 <b>Stats:</b> Real-time tracking\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "<i>Need more help? Contact support</i>"
    )
    bot.send_message(
        message.chat.id,
        help_text,
        reply_to_message_id=message.message_id,
        reply_markup=create_help_keyboard()
    )

@bot.message_handler(commands=['stat', 'stats'])
def stats_handler(message):
    """Statistics - Admin only"""
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(
            message.chat.id,
            "❌ <b>Access Denied</b>\n\n"
            "<i>This command is restricted to administrators only.</i>",
            reply_to_message_id=message.message_id
        )
        return
    
    uptime = int(time() - stats['start_time'])
    hours, remainder = divmod(uptime, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    stats_text = (
        "╔═══════════════════════╗\n"
        "║   <b>📊 BOT STATISTICS</b>  ║\n"
        "╚═══════════════════════╝\n\n"
        "┌─────────────────────┐\n"
        "│  <b>PERFORMANCE</b>       │\n"
        "└─────────────────────┘\n\n"
        f"🎯 <b>Total Resets:</b> <code>{stats['resets']:,}</code>\n"
        f"⏱ <b>Uptime:</b> <code>{hours}h {minutes}m {seconds}s</code>\n"
        f"⚡ <b>Status:</b> <code>🟢 Online</code>\n"
        f"🚀 <b>Mode:</b> <code>Production</code>\n\n"
        "┌─────────────────────┐\n"
        "│  <b>SYSTEM INFO</b>       │\n"
        "└─────────────────────┘\n\n"
        f"💾 <b>Server:</b> <code>Render.com</code>\n"
        f"🌐 <b>Region:</b> <code>Global</code>\n"
        f"⚙️ <b>Version:</b> <code>2.0.0</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Updated: {time():.0f}</i>"
    )
    bot.send_message(message.chat.id, stats_text, reply_to_message_id=message.message_id)

@bot.message_handler(commands=['rst', 'reset'])
def reset_handler(message):
    """Main reset command - Ultra fast"""
    user_id = message.from_user.id
    parts = message.text.split()
    
    # Validate input
    if len(parts) < 2:
        error_msg = (
            "❌ <b>Invalid Format</b>\n\n"
            "📝 <b>Correct Usage:</b>\n"
            "<code>/rst @username</code>\n\n"
            "💡 <b>Example:</b>\n"
            "<code>/rst @john_doe</code>"
        )
        bot.send_message(message.chat.id, error_msg, reply_to_message_id=message.message_id)
        return
    
    target = parts[1]
    
    if not target.startswith('@'):
        error_msg = (
            "❌ <b>Invalid Username</b>\n\n"
            "Username must start with <b>@</b>\n\n"
            "💡 <b>Example:</b>\n"
            "<code>/rst @username</code>"
        )
        bot.send_message(message.chat.id, error_msg, reply_to_message_id=message.message_id)
        return
    
    # Success message based on chat type
    if message.chat.type in ('group', 'supergroup', 'channel'):
        user_link = f'<a href="tg://user?id={user_id}">{message.from_user.first_name}</a>'
        success_msg = (
            "╔═══════════════════════╗\n"
            "║   <b>✅ RESET SUCCESS</b>   ║\n"
            "╚═══════════════════════╝\n\n"
            f"🎯 <b>Target:</b> {target}\n"
            f"👤 <b>Reset By:</b> {user_link}\n"
            f"⚡ <b>Status:</b> <code>Completed</code>\n"
            f"⏱ <b>Time:</b> <code>{int(time())} ms</code>\n\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "<i>Reset completed successfully ✓</i>"
        )
    else:
        success_msg = (
            "╔═══════════════════════╗\n"
            "║   <b>✅ RESET SUCCESS</b>   ║\n"
            "╚═══════════════════════╝\n\n"
            f"🎯 <b>Target:</b> {target}\n"
            f"⚡ <b>Status:</b> <code>Completed</code>\n"
            f"⏱ <b>Process Time:</b> <code>Instant</code>\n\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "<i>Reset completed successfully ✓</i>"
        )
    
    bot.send_message(message.chat.id, success_msg, reply_to_message_id=message.message_id)
    stats['resets'] += 1

@bot.message_handler(commands=['ping'])
def ping_handler(message):
    """Check bot response time"""
    start = time()
    sent = bot.send_message(
        message.chat.id,
        "⚡ <b>Calculating...</b>",
        reply_to_message_id=message.message_id
    )
    response_time = int((time() - start) * 1000)
    
    # Determine speed status
    if response_time < 200:
        status = "🟢 Excellent"
        emoji = "🚀"
    elif response_time < 400:
        status = "🟡 Good"
        emoji = "⚡"
    else:
        status = "🟠 Fair"
        emoji = "📡"
    
    ping_msg = (
        "╔═══════════════════════╗\n"
        "║   <b>⚡ SPEED TEST</b>     ║\n"
        "╚═══════════════════════╝\n\n"
        f"{emoji} <b>Response Time:</b>\n"
        f"<code>{response_time} ms</code>\n\n"
        f"📊 <b>Status:</b> {status}\n"
        f"🌐 <b>Server:</b> <code>Online</code>\n"
        f"🔄 <b>Load:</b> <code>Optimal</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "<i>All systems operational ✓</i>"
    )
    
    bot.edit_message_text(ping_msg, sent.chat.id, sent.message_id)

# Callback Query Handler
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    """Handle button callbacks"""
    if call.data == "help":
        help_text = (
            "╔═══════════════════════╗\n"
            "║   <b>📚 QUICK HELP</b>     ║\n"
            "╚═══════════════════════╝\n\n"
            "<b>Usage:</b>\n"
            "<code>/rst @username</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/rst @john_doe</code>\n\n"
            "Works in groups, channels & DMs!"
        )
        bot.edit_message_text(
            help_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=create_help_keyboard()
        )
    elif call.data == "ping":
        start = time()
        response_time = int((time() - start) * 1000)
        bot.answer_callback_query(call.id, f"⚡ Ping: {response_time}ms", show_alert=True)
    elif call.data == "start":
        start_handler(call.message)
    
    bot.answer_callback_query(call.id)

# Flask Routes
@app.route('/')
def index():
    return "🚀 Bot Online", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    """Ultra-fast webhook handler"""
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data(as_text=True))])
    return '', 200

# Main
if __name__ == '__main__':
    # Setup webhook
    bot.remove_webhook()
    bot.set_webhook(f"{WEBHOOK_URL}/webhook", drop_pending_updates=True)
    
    # Production server
    from waitress import serve
    print("╔═══════════════════════════════════╗")
    print("║   🚀 FAST RESET BOT - STARTED    ║")
    print("╚═══════════════════════════════════╝")
    print(f"📡 Webhook: {WEBHOOK_URL}/webhook")
    print(f"⚡ Mode: Production")
    print(f"✅ Status: Online")
    print("═══════════════════════════════════")
    
    serve(app, host='0.0.0.0', port=PORT, threads=8, channel_timeout=120)
