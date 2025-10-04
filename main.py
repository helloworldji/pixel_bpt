import os
import logging
import asyncio
import uuid
import string
import random
import httpx
import re
from telegram import Update, BotCommand, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters
)
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
import uvicorn
import io
import json
from contextlib import asynccontextmanager
import qrcode
from typing import Tuple

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

# Validate required environment variables
if not TELEGRAM_TOKEN:
    logger.critical("FATAL: TELEGRAM_BOT_TOKEN environment variable not set. Bot cannot start.")
    exit(1)

# Global variables to track bot status for health checks
application = None
bot_status = {"initialized": False, "webhook_verified": False, "error": None, "details": {}}

# Conversation states
MAIN_MENU, INSTA_MODE = range(2)

# =========================
# Core Features
# =========================

async def send_password_reset(target: str, client: httpx.AsyncClient) -> Tuple[bool, str]:
    """Sends a password reset request and returns a status tuple."""
    try:
        data = {'guid': str(uuid.uuid4()), 'device_id': str(uuid.uuid4())}
        if '@' in target: data['user_email'] = target
        elif target.isdigit(): data['user_id'] = target
        else: data['username'] = target

        headers = {'user-agent': f"Instagram 150.0.0.0.000 Android (29/10; 300dpi; 720x1440; {''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}/{''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}; {''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}; {''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}; en_GB;)"}
        
        response = await client.post('https://i.instagram.com/api/v1/accounts/send_password_reset/', headers=headers, data=data)
        
        if response.status_code == 404:
            return False, f"User Not Found: The account '{target}' does not exist."
        
        if 'obfuscated_email' in response.text:
            return True, f"Password reset link sent for '{target}'."
        
        try:
            error_message = response.json().get('message', response.text)
            return False, f"Failed for '{target}': {error_message}"
        except json.JSONDecodeError:
            return False, f"Failed for '{target}': {response.text}"
            
    except httpx.RequestError as e:
        logger.error(f"Network error during password reset for {target}: {e}")
        return False, f"Network Error for '{target}'."
    except Exception as e:
        logger.error(f"Exception during password reset for {target}: {e}")
        return False, f"An unexpected error occurred for '{target}'."

# =========================
# Command Handlers & Conversation Flow
# =========================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - entry point to main menu."""
    try:
        user = update.effective_user
        reply_keyboard = [
            ["Instagram Reset"],
            ["Generate Password", "Shorten URL"],
            ["Create QR Code", "Help"]
        ]
        welcome_message = (
            f"Hello {user.first_name}!\n\n"
            "Welcome to the Utility Bot.\n\n"
            "Select a feature to get started:\n"
            "- Instagram Reset\n"
            "- Generate Password\n"
            "- Shorten URL\n"
            "- Create QR Code\n\n"
            f"Developed by {DEV_HANDLE}"
        )
        await update.message.reply_text(
            welcome_message,
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True, one_time_keyboard=True)
        )
        return MAIN_MENU
    except Exception as e:
        logger.error(f"Error in start_command: {e}")
        await update.message.reply_text("Welcome! Please select a feature using the keyboard.")
        return MAIN_MENU

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle main menu selections."""
    text = update.message.text
    if text == "Instagram Reset":
        return await switch_to_insta_mode(update, context)
    elif text == "Generate Password":
        await update.message.reply_text("Send /genpass or /genpass <length> to create a password.", reply_markup=ReplyKeyboardRemove())
    elif text == "Shorten URL":
        await update.message.reply_text("Send /shorten <your_url> to get a short link.", reply_markup=ReplyKeyboardRemove())
    elif text == "Create QR Code":
        await update.message.reply_text("Send /qr <text_or_url> to generate a QR code.", reply_markup=ReplyKeyboardRemove())
    elif text == "Help":
        await help_command(update, context)
    return MAIN_MENU

async def switch_to_insta_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = (
        "Instagram Reset Mode Activated.\n\n"
        "Available Commands:\n"
        "/rst <username> - Reset by username\n"
        "/blk <user1> <user2> - Bulk reset (max 3)\n\n"
        "Use /mode to return to the menu."
    )
    await update.message.reply_text(message, reply_markup=ReplyKeyboardRemove())
    return INSTA_MODE

async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Returns the user to the main menu."""
    return await start_command(update, context)

