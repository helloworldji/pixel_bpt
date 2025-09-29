import os
import logging
import asyncio
import html
import uuid
import string
import random
import requests
import google.generativeai as genai
from telegram import Update, BotCommand, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    filters
)
from telegram.request import HTTPXRequest
from telegram.error import BadRequest, Forbidden
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
import uvicorn
from PIL import Image
import io
import time

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

# Channel configuration for Instagram reset feature
CHANNELS = [
    {"url": "https://t.me/+YEObPfKXsK1hNjU9", "name": "Main Channel", "id": "-1002628211220"},
    {"url": "https://t.me/pytimebruh", "name": "Backup 1", "id": "@pytimebruh"},
    {"url": "https://t.me/HazyPy", "name": "Backup 2", "id": "@HazyPy"},
    {"url": "https://t.me/HazyGC", "name": "Chat Group", "id": "@HazyGC"}
]

# Initialize Gemini model
try:
    model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')
    logger.info("Successfully initialized Gemini model")
except Exception as e:
    logger.error(f"Failed to initialize Gemini model: {e}")
    model = genai.GenerativeModel('gemini-1.5-flash')

# =========================
# Instagram Reset Bot Feature - FIXED API METHOD
# =========================

class InstagramResetHandler:
    def __init__(self):
        self.user_sessions = {}

    async def check_channel_subscription(self, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> tuple[bool, list]:
        """
        Check if user is subscribed to all channels
        Returns (is_subscribed, not_joined_channels)
        """
        not_joined = []
        
        for channel in CHANNELS:
            try:
                chat_id = channel['id']
                member = await context.bot.get_chat_member(chat_id, user_id)
                
                # Check if user is a member (not left or kicked)
                if member.status in ['left', 'kicked']:
                    not_joined.append(channel)
                    logger.info(f"User {user_id} not in channel {channel['name']}: {member.status}")
                    
            except BadRequest as e:
                logger.error(f"BadRequest checking {channel['name']}: {e}")
                # If we can't check, assume they're not joined
                not_joined.append(channel)
                
            except Forbidden as e:
                logger.error(f"Bot not admin in {channel['name']}: {e}")
                # Critical: Bot needs to be admin to check membership
                not_joined.append(channel)
                
            except Exception as e:
                logger.error(f"Error checking channel {channel['name']}: {e}")
                not_joined.append(channel)
                
        return len(not_joined) == 0, not_joined

    async def send_password_reset(self, target: str) -> str:
        """Send password reset request to Instagram using mobile API method"""
        try:
            # Generate random device identifiers
            device_id = f"android-{''.join(random.choices(string.hexdigits, k=16))}"
            guid = str(uuid.uuid4())
            
            # Prepare data based on input type
            if '@' in target:
                data = {
                    'email_or_username': target,
                    'device_id': device_id,
                }
            else:
                data = {
                    'username_or_email': target,
                    'device_id': device_id,
                }
            
            # Mobile API headers
            headers = {
                'User-Agent': 'Instagram 219.0.0.12.117 Android',
                'Accept': '*/*',
                'Accept-Language': 'en-US',
                'Accept-Encoding': 'gzip, deflate',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-IG-Capabilities': '3brTvw==',
                'X-IG-Connection-Type': 'WIFI',
                'X-IG-App-ID': '567067343352427',
                'Connection': 'close',
            }
            
            logger.info(f"Attempting Instagram API reset for: {target}")
            
            # Use the account recovery endpoint
            response = requests.post(
                'https://i.instagram.com/api/v1/accounts/send_password_reset/',
                headers=headers,
                data=data,
                timeout=30
            )
            
            logger.info(f"API Response Status: {response.status_code}")
            logger.info(f"API Response: {response.text}")
            
            if response.status_code == 200:
                response_data = response.json()
                if response_data.get('status') == 'ok':
                    return f"✅ Password reset email sent successfully for: {target}"
                else:
                    error_msg = response_data.get('message', 'Unknown error')
                    return f"❌ Instagram API error for {target}: {error_msg}"
            elif response.status_code == 400:
                return f"❌ Bad request (400) for {target}. This usually means the account doesn't exist or Instagram blocked the request."
            elif response.status_code == 429:
                return f"❌ Rate limit exceeded for {target}. Please try again later."
            else:
                return f"❌ Instagram returned status {response.status_code} for: {target}"
                
        except requests.exceptions.Timeout:
            return f"❌ Request timeout for: {target}"
        except requests.exceptions.ConnectionError:
            return f"❌ Connection error for: {target}"
        except Exception as e:
            logger.error(f"Error in Instagram API reset: {e}")
            return f"❌ Error processing reset for: {target}"

    async def create_subscription_keyboard(self, not_joined_channels=None) -> InlineKeyboardMarkup:
        """Create subscription check keyboard"""
        keyboard = []
        
        channels_to_show = not_joined_channels if not_joined_channels else CHANNELS
        
        for channel in channels_to_show:
            keyboard.append([InlineKeyboardButton(
                f"🔗 Join {channel['name']}", 
                url=channel['url']
            )])
        
        keyboard.append([InlineKeyboardButton(
            "✅ I JOINED ALL CHANNELS", 
            callback_data="check_subscription"
        )])
        
        return InlineKeyboardMarkup(keyboard)

    async def send_force_join_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, not_joined_channels: list = None):
        """Send force join message"""
        keyboard = await self.create_subscription_keyboard(not_joined_channels)
        
        message_text = """
🚫 **ACCESS RESTRICTED** 🚫

❗️ **You must join ALL our channels to use Instagram Reset!**

📋 **Missing channels:**
"""
        
        if not_joined_channels:
            for channel in not_joined_channels:
                message_text += f"• {channel['name']}\n"
        else:
            message_text += "• Please join all channels below\n"
            
        message_text += """
🔄 **Steps:**
1️⃣ Click each "Join" button below
2️⃣ Join ALL channels/groups  
3️⃣ Click "I JOINED ALL CHANNELS"

⚠️ **Bot will verify your membership!**
        """
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                message_text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                message_text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )

