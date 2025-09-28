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

# Credit attribution
CREDIT = "\n\n💡 Powered by @AADI_IO"

# Configure Gemini AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

class TelegramBot:
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
    
    def send_message(self, chat_id, text, parse_mode=None, reply_markup=None):
        """Send message to Telegram chat"""
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
            response = requests.post(url, json=data)
            return response.json()
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return None
    
    def get_file_url(self, file_id):
        """Get file URL from Telegram"""
        url = f"{self.base_url}/getFile"
        data = {'file_id': file_id}
        
        try:
            response = requests.post(url, json=data)
            result = response.json()
            
            if result.get('ok'):
                file_path
