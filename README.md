# 🚀 CZ_SNIPE BOT

A high-performance trading bot designed to monitor **Twitter** accounts (like @cz_binance) and correlate tweets with new token launches on **Four.Meme** (Binance Smart Chain).

## 🌟 Key Features

- **Extreme Speed**: Real-time monitoring of Four.Meme token launches using Bitquery GraphQL.
- **Twitter Correlation**: Automatically detects when a token name or symbol matches a recent tweet from monitored accounts.
- **Smart Filtering**: Built-in confidence scoring system to reduce false positives.
- **Optimized Logic**: Configurable time windows for both startup and ongoing correlation.
- **Security & Efficiency**: Rate limiting for Twitter API calls to prevent exhaustion and unnecessary costs.
- **Telegram Notifications**: Real-time alerts sent directly to your Telegram group with direct links to Four.Meme, PancakeSwap, and DexScreener.

## 📁 Repository Structure

- `bot.py`: Main trading bot with optimized correlation logic.
- `bot2.py`: Faster and more secure alternative implementation with enhanced consumption protection.
- `get_chat_id.py`: Helper script to retrieve your Telegram group's Chat ID.
- `test_telegram_grupo.py`: Connectivity test to ensure Telegram notifications are working correctly.

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.8+
- [Twitter API IO Key](https://twitterapi.io/)
- [Bitquery API Key](https://bitquery.io/)
- [Telegram Bot Token](https://tme.bot/botfather)

### 2. Installation
```bash
pip install aiohttp python-dotenv
```

### 3. Configuration
Create a `.env` file in the root directory:
```env
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
BITQUERY_API_KEY=your_key_here
TWITTER_API_KEY=your_key_here
```

### 4. Running the Bot
```bash
python bot.py
# OR for the faster version
python bot2.py
```

## 📊 Monitoring
The bot will report stats every 5 minutes including:
- API call counts (to manage your limits)
- Tokens detected
- Tweets analyzed
- Successful correlations found

## 🛡️ Protections
- **Emergency Stop**: Automatically stops Twitter polling if API credits run out (Error 402).
- **Rate Limiting**: Configurable maximum calls per hour and per day.

---
*Created for fast sniping on BSC.*