# Create Instagram handler instance
insta_handler = InstagramResetHandler()

async def insta_reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Instagram reset in Instagram mode"""
    user_id = update.effective_user.id
    
    # Check subscription
    subscribed, not_joined = await insta_handler.check_channel_subscription(user_id, context)
    
    if not subscribed:
        await insta_handler.send_force_join_message(update, context, not_joined)
        return INSTA_MODE
    
    if not context.args:
        await update.message.reply_text(
            "Usage: /rst username_or_email\nExample: /rst johndoe\nExample: /rst johndoe@gmail.com"
        )
        return INSTA_MODE
    
    target = context.args[0]
    
    if len(target) < 3:
        await update.message.reply_text(
            "Invalid input. Please provide a valid username or email address."
        )
        return INSTA_MODE
    
    processing_msg = await update.message.reply_text(
        f"🔄 Processing Instagram reset for: `{target}`\nThis may take 10-15 seconds...",
        parse_mode='Markdown'
    )
    
    # Send reset request using the API method
    result = await insta_handler.send_password_reset(target)
    await processing_msg.edit_text(result, parse_mode='Markdown')
    return INSTA_MODE

async def insta_bulk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bulk Instagram reset"""
    user_id = update.effective_user.id
    
    # Check subscription
    subscribed, not_joined = await insta_handler.check_channel_subscription(user_id, context)
    
    if not subscribed:
        await insta_handler.send_force_join_message(update, context, not_joined)
        return INSTA_MODE
    
    if not context.args:
        await update.message.reply_text(
            "Usage: /blk user1 user2 user3\nMax 3 accounts per request"
        )
        return INSTA_MODE
    
    targets = context.args[:3]
    if len(context.args) > 3:
        await update.message.reply_text("Limited to 3 accounts per request")
    
    processing_msg = await update.message.reply_text(
        f"🔄 Processing bulk Instagram reset for {len(targets)} accounts...",
        parse_mode='Markdown'
    )
    
    results = []
    for i, target in enumerate(targets, 1):
        await asyncio.sleep(5)  # Rate limiting
        result = await insta_handler.send_password_reset(target)
        results.append(f"{i}. {result}")
        
        # Update progress
        progress_text = f"Progress: {i}/{len(targets)} accounts\n\n" + "\n".join(results[-3:])
        await processing_msg.edit_text(progress_text, parse_mode='Markdown')
    
    final_text = "📊 Bulk Reset Results:\n" + "\n".join(results)
    await processing_msg.edit_text(final_text, parse_mode='Markdown')
    return INSTA_MODE

