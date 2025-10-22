import logging
import json
import os
from datetime import datetime
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = "8256075803:AAEBqIpIC514IcY-9HptJyAJA4XIdP8CDog"
ADMIN_IDS = [8275649347, 8175884349]
FORCE_SUB_CHANNEL = "@thebosssquad"
PORT = int(os.environ.get('PORT', 10000))
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL', '')

# Initialize bot and Flask
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')
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

def check_subscription(user_id: int) -> bool:
    """Check if user is subscribed to the channel"""
    try:
        member = bot.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Subscription check error: {e}")
        return True

def get_subscription_keyboard():
    """Create subscription keyboard"""
    keyboard = InlineKeyboardMarkup()
    keyboard.row(InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_SUB_CHANNEL[1:]}"))
    keyboard.row(InlineKeyboardButton("✅ I've Joined", callback_data="check_sub"))
    return keyboard

@bot.message_handler(commands=['start'])
def start_command(message):
    """Handle /start command"""
    user_id = message.from_user.id
    
    if not check_subscription(user_id):
        bot.reply_to(
            message,
            "❌ <b>Please join our channel first!</b>\n\n"
            "Join the channel below and click 'I've Joined' to continue.",
            reply_markup=get_subscription_keyboard()
        )
        return
    
    welcome_text = (
        "👋 <b>Welcome to Fast Reset Bot!</b>\n\n"
        "🚀 <b>Commands:</b>\n"
        "• <code>/rst @username</code> - Reset a user\n"
        "• <code>/help</code> - Show help\n"
        "• <code>/start</code> - Start bot\n\n"
        "⚡ <b>Features:</b>\n"
        "• Ultra-fast response (<0.3s)\n"
        "• Works in groups and channels\n"
        "• Simple and efficient\n\n"
        "Made with ❤️"
    )
    
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['help'])
def help_command(message):
    """Handle /help command"""
    user_id = message.from_user.id
    
    if message.chat.type == "private":
        if not check_subscription(user_id):
            bot.reply_to(
                message,
                "❌ Please join our channel first!",
                reply_markup=get_subscription_keyboard()
            )
            return
    
    help_text = (
        "📚 <b>Bot Help</b>\n\n"
        "<b>How to use:</b>\n"
        "Send <code>/rst @username</code> to reset someone\n\n"
        "<b>Where it works:</b>\n"
        "• Private chat with bot\n"
        "• Groups (bot must be admin)\n"
        "• Channels (bot must be admin)\n\n"
        "<b>Note:</b> One reset at a time!"
    )
    
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['stat'])
def stat_command(message):
    """Handle /stat command (owners only)"""
    user_id = message.from_user.id
    
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
    
    if not stats.can_use(user_id):
        return
    
    if message.chat.type == "private":
        if not check_subscription(user_id):
            bot.reply_to(
                message,
                "❌ Please join our channel first!",
                reply_markup=get_subscription_keyboard()
            )
            return
    
    # Parse command
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ <b>Usage:</b> <code>/rst @username</code>")
        return
    
    target = parts[1]
    
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
    logger.info(f"Reset processed in {response_time:.3f}s")

@bot.message_handler(commands=['ping'])
def ping_command(message):
    """Handle /ping command"""
    start = datetime.now()
    sent = bot.reply_to(message, "🏓 Pong!")
    end = datetime.now()
    response_time = (end - start).total_seconds() * 1000
    bot.edit_message_text(
        f"🏓 Pong! <code>{response_time:.1f}ms</code>",
        sent.chat.id,
        sent.message_id
    )

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def check_subscription_callback(call):
    """Handle subscription check callback"""
    user_id = call.from_user.id
    
    if check_subscription(user_id):
        bot.edit_message_text(
            "✅ <b>Thank you for joining!</b>\n\n"
            "You can now use all bot features.\n"
            "Send /help to see available commands.",
            call.message.chat.id,
            call.message.message_id
        )
    else:
        bot.answer_callback_query(
            call.id,
            "❌ You haven't joined the channel yet!",
            show_alert=True
        )

# Flask routes
@app.route('/')
def index():
    """Health check endpoint for UptimeRobot"""
    return "Bot is running! 🚀", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle webhook updates"""
    try:
        json_data = request.get_json()
        update = telebot.types.Update.de_json(json_data)
        bot.process_new_updates([update])
        return "OK", 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "Error", 500

if __name__ == '__main__':
    # Setup webhook
    webhook_url = f"{WEBHOOK_URL}/webhook"
    bot.remove_webhook()
    bot.set_webhook(url=webhook_url)
    
    logger.info("🚀 Bot started successfully!")
    logger.info(f"📡 Webhook set to: {webhook_url}")
    logger.info(f"✅ Authorized users: {len(ADMIN_IDS)}")
    
    # Start Flask app
    app.run(host='0.0.0.0', port=PORT)
