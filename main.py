# =================================================================================================
# 🚀 ADVANCED MULTI-FUNCTIONAL TELEGRAM BOT (OPTIMIZED)
# =================================================================================================
# This bot integrates several features:
# 1. Instagram Tools: Heavily optimized password reset to reduce rate-limiting.
# 2. Utility Tools: URL shortening, QR codes, PDF creation, and a self-destructing password generator.
# 3. Weather: Real-time weather forecasts via Visual Crossing.
# 4. Advanced AI Features: Conversational chat, image analysis, and a new interactive AI utilities menu.
# 5. Web Framework: Deployed using FastAPI and Uvicorn for webhook support.
#
# Dev: Aadi (@aadi_io)
# =================================================================================================

import os
import logging
import asyncio
import uuid
import string
import random
import io
import secrets
from typing import Dict, List, Optional

import httpx
import uvicorn
import qrcode  # Dependency: pip install qrcode[pil]
from PIL import Image
from fpdf import FPDF # Dependency: pip install fpdf2
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
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
WEATHER_API_KEY = "EKCSKX5PQBL52PZGCGJDXHCU4" # Hardcoded as requested

if not BOT_TOKEN or not GEMINI_API_KEY:
    logger.critical("FATAL ERROR: Bot token or Gemini API key is missing!")
    exit(1)

# =====================================
# GLOBAL VARIABLES & STATE
# =====================================
telegram_app: Optional[Application] = None
user_sessions: Dict[int, Dict] = {}
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}
USER_AGENTS = [
    "Instagram 113.0.0.39.122 Android/24 (API 24; 640dpi; 1440x2560; samsung; SM-G935F; hero2lte; samsungexynos8890; en_US)",
    "Instagram 150.0.0.22.122 Android (29/10; 450dpi; 1080x2340; samsung; SM-A505F; a50; exynos9610; en_US; 233481232)",
    "Instagram 169.0.0.28.122 Android (28/9; 480dpi; 1080x2160; OnePlus; ONEPLUS A6003; OnePlus6; qcom; en_US; 254236932)",
    "Instagram 203.0.0.28.120 Android (29/10; 440dpi; 1080x2340; Xiaomi; Mi 9T; davinci; qcom; en_US; 317351663)",
]

# =====================================
# GEMINI AI INITIALIZATION
# =====================================
try:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
    logger.info("✅ Successfully initialized Gemini AI models.")
except Exception as e:
    logger.critical(f"❌ FATAL ERROR: Could not initialize Gemini AI. Error: {e}", exc_info=True)
    exit(1)

# =====================================
# USER SESSION MANAGEMENT
# =====================================
def get_user_session(user_id: int) -> Dict:
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            'mode': 'menu', 'history': [], 'last_analysis': None, 'pdf_images': [], 'ai_utility_mode': None
        }
    return user_sessions[user_id]

def set_user_mode(user_id: int, mode: str, ai_utility: Optional[str] = None) -> None:
    session = get_user_session(user_id)
    session['mode'] = mode
    session['ai_utility_mode'] = ai_utility
    logger.info(f"User {user_id} switched to mode: {mode} (Utility: {ai_utility})")

# =====================================
# SHARED HELPER FUNCTIONS
# =====================================
def split_long_message(text: str, max_length: int = 4096) -> List[str]:
    if not isinstance(text, str): return []
    chunks = []
    while len(text) > max_length:
        split_pos = text.rfind('\n', 0, max_length)
        if split_pos == -1: split_pos = max_length
        chunks.append(text[:split_pos]); text = text[split_pos:]
    chunks.append(text)
    return chunks