async def insta_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks for Instagram subscription"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == "check_subscription":
        # Re-check subscription
        subscribed, not_joined = await insta_handler.check_channel_subscription(user_id, context)
        
        if subscribed:
            await query.edit_message_text(
                "✅ **Verification Successful!** 🎉\n\n"
                "🔓 **You can now use Instagram reset features!**\n\n"
                "📖 Use /help to see available commands.\n"
                "🚀 Use /rst for single reset\n"
                "⚡ Use /blk for bulk reset\n\n"
                "@aadi_io",
                parse_mode='Markdown'
            )
        else:
            await insta_handler.send_force_join_message(update, context, not_joined)

# =========================
# Image Compression Functions
# =========================

def compress_image(image_bytes, max_size=(1024, 1024), quality=85):
    """Compress image to reduce file size and prevent message length errors"""
    try:
        image = Image.open(io.BytesIO(image_bytes))
        
        # Convert to RGB if necessary (for JPEG)
        if image.mode in ('RGBA', 'P'):
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
            "MULTI-FEATURE BOT\n\n"
            "MAIN FEATURE: INSTAGRAM PASSWORD RESET\n\n"
            "Select a mode to start:\n"
            "Instagram Reset - Password recovery tool\n"
            "Chat Mode - AI conversations\n"
            "OCR Mode - Extract text from images\n"
            "Screenshot Mode - Analyze screenshots\n\n"
            "Instant Access - No Verification Required\n\n"
            "@aadi_io"
        )
        
        await update.message.reply_text(
            welcome_message,
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard, 
                resize_keyboard=True,
                one_time_keyboard=False
            )
        )
        return MAIN_MENU
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("Welcome! Use the keyboard to select a mode.")
        return MAIN_MENU

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle main menu selections"""
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

async def switch_to_insta_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to Instagram reset mode"""
    try:
        user_id = update.effective_user.id
        
        # Check subscription when switching to Instagram mode
        subscribed, not_joined = await insta_handler.check_channel_subscription(user_id, context)
        
        if not subscribed:
            await insta_handler.send_force_join_message(update, context, not_joined)
            return INSTA_MODE
            
        await update.message.reply_text(
            "🔓 **INSTAGRAM RESET MODE ACTIVATED** 🔓\n\n"
            "✨ *Welcome to the most advanced IG recovery tool!* ✨\n\n"
            "🚀 **Available Commands:**\n"
            "/rst username - Single account reset\n"
            "/rst email@gmail.com - Reset by email\n"
            "/blk user1 user2 - Bulk reset (max 3 accounts)\n\n"
            "💫 **Examples:**\n"
            "/rst johndoe\n"
            "/rst johndoe@gmail.com\n"
            "/blk user1 user2 user3\n\n"
            "⚡ *Start recovering now!*\n\n"
            "@aadi_io",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='Markdown'
        )
        return INSTA_MODE
    except Exception as e:
        logger.error(f"Error switching to Instagram mode: {e}")
        return MAIN_MENU

async def switch_to_chat_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to chat mode"""
    try:
        await update.message.reply_text(
            "Switched to Chat Mode\n\n"
            "Now you can chat with me normally! Just send your messages and I'll respond.\n\n"
            "Use /mode to return to mode selection.",
            reply_markup=ReplyKeyboardRemove()
        )
        return CHAT_MODE
    except Exception as e:
        logger.error(f"Error switching to chat mode: {e}")
        return MAIN_MENU

async def switch_to_ocr_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to OCR mode"""
    try:
        await update.message.reply_text(
            "Switched to OCR Mode\n\n"
            "Now send me images and I'll extract text from them!\n\n"
            "Use /mode to return to mode selection.",
            reply_markup=ReplyKeyboardRemove()
        )
        return OCR_MODE
    except Exception as e:
        logger.error(f"Error switching to OCR mode: {e}")
        return MAIN_MENU

