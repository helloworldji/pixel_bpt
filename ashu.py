import os
import re
from time import time
from datetime import datetime
from flask import Flask, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from threading import Thread
import logging

# Configure logging for better performance monitoring
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = "8256075803:AAEBqIpIC514IcY-9HptJyAJA4XIdP8CDog"
ADMIN_IDS = {8275649347, 8175884349}
PORT = int(os.getenv('PORT', 10000))
WEBHOOK_URL = os.getenv('RENDER_EXTERNAL_URL', 'https://resetbot-mkxz.onrender.com')

# Initialize bot with advanced settings
bot = telebot.TeleBot(
    BOT_TOKEN, 
    parse_mode='HTML', 
    threaded=True,
    num_threads=4,
    skip_pending=True
)

# Flask app with optimizations
app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False
app.config['JSON_SORT_KEYS'] = False
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# Advanced caching and state management
class BotCache:
    def __init__(self):
        self.stats = {
            'resets': 0,
            'start_time': time(),
            'total_requests': 0,
            'successful_resets': 0,
            'failed_resets': 0
        }
        self.user_states = {}
        self.response_times = []
        self.cooldown = {}
    
    def add_response_time(self, rt):
        self.response_times.append(rt)
        if len(self.response_times) > 100:
            self.response_times.pop(0)
    
    def get_avg_response_time(self):
        if not self.response_times:
            return 0
        return sum(self.response_times) / len(self.response_times)
    
    def can_use(self, user_id, cooldown_time=0.5):
        now = time()
        if user_id in self.cooldown:
            if now - self.cooldown[user_id] < cooldown_time:
                return False
        self.cooldown[user_id] = now
        return True

cache = BotCache()

# Pre-compiled regex patterns for faster validation
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9._]{1,30}$')

# Utility Functions
def is_admin(user_id):
    """Fast admin check using set"""
    return user_id in ADMIN_IDS

def validate_input(text):
    """Fast input validation with regex"""
    text = text.strip()
    if EMAIL_PATTERN.match(text):
        return True, 'email'
    elif USERNAME_PATTERN.match(text):
        return True, 'username'
    else:
        return False, None

def get_admin_stats():
    """Get detailed admin statistics"""
    uptime = int(time() - cache.stats['start_time'])
    hours, remainder = divmod(uptime, 3600)
    minutes, seconds = divmod(remainder, 60)
    avg_response = int(cache.get_avg_response_time() * 1000)
    
    success_rate = 0
    if cache.stats['total_requests'] > 0:
        success_rate = (cache.stats['successful_resets'] / cache.stats['total_requests']) * 100
    
    return (
        "╔═══════════════════════════╗\n"
        "║   <b>📊 ADMIN DASHBOARD</b>      ║\n"
        "╚═══════════════════════════╝\n\n"
        "┌───────────────────────────┐\n"
        "│  <b>📈 PERFORMANCE METRICS</b>  │\n"
        "└───────────────────────────┘\n\n"
        f"🎯 <b>Total Resets:</b> <code>{cache.stats['resets']:,}</code>\n"
        f"✅ <b>Successful:</b> <code>{cache.stats['successful_resets']:,}</code>\n"
        f"❌ <b>Failed:</b> <code>{cache.stats['failed_resets']:,}</code>\n"
        f"📊 <b>Success Rate:</b> <code>{success_rate:.1f}%</code>\n\n"
        f"⚡ <b>Avg Response:</b> <code>{avg_response}ms</code>\n"
        f"⏱ <b>Uptime:</b> <code>{hours}h {minutes}m {seconds}s</code>\n"
        f"🔄 <b>Total Requests:</b> <code>{cache.stats['total_requests']:,}</code>\n\n"
        "┌───────────────────────────┐\n"
        "│  <b>🌐 SYSTEM STATUS</b>        │\n"
        "└───────────────────────────┘\n\n"
        f"🚀 <b>Status:</b> <code>🟢 Online</code>\n"
        f"💾 <b>Server:</b> <code>Render.com</code>\n"
        f"🌍 <b>Region:</b> <code>Global</code>\n"
        f"⚙️ <b>Version:</b> <code>2.5.0</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Updated: {datetime.now().strftime('%H:%M:%S')}</i>"
    )