# --- Feature-Specific Handlers ---
async def insta_reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /rst <target>")
        return INSTA_MODE
    target = context.args[0].strip()
    processing_msg = await update.message.reply_text(f"Processing reset for: {target}...")
    
    # REMOVED: Proxy logic has been completely removed.
    async with httpx.AsyncClient(timeout=30) as client:
        success, message = await send_password_reset(target, client)
    
    icon = "✅" if success else "❌"
    formatted_message = f"{icon} {message}"
        
    await processing_msg.edit_text(formatted_message)
    return INSTA_MODE

async def insta_bulk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /blk user1 user2 ...\n(Max 3 accounts)")
        return INSTA_MODE
        
    targets = list(set([t.strip() for t in context.args[:3] if t.strip()]))
    processing_msg = await update.message.reply_text(f"Processing {len(targets)} accounts concurrently...")
    
    # REMOVED: Proxy logic has been completely removed.
    async with httpx.AsyncClient(timeout=30) as client:
        tasks = [send_password_reset(target, client) for target in targets]
        results = await asyncio.gather(*tasks)
    
    formatted_results = []
    for success, message in results:
        icon = "✅" if success else "❌"
        formatted_results.append(f"{icon} {message}")

    final_text = "Bulk Reset Complete:\n\n" + "\n\n".join(formatted_results)
    await processing_msg.edit_text(final_text)
    return INSTA_MODE

async def insta_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Instagram Reset Mode: Use /rst or /blk to proceed.")
    return INSTA_MODE

async def genpass_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        length = int(context.args[0]) if context.args else 16
        if not 8 <= length <= 64:
            await update.message.reply_text("Please choose a length between 8 and 64.")
            return
        
        chars = string.ascii_letters + string.digits + string.punctuation
        password = ''.join(random.choice(chars) for _ in range(length))
        
        sent_message = await update.message.reply_text(
            f"Generated Password ({length} characters):\n`{password}`\n\nThis message will be deleted in 1 minute."
        )

        asyncio.create_task(delete_messages_after_delay(
            messages_to_delete=[sent_message, update.message],
            delay=60
        ))

    except (ValueError, IndexError):
        await update.message.reply_text("Invalid length. Usage: /genpass <number between 8-64>")

async def delete_messages_after_delay(messages_to_delete: list, delay: int):
    """Waits for a specified delay and then deletes a list of messages."""
    await asyncio.sleep(delay)
    for msg in messages_to_delete:
        try:
            await msg.delete()
        except Exception as e:
            logger.warning(f"Could not delete message {msg.message_id}: {e}")


async def shorten_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /shorten <url>")
        return
    
    long_url = context.args[0]
    if not re.match(r'http[s]?://', long_url):
        long_url = 'http://' + long_url
        
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://tinyurl.com/api-create.php?url={long_url}")
        
        if response.status_code == 200:
            await update.message.reply_text(f"Shortened URL: {response.text}")
        else:
            await update.message.reply_text(f"Error: Could not shorten URL (Status: {response.status_code})")
    except httpx.RequestError as e:
        logger.error(f"URL shortener failed: {e}")
        await update.message.reply_text("Error: Could not connect to the URL shortening service.")

async def qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /qr <text or url>")
        return
        
    text_to_encode = " ".join(context.args)
    
    buffer = io.BytesIO()
    qrcode.make(text_to_encode).save(buffer, "PNG")
    buffer.seek(0)
    
    await update.message.reply_photo(photo=buffer, caption=f"QR Code for: {text_to_encode}")

