import logging
import json
import os
from datetime import datetime
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = "8256075803:AAEBqIpIC514IcY-9HptJyAJA4XIdP8CDog"
ADMIN_IDS = [8275649347, 8175884349]
FORCE_SUB_CHANNEL = "@thebosssquad"
PORT = int(os.environ.get('PORT', 10000))
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL', '')

# Flask app
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

async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is subscribed to the channel"""
    try:
        member = await context.bot.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Subscription check error: {e}")
        return True

def get_subscription_keyboard():
    """Create subscription keyboard"""
    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_SUB_CHANNEL[1:]}")],
        [InlineKeyboardButton("✅ I've Joined", callback_data="check_sub")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    
    if not await check_subscription(user.id, context):
        await update.message.reply_html(
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
    
    await update.message.reply_html(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    user = update.effective_user
    
    if update.effective_chat.type == "private":
        if not await check_subscription(user.id, context):
            await update.message.reply_html(
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
    
    await update.message.reply_html(help_text)

async def stat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stat command (owners only)"""
    user = update.effective_user
    
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ This command is not available!")
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
    
    await update.message.reply_html(stat_text)

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /rst command"""
    start_time = datetime.now()
    user = update.effective_user
    
    if not stats.can_use(user.id):
        return
    
    if update.effective_chat.type == "private":
        if not await check_subscription(user.id, context):
            await update.message.reply_html(
                "❌ Please join our channel first!",
                reply_markup=get_subscription_keyboard()
            )
            return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_html("❌ <b>Usage:</b> <code>/rst @username</code>")
        return
    
    target = context.args[0]
    
    if not target.startswith("@"):
        await update.message.reply_html("❌ <b>Please provide a valid username starting with @</b>")
        return
    
    if update.effective_chat.type in ["group", "supergroup", "channel"]:
        sender_link = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'
        reset_text = (
            f"✅ <b>Reset successful!</b>\n\n"
            f"👤 <b>Target:</b> {target}\n"
            f"🔄 <b>Reset by:</b> {sender_link}"
        )
    else:
        reset_text = f"✅ <b>Reset successful!</b>\n\n👤 <b>Target:</b> {target}"
    
    await update.message.reply_html(reset_text)
    stats.increment_resets()
    
    response_time = (datetime.now() - start_time).total_seconds()
    logger.info(f"Reset processed in {response_time:.3f}s")

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ping command"""
    start = datetime.now()
    msg = await update.message.reply_text("🏓 Pong!")
    end = datetime.now()
    response_time = (end - start).total_seconds() * 1000
    await msg.edit_text(f"🏓 Pong! <code>{response_time:.1f}ms</code>", parse_mode="HTML")

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle subscription check callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if await check_subscription(user_id, context):
        await query.edit_message_text(
            "✅ <b>Thank you for joining!</b>\n\n"
            "You can now use all bot features.\n"
            "Send /help to see available commands.",
            parse_mode="HTML"
        )
    else:
        await query.answer(
            "❌ You haven't joined the channel yet!",
            show_alert=True
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")

# Initialize bot application
application = Application.builder().token(BOT_TOKEN).build()

# Add handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CommandHandler("stat", stat_command))
application.add_handler(CommandHandler("rst", reset_command))
application.add_handler(CommandHandler("ping", ping_command))
application.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_sub$"))
application.add_error_handler(error_handler)

@app.route('/')
def index():
    """Health check endpoint for UptimeRobot"""
    return "Bot is running! 🚀", 200

@app.route('/webhook', methods=['POST'])
async def webhook():
    """Handle webhook updates"""
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        await application.process_update(update)
        return "OK", 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "Error", 500

if __name__ == '__main__':
    import asyncio
    from threading import Thread
    
    async def setup_webhook():
        """Setup webhook"""
        webhook_url = f"{WEBHOOK_URL}/webhook"
        await application.bot.set_webhook(url=webhook_url)
        logger.info(f"🚀 Webhook set to: {webhook_url}")
        logger.info(f"✅ Bot is running on port {PORT}")
        logger.info(f"✅ Authorized users: {len(ADMIN_IDS)}")
    
    # Run webhook setup
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(setup_webhook())
    
    # Start Flask app
    app.run(host='0.0.0.0', port=PORT)
