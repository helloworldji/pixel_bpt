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
from contextlib import asynccontextmanager
import re

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
# MODIFIED: Prioritize Render's automatic URL, fall back to user-defined WEBHOOK_URL
RENDER_EXTERNAL_URL = os.getenv('RENDER_EXTERNAL_URL')
WEBHOOK_URL = RENDER_EXTERNAL_URL if RENDER_EXTERNAL_URL else os.getenv('WEBHOOK_URL')


# Centralized developer handle for easy updates
DEV_HANDLE = "@aadi_io"

# Validate required environment variables
if not TELEGRAM_TOKEN:
    logger.critical("FATAL: TELEGRAM_BOT_TOKEN environment variable not set. Bot cannot start.")
    exit(1)
if not GEMINI_API_KEY:
    logger.critical("FATAL: GEMINI_API_KEY environment variable not set. Bot cannot start.")
    exit(1)

# Configure Gemini AI
genai.configure(api_key=GEMINI_API_KEY)

# Global variables
application = None
bot_status = {"initialized": False, "webhook_verified": False, "error": None, "details": {}}

# Conversation states
MAIN_MENU, CHAT_MODE, OCR_MODE, SSHOT_MODE, INSTA_MODE = range(5)

# Initialize Gemini model
try:
    model = genai.GenerativeModel('gemini-1.5-flash')
    logger.info("Successfully initialized Gemini model")
except Exception as e:
    logger.error(f"Failed to initialize Gemini model: {e}")
    exit(1)

# =========================
# Instagram Reset Feature
# =========================

async def send_password_reset(target: str, client: httpx.AsyncClient) -> str:
    """Send a single password reset request using a shared httpx client."""
    try:
        data = {'guid': str(uuid.uuid4()), 'device_id': str(uuid.uuid4())}
        if '@' in target: data['user_email'] = target
        elif target.isdigit(): data['user_id'] = target
        else: data['username'] = target

        headers = {'user-agent': f"Instagram 150.0.0.0.000 Android (29/10; 300dpi; 720x1440; {''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}/{''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}; {''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}; {''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}; en_GB;)"}
        
        response = await client.post('https://i.instagram.com/api/v1/accounts/send_password_reset/', headers=headers, data=data)
        
        if response.status_code == 404:
            return f"❌ *User Not Found\\!* The account `{target}` does not exist."
        
        if 'obfuscated_email' in response.text:
            return f"✅ *Success\\!* Password reset link sent for: `{target}`"
        
        try:
            error_message = response.json().get('message', response.text)
            return f"❌ *Failed* for: `{target}`\nReason: `{error_message}`"
        except json.JSONDecodeError:
            return f"❌ *Failed* for: `{target}`\nRaw Error: `{response.text}`"
            
    except httpx.RequestError as e:
        logger.error(f"Network error during password reset for {target}: {e}")
        return f"❌ *Network Error* for: `{target}`."
    except Exception as e:
        logger.error(f"Exception during password reset for {target}: {e}")
        return f"❌ *Error* for: `{target}`."

# =========================
# Image Processing
# =========================

