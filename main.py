import os
import logging
import asyncio
import uuid
import string
import random
from typing import Dict, List, Optional
import httpx
import google.generativeai as genai
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode
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
    logger.error("Missing environment variables!")
    exit(1)

logger.info(f"Bot Token: {BOT_TOKEN[:10]}...")
logger.info(f"Webhook URL: {WEBHOOK_URL}")

# =====================================
# GLOBAL VARIABLES
# =====================================
telegram_app: Optional[Application] = None
user_sessions: Dict[int, Dict] = {}

# =====================================
# GEMINI AI SETUP
# =====================================
try:
    genai.configure(api_key=GEMINI_KEY)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
    logger.info("✅ Gemini AI initialized")
except Exception as e:
    logger.error(f"❌ Gemini initialization failed: {e}")
    exit(1)

# =====================================
# USER SESSION MANAGEMENT
# =====================================
def get_session(user_id: int) -> Dict:
    """Get or create user session."""
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            'mode': 'menu',
            'history': []
        }
    return user_sessions[user_id]

def set_mode(user_id: int, mode: str):
    """Set user's current mode."""
    session = get_session(user_id)
    session['mode'] = mode
    logger.info(f"User {user_id} switched to mode: {mode}")

def get_mode(user_id: int) -> str:
    """Get user's current mode."""
    return get_session(user_id)['mode']

# =====================================
# INSTAGRAM PASSWORD RESET
# =====================================
async def instagram_reset_request(target: str) -> Dict:
    """Send Instagram password reset request."""
    try:
        logger.info(f"Processing reset for: {target}")
        
        # Build payload
        payload = {
            '_csrftoken': ''.join(random.choices(string.ascii_letters + string.digits, k=32)),
            'guid': str(uuid.uuid4()),
            'device_id': str(uuid.uuid4())
        }
        
        # Determine target type
        if '@' in target and '.' in target:
            payload['user_email'] = target
        elif target.isdigit():
            payload['user_id'] = target
        else:
            payload['username'] = target
        
        # Generate headers
        headers = {
            'User-Agent': f'Instagram 150.0.0.0.000 Android (29/10; 300dpi; 720x1440; OnePlus/GM1903; OnePlus7; qcom; en_US;)',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
        }
        
        # Make request
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                'https://i.instagram.com/api/v1/accounts/send_password_reset/',
                headers=headers,
                data=payload
            )
            
            logger.info(f"Instagram API response: {response.status_code}")
            
            if response.status_code == 200:
                if 'obfuscated' in response.text:
                    return {'success': True, 'message': f"✅ Reset link sent to: {target}"}
                else:
                    return {'success': False, 'message': f"⚠️ Request sent but no confirmation"}
            elif response.status_code == 404:
                return {'success': False, 'message': f"❌ Account not found: {target}"}
            elif response.status_code == 429:
                return {'success': False, 'message': f"⏳ Rate limited. Wait 10 minutes"}
            else:
                return {'success': False, 'message': f"❌ Failed (Status: {response.status_code})"}
    
    except Exception as e:
        logger.error(f"Instagram reset error: {e}")
        return {'success': False, 'message': f"❌ Error: {str(e)[:50]}"}

# =====================================
# IMAGE PROCESSING
# =====================================
def compress_image(img_bytes: bytes) -> bytes:
    """Compress image."""
    try:
        img = Image.open(io.BytesIO(img_bytes))
        if img.mode in ('RGBA', 'P', 'LA'):
            img = img.convert('RGB')
        img.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=80, optimize=True)
        return buffer.getvalue()
    except Exception as e:
        logger.error(f"Compression error: {e}")
        return img_bytes

def split_long_text(text: str, max_len: int = 4000) -> List[str]:
    """Split text into chunks."""
    if len(text) <= max_len:
        return [text]
    
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        split_pos = text.rfind('\n', 0, max_len)
        if split_pos == -1:
            split_pos = max_len
        chunks.append(text[:split_pos].strip())
        text = text[split_pos:].strip()
    return chunks

