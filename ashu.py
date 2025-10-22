import logging
import json
import os
from datetime import datetime
from flask import Flask, request
import telebot
from time import time

# Minimal logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = "8256075803:AAEBqIpIC514IcY-9HptJyAJA4XIdP8CDog"
ADMIN_IDS = {8275649347, 8175884349}  # Set is faster than list
PORT = int(os.environ.get('PORT', 10000))
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL', '')

# Initialize bot and Flask
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML', threaded=False)
app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

# Ultra-fast stats tracking
class FastStats:
    __slots__ = ('total_resets', 'start_time', 'cooldown')  # Memory optimization
    
    def __init__(self):
        self.total_resets = 0
        self.start_time = time()
        self.cooldown = {}
    
    def can_use(self, user_id: int) -> bool:
        now = time()
        if user_id in self.cooldown:
            if now - self.cooldown[user_id] < 0.5:  # Reduced from 1s to 0.5s
                return False
        self.cooldown[user_id] = now
        return True
    
    def increment(self):
        self.total_resets += 1

stats = FastStats()

@bot.message_handler(commands=['start'])
def start_command(message):
    """Handle /start command"""
    bot.reply_to(message, 
        "👋 <b>Welcome to Fast Reset Bot!</b>\n\n"
        "🚀 <b>Commands:</b>\n"
        "• <code>/rst @username</code> - Reset a user\n"
        "• <code>/help</code> - Show help\n"
        "• <code>/ping</code> - Test speed\n\n"
        "⚡ Ultra-fast • No restrictions\n\n"
        "Dev: @yaplol")

@bot.message_handler(commands=['help'])
def help_command(message):
    """Handle /help command"""
    bot.reply_to(message,
        "📚 <b>Bot Help</b>\n\n"
        "<b>Usage:</b> <code>/rst @username</code>\n\n"
        "<b>Works in:</b>\n"
        "• Private chats\n"
        "• Groups\n"
        "• Channels\n\n"
        "⚡ Lightning fast!")

@bot.message_handler(commands=['stat'])
def stat_command(message):
    """Handle /stat command"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    uptime = int(time() - stats.start_time)
    hours, remainder = divmod(uptime, 3600)
    minutes, _ = divmod(remainder, 60)
    
    bot.reply_to(message,
        f"📊 <b>Stats</b>\n\n"
        f"🎯 <b>Resets:</b> <code>{stats.total_resets}</code>\n"
        f"⏱ <b>Uptime:</b> <code>{hours}h {minutes}m</code>\n"
        f"⚡ <b>Status:</b> Online")

@bot.message_handler(commands=['rst'])
def reset_command(message):
    """Handle /rst command - OPTIMIZED"""
    user_id = message.from_user.id
    
    # Fast cooldown check
    if not stats.can_use(user_id):
        return
    
    # Fast parsing
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "❌ <b>Usage:</b> <code>/rst @username</code>")
        return
    
    target = parts[1].split()[0]  # Get first word only
    
    # Fast validation
    if not target.startswith("@"):
        bot.reply_to(message, "❌ Use: <code>/rst @username</code>")
        return
    
    # Prepare message (optimized)
    if message.chat.type in ("group", "supergroup", "channel"):
        reset_text = (
            f"✅ <b>Reset successful!</b>\n\n"
            f"👤 <b>Target:</b> {target}\n"
            f"🔄 <b>By:</b> <a href='tg://user?id={user_id}'>{message.from_user.first_name}</a>"
        )
    else:
        reset_text = f"✅ <b>Reset successful!</b>\n\n👤 <b>Target:</b> {target}"
    
    bot.reply_to(message, reset_text)
    stats.increment()

@bot.message_handler(commands=['ping'])
def ping_command(message):
    """Handle /ping command"""
    start = time()
    sent = bot.reply_to(message, "🏓")
    response_time = (time() - start) * 1000
    
    bot.edit_message_text(
        f"🏓 <code>{response_time:.0f}ms</code>",
        sent.chat.id,
        sent.message_id
    )

# Flask routes (optimized)
@app.route('/')
def index():
    return "OK", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle webhook - ULTRA FAST"""
    try:
        json_string = request.get_data(as_text=True)
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
    except:
        pass
    return '', 200

if __name__ == '__main__':
    # Setup webhook
    bot.remove_webhook()
    webhook_url = f"{WEBHOOK_URL}/webhook"
    bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    
    logger.warning("🚀 Bot started - Ultra-fast mode")
    logger.warning(f"📡 Webhook: {webhook_url}")
    
    # Start Flask with optimizations
    from werkzeug.serving import run_simple
    run_simple('0.0.0.0', PORT, app, threaded=True, use_reloader=False, use_debugger=False)
