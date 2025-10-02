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
from fastapi import FastAPI, Request, Response
import uvicorn
from PIL import Image
import io
from contextlib import asynccontextmanager

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

# Validate required environment variables
if not all([TELEGRAM_TOKEN, GEMINI_API_KEY]):
    logger.error("Missing required environment variables")
    exit(1)

# Configure Gemini AI
genai.configure(api_key=GEMINI_API_KEY)

# Global variables
application = None
http_client = None
user_conversations = {}

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
# Instagram Reset Functions
# =========================

async def send_password_reset(target: str) -> dict:
    """Send password reset request to Instagram - Async implementation"""
    try:
        data = {
            '_csrftoken': ''.join(random.choices(string.ascii_letters + string.digits, k=32)),
            'guid': str(uuid.uuid4()),
            'device_id': str(uuid.uuid4())
        }
        
        # Determine target type
        if '@' in target:
            data['user_email'] = target
            logger.info(f"Reset attempt for email: {target}")
        elif target.isdigit():
            data['user_id'] = target
            logger.info(f"Reset attempt for User ID: {target}")
        else:
            data['username'] = target
            logger.info(f"Reset attempt for username: {target}")
        
        # Generate random device info
        brand = ''.join(random.choices(string.ascii_lowercase, k=8))
        device = ''.join(random.choices(string.ascii_lowercase, k=8))
        model_name = ''.join(random.choices(string.ascii_lowercase, k=8))
        
        headers = {
            'user-agent': f"Instagram 150.0.0.0.000 Android (29/10; 300dpi; 720x1440; {brand}/{device}; {model_name}; {model_name}; en_GB;)",
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8'
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                'https://i.instagram.com/api/v1/accounts/send_password_reset/',
                headers=headers,
                data=data
            )
            
            result = {
                'target': target,
                'status_code': response.status_code,
                'success': False,
                'message': ''
            }
            
            if response.status_code == 404:
                result['message'] = f"❌ User `{target}` not found"
            elif response.status_code == 429:
                result['message'] = f"⏳ Rate limited for `{target}`. Try again later"
            elif 'obfuscated_email' in response.text or 'sms_two_factor_identifier' in response.text:
                result['success'] = True
                result['message'] = f"✅ Reset sent for `{target}`"
            else:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('message', 'Unknown error')
                    result['message'] = f"❌ Failed for `{target}`: {error_msg}"
                except:
                    result['message'] = f"❌ Failed for `{target}` (Status: {response.status_code})"
            
            return result
            
    except asyncio.TimeoutError:
        return {'target': target, 'success': False, 'message': f"⏱️ Timeout for `{target}`"}
    except Exception as e:
        logger.error(f"Exception during reset for {target}: {e}")
        return {'target': target, 'success': False, 'message': f"❌ Error for `{target}`: {str(e)[:50]}"}

