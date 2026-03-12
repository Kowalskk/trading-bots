"""
🛠️ Telegram Chat ID Helper
Run this to get the chat IDs where your bot is present.
"""

import os
import asyncio
import aiohttp
from dotenv import load_dotenv

load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

async def get_updates():
    if not TELEGRAM_BOT_TOKEN:
        print("❌ Error: TELEGRAM_BOT_TOKEN not found in .env file")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    
    print("🔍 Looking for updates...")
    print("💡 Tip: Send a message to your bot or the group first!")
    print("-" * 50)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if not data.get('result'):
                        print("ℹ️ No messages found yet.")
                        print("👉 Send a message to the bot and run this script again.")
                        return

                    found_chats = {}
                    
                    for update in data['result']:
                        if 'message' in update:
                            chat = update['message']['chat']
                            chat_id = chat['id']
                            chat_type = chat['type']
                            chat_title = chat.get('title', 'Private Chat')
                            username = chat.get('username', 'N/A')
                            
                            key = f"{chat_id}_{chat_type}"
                            if key not in found_chats:
                                found_chats[key] = {
                                    'id': chat_id,
                                    'type': chat_type,
                                    'title': chat_title,
                                    'username': username
                                }

                    print(f"✅ Found {len(found_chats)} active chats:")
                    print("-" * 50)
                    
                    for chat in found_chats.values():
                        print(f"📌 Chat Name: {chat['title']}")
                        print(f"🆔 Chat ID: {chat['id']}")
                        print(f"👤 Type: {chat['type']}")
                        if chat['username'] != 'N/A':
                            print(f"🔗 Username: @{chat['username']}")
                        print("-" * 50)
                        
                        print(f"\n🚀 To use this chat, add this to your .env:")
                        print(f"TELEGRAM_CHAT_ID={chat['id']}\n")
                else:
                    print(f"❌ Error API: Status {response.status}")
                    print(await response.text())
    except Exception as e:
        print(f"❌ Connection error: {e}")

if __name__ == "__main__":
    asyncio.run(get_updates())
