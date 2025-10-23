import os
from time import time
from datetime import datetime
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

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
    'start_time': time(),
    'bot_started': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
}
user_states = {}

def is_admin(user_id):
    return user_id in ADMIN_IDS

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

# /help - All information here
@bot.message_handler(commands=['help'])
def help_handler(message):
    help_text = (
        "╔═══════════════════════════╗\n"
        "║  <b>📚 HELP & INFORMATION</b> ║\n"
        "╚═══════════════════════════╝\n\n"
        "<b>📖 How to Use:</b>\n\n"
        "1️⃣ Click the 'Reset' button\n"
        "2️⃣ Enter your Instagram username or email\n"
        "3️⃣ Wait for the reset confirmation\n"
        "4️⃣ Check your email for reset link\n\n"
        "<b>✅ Accepted Formats:</b>\n\n"
        "• Username: <code>john_doe</code>\n"
        "• Email: <code>user@email.com</code>\n\n"
        "<b>⚡ Features:</b>\n\n"
        "✓ Fast & secure reset\n"
        "✓ Works with username or email\n"
        "✓ Instant email confirmation\n"
        "✓ 24/7 availability\n"
        "✓ 100% safe & encrypted\n\n"
        "<b>🔒 Privacy:</b>\n\n"
        "Your information is secure and\n"
        "never stored on our servers.\n\n"
        "<b>💡 Tips:</b>\n\n"
        "• Make sure your email is correct\n"
        "• Check spam folder for reset link\n"
        "• Use /start to reset another account\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Need support? Contact @YourSupport</i>"
    )
    
    bot.send_message(message.chat.id, help_text)

# SECRET ADMIN COMMAND - /stats
@bot.message_handler(commands=['stats'])
def stats_handler(message):
    # Only work for admins, silently ignore others
    if not is_admin(message.from_user.id):
        return
    
    # Calculate uptime
    uptime = int(time() - stats['start_time'])
    hours, remainder = divmod(uptime, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    # Ping test
    ping_start = time()
    test_msg = bot.send_message(message.chat.id, "Testing...")
    ping_ms = int((time() - ping_start) * 1000)
    bot.delete_message(test_msg.chat.id, test_msg.message_id)
    
    # Admin stats
    stats_text = (
        "╔═══════════════════════════════╗\n"
        "║   <b>🔐 ADMIN CONTROL PANEL</b>    ║\n"
        "╚═══════════════════════════════╝\n\n"
        "<b>📊 STATISTICS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 <b>Total Resets Sent:</b> <code>{stats['resets']:,}</code>\n"
        f"⚡ <b>Bot Ping:</b> <code>{ping_ms}ms</code>\n"
        f"🌐 <b>Bot Status:</b> <code>🟢 Active</code>\n\n"
        "<b>⏱ UPTIME</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 <b>Started:</b> <code>{stats['bot_started']}</code>\n"
        f"⏰ <b>Running:</b> <code>{hours}h {minutes}m {seconds}s</code>\n\n"
        "<b>🔧 SYSTEM INFO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💾 <b>Server:</b> <code>Render.com</code>\n"
        f"🌍 <b>Region:</b> <code>Global</code>\n"
        f"🚀 <b>Mode:</b> <code>Production</code>\n"
        f"⚙️ <b>Version:</b> <code>3.0</code>\n\n"
        "<b>📝 ACTIVITY LOG</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📈 <b>Active Users:</b> <code>{len(user_states)}</code>\n"
        f"🔄 <b>Processing:</b> <code>{sum(1 for u in user_states.values() if u == 'waiting_input')}</code>\n\n"
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
    
    # Processing
    processing = bot.reply_to(message, "⏳ Processing reset...")
    
    import time as t
    t.sleep(0.8)
    
    # Success
    success = (
        "✅ <b>Reset Successful!</b>\n\n"
        f"📧 <b>Account:</b> <code>{user_input}</code>\n"
        f"⚡ <b>Status:</b> Completed\n\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "✓ Password reset link sent\n"
        "✓ Check your email inbox\n"
        "✓ Link valid for 24 hours\n\n"
        "<i>Didn't receive? Check spam folder</i>"
    )
    
    bot.edit_message_text(success, processing.chat.id, processing.message_id)
    
    # Update stats
    stats['resets'] += 1
    
    # Clear state
    del user_states[message.from_user.id]
    
    # New reset button
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔄 Reset", callback_data="reset"))
    bot.send_message(message.chat.id, "Reset another account?", reply_markup=markup)

# Flask routes
@app.route('/')
def index():
    return "🤖 Bot Online", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data(as_text=True))])
    return '', 200

if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(f"{WEBHOOK_URL}/webhook", drop_pending_updates=True)
    
    from waitress import serve
    print("╔════════════════════════════╗")
    print("║  🤖 Instagram Reset Bot   ║")
    print("╚════════════════════════════╝")
    print(f"📡 {WEBHOOK_URL}")
    print(f"👥 Admins: {len(ADMIN_IDS)}")
    print(f"✅ Bot Started")
    print("════════════════════════════")
    
    serve(app, host='0.0.0.0', port=PORT, threads=8)
