import os
import logging
import asyncio
import html
import uuid
import string
import random
from typing import Dict, List
import httpx
import google.generativeai as genai
from telegram import Update, BotCommand, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
import uvicorn
from PIL import Image
import io

# =====================================
# LOGGING CONFIGURATION
# =====================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =====================================
# ENVIRONMENT VARIABLES
# =====================================
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

if not BOT_TOKEN or not GEMINI_KEY:
    logger.error("Missing TELEGRAM_BOT_TOKEN or GEMINI_API_KEY")
    exit(1)

# =====================================
# GLOBAL VARIABLES
# =====================================
telegram_app = None
conversation_history: Dict[int, List] = {}

# Conversation states
MENU, INSTAGRAM, CHAT, OCR, SCREENSHOT = range(5)

# =====================================
# GEMINI AI SETUP
# =====================================
try:
    genai.configure(api_key=GEMINI_KEY)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
    logger.info("Gemini AI initialized successfully")
except Exception as e:
    logger.error(f"Gemini initialization failed: {e}")
    exit(1)

# =====================================
# INSTAGRAM PASSWORD RESET FUNCTIONS
# =====================================
async def instagram_reset_api(target: str) -> Dict:
    """
    Send Instagram password reset request.
    Returns dict with status and message.
    """
    try:
        # Prepare request data
        csrf_token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
        guid = str(uuid.uuid4())
        device_id = str(uuid.uuid4())
        
        payload = {
            '_csrftoken': csrf_token,
            'guid': guid,
            'device_id': device_id
        }
        
        # Determine target type and add to payload
        if '@' in target and '.' in target:
            payload['user_email'] = target
            target_type = "email"
        elif target.isdigit() and len(target) > 5:
            payload['user_id'] = target
            target_type = "user_id"
        else:
            payload['username'] = target
            target_type = "username"
        
        logger.info(f"Attempting reset for {target_type}: {target}")
        
        # Generate random device info
        random_brand = ''.join(random.choices(string.ascii_lowercase, k=8))
        random_device = ''.join(random.choices(string.ascii_lowercase, k=8))
        random_model = ''.join(random.choices(string.ascii_lowercase, k=8))
        
        headers = {
            'User-Agent': f'Instagram 150.0.0.0.000 Android (29/10; 300dpi; 720x1440; {random_brand}/{random_device}; {random_model}; {random_model}; en_US;)',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Accept-Language': 'en-US',
            'X-IG-App-ID': '567067343352427',
            'X-IG-Capabilities': '3brTvw==',
            'X-IG-Connection-Type': 'WIFI',
            'X-IG-Device-ID': device_id,
        }
        
        # Make async request
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.post(
                'https://i.instagram.com/api/v1/accounts/send_password_reset/',
                headers=headers,
                data=payload
            )
            
            status_code = response.status_code
            response_text = response.text
            
            logger.info(f"Instagram API response for {target}: {status_code}")
            
            # Parse response
            if status_code == 200:
                if 'obfuscated_email' in response_text or 'obfuscated_phone' in response_text:
                    return {
                        'success': True,
                        'message': f"✅ **Success!** Password reset link sent to {target}"
                    }
                else:
                    return {
                        'success': False,
                        'message': f"⚠️ Request sent for {target} but no confirmation received"
                    }
            elif status_code == 404:
                return {
                    'success': False,
                    'message': f"❌ **Not Found:** Account `{target}` doesn't exist"
                }
            elif status_code == 429:
                return {
                    'success': False,
                    'message': f"⏳ **Rate Limited:** Too many requests. Try again in 5-10 minutes"
                }
            elif status_code == 400:
                return {
                    'success': False,
                    'message': f"❌ **Invalid Input:** Check the username/email format for `{target}`"
                }
            else:
                return {
                    'success': False,
                    'message': f"❌ **Failed:** Status {status_code} for `{target}`"
                }
                
    except asyncio.TimeoutError:
        logger.error(f"Timeout for {target}")
        return {
            'success': False,
            'message': f"⏱️ **Timeout:** Request took too long for `{target}`"
        }
    except Exception as e:
        logger.error(f"Instagram reset error for {target}: {e}")
        return {
            'success': False,
            'message': f"❌ **Error:** {str(e)[:80]}"
        }