# =====================================
# CORE COMMAND HANDLERS
# =====================================
async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user = update.effective_user; user_id = user.id
        session = get_user_session(user_id)
        set_user_mode(user_id, 'menu')
        session['history'].clear(); session['pdf_images'].clear()
        logger.info(f"User {user.id} ({user.username}) started the bot.")
        keyboard = [
            ["🔓 Instagram", "🔑 Gen Password"], ["🔗 URL Shortener", "🔳 QR Code"],
            ["📄 Image to PDF", "🌤️ Weather"], ["💬 AI Chat", "📷 Image Analysis"],
            ["🤖 AI Utilities", "❓ Help"],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        welcome_text = (
            f"👋 **Welcome, {user.first_name}!**\n\n"
            "I'm your all-in-one assistant bot. Here's a quick look at what I can do:\n\n"
            "📸 **Social & Media**: Instagram tools, PDF creation, QR codes.\n"
            "🛠️ **Utilities**: URL shortener, password generator, weather.\n"
            "🧠 **AI-Powered**: Advanced chat, image analysis, and special AI utilities.\n\n"
            "👇 Select an option from the menu to begin.\n\n"
            "*Dev: Aadi (@aadi_io)*"
        )
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error in /start handler: {e}", exc_info=True)

async def help_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = """
    *🤖 Bot Help & Commands Guide*

    *Social & Media*
    • `/rst <user>`: Single Instagram reset.
    • `/bulk <users...>`: Bulk Instagram reset.
    • *Image to PDF*: Select from menu, send images, then `/createpdf`. Use `/cancelpdf` to abort.

    *Utilities*
    • `/shorten <url>`: Shortens a long URL.
    • `/qr <text>`: Generates a QR code.
    • `/genpass <len>`: Creates a secure password.
    • `/weather <city>`: Gets the weather forecast.

    *AI Tools*
    • *AI Chat*: Conversational mode. Use `/clear` to reset.
    • *Image Analysis*: Get insights on any image.
    • *AI Utilities*: Select from the menu for Summarize, Email, and Code help.

    *General*
    • `/start` or `/menu`: Return to the main menu.
    """
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

# =====================================
# INSTAGRAM FEATURE [HEAVILY OPTIMIZED]
# =====================================
def _generate_device_info() -> Dict:
    """Generates a realistic, randomized set of device identifiers for each request."""
    return {
        'guid': str(uuid.uuid4()),
        'phone_id': str(uuid.uuid4()),
        'device_id': f'android-{uuid.uuid4().hex[:16]}',
        '_csrftoken': ''.join(random.choices(string.ascii_letters + string.digits, k=32)),
    }

async def send_instagram_reset(target: str) -> Dict:
    await asyncio.sleep(random.uniform(1.0, 2.5)) # Increased random delay
    try:
        clean_target = target.strip().lstrip('@')
        logger.info(f"Processing Instagram reset for target: {clean_target}")
        
        headers = {'User-Agent': random.choice(USER_AGENTS), 'X-IG-App-ID': '936619743392459'}
        payload = _generate_device_info()

        if '@' in clean_target and '.' in clean_target: payload['user_email'] = clean_target
        elif clean_target.isdigit(): payload['user_id'] = clean_target
        else: payload['username'] = clean_target

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post('https://i.instagram.com/api/v1/accounts/send_password_reset/', headers=headers, data=payload)
        
        logger.info(f"IG API Response for {clean_target}: {response.status_code} - {response.text[:120]}")

        if response.status_code == 200:
            try:
                data = response.json()
                if 'obfuscated_email' in data or 'obfuscated_phone_number' in data:
                    return {'success': True, 'message': f"✅ Reset link sent for *{clean_target}*."}
                elif data.get('spam') is True:
                     return {'success': False, 'message': f"❌ Request blocked as spam for *{clean_target}*."}
                else:
                    return {'success': False, 'message': f"⚠️ Request failed for *{clean_target}*."}
            except Exception:
                return {'success': False, 'message': f"⚠️ Failed to parse response for *{clean_target}*."}
        elif response.status_code == 429:
            return {'success': False, 'message': f"⏳ *Rate Limited.* Instagram is blocking requests. Please wait at least *15-20 minutes* before trying again."}
        elif response.status_code == 404: return {'success': False, 'message': f"❌ Account not found: *{clean_target}*."}
        else: return {'success': False, 'message': f"❌ Error (Status: {response.status_code}) for *{clean_target}*."}
    except httpx.RequestError as e:
        logger.error(f"HTTP error during IG reset: {e}"); return {'success': False, 'message': "❌ Network error connecting to Instagram."}
    except Exception as e:
        logger.error(f"Unexpected error in send_instagram_reset: {e}", exc_info=True); return {'success': False, 'message': "❌ A critical internal error occurred."}

async def rst_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args: await update.message.reply_text("📋 *Usage:* `/rst <username>`", parse_mode=ParseMode.MARKDOWN); return
    msg = await update.message.reply_text(f"🔄 Processing reset for *{context.args[0]}*...", parse_mode=ParseMode.MARKDOWN)
    result = await send_instagram_reset(context.args[0]); await msg.edit_text(result['message'], parse_mode=ParseMode.MARKDOWN)

async def bulk_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args: await update.message.reply_text("📋 *Usage:* `/bulk <user1> <user2>...` (max 3)", parse_mode=ParseMode.MARKDOWN); return
    targets = context.args[:3]; msg = await update.message.reply_text(f"🔄 Processing *{len(targets)}* accounts...", parse_mode=ParseMode.MARKDOWN)
    results = []
    for i, target in enumerate(targets, 1):
        result = await send_instagram_reset(target); results.append(f"*{i}.* {result['message']}")
        try: await msg.edit_text(f"⚙️ *Progress: {i}/{len(targets)}*\n\n" + "\n".join(results), parse_mode=ParseMode.MARKDOWN)
        except Exception: pass
    await msg.edit_text(f"✅ *Bulk processing complete!*\n\n" + "\n".join(results), parse_mode=ParseMode.MARKDOWN)

# =====================================
# UTILITY FEATURES
# =====================================
async def shorten_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args: await update.message.reply_text("📋 *Usage:* `/shorten <url>`", parse_mode=ParseMode.MARKDOWN); return
    long_url = context.args[0]
    if not long_url.startswith(('http://', 'https://')): await update.message.reply_text("❌ *Invalid URL*", parse_mode=ParseMode.MARKDOWN); return
    msg = await update.message.reply_text("🔗 Shortening link...", parse_mode=ParseMode.MARKDOWN)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://tinyurl.com/api-create.php?url={long_url}")
        if response.status_code == 200: await msg.edit_text(f"✅ *Success!* Here is your short link:\n{response.text}", parse_mode=ParseMode.MARKDOWN)
        else: await msg.edit_text("❌ *Error:* Could not shorten the link.", parse_mode=ParseMode.MARKDOWN)
    except Exception as e: logger.error(f"URL shortening error: {e}"); await msg.edit_text("❌ A network error occurred.")

async def qr_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args: await update.message.reply_text("📋 *Usage:* `/qr <text>`", parse_mode=ParseMode.MARKDOWN); return
    text = " ".join(context.args); msg = await update.message.reply_text("🔳 Generating QR code...", parse_mode=ParseMode.MARKDOWN)
    try:
        qr_img = qrcode.make(text); img_buffer = io.BytesIO(); qr_img.save(img_buffer, format='PNG'); img_buffer.seek(0)
        await update.message.reply_photo(photo=img_buffer, caption=f"✅ QR code for:\n`{text}`", parse_mode=ParseMode.MARKDOWN)
        await msg.delete()
    except Exception as e: logger.error(f"QR code error: {e}"); await msg.edit_text("❌ An error occurred.")

async def genpass_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        length = int(context.args[0]) if context.args and context.args[0].isdigit() else 16
        length = min(length, 128)
        alphabet = string.ascii_letters + string.digits + string.punctuation
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        msg = await update.message.reply_text(f"🔑 Your secure password (`{length}` characters):\n\n`{password}`", parse_mode=ParseMode.MARKDOWN)
        
        # Self-destruct logic
        context.job_queue.run_once(
            lambda ctx: ctx.bot.edit_message_text("🔑 Password has been cleared for security.", chat_id=msg.chat_id, message_id=msg.message_id),
            30  # 30 seconds
        )
    except Exception as e: logger.error(f"Password gen error: {e}"); await update.message.reply_text("❌ Error generating password.")

async def weather_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args: await update.message.reply_text("📋 *Usage:* `/weather <city>`", parse_mode=ParseMode.MARKDOWN); return
    city = " ".join(context.args); msg = await update.message.reply_text(f"🌤️ Fetching weather for *{city}*...", parse_mode=ParseMode.MARKDOWN)
    try:
        api_url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{city}/today?unitGroup=metric&include=current&key={WEATHER_API_KEY}&contentType=json"
        async with httpx.AsyncClient() as client: response = await client.get(api_url)
        if response.status_code == 200:
            data = response.json(); current = data['days'][0]
            report = (f"*{data['resolvedAddress']}*\n*{current['conditions']}* ({current['description']})\n\n"
                      f"🌡️ *Temp*: {current['temp']}°C (Feels like: {current['feelslike']}°C)\n"
                      f"💧 *Humidity*: {current['humidity']}%\n💨 *Wind*: {current['windspeed']} km/h")
            await msg.edit_text(report, parse_mode=ParseMode.MARKDOWN)
        else: await msg.edit_text(f"❌ Could not retrieve weather for *{city}*.", parse_mode=ParseMode.MARKDOWN)
    except Exception as e: logger.error(f"Weather error: {e}"); await msg.edit_text("❌ An unexpected error occurred.")

# =====================================
# PDF CREATION FEATURE
# =====================================
async def createpdf_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id; session = get_user_session(user_id)
    if get_user_mode(user_id) != 'pdf_creation' or not session['pdf_images']:
        await update.message.reply_text("No images added. Enter PDF mode and send photos first.", parse_mode=ParseMode.MARKDOWN); return
    msg = await update.message.reply_text(f"📄 Creating PDF from {len(session['pdf_images'])} images...", parse_mode=ParseMode.MARKDOWN)
    try:
        pdf = FPDF()
        for img_bytes in session['pdf_images']:
            with Image.open(io.BytesIO(img_bytes)) as img:
                if img.mode == 'RGBA': img = img.convert('RGB')
                with io.BytesIO() as temp_img_file:
                    img.save(temp_img_file, format='JPEG'); temp_img_file.seek(0)
                    pdf.add_page(); pdf.image(temp_img_file, x=10, y=10, w=190)
        pdf_buffer = io.BytesIO(); pdf.output(pdf_buffer); pdf_buffer.seek(0)
        await update.message.reply_document(document=pdf_buffer, filename="created_document.pdf", caption="✅ Here is your generated PDF file.")
        await msg.delete()
    except Exception as e: logger.error(f"PDF creation error: {e}"); await msg.edit_text("❌ An error occurred.")
    finally: session['pdf_images'].clear(); await start_command_handler(update, context)

async def cancelpdf_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    get_user_session(update.effective_user.id)['pdf_images'].clear()
    await update.message.reply_text("PDF creation cancelled.", parse_mode=ParseMode.MARKDOWN)
    await start_command_handler(update, context)

# =====================================
# AI FEATURES
# =====================================
async def ai_utility_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id; session = get_user_session(user_id)
    utility_mode = session.get('ai_utility_mode')
    prompt_text = update.message.text

    if not utility_mode: await update.message.reply_text("Invalid state. Please use /start."); return
    
    system_instructions = {
        'summarize': "You are a text summarization expert. Take the following text and provide a concise summary.",
        'email': "You are an email writing assistant. Based on the user's prompt, write a clear, professional email.",
        'code': "You are an expert programmer. Analyze the user's question or code and provide a helpful explanation or solution."
    }
    
    full_prompt = f"{system_instructions[utility_mode]}\n\nUser's request: \"{prompt_text}\""
    msg = await update.message.reply_text(f"🤖 Processing your request with AI...", parse_mode=ParseMode.MARKDOWN)
    
    try:
        response = await gemini_model.generate_content_async(full_prompt, safety_settings=SAFETY_SETTINGS)
        await msg.delete()
        for chunk in split_long_message(response.text):
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
    except google_exceptions.GoogleAPICallError as e:
        logger.error(f"Gemini API Error in utility '{utility_mode}': {e}")
        await msg.edit_text("❌ The AI service returned an API error. It might be temporarily unavailable.")
    except Exception as e:
        logger.error(f"AI utility error in '{utility_mode}': {e}", exc_info=True)
        await msg.edit_text("❌ An unexpected error occurred with the AI service.")
    finally:
        set_user_mode(user_id, 'menu') # Exit utility mode after use
        await start_command_handler(update, context)

async def clear_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if get_user_mode(update.effective_user.id) == 'chat':
        get_user_session(update.effective_user.id)['history'].clear()
        await update.message.reply_text("AI conversation history cleared.")
    else:
        await update.message.reply_text("This command is only active in *AI Chat* mode.", parse_mode=ParseMode.MARKDOWN)

async def gemini_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id; prompt = update.message.text; session = get_user_session(user_id)
    msg = await update.message.reply_text("🤔 Thinking...", parse_mode=ParseMode.MARKDOWN)
    try:
        chat = gemini_model.start_chat(history=session['history'])
        response = await chat.send_message_async(prompt, safety_settings=SAFETY_SETTINGS)
        if not response.text: await msg.edit_text("The AI returned an empty response, possibly due to safety filters."); return
        session['history'].extend([{"role": "user", "parts": [prompt]}, {"role": "model", "parts": [response.text]}])
        if len(session['history']) > 20: session['history'] = session['history'][-20:]
        await msg.delete()
        for chunk in split_long_message(response.text): await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
    except google_exceptions.GoogleAPICallError as e:
        logger.error(f"Gemini API Chat Error: {e}"); await msg.edit_text("❌ The AI service returned an API error.")
    except Exception as e:
        logger.error(f"Gemini chat error: {e}", exc_info=True); await msg.edit_text("❌ Sorry, I couldn't connect to the AI service.")

async def photo_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id; mode = get_user_mode(user_id); session = get_user_session(user_id)
    
    if mode == 'pdf_creation':
        try:
            photo_file = await update.message.photo[-1].get_file()
            photo_bytes = await photo_file.download_as_bytearray()
            session['pdf_images'].append(bytes(photo_bytes))
            await update.message.reply_text(f"✅ Image added ({len(session['pdf_images'])} total). Send more or use `/createpdf`.", parse_mode=ParseMode.MARKDOWN)
        except Exception as e: logger.error(f"PDF image add error: {e}"); await update.message.reply_text("❌ Couldn't add that image.")
        return
    
    if mode != 'image_analysis': await update.message.reply_text("Please select a mode from the menu first."); return

    msg = await update.message.reply_text("🔎 Analyzing image...", parse_mode=ParseMode.MARKDOWN)
    try:
        photo = update.message.photo[-1]
        if photo.file_size > 10 * 1024 * 1024: await msg.edit_text("❌ Image too large (max 10MB)."); return
        photo_bytes = await (await photo.get_file()).download_as_bytearray()
        img = Image.open(io.BytesIO(photo_bytes))
        
        response = await gemini_model.generate_content_async(
            ["Analyze this image and identify potential problems. If none, just describe it.", img], safety_settings=SAFETY_SETTINGS
        )
        session['last_analysis'] = response.text
        keyboard = [[InlineKeyboardButton("Yes, provide a solution", callback_data='provide_solution')]]
        await msg.delete()
        await update.message.reply_text(f"📊 *Initial Analysis:*\n\n{response.text}\n\nWant me to suggest a solution?", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    except google_exceptions.GoogleAPICallError as e:
        logger.error(f"Gemini Vision API Error: {e}"); await msg.edit_text("❌ The AI service returned an API error for image analysis.")
    except Exception as e: logger.error(f"Image analysis error: {e}", exc_info=True); await msg.edit_text("❌ Error processing image.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query; await query.answer(); user_id = query.from_user.id
    data = query.data
    
    # AI Utilities Button Handler
    ai_utilities = ['summarize', 'email', 'code']
    if data in ai_utilities:
        set_user_mode(user_id, 'ai_utility', ai_utility=data)
        utility_name = data.replace('_', ' ').title()
        await query.edit_message_text(f"🤖 *{utility_name} Mode*\n\nPlease send me the text or prompt you want me to work on.", parse_mode=ParseMode.MARKDOWN)
        return

    # Solution Button Handler
    if data == 'provide_solution':
        session = get_user_session(user_id); last_analysis = session.get('last_analysis')
        if not last_analysis: await query.edit_message_text("Sorry, analysis expired. Please send the image again."); return
        await query.edit_message_text(f"📊 *Initial Analysis:*\n\n{last_analysis}\n\n🧠 *Generating solution...*", parse_mode=ParseMode.MARKDOWN)
        try:
            prompt = f"Based on this analysis, provide a step-by-step solution:\n\n{last_analysis}"
            response = await gemini_model.generate_content_async(prompt, safety_settings=SAFETY_SETTINGS)
            await query.message.reply_text("💡 *Suggested Solution*:", parse_mode=ParseMode.MARKDOWN)
            for chunk in split_long_message(response.text): await query.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
        except Exception as e: logger.error(f"Solution gen error: {e}"); await query.message.reply_text("❌ Error generating solution.")

# =====================================
# MAIN MESSAGE ROUTER
# =====================================
async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id; text = update.message.text; session = get_user_session(user_id)
    mode = session.get('mode')

    # Handle messages for active interactive modes first
    if mode == 'chat': await gemini_chat_handler(update, context); return
    if mode == 'ai_utility': await ai_utility_handler(update, context); return
    if mode in ['image_analysis', 'pdf_creation']:
        await update.message.reply_text("Please send an image, not text. Use `/menu` to return.", parse_mode=ParseMode.MARKDOWN); return

    # Map menu buttons to functions or info messages
    menu_actions = {
        "🔓 Instagram": "🔓 *Instagram Reset*\nUse `/rst <user>` or `/bulk <users...>`.",
        "🔑 Gen Password": "🔑 *Password Generator*\nUse `/genpass <length>`.",
        "🔗 URL Shortener": "🔗 *URL Shortener*\nUse `/shorten <url>`.",
        "🔳 QR Code": "🔳 *QR Code*\nUse `/qr <text>`.",
        "🌤️ Weather": "🌤️ *Weather Forecast*\nUse `/weather <city>`.",
        "❓ Help": help_command_handler,
    }
    
    if text in menu_actions:
        action = menu_actions[text]
        if callable(action): await action(update, context)
        else: await update.message.reply_text(f"{action}\n\n*Dev: Aadi (@aadi_io)*", parse_mode=ParseMode.MARKDOWN)
    elif "AI Chat" in text:
        set_user_mode(user_id, 'chat')
        await update.message.reply_text("💬 *AI Chat Mode*\nSend any message to start. Use `/clear` to reset or `/menu` to exit.\n\n*Dev: Aadi (@aadi_io)*", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
    elif "Image Analysis" in text:
        set_user_mode(user_id, 'image_analysis')
        await update.message.reply_text("📷 *Image Analysis Mode*\nSend me an image to analyze. Use `/menu` to exit.\n\n*Dev: Aadi (@aadi_io)*", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
    elif "Image to PDF" in text:
        set_user_mode(user_id, 'pdf_creation')
        await update.message.reply_text("📄 *PDF Creator Mode*\nSend me your images one by one. When done, use `/createpdf` to generate or `/cancelpdf` to quit.\n\n*Dev: Aadi (@aadi_io)*", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardRemove())
    elif "AI Utilities" in text:
        keyboard = [
            [InlineKeyboardButton("📝 Summarize Text", callback_data='summarize')],
            [InlineKeyboardButton("✉️ Write Email", callback_data='email')],
            [InlineKeyboardButton("💻 Code Helper", callback_data='code')]
        ]
        await update.message.reply_text("🤖 *AI Utilities*\nSelect a tool to use:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("Please select an option using the menu buttons, or type /start.")

# =====================================
# FASTAPI APP & BOT INITIALIZATION
# =====================================
def register_handlers(app: Application):
    """Registers all command, message, and callback handlers."""
    app.add_handler(CommandHandler("start", start_command_handler))
    app.add_handler(CommandHandler("menu", start_command_handler))
    app.add_handler(CommandHandler("help", help_command_handler))
    app.add_handler(CommandHandler("rst", rst_command_handler))
    app.add_handler(CommandHandler("bulk", bulk_command_handler))
    app.add_handler(CommandHandler("shorten", shorten_command_handler))
    app.add_handler(CommandHandler("qr", qr_command_handler))
    app.add_handler(CommandHandler("clear", clear_command_handler))
    app.add_handler(CommandHandler("genpass", genpass_command_handler))
    app.add_handler(CommandHandler("weather", weather_command_handler))
    app.add_handler(CommandHandler("createpdf", createpdf_command_handler))
    app.add_handler(CommandHandler("cancelpdf", cancelpdf_command_handler))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_message_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_error_handler(logging.error)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app; logger.info("🚀 Starting bot initialization...")
    telegram_app = Application.builder().token(BOT_TOKEN).build()
    register_handlers(telegram_app)
    await telegram_app.initialize()
    if WEBHOOK_URL:
        await telegram_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}")
        logger.info(f"✅ Webhook set to {WEBHOOK_URL}")
    yield
    logger.info("👋 Shutting down bot..."); await telegram_app.stop(); await telegram_app.shutdown()

app = FastAPI(lifespan=lifespan)
@app.get("/")
async def health_check(): return {"status": "ok", "bot_initialized": telegram_app is not None}
@app.post("/webhook/{token}")
async def process_webhook(token: str, request: Request):
    if token != BOT_TOKEN: raise HTTPException(status_code=403, detail="Invalid token")
    if not telegram_app: raise HTTPException(status_code=503, detail="Bot not initialized")
    try:
        data = await request.json(); update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update); return {"status": "ok"}
    except Exception as e: logger.error(f"Error processing webhook update: {e}", exc_info=True); return {"status": "error"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000)); logger.info(f"🚀 Starting FastAPI server on http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)