def compress_image_sync(image_bytes, max_size=(1024, 1024), quality=85):
    """Synchronous function for image compression (to be run in a thread)."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            if image.mode in ('RGBA', 'P', 'LA'):
                image = image.convert('RGB')
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
            output_buffer = io.BytesIO()
            image.save(output_buffer, format='JPEG', quality=quality, optimize=True)
            return output_buffer.getvalue()
    except Exception as e:
        logger.error(f"Error compressing image: {e}")
        return image_bytes

async def process_image(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: int):
    """Generic async function for image processing."""
    try:
        await update.message.chat.send_action(action="typing")
        
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        compressed_bytes = await asyncio.to_thread(compress_image_sync, photo_bytes)
        image = Image.open(io.BytesIO(compressed_bytes))
        
        prompt, result_title = "", ""
        if mode == OCR_MODE:
            prompt, result_title = "Extract all text from this image.", "📝 Extracted Text:"
        elif mode == SSHOT_MODE:
            prompt, result_title = "Analyze this screenshot and suggest solutions.", "📊 Screenshot Analysis:"

        response = await model.generate_content_async([prompt, image])
        
        if response.text.strip():
            safe_text = escape_markdown(response.text.strip())
            for i, chunk in enumerate(split_long_message(safe_text)):
                full_chunk = f"*{result_title}*\n\n{chunk}" if i == 0 else chunk
                await update.message.reply_text(full_chunk, parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await update.message.reply_text("❌ No text could be extracted or analyzed.")
            
    except Exception as e:
        logger.error(f"Error in image processing (mode {mode}): {e}")
        await update.message.reply_text("❌ Sorry, an error occurred while processing the image.")
    
    return mode

# =========================
# Utility Functions
# =========================

def escape_markdown(text: str) -> str:
    """Escapes special characters for Telegram MarkdownV2."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def split_long_message(text, max_length=4000):
    """Split long messages into chunks."""
    if len(text) <= max_length: return [text]
    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text); break
        split_index = text.rfind('\n', 0, max_length)
        if split_index == -1: split_index = text.rfind(' ', 0, max_length)
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
        reply_keyboard = [["Instagram Reset"], ["Chat Mode", "OCR Mode"], ["Screenshot Mode", "Help"]]
        welcome_message = escape_markdown(
            f"Hello {user.first_name}!\n\n"
            "🤖 *MULTI-FEATURE BOT*\n\n"
            "Select a mode to start:\n"
            "• *Instagram Reset* - Password recovery tool\n"
            "• *Chat Mode* - AI conversations\n"
            "• *OCR Mode* - Extract text from images\n"
            "• *Screenshot Mode* - Analyze screenshots\n\n"
            f"Developed by {DEV_HANDLE}"
        )
        await update.message.reply_text(
            welcome_message,
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return MAIN_MENU
    except Exception as e:
        logger.error(f"Error in start_command: {e}")
        await update.message.reply_text("Welcome! Please select a mode using the keyboard.")
        return MAIN_MENU

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle main menu selections."""
    mode_map = {
        "Instagram Reset": switch_to_insta_mode, "Chat Mode": switch_to_chat_mode,
        "OCR Mode": switch_to_ocr_mode, "Screenshot Mode": switch_to_sshot_mode,
        "Help": help_command
    }
    handler = mode_map.get(update.message.text)
    return await handler(update, context) if handler else MAIN_MENU

# --- Mode Switching Handlers ---
async def switch_to_insta_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = escape_markdown(
        "🔓 *INSTAGRAM RESET MODE ACTIVATED*\n\n"
        "🚀 *Available Commands:*\n"
        "`/rst username` - Reset by username\n"
        "`/blk user1 user2` - Bulk reset (max 3)\n\n"
        f"Use `/mode` to return to the menu.\nDeveloped by {DEV_HANDLE}"
    )
    await update.message.reply_text(message, reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.MARKDOWN_V2)
    return INSTA_MODE

async def switch_to_chat_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = escape_markdown(f"💬 *Switched to Chat Mode*\n\nNow you can chat with me normally.\n\nDeveloped by {DEV_HANDLE}")
    await update.message.reply_text(message, reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.MARKDOWN_V2)
    return CHAT_MODE

async def switch_to_ocr_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = escape_markdown(f"📷 *Switched to OCR Mode*\n\nSend me an image to extract text.\n\nDeveloped by {DEV_HANDLE}")
    await update.message.reply_text(message, reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.MARKDOWN_V2)
    return OCR_MODE

async def switch_to_sshot_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = escape_markdown(f"📱 *Switched to Screenshot Mode*\n\nSend me a screenshot to analyze.\n\nDeveloped by {DEV_HANDLE}")
    await update.message.reply_text(message, reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.MARKDOWN_V2)
    return SSHOT_MODE

async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start_command(update, context)

# --- Mode-Specific Handlers ---
async def insta_reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(escape_markdown("Usage: /rst <target>"), parse_mode=ParseMode.MARKDOWN_V2)
        return INSTA_MODE
    target = context.args[0].strip()
    processing_msg = await update.message.reply_text(f"🔄 Processing reset for: `{target}`...", parse_mode=ParseMode.MARKDOWN)
    
    proxy_url = "http://bgibhytx:nhrg5qvjfqy7@142.111.48.253:7030/"
    proxies = {'http://': proxy_url, 'https://': proxy_url}
    async with httpx.AsyncClient(proxies=proxies, timeout=30) as client:
        result = await send_password_reset(target, client)
        
    await processing_msg.edit_text(escape_markdown(result), parse_mode=ParseMode.MARKDOWN_V2)
    return INSTA_MODE

async def insta_bulk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """OPTIMIZED: Runs all reset requests concurrently for maximum speed."""
    if not context.args:
        await update.message.reply_text(escape_markdown("Usage: /blk user1 user2 ...\nMax 3 accounts."), parse_mode=ParseMode.MARKDOWN_V2)
        return INSTA_MODE
        
    targets = list(set([t.strip() for t in context.args[:3] if t.strip()]))
    
    processing_msg = await update.message.reply_text(f"🔄 Processing {len(targets)} accounts concurrently...")
    
    proxy_url = "http://bgibhytx:nhrg5qvjfqy7@142.111.48.253:7030/"
    proxies = {'http://': proxy_url, 'https://': proxy_url}
    async with httpx.AsyncClient(proxies=proxies, timeout=30) as client:
        tasks = [send_password_reset(target, client) for target in targets]
        results = await asyncio.gather(*tasks)
        
    final_text = "📊 *Bulk Reset Complete:*\n\n" + "\n".join(f"• {res}" for res in results)
    await processing_msg.edit_text(escape_markdown(final_text), parse_mode=ParseMode.MARKDOWN_V2)
    return INSTA_MODE

async def insta_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(escape_markdown("🔓 *IG Reset Mode*\nUse `/rst` or `/blk`."), parse_mode=ParseMode.MARKDOWN_V2)
    return INSTA_MODE

async def chat_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Optimized chat handler that reuses the chat session."""
    try:
        user_id = update.effective_user.id
        if update.message.text.startswith('/'): return CHAT_MODE
        
        if user_id not in user_conversations:
            user_conversations[user_id] = model.start_chat(history=[])
        
        await update.message.chat.send_action(action="typing")
        response = await user_conversations[user_id].send_message_async(update.message.text)
        
        for chunk in split_long_message(html.escape(response.text)):
            await update.message.reply_text(chunk)
    except Exception as e:
        logger.error(f"Error in chat mode: {e}")
        await update.message.reply_text("An error occurred. Try /newchat to reset.")
    return CHAT_MODE

async def newchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_conversations: del user_conversations[user_id]
    await update.message.reply_text("✅ Conversation history cleared.")
    return CHAT_MODE

async def ocr_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: await update.message.reply_text("📷 Please send an image."); return OCR_MODE
    return await process_image(update, context, OCR_MODE)

async def sshot_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: await update.message.reply_text("📱 Please send a screenshot."); return SSHOT_MODE
    return await process_image(update, context, SSHOT_MODE)

# --- Help, About, Error ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(escape_markdown("🤖 *HELP*\n\n/start or /mode - Main menu\n/rst <target> - Reset IG\n/blk <targets> - Bulk reset IG\n/newchat - Clear chat history"), parse_mode=ParseMode.MARKDOWN_V2)

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(escape_markdown(f"ℹ️ *ABOUT*\n\nMulti-feature bot by {DEV_HANDLE}."), parse_mode=ParseMode.MARKDOWN_V2)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}", exc_info=context.error)
    if update and update.effective_message: await update.message.reply_text("❌ An unexpected error occurred.")

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
        request = HTTPXRequest(pool_limits=httpx.Limits(max_connections=20))
        application = Application.builder().token(TELEGRAM_TOKEN).request(request).build()
        
        # Add handlers
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start_command)],
            states={
                MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_handler)],
                CHAT_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, chat_mode_handler), CommandHandler("newchat", newchat_command)],
                OCR_MODE: [MessageHandler(filters.PHOTO | filters.TEXT, ocr_mode_handler)],
                SSHOT_MODE: [MessageHandler(filters.PHOTO | filters.TEXT, sshot_mode_handler)],
                INSTA_MODE: [CommandHandler("rst", insta_reset_command), CommandHandler("blk", insta_bulk_command), MessageHandler(filters.TEXT & ~filters.COMMAND, insta_mode_handler)],
            },
            fallbacks=[CommandHandler("mode", mode_command), CommandHandler("start", start_command)],
            allow_reentry=True
        )
        application.add_handler(conv_handler)
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("about", about_command))
        application.add_error_handler(error_handler)
        
        # Initialize and start application
        logger.info("PTB application configured. Initializing...")
        await application.initialize()
        await application.start()
        
        # Set commands
        await application.bot.set_my_commands([
            BotCommand("start", "Start & select mode"), BotCommand("mode", "Return to menu"),
            BotCommand("rst", "IG single reset"), BotCommand("blk", "IG bulk reset"),
            BotCommand("newchat", "Reset chat history"), BotCommand("help", "Get help"),
            BotCommand("about", "About this bot"),
        ])
        
        # Set and verify webhook
        full_webhook_url = f"{WEBHOOK_URL.rstrip('/')}/{TELEGRAM_TOKEN}"
        logger.info(f"Attempting to set webhook to: {full_webhook_url}")
        await application.bot.set_webhook(full_webhook_url, allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        
        # NEW: Verify webhook status
        await asyncio.sleep(1) # Give Telegram a moment to process
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

app = FastAPI(title="Telegram Multi-Feature Bot", lifespan=lifespan)

@app.get("/", include_in_schema=False)
async def root_path():
    """A simple root endpoint to confirm the server is running."""
    return JSONResponse(content={"status": "ok", "message": "Bot server is running. Use /health for status."})


@app.get("/health", include_in_schema=False)
async def health_check():
    """Diagnostic endpoint to check bot status."""
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

