import os
import logging
import asyncio
import html
import uuid
import string
import random
import requests
import google.generativeai as genai
from telegram import Update, BotCommand, ReplyKeyboardMarkup, ReplyKeyboardRemove, ParseMode
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
import time
import json

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

# Initialize Gemini model
try:
    model = genai.GenerativeModel('gemini-1.5-flash')
    logger.info("Successfully initialized Gemini model")
except Exception as e:
    logger.error(f"Failed to initialize Gemini model: {e}")
    exit(1)

# =========================
# Instagram Reset Bot Feature - REVISED AND STABLE METHOD
# =========================

async def send_password_reset(target: str) -> str:
    """
    Send password reset request to Instagram.
    This function is adapted from the stable, single-purpose bot.
    """
    try:
        if '@' in target:
            data = {
                '_csrftoken': ''.join(random.choices(string.ascii_letters + string.digits, k=32)),
                'user_email': target,
                'guid': str(uuid.uuid4()),
                'device_id': str(uuid.uuid4())
            }
        else: 
            data = {
                '_csrftoken': ''.join(random.choices(string.ascii_letters + string.digits, k=32)),
                'username': target,
                'guid': str(uuid.uuid4()),
                'device_id': str(uuid.uuid4())
            }
        
        headers = {
            'user-agent': f"Instagram 150.0.0.0.000 Android (29/10; 300dpi; 720x1440; {''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}/{''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}; {''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}; {''.join(random.choices(string.ascii_lowercase + string.digits, k=16))}; en_GB;)"
        }
        
        # NOTE: requests is a synchronous library. In a high-load async environment,
        # an async HTTP client like httpx would be more performant.
        # However, for this use case and to match the original script's logic, this is sufficient.
        response = requests.post(
            'https://i.instagram.com/api/v1/accounts/send_password_reset/',
            headers=headers,
            data=data,
            timeout=30
        )
        
        if 'obfuscated_email' in response.text:
            return f"✅ *Success!* Password reset link sent for: `{target}`"
        else:
            # Provide more helpful feedback if possible
            try:
                error_data = response.json()
                error_message = error_data.get('message', response.text)
                return f"❌ *Failed* for: `{target}`\nReason: `{error_message}`"
            except json.JSONDecodeError:
                return f"❌ *Failed* for: `{target}`\nRaw Error: `{response.text}`"
            
    except Exception as e:
        logger.error(f"Exception during password reset for {target}: {e}")
        return f"❌ *Error* for: `{target}`\nException: `{str(e)}`"

