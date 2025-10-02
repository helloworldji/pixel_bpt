# =================================================================================================
# 🚀 MULTI-FUNCTIONAL TELEGRAM BOT
# =================================================================================================
# This bot integrates several features:
# 1. Instagram Tools: Password reset functionality (single and bulk).
# 2. Utility Tools: URL shortening and QR code generation.
# 3. AI Features: Conversational chat and interactive image analysis using Google's Gemini AI.
# 4. Web Framework: Deployed using FastAPI and Uvicorn for webhook support.
# =================================================================================================

import os
import logging
import asyncio
import uuid
import string
import random
import io
from typing import Dict, List, Optional

import httpx
import uvicorn
import qrcode
from PIL import Image
import google.generativeai as genai
from google.generativeai.types import GenerationConfig, HarmCategory, HarmBlockThreshold

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters,
)
from telegram.constants import ParseMode
from fastapi import FastAPI, Request, HTTPException
from contextlib import asynccontextmanager

# =====================================
# LOGGING CONFIGURATION
# =====================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =====================================
# ENVIRONMENT & API KEYS
# =====================================
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

if not BOT_TOKEN or not GEMINI_API_KEY:
    logger.critical("FATAL ERROR: Bot token or Gemini API key is missing!")
    exit(1)

# =====================================
# GLOBAL VARIABLES & STATE
# =====================================
telegram_app: Optional[Application] = None
# Note: User sessions are stored in-memory. They will be lost if the bot restarts.
# For persistence, consider using a database like Redis or a simple file-based solution.
user_sessions: Dict[int, Dict] = {}
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

# =====================================
# GEMINI AI INITIALIZATION
# =====================================
try:
    genai.configure(api_key=GEMINI_API_KEY)
    # Model for general text-only chat, configured to be a friendly assistant.
    gemini_model = genai.GenerativeModel(
        'gemini-1.5-flash',
        system_instruction="You are a friendly and helpful assistant. Your responses should be informative, well-structured, and easy to understand. Use Markdown for formatting when it improves clarity."
    )
    # A dedicated, specialized model for handling vision-related tasks.
    gemini_vision_model = genai.GenerativeModel(
        'gemini-1.5-flash-latest',
        system_instruction="You are a specialized image analyst. Your primary goal is to identify problems shown in images (especially screenshots) and describe them clearly. If the image is a general photograph, simply describe its contents in detail."
    )
    logger.info("✅ Successfully initialized Gemini AI models.")
except Exception as e:
    logger.critical(f"❌ FATAL ERROR: Could not initialize Gemini AI. Error: {e}")
    exit(1)

# =====================================
# USER SESSION MANAGEMENT
# =====================================
def get_user_session(user_id: int) -> Dict:
    """Gets or creates a new session for a given user."""
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            'mode': 'menu',
            'history': [],
            'last_analysis': None
        }
    return user_sessions[user_id]

def set_user_mode(user_id: int, mode: str) -> None:
    """Sets the interaction mode for a user."""
    session = get_user_session(user_id)
    session['mode'] = mode
    logger.info(f"User {user_id} switched to mode: {mode}")

def get_user_mode(user_id: int) -> str:
    """Retrieves the current interaction mode for a user."""
    return get_user_session(user_id).get('mode', 'menu')

# =====================================
# SHARED HELPER FUNCTIONS
# =====================================
def split_long_message(text: str, max_length: int = 4096) -> List[str]:
    """Splits a long message into multiple chunks suitable for Telegram."""
    if not isinstance(text, str):
        return []
    chunks = []
    while len(text) > max_length:
        split_pos = text.rfind('\n', 0, max_length)
        if split_pos == -1:
            split_pos = max_length
        chunks.append(text[:split_pos])
        text = text[split_pos:]
    chunks.append(text)
    return chunks

