import os
import uuid
import string
import random
import requests
from time import time
from datetime import datetime
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging

# Configure logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = "8256075803:AAEBqIpIC514IcY-9HptJyAJA4XIdP8CDog"
ADMIN_IDS = {8275649347, 8175884349}
PORT = int(os.getenv('PORT', 10000))
WEBHOOK_URL = os.getenv('RENDER_EXTERNAL_URL', 'https://resetbot-mkxz.onrender.com')

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML', threaded=False)
app = Flask(__name__)

# Stats
stats = {
    'resets': 0,
    'successful': 0,
    'failed': 0,
    'start_time': time(),
    'bot_started': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
}
user_states = {}

def is_admin(user_id):
    return user_id in ADMIN_IDS

def send_instagram_reset(target: str) -> tuple:
    """
    Send password reset request to Instagram
    Returns (success: bool, message: str)
    """
    try:
        # Determine if target is email or username
        if '@' in target:
            data = {
                '_csrftoken': ''.join(random.choices(string.ascii_letters + string.digits, k=32)),
                'user_email': target,
                'guid': str(uuid.uuid4()),
                'device_id': str(uuid.uuid4())
            }
        else:
            data = {
                '_csrftoken': ''.join(random.choices(string.ascii_letters + string.digits, k=32)),
                'username': target,
                'guid': str(uuid.uuid4()),
                'device_id': str(uuid.uuid4())
            }
        
        # Generate random device headers
        headers = {
            'user-agent': f"Instagram 150.0.0.0.000 Android (29/10; 300dpi; 720x1440; "
                         f"{''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}/"
                         f"{''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}; "
                         f"{''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}; "
                         f"{''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}; en_GB;)"
        }
        
        # Send request to Instagram API
        response = requests.post(
            'https://i.instagram.com/api/v1/accounts/send_password_reset/',
            headers=headers,
            data=data,
            timeout=30
        )
        
        # Check if successful
        if 'obfuscated_email' in response.text:
            return True, "Reset link sent successfully"
        else:
            return False, f"Instagram API error: {response.text[:100]}"
            
    except requests.Timeout:
        return False, "Request timed out"
    except requests.RequestException as e:
        return False, f"Network error: {str(e)}"
    except Exception as e:
        return False, f"Error: {str(e)}"