async def switch_to_sshot_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to screenshot mode"""
    try:
        await update.message.reply_text(
            "Switched to Screenshot Mode\n\n"
            "Now send me screenshots and I'll analyze them for issues and solutions!\n\n"
            "Use /mode to return to mode selection.",
            reply_markup=ReplyKeyboardRemove()
        )
        return SSHOT_MODE
    except Exception as e:
        logger.error(f"Error switching to screenshot mode: {e}")
        return MAIN_MENU

async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to mode selection"""
    return await start_command(update, context)

# =========================
# Instagram Mode Handlers
# =========================

async def insta_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages in Instagram mode"""
    message_text = update.message.text
    
    if message_text.startswith('/'):
        await update.message.reply_text(
            "Use /rst or /blk commands for Instagram reset, or /mode to switch modes."
        )
        return INSTA_MODE
    
    help_text = """
🔓 **Instagram Reset Mode Active** 🔓

✨ *Advanced Instagram Password Recovery Tool* ✨

**Available Commands:**
/rst username - Single account reset
/rst email@gmail.com - Reset by email  
/blk user1 user2 - Bulk reset (max 3 accounts)

**Examples:**
/rst johndoe
/rst johndoe@gmail.com  
/blk user1 user2 user3

💡 **Tips:**
• Use username or email
• Works with both public and private accounts
• High success rate

Use /mode to return to main menu.

@aadi_io
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')
    return INSTA_MODE

# =========================
# Chat Mode Handlers
# =========================

async def chat_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle normal messages in chat mode"""
    user_id = update.effective_user.id
    message_text = update.message.text
    
    if message_text.startswith('/'):
        await update.message.reply_text("Use /mode to switch modes.")
        return CHAT_MODE
    
    try:
        if user_id not in user_conversations:
            user_conversations[user_id] = []
        
        await update.message.chat.send_action(action="typing")
        
        chat_session = model.start_chat(history=user_conversations[user_id])
        response = chat_session.send_message(message_text)
        
        user_conversations[user_id].extend([
            {"role": "user", "parts": [message_text]},
            {"role": "model", "parts": [response.text]}
        ])
        
        if len(user_conversations[user_id]) > 20:
            user_conversations[user_id] = user_conversations[user_id][-20:]
        
        safe_response = html.escape(response.text)
        
        # Split long messages
        message_chunks = split_long_message(safe_response)
        for i, chunk in enumerate(message_chunks):
            if i == len(message_chunks) - 1:
                await update.message.reply_text(f"{chunk}\n\n@aadi_io")
            else:
                await update.message.reply_text(chunk)
        
    except Exception as e:
        logger.error(f"Error in chat mode: {e}")
        await update.message.reply_text("Sorry, I encountered an error. Please try again.")
    
    return CHAT_MODE

async def newchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset conversation history"""
    try:
        user_id = update.effective_user.id
        
        if user_id in user_conversations:
            user_conversations[user_id] = []
            await update.message.reply_text("Conversation history cleared. Continuing in chat mode.\n\n@aadi_io")
        else:
            await update.message.reply_text("No active chat session to clear. Continuing in chat mode.\n\n@aadi_io")
    except Exception as e:
        logger.error(f"Error in newchat command: {e}")
        await update.message.reply_text("Error clearing conversation. Continuing in chat mode.")
    
    return CHAT_MODE

# =========================
# OCR Mode Handlers
# =========================