async def insta_reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Instagram reset in Instagram mode"""
    try:
        if not context.args:
            await update.message.reply_text(
                "Usage: /rst username_or_email\nExample: /rst johndoe\nExample: /rst johndoe@gmail.com"
            )
            return INSTA_MODE
        
        target = context.args[0].strip()
        
        if len(target) < 3:
            await update.message.reply_text(
                "Invalid input. Please provide a valid username or email address (at least 3 characters)."
            )
            return INSTA_MODE
        
        processing_msg = await update.message.reply_text(
            f"🔄 Processing Instagram reset for: `{target}`...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Send reset request using the API method
        result = await send_password_reset(target)
        await processing_msg.edit_text(result, parse_mode=ParseMode.MARKDOWN)
        return INSTA_MODE
        
    except Exception as e:
        logger.error(f"Error in insta_reset_command: {e}")
        await update.message.reply_text("❌ Error processing your request. Please try again.")
        return INSTA_MODE

async def insta_bulk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bulk Instagram reset"""
    try:
        if not context.args:
            await update.message.reply_text(
                "Usage: /blk user1 user2 user3\nMax 3 accounts per request"
            )
            return INSTA_MODE
        
        targets = [t.strip() for t in context.args[:3] if t.strip()]
        
        if len(context.args) > 3:
            await update.message.reply_text("⚠️ Limited to 3 accounts per request")
        
        if not targets:
            await update.message.reply_text("Please provide valid usernames/emails")
            return INSTA_MODE
        
        processing_msg = await update.message.reply_text(
            f"🔄 Processing bulk Instagram reset for {len(targets)} accounts..."
        )
        
        results = []
        for i, target in enumerate(targets, 1):
            try:
                # Add a small delay between requests to avoid being rate-limited
                await asyncio.sleep(2) 
                result = await send_password_reset(target)
                results.append(f"{i}. {result}")
                
                # Update progress after each account
                progress_text = f"📊 *Bulk Reset Progress: {i}/{len(targets)}*\n\n" + "\n".join(results)
                await processing_msg.edit_text(progress_text, parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                logger.error(f"Error processing target {target}: {e}")
                results.append(f"{i}. ❌ Error processing: `{target}`")
        
        final_text = "📊 *Bulk Reset Complete:*\n\n" + "\n".join(results)
        await processing_msg.edit_text(final_text, parse_mode=ParseMode.MARKDOWN)
        return INSTA_MODE
        
    except Exception as e:
        logger.error(f"Error in insta_bulk_command: {e}")
        await update.message.reply_text("❌ Error processing bulk request. Please try again.")
        return INSTA_MODE


# =========================
# Image Compression Functions
# =========================

def compress_image(image_bytes, max_size=(1024, 1024), quality=85):
    """Compress image to reduce file size and prevent message length errors"""
    try:
        image = Image.open(io.BytesIO(image_bytes))
        
        # Convert to RGB if necessary (for JPEG)
        if image.mode in ('RGBA', 'P', 'LA'):
            image = image.convert('RGB')
        
        # Resize if image is too large
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Save compressed image to bytes
        output_buffer = io.BytesIO()
        image.save(output_buffer, format='JPEG', quality=quality, optimize=True)
        compressed_bytes = output_buffer.getvalue()
        
        logger.info(f"Image compressed from {len(image_bytes)} to {len(compressed_bytes)} bytes")
        return compressed_bytes
        
    except Exception as e:
        logger.error(f"Error compressing image: {e}")
        return image_bytes  # Return original if compression fails

def split_long_message(text, max_length=4000):
    """Split long messages into chunks to avoid Telegram message limits"""
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        
        # Find the last space within the limit
        split_index = text.rfind(' ', 0, max_length)
        if split_index == -1:
            split_index = max_length
        
        chunks.append(text[:split_index])
        text = text[split_index:].strip()
    
    return chunks

# =========================
# Main Menu & Mode Management
# =========================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - entry point to main menu"""
    try:
        user = update.effective_user
        
        # Create mode selection keyboard
        reply_keyboard = [
            ["Instagram Reset"],
            ["Chat Mode", "OCR Mode"],
            ["Screenshot Mode", "Help"]
        ]
        
        welcome_message = (
            f"Hello {user.first_name}!\n\n"
            "🤖 **MULTI-FEATURE BOT**\n\n"
            "🔓 **MAIN FEATURE: INSTAGRAM PASSWORD RESET**\n\n"
            "Select a mode to start:\n"
            "• **Instagram Reset** - Password recovery tool\n"
            "• **Chat Mode** - AI conversations\n"
            "• **OCR Mode** - Extract text from images\n"
            "• **Screenshot Mode** - Analyze screenshots\n\n"
            "⚡ Instant Access - No Verification Required\n\n"
            "Developed by @aadi_io"
        )
        
        await update.message.reply_text(
            welcome_message,
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard, 
                resize_keyboard=True,
                one_time_keyboard=False
            ),
            parse_mode=ParseMode.MARKDOWN
        )
        return MAIN_MENU
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("Welcome! Use the keyboard to select a mode.")
        return MAIN_MENU

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle main menu selections"""
    try:
        text = update.message.text
        
        if text == "Instagram Reset":
            return await switch_to_insta_mode(update, context)
        elif text == "Chat Mode":
            return await switch_to_chat_mode(update, context)
        elif text == "OCR Mode":
            return await switch_to_ocr_mode(update, context)
        elif text == "Screenshot Mode":
            return await switch_to_sshot_mode(update, context)
        elif text == "Help":
            return await help_command(update, context)
        else:
            await update.message.reply_text("Please select a mode from the keyboard below:")
            return MAIN_MENU
    except Exception as e:
        logger.error(f"Error in main_menu_handler: {e}")
        await update.message.reply_text("Error processing your selection. Please try again.")
        return MAIN_MENU

async def switch_to_insta_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to Instagram reset mode"""
    await update.message.reply_text(
        "🔓 *INSTAGRAM RESET MODE ACTIVATED*\n\n"
        "✨ Welcome to the Instagram Password Recovery Tool ✨\n\n"
        "🚀 *Available Commands:*\n"
        "`/rst username` - Single account reset\n"
        "`/rst email@gmail.com` - Reset by email\n"
        "`/blk user1 user2` - Bulk reset (max 3 accounts)\n\n"
        "💫 *Examples:*\n"
        "`/rst johndoe`\n"
        "`/blk user1 user2 user3`\n\n"
        "⚡ Start recovering now! Use `/mode` to return to the menu.\n\n"
        "Developed by @aadi_io",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN
    )
    return INSTA_MODE

async def switch_to_chat_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to chat mode"""
    await update.message.reply_text(
        "💬 *Switched to Chat Mode*\n\n"
        "Now you can chat with me normally! Just send your messages and I'll respond.\n\n"
        "Use `/mode` to return to mode selection.\n\n"
        "Developed by @aadi_io",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN
    )
    return CHAT_MODE

async def switch_to_ocr_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to OCR mode"""
    await update.message.reply_text(
        "📷 *Switched to OCR Mode*\n\n"
        "Now send me images and I'll extract text from them!\n\n"
        "Use `/mode` to return to mode selection.\n\n"
        "Developed by @aadi_io",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN
    )
    return OCR_MODE