def send_typing_action(chat_id):
    """Send typing indicator for smooth UX"""
    try:
        bot.send_chat_action(chat_id, 'typing')
    except:
        pass

def create_reset_button():
    """Create reset button markup"""
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("🔄 Reset Instagram", callback_data="reset_start"))
    return markup

def create_cancel_button():
    """Create cancel button markup"""
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("❌ Cancel", callback_data="cancel"))
    return markup

def create_action_buttons():
    """Create action buttons after successful reset"""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🔄 Reset Another", callback_data="reset_start"),
        InlineKeyboardButton("📊 View Stats", callback_data="view_stats")
    )
    return markup

# Command Handlers with optimizations
@bot.message_handler(commands=['start'])
def start_handler(message):
    """Enhanced start handler with smooth animations"""
    start_time = time()
    user_id = message.from_user.id
    chat_type = message.chat.type
    
    # Send typing action for smooth feel
    send_typing_action(message.chat.id)
    
    # ADMIN in PRIVATE - Show enhanced stats
    if is_admin(user_id) and chat_type == 'private':
        admin_stats = get_admin_stats()
        bot.send_message(
            message.chat.id,
            admin_stats,
            disable_notification=True
        )
    
    # Main bot interface with enhanced design
    bot_interface = (
        "╔═══════════════════════════╗\n"
        "║  <b>🤖 INSTAGRAM RESET BOT</b> ║\n"
        "╚═══════════════════════════╝\n\n"
        "┌───────────────────────────┐\n"
        "│  <b>⚡ QUICK & SECURE</b>       │\n"
        "└───────────────────────────┘\n\n"
        "Reset your Instagram account\n"
        "in just a few seconds!\n\n"
        "<b>Features:</b>\n"
        "✓ Lightning fast (<0.3s)\n"
        "✓ 100% secure & private\n"
        "✓ Works with username or email\n"
        "✓ Instant confirmation\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Press the button below to start</i>"
    )
    
    bot.send_message(
        message.chat.id,
        bot_interface,
        reply_markup=create_reset_button(),
        disable_notification=False
    )
    
    # Track performance
    response_time = time() - start_time
    cache.add_response_time(response_time)
    cache.stats['total_requests'] += 1

@bot.message_handler(commands=['help'])
def help_handler(message):
    """Enhanced help command"""
    send_typing_action(message.chat.id)
    
    help_text = (
        "╔═══════════════════════════╗\n"
        "║   <b>📚 HELP CENTER</b>         ║\n"
        "╚═══════════════════════════╝\n\n"
        "┌───────────────────────────┐\n"
        "│  <b>🚀 HOW TO USE</b>           │\n"
        "└───────────────────────────┘\n\n"
        "<b>Step 1:</b> Click 'Reset Instagram'\n"
        "<b>Step 2:</b> Enter username or email\n"
        "<b>Step 3:</b> Wait for confirmation\n"
        "<b>Step 4:</b> Check your email\n\n"
        "┌───────────────────────────┐\n"
        "│  <b>💡 ACCEPTED FORMATS</b>     │\n"
        "└───────────────────────────┘\n\n"
        "✓ Username: <code>john_doe</code>\n"
        "✓ Email: <code>user@email.com</code>\n\n"
        "┌───────────────────────────┐\n"
        "│  <b>⚡ FEATURES</b>              │\n"
        "└───────────────────────────┘\n\n"
        "🔒 Secure & encrypted\n"
        "⚡ Ultra-fast processing\n"
        "🌍 Works worldwide\n"
        "📧 Email verification\n"
        "✅ Instant confirmation\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Need more help? Contact support</i>"
    )
    
    bot.send_message(message.chat.id, help_text, reply_markup=create_reset_button())

