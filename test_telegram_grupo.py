"""
🧪 Telegram Group Test
Quickly test if your bot has permissions to send messages to the configured group.
"""

import os
import asyncio
import aiohttp
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
try:
    TELEGRAM_CHAT_ID = int(os.getenv('TELEGRAM_CHAT_ID'))
except:
    TELEGRAM_CHAT_ID = None

async def test_telegram():
    print("🧪 Starting Telegram Test...")
    print("-" * 50)
    
    if not TELEGRAM_BOT_TOKEN:
        print("❌ Error: TELEGRAM_BOT_TOKEN missing")
        return
        
    if not TELEGRAM_CHAT_ID:
        print("❌ Error: TELEGRAM_CHAT_ID missing or invalid")
        return

    print(f"🤖 Bot Token: {TELEGRAM_BOT_TOKEN[:10]}...{TELEGRAM_BOT_TOKEN[-5:]}")
    print(f"🆔 Chat ID: {TELEGRAM_CHAT_ID}")
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    timestamp = datetime.now().strftime('%H:%M:%S')
    message = f"""
✅ <b>CZ_SNIPE BOT - Connection Test</b>
🚀 Status: online
⏱️ Time: {timestamp}

If you see this message, the bot is correctly configured!
"""

    data = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as response:
                result = await response.json()
                
                if response.status == 200 and result.get('ok'):
                    print("-" * 50)
                    print("✅ SUCCESS! Message sent correctly.")
                    print("📱 Check your Telegram group.")
                else:
                    print("-" * 50)
                    print("❌ FAILED to send message.")
                    print(f"📝 Response: {result.get('description', 'Unknown error')}")
                    
                    if not result.get('ok'):
                        print("\n💡 Common fixes:")
                        print("1. Make sure the bot is an ADMIN in the group")
                        print("2. Verify the TELEGRAM_CHAT_ID is correct")
                        print("3. Check if the bot is blocked")
    except Exception as e:
        print(f"❌ Error during connection: {e}")

if __name__ == "__main__":
    asyncio.run(test_telegram())