async def switch_to_sshot_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to screenshot mode"""
    await update.message.reply_text(
        "📱 *Switched to Screenshot Mode*\n\n"
        "Now send me screenshots and I'll analyze them for issues and solutions!\n\n"
        "Use `/mode` to return to mode selection.\n\n"
        "Developed by @aadi_io",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN
    )
    return SSHOT_MODE

async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to mode selection"""
    return await start_command(update, context)

# =========================
# Instagram Mode Handlers
# =========================

async def insta_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle non-command messages in Instagram mode"""
    help_text = (
        "🔓 *Instagram Reset Mode Active*\n\n"
        "Please use a command to proceed:\n\n"
        "`/rst <username/email>`\n"
        "Example: `/rst johndoe`\n\n"
        "`/blk <user1> <user2> ...`\n"
        "Example: `/blk user1 user2`\n\n"
        "Use `/mode` to return to the main menu."
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    return INSTA_MODE

# =========================
# Chat Mode Handlers
# =========================

async def chat_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle normal messages in chat mode"""
    try:
        user_id = update.effective_user.id
        message_text = update.message.text
        
        if message_text.startswith('/'):
            await update.message.reply_text("Use /mode to switch modes or /newchat to clear history.")
            return CHAT_MODE
        
        if user_id not in user_conversations:
            user_conversations[user_id] = []
        
        await update.message.chat.send_action(action="typing")
        
        chat_session = model.start_chat(history=user_conversations[user_id])
        response = chat_session.send_message(message_text)
        
        user_conversations[user_id].extend([
            {"role": "user", "parts": [message_text]},
            {"role": "model", "parts": [response.text]}
        ])
        
        # Keep only last 10 messages to avoid context overflow
        if len(user_conversations[user_id]) > 10:
            user_conversations[user_id] = user_conversations[user_id][-10:]
        
        safe_response = html.escape(response.text)
        
        # Split long messages
        message_chunks = split_long_message(safe_response)
        for i, chunk in enumerate(message_chunks):
            await update.message.reply_text(chunk)
        
    except Exception as e:
        logger.error(f"Error in chat mode: {e}")
        await update.message.reply_text("Sorry, I encountered an error. Please try again or use /newchat.")
    
    return CHAT_MODE

async def newchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset conversation history"""
    user_id = update.effective_user.id
    if user_id in user_conversations:
        user_conversations[user_id] = []
    await update.message.reply_text("✅ Conversation history cleared. You can start a new chat.")
    return CHAT_MODE

# =========================
# OCR & Screenshot Mode Handlers (Combined logic for image processing)
# =========================

async def process_image(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: int):
    """Generic function to handle image processing for OCR and Screenshot modes"""
    try:
        await update.message.chat.send_action(action="typing")
        
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        # Compress image before processing
        compressed_bytes = compress_image(photo_bytes)
        image = Image.open(io.BytesIO(compressed_bytes))
        
        prompt = ""
        result_title = ""
        if mode == OCR_MODE:
            prompt = "Extract all the text from this image. Return only the extracted text without any additional commentary or formatting."
            result_title = "📝 Extracted Text:"
        elif mode == SSHOT_MODE:
            prompt = "Analyze this screenshot. Provide a brief overview, identify key elements, note any potential issues, and suggest solutions or best practices. Be specific and concise."
            result_title = "📊 Screenshot Analysis:"

        response = model.generate_content([prompt, image])
        processed_text = response.text.strip()
        
        if processed_text:
            safe_text = html.escape(processed_text)
            message_chunks = split_long_message(safe_text)
            for i, chunk in enumerate(message_chunks):
                if i == 0:
                     await update.message.reply_text(f"*{result_title}*\n\n{chunk}", parse_mode=ParseMode.MARKDOWN)
                else:
                    await update.message.reply_text(chunk)
        else:
            await update.message.reply_text("❌ No text could be extracted or analyzed from the image.")
            
    except Exception as e:
        logger.error(f"Error in image processing (mode {mode}): {e}")
        await update.message.reply_text("❌ Sorry, I encountered an error processing the image. Please try again.")
    
    return mode

async def ocr_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle images in OCR mode"""
    if not update.message.photo:
        await update.message.reply_text("📷 Please send an image to extract text.")
        return OCR_MODE
    return await process_image(update, context, OCR_MODE)

async def sshot_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle images in screenshot mode"""
    if not update.message.photo:
        await update.message.reply_text("📱 Please send a screenshot to analyze.")
        return SSHOT_MODE
    return await process_image(update, context, SSHOT_MODE)

# =========================
# Help & About Commands
# =========================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """
🤖 *MULTI-FEATURE BOT - Complete Help Guide* 🤖

