import os
import logging
import asyncio
import uuid
import httpx
import re
import json
from telegram import Update, BotCommand, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    filters
)
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
import uvicorn
from contextlib import asynccontextmanager
from typing import Tuple, List

# = a========================
# Configuration
# =========================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
RENDER_EXTERNAL_URL = os.getenv('RENDER_EXTERNAL_URL')
WEBHOOK_URL = RENDER_EXTERNAL_URL if RENDER_EXTERNAL_URL else os.getenv('WEBHOOK_URL')
DEV_HANDLE = "@aadi_io"

# --- Force Join Configuration ---
# Replace with your actual channel/group IDs and links
CHANNELS = [
    {"id": "-1002628211220", "name": "MAIN CHANNEL 📢", "link": "https://t.me/c/2628211220/1"}, # Example private link
    {"id": "@pytimebruh", "name": "BACKUP", "link": "https://t.me/pytimebruh"},
    {"id": "@HazyPy", "name": "BACKUP 2", "link": "https://t.me/HazyPy"},
    {"id": "@thewalkingexcuse", "name": "BACKUP 3", "link": "https://t.me/thewalkingexcuse"},
]

# Validate required environment variables
if not TELEGRAM_TOKEN:
    logger.critical("FATAL: TELEGRAM_BOT_TOKEN environment variable not set. Bot cannot start.")
    exit(1)

# Global variables
application = None
bot_status = {"initialized": False, "webhook_verified": False, "error": None, "details": {}}

# Conversation states
AWAITING_TARGET, AWAITING_BULK = range(2)

# =========================
# Force Join Logic
# =========================