async def ocr_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle images in OCR mode"""
    if not update.message.photo:
        await update.message.reply_text(
            "OCR Mode Active\n\n"
            "Please send an image containing text for extraction.\n\n"
            "Use /mode to switch modes."
        )
        return OCR_MODE
    
    try:
        await update.message.chat.send_action(action="typing")
        
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        # Compress image before processing
        compressed_bytes = compress_image(photo_bytes)
        image = Image.open(io.BytesIO(compressed_bytes))
        
        response = model.generate_content([
            "Extract all the text from this image. Return only the extracted text without any additional commentary or formatting.",
            image
        ])
        
        extracted_text = response.text.strip()
        
        if extracted_text:
            safe_text = html.escape(extracted_text)
            
            # Split long OCR results
            message_chunks = split_long_message(safe_text)
            for i, chunk in enumerate(message_chunks):
                if i == len(message_chunks) - 1:
                    await update.message.reply_text(
                        f"Extracted Text:\n\n{chunk}\n\n"
                        f"OCR Mode still active - send another image or use /mode to switch.\n\n"
                        f"@aadi_io"
                    )
                else:
                    await update.message.reply_text(chunk)
        else:
            await update.message.reply_text(
                "No text could be extracted from the image.\n\n"
                "OCR Mode still active - send another image or use /mode to switch.\n\n"
                "@aadi_io"
            )
            
    except Exception as e:
        logger.error(f"Error in OCR mode processing: {e}")
        await update.message.reply_text(
            "Sorry, I encountered an error processing the image. Please try again.\n\n"
            "OCR Mode still active\n\n"
            "@aadi_io"
        )
    
    return OCR_MODE

# =========================
# Screenshot Mode Handlers
# =========================

async def sshot_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle images in screenshot mode with compression"""
    if not update.message.photo:
        await update.message.reply_text(
            "Screenshot Mode Active\n\n"
            "Please send a screenshot for analysis.\n\n"
            "Use /mode to switch modes."
        )
        return SSHOT_MODE
    
    try:
        await update.message.chat.send_action(action="typing")
        
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        # Compress image before processing to avoid size issues
        compressed_bytes = compress_image(photo_bytes)
        image = Image.open(io.BytesIO(compressed_bytes))
        
        analysis_prompt = """
        Analyze this screenshot and provide:
        1. Overview of what's visible
        2. Key elements and text
        3. Any issues or notable observations
        4. Solutions and recommendations
        5. Best practices

        Be specific and focus on clear guidance. Keep response concise.
        """
        
        response = model.generate_content([analysis_prompt, image])
        
        analysis_text = response.text.strip()
        
        if analysis_text:
            safe_analysis = html.escape(analysis_text)
            
            # Split long analysis results to avoid message length errors
            message_chunks = split_long_message(safe_analysis)
            for i, chunk in enumerate(message_chunks):
                if i == len(message_chunks) - 1:
                    await update.message.reply_text(
                        f"Screenshot Analysis:\n\n{chunk}\n\n"
                        f"Screenshot Mode still active - send another screenshot or use /mode to switch.\n\n"
                        f"@aadi_io"
                    )
                else:
                    await update.message.reply_text(chunk)
        else:
            await update.message.reply_text(
                "I couldn't generate a detailed analysis for this screenshot. Please try with a clearer image.\n\n"
                "Screenshot Mode still active - send another screenshot or use /mode to switch.\n\n"
                "@aadi_io"
            )
            
    except Exception as e:
        logger.error(f"Error in screenshot mode analysis: {e}")
        await update.message.reply_text(
            "Sorry, I encountered an error analyzing the screenshot. Please try again.\n\n"
            "Screenshot Mode still active\n\n"
            "@aadi_io"
        )
    
    return SSHOT_MODE

# =========================
# Help & About Commands
# =========================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """
🤖 **MULTI-FEATURE BOT - Complete Help Guide** 🤖

🔓 **MAIN FEATURE: INSTAGRAM PASSWORD RESET**

📋 **Available Modes:**
• Instagram Reset - Password recovery tool
• Chat Mode - AI conversations
• OCR Mode - Extract text from images  
• Screenshot Mode - Analyze screenshots & provide solutions

🔧 **Instagram Reset Commands:**
/rst username - Single account reset
/rst email@gmail.com - Reset by email
/blk user1 user2 - Bulk reset (max 3 accounts)

⚡ **General Commands:**
/start - Start bot and select mode
/mode - Return to mode selection  
/newchat - Reset conversation history (in chat mode)

💫 **Instant Access - No Verification Required**

🚀 **Usage:** Select a mode, then interact normally!

@aadi_io
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /about command"""
    about_text = """
ℹ️ **About This Multi-Feature Bot**

👨‍💻 **Developer:** @aadi_io

🌟 **FEATURED CAPABILITIES:**

🔓 **MAIN FEATURE: Instagram Password Recovery**
• Instant password reset tool
• Bulk account support
• Enhanced error handling
• Channel subscription system