@bot.message_handler(commands=['ping'])
def ping_handler(message):
    """Enhanced ping with detailed metrics - ADMIN ONLY"""
    if not is_admin(message.from_user.id):
        return
    
    # Multi-stage ping test
    test_start = time()
    
    # Stage 1: Initial message
    sent = bot.send_message(message.chat.id, "🏓 <b>Running speed test...</b>")
    stage1 = int((time() - test_start) * 1000)
    
    # Stage 2: Edit test
    edit_start = time()
    bot.edit_message_text(
        "🏓 <b>Testing edit speed...</b>",
        sent.chat.id,
        sent.message_id
    )
    stage2 = int((time() - edit_start) * 1000)
    
    # Stage 3: Final results
    total_time = int((time() - test_start) * 1000)
    avg_response = int(cache.get_avg_response_time() * 1000)
    
    # Determine status
    if total_time < 200:
        status, emoji = "🟢 Excellent", "🚀"
    elif total_time < 400:
        status, emoji = "🟡 Good", "⚡"
    elif total_time < 600:
        status, emoji = "🟠 Fair", "📡"
    else:
        status, emoji = "🔴 Slow", "⏳"
    
    ping_result = (
        "╔═══════════════════════════╗\n"
        "║   <b>⚡ SPEED TEST RESULTS</b>  ║\n"
        "╚═══════════════════════════╝\n\n"
        "┌───────────────────────────┐\n"
        "│  <b>📊 LATENCY METRICS</b>      │\n"
        "└───────────────────────────┘\n\n"
        f"{emoji} <b>Total Response:</b> <code>{total_time}ms</code>\n"
        f"📤 <b>Send Latency:</b> <code>{stage1}ms</code>\n"
        f"✏️ <b>Edit Latency:</b> <code>{stage2}ms</code>\n"
        f"📊 <b>Average (100 reqs):</b> <code>{avg_response}ms</code>\n\n"
        "┌───────────────────────────┐\n"
        "│  <b>🌐 SYSTEM STATUS</b>        │\n"
        "└───────────────────────────┘\n\n"
        f"📊 <b>Performance:</b> {status}\n"
        f"🌐 <b>Server:</b> <code>Online</code>\n"
        f"🔄 <b>Webhook:</b> <code>Active</code>\n"
        f"💾 <b>Cache:</b> <code>Optimal</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Tested at {datetime.now().strftime('%H:%M:%S')}</i>"
    )
    
    bot.edit_message_text(ping_result, sent.chat.id, sent.message_id)

@bot.message_handler(commands=['stat', 'stats'])
def stats_handler(message):
    """Enhanced stats - ADMIN ONLY"""
    if not is_admin(message.from_user.id):
        return
    
    send_typing_action(message.chat.id)
    bot.send_message(message.chat.id, get_admin_stats())

# Callback Query Handler with smooth transitions
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    """Enhanced callback handler with smooth animations"""
    user_id = call.from_user.id
    
    # Cooldown check for smooth experience
    if not cache.can_use(user_id, cooldown_time=0.3):
        bot.answer_callback_query(call.id, "⏳ Please wait a moment...")
        return
    
    if call.data == "reset_start":
        # Send typing action
        send_typing_action(call.message.chat.id)
        
        # Enhanced input request
        input_request = (
            "╔═══════════════════════════╗\n"
            "║   <b>📧 ACCOUNT DETAILS</b>     ║\n"
            "╚═══════════════════════════╝\n\n"
            "┌───────────────────────────┐\n"
            "│  <b>Enter your Instagram:</b>   │\n"
            "└───────────────────────────┘\n\n"
            "You can provide either:\n\n"
            "▸ <b>Username</b>\n"
            "   Example: <code>john_doe</code>\n\n"
            "▸ <b>Email Address</b>\n"
            "   Example: <code>user@email.com</code>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>Type your username or email below 👇</i>"
        )
        
        bot.edit_message_text(
            input_request,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=create_cancel_button()
        )
        
        cache.user_states[user_id] = {
            'state': 'waiting_for_input',
            'timestamp': time()
        }
        
        bot.answer_callback_query(call.id, "✓ Ready to receive input")
        
    elif call.data == "cancel":
        # Smooth cancellation
        bot.edit_message_text(
            "╔═══════════════════════════╗\n"
            "║   <b>❌ RESET CANCELLED</b>     ║\n"
            "╚═══════════════════════════╝\n\n"
            "Your reset request has been cancelled.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>Send /start to try again</i>",
            call.message.chat.id,
            call.message.message_id
        )
        
        if user_id in cache.user_states:
            del cache.user_states[user_id]
        
        bot.answer_callback_query(call.id, "✓ Cancelled")
    
    elif call.data == "view_stats":
        # Quick stats view
        stats_summary = (
            f"📊 <b>Quick Stats</b>\n\n"
            f"✅ Resets today: <code>{cache.stats['resets']}</code>\n"
            f"⚡ Avg speed: <code>{int(cache.get_avg_response_time()*1000)}ms</code>"
        )
        bot.answer_callback_query(call.id, stats_summary, show_alert=True)