# =====================================
# CORE COMMAND HANDLERS
# =====================================
async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command and displays the main menu."""
    try:
        user = update.effective_user
        user_id = user.id
        set_user_mode(user_id, 'menu')
        get_user_session(user_id)['history'].clear() # Clear history on new start

        logger.info(f"User {user.id} ({user.username}) started the bot.")

        keyboard = [
            ["🔓 Instagram Reset"],
            ["🔗 URL Shortener", "🔳 QR Code"],
            ["💬 AI Chat", "📷 Image Analysis"],
            ["❓ Help"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        welcome_text = (
            f"👋 **Welcome, {user.first_name}!**\n\n"
            "I am a multi-functional bot designed to assist you with various tasks.\n\n"
            "Here are the main tools available:\n"
            "1️⃣ **Instagram Reset**: Secure your account.\n"
            "2️⃣ **Utilities**: Shorten URLs and create QR codes.\n"
            "3️⃣ **AI Tools**: Chat with an advanced AI and get detailed image analysis.\n\n"
            "👇 Please select an option from the menu below to get started."
        )
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error in /start handler for user {update.effective_user.id}: {e}", exc_info=True)
        await update.message.reply_text("❌ A critical error occurred. Please try sending /start again.")

async def help_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /help command and displays feature instructions."""
    try:
        help_text = """
        *🤖 Bot Help & Commands Guide*

        Here's how to use my features:

        *1. Instagram Reset*
        • `/rst <username>`: Send a reset link to a single account.
        • `/bulk <user1> <user2> ...`: Send reset links to multiple accounts (max 3 per command).

        *2. URL Shortener*
        • `/shorten <your_long_url>`: Creates a short TinyURL link.

        *3. QR Code Generator*
        • `/qr <text_or_link>`: Generates a QR code image from your input.

        *4. AI Chat*
        • Select 'AI Chat' from the menu and start talking!
        • `/clear`: Clears your current conversation history with the AI.

        *5. Image Analysis*
        • Select 'Image Analysis' from the menu and send an image. The bot will identify problems and offer a solution.

        *General Commands*
        • `/start`: Shows the main menu.
        • `/menu`: An alias for `/start`.
        • `/help`: Displays this help message.
        """
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error in /help handler: {e}", exc_info=True)

# =====================================
# INSTAGRAM FEATURE [UNCHANGED]
# =====================================
async def send_instagram_reset(target: str) -> Dict:
    """Sends a password reset request to the Instagram private API."""
    try:
        clean_target = target.strip().lstrip('@')
        logger.info(f"Processing Instagram reset request for target: {clean_target}")
        
        headers = {
            'User-Agent': 'Instagram 113.0.0.39.122 Android/24 (API 24; 640dpi; 1440x2560; samsung; SM-G935F; hero2lte; samsungexynos8890; en_US)',
            'X-IG-App-ID': '936619743392459',
        }
        
        payload = {
            'device_id': f'android-{uuid.uuid4()}',
            'guid': str(uuid.uuid4()),
            '_csrftoken': ''.join(random.choices(string.ascii_letters + string.digits, k=32)),
        }

        if '@' in clean_target and '.' in clean_target:
            payload['user_email'] = clean_target
        elif clean_target.isdigit() and len(clean_target) > 5:
            payload['user_id'] = clean_target
        else:
            payload['username'] = clean_target

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                'https://i.instagram.com/api/v1/accounts/send_password_reset/',
                headers=headers,
                data=payload
            )
        
        logger.info(f"Instagram API response for {clean_target}: {response.status_code} - {response.text[:100]}")

        if response.status_code == 200:
            try:
                data = response.json()
                if 'obfuscated_email' in data or 'obfuscated_phone_number' in data:
                    return {'success': True, 'message': f"✅ Reset link successfully sent for *{clean_target}*."}
                else:
                    return {'success': False, 'message': f"⚠️ Request failed for *{clean_target}*. Response indicates an issue."}
            except Exception:
                 return {'success': False, 'message': f"⚠️ Failed to parse response for *{clean_target}*."}
        elif response.status_code == 404:
            return {'success': False, 'message': f"❌ Account not found: *{clean_target}*."}
        elif response.status_code == 400:
             return {'success': False, 'message': f"❌ Bad Request for *{clean_target}*. Check the username/email."}
        elif response.status_code == 429:
            return {'success': False, 'message': f"⏳ Rate limited. Please wait a few minutes before trying again."}
        else:
            return {'success': False, 'message': f"❌ An unknown error occurred (Status: {response.status_code}) for *{clean_target}*."}
    except httpx.RequestError as e:
        logger.error(f"HTTP error during Instagram reset for {target}: {e}")
        return {'success': False, 'message': f"❌ Network error. Could not connect to Instagram."}
    except Exception as e:
        logger.error(f"Unexpected error in send_instagram_reset for {target}: {e}", exc_info=True)
        return {'success': False, 'message': f"❌ A critical error occurred during the request."}