# --- Help, About, Error ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = (
        "Help Guide:\n\n"
        "/start or /mode - Return to the main menu.\n"
        "/rst <target> - Reset an Instagram account.\n"
        "/blk <targets> - Bulk reset IG accounts.\n"
        "/genpass <len> - Generate a secure password.\n"
        "/shorten <url> - Shorten a long URL.\n"
        "/qr <text> - Create a QR code."
    )
    await update.message.reply_text(message)

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Multi-utility bot by {DEV_HANDLE}.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}", exc_info=context.error)
    if update and update.effective_message: await update.message.reply_text("An unexpected error occurred.")

# =========================
# Bot Setup & Web Server
# =========================

async def initialize_bot():
    """Robust bot initialization with detailed logging and webhook verification."""
    global application
    logger.info("Starting bot initialization...")
    if not WEBHOOK_URL:
        bot_status.update({"initialized": False, "error": "WEBHOOK_URL not set."})
        logger.critical("FATAL: WEBHOOK_URL is not set. Bot cannot start.")
        return

    try:
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start_command)],
            states={
                MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_handler)],
                INSTA_MODE: [CommandHandler("rst", insta_reset_command), CommandHandler("blk", insta_bulk_command), MessageHandler(filters.TEXT & ~filters.COMMAND, insta_mode_handler)],
            },
            fallbacks=[CommandHandler("mode", mode_command)],
            allow_reentry=True
        )
        application.add_handler(conv_handler)
        application.add_handler(CommandHandler("genpass", genpass_command))
        application.add_handler(CommandHandler("shorten", shorten_command))
        application.add_handler(CommandHandler("qr", qr_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("about", about_command))
        application.add_error_handler(error_handler)
        
        logger.info("PTB application configured. Initializing...")
        await application.initialize()
        await application.start()
        
        await application.bot.set_my_commands([
            BotCommand("start", "Show main menu"), BotCommand("mode", "Return to menu"),
            BotCommand("rst", "Reset an IG account"), BotCommand("blk", "Bulk reset IG accounts"),
            BotCommand("genpass", "Generate a password"), BotCommand("shorten", "Shorten a URL"),
            BotCommand("qr", "Create a QR code"), BotCommand("help", "Get help"),
        ])
        
        full_webhook_url = f"{WEBHOOK_URL.rstrip('/')}/{TELEGRAM_TOKEN}"
        logger.info(f"Attempting to set webhook to: {full_webhook_url}")
        await application.bot.set_webhook(full_webhook_url, allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        
        await asyncio.sleep(1)
        webhook_info = await application.bot.get_webhook_info()
        bot_status["details"]["webhook_info"] = webhook_info.to_dict()
        
        if webhook_info.url == full_webhook_url:
            logger.info("SUCCESS: Webhook verification passed.")
            bot_status.update({"initialized": True, "webhook_verified": True, "error": None})
        else:
            error_msg = f"Webhook verification FAILED. Expected '{full_webhook_url}', but got '{webhook_info.url}'"
            logger.critical(f"FATAL: {error_msg}")
            bot_status.update({"initialized": False, "webhook_verified": False, "error": error_msg})

        logger.info("Bot initialization process finished.")
        
    except Exception as e:
        error_str = str(e)
        bot_status.update({"initialized": False, "webhook_verified": False, "error": error_str})
        logger.critical(f"FATAL ERROR during bot initialization: {e}", exc_info=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages bot startup and shutdown."""
    asyncio.create_task(initialize_bot())
    yield
    if application: logger.info("Shutting down..."); await application.stop()

app = FastAPI(title="Telegram Utility Bot", lifespan=lifespan)

@app.get("/", include_in_schema=False)
async def root_path():
    return JSONResponse(content={"status": "ok", "message": "Bot server is running. Use /health for status."})


@app.get("/health", include_in_schema=False)
async def health_check():
    if bot_status["initialized"] and bot_status["webhook_verified"]:
        return JSONResponse(content={"status": "ok", "message": "Bot is initialized and webhook is verified.", "details": bot_status["details"]})
    else:
        return JSONResponse(
            content={"status": "error", "message": "Bot is not healthy.", "details": bot_status},
            status_code=503
        )

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