# =====================================
# COMMAND HANDLERS
# =====================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    try:
        user = update.effective_user
        user_id = user.id
        
        logger.info(f"Start command from user {user_id}")
        
        set_mode(user_id, 'menu')
        
        keyboard = [
            ["🔓 Instagram Reset"],
            ["💬 AI Chat", "📷 OCR"],
            ["📱 Screenshot", "❓ Help"]
        ]
        
        text = (
            f"👋 Welcome {user.first_name}!\n\n"
            "🤖 **Multi-Feature Bot**\n\n"
            "Select a feature:\n"
            "🔓 Instagram Reset\n"
            "💬 AI Chat\n"
            "📷 OCR\n"
            "📱 Screenshot Analysis\n\n"
            "Choose from menu below:"
        )
        
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        
    except Exception as e:
        logger.error(f"Start command error: {e}", exc_info=True)
        await update.message.reply_text("Error starting bot. Please try /start again.")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    try:
        help_text = """
🤖 **BOT HELP**

**Instagram Reset:**
/rst username - Single reset
/bulk user1 user2 - Bulk reset

**AI Chat:**
Just send messages

**OCR:**
Send images to extract text

**Screenshot:**
Send screenshots to analyze

**Commands:**
/start - Main menu
/menu - Return to menu
/help - This help
"""
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Help error: {e}", exc_info=True)

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to main menu."""
    return await cmd_start(update, context)

# =====================================
# INSTAGRAM COMMANDS
# =====================================
async def cmd_rst(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /rst command."""
    try:
        user_id = update.effective_user.id
        logger.info(f"RST command from user {user_id}")
        
        if not context.args:
            await update.message.reply_text(
                "**Usage:** /rst username\n**Example:** /rst johndoe",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        target = context.args[0].strip()
        
        msg = await update.message.reply_text(f"🔄 Processing: {target}...")
        
        result = await instagram_reset_request(target)
        
        await msg.edit_text(result['message'], parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"RST error: {e}", exc_info=True)
        await update.message.reply_text("❌ Error processing reset request")

async def cmd_bulk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /bulk command."""
    try:
        user_id = update.effective_user.id
        logger.info(f"BULK command from user {user_id}")
        
        if not context.args:
            await update.message.reply_text(
                "**Usage:** /bulk user1 user2 user3\n**Max:** 3 accounts",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        targets = context.args[:3]
        
        msg = await update.message.reply_text(f"🔄 Processing {len(targets)} accounts...")
        
        results = []
        for i, target in enumerate(targets, 1):
            if i > 1:
                await asyncio.sleep(2)
            result = await instagram_reset_request(target)
            results.append(f"{i}. {result['message']}")
            
            progress = f"**Progress: {i}/{len(targets)}**\n\n" + "\n".join(results)
            try:
                await msg.edit_text(progress, parse_mode=ParseMode.MARKDOWN)
            except:
                pass
        
        final = f"**✅ Complete ({len(targets)} accounts)**\n\n" + "\n".join(results)
        await msg.edit_text(final, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"BULK error: {e}", exc_info=True)
        await update.message.reply_text("❌ Error processing bulk request")

# =====================================
# TEXT MESSAGE HANDLER
# =====================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages."""
    try:
        user_id = update.effective_user.id
        text = update.message.text
        mode = get_mode(user_id)
        
        logger.info(f"Message from {user_id} in mode {mode}: {text[:30]}")
        
        # Menu selection
        if "Instagram" in text:
            set_mode(user_id, 'instagram')
            await update.message.reply_text(
                "🔓 **Instagram Mode**\n\n"
                "Use:\n"
                "/rst username\n"
                "/bulk user1 user2\n\n"
                "/menu to go back",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=ReplyKeyboardRemove()
            )
            return
        
        elif "Chat" in text:
            set_mode(user_id, 'chat')
            await update.message.reply_text(
                "💬 **Chat Mode**\n\nSend me any message!\n\n/menu to go back",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=ReplyKeyboardRemove()
            )
            return
        
        elif "OCR" in text:
            set_mode(user_id, 'ocr')
            await update.message.reply_text(
                "📷 **OCR Mode**\n\nSend me an image!\n\n/menu to go back",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=ReplyKeyboardRemove()
            )
            return
        
        elif "Screenshot" in text:
            set_mode(user_id, 'screenshot')
            await update.message.reply_text(
                "📱 **Screenshot Mode**\n\nSend me a screenshot!\n\n/menu to go back",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=ReplyKeyboardRemove()
            )
            return
        
        elif "Help" in text:
            await cmd_help(update, context)
            return
        
        # Handle based on mode
        if mode == 'chat':
            await handle_chat(update, context)
        elif mode == 'instagram':
            await update.message.reply_text(
                "Use /rst or /bulk commands\n/menu to go back"
            )
        elif mode in ['ocr', 'screenshot']:
            await update.message.reply_text(
                "Please send an image\n/menu to go back"
            )
        else:
            await update.message.reply_text("Use the menu buttons")
            
    except Exception as e:
        logger.error(f"Message handler error: {e}", exc_info=True)
        await update.message.reply_text("❌ Error. Try /start")

# =====================================
# CHAT HANDLER
# =====================================
async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle chat messages."""
    try:
        user_id = update.effective_user.id
        text = update.message.text
        
        session = get_session(user_id)
        
        chat = gemini_model.start_chat(history=session['history'])
        response = chat.send_message(text)
        
        session['history'].extend([
            {"role": "user", "parts": [text]},
            {"role": "model", "parts": [response.text]}
        ])
        
        if len(session['history']) > 40:
            session['history'] = session['history'][-40:]
        
        chunks = split_long_text(response.text)
        for chunk in chunks:
            await update.message.reply_text(chunk)
            
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        await update.message.reply_text("❌ Chat error. Try /menu")

# =====================================
# PHOTO HANDLER
# =====================================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photos."""
    try:
        user_id = update.effective_user.id
        mode = get_mode(user_id)
        
        logger.info(f"Photo from {user_id} in mode {mode}")
        
        if mode not in ['ocr', 'screenshot']:
            await update.message.reply_text("Please select OCR or Screenshot mode first")
            return
        
        # Download photo
        photo = update.message.photo[-1]
        file = await photo.get_file()
        photo_bytes = await file.download_as_bytearray()
        
        # Compress
        compressed = compress_image(bytes(photo_bytes))
        img = Image.open(io.BytesIO(compressed))
        
        # Process based on mode
        if mode == 'ocr':
            prompt = "Extract all text from this image. Only return the text."
            title = "📝 **Text Extracted:**"
        else:
            prompt = "Analyze this screenshot. Identify key elements, issues, and provide solutions."
            title = "📊 **Analysis:**"
        
        response = gemini_model.generate_content([prompt, img])
        
        if response.text:
            chunks = split_long_text(response.text)
            await update.message.reply_text(title, parse_mode=ParseMode.MARKDOWN)
            for chunk in chunks:
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text("❌ No content found")
            
    except Exception as e:
        logger.error(f"Photo handler error: {e}", exc_info=True)
        await update.message.reply_text("❌ Error processing image")

# =====================================
# ERROR HANDLER
# =====================================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors."""
    logger.error(f"Update {update} caused error: {context.error}", exc_info=context.error)
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Error occurred. Use /start to restart."
            )
        except:
            pass