# =====================================
# UTILITY FUNCTIONS
# =====================================
def split_text(text: str, max_len: int = 4000) -> List[str]:
    """Split long text into smaller chunks."""
    if len(text) <= max_len:
        return [text]
    
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        
        # Find last newline or space
        split_pos = text.rfind('\n', 0, max_len)
        if split_pos == -1:
            split_pos = text.rfind(' ', 0, max_len)
        if split_pos == -1:
            split_pos = max_len
        
        chunks.append(text[:split_pos].strip())
        text = text[split_pos:].strip()
    
    return chunks

def compress_image_data(image_bytes: bytes) -> bytes:
    """Compress image to reduce size."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        
        # Convert to RGB
        if img.mode in ('RGBA', 'P', 'LA'):
            img = img.convert('RGB')
        
        # Resize if too large
        max_size = (1920, 1920)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Compress
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=80, optimize=True)
        compressed = buffer.getvalue()
        
        logger.info(f"Image compressed: {len(image_bytes)} → {len(compressed)} bytes")
        return compressed
    except Exception as e:
        logger.error(f"Image compression error: {e}")
        return image_bytes

# =====================================
# START AND MENU HANDLERS
# =====================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /start command - show main menu."""
    user = update.effective_user
    
    keyboard = [
        [KeyboardButton("🔓 Instagram Reset")],
        [KeyboardButton("💬 AI Chat"), KeyboardButton("📷 OCR")],
        [KeyboardButton("📱 Screenshot Analysis")],
        [KeyboardButton("ℹ️ Help")]
    ]
    
    welcome_text = (
        f"👋 **Welcome {user.first_name}!**\n\n"
        "🤖 **Multi-Feature Bot**\n\n"
        "**Available Features:**\n"
        "🔓 Instagram Password Reset\n"
        "💬 AI-Powered Chat\n"
        "📷 OCR Text Extraction\n"
        "📱 Screenshot Analysis\n\n"
        "Select a feature from the menu below:\n\n"
        "_Developed by @aadi\\_io_"
    )
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    
    return MENU

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle menu button selections."""
    text = update.message.text
    
    if "Instagram" in text:
        return await enter_instagram_mode(update, context)
    elif "Chat" in text:
        return await enter_chat_mode(update, context)
    elif "OCR" in text:
        return await enter_ocr_mode(update, context)
    elif "Screenshot" in text:
        return await enter_screenshot_mode(update, context)
    elif "Help" in text:
        return await show_help(update, context)
    else:
        await update.message.reply_text(
            "Please use the buttons below to select a feature."
        )
        return MENU

# =====================================
# INSTAGRAM MODE
# =====================================
async def enter_instagram_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Enter Instagram reset mode."""
    help_text = (
        "🔓 **INSTAGRAM PASSWORD RESET MODE**\n\n"
        "**Commands:**\n"
        "`/rst <username>` - Reset single account\n"
        "`/rst <email@domain.com>` - Reset by email\n"
        "`/rst <user_id>` - Reset by ID\n"
        "`/bulk <user1> <user2> <user3>` - Reset multiple (max 3)\n\n"
        "**Examples:**\n"
        "`/rst johndoe`\n"
        "`/rst user@gmail.com`\n"
        "`/bulk john jane jack`\n\n"
        "Use `/menu` to return to main menu."
    )
    
    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove()
    )
    
    return INSTAGRAM

