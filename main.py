import os
import logging
import asyncio
import html
import uuid
import string
import random
import httpx
import google.generativeai as genai
from telegram import Update, BotCommand, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters
)
from telegram.request import HTTPXRequest
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
import uvicorn
from PIL import Image
import io
import json

# =========================
# Configuration
# =========================

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# Centralized developer handle for easy updates
DEV_HANDLE = "@aadi_io"

# Validate required environment variables
if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN environment variable not set")
    exit(1)
if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY environment variable not set")
    exit(1)

# Configure Gemini AI
genai.configure(api_key=GEMINI_API_KEY)

# Initialize FastAPI app
app = FastAPI(title="Telegram Multi-Feature Bot")

# Global variable for Telegram application
application = None

# Store conversation history
user_conversations = {}

# Conversation states
MAIN_MENU, CHAT_MODE, OCR_MODE, SSHOT_MODE, INSTA_MODE = range(5)

# Initialize Gemini model (using a more robust async-first approach)
try:
    model = genai.GenerativeModel('gemini-1.5-flash')
    logger.info("Successfully initialized Gemini model")
except Exception as e:
    logger.error(f"Failed to initialize Gemini model: {e}")
    exit(1)

# =========================
# Instagram Reset Feature (Optimized with Async HTTPX)
# =========================

async def send_password_reset(target: str) -> str:
    """
    Send password reset request to Instagram using asynchronous httpx.
    This version has the proxy information hardcoded directly into it.
    """
    try:
        data = {
            '_csrftoken': ''.join(random.choices(string.ascii_letters + string.digits, k=32)),
            'guid': str(uuid.uuid4()),
            'device_id': str(uuid.uuid4())
        }
        
        if '@' in target:
            data['user_email'] = target
            log_msg = f"Attempting reset for email: {target}"
        elif target.isdigit():
            data['user_id'] = target
            log_msg = f"Attempting reset for User ID: {target}"
        else:
            data['username'] = target
            log_msg = f"Attempting reset for username: {target}"
        logger.info(log_msg)

        headers = {
            'user-agent': f"Instagram 150.0.0.0.000 Android (29/10; 300dpi; 720x1440; {''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}/{''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}; {''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}; {''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}; en_GB;)"
        }
        
        proxy_url = "http://bgibhytx:nhrg5qvjfqy7@142.111.48.253:7030/"
        proxies = {'http://': proxy_url, 'https://': proxy_url}
        
        async with httpx.AsyncClient(proxies=proxies, timeout=30) as client:
            response = await client.post(
                'https://i.instagram.com/api/v1/accounts/send_password_reset/',
                headers=headers,
                data=data
            )
        
        if response.status_code == 404:
            return f"❌ *User Not Found!* The account `{target}` does not exist."
        
        response_text = response.text
        if 'obfuscated_email' in response_text:
            return f"✅ *Success!* Password reset link sent for: `{target}`"
        else:
            try:
                error_data = response.json()
                error_message = error_data.get('message', response_text)
                return f"❌ *Failed* for: `{target}`\nReason: `{error_message}`"
            except json.JSONDecodeError:
                return f"❌ *Failed* for: `{target}`\nRaw Error: `{response_text}`"
            
    except httpx.RequestError as e:
        logger.error(f"Network error during password reset for {target}: {e}")
        return f"❌ *Network Error* for: `{target}`. Could not connect to Instagram."
    except Exception as e:
        logger.error(f"Exception during password reset for {target}: {e}")
        return f"❌ *Error* for: `{target}`\nException: `{str(e)}`"

# =========================
# Image Processing (Optimized with Async Threading)
# =========================

def compress_image_sync(image_bytes, max_size=(1024, 1024), quality=85):
    """Synchronous function for image compression (to be run in a thread)."""
    try:
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode in ('RGBA', 'P', 'LA'):
            image = image.convert('RGB')
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        output_buffer = io.BytesIO()
        image.save(output_buffer, format='JPEG', quality=quality, optimize=True)
        compressed_bytes = output_buffer.getvalue()
        logger.info(f"Image compressed from {len(image_bytes)} to {len(compressed_bytes)} bytes")
        return compressed_bytes
    except Exception as e:
        logger.error(f"Error compressing image: {e}")
        return image_bytes

