import os
import logging
import base64
import io
import requests
from flask import Flask, request, jsonify
import google.generativeai as genai
from PIL import Image
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Configuration - Set these as environment variables in Render
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AIzaSyBKRhZqDPP5BM8_1fP0vsUPQgEqw4Mkh6o')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # Your Render app URL
PORT = int(os.getenv('PORT', 5000))

# Credit attribution (only AADI)
CREDIT = "\n\n💡 By AADI"

# Configure Gemini AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

class TelegramBot:
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        if self.bot_token:
            self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        else:
            logger.error("TELEGRAM_BOT_TOKEN not found!")
    
    def send_message(self, chat_id, text, parse_mode=None, reply_markup=None):
        """Send message to Telegram chat"""
        if not self.bot_token:
            logger.error("Bot token not configured")
            return None
            
        url = f"{self.base_url}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': text
        }
        
        if parse_mode:
            data['parse_mode'] = parse_mode
        
        if reply_markup:
            data['reply_markup'] = json.dumps(reply_markup)
        
        try:
            response = requests.post(url, json=data, timeout=30)
            return response.json()
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return None
    
    def get_file_url(self, file_id):
        """Get file URL from Telegram"""
        if not self.bot_token:
            return None
            
        url = f"{self.base_url}/getFile"
        data = {'file_id': file_id}
        
        try:
            response = requests.post(url, json=data, timeout=30)
            result = response.json()
            
            if result.get('ok'):
                file_path = result['result']['file_path']
                return f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
            return None
        except Exception as e:
            logger.error(f"Error getting file URL: {e}")
            return None
    
    def download_image(self, file_id):
        """Download image and convert to base64"""
        file_url = self.get_file_url(file_id)
        if not file_url:
            return None
        
        try:
            response = requests.get(file_url, timeout=30)
            if response.status_code == 200:
                return base64.b64encode(response.content).decode('utf-8')
            return None
        except Exception as e:
            logger.error(f"Error downloading image: {e}")
            return None
    
    def set_webhook(self, webhook_url):
        """Set webhook URL"""
        if not self.bot_token:
            return None
            
        url = f"{self.base_url}/setWebhook"
        data = {'url': webhook_url}
        
        try:
            response = requests.post(url, json=data, timeout=30)
            return response.json()
        except Exception as e:
            logger.error(f"Error setting webhook: {e}")
            return None

# Initialize bot
bot = TelegramBot()

class AIAssistant:
    def __init__(self):
        self.model = model
    
    def chat_response(self, message):
        """Generate chat response using Gemini"""
        try:
            prompt = f"You are a helpful AI assistant. Answer the following question naturally and helpfully: {message}"
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Error generating chat response: {e}")
            return "Sorry, I couldn't process your message. Please try again."
    
    def analyze_image(self, image_base64, task="general"):
        """Analyze image using Gemini Vision"""
        try:
            # Convert base64 to PIL Image
            image_data = base64.b64decode(image_base64)
            image = Image.open(io.BytesIO(image_data))
            
            if task == "ocr":
                prompt = "Extract all text from this image. Format it clearly and preserve the structure. If there's no text, say 'No text found in the image.'"
            elif task == "screenshot":
                prompt = "Analyze this screenshot in detail. Describe what you see, identify the application/website, explain the content, and provide any relevant insights or observations. Be thorough and helpful."
            else:
                prompt = "Describe this image in detail. What do you see? Provide a comprehensive analysis."
            
            response = self.model.generate_content([prompt, image])
            return response.text
        except Exception as e:
            logger.error(f"Error analyzing image: {e}")
            return "Sorry, I couldn't analyze the image. Please try again."

# Initialize AI assistant
ai = AIAssistant()

def handle_start_command(chat_id):
    """Handle /start command"""
    welcome_message = f"""🤖 *Welcome to AI Assistant Bot!*

🔥 *Features Available:*
• 📸 *Screenshot Scanner* - Send any screenshot for analysis
• 🤖 *AI Chatbot* - Ask me anything, I'll help you
• 📝 *Image to Text (OCR)* - Extract text from any image
• ⚡ *Powered by Google Gemini AI*

🚀 *How to use:*
• Send me any image for OCR or analysis
• Just type your question for AI chat
• Use /help for more commands

Ready to assist you! What can I help you with today?{CREDIT}"""
    
    bot.send_message(chat_id, welcome_message, parse_mode='Markdown')

