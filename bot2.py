"""
🚀 CZ_SNIPE BOT - FAST AND SECURE
Maximum speed with excessive consumption protection
"""

import os
import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
import re
import aiohttp
from dotenv import load_dotenv

load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = int(os.getenv('TELEGRAM_CHAT_ID'))
BITQUERY_API_KEY = os.getenv('BITQUERY_API_KEY')
TWITTER_API_KEY = os.getenv('TWITTER_API_KEY')

CONFIG = {
    'twitter_accounts': ['cz_binance', 'heyibinance'],
    'correlation_window': 600,
    'min_confidence': 60,
    
    # FAST SPEED
    'twitter_check_interval': 15,  # 15 seconds (good speed)
    'fourmeme_check_interval': 10,  # 10 seconds (very fast)
    
    # SECURITY PROTECTIONS
    'max_twitter_calls_per_hour': 300,  # Limit: 300 calls/hour (7,200/day)
    'max_twitter_calls_per_day': 10000,  # Limit: 10K calls/day
    'emergency_stop_on_402': True,  # Stop automatically if credits run out
}

STATS = {
    'tweets_detected': 0,
    'tokens_found': 0,
    'correlations_found': 0,
    'api_calls_twitter': 0,
    'api_calls_twitter_last_hour': [],  # Last hour call timestamps
    'api_calls_twitter_today': 0,
    'api_calls_bitquery': 0,
    'started_at': datetime.now(),
    'last_reset': datetime.now()
}

def log_debug(emoji, message):
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {emoji} {message}")

async def send_telegram_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=10)) as response:
                return response.status == 200
    except:
        return False

def check_rate_limit():
    """Verify if we can make more calls"""
    now = datetime.now()
    
    # Clear calls older than 1 hour
    hour_ago = now - timedelta(hours=1)
    STATS['api_calls_twitter_last_hour'] = [
        t for t in STATS['api_calls_twitter_last_hour'] 
        if t > hour_ago
    ]
    
    # Daily reset
    if now.date() > STATS['last_reset'].date():
        STATS['api_calls_twitter_today'] = 0
        STATS['last_reset'] = now
        log_debug("🔄", "Daily counter reset")
    
    # Check limits
    calls_last_hour = len(STATS['api_calls_twitter_last_hour'])
    
    if calls_last_hour >= CONFIG['max_twitter_calls_per_hour']:
        log_debug("⚠️", f"HOURLY LIMIT reached ({calls_last_hour}/{CONFIG['max_twitter_calls_per_hour']})")
        return False, "hourly"
    
    if STATS['api_calls_twitter_today'] >= CONFIG['max_twitter_calls_per_day']:
        log_debug("⚠️", f"DAILY LIMIT reached ({STATS['api_calls_twitter_today']}/{CONFIG['max_twitter_calls_per_day']})")
        return False, "daily"
    
    return True, None

def record_api_call():
    """Record an API call"""
    now = datetime.now()
    STATS['api_calls_twitter'] += 1
    STATS['api_calls_twitter_today'] += 1
    STATS['api_calls_twitter_last_hour'].append(now)

class TweetCache:
    def __init__(self):
        self.tweets = []
        self.max_age = CONFIG['correlation_window']
        self.seen_ids = set()
    
    def add(self, text, username, timestamp):
        STATS['tweets_detected'] += 1
        tweet_id = f"{username}_{timestamp}_{text[:50]}"
        
        if tweet_id in self.seen_ids:
            return
        
        self.seen_ids.add(tweet_id)
        keywords = self._extract_keywords(text)
        
        self.tweets.append({
            'text': text,
            'username': username,
            'timestamp': timestamp,
            'keywords': keywords
        })
        
        log_debug("📝", f"@{username}: {text[:60]}...")
        self._cleanup()
    
    def _extract_keywords(self, text):
        text_lower = text.lower()
        words = re.findall(r'\b[a-z]{3,}\b', text_lower)
        stopwords = {'the', 'and', 'for', 'with', 'this', 'that', 'are', 'but', 'not', 'you', 'all', 'can', 'has', 'was', 'were', 'been', 'have', 'from', 'they', 'will'}
        keywords = [w for w in words if w not in stopwords]
        return set(keywords)
    
    def _cleanup(self):
        cutoff = time.time() - self.max_age
        self.tweets = [t for t in self.tweets if t['timestamp'] > cutoff]
    
    def search(self, token_name, token_symbol):
        self._cleanup()
        
        if not self.tweets:
            return None, 0
        
        token_name_lower = token_name.lower()
        token_symbol_lower = token_symbol.lower()
        best_match = None
        best_score = 0
        
        for tweet in self.tweets:
            score = 0
            tweet_text_lower = tweet['text'].lower()
            
            if token_name_lower in tweet_text_lower or token_symbol_lower in tweet_text_lower:
                score += 60
            
            token_keywords = self._extract_keywords(token_name + " " + token_symbol)
            matching_keywords = token_keywords & tweet['keywords']
            score += len(matching_keywords) * 15
            
            similarity = SequenceMatcher(None, token_name_lower, tweet_text_lower).ratio()
            if similarity > 0.3:
                score += similarity * 25
            
            crypto_words = {'moon', 'pump', 'gem', 'launch', 'bullish', 'meme', 'token', 'rocket', 'binance'}
            if any(word in tweet_text_lower for word in crypto_words):
                score += 5
            
            age = time.time() - tweet['timestamp']
            if age < 300:
                score += 10
            
            if score > best_score:
                best_score = score
                best_match = tweet
        
        return best_match, min(best_score, 100)
    
