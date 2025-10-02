# main.py

# ==============================================================================
# Standard Library Imports
# ==============================================================================
import os
import logging
import asyncio
import uuid
import string
import random
import io
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any, AsyncGenerator

# ==============================================================================
# Third-Party Library Imports
# ==============================================================================
import uvicorn
import httpx
import google.generativeai as genai
from PIL import Image
from fastapi import FastAPI, Request, HTTPException
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode
from google.generativeai.types import GenerationConfig

# ==============================================================================
# Logging Configuration
# ==============================================================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==============================================================================
# Environment Variable & API Configuration
# ==============================================================================
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

if not BOT_TOKEN or not GEMINI_API_KEY:
    logger.critical("FATAL: Missing TELEGRAM_BOT_TOKEN or GEMINI_API_KEY.")
    exit(1)

# Configure safety settings to be less restrictive, reducing false positives.
SAFETY_SETTINGS = {
    "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
    "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
    "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
}

try:
    genai.configure(api_key=GEMINI_API_KEY)
    # Model for text-only chat
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
    # A dedicated model for vision tasks with a specific system instruction for more reliable outputs.
    gemini_vision_model = genai.GenerativeModel(
        'gemini-2.5-flash-preview-05-20',
        system_instruction="You are an expert image analyst. Your task is to analyze the provided image. If it primarily contains text (like a screenshot or document), perform OCR and return ONLY the extracted text, without any additional comments, formatting, or explanations. If the image is a photograph, describe its contents, context, and any notable elements in detail."
    )
    logger.info("Successfully initialized Gemini AI models.")
except Exception as e:
    logger.critical(f"FATAL: Failed to initialize Gemini AI: {e}", exc_info=True)
    exit(1)

# ==============================================================================
# Global State Management
# ==============================================================================
telegram_app: Optional[Application] = None
# NOTE: User sessions are stored in-memory. They will be lost on restart.
# For production, consider using a persistent store like Redis or a database.
user_sessions: Dict[int, Dict] = {}

# ==============================================================================
# User Session Management
# ==============================================================================
def get_user_session(user_id: int) -> Dict[str, Any]:
    """
    Retrieves or creates a session for a given user ID.
    Each session stores the user's current mode and chat history.
    """
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            'mode': 'menu',
            'history': []
        }
    return user_sessions[user_id]

def set_user_mode(user_id: int, mode: str) -> None:
    """Sets the interaction mode for a specific user's session."""
    session = get_user_session(user_id)
    session['mode'] = mode
    logger.info(f"User {user_id} switched to mode: {mode}")

def get_user_mode(user_id: int) -> str:
    """Gets the current interaction mode from a user's session."""
    return get_user_session(user_id).get('mode', 'menu')