async def rst_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /rst command for single account resets."""
    try:
        if not context.args:
            await update.message.reply_text("📋 *Usage:* `/rst <username_or_email>`", parse_mode=ParseMode.MARKDOWN)
            return
        
        target = context.args[0]
        msg = await update.message.reply_text(f"🔄 Processing reset for *{target}*...", parse_mode=ParseMode.MARKDOWN)
        result = await send_instagram_reset(target)
        await msg.edit_text(result['message'], parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error in /rst handler for user {update.effective_user.id}: {e}", exc_info=True)
        await update.message.reply_text("❌ An unexpected error occurred while processing your request.")

async def bulk_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /bulk command for multiple account resets."""
    try:
        if not context.args:
            await update.message.reply_text("📋 *Usage:* `/bulk <user1> <user2> ...` (max 3)", parse_mode=ParseMode.MARKDOWN)
            return
            
        targets = context.args[:3]
        num_targets = len(targets)
        msg = await update.message.reply_text(f"🔄 Processing *{num_targets}* accounts...", parse_mode=ParseMode.MARKDOWN)
        
        results = []
        for i, target in enumerate(targets, 1):
            result = await send_instagram_reset(target)
            results.append(f"*{i}.* {result['message']}")
            progress_text = f"⚙️ *Progress: {i}/{num_targets}*\n\n" + "\n".join(results)
            try:
                await msg.edit_text(progress_text, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                pass 
            if i < num_targets:
                await asyncio.sleep(2) # Brief pause to avoid rate limiting

        final_text = f"✅ *Bulk processing complete for {num_targets} accounts!*\n\n" + "\n".join(results)
        await msg.edit_text(final_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error in /bulk handler for user {update.effective_user.id}: {e}", exc_info=True)
        await update.message.reply_text("❌ An unexpected error occurred during the bulk request.")

# =====================================
# UTILITY FEATURES
# =====================================
async def shorten_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /shorten command to shorten a URL using TinyURL."""
    try:
        if not context.args:
            await update.message.reply_text("📋 *Usage:* `/shorten <your_long_url>`", parse_mode=ParseMode.MARKDOWN)
            return
            
        long_url = context.args[0]
        if not long_url.startswith(('http://', 'https://')):
            await update.message.reply_text("❌ *Invalid URL*. Please include `http://` or `https://`.", parse_mode=ParseMode.MARKDOWN)
            return

        api_url = f"http://tinyurl.com/api-create.php?url={long_url}"
        msg = await update.message.reply_text(" shortening your link...", parse_mode=ParseMode.MARKDOWN)

        async with httpx.AsyncClient() as client:
            response = await client.get(api_url)
            if response.status_code == 200:
                short_url = response.text
                await msg.edit_text(f"✅ *Success!* Here is your short link:\n{short_url}", parse_mode=ParseMode.MARKDOWN)
            else:
                await msg.edit_text("❌ *Error:* Could not shorten the link. The service may be down.", parse_mode=ParseMode.MARKDOWN)
    except httpx.RequestError as e:
        logger.error(f"HTTP error during URL shortening for user {update.effective_user.id}: {e}")
        await msg.edit_text("❌ A network error occurred. Please try again later.")
    except Exception as e:
        logger.error(f"Error in /shorten handler for user {update.effective_user.id}: {e}", exc_info=True)
        await update.message.reply_text("❌ An unexpected error occurred.")
        
async def qr_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /qr command to generate a QR code."""
    try:
        if not context.args:
            await update.message.reply_text("📋 *Usage:* `/qr <text_or_link>`", parse_mode=ParseMode.MARKDOWN)
            return

        input_text = " ".join(context.args)
        msg = await update.message.reply_text("🔳 Generating your QR code...", parse_mode=ParseMode.MARKDOWN)

        # Generate QR Code in memory
        qr_img = qrcode.make(input_text)
        img_buffer = io.BytesIO()
        qr_img.save(img_buffer, format='PNG')
        img_buffer.seek(0)

        await update.message.reply_photo(
            photo=img_buffer,
            caption=f"✅ Here is the QR code for:\n`{input_text}`",
            parse_mode=ParseMode.MARKDOWN
        )
        await msg.delete() # Clean up the "generating" message
    except Exception as e:
        logger.error(f"Error in /qr handler for user {update.effective_user.id}: {e}", exc_info=True)
        await update.message.reply_text("❌ An error occurred while creating the QR code.")

# =====================================
# AI FEATURES
# =====================================
async def clear_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /clear command to reset the AI chat history."""
    try:
        user_id = update.effective_user.id
        if get_user_mode(user_id) == 'chat':
            session = get_user_session(user_id)
            session['history'].clear()
            await update.message.reply_text("AI conversation history has been cleared. You can start a new topic.")
        else:
            await update.message.reply_text("This command is only active in *AI Chat* mode.", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error in /clear handler for user {update.effective_user.id}: {e}", exc_info=True)

async def gemini_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles text messages in AI Chat mode."""
    user_id = update.effective_user.id
    prompt = update.message.text
    session = get_user_session(user_id)
    msg = await update.message.reply_text("🤔 Thinking...", parse_mode=ParseMode.MARKDOWN)

    try:
        chat = gemini_model.start_chat(history=session['history'])
        response = await chat.send_message_async(
            prompt,
            generation_config=GenerationConfig(temperature=0.8),
            safety_settings=SAFETY_SETTINGS
        )
        
        if not response.text:
            await msg.edit_text("The AI returned an empty response, possibly due to safety filters or reaching a content limit. Please try rephrasing your prompt.")
            return

        # Update history
        session['history'].extend([{"role": "user", "parts": [prompt]}, {"role": "model", "parts": [response.text]}])
        if len(session['history']) > 20: # Keep history from getting too long
            session['history'] = session['history'][-20:]

        await msg.delete()
        for chunk in split_long_message(response.text):
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.error(f"Gemini chat error for user {user_id}: {e}", exc_info=True)
        await msg.edit_text("❌ Sorry, I couldn't connect to the AI service. It might be busy or temporarily unavailable. Please try again in a moment.")

async def photo_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles incoming photos, starting the two-step analysis process."""
    user_id = update.effective_user.id
    if get_user_mode(user_id) != 'image_analysis':
        await update.message.reply_text("Please switch to *Image Analysis* mode from the menu to use this feature.", parse_mode=ParseMode.MARKDOWN)
        return

    msg = await update.message.reply_text("🔎 Analyzing your image...", parse_mode=ParseMode.MARKDOWN)
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        img = Image.open(io.BytesIO(photo_bytes))
        
        # Analyze the image for problems
        response_analysis = await gemini_vision_model.generate_content_async(
            ["Analyze this image and identify any potential problems or issues. If there are no clear problems, just describe the image.", img],
            generation_config=GenerationConfig(temperature=0.4),
            safety_settings=SAFETY_SETTINGS
        )

        analysis_text = response_analysis.text
        get_user_session(user_id)['last_analysis'] = analysis_text

        keyboard = [[InlineKeyboardButton("Yes, provide a solution", callback_data='provide_solution')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        title = "📊 *Initial Analysis*:"
        await msg.delete()
        await update.message.reply_text(
            f"{title}\n\n{analysis_text}\n\nWould you like me to suggest a solution for this?",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        logger.error(f"Image analysis error for user {user_id}: {e}", exc_info=True)
        await msg.edit_text("❌ An error occurred while processing the image. It might be an unsupported format or too large.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'provide_solution' button press."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if query.data == 'provide_solution':
        session = get_user_session(user_id)
        last_analysis = session.get('last_analysis')

        if not last_analysis:
            await query.edit_message_text(text="Sorry, the previous analysis has expired. Please send the image again.")
            return
            
        await query.edit_message_text(text=f"📊 *Initial Analysis:*\n\n{last_analysis}\n\n🧠 *Generating solution...*", parse_mode=ParseMode.MARKDOWN)

        try:
            solution_prompt = f"Based on the following problem analysis, provide a clear, step-by-step solution. Be detailed and helpful.\n\nAnalysis:\n{last_analysis}"
            response_solution = await gemini_model.generate_content_async(
                solution_prompt,
                generation_config=GenerationConfig(temperature=0.7),
                safety_settings=SAFETY_SETTINGS
            )
            
            title = "💡 *Suggested Solution*:"
            await query.message.reply_text(title, parse_mode=ParseMode.MARKDOWN)
            for chunk in split_long_message(response_solution.text):
                await query.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Solution generation error for user {user_id}: {e}", exc_info=True)
            await query.message.reply_text("❌ An error occurred while generating the solution.")

# =====================================
# MAIN MESSAGE ROUTER
# =====================================
async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Routes incoming text messages based on the user's current mode."""
    try:
        user_id = update.effective_user.id
        text = update.message.text
        mode = get_user_mode(user_id)
        
        # --- Mode Selection from Main Menu ---
        if "Instagram Reset" in text:
            set_user_mode(user_id, 'instagram')
            await update.message.reply_text("🔓 *Instagram Reset Mode*\nUse `/rst` or `/bulk`.", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
        elif "URL Shortener" in text:
            set_user_mode(user_id, 'shorten')
            await update.message.reply_text("🔗 *URL Shortener Mode*\nUse `/shorten <url>`.", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
        elif "QR Code" in text:
            set_user_mode(user_id, 'qr')
            await update.message.reply_text("🔳 *QR Code Mode*\nUse `/qr <text>`.", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
        elif "AI Chat" in text:
            set_user_mode(user_id, 'chat')
            await update.message.reply_text("💬 *AI Chat Mode*\nSend any message to start. Use `/clear` to reset history.", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
        elif "Image Analysis" in text:
            set_user_mode(user_id, 'image_analysis')
            await update.message.reply_text("📷 *Image Analysis Mode*\nSend me an image to analyze.", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
        elif "Help" in text:
            await help_command_handler(update, context)
        # --- Handle Messages Based on Active Mode ---
        elif mode == 'chat':
            await gemini_chat_handler(update, context)
        elif mode == 'instagram':
            await update.message.reply_text("Please use the `/rst` or `/bulk` commands.")
        elif mode == 'shorten':
             await update.message.reply_text("Please use the `/shorten` command.")
        elif mode == 'qr':
             await update.message.reply_text("Please use the `/qr` command.")
        elif mode == 'image_analysis':
            await update.message.reply_text("Please send an image for analysis.")
        else: # Default/menu mode
            await update.message.reply_text("Please select an option from the menu, or use /start.")
    except Exception as e:
        logger.error(f"Error in text message router for user {update.effective_user.id}: {e}", exc_info=True)

# =====================================
# GLOBAL ERROR HANDLER
# =====================================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs all errors raised by the handlers."""
    logger.error(f"Exception while handling an update:", exc_info=context.error)

# =====================================
# FASTAPI APP & BOT INITIALIZATION
# =====================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles the bot's startup and shutdown lifecycle within FastAPI."""
    global telegram_app
    logger.info("🚀 Starting bot initialization...")
    
    telegram_app = Application.builder().token(BOT_TOKEN).build()

    # Register command handlers
    telegram_app.add_handler(CommandHandler("start", start_command_handler))
    telegram_app.add_handler(CommandHandler("menu", start_command_handler)) # Alias
    telegram_app.add_handler(CommandHandler("help", help_command_handler))
    telegram_app.add_handler(CommandHandler("rst", rst_command_handler))
    telegram_app.add_handler(CommandHandler("bulk", bulk_command_handler))
    telegram_app.add_handler(CommandHandler("shorten", shorten_command_handler))
    telegram_app.add_handler(CommandHandler("qr", qr_command_handler))
    telegram_app.add_handler(CommandHandler("clear", clear_command_handler))

    # Register message handlers
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    telegram_app.add_handler(MessageHandler(filters.PHOTO, photo_message_handler))
    
    # Register callback query handler for buttons
    telegram_app.add_handler(CallbackQueryHandler(button_handler))

    # Register the global error handler
    telegram_app.add_error_handler(error_handler)

    await telegram_app.initialize()
    if WEBHOOK_URL:
        await telegram_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}")
        logger.info(f"✅ Webhook set successfully to {WEBHOOK_URL}")
    else:
        logger.info("⚠️ Webhook URL not set. Bot will run in polling mode (if run directly).")
    
    # This part runs after the app starts
    yield
    # This part runs on shutdown
    logger.info("👋 Shutting down bot...")
    await telegram_app.stop()
    await telegram_app.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def health_check():
    """A simple endpoint to confirm the web server is running."""
    return {"status": "ok", "bot_initialized": telegram_app is not None}

@app.post("/webhook/{token}")
async def process_webhook(token: str, request: Request):
    """Processes incoming updates from Telegram's webhook."""
    if token != BOT_TOKEN:
        logger.warning("Received update with invalid token.")
        raise HTTPException(status_code=403, detail="Invalid token")
    
    if not telegram_app:
        logger.error("Webhook called but bot application is not ready.")
        raise HTTPException(status_code=503, detail="Bot not initialized")

    try:
        data = await request.json()
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error processing webhook update: {e}", exc_info=True)
        return {"status": "error"}

# =====================================
# SCRIPT ENTRY POINT
# =====================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"🚀 Starting FastAPI server on http://0.0.0.0:{port}")
    # Note: Running this script directly is for local testing.
    # For deployment, a production-grade server like Gunicorn or Uvicorn with workers is recommended.
    # Example: uvicorn main:app --host 0.0.0.0 --port 8000
    uvicorn.run(app, host="0.0.0.0", port=port)