class TwitterMonitor:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.twitterapi.io/twitter/user/last_tweets"
        self.last_tweet_ids = {}
        self.check_count = 0
        self.stopped = False
    
    async def start(self, tweet_cache):
        log_debug("📱", "=== TWITTER MONITOR (FAST AND SECURE) ===")
        log_debug("⏱️", f"Interval: {CONFIG['twitter_check_interval']}s")
        log_debug("🛡️", f"Hourly limit: {CONFIG['max_twitter_calls_per_hour']} calls")
        log_debug("🛡️", f"Daily limit: {CONFIG['max_twitter_calls_per_day']} calls")
        
        if not self.api_key:
            log_debug("⚠️", "API key not configured")
            while True:
                await asyncio.sleep(60)
            return
        
        log_debug("🔍", "Testing...")
        if not await self._test_api():
            log_debug("❌", "Twitter not available")
            while True:
                await asyncio.sleep(60)
            return
        
        log_debug("✅", "Connected!")
        
        # Initialize
        for account in CONFIG['twitter_accounts']:
            can_call, reason = check_rate_limit()
            if not can_call:
                log_debug("⚠️", f"{reason.capitalize()} limit reached during init")
                break
            await self._initialize_account(account)
        
        log_debug("✅", "Ready! Monitoring...")
        
        # Main Loop
        while True:
            try:
                if self.stopped:
                    log_debug("🛑", "Monitor stopped for safety")
                    await asyncio.sleep(300)  # Wait 5 minutes
                    continue
                
                self.check_count += 1
                
                for account in CONFIG['twitter_accounts']:
                    # Check limit BEFORE each call
                    can_call, reason = check_rate_limit()
                    
                    if not can_call:
                        if reason == "hourly":
                            log_debug("⏸️", f"Hourly limit - Waiting 60s...")
                            await asyncio.sleep(60)
                            continue
                        elif reason == "daily":
                            log_debug("⏸️", "Daily limit - Twitter paused until tomorrow")
                            await asyncio.sleep(3600)  # Wait 1 hour
                            continue
                    
                    await self._check_account(account, tweet_cache)
                
                await asyncio.sleep(CONFIG['twitter_check_interval'])
                
            except Exception as e:
                log_debug("❌", f"Error: {e}")
                await asyncio.sleep(30)
    
    async def _test_api(self):
        try:
            params = {"userName": "elonmusk"}
            headers = {"X-API-Key": self.api_key}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    return response.status == 200
        except:
            return False
    
    async def _initialize_account(self, account):
        try:
            clean_account = account.replace('@', '')
            params = {
                "userName": clean_account,
                "includeReplies": "true",
                "includeRetweets": "true"
            }
            headers = {"X-API-Key": self.api_key}
            
            record_api_call()
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        if isinstance(data, dict) and 'data' in data:
                            tweets = data['data'].get('tweets', [])
                        else:
                            tweets = []
                        
                        if tweets:
                            latest_id = tweets[0].get('id', '0')
                            self.last_tweet_ids[account] = str(latest_id)
                            log_debug("✓", f"@{clean_account}: Initialized")
        except Exception as e:
            log_debug("❌", f"Init: {e}")
    
    async def _check_account(self, account, tweet_cache):
        try:
            clean_account = account.replace('@', '')
            params = {
                "userName": clean_account,
                "includeReplies": "true",
                "includeRetweets": "true"
            }
            headers = {"X-API-Key": self.api_key}
            
            record_api_call()
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if isinstance(data, dict) and 'data' in data:
                            tweets = data['data'].get('tweets', [])
                        else:
                            tweets = []
                        
                        if not tweets:
                            return
                        
                        new_tweets = 0
                        last_id = self.last_tweet_ids.get(account, '0')
                        
                        for tweet in tweets:
                            tweet_id = str(tweet.get('id', ''))
                            text = tweet.get('text', '')
                            
                            if tweet_id > last_id and text:
                                created_at = tweet.get('createdAt', '')
                                
                                try:
                                    if created_at:
                                        try:
                                            ts = datetime.fromisoformat(created_at.replace('Z', '+00:00')).timestamp()
                                        except:
                                            from datetime import datetime as dt
                                            ts = dt.strptime(created_at, '%a %b %d %H:%M:%S %z %Y').timestamp()
                                    else:
                                        ts = time.time()
                                    
                                    tweet_cache.add(text, account, ts)
                                    new_tweets += 1
                                    self.last_tweet_ids[account] = tweet_id
                                    
                                except:
                                    pass
                        
                        if new_tweets > 0:
                            log_debug("🎉", f"{new_tweets} new from @{clean_account}")
                    
                    elif response.status == 402:
                        log_debug("🚨", "ERROR 402 - Out of credits!")
                        if CONFIG['emergency_stop_on_402']:
                            log_debug("🛑", "STOPPING Twitter for safety")
                            self.stopped = True
                            await send_telegram_message("🚨 <b>ALERT</b>\n\nTwitter out of credits - Monitor paused")
        
        except Exception as e:
            pass