🔓 *MAIN FEATURE: INSTAGRAM PASSWORD RESET*

📋 *Available Modes:*
• *Instagram Reset* - Password recovery tool
• *Chat Mode* - AI conversations
• *OCR Mode* - Extract text from images  
• *Screenshot Mode* - Analyze screenshots & provide solutions

🔧 *Instagram Reset Commands:*
`/rst <username>` - Single account reset
`/blk <user1> <user2>` - Bulk reset (max 3)

⚡ *General Commands:*
`/start` - Start bot and select mode
`/mode` - Return to mode selection  
`/newchat` - Reset conversation history (in chat mode)

Developed by @aadi_io
    """
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /about command"""
    about_text = """
ℹ️ *About This Multi-Feature Bot*

👨‍💻 *Developer:* @aadi_io

🌟 *FEATURED CAPABILITIES:*

🔓 *MAIN FEATURE: Instagram Password Recovery*
• Instant password reset tool
• Bulk account support (up to 3)
• Enhanced error handling

🤖 *Additional Features:*
• AI-powered conversations
• Image text extraction (OCR)
• Screenshot analysis & troubleshooting

🛠️ *Core Technologies:*
• Telegram Bot API & `python-telegram-bot`
• Google Gemini AI Integration
• FastAPI Web Framework for Webhooks
• Python 3

⚡ *Instant Access - No Verification Required*
    """
    await update.message.reply_text(about_text, parse_mode=ParseMode.MARKDOWN)

# =========================
# Error Handler
# =========================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors in the telegram bot."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=True)
    
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ Sorry, an unexpected error occurred. Use /mode to return to the main menu."
            )
    except Exception as e:
        logger.error(f"Error while sending error message: {e}")

# =========================
# Bot Setup & Webhook Configuration
# =========================

async def setup_commands(app: Application):
    """Setup bot commands menu"""
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
    """Initialize the Telegram bot and set webhook"""
    global application
    
    if not WEBHOOK_URL:
        logger.error("WEBHOOK_URL environment variable is not set. Cannot initialize bot.")
        return

    try:
        # Initialize Telegram application
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .request(HTTPXRequest(connect_timeout=30, read_timeout=30))
            .build()
        )
        
        # Add error handler
        application.add_error_handler(error_handler)
        
        # Create main conversation handler
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start_command)],
            states={
                MAIN_MENU: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_handler)
                ],
                CHAT_MODE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, chat_mode_handler),
                    CommandHandler("newchat", newchat_command),
                ],
                OCR_MODE: [
                    MessageHandler(filters.PHOTO | filters.TEXT, ocr_mode_handler),
                ],
                SSHOT_MODE: [
                    MessageHandler(filters.PHOTO | filters.TEXT, sshot_mode_handler),
                ],
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
        
        # Add conversation handler
        application.add_handler(conv_handler)
        
        # Add global command handlers that should work outside the conversation
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("about", about_command))
        
        # Initialize the application properly
        await application.initialize()
        await application.start()
        logger.info("Telegram application initialized and started")
        
        # Setup commands menu
        await setup_commands(application)
        
        # Set webhook
        webhook_url_path = f"/{TELEGRAM_TOKEN}"
        full_webhook_url = f"{WEBHOOK_URL}{webhook_url_path}"
        await application.bot.set_webhook(full_webhook_url)
        logger.info(f"Webhook set to: {full_webhook_url}")
        
        logger.info("Bot initialization completed successfully!")
        
    except Exception as e:
        logger.error(f"Error during bot initialization: {e}")
        if application:
            await application.stop()
        raise

# =========================
# FastAPI Routes & Server Setup
# =========================

@app.on_event("startup")
async def startup_event():
    """Initialize bot on startup"""
    logger.info("Starting up FastAPI application...")
    asyncio.create_task(initialize_bot())

@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown bot application properly"""
    if application:
        logger.info("Shutting down Telegram application...")
        await application.stop()
        await application.shutdown()
        logger.info("Telegram application stopped successfully")

@app.get("/", include_in_schema=False)
@app.head("/", include_in_schema=False)
async def health_check():
    """Health check endpoint"""
    return JSONResponse(
        content={"status": "ok", "message": "Bot is running"},
        status_code=status.HTTP_200_OK
    )

@app.post("/{token}")
async def webhook_endpoint(token: str, request: Request):
    """Webhook endpoint for Telegram updates"""
    if token != TELEGRAM_TOKEN:
        logger.warning(f"Invalid token received: {token}")
        return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED)
    
    if not application:
        logger.error("Application not initialized yet")
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return JSONResponse(status_code=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

if __name__ == "__main__":
    # Use PORT environment variable (default to 8000 for local dev)
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