def handle_help_command(chat_id):
    """Handle /help command"""
    help_message = f"""📋 *Available Commands:*

/start - Welcome message and bot introduction
/help - Show this help message
/features - List all available features
/about - About this bot

🔧 *How to use features:*
• *Screenshot Scanner:* Send any screenshot
• *AI Chat:* Just type your question
• *OCR:* Send any image with text

💡 *Tips:*
• Images work best in good lighting
• For OCR, ensure text is clear and readable
• Ask me anything - I'm powered by advanced AI!{CREDIT}"""
    
    bot.send_message(chat_id, help_message, parse_mode='Markdown')

def handle_features_command(chat_id):
    """Handle /features command"""
    keyboard = {
        'inline_keyboard': [
            [
                {'text': '📸 Screenshot Scanner', 'callback_data': 'feature_screenshot'},
                {'text': '🤖 AI Chatbot', 'callback_data': 'feature_chatbot'}
            ],
            [
                {'text': '📝 OCR (Image to Text)', 'callback_data': 'feature_ocr'},
                {'text': 'ℹ️ About Bot', 'callback_data': 'feature_about'}
            ]
        ]
    }
    
    bot.send_message(chat_id, "🚀 Choose a feature to learn more:", reply_markup=keyboard)

def handle_about_command(chat_id):
    """Handle /about command"""
    about_message = f"""🤖 *AI Assistant Bot*

*Version:* 1.0
*Powered by:* Google Gemini AI
*Hosted on:* Render
*Developer:* AADI

*Capabilities:*
• Advanced image analysis
• OCR text extraction
• Natural language conversation
• Real-time processing

*Privacy:* Your messages are processed securely and not stored.{CREDIT}"""
    
    bot.send_message(chat_id, about_message, parse_mode='Markdown')

def handle_image_message(message, chat_id):
    """Handle image messages"""
    bot.send_message(chat_id, "🔍 Processing your image... Please wait.")
    
    try:
        file_id = None
        caption = message.get('caption', '')
        
        # Get file ID from photo or document
        if message.get('photo'):
            file_id = message['photo'][-1]['file_id']  # Get highest resolution
        elif message.get('document') and message['document'].get('mime_type', '').startswith('image/'):
            file_id = message['document']['file_id']
        else:
            bot.send_message(chat_id, f"Please send a valid image file.{CREDIT}")
            return
        
        # Download image
        image_base64 = bot.download_image(file_id)
        if not image_base64:
            bot.send_message(chat_id, f"Sorry, I couldn't download the image. Please try again.{CREDIT}")
            return
        
        # Determine task based on caption or show options
        if 'ocr' in caption.lower() or 'text' in caption.lower():
            result = ai.analyze_image(image_base64, task="ocr")
            response = f"📝 *Text Extracted:*\n\n{result}{CREDIT}"
            bot.send_message(chat_id, response, parse_mode='Markdown')
        elif 'scan' in caption.lower() or 'analyze' in caption.lower():
            result = ai.analyze_image(image_base64, task="screenshot")
            response = f"📸 *Screenshot Analysis:*\n\n{result}{CREDIT}"
            bot.send_message(chat_id, response, parse_mode='Markdown')
        else:
            # Show options
            keyboard = {
                'inline_keyboard': [
                    [
                        {'text': '📝 Extract Text (OCR)', 'callback_data': f'ocr_{file_id}'},
                        {'text': '📸 Analyze Screenshot', 'callback_data': f'analyze_{file_id}'}
                    ],
                    [
                        {'text': '🔍 General Image Analysis', 'callback_data': f'general_{file_id}'}
                    ]
                ]
            }
            bot.send_message(chat_id, "What would you like me to do with this image?", reply_markup=keyboard)
    
    except Exception as e:
        logger.error(f"Error handling image: {e}")
        bot.send_message(chat_id, f"Sorry, I couldn't process the image. Please try again.{CREDIT}")

def handle_text_message(text, chat_id):
    """Handle text messages (chatbot)"""
    bot.send_message(chat_id, "🤖 Thinking...")
    
    try:
        response = ai.chat_response(text)
        bot.send_message(chat_id, f"{response}{CREDIT}")
    except Exception as e:
        logger.error(f"Error in chatbot: {e}")
        bot.send_message(chat_id, f"Sorry, I couldn't process your message. Please try again.{CREDIT}")