async def process_image(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: int):
    """Generic async function for image processing for OCR and Screenshot modes."""
    try:
        await update.message.chat.send_action(action="typing")
        
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        compressed_bytes = await asyncio.to_thread(compress_image_sync, photo_bytes)
        image = Image.open(io.BytesIO(compressed_bytes))
        
        prompt, result_title = "", ""
        if mode == OCR_MODE:
            prompt = "Extract all the text from this image. Return only the extracted text without any additional commentary or formatting."
            result_title = "📝 Extracted Text:"
        elif mode == SSHOT_MODE:
            prompt = "Analyze this screenshot. Provide a brief overview, identify key elements, note any potential issues, and suggest solutions or best practices. Be specific and concise."
            result_title = "📊 Screenshot Analysis:"

        response = await model.generate_content_async([prompt, image])
        processed_text = response.text.strip()
        
        if processed_text:
            safe_text = html.escape(processed_text)
            message_chunks = split_long_message(safe_text)
            for i, chunk in enumerate(message_chunks):
                full_chunk = f"*{result_title}*\n\n{chunk}" if i == 0 else chunk
                await update.message.reply_text(full_chunk, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("❌ No text could be extracted or analyzed from the image.")
            
    except Exception as e:
        logger.error(f"Error in image processing (mode {mode}): {e}")
        await update.message.reply_text("❌ Sorry, I encountered an error processing the image. Please try again.")
    
    return mode

# =========================
# Utility Functions
# =========================

def split_long_message(text, max_length=4000):
    """Split long messages into chunks to avoid Telegram message limits."""
    if len(text) <= max_length: return [text]
    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        split_index = text.rfind(' ', 0, max_length)
        if split_index == -1: split_index = max_length
        chunks.append(text[:split_index])
        text = text[split_index:].strip()
    return chunks

# =========================
# Command Handlers & Conversation Flow
# =========================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - entry point to main menu."""
    try:
        user = update.effective_user
        reply_keyboard = [
            ["Instagram Reset"],
            ["Chat Mode", "OCR Mode"],
            ["Screenshot Mode", "Help"]
        ]
        welcome_message = (
            f"Hello {user.first_name}!\n\n"
            "🤖 *MULTI-FEATURE BOT*\n\n"
            "🔓 *MAIN FEATURE: INSTAGRAM PASSWORD RESET*\n\n"
            "Select a mode to start:\n"
            "• *Instagram Reset* - Password recovery tool\n"
            "• *Chat Mode* - AI conversations\n"
            "• *OCR Mode* - Extract text from images\n"
            "• *Screenshot Mode* - Analyze screenshots\n\n"
            f"⚡ Instant Access - No Verification Required\n\nDeveloped by {DEV_HANDLE}"
        )
        await update.message.reply_text(
            welcome_message,
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )
        return MAIN_MENU
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("Welcome! Use the keyboard to select a mode.")
        return MAIN_MENU

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle main menu selections."""
    mode_map = {
        "Instagram Reset": switch_to_insta_mode,
        "Chat Mode": switch_to_chat_mode,
        "OCR Mode": switch_to_ocr_mode,
        "Screenshot Mode": switch_to_sshot_mode,
        "Help": help_command
    }
    handler = mode_map.get(update.message.text)
    if handler:
        return await handler(update, context)
    else:
        await update.message.reply_text("Please select a mode from the keyboard below:")
        return MAIN_MENU

# --- Mode Switching Handlers ---
async def switch_to_insta_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔓 *INSTAGRAM RESET MODE ACTIVATED*\n\n"
        "✨ Welcome to the Instagram Password Recovery Tool ✨\n\n"
        "🚀 *Available Commands:*\n"
        "`/rst username` - Reset by username\n"
        "`/rst email@gmail.com` - Reset by email\n"
        "`/rst 1234567890` - Reset by User ID\n"
        "`/blk user1 user2` - Bulk reset (max 3 accounts)\n\n"
        f"Use `/mode` to return to the menu.\n\nDeveloped by {DEV_HANDLE}",
        reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.MARKDOWN
    )
    return INSTA_MODE

async def switch_to_chat_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💬 *Switched to Chat Mode*\n\n"
        "Now you can chat with me normally! Just send your messages and I'll respond.\n\n"
        f"Use `/mode` to return to mode selection.\n\nDeveloped by {DEV_HANDLE}",
        reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.MARKDOWN
    )
    return CHAT_MODE

async def switch_to_ocr_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📷 *Switched to OCR Mode*\n\n"
        "Now send me images and I'll extract text from them!\n\n"
        f"Use `/mode` to return to mode selection.\n\nDeveloped by {DEV_HANDLE}",
        reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.MARKDOWN
    )
    return OCR_MODE

async def switch_to_sshot_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📱 *Switched to Screenshot Mode*\n\n"
        "Now send me screenshots and I'll analyze them for issues and solutions!\n\n"
        f"Use `/mode` to return to mode selection.\n\nDeveloped by {DEV_HANDLE}",
        reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.MARKDOWN
    )
    return SSHOT_MODE

async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start_command(update, context)

# --- Mode-Specific Handlers ---
async def insta_reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /rst <username | email | user_id>")
        return INSTA_MODE
    target = context.args[0].strip()
    processing_msg = await update.message.reply_text(f"🔄 Processing reset for: `{target}`...", parse_mode=ParseMode.MARKDOWN)
    result = await send_password_reset(target)
    await processing_msg.edit_text(result, parse_mode=ParseMode.MARKDOWN)
    return INSTA_MODE

async def insta_bulk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /blk user1 user2 user3\nMax 3 accounts.")
        return INSTA_MODE
    targets = [t.strip() for t in context.args[:3] if t.strip()]
    processing_msg = await update.message.reply_text(f"🔄 Processing bulk reset for {len(targets)} accounts...")
    results = []
    for i, target in enumerate(targets, 1):
        await asyncio.sleep(2)
        result = await send_password_reset(target)
        results.append(f"{i}. {result}")
        progress_text = f"📊 *Bulk Progress: {i}/{len(targets)}*\n\n" + "\n".join(results)
        try:
            await processing_msg.edit_text(progress_text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass # Ignore if message not modified
    final_text = "📊 *Bulk Reset Complete:*\n\n" + "\n".join(results)
    await processing_msg.edit_text(final_text, parse_mode=ParseMode.MARKDOWN)
    return INSTA_MODE

async def insta_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔓 *Instagram Reset Mode Active*\n\nPlease use a command like `/rst <username>` or `/blk <user1> ...`",
        parse_mode=ParseMode.MARKDOWN
    )
    return INSTA_MODE

async def chat_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        message_text = update.message.text
        if message_text.startswith('/'):
            await update.message.reply_text("Use /mode to switch modes or /newchat to clear history.")
            return CHAT_MODE
        if user_id not in user_conversations:
            user_conversations[user_id] = model.start_chat(history=[])
        
        await update.message.chat.send_action(action="typing")
        chat_session = user_conversations[user_id]
        response = await chat_session.send_message_async(message_text)
        
        safe_response = html.escape(response.text)
        for chunk in split_long_message(safe_response):
            await update.message.reply_text(chunk)
    except Exception as e:
        logger.error(f"Error in chat mode: {e}")
        await update.message.reply_text("Sorry, an error occurred. Try /newchat to reset.")
    return CHAT_MODE

async def newchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_conversations:
        del user_conversations[user_id]
    await update.message.reply_text("✅ Conversation history cleared.")
    return CHAT_MODE

async def ocr_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("📷 Please send an image to extract text.")
        return OCR_MODE
    return await process_image(update, context, OCR_MODE)

async def sshot_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("📱 Please send a screenshot to analyze.")
        return SSHOT_MODE
    return await process_image(update, context, SSHOT_MODE)

# --- Help, About, Error ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *BOT HELP GUIDE*\n\n"
        "*/start* or */mode* - Go to the main menu.\n"
        "*/rst <target>* - Reset an Instagram account.\n"
        "*/blk <targets>* - Reset multiple IG accounts.\n"
        "*/newchat* - Clear conversation history.\n\n"
        f"Developed by {DEV_HANDLE}",
        parse_mode=ParseMode.MARKDOWN
    )

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *ABOUT THIS BOT*\n\n"
        "This is a multi-feature bot powered by Google Gemini, FastAPI, and `python-telegram-bot`.\n\n"
        f"*Developer:* {DEV_HANDLE}",
        parse_mode=ParseMode.MARKDOWN
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    if update and update.effective_message:
        await update.message.reply_text("❌ An unexpected error occurred. Please try again or use /mode.")

# =========================
# Bot Setup & Web Server
# =========================

async def setup_bot_commands(app: Application):
    commands = [
        BotCommand("start", "Start bot & select mode"),
        BotCommand("mode", "Return to mode selection"),
        BotCommand("rst", "IG single account reset"),
        BotCommand("blk", "IG bulk reset (max 3)"),
        BotCommand("newchat", "Reset conversation history"),
        BotCommand("help", "Get help guide"),
        BotCommand("about", "About this bot"),
    ]
    await app.bot.set_my_commands(commands)
    logger.info("Bot commands menu set successfully")

async def initialize_bot():
    global application
    if not WEBHOOK_URL:
        logger.error("WEBHOOK_URL environment variable is not set. Cannot initialize bot.")
        return
    
    application = Application.builder().token(TELEGRAM_TOKEN).request(HTTPXRequest()).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_handler)],
            CHAT_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, chat_mode_handler), CommandHandler("newchat", newchat_command)],
            OCR_MODE: [MessageHandler(filters.PHOTO | filters.TEXT, ocr_mode_handler)],
            SSHOT_MODE: [MessageHandler(filters.PHOTO | filters.TEXT, sshot_mode_handler)],
            INSTA_MODE: [
                CommandHandler("rst", insta_reset_command),
                CommandHandler("blk", insta_bulk_command),
                MessageHandler(filters.TEXT & ~filters.COMMAND, insta_mode_handler),
            ],
        },
        fallbacks=[CommandHandler("mode", mode_command), CommandHandler("start", start_command)],
        allow_reentry=True
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_error_handler(error_handler)
    
    await application.initialize()
    await setup_bot_commands(application)
    await application.start()
    
    full_webhook_url = f"{WEBHOOK_URL.rstrip('/')}/{TELEGRAM_TOKEN}"
    await application.bot.set_webhook(full_webhook_url)
    logger.info(f"Webhook set to: {full_webhook_url}")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(initialize_bot())

@app.on_event("shutdown")
async def shutdown_event():
    if application: await application.stop()

@app.get("/", include_in_schema=False)
async def health_check():
    return JSONResponse(content={"status": "ok"})

@app.post("/{token}")
async def webhook_endpoint(token: str, request: Request):
    if token != TELEGRAM_TOKEN:
        return JSONResponse(content={"status": "invalid token"}, status_code=401)
    if not application:
        return JSONResponse(content={"status": "service unavailable"}, status_code=503)
    
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