# ==============================================================================
# Helper Utilities
# ==============================================================================
def split_long_message(text: str, max_length: int = 4096) -> List[str]:
    """
    Splits a long message into smaller chunks that respect Telegram's
    message length limit, prioritizing splits at newlines for readability.
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        split_at = text.rfind('\n', 0, max_length)
        if split_at == -1:
            split_at = max_length
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()
    return chunks

def compress_image(image_bytes: bytes, max_size_kb: int = 1024) -> bytes:
    """
    Compresses an image to reduce its file size, improving performance.
    Converts image to RGB, resizes, and optimizes JPEG quality.
    """
    original_size = len(image_bytes) / 1024
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ('RGBA', 'P', 'LA'):
            img = img.convert('RGB')
        
        img.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
        
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=85, optimize=True)
        
        if buffer.tell() / 1024 > max_size_kb:
             buffer = io.BytesIO()
             img.save(buffer, format='JPEG', quality=70, optimize=True)
        
        compressed_bytes = buffer.getvalue()
        new_size = len(compressed_bytes) / 1024
        logger.info(f"Image compressed from {original_size:.2f} KB to {new_size:.2f} KB.")
        return compressed_bytes
    except Exception as e:
        logger.error(f"Image compression failed: {e}", exc_info=True)
        return image_bytes

# ==============================================================================
# Instagram API Interaction
# ==============================================================================
async def send_instagram_reset(target_identifier: str) -> Dict[str, Any]:
    """
    Sends a password reset request to Instagram's internal API using an
    updated client signature to avoid blocks.
    """
    api_url = 'https://i.instagram.com/api/v1/accounts/send_password_reset/'
    headers = {
        'User-Agent': 'Instagram 294.0.0.33.110 Android (29/10; 300dpi; 720x1440; OnePlus; GM1903; OnePlus7; qcom; en_US; 50322223)',
        'X-IG-App-ID': '936619743392459',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
    }
    
    payload = {
        '_csrftoken': ''.join(random.choices(string.ascii_letters + string.digits, k=32)),
        'guid': str(uuid.uuid4()),
        'device_id': str(uuid.uuid4())
    }
    
    clean_target = target_identifier.strip().lstrip('@')
    
    if '@' in clean_target and '.' in clean_target:
        payload['user_email'] = clean_target
    elif clean_target.isdigit():
        payload['user_id'] = clean_target
    else:
        payload['username'] = clean_target

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(api_url, headers=headers, data=payload)
        
        logger.info(f"Instagram API response for '{clean_target}': {response.status_code} - {response.text[:150]}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                if data.get('status') == 'ok':
                    contact_point = data.get('obfuscated_email', 'the registered contact point')
                    return {'success': True, 'message': f"✅ Reset link sent to {contact_point} for: `{clean_target}`"}
                else:
                    return {'success': False, 'message': f"⚠️ Request failed: {data.get('message', 'User may not exist.')}"}
            except Exception:
                return {'success': False, 'message': f"⚠️ Request sent, but received an invalid response."}
        elif response.status_code == 400:
            return {'success': False, 'message': f"❌ Bad Request (400). Instagram may have blocked requests. Please try again later."}
        elif response.status_code == 404:
            return {'success': False, 'message': f"❌ Account not found: `{clean_target}`"}
        elif response.status_code == 429:
            return {'success': False, 'message': f"⏳ Rate limited. Please wait a few minutes."}
        else:
            return {'success': False, 'message': f"❌ Unknown error for `{clean_target}` (Status: {response.status_code})"}
            
    except httpx.RequestError as e:
        logger.error(f"HTTP error during Instagram reset for '{clean_target}': {e}", exc_info=True)
        return {'success': False, 'message': f"❌ Network error. Please try again."}
    except Exception as e:
        logger.error(f"Unexpected error during Instagram reset: {e}", exc_info=True)
        return {'success': False, 'message': f"❌ An unexpected internal error occurred."}

# ==============================================================================
# Telegram Command Handlers
# ==============================================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start and /menu commands, showing the main menu."""
    user = update.effective_user
    set_user_mode(user.id, 'menu')
    
    keyboard = [
        ["🔓 Instagram Reset"],
        ["💬 AI Chat", "🖼️ Image Analysis"],
        ["❓ Help"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    welcome_text = (
        f"👋 *Welcome, {user.first_name}!* 👋\n\n"
        "I am a multi-function bot. Here's what I can do:\n\n"
        "🔓 *Instagram Reset*: Send password reset links.\n"
        "💬 *AI Chat*: Talk with an advanced AI.\n"
        "🖼️ *Image Analysis*: Get text (OCR) or insights from images.\n\n"
        "Please select an option from the menu below."
    )
    try:
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error in start_command for user {user.id}: {e}", exc_info=True)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /help command, showing detailed instructions."""
    help_text = """
*🤖 Bot Help & Instructions 🤖*

*GENERAL COMMANDS*
`/start` or `/menu` - Show the main menu.
`/help` - Show this help message.

---
*MODES OF OPERATION*

1️⃣ *Instagram Reset*
- `/rst <username_or_email>`
  Sends a single password reset link.
  *Example*: `/rst johndoe`
- `/bulk <user1> <user2> ...`
  Sends reset links for up to 5 accounts.
  *Example*: `/bulk user1 user2`

2️⃣ *AI Chat*
Select this mode from the menu, then simply send any text message to start a conversation. The AI remembers the last few messages for context.

3️⃣ *Image Analysis*
Select this mode, then send any image (photo or screenshot). The AI will analyze it to extract text (OCR) or provide a detailed description.
    """
    try:
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error in help_command for user {update.effective_user.id}: {e}", exc_info=True)

async def rst_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /rst command for a single Instagram reset."""
    user = update.effective_user
    try:
        if not context.args:
            await update.message.reply_text("Please provide a username or email.\n*Usage*: `/rst <username>`", parse_mode=ParseMode.MARKDOWN)
            return
            
        target = context.args[0]
        msg = await update.message.reply_text(f"🔄 Processing `{target}`...", parse_mode=ParseMode.MARKDOWN)
        
        result = await send_instagram_reset(target)
        await msg.edit_text(result['message'], parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error in rst_command for user {user.id}: {e}", exc_info=True)
        await update.message.reply_text("❌ An unexpected error occurred while processing your request.")

async def bulk_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /bulk command for multiple Instagram resets with progress updates."""
    user = update.effective_user
    try:
        if not context.args:
            await update.message.reply_text("Please provide at least one target.\n*Usage*: `/bulk user1 user2`", parse_mode=ParseMode.MARKDOWN)
            return
            
        targets = context.args[:5]
        msg = await update.message.reply_text(f"🔄 Processing {len(targets)} accounts...", parse_mode=ParseMode.MARKDOWN)
        
        results = []
        for i, target in enumerate(targets, 1):
            result = await send_instagram_reset(target)
            results.append(f"{i}. {result['message']}")
            progress_text = f"**Progress: {i}/{len(targets)}**\n\n" + "\n".join(results)
            try:
                await msg.edit_text(progress_text, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                pass
            if i < len(targets):
                await asyncio.sleep(2)
        
        final_text = f"✅ *Bulk processing complete!* ✅\n\n" + "\n".join(results)
        await msg.edit_text(final_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error in bulk_command for user {user.id}: {e}", exc_info=True)
        await update.message.reply_text("❌ An unexpected error occurred during the bulk operation.")

# ==============================================================================
# Telegram Message Handlers
# ==============================================================================
async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles all incoming text messages, routing them based on user mode."""
    user_id = update.effective_user.id
    text = update.message.text
    mode = get_user_mode(user_id)

    # This dictionary maps menu button text to a specific mode and a response message.
    # It makes the code cleaner and easier to add new options.
    menu_options = {
        "🔓 Instagram Reset": ("instagram", "🔓 *Instagram Reset Mode*\n\nUse `/rst <username>` or `/bulk <user1> ...`"),
        "💬 AI Chat": ("chat", "💬 *AI Chat Mode*\n\nSend me any message to start our conversation! Use `/start` to return to the menu."),
        "🖼️ Image Analysis": ("image", "🖼️ *Image Analysis Mode*\n\nSend me an image or screenshot to analyze. Use `/start` to return."),
    }

    try:
        if text in menu_options:
            new_mode, message = menu_options[text]
            set_user_mode(user_id, new_mode)
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
        elif text == "❓ Help":
            await help_command(update, context)
        elif mode == 'chat':
            await chat_with_gemini(update, context)
        elif mode == 'instagram':
            await update.message.reply_text("You are in Instagram mode. Please use `/rst` or `/bulk`.")
        elif mode == 'image':
            await update.message.reply_text("You are in Image Analysis mode. Please send an image.")
        else:
            await update.message.reply_text("Please select an option from the menu or use `/start`.")
    except Exception as e:
        logger.error(f"Error in text_message_handler for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("An error occurred. Please try again or use /start.")

async def chat_with_gemini(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the conversation logic with the Gemini AI model."""
    user_id = update.effective_user.id
    prompt = update.message.text
    session = get_user_session(user_id)

    msg = await update.message.reply_text("🤔 Thinking...")

    try:
        chat = gemini_model.start_chat(history=session['history'])
        response = await chat.send_message_async(
            prompt,
            generation_config=GenerationConfig(temperature=0.7),
            safety_settings=SAFETY_SETTINGS
        )
        
        session['history'].extend([{"role": "user", "parts": [prompt]}, {"role": "model", "parts": [response.text]}])
        if len(session['history']) > 20:
            session['history'] = session['history'][-20:]

        await msg.delete()
        for chunk in split_long_message(response.text):
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Gemini chat error for user {user_id}: {e}", exc_info=True)
        await msg.edit_text("❌ Sorry, an error occurred with the AI. Please try again. If the problem persists, the content might be blocked.")

async def photo_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles incoming photos, sending them to Gemini for analysis."""
    user_id = update.effective_user.id
    mode = get_user_mode(user_id)

    try:
        if mode != 'image':
            await update.message.reply_text("To analyze an image, please switch to *Image Analysis* mode from the `/start` menu.", parse_mode=ParseMode.MARKDOWN)
            return

        msg = await update.message.reply_text("🖼️ Analyzing your image, please wait...")
        
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        compressed_bytes = compress_image(bytes(photo_bytes))
        image_for_ai = Image.open(io.BytesIO(compressed_bytes))
        
        # The detailed prompt is now a system instruction, leading to more consistent behavior.
        # We just need to send the image itself.
        response = await gemini_vision_model.generate_content_async(
            [image_for_ai],
            safety_settings=SAFETY_SETTINGS
        )

        await msg.delete()
        title = "📄 *Image Analysis Result*:"
        await update.message.reply_text(title, parse_mode=ParseMode.MARKDOWN)
        
        for chunk in split_long_message(response.text):
            await update.message.reply_text(chunk)
    except Exception as e:
        logger.error(f"Image analysis error for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("❌ Sorry, I couldn't process that image. Please try another one.")

# ==============================================================================
# Error Handler
# ==============================================================================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs all errors and sends a user-friendly message."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("An internal error occurred. Please try again or use /start to reset.")
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}", exc_info=True)

# ==============================================================================
# Bot & Webhook Initialization
# ==============================================================================
async def initialize_bot() -> None:
    """Initializes the bot, registers all handlers, and sets the webhook."""
    global telegram_app
    telegram_app = Application.builder().token(BOT_TOKEN).build()

    handlers: List[Any] = [
        CommandHandler("start", start_command),
        CommandHandler("menu", start_command),
        CommandHandler("help", help_command),
        CommandHandler("rst", rst_command),
        CommandHandler("bulk", bulk_command),
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler),
        MessageHandler(filters.PHOTO, photo_message_handler),
    ]
    for handler in handlers:
        telegram_app.add_handler(handler)
    telegram_app.add_error_handler(error_handler)

    await telegram_app.initialize()
    await telegram_app.start()

    if WEBHOOK_URL:
        webhook_endpoint = f"{WEBHOOK_URL}/{BOT_TOKEN}"
        await telegram_app.bot.set_webhook(url=webhook_endpoint)
        logger.info(f"Webhook successfully set to {webhook_endpoint}")
    else:
        logger.warning("WEBHOOK_URL not set. Bot will run in polling mode.")
        await telegram_app.updater.start_polling()
        
    logger.info("Bot is now running!")

async def shutdown_bot() -> None:
    """Gracefully shuts down the bot and its components."""
    if telegram_app:
        logger.info("Shutting down bot...")
        if not WEBHOOK_URL and telegram_app.updater:
            await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()
        logger.info("Bot has been shut down successfully.")

# ==============================================================================
# FastAPI Application
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manages the bot's lifecycle, starting it with FastAPI and shutting it down gracefully."""
    await initialize_bot()
    yield
    await shutdown_bot()

app = FastAPI(lifespan=lifespan)

@app.get("/", summary="Health Check")
async def health_check() -> Dict[str, str]:
    """A simple endpoint to confirm the web service is online."""
    return {"status": "ok", "bot_status": "active"}

@app.post("/{token}", summary="Telegram Webhook")
async def telegram_webhook(token: str, request: Request) -> Dict[str, Any]:
    """Endpoint to receive updates from the Telegram API via webhook."""
    if token != BOT_TOKEN:
        logger.warning(f"Received request with invalid token: {token}")
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    if not telegram_app:
        logger.error("Webhook received but bot is not initialized.")
        raise HTTPException(status_code=503, detail="Bot not ready")
        
    try:
        update_data = await request.json()
        logger.debug(f"Webhook received data: {update_data}")
        update = Update.de_json(data=update_data, bot=telegram_app.bot)
        await telegram_app.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error processing update from webhook: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

# ==============================================================================
# Main Execution Block
# ==============================================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting Uvicorn server on http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)