async def check_membership(user_id: int, channel_id: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if a user is a member of a single channel."""
    try:
        member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.warning(f"Could not check membership for user {user_id} in channel {channel_id}: {e}")
        return False

async def has_joined_all(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if a user has joined all required channels concurrently."""
    tasks = [check_membership(user_id, channel['id'], context) for channel in CHANNELS]
    results = await asyncio.gather(*tasks)
    return all(results)

async def send_join_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the force-join message with inline keyboard."""
    keyboard = []
    for channel in CHANNELS:
        keyboard.append([InlineKeyboardButton(channel['name'], url=channel['link'])])
    keyboard.append([InlineKeyboardButton("✅ I Have Joined All", callback_data="check_joined")])
    
    markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🚫 ACCESS DENIED\n\n"
        "You must join all our channels and groups to use this bot.\n\n"
        "Join all channels below, then click the button to verify.",
        reply_markup=markup
    )

# =========================
# Instagram Reset Core Logic (Optimized & Async)
# =========================

async def send_reset_email_async(target: str, client: httpx.AsyncClient) -> str:
    """Method 1: Tries to send a reset link via a web ajax endpoint."""
    try:
        response = await client.post(
            'https://www.instagram.com/accounts/account_recovery_send_ajax/',
            headers={'X-Requested-With': 'XMLHttpRequest'},
            data={'email_or_username': target, 'recaptcha_challenge_field': ''}
        )
        if response.status_code == 200 and 'email_sent' in response.text:
            match = re.search('<b>(.*?)</b>', response.text)
            email = match.group(1) if match else 'an associated account'
            return f"METHOD 1: Success (Sent to {email})"
        return "METHOD 1: Failed"
    except Exception as e:
        logger.error(f"IG Reset Method 1 failed for {target}: {e}")
        return "METHOD 1: Error"

async def send_reset_advanced_async(target: str, client: httpx.AsyncClient) -> str:
    """Method 2: Gets user ID and uses the mobile API endpoint."""
    try:
        # First, get the user ID from the web profile
        profile_url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={target}"
        profile_res = await client.get(profile_url, headers={'X-IG-App-ID': '936619743392459'})
        user_id = profile_res.json()['data']['user']['id']
        
        # Then, use the user ID to send the reset link
        reset_url = 'https://i.instagram.com/api/v1/accounts/send_password_reset/'
        headers = {'User-Agent': 'Instagram 6.12.1 Android (30/11; 480dpi; 1080x2004; HONOR; ANY-LX2; HNANY-Q1; qcom; ar_EG_#u-nu-arab)'}
        data = {'user_id': user_id, 'device_id': str(uuid.uuid4())}
        reset_res = await client.post(reset_url, headers=headers, data=data)
        
        if 'obfuscated_email' in reset_res.text:
            email = reset_res.json()['obfuscated_email']
            return f"METHOD 2: Success (Sent to {email})"
        return f"METHOD 2: Failed ({reset_res.json().get('message', 'No message')})"
    except Exception as e:
        logger.error(f"IG Reset Method 2 failed for {target}: {e}")
        return "METHOD 2: Error or User Not Found"

async def send_reset_web_async(target: str, client: httpx.AsyncClient) -> str:
    """Method 3: Uses a different web API endpoint."""
    try:
        headers = {
            'x-csrftoken': 'missing', 'x-ig-app-id': '936619743392459',
            'x-requested-with': 'XMLHttpRequest', 'x-web-session-id': 'ag36cv:1ko17s:9bxl9b'
        }
        data = {'email_or_username': target, 'flow': 'fxcal'}
        response = await client.post('https://www.instagram.com/api/v1/web/accounts/account_recovery_send_ajax/', headers=headers, data=data)
        
        res_json = response.json()
        if res_json.get('status') == 'ok':
            return f"METHOD 3: Success ({res_json.get('message', 'OK')})"
        else:
            return f"METHOD 3: Failed ({res_json.get('message', 'Unknown Error')})"
    except Exception as e:
        logger.error(f"IG Reset Method 3 failed for {target}: {e}")
        return "METHOD 3: Error"

async def process_target_concurrently(target: str) -> str:
    """Runs all three reset methods at the same time for one target."""
    async with httpx.AsyncClient(timeout=20) as client:
        tasks = [
            send_reset_email_async(target, client),
            send_reset_advanced_async(target, client),
            send_reset_web_async(target, client),
        ]
        results = await asyncio.gather(*tasks)
    return "\n".join(results)

# =========================
# Command & Message Handlers
# =========================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start command. Checks membership and shows appropriate message."""
    if await has_joined_all(update.effective_user.id, context):
        await show_main_menu(update, context)
    else:
        await send_join_prompt(update, context)

async def check_joined_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'I Have Joined All' button press."""
    query = update.callback_query
    await query.answer()
    if await has_joined_all(query.from_user.id, context):
        await query.edit_message_text("✅ Welcome! You can now use the bot.")
        await show_main_menu(update, context)
    else:
        await query.answer("❌ You haven't joined all the required channels yet. Please join them and try again.", show_alert=True)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the main menu keyboard."""
    markup = ReplyKeyboardMarkup([
        [KeyboardButton("/reset")], [KeyboardButton("/bulk_reset")], [KeyboardButton("/help")]
    ], resize_keyboard=True)
    
    # Determine the correct message object to use
    message_obj = update.message or update.callback_query.message

    await message_obj.reply_text(
        "Bot Menu:\nSelect a command to proceed.",
        reply_markup=markup
    )

async def help_command(message: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the help message."""
    await message.message.reply_text(
        "Help Guide\n\n"
        "/reset - Start the process to reset a single account.\n"
        "/bulk_reset - Start the process to reset multiple accounts.\n"
        "/help - Show this help message."
    )

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Asks for the target for a single reset."""
    await update.message.reply_text("🔑 Enter the Instagram username or email:")
    return AWAITING_TARGET

async def bulk_reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Asks for targets for a bulk reset."""
    await update.message.reply_text(
        "📝 Enter multiple Instagram usernames/emails (one per line, max 10):\n\n"
        "Example:\n"
        "username1\n"
        "email@gmail.com\n"
        "username2"
    )
    return AWAITING_BULK

async def handle_single_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processes the single target provided by the user."""
    target = update.message.text.strip()
    await update.message.reply_text(f"⏳ Processing {target}... This may take a moment.")
    
    result = await process_target_concurrently(target)
    
    await update.message.reply_text(f"📊 Results for {target}:\n\n{result}")
    await show_main_menu(update, context)
    return ConversationHandler.END

async def handle_bulk_targets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processes the bulk targets provided by the user."""
    targets = [t.strip() for t in update.message.text.strip().split('\n') if t.strip()][:10]
    if not targets:
        await update.message.reply_text("No valid targets provided. Please try again.")
        return AWAITING_BULK

    await update.message.reply_text(f"⏳ Processing {len(targets)} targets concurrently...")
    
    tasks = [process_target_concurrently(target) for target in targets]
    all_results = await asyncio.gather(*tasks)
    
    final_report = []
    for target, result in zip(targets, all_results):
        final_report.append(f"📊 Results for {target}:\n{result}")
    
    await update.message.reply_text("\n\n---\n\n".join(final_report))
    await show_main_menu(update, context)
    return ConversationHandler.END

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the current operation."""
    await update.message.reply_text("Operation cancelled.", reply_markup=ReplyKeyboardRemove())
    await show_main_menu(update, context)
    return ConversationHandler.END

async def pre_command_check(update: Update, context: ContextTypes.DEFAULT_TYPE, command_handler):
    """Wrapper to check membership before executing a command."""
    if await has_joined_all(update.effective_user.id, context):
        return await command_handler(update, context)
    else:
        await send_join_prompt(update, context)
        return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}", exc_info=context.error)
    if update and update.effective_message: await update.message.reply_text("An unexpected error occurred.")

# =========================
# Bot Setup & Web Server
# =========================

async def initialize_bot():
    """Robust bot initialization."""
    global application
    logger.info("Starting bot initialization...")
    if not WEBHOOK_URL:
        bot_status.update({"initialized": False, "error": "WEBHOOK_URL not set."})
        logger.critical("FATAL: WEBHOOK_URL is not set. Bot cannot start.")
        return

    try:
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("reset", lambda u, c: pre_command_check(u, c, reset_command)),
                CommandHandler("bulk_reset", lambda u, c: pre_command_check(u, c, bulk_reset_command))
            ],
            states={
                AWAITING_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_single_target)],
                AWAITING_BULK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bulk_targets)],
            },
            fallbacks=[CommandHandler("cancel", cancel_command)],
        )
        
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(check_joined_callback, pattern="^check_joined$"))
        application.add_handler(conv_handler)
        application.add_handler(CommandHandler("help", lambda u, c: pre_command_check(u, c, help_command)))
        application.add_handler(MessageHandler(filters.COMMAND, start_command)) # Fallback for unknown commands
        application.add_error_handler(error_handler)
        
        await application.initialize()
        await application.start()
        
        await application.bot.set_my_commands([
            BotCommand("start", "Start or return to menu"),
            BotCommand("reset", "Reset a single IG account"),
            BotCommand("bulk_reset", "Reset multiple IG accounts"),
            BotCommand("help", "Get help"),
        ])
        
        full_webhook_url = f"{WEBHOOK_URL.rstrip('/')}/{TELEGRAM_TOKEN}"
        await application.bot.set_webhook(full_webhook_url, allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        
        webhook_info = await application.bot.get_webhook_info()
        bot_status["details"]["webhook_info"] = webhook_info.to_dict()
        
        if webhook_info.url == full_webhook_url:
            logger.info("SUCCESS: Webhook verification passed.")
            bot_status.update({"initialized": True, "webhook_verified": True, "error": None})
        else:
            error_msg = f"Webhook verification FAILED. Expected '{full_webhook_url}', but got '{webhook_info.url}'"
            logger.critical(f"FATAL: {error_msg}")
            bot_status.update({"initialized": False, "webhook_verified": False, "error": error_msg})

    except Exception as e:
        bot_status.update({"initialized": False, "webhook_verified": False, "error": str(e)})
        logger.critical(f"FATAL ERROR during bot initialization: {e}", exc_info=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages bot startup and shutdown."""
    asyncio.create_task(initialize_bot())
    yield
    if application: await application.stop()

app = FastAPI(title="Instagram Reset Bot", lifespan=lifespan)

@app.get("/health", include_in_schema=False)
async def health_check():
    """Diagnostic endpoint to check bot status."""
    if bot_status["initialized"] and bot_status["webhook_verified"]:
        return JSONResponse(content={"status": "ok", "message": "Bot is initialized and webhook is verified.", "details": bot_status})
    else:
        return JSONResponse(content={"status": "error", "message": "Bot is not healthy.", "details": bot_status}, status_code=503)

@app.post("/{token}")
async def webhook_endpoint(token: str, request: Request):
    if token != TELEGRAM_TOKEN: return JSONResponse(content={"status": "invalid token"}, status_code=401)
    if not (application and bot_status["initialized"]): 
        return JSONResponse(content={"status": "service unavailable, bot not initialized"}, status_code=503)
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return JSONResponse(content={"status": "error"}, status_code=500)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