def handle_callback_query(callback_query):
    """Handle inline keyboard callbacks"""
    chat_id = callback_query['message']['chat']['id']
    data = callback_query['data']
    
    # Answer callback query
    if TELEGRAM_BOT_TOKEN:
        try:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", 
                         json={'callback_query_id': callback_query['id']}, timeout=10)
        except Exception as e:
            logger.error(f"Error answering callback query: {e}")
    
    if data.startswith('feature_'):
        feature = data.replace('feature_', '')
        
        if feature == 'screenshot':
            response = f"📸 *Screenshot Scanner*\n\nSend me any screenshot and I'll:\n• Analyze the content\n• Identify applications/websites\n• Explain what's happening\n• Provide insights and observations\n\nJust upload your screenshot!{CREDIT}"
        elif feature == 'chatbot':
            response = f"🤖 *AI Chatbot*\n\nI can help you with:\n• Answering questions\n• Explaining concepts\n• Problem-solving\n• Creative tasks\n• General conversation\n\nJust type your question!{CREDIT}"
        elif feature == 'ocr':
            response = f"📝 *OCR (Image to Text)*\n\nI can extract text from:\n• Screenshots\n• Photos of documents\n• Handwritten notes\n• Signs and text in images\n\nSend any image with text!{CREDIT}"
        elif feature == 'about':
            response = f"ℹ️ *About This Bot*\n\nBuilt with:\n• Google Gemini AI\n• Hosted on Render\n• Advanced image processing\n\nCreated by AADI{CREDIT}"
        
        bot.send_message(chat_id, response, parse_mode='Markdown')
    
    elif data.startswith(('ocr_', 'analyze_', 'general_')):
        action, file_id = data.split('_', 1)
        bot.send_message(chat_id, "🔍 Processing your request...")
        
        try:
            image_base64 = bot.download_image(file_id)
            if not image_base64:
                bot.send_message(chat_id, f"Sorry, I couldn't process the image. Please try again.{CREDIT}")
                return
            
            if action == 'ocr':
                result = ai.analyze_image(image_base64, task="ocr")
                response = f"📝 *Text Extracted:*\n\n{result}{CREDIT}"
            elif action == 'analyze':
                result = ai.analyze_image(image_base64, task="screenshot")
                response = f"📸 *Screenshot Analysis:*\n\n{result}{CREDIT}"
            elif action == 'general':
                result = ai.analyze_image(image_base64, task="general")
                response = f"🔍 *Image Analysis:*\n\n{result}{CREDIT}"
            
            bot.send_message(chat_id, response, parse_mode='Markdown')
        
        except Exception as e:
            logger.error(f"Error processing callback: {e}")
            bot.send_message(chat_id, f"Sorry, I couldn't process the image. Please try again.{CREDIT}")

# Flask routes
@app.route('/')
def index():
    return "🤖 Telegram AI Bot is running! Ready to assist users with AI-powered features."

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming Telegram updates"""
    try:
        update = request.get_json()
        logger.info(f"Received update: {update}")
        
        if 'message' in update:
            message = update['message']
            chat_id = message['chat']['id']
            
            # Handle commands
            if message.get('text') and message['text'].startswith('/'):
                command = message['text'].split()[0].lower()
                
                if command == '/start':
                    handle_start_command(chat_id)
                elif command == '/help':
                    handle_help_command(chat_id)
                elif command == '/features':
                    handle_features_command(chat_id)
                elif command == '/about':
                    handle_about_command(chat_id)
                else:
                    bot.send_message(chat_id, f"Unknown command. Use /help to see available commands.{CREDIT}")
            
            # Handle images
            elif message.get('photo') or (message.get('document') and 
                                         message['document'].get('mime_type', '').startswith('image/')):
                handle_image_message(message, chat_id)
            
            # Handle text messages
            elif message.get('text'):
                handle_text_message(message['text'], chat_id)
        
        # Handle callback queries
        elif 'callback_query' in update:
            handle_callback_query(update['callback_query'])
        
        return jsonify({'status': 'ok'})
    
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/setup')
def setup_webhook():
    """Setup webhook - visit this URL after deployment"""
    if not WEBHOOK_URL:
        return jsonify({'error': 'WEBHOOK_URL not set'})
    
    if not TELEGRAM_BOT_TOKEN:
        return jsonify({'error': 'TELEGRAM_BOT_TOKEN not set'})
    
    webhook_url = f"{WEBHOOK_URL}/webhook"
    result = bot.set_webhook(webhook_url)
    
    if result and result.get('ok'):
        return jsonify({
            'status': 'success',
            'message': 'Webhook set successfully!',
            'webhook_url': webhook_url
        })
    else:
        return jsonify({
            'status': 'error',
            'message': 'Failed to set webhook',
            'details': result
        })

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'bot_token_configured': bool(TELEGRAM_BOT_TOKEN),
        'gemini_api_configured': bool(GEMINI_API_KEY),
        'webhook_url_configured': bool(WEBHOOK_URL)
    })

if __name__ == '__main__':
    logger.info("Starting Telegram AI Bot...")
    logger.info(f"Port: {PORT}")
    logger.info(f"Bot token configured: {bool(TELEGRAM_BOT_TOKEN)}")
    logger.info(f"Webhook URL: {WEBHOOK_URL}")
    
    app.run(host='0.0.0.0', port=PORT, debug=False)