🤖 **Additional Features:**
• AI-powered conversations
• Image text extraction (OCR)
• Screenshot analysis & troubleshooting

🛠️ **Core Technologies:**
• Telegram Bot API
• AI Integration
• FastAPI Web Framework
• Python

⚡ **Instant Access - No Verification Required**

@aadi_io
    """
    await update.message.reply_text(about_text, parse_mode='Markdown')

# =========================
# Error Handler
# =========================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors in the telegram bot."""
    logger.error(f"Exception while handling an update: {context.error}")
    
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "Sorry, I encountered an error. Use /mode to return to mode selection."
            )
    except Exception as e:
        logger.error(f"Error while sending error message: {e}")

# =========================
# Bot Setup & Webhook Configuration
# =========================

async def setup_commands(app: Application):
    """Setup bot commands menu"""
    try:
        commands = [
            BotCommand("start", "Start bot and select mode"),
            BotCommand("mode", "Return to mode selection"),
            BotCommand("rst", "Instagram single account reset"),
            BotCommand("blk", "Instagram bulk reset (max 3)"),
            BotCommand("newchat", "Reset conversation history"),
            BotCommand("help", "Get help guide"),
            BotCommand("about", "About this bot"),
        ]
        await app.bot.set_my_commands(commands)
        logger.info("Bot commands menu set successfully")
    except Exception as e:
        logger.error(f"Error setting up commands: {e}")

async def initialize_bot():
    """Initialize the Telegram bot and set webhook"""
    global application
    
    # Wait for WEBHOOK_URL to be available
    max_retries = 24
    webhook_url_env = None
    
    for i in range(max_retries):
        webhook_url_env = os.getenv('WEBHOOK_URL')
        if webhook_url_env:
            logger.info(f"WEBHOOK_URL found: {webhook_url_env}")
            break
        elif i == max_retries - 1:
            logger.error("WEBHOOK_URL not found after 2 minutes. Exiting.")
            return
        else:
            logger.info(f"Waiting for WEBHOOK_URL... (attempt {i+1}/{max_retries})")
            await asyncio.sleep(5)
    
    if not webhook_url_env:
        logger.error("WEBHOOK_URL not available after retries")
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
                    MessageHandler(filters.PHOTO, ocr_mode_handler),
                ],
                SSHOT_MODE: [
                    MessageHandler(filters.PHOTO, sshot_mode_handler),
                ],
                INSTA_MODE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, insta_mode_handler),
                    CommandHandler("rst", insta_reset_command),
                    CommandHandler("blk", insta_bulk_command),
                    CallbackQueryHandler(insta_button_callback, pattern="^check_subscription$")
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
        
        # Add global command handlers
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("about", about_command))
        application.add_handler(CommandHandler("mode", mode_command))
        
        # Initialize the application properly
        await application.initialize()
        await application.start()
        logger.info("Telegram application initialized and started")
        
        # Setup commands menu
        await setup_commands(application)
        
        # Set webhook
        webhook_url = f"{webhook_url_env}/{TELEGRAM_TOKEN}"
        await application.bot.set_webhook(webhook_url)
        logger.info(f"Webhook set to: {webhook_url}")
        
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
    global application
    if application:
        logger.info("Shutting down Telegram application...")
        await application.stop()
        await application.shutdown()
        logger.info("Telegram application stopped successfully")

@app.get("/")
@app.head("/")
async def health_check():
    """Health check endpoint for Render"""
    return JSONResponse(
        content={"status": "ok"},
        status_code=status.HTTP_200_OK
    )

@app.post("/{token}")
async def webhook_endpoint(token: str, request: Request):
    """Webhook endpoint for Telegram updates"""
    global application
    
    if token != TELEGRAM_TOKEN:
        logger.warning(f"Invalid token received: {token}")
        return JSONResponse(
            content={"status": "invalid token"},
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    
    if not application:
        logger.error("Application not initialized yet")
        return JSONResponse(
            content={"status": "service unavailable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return JSONResponse(
            content={"status": "ok"},
            status_code=status.HTTP_200_OK
        )
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return JSONResponse(
            content={"status": "error"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

if __name__ == "__main__":
    # Use Render's PORT environment variable (default to 10000 for Render)
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