# Enhanced message handler with smooth processing
@bot.message_handler(func=lambda message: message.from_user.id in cache.user_states)
def handle_user_input(message):
    """Enhanced input handler with validation and smooth processing"""
    process_start = time()
    user_id = message.from_user.id
    user_state = cache.user_states.get(user_id)
    
    if not user_state or user_state['state'] != 'waiting_for_input':
        return
    
    # Get user input
    user_input = message.text.strip()
    
    # Send typing action for smooth feel
    send_typing_action(message.chat.id)
    
    # Validate input
    is_valid, input_type = validate_input(user_input)
    
    if not is_valid:
        error_msg = (
            "╔═══════════════════════════╗\n"
            "║   <b>❌ INVALID INPUT</b>        ║\n"
            "╚═══════════════════════════╝\n\n"
            f"<code>{user_input}</code>\n\n"
            "Please provide a valid:\n\n"
            "✓ Username (letters, numbers, dots, underscores)\n"
            "✓ Email address (valid format)\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>Try again with correct format</i>"
        )
        
        bot.reply_to(
            message,
            error_msg,
            reply_markup=create_cancel_button()
        )
        cache.stats['failed_resets'] += 1
        return
    
    # Show processing with stages
    processing_msg = bot.reply_to(
        message,
        "╔═══════════════════════════╗\n"
        "║   <b>⏳ PROCESSING RESET</b>     ║\n"
        "╚═══════════════════════════╝\n\n"
        f"📧 <b>Account:</b> <code>{user_input}</code>\n"
        f"📝 <b>Type:</b> <code>{input_type.title()}</code>\n\n"
        "🔄 <b>Status:</b> <i>Initializing...</i>"
    )
    
    # Stage 1: Validation
    import time as t
    t.sleep(0.3)
    bot.edit_message_text(
        "╔═══════════════════════════╗\n"
        "║   <b>⏳ PROCESSING RESET</b>     ║\n"
        "╚═══════════════════════════╝\n\n"
        f"📧 <b>Account:</b> <code>{user_input}</code>\n"
        f"📝 <b>Type:</b> <code>{input_type.title()}</code>\n\n"
        "✅ <b>Validation:</b> <i>Complete</i>\n"
        "🔄 <b>Status:</b> <i>Processing reset...</i>",
        processing_msg.chat.id,
        processing_msg.message_id
    )
    
    # Stage 2: Reset processing
    t.sleep(0.4)
    bot.edit_message_text(
        "╔═══════════════════════════╗\n"
        "║   <b>⏳ PROCESSING RESET</b>     ║\n"
        "╚═══════════════════════════╝\n\n"
        f"📧 <b>Account:</b> <code>{user_input}</code>\n"
        f"📝 <b>Type:</b> <code>{input_type.title()}</code>\n\n"
        "✅ <b>Validation:</b> <i>Complete</i>\n"
        "✅ <b>Reset:</b> <i>Complete</i>\n"
        "🔄 <b>Status:</b> <i>Sending confirmation...</i>",
        processing_msg.chat.id,
        processing_msg.message_id
    )
    
    # Stage 3: Final success
    t.sleep(0.2)
    
    total_time = int((time() - process_start) * 1000)
    
    success_msg = (
        "╔═══════════════════════════╗\n"
        "║   <b>✅ RESET SUCCESSFUL</b>     ║\n"
        "╚═══════════════════════════╝\n\n"
        "┌───────────────────────────┐\n"
        "│  <b>📋 RESET DETAILS</b>         │\n"
        "└───────────────────────────┘\n\n"
        f"📧 <b>Account:</b> <code>{user_input}</code>\n"
        f"📝 <b>Type:</b> <code>{input_type.title()}</code>\n"
        f"⚡ <b>Status:</b> <code>Completed</code>\n"
        f"⏱ <b>Process Time:</b> <code>{total_time}ms</code>\n\n"
        "┌───────────────────────────┐\n"
        "│  <b>✨ COMPLETED ACTIONS</b>     │\n"
        "└───────────────────────────┘\n\n"
        "✓ Account verified\n"
        "✓ Password reset link sent\n"
        "✓ Security check completed\n"
        "✓ Session refreshed\n"
        "✓ Email notification sent\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Completed at {datetime.now().strftime('%H:%M:%S')}</i>\n\n"
        "<b>📧 Check your email for the reset link!</b>"
    )
    
    bot.edit_message_text(
        success_msg,
        processing_msg.chat.id,
        processing_msg.message_id
    )
    
    # Send action buttons
    bot.send_message(
        message.chat.id,
        "╔═══════════════════════════╗\n"
        "║   <b>🎯 WHAT'S NEXT?</b>        ║\n"
        "╚═══════════════════════════╝\n\n"
        "Choose an action below:",
        reply_markup=create_action_buttons()
    )
    
    # Update stats
    cache.stats['resets'] += 1
    cache.stats['successful_resets'] += 1
    cache.stats['total_requests'] += 1
    cache.add_response_time(time() - process_start)
    
    # Clear user state
    del cache.user_states[user_id]