async def instagram_single_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle single account reset."""
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "**Usage:** `/rst <username|email|user_id>`\n\n"
            "**Example:** `/rst johndoe`",
            parse_mode=ParseMode.MARKDOWN
        )
        return INSTAGRAM
    
    target = context.args[0].strip()
    
    if len(target) < 3:
        await update.message.reply_text(
            "❌ Username/email must be at least 3 characters long."
        )
        return INSTAGRAM
    
    # Show processing message
    status_msg = await update.message.reply_text(
        f"🔄 Processing reset for: `{target}`...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Call Instagram API
    result = await instagram_reset_api(target)
    
    # Update message with result
    await status_msg.edit_text(
        result['message'],
        parse_mode=ParseMode.MARKDOWN
    )
    
    return INSTAGRAM

async def instagram_bulk_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle bulk account reset."""
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "**Usage:** `/bulk <user1> <user2> <user3>`\n\n"
            "**Example:** `/bulk john jane jack`\n"
            "**Note:** Maximum 3 accounts per request",
            parse_mode=ParseMode.MARKDOWN
        )
        return INSTAGRAM
    
    targets = [t.strip() for t in context.args[:3]]
    
    if len(context.args) > 3:
        await update.message.reply_text(
            "⚠️ Limited to 3 accounts per request. Processing first 3..."
        )
    
    status_msg = await update.message.reply_text(
        f"🔄 Processing {len(targets)} accounts...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    results = []
    for idx, target in enumerate(targets, 1):
        # Add delay to avoid rate limiting
        if idx > 1:
            await asyncio.sleep(3)
        
        result = await instagram_reset_api(target)
        results.append(f"{idx}. {result['message']}")
        
        # Update progress
        progress_text = f"**Progress: {idx}/{len(targets)}**\n\n" + "\n\n".join(results)
        try:
            await status_msg.edit_text(progress_text, parse_mode=ParseMode.MARKDOWN)
        except:
            pass  # Ignore if message unchanged
    
    # Final result
    final_text = f"**🎯 Bulk Reset Complete ({len(targets)} accounts)**\n\n" + "\n\n".join(results)
    await status_msg.edit_text(final_text, parse_mode=ParseMode.MARKDOWN)
    
    return INSTAGRAM

async def instagram_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle non-command text in Instagram mode."""
    await update.message.reply_text(
        "Please use `/rst <target>` or `/bulk <targets>` commands.\n"
        "Use `/menu` to return to main menu."
    )
    return INSTAGRAM

# =====================================
# CHAT MODE
# =====================================
async def enter_chat_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Enter chat mode."""
    await update.message.reply_text(
        "💬 **AI CHAT MODE ACTIVATED**\n\n"
        "Send me any message and I'll respond!\n\n"
        "Commands:\n"
        "`/clear` - Clear conversation history\n"
        "`/menu` - Return to main menu",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove()
    )
    return CHAT

async def chat_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle chat messages."""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    # Initialize conversation history
    if user_id not in conversation_history:
        conversation_history[user_id] = []
    
    try:
        # Show typing indicator
        await update.message.chat.send_action(ChatAction.TYPING)
        
        # Get AI response
        chat = gemini_model.start_chat(history=conversation_history[user_id])
        response = chat.send_message(user_message)
        
        # Update history
        conversation_history[user_id].extend([
            {"role": "user", "parts": [user_message]},
            {"role": "model", "parts": [response.text]}
        ])
        
        # Limit history to last 20 exchanges
        if len(conversation_history[user_id]) > 40:
            conversation_history[user_id] = conversation_history[user_id][-40:]
        
        # Send response (handle long messages)
        response_text = html.escape(response.text)
        chunks = split_text(response_text)
        
        for chunk in chunks:
            await update.message.reply_text(chunk)
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        await update.message.reply_text(
            "❌ Sorry, I encountered an error. Try `/clear` or `/menu`"
        )
    
    return CHAT

async def clear_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Clear chat history."""
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("✅ Chat history cleared! Start fresh.")
    return CHAT

# =====================================
# OCR MODE
# =====================================
async def enter_ocr_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Enter OCR mode."""
    await update.message.reply_text(
        "📷 **OCR MODE ACTIVATED**\n\n"
        "Send me an image and I'll extract all text from it.\n\n"
        "Use `/menu` to return to main menu.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove()
    )
    return OCR

async def ocr_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle photos in OCR mode."""
    try:
        await update.message.chat.send_action(ChatAction.TYPING)
        
        # Download photo
        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        # Compress and process
        compressed = compress_image_data(bytes(photo_bytes))
        image = Image.open(io.BytesIO(compressed))
        
        # Extract text
        prompt = "Extract all text from this image. Only return the extracted text, no commentary."
        response = gemini_model.generate_content([prompt, image])
        
        extracted_text = response.text.strip()
        
        if extracted_text:
            safe_text = html.escape(extracted_text)
            chunks = split_text(safe_text)
            
            await update.message.reply_text(
                "📝 **Extracted Text:**",
                parse_mode=ParseMode.MARKDOWN
            )
            
            for chunk in chunks:
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text("❌ No text found in the image.")
            
    except Exception as e:
        logger.error(f"OCR error: {e}")
        await update.message.reply_text("❌ Error processing image. Please try again.")
    
    return OCR

async def ocr_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle text messages in OCR mode."""
    await update.message.reply_text(
        "📷 Please send an image to extract text.\n"
        "Use `/menu` to return to main menu."
    )
    return OCR

# =====================================
# SCREENSHOT MODE
# =====================================
async def enter_screenshot_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Enter screenshot analysis mode."""
    await update.message.reply_text(
        "📱 **SCREENSHOT ANALYSIS MODE**\n\n"
        "Send me a screenshot and I'll analyze it for:\n"
        "• Key elements and components\n"
        "• Potential issues or errors\n"
        "• Suggestions and solutions\n\n"
        "Use `/menu` to return to main menu.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove()
    )
    return SCREENSHOT

async def screenshot_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle photos in screenshot mode."""
    try:
        await update.message.chat.send_action(ChatAction.TYPING)
        
        # Download photo
        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        # Compress and process
        compressed = compress_image_data(bytes(photo_bytes))
        image = Image.open(io.BytesIO(compressed))
        
        # Analyze screenshot
        prompt = (
            "Analyze this screenshot thoroughly. Identify:\n"
            "1. Key elements and what's shown\n"
            "2. Any errors, issues, or problems\n"
            "3. Specific solutions or recommendations\n"
            "Be concise and actionable."
        )
        response = gemini_model.generate_content([prompt, image])
        
        analysis = response.text.strip()
        
        if analysis:
            safe_text = html.escape(analysis)
            chunks = split_text(safe_text)
            
            await update.message.reply_text(
                "📊 **Screenshot Analysis:**",
                parse_mode=ParseMode.MARKDOWN
            )
            
            for chunk in chunks:
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text("❌ Couldn't analyze the screenshot.")
            
    except Exception as e:
        logger.error(f"Screenshot analysis error: {e}")
        await update.message.reply_text("❌ Error analyzing screenshot. Please try again.")
    
    return SCREENSHOT

async def screenshot_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle text messages in screenshot mode."""
    await update.message.reply_text(
        "📱 Please send a screenshot to analyze.\n"
        "Use `/menu` to return to main menu."
    )
    return SCREENSHOT

# =====================================
# HELP AND ABOUT
# =====================================
async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show help information."""
    help_text = """
🤖 **COMPLETE BOT GUIDE**

**🔓 Instagram Reset:**
`/rst <target>` - Single reset
`/bulk <t1> <t2> <t3>` - Bulk reset

**💬 AI Chat:**
Send any message to chat
`/clear` - Clear history

**📷 OCR:**
Send image to extract text

**📱 Screenshot:**
Send screenshot for analysis

**⚡ General:**
`/start` or `/menu` - Main menu
`/help` - This help message
`/about` - Bot information

_Developer: @aadi\\_io_
    """
    
    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.MARKDOWN
    )
    
    return MENU

async def show_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show about information."""
    about_text = """
ℹ️ **ABOUT THIS BOT**

**Developer:** @aadi_io

**Features:**
🔓 Instagram Password Reset
💬 AI-Powered Conversations
📷 OCR Text Extraction
📱 Screenshot Analysis

**Technology Stack:**
• Python 3.11+
• python-telegram-bot
• Google Gemini AI
• FastAPI
• Async/Await Architecture

**Hosting:** Render.com

⚡ Built for speed and reliability
    """
    
    await update.message.reply_text(
        about_text,
        parse_mode=ParseMode.MARKDOWN
    )

async def return_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Return to main menu."""
    return await start(update, context)

# =====================================
# ERROR HANDLER
# =====================================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors."""
    logger.error(f"Update {update} caused error: {context.error}")
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ An unexpected error occurred.\n"
                "Use `/menu` to restart or `/help` for assistance."
            )
        except Exception as e:
            logger.error(f"Error sending error message: {e}")

