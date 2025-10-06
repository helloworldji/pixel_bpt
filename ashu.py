import os
import logging
import asyncio
import uuid
import httpx
import re
import json
from telegram import Update, BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ChatType
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters
)
from telegram.error import BadRequest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
from contextlib import asynccontextmanager
from typing import List

# =========================
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
CHANNELS = [
    {"id": "-1002628211220", "name": "MAIN CHANNEL 📢", "link": "https://t.me/c/2628211220/1"},
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

# =========================
# Force Join Logic
# =========================

async def check_membership(user_id: int, channel_id: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if a user is a member of a single channel."""
    try:
        member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except BadRequest as e:
        if "user not found" in e.message.lower(): return False
        logger.error(f"Error checking membership for user {user_id} in {channel_id}: {e}. BOT MUST BE ADMIN.")
        return False
    except Exception as e:
        logger.warning(f"Could not check membership for user {user_id} in channel {channel_id}: {e}")
        return False

async def get_membership_statuses(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> List[bool]:
    """Checks all channels and returns a list of boolean statuses."""
    tasks = [check_membership(user_id, channel['id'], context) for channel in CHANNELS]
    return await asyncio.gather(*tasks)

def create_join_keyboard() -> InlineKeyboardMarkup:
    """Creates the keyboard with channel links and a verification button."""
    keyboard = [[InlineKeyboardButton(ch['name'], url=ch['link'])] for ch in CHANNELS]
    keyboard.append([InlineKeyboardButton("✅ I Have Joined All", callback_data="check_joined")])
    return InlineKeyboardMarkup(keyboard)

async def send_join_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, statuses: List[bool] = None):
    """Sends or edits the force-join message, showing a checklist if statuses are provided."""
    message_text = "🚫 ACCESS DENIED\n\n"
    
    if statuses:
        message_text += "Your membership status:\n"
        for i, channel in enumerate(CHANNELS):
            icon = "✅" if statuses[i] else "❌"
            message_text += f"{icon} {channel['name']}\n"
        message_text += "\nPlease join all channels marked with ❌ and try again."
    else:
        message_text += "You must join all our channels to use this bot.\n\n"
        message_text += "Join all channels below, then click the button to verify."

    markup = create_join_keyboard()
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(message_text, reply_markup=markup)
        else:
            await update.message.reply_text(message_text, reply_markup=markup)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            logger.info("Ignored 'Message is not modified' error.")
        else:
            raise e

# =========================
# Instagram Reset Core Logic
# =========================

async def send_reset_email_async(target: str, client: httpx.AsyncClient) -> bool:
    """Method 1: Returns True on success, False on failure."""
    try:
        response = await client.post('https://www.instagram.com/accounts/account_recovery_send_ajax/', headers={'X-Requested-With': 'XMLHttpRequest'}, data={'email_or_username': target})
        return response.status_code == 200 and 'email_sent' in response.text
    except Exception:
        return False

async def send_reset_advanced_async(target: str, client: httpx.AsyncClient) -> bool:
    """Method 2: Returns True on success, False on failure."""
    try:
        profile_res = await client.get(f"https://www.instagram.com/api/v1/users/web_profile_info/?username={target}", headers={'X-IG-App-ID': '936619743392459'})
        user_id = profile_res.json()['data']['user']['id']
        headers = {'User-Agent': 'Instagram 6.12.1 Android (30/11; 480dpi; 1080x2004; HONOR; ANY-LX2; HNANY-Q1; qcom; ar_EG_#u-nu-arab)'}
        data = {'user_id': user_id, 'device_id': str(uuid.uuid4())}
        reset_res = await client.post('https://i.instagram.com/api/v1/accounts/send_password_reset/', headers=headers, data=data)
        return 'obfuscated_email' in reset_res.text
    except Exception:
        return False

async def send_reset_web_async(target: str, client: httpx.AsyncClient) -> bool:
    """Method 3: Returns True on success, False on failure."""
    try:
        headers = {'x-csrftoken': 'missing', 'x-ig-app-id': '936619743392459', 'x-requested-with': 'XMLHttpRequest'}
        data = {'email_or_username': target, 'flow': 'fxcal'}
        response = await client.post('https://www.instagram.com/api/v1/web/accounts/account_recovery_send_ajax/', headers=headers, data=data)
        return response.json().get('status') == 'ok'
    except Exception:
        return False

async def process_target_concurrently(target: str) -> bool:
    """Runs all three reset methods concurrently and returns True if any succeed."""
    async with httpx.AsyncClient(timeout=20) as client:
        tasks = [
            send_reset_email_async(target, client),
            send_reset_advanced_async(target, client),
            send_reset_web_async(target, client),
        ]
        results = await asyncio.gather(*tasks)
    return any(results)

# =========================
# Command & Message Handlers
# =========================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles /start command. In private chats, it checks membership and shows the main menu.
    In group chats, it does nothing to prevent spam.
    """
    if update.effective_chat.type == ChatType.PRIVATE:
        statuses = await get_membership_statuses(update.effective_user.id, context)
        if all(statuses):
            await show_main_menu(update, context)
        else:
            await send_join_prompt(update, context, statuses=statuses)
    # In a group chat, the bot will not respond to /start to avoid clutter.

async def check_joined_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'I Have Joined All' button press."""
    query = update.callback_query
    user_id = query.from_user.id
    
    statuses = await get_membership_statuses(user_id, context)
    
    if all(statuses):
        await query.answer("✅ Verification successful!", show_alert=True)
        await query.edit_message_text("Welcome! You can now use the bot.")
        await show_main_menu(update, context)
    else:
        await query.answer("❌ You haven't joined all channels. Check the list below.", show_alert=True)
        await send_join_prompt(update, context, statuses=statuses)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the main menu message."""
    message_obj = update.message or update.callback_query.message
    await message_obj.reply_text(
        "Welcome!\n\n"
        "Please use the commands to interact with the bot:\n\n"
        "🔹 /rst <username> - Reset a single account.\n"
        "🔹 /blk <user1> <user2>... - Reset multiple accounts.\n\n"
        "For more information, use /help."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the help message."""
    await update.message.reply_text(
        "Help Guide\n\n"
        "This bot helps you send password reset links to Instagram accounts. It only responds to direct commands.\n\n"
        "COMMANDS:\n\n"
        "🔹 Single Reset:\n"
        "   Use the command `/rst` followed by a username.\n"
        "   Example: `/rst example.user`\n\n"
        "🔹 Bulk Reset (Max 10):\n"
        "   Use the command `/blk` followed by usernames separated by spaces.\n"
        "   Example: `/blk user1 user2 user3`"
    )
    
async def direct_reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /rst command with arguments."""
    if not context.args:
        await update.message.reply_text("Usage: /rst <username_or_email>\nExample: `/rst example.user`")
        return

    target = context.args[0].strip()
    processing_msg = await update.message.reply_text(f"⏳ Processing reset for {target}...")
    
    success = await process_target_concurrently(target)
    
    icon = "✅" if success else "❌"
    status_text = "Reset link sent" if success else "Failed to send reset link"
    
    await processing_msg.edit_text(f"{icon} {status_text} for {target}.")

async def direct_bulk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /blk command with arguments."""
    targets = [t.strip() for t in context.args if t.strip()][:10]
    if not targets:
        await update.message.reply_text("Usage: /blk <user1> <user2> ...\nExample: `/blk user1 user2`")
        return

    await update.message.reply_text(f"⏳ Processing {len(targets)} targets concurrently...")
    
    tasks = {target: asyncio.create_task(process_target_concurrently(target)) for target in targets}
    
    final_report = ["📊 Bulk Reset Complete:"]
    for target, task in tasks.items():
        success = await task
        icon = "✅" if success else "❌"
        status_text = "Reset link sent" if success else "Failed"
        final_report.append(f"{icon} {target} - {status_text}")
    
    await update.message.reply_text("\n".join(final_report))

async def pre_command_check(update: Update, context: ContextTypes.DEFAULT_TYPE, command_handler):
    """Wrapper to check membership before executing a command. Skips check in group chats."""
    # In groups, anyone can use commands. The check is bypassed.
    if update.effective_chat.type != ChatType.PRIVATE:
        return await command_handler(update, context)

    # In private chats, membership is required.
    if all(await get_membership_statuses(update.effective_user.id, context)):
        return await command_handler(update, context)
    else:
        await send_join_prompt(update, context)
        return None

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Logs errors and sends a user-friendly message."""
    logger.error(f"Update {update} caused error: {context.error}", exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="An unexpected error occurred. Please try again.")
        except Exception as e:
            logger.error(f"Failed to send error message to chat {update.effective_chat.id}: {e}")

# =========================
# Bot Setup & Web Server
# =========================

async def initialize_bot():
    """Robust bot initialization."""
    global application
    logger.info("Starting bot initialization...")
    if not WEBHOOK_URL:
        bot_status.update({"initialized": False, "error": "WEBHOOK_URL not set."})
        logger.critical("FATAL: WEBHOOK_URL is not set.")
        return

    try:
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Core command handlers
        application.add_handler(CommandHandler("start", start_command)) # This now only works effectively in private chat
        application.add_handler(CallbackQueryHandler(check_joined_callback, pattern="^check_joined$"))
        application.add_handler(CommandHandler("rst", lambda u, c: pre_command_check(u, c, direct_reset_command)))
        application.add_handler(CommandHandler("blk", lambda u, c: pre_command_check(u, c, direct_bulk_command)))
        application.add_handler(CommandHandler("help", lambda u, c: pre_command_check(u, c, help_command)))
        
        # The handler for general text messages has been removed to stop the bot from replying to everything.
        
        application.add_error_handler(error_handler)
        
        await application.initialize()
        await application.start()
        
        await application.bot.set_my_commands([
            BotCommand("start", "Start the bot (in private chat)"),
            BotCommand("rst", "Reset a single IG account"),
            BotCommand("blk", "Reset multiple IG accounts"),
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
    return JSONResponse(content={"status": "ok" if bot_status["initialized"] and bot_status["webhook_verified"] else "error", "details": bot_status})

@app.post("/{token}")
async def webhook_endpoint(token: str, request: Request):
    if token != TELEGRAM_TOKEN: return JSONResponse(content={"status": "invalid token"}, status_code=401)
    if not (application and bot_status["initialized"]): 
        return JSONResponse(content={"status": "service unavailable"}, status_code=503)
    try:
        data = await request.json()
        await application.process_update(Update.de_json(data, application.bot))
        return JSONResponse(content={"status": "ok"})
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return JSONResponse(content={"status": "error"}, status_code=500)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