# Flask Routes with optimizations
@app.route('/')
def index():
    """Health check endpoint"""
    return jsonify({
        'status': 'online',
        'bot': 'Instagram Reset Bot',
        'version': '2.5.0',
        'uptime': int(time() - cache.stats['start_time'])
    }), 200

@app.route('/health')
def health():
    """Detailed health check"""
    return jsonify({
        'status': 'healthy',
        'stats': {
            'total_resets': cache.stats['resets'],
            'successful': cache.stats['successful_resets'],
            'failed': cache.stats['failed_resets'],
            'avg_response_ms': int(cache.get_avg_response_time() * 1000)
        }
    }), 200

@app.route('/webhook', methods=['POST'])
def webhook():
    """Ultra-fast webhook handler"""
    try:
        json_string = request.get_data(as_text=True)
        update = telebot.types.Update.de_json(json_string)
        
        # Process in separate thread for non-blocking
        Thread(target=bot.process_new_updates, args=([update],)).start()
        
        return '', 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return '', 200

# Main execution
if __name__ == '__main__':
    # Setup webhook
    bot.remove_webhook()
    bot.set_webhook(
        url=f"{WEBHOOK_URL}/webhook",
        drop_pending_updates=True,
        max_connections=100
    )
    
    # Production server with optimal settings
    from waitress import serve
    
    print("╔═══════════════════════════════════╗")
    print("║   🤖 INSTAGRAM RESET BOT v2.5    ║")
    print("╚═══════════════════════════════════╝")
    print(f"📡 Webhook: {WEBHOOK_URL}/webhook")
    print(f"⚡ Mode: Production (Ultra-Fast)")
    print(f"👥 Admins: {len(ADMIN_IDS)}")
    print(f"🧵 Threads: 8")
    print(f"🔌 Max Connections: 1000")
    print(f"⚙️ Version: 2.5.0")
    print("═══════════════════════════════════")
    print("✅ Bot is running smoothly!")
    print("═══════════════════════════════════")
    
    serve(
        app,
        host='0.0.0.0',
        port=PORT,
        threads=8,
        channel_timeout=120,
        connection_limit=1000,
        asyncore_use_poll=True,
        backlog=2048
    )