# =====================================
# BOT INITIALIZATION
# =====================================
async def init_bot():
    """Initialize bot."""
    global telegram_app
    
    logger.info("🚀 Initializing bot...")
    
    telegram_app = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    telegram_app.add_handler(CommandHandler("start", cmd_start))
    telegram_app.add_handler(CommandHandler("menu", cmd_menu))
    telegram_app.add_handler(CommandHandler("help", cmd_help))
    telegram_app.add_handler(CommandHandler("rst", cmd_rst))
    telegram_app.add_handler(CommandHandler("bulk", cmd_bulk))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    telegram_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    telegram_app.add_error_handler(error_handler)
    
    # Initialize
    await telegram_app.initialize()
    await telegram_app.start()
    
    # Set webhook
    if WEBHOOK_URL:
        webhook = f"{WEBHOOK_URL}/{BOT_TOKEN}"
        await telegram_app.bot.set_webhook(webhook)
        logger.info(f"✅ Webhook set: {webhook}")
    
    logger.info("✅ Bot initialized successfully!")

# =====================================
# FASTAPI APP
# =====================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager."""
    logger.info("Starting FastAPI...")
    await init_bot()
    yield
    logger.info("Stopping bot...")
    if telegram_app:
        await telegram_app.stop()
        await telegram_app.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    """Health check."""
    return {"status": "online", "bot": "running"}

@app.post("/{token}")
async def webhook(token: str, request: Request):
    """Webhook endpoint."""
    if token != BOT_TOKEN:
        logger.warning("Invalid token")
        return {"error": "unauthorized"}
    
    if not telegram_app:
        logger.error("Bot not ready")
        return {"error": "not ready"}
    
    try:
        data = await request.json()
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return {"error": str(e)}

# =====================================
# MAIN
# =====================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"🚀 Starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