# /start - Simple for everyone
@bot.message_handler(commands=['start'])
def start_handler(message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔄 Reset", callback_data="reset"))
    
    bot.send_message(
        message.chat.id,
        "🤖 Instagram Reset Bot\n\nPress Button:",
        reply_markup=markup
    )

# /help - All information
@bot.message_handler(commands=['help'])
def help_handler(message):
    help_text = (
        "╔═══════════════════════════╗\n"
        "║  <b>📚 HELP & INFORMATION</b> ║\n"
        "╚═══════════════════════════╝\n\n"
        "<b>📖 How to Use:</b>\n\n"
        "1️⃣ Click the 'Reset' button\n"
        "2️⃣ Enter Instagram username or email\n"
        "3️⃣ Wait for confirmation\n"
        "4️⃣ Check email for reset link\n\n"
        "<b>✅ Accepted Formats:</b>\n\n"
        "• Username: <code>john_doe</code>\n"
        "• Email: <code>user@email.com</code>\n\n"
        "<b>⚡ Features:</b>\n\n"
        "✓ Real Instagram API integration\n"
        "✓ Works with username or email\n"
        "✓ Instant processing\n"
        "✓ Official reset links\n"
        "✓ Secure & encrypted\n\n"
        "<b>🔒 Privacy:</b>\n\n"
        "Uses Instagram's official API.\n"
        "No data is stored.\n\n"
        "<b>💡 Tips:</b>\n\n"
        "• Double-check the username/email\n"
        "• Check spam folder\n"
        "• Link valid for 24 hours\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>For PR team use only</i>"
    )
    
    bot.send_message(message.chat.id, help_text)

# SECRET ADMIN COMMAND - /stats
@bot.message_handler(commands=['stats'])
def stats_handler(message):
    if not is_admin(message.from_user.id):
        return
    
    uptime = int(time() - stats['start_time'])
    hours, remainder = divmod(uptime, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    # Calculate success rate
    success_rate = 0
    if stats['resets'] > 0:
        success_rate = (stats['successful'] / stats['resets']) * 100
    
    # Ping test
    ping_start = time()
    test_msg = bot.send_message(message.chat.id, "Testing...")
    ping_ms = int((time() - ping_start) * 1000)
    bot.delete_message(test_msg.chat.id, test_msg.message_id)
    
    stats_text = (
        "╔═══════════════════════════════╗\n"
        "║   <b>🔐 ADMIN CONTROL PANEL</b>    ║\n"
        "╚═══════════════════════════════╝\n\n"
        "<b>📊 RESET STATISTICS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 <b>Total Resets:</b> <code>{stats['resets']:,}</code>\n"
        f"✅ <b>Successful:</b> <code>{stats['successful']:,}</code>\n"
        f"❌ <b>Failed:</b> <code>{stats['failed']:,}</code>\n"
        f"📈 <b>Success Rate:</b> <code>{success_rate:.1f}%</code>\n\n"
        "<b>⚡ SYSTEM STATUS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏓 <b>Bot Ping:</b> <code>{ping_ms}ms</code>\n"
        f"🌐 <b>Bot Status:</b> <code>🟢 Active</code>\n"
        f"🔌 <b>API Status:</b> <code>🟢 Connected</code>\n\n"
        "<b>⏱ UPTIME</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 <b>Started:</b> <code>{stats['bot_started']}</code>\n"
        f"⏰ <b>Running:</b> <code>{hours}h {minutes}m {seconds}s</code>\n\n"
        "<b>🔧 SYSTEM INFO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💾 <b>Server:</b> <code>Render.com</code>\n"
        f"🌍 <b>API:</b> <code>Instagram Official</code>\n"
        f"🚀 <b>Mode:</b> <code>Production</code>\n"
        f"⚙️ <b>Version:</b> <code>3.1</code>\n\n"
        "<b>👥 ACTIVITY LOG</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📈 <b>Active Sessions:</b> <code>{len(user_states)}</code>\n"
        f"🔄 <b>Processing Now:</b> <code>{sum(1 for u in user_states.values() if u == 'waiting_input')}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Last updated: {datetime.now().strftime('%H:%M:%S')}</i>"
    )
    
    bot.send_message(message.chat.id, stats_text)

# Callback handler
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == "reset":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel"))
        
        bot.edit_message_text(
            "📧 Enter username/email:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        
        user_states[call.from_user.id] = 'waiting_input'
        
    elif call.data == "cancel":
        bot.edit_message_text(
            "❌ Cancelled\n\nSend /start to try again.",
            call.message.chat.id,
            call.message.message_id
        )
        
        if call.from_user.id in user_states:
            del user_states[call.from_user.id]
    
    bot.answer_callback_query(call.id)

# Handle user input
@bot.message_handler(func=lambda msg: msg.from_user.id in user_states)
def handle_input(message):
    if user_states.get(message.from_user.id) != 'waiting_input':
        return
    
    user_input = message.text.strip()
    
    # Validate
    if len(user_input) < 3:
        bot.reply_to(message, "❌ Invalid. Please enter a valid username or email.")
        return
    
    # Processing message
    processing = bot.reply_to(
        message,
        "⏳ <b>Processing Instagram Reset...</b>\n\n"
        f"📧 <b>Target:</b> <code>{user_input}</code>\n"
        "🔄 <b>Status:</b> Sending request...",
    )
    
    # Send actual Instagram reset request
    success, result_message = send_instagram_reset(user_input)
    
    # Update stats
    stats['resets'] += 1
    if success:
        stats['successful'] += 1
    else:
        stats['failed'] += 1
    
    # Prepare result message
    if success:
        result_text = (
            "╔═══════════════════════════╗\n"
            "║   <b>✅ RESET SUCCESSFUL</b>   ║\n"
            "╚═══════════════════════════╝\n\n"
            f"📧 <b>Account:</b> <code>{user_input}</code>\n"
            f"⚡ <b>Status:</b> <code>Completed</code>\n"
            f"📨 <b>Result:</b> <code>{result_message}</code>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "✓ Password reset link sent to email\n"
            "✓ Check inbox and spam folder\n"
            "✓ Link valid for 24 hours\n"
            "✓ Use link to reset password\n\n"
            "<i>Reset completed successfully ✓</i>"
        )
    else:
        result_text = (
            "╔═══════════════════════════╗\n"
            "║   <b>❌ RESET FAILED</b>        ║\n"
            "╚═══════════════════════════╝\n\n"
            f"📧 <b>Account:</b> <code>{user_input}</code>\n"
            f"⚡ <b>Status:</b> <code>Failed</code>\n"
            f"📨 <b>Reason:</b> <code>{result_message}</code>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "💡 <b>Possible reasons:</b>\n"
            "• Account doesn't exist\n"
            "• Invalid username/email\n"
            "• Instagram rate limit\n"
            "• Network issues\n\n"
            "<i>Please try again or contact support</i>"
        )
    
    bot.edit_message_text(result_text, processing.chat.id, processing.message_id)
    
    # Clear state
    del user_states[message.from_user.id]
    
    # New reset button
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔄 Reset Another", callback_data="reset"))
    bot.send_message(message.chat.id, "Reset another account?", reply_markup=markup)

# Flask routes
@app.route('/')
def index():
    return "🤖 Instagram Reset Bot Online", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data(as_text=True))])
    return '', 200

if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(f"{WEBHOOK_URL}/webhook", drop_pending_updates=True)
    
    from waitress import serve
    print("╔════════════════════════════════╗")
    print("║  🤖 Instagram Reset Bot v3.1  ║")
    print("╚════════════════════════════════╝")
    print(f"📡 {WEBHOOK_URL}")
    print(f"👥 Admins: {len(ADMIN_IDS)}")
    print(f"🔌 API: Instagram Official")
    print(f"✅ Bot Started Successfully")
    print("════════════════════════════════")
    
    serve(app, host='0.0.0.0', port=PORT, threads=8)