async def insta_reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Instagram reset command"""
    try:
        if not context.args:
            await update.message.reply_text(
                "📝 *Usage:*\n"
                "`/rst <username|email|user_id>`\n\n"
                "*Examples:*\n"
                "`/rst johndoe`\n"
                "`/rst user@email.com`\n"
                "`/rst 123456789`",
                parse_mode=ParseMode.MARKDOWN
            )
            return INSTA_MODE
        
        target = context.args[0].strip()
        
        if len(target) < 3:
            await update.message.reply_text("⚠️ Input must be at least 3 characters")
            return INSTA_MODE
        
        processing_msg = await update.message.reply_text(
            f"🔄 Processing reset for: `{target}`...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        result = await send_password_reset(target)
        await processing_msg.edit_text(result['message'], parse_mode=ParseMode.MARKDOWN)
        
        return INSTA_MODE
        
    except Exception as e:
        logger.error(f"Error in insta_reset_command: {e}")
        await update.message.reply_text("❌ Error occurred. Please try again.")
        return INSTA_MODE

async def insta_bulk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bulk Instagram reset"""
    try:
        if not context.args:
            await update.message.reply_text(
                "📝 *Bulk Reset Usage:*\n"
                "`/blk user1 user2 user3`\n\n"
                "⚠️ Max 3 accounts per request",
                parse_mode=ParseMode.MARKDOWN
            )
            return INSTA_MODE
        
        targets = [t.strip() for t in context.args[:3] if t.strip()]
        
        if not targets:
            await update.message.reply_text("⚠️ Please provide valid usernames/emails")
            return INSTA_MODE
        
        if len(context.args) > 3:
            await update.message.reply_text("⚠️ Limited to 3 accounts. Processing first 3...")
        
        processing_msg = await update.message.reply_text(
            f"🔄 Processing {len(targets)} accounts...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        results = []
        for i, target in enumerate(targets, 1):
            await asyncio.sleep(2)  # Rate limiting
            result = await send_password_reset(target)
            results.append(f"{i}. {result['message']}")
            
            progress = f"📊 *Progress: {i}/{len(targets)}*\n\n" + "\n".join(results)
            try:
                await processing_msg.edit_text(progress, parse_mode=ParseMode.MARKDOWN)
            except:
                pass  # Ignore "message not modified" errors
        
        final_text = "📊 *Bulk Reset Complete*\n\n" + "\n".join(results)
        await processing_msg.edit_text(final_text, parse_mode=ParseMode.MARKDOWN)
        
        return INSTA_MODE
        
    except Exception as e:
        logger.error(f"Error in bulk command: {e}")
        await update.message.reply_text("❌ Error processing bulk request")
        return INSTA_MODE

# =========================
# Image Processing Functions
# =========================

def compress_image(image_bytes, max_size=(1024, 1024), quality=85):
    """Compress image to reduce file size"""
    try:
        image = Image.open(io.BytesIO(image_bytes))
        
        if image.mode in ('RGBA', 'P', 'LA'):
            image = image.convert('RGB')
        
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        output_buffer = io.BytesIO()
        image.save(output_buffer, format='JPEG', quality=quality, optimize=True)
        compressed_bytes = output_buffer.getvalue()
        
        logger.info(f"Compressed: {len(image_bytes)} → {len(compressed_bytes)} bytes")
        return compressed_bytes
        
    except Exception as e:
        logger.error(f"Compression error: {e}")
        return image_bytes

def split_message(text, max_length=4000):
    """Split long messages into chunks"""
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        
        split_index = text.rfind('\n', 0, max_length)
        if split_index == -1:
            split_index = text.rfind(' ', 0, max_length)
        if split_index == -1:
            split_index = max_length
        
        chunks.append(text[:split_index])
        text = text[split_index:].strip()
    
    return chunks

# =========================
# Command Handlers
# =========================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    try:
        user = update.effective_user
        
        reply_keyboard = [
            ["🔓 Instagram Reset"],
            ["💬 Chat Mode", "📷 OCR Mode"],
            ["📱 Screenshot Mode", "❓ Help"]
        ]
        
        welcome = (
            f"👋 Hello {user.first_name}!\n\n"
            "🤖 *MULTI-FEATURE BOT*\n\n"
            "🔓 *Instagram Password Reset*\n"
            "💬 *AI Conversations*\n"
            "📷 *Text Extraction (OCR)*\n"
            "📱 *Screenshot Analysis*\n\n"
            "⚡ Select a mode below to start!\n\n"
            "Developer: @aadi_io"
        )
        
        await update.message.reply_text(
            welcome,
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )
        return MAIN_MENU
        
    except Exception as e:
        logger.error(f"Start error: {e}")
        await update.message.reply_text("Welcome! Select a mode:")
        return MAIN_MENU

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle main menu selections"""
    try:
        text = update.message.text
        
        if "Instagram" in text:
            return await switch_to_insta_mode(update, context)
        elif "Chat" in text:
            return await switch_to_chat_mode(update, context)
        elif "OCR" in text:
            return await switch_to_ocr_mode(update, context)
        elif "Screenshot" in text:
            return await switch_to_sshot_mode(update, context)
        elif "Help" in text:
            return await help_command(update, context)
        else:
            await update.message.reply_text("Please select a mode from the menu:")
            return MAIN_MENU
    except Exception as e:
        logger.error(f"Menu error: {e}")
        return MAIN_MENU

async def switch_to_insta_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to Instagram mode"""
    await update.message.reply_text(
        "🔓 *INSTAGRAM RESET MODE*\n\n"
        "🚀 *Commands:*\n"
        "`/rst <target>` - Single reset\n"
        "`/blk <t1> <t2> <t3>` - Bulk reset\n\n"
        "💡 *Examples:*\n"
        "`/rst johndoe`\n"
        "`/rst user@email.com`\n"
        "`/blk user1 user2 user3`\n\n"
        "⚡ Use `/mode` to return to menu",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN
    )
    return INSTA_MODE

async def switch_to_chat_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to chat mode"""
    await update.message.reply_text(
        "💬 *CHAT MODE ACTIVE*\n\n"
        "Send me any message and I'll respond!\n\n"
        "Use `/newchat` to clear history\n"
        "Use `/mode` to return to menu",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN
    )
    return CHAT_MODE

async def switch_to_ocr_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to OCR mode"""
    await update.message.reply_text(
        "📷 *OCR MODE ACTIVE*\n\n"
        "Send me an image and I'll extract text!\n\n"
        "Use `/mode` to return to menu",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN
    )
    return OCR_MODE

async def switch_to_sshot_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to screenshot mode"""
    await update.message.reply_text(
        "📱 *SCREENSHOT MODE ACTIVE*\n\n"
        "Send me a screenshot for analysis!\n\n"
        "Use `/mode` to return to menu",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN
    )
    return SSHOT_MODE

async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to mode selection"""
    return await start_command(update, context)

# =========================
# Instagram Mode Handler
# =========================

async def insta_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages in Instagram mode"""
    await update.message.reply_text(
        "🔓 Use `/rst <target>` or `/blk <targets>`\n"
        "Or use `/mode` to return to menu",
        parse_mode=ParseMode.MARKDOWN
    )
    return INSTA_MODE

# =========================
# Chat Mode Handler
# =========================

async def chat_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle chat messages"""
    try:
        user_id = update.effective_user.id
        message_text = update.message.text
        
        if message_text.startswith('/'):
            return CHAT_MODE
        
        if user_id not in user_conversations:
            user_conversations[user_id] = []
        
        await update.message.chat.send_action(action="typing")
        
        chat = model.start_chat(history=user_conversations[user_id])
        response = chat.send_message(message_text)
        
        user_conversations[user_id].extend([
            {"role": "user", "parts": [message_text]},
            {"role": "model", "parts": [response.text]}
        ])
        
        # Keep last 10 exchanges
        if len(user_conversations[user_id]) > 20:
            user_conversations[user_id] = user_conversations[user_id][-20:]
        
        safe_text = html.escape(response.text)
        chunks = split_message(safe_text)
        
        for chunk in chunks:
            await update.message.reply_text(chunk)
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        await update.message.reply_text("❌ Error occurred. Try `/newchat` or `/mode`")
    
    return CHAT_MODE

async def newchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset conversation"""
    user_id = update.effective_user.id
    user_conversations[user_id] = []
    await update.message.reply_text("✅ Chat history cleared!")
    return CHAT_MODE

# =========================
# Image Processing Handlers
# =========================

async def process_image(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: int):
    """Process images for OCR or Screenshot mode"""
    try:
        await update.message.chat.send_action(action="typing")
        
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        compressed = compress_image(photo_bytes)
        image = Image.open(io.BytesIO(compressed))
        
        if mode == OCR_MODE:
            prompt = "Extract all text from this image. Return only the text."
            title = "📝 *Extracted Text:*"
        else:  # SSHOT_MODE
            prompt = "Analyze this screenshot. Identify key elements, issues, and provide solutions."
            title = "📊 *Screenshot Analysis:*"
        
        response = model.generate_content([prompt, image])
        text = response.text.strip()
        
        if text:
            safe_text = html.escape(text)
            chunks = split_message(safe_text)
            
            for i, chunk in enumerate(chunks):
                if i == 0:
                    await update.message.reply_text(f"{title}\n\n{chunk}", parse_mode=ParseMode.MARKDOWN)
                else:
                    await update.message.reply_text(chunk)
        else:
            await update.message.reply_text("❌ No text/content found in image")
            
    except Exception as e:
        logger.error(f"Image processing error: {e}")
        await update.message.reply_text("❌ Error processing image. Try again.")
    
    return mode

async def ocr_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle OCR mode"""
    if not update.message.photo:
        await update.message.reply_text("📷 Please send an image")
        return OCR_MODE
    return await process_image(update, context, OCR_MODE)

async def sshot_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle screenshot mode"""
    if not update.message.photo:
        await update.message.reply_text("📱 Please send a screenshot")
        return SSHOT_MODE
    return await process_image(update, context, SSHOT_MODE)

# =========================
# Help Commands
# =========================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display help"""
    help_text = """
🤖 *BOT HELP GUIDE*

🔓 *Instagram Reset:*
`/rst <target>` - Single reset
`/blk <t1> <t2> <t3>` - Bulk reset

💬 *Chat Mode:*
Send messages for AI responses
`/newchat` - Clear history

📷 *OCR Mode:*
Send images to extract text

📱 *Screenshot Mode:*
Send screenshots for analysis

⚡ *General:*
`/start` - Main menu
`/mode` - Switch modes
`/help` - This help
`/about` - About bot

Developer: @aadi_io
    """
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display about info"""
    about = """
ℹ️ *MULTI-FEATURE BOT*

👨‍💻 Developer: @aadi_io

✨ *Features:*
• Instagram password recovery
• AI-powered chat
• OCR text extraction
• Screenshot analysis

🛠️ *Technology:*
• Python 3 + Telegram Bot API
• Google Gemini AI
• FastAPI webhooks
• Async/await architecture

⚡ Optimized for Render hosting
    """
    await update.message.reply_text(about, parse_mode=ParseMode.MARKDOWN)

# =========================
# Error Handler
# =========================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler"""
    logger.error(f"Update {update} caused error: {context.error}")
    
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ An error occurred. Use `/mode` to reset."
            )
    except Exception as e:
        logger.error(f"Error in error handler: {e}")