# =====================================
# BOT INITIALIZATION
# =====================================
async def initialize_telegram_bot():
    """Initialize the Telegram bot application."""
    global telegram_app
    
    logger.info("Initializing Telegram bot...")
    
    # Create application
    telegram_app = Application.builder().token(BOT_TOKEN).build()
    
    # Add error handler
    telegram_app.add_error_handler(error_handler)
    
    # Create conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler)
            ],
            INSTAGRAM: [
                CommandHandler("rst", instagram_single_reset),
                CommandHandler("bulk", instagram_bulk_reset),
                MessageHandler(filters.TEXT & ~filters.COMMAND, instagram_text_handler)
            ],
            CHAT: [
                CommandHandler("clear", clear_chat),
                MessageHandler(filters.TEXT & ~filters.COMMAND, chat_message_handler)
            ],
            OCR: [
                MessageHandler(filters.PHOTO, ocr_photo_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ocr_text_handler)
            ],
            SCREENSHOT: [
                MessageHandler(filters.PHOTO, screenshot_photo_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, screenshot_text_handler)
            ]
        },
        fallbacks=[
            CommandHandler("menu", return_to_menu),
            CommandHandler("start", start),
            CommandHandler("help", show_help)
        ],
        allow_reentry=True
    )
    
    # Add handlers
    telegram_app.add_handler(conv_handler)
    telegram_app.add_handler(CommandHandler("help", show_help))
    telegram_app.add_handler(CommandHandler("about", show_about))
    
    # Set bot commands
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("menu", "Main menu"),
        BotCommand("rst", "Instagram single reset"),
        BotCommand("bulk", "Instagram bulk reset"),
        BotCommand("clear", "Clear chat history"),
        BotCommand("help", "Show help"),
        BotCommand("about", "About bot")
    ]
    
    # Initialize and start
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.bot.set_my_commands(commands)
    
    # Set webhook if URL provided
    if WEBHOOK_URL:
        webhook_path = f"{WEBHOOK_URL}/{BOT_TOKEN}"
        await telegram_app.bot.set_webhook(webhook_path)
        logger.info(f"Webhook set to: {webhook_path}")
    else:
        logger.warning("No WEBHOOK_URL set. Bot will not receive updates.")
    
    logger.info("✅ Telegram bot initialized successfully!")

