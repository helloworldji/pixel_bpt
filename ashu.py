import logging
import json
import os
from datetime import datetime
from flask import Flask, request
import telebot

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = "8256075803:AAEBqIpIC514IcY-9HptJyAJA4XIdP8CDog"
ADMIN_IDS = [8275649347, 8175884349]
PORT = int(os.environ.get('PORT', 10000))
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL', '')

# Initialize bot and Flask
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML', threaded=False)
app = Flask(__name__)

# Stats tracking
class BotStats:
    def __init__(self):
        self.total_resets = 0
        self.start_time = datetime.now()
        self.user_cooldown = {}
        self.load_stats()
    
    def load_stats(self):
        try:
            if os.path.exists("stats.json"):
                with open("stats.json", "r") as f:
                    data = json.load(f)
                    self.total_resets = data.get("total_resets", 0)
                    logger.info(f"Loaded stats: {self.total_resets} total resets")
        except Exception as e:
            logger.error(f"Error loading stats: {e}")
    
    def save_stats(self):
        try:
            with open("stats.json", "w") as f:
                json.dump({"total_resets": self.total_resets}, f)
        except Exception as e:
            logger.error(f"Error saving stats: {e}")
    
    def can_use(self, user_id: int) -> bool:
        now = datetime.now()
        if user_id in self.user_cooldown:
            if (now - self.user_cooldown[user_id]).total_seconds() < 1:
                return False
        self.user_cooldown[user_id] = now
        return True
    
    def increment_resets(self):
        self.total_resets += 1
        if self.total_resets % 10 == 0:
            self.save_stats()

stats = BotStats()

@bot.message_handler(commands=['start'])
def start_command(message):
    """Handle /start command"""
    logger.info(f"Start command from user {message.from_user.id}")
    welcome_text = (
        "👋 <b>Welcome to Fast Reset Bot!</b>\n\n"
        "🚀 <b>Commands:</b>\n"
        "• <code>/rst @username</code> - Reset a user\n"
        "• <code>/help</code> - Show help\n"
        "• <code>/ping</code> - Test bot speed\n\n"
        "⚡ <b>Features:</b>\n"
        "• Ultra-fast response (under 0.3s)\n"
        "• Works in groups and channels\n"
        "• Simple and efficient\n\n"
        "Made with ❤️"
    )
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['help'])
def help_command(message):
    """Handle /help command"""
    logger.info(f"Help command from user {message.from_user.id}")
    help_text = (
        "📚 <b>Bot Help</b>\n\n"
        "<b>How to use:</b>\n"
        "Send <code>/rst @username</code> to reset someone\n\n"
        "<b>Where it works:</b>\n"
        "• Private chat with bot\n"
        "• Groups\n"
        "• Channels\n\n"
        "<b>Example:</b>\n"
        "<code>/rst @username</code>\n\n"
        "<b>Note:</b> Super fast and simple!"
    )
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['stat'])
def stat_command(message):
    """Handle /stat command (owners only)"""
    user_id = message.from_user.id
    logger.info(f"Stat command from user {user_id}")
    
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ This command is not available!")
        return
    
    uptime = datetime.now() - stats.start_time
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    stat_text = (
        "📊 <b>Bot Statistics</b>\n\n"
        f"🎯 <b>Total Resets:</b> <code>{stats.total_resets}</code>\n"
        f"⏱ <b>Uptime:</b> <code>{uptime.days}d {hours}h {minutes}m</code>\n"
        f"🚀 <b>Status:</b> <code>Online</code>\n"
        f"⚡ <b>Performance:</b> <code>Optimized</code>"
    )
    
    bot.reply_to(message, stat_text)

@bot.message_handler(commands=['rst'])
def reset_command(message):
    """Handle /rst command"""
    start_time = datetime.now()
    user_id = message.from_user.id
    
    logger.info(f"Reset command from user {user_id}: {message.text}")
    
    # Cooldown check
    if not stats.can_use(user_id):
        logger.info(f"User {user_id} hit cooldown")
        return
    
    # Parse command
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ <b>Usage:</b> <code>/rst @username</code>")
        return
    
    target = parts[1]
    
    # Validate username
    if not target.startswith("@"):
        bot.reply_to(message, "❌ <b>Please provide a valid username starting with @</b>")
        return
    
    # Prepare reset message
    if message.chat.type in ["group", "supergroup", "channel"]:
        sender_link = f'<a href="tg://user?id={user_id}">{message.from_user.first_name}</a>'
        reset_text = (
            f"✅ <b>Reset successful!</b>\n\n"
            f"👤 <b>Target:</b> {target}\n"
            f"🔄 <b>Reset by:</b> {sender_link}"
        )
    else:
        reset_text = f"✅ <b>Reset successful!</b>\n\n👤 <b>Target:</b> {target}"
    
    bot.reply_to(message, reset_text)
    stats.increment_resets()
    
    response_time = (datetime.now() - start_time).total_seconds()
    logger.info(f"Reset processed in {response_time:.3f}s for user {user_id}")

@bot.message_handler(commands=['ping'])
def ping_command(message):
    """Handle /ping command"""
    logger.info(f"Ping command from user {message.from_user.id}")
    start = datetime.now()
    sent = bot.reply_to(message, "🏓 Pong!")
    end = datetime.now()
    response_time = (end - start).total_seconds() * 1000
    try:
        bot.edit_message_text(
            f"🏓 Pong! <code>{response_time:.1f}ms</code>",
            sent.chat.id,
            sent.message_id
        )
    except Exception as e:
        logger.error(f"Error editing ping message: {e}")

# Flask routes
@app.route('/')
def index():
    """Health check endpoint for UptimeRobot"""
    return "Bot is running! 🚀", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle webhook updates"""
    try:
        if request.headers.get('content-type') == 'application/json':
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return '', 200
        else:
            return '', 403
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return '', 200

if __name__ == '__main__':
    try:
        # Remove old webhook
        bot.remove_webhook()
        logger.info("Old webhook removed")
        
        # Set new webhook with drop_pending_updates
        webhook_url = f"{WEBHOOK_URL}/webhook"
        bot.set_webhook(url=webhook_url, drop_pending_updates=True)
        
        logger.info("🚀 Bot started successfully!")
        logger.info(f"📡 Webhook: {webhook_url}")
        logger.info(f"✅ Authorized users: {len(ADMIN_IDS)}")
        logger.info("⚡ No force join - All users can access!")
        
        # Start Flask app
        app.run(host='0.0.0.0', port=PORT, debug=False)
    except Exception as e:
        logger.error(f"Startup error: {e}", exc_info=True)