# =========================
# Bot Setup
# =========================

async def setup_bot():
    """Initialize bot and set commands"""
    global application
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Error handler
    application.add_error_handler(error_handler)
    
    # Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_handler)],
            CHAT_MODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, chat_mode_handler),
                CommandHandler("newchat", newchat_command),
            ],
            OCR_MODE: [MessageHandler(filters.PHOTO | filters.TEXT, ocr_mode_handler)],
            SSHOT_MODE: [MessageHandler(filters.PHOTO | filters.TEXT, sshot_mode_handler)],
            INSTA_MODE: [
                CommandHandler("rst", insta_reset_command),
                CommandHandler("blk", insta_bulk_command),
                MessageHandler(filters.TEXT & ~filters.COMMAND, insta_mode_handler),
            ],
        },
        fallbacks=[
            CommandHandler("mode", mode_command),
            CommandHandler("start", start_command),
            CommandHandler("help", help_command),
        ],
        allow_reentry=True
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about_command))
    
    # Set bot commands
    commands = [
        BotCommand("start", "Start bot"),
        BotCommand("mode", "Switch mode"),
        BotCommand("rst", "Instagram reset"),
        BotCommand("blk", "Bulk reset"),
        BotCommand("newchat", "Clear chat"),
        BotCommand("help", "Help"),
        BotCommand("about", "About"),
    ]
    await application.bot.set_my_commands(commands)
    
    await application.initialize()
    await application.start()
    
    # Set webhook if URL provided
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/{TELEGRAM_TOKEN}"
        await application.bot.set_webhook(webhook_url)
        logger.info(f"Webhook set: {webhook_url}")
    
    logger.info("Bot initialized successfully")

# =========================
# FastAPI App
# =========================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifecycle"""
    logger.info("Starting bot...")
    await setup_bot()
    yield
    logger.info("Shutting down bot...")
    if application:
        await application.stop()
        await application.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def health():
    """Health check"""
    return {"status": "ok", "bot": "running"}

@app.post("/{token}")
async def webhook(token: str, request: Request):
    """Handle webhook updates"""
    if token != TELEGRAM_TOKEN:
        return Response(status_code=401)
    
    if not application:
        return Response(status_code=503)
    
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return Response(status_code=500)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