class FourMemeMonitor:
    def __init__(self, api_key):
        self.api_key = api_key
        self.endpoint = "https://streaming.bitquery.io/graphql"
        self.check_count = 0
        self.seen_contracts = set()
    
    async def start(self, tweet_cache):
        log_debug("🔥", "=== FOUR.MEME MONITOR (ULTRA FAST) ===")
        log_debug("⏱️", f"Interval: {CONFIG['fourmeme_check_interval']}s")
        await asyncio.sleep(5)
        
        while True:
            try:
                self.check_count += 1
                
                if self.check_count % 6 == 0:
                    log_debug("🔄", f"Four.meme check #{self.check_count}")
                
                await self._poll_new_tokens(tweet_cache)
                await asyncio.sleep(CONFIG['fourmeme_check_interval'])
                
            except Exception as e:
                log_debug("❌", f"Error: {e}")
                await asyncio.sleep(30)
    
    async def _poll_new_tokens(self, tweet_cache):
        try:
            # Only last 3 minutes (very fresh)
            since_time = (datetime.now(timezone.utc) - timedelta(minutes=3)).strftime('%Y-%m-%dT%H:%M:%SZ')
            
            query = """
            query ($since: DateTime!) {
              EVM(network: bsc, dataset: combined) {
                DEXTrades(
                  where: {
                    Trade: {
                      Dex: {ProtocolName: {is: "fourmeme_v1"}}
                    }
                    Block: {Time: {since: $since}}
                  }
                  limit: {count: 10}
                  orderBy: {descending: Block_Time}
                ) {
                  Block {
                    Time
                  }
                  Trade {
                    Buy {
                      Currency {
                        Name
                        Symbol
                        SmartContract
                      }
                    }
                  }
                }
              }
            }
            """
            
            variables = {"since": since_time}
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            STATS['api_calls_bitquery'] += 1
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.endpoint,
                    json={"query": query, "variables": variables},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        if 'errors' in data:
                            return
                        
                        trades = data.get('data', {}).get('EVM', {}).get('DEXTrades', [])
                        
                        for trade_data in trades:
                            buy = trade_data.get('Trade', {}).get('Buy', {}).get('Currency', {})
                            block = trade_data.get('Block', {})
                            
                            name = buy.get('Name', 'Unknown')
                            symbol = buy.get('Symbol', 'UNKNOWN')
                            contract = buy.get('SmartContract', '')
                            timestamp = block.get('Time', '')
                            
                            if not contract or contract in self.seen_contracts:
                                continue
                            
                            self.seen_contracts.add(contract)
                            STATS['tokens_found'] += 1
                            
                            log_debug("🪙", f"{name} (${symbol})")
                            
                            match, confidence = tweet_cache.search(name, symbol)
                            
                            if match and confidence >= CONFIG['min_confidence']:
                                STATS['correlations_found'] += 1
                                log_debug("🎉", f"CORRELATION {confidence}%!")
                                await self._send_alert(name, symbol, contract, timestamp, match, confidence)
                            elif confidence > 35:
                                log_debug("⚪", f"{confidence}%")
        
        except:
            pass
    
    async def _send_alert(self, name, symbol, contract, timestamp, match, confidence):
        try:
            tweet_time = datetime.fromtimestamp(match['timestamp'])
            token_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            time_diff = (token_time - tweet_time).total_seconds()
            
            minutes = int(time_diff // 60)
            seconds = int(time_diff % 60)
            
            message = f"""
🚨 <b>OPPORTUNITY DETECTED</b> 🚨

📱 <b>Tweet:</b> @{match['username']}
💬 "{match['text'][:100]}..."

🪙 <b>Token:</b> {name}
💲 <b>Symbol:</b> ${symbol}
📜 <b>Contract:</b> <code>{contract}</code>
⏱️ <b>Time:</b> {minutes}m {seconds}s later

🔗 <b>Four.meme:</b> https://four.meme/token/{contract}
📊 <b>PancakeSwap:</b> https://pancakeswap.finance/swap?outputCurrency={contract}
📈 <b>DexScreener:</b> https://dexscreener.com/bsc/{contract}

⚡ <b>Confidence:</b> {confidence}%
"""
            
            await send_telegram_message(message)
            log_debug("✅", "Alert sent!")
        
        except:
            pass

async def stats_reporter():
    """Report every 5 minutes"""
    await asyncio.sleep(300)
    
    while True:
        try:
            calls_last_hour = len(STATS['api_calls_twitter_last_hour'])
            
            log_debug("📊", "=== STATS ===")
            log_debug("📱", f"Twitter: {STATS['api_calls_twitter_today']}/day, {calls_last_hour}/hour")
            log_debug("🔥", f"Bitquery: {STATS['api_calls_bitquery']} calls")
            log_debug("🪙", f"Tokens: {STATS['tokens_found']}")
            log_debug("✨", f"Correlations: {STATS['correlations_found']}")
            
            await asyncio.sleep(300)
        except:
            await asyncio.sleep(300)

async def main():
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║      🚀 CZ_SNIPE BOT 🚀                                  ║
    ║      ⚡ FAST AND SECURE                                   ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    log_debug("🔧", "=== CONFIGURATION ===")
    log_debug("⏱️", f"Twitter: every {CONFIG['twitter_check_interval']}s")
    log_debug("⏱️", f"Four.meme: every {CONFIG['fourmeme_check_interval']}s")
    
    # Calculate consumption
    calls_per_hour = (3600 / CONFIG['twitter_check_interval']) * len(CONFIG['twitter_accounts'])
    calls_per_day = min(calls_per_hour * 24, CONFIG['max_twitter_calls_per_day'])
    
    log_debug("💰", f"Max consumption: {calls_per_day:.0f} calls/day")
    log_debug("🛡️", f"Active protection: Limits {CONFIG['max_twitter_calls_per_hour']}/h, {CONFIG['max_twitter_calls_per_day']}/day")
    print()
    
    await send_telegram_message(f"🤖 <b>Bot started</b>\n\n⚡ Fast mode\n🛡️ With protection\n💰 Max: {int(calls_per_day)} calls/day")
    
    tweet_cache = TweetCache()
    twitter_monitor = TwitterMonitor(TWITTER_API_KEY)
    fourmeme_monitor = FourMemeMonitor(BITQUERY_API_KEY)
    
    await asyncio.gather(
        twitter_monitor.start(tweet_cache),
        fourmeme_monitor.start(tweet_cache),
        stats_reporter()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n")
        log_debug("👋", "Bot stopped")
        log_debug("📊", f"Twitter: {STATS['api_calls_twitter']} calls")
        log_debug("📊", f"Tokens: {STATS['tokens_found']}")
        log_debug("📊", f"Correlations: {STATS['correlations_found']}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n")
        log_debug("👋", "Bot stopped")
        log_debug("📊", f"Twitter: {STATS['api_calls_twitter']} calls")
        log_debug("📊", f"Tokens: {STATS['tokens_found']}")
        log_debug("📊", f"Correlations: {STATS['correlations_found']}")