# =====================================
# FASTAPI APPLICATION
# =====================================
@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """Manage FastAPI application lifecycle."""
    # Startup
    logger.info("FastAPI startup - initializing bot...")
    await initialize_telegram_bot()
    yield
    # Shutdown
    logger.info("FastAPI shutdown - stopping bot...")
    if telegram_app:
        await telegram_app.stop()
        await telegram_app.shutdown()
    logger.info("Bot stopped successfully")

app = FastAPI(title="Telegram Multi-Feature Bot", lifespan=app_lifespan)

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "online",
        "bot": "running",
        "features": ["instagram_reset", "ai_chat", "ocr", "screenshot_analysis"]
    }

@app.get("/health")
async def health_check():
    """Detailed health check."""
    return {
        "status": "healthy",
        "bot_initialized": telegram_app is not None,
        "gemini_ready": True
    }

@app.post("/{token}")
async def webhook_handler(token: str, request: Request):
    """Handle incoming webhook updates from Telegram."""
    # Verify token
    if token != BOT_TOKEN:
        logger.warning(f"Invalid token attempt: {token}")
        return {"error": "unauthorized"}, 401
    
    # Check if bot is ready
    if not telegram_app:
        logger.error("Bot not initialized")
        return {"error": "bot not ready"}, 503
    
    try:
        # Parse update
        data = await request.json()
        update = Update.de_json(data, telegram_app.bot)
        
        # Process update
        await telegram_app.process_update(update)
        
        return {"status": "ok"}
    
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        return {"error": "internal error"}, 500

# =====================================
# MAIN ENTRY POINT
# =====================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}...")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True
    )
