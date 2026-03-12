"""
🚀 CZ_SNIPE BOT - OPTIMIZED LOGIC
PRIORITY: New tokens + New tweets ONLY
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

# Support for multiple chats
# Can be a single ID or several separated by commas
telegram_chat_id_str = os.getenv('TELEGRAM_CHAT_ID', '')
if ',' in telegram_chat_id_str:
    # Multiple IDs
    TELEGRAM_CHAT_IDS = [int(id.strip()) for id in telegram_chat_id_str.split(',')]
else:
    # Single ID
    TELEGRAM_CHAT_IDS = [int(telegram_chat_id_str)] if telegram_chat_id_str else []

BITQUERY_API_KEY = os.getenv('BITQUERY_API_KEY')
TWITTER_API_KEY = os.getenv('TWITTER_API_KEY')

CONFIG = {
    'twitter_accounts': ['cz_binance', 'heyibinance'],
    
    # TIME WINDOWS (OPTIMIZED)
    'startup_window': 180,  # 3 minutes at startup
    'correlation_window': 120,  # Only 2 minutes of correlation (VERY short)
    'max_tweet_age_for_correlation': 120,  # Tweet must be < 2 min when correlating
    
    # SPEED
    'twitter_check_interval': 15,
    'fourmeme_check_interval': 10,
    
    # CORRELATION
    'min_confidence': 60,
    'recency_boost_threshold': 60,  # If tweet is < 1 min, +20 points
    
    # NOTIFICATIONS
    'notify_new_tweets': True,  # Send new tweets to Telegram
    'notify_only_after_init': True,  # Only notify after startup
    
    # PROTECTIONS
    'max_twitter_calls_per_hour': 300,
    'max_twitter_calls_per_day': 10000,
    'emergency_stop_on_402': True,
}

STATS = {
    'tweets_detected': 0,
    'tokens_found': 0,
    'correlations_found': 0,
    'api_calls_twitter': 0,
    'api_calls_twitter_last_hour': [],
    'api_calls_twitter_today': 0,
    'api_calls_bitquery': 0,
    'started_at': datetime.now(),
    'last_reset': datetime.now(),
    'initialization_complete': False  # Initialization flag
}

def log_debug(emoji, message):
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {emoji} {message}")

async def send_telegram_message(text):
    """Send message to one or multiple Telegram chats"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        success_count = 0
        
        for chat_id in TELEGRAM_CHAT_IDS:
            try:
                data = {
                    'chat_id': chat_id,
                    'text': text,
                    'parse_mode': 'HTML',
                    'disable_web_page_preview': True
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            success_count += 1
            except Exception as e:
                log_debug("❌", f"Error sending to chat {chat_id}: {e}")
                continue
        
        return success_count > 0
    except Exception as e:
        log_debug("❌", f"General error in send_telegram_message: {e}")
        return False

async def send_tweet_notification(username, text, url, timestamp):
    """Send notification for a new tweet"""
    try:
        age_seconds = int(time.time() - timestamp)
        
        # Format tweet text
        tweet_text = text[:400]  # Limit to 400 characters
        if len(text) > 400:
            tweet_text += "..."
        
        message = f"""
🐦 <b>NEW TWEET</b>

👤 <b>@{username}</b>
⏱️ {age_seconds} seconds ago

💬 {tweet_text}

🔗 {url if url else 'Twitter'}
"""
        
        success = await send_telegram_message(message)
        if success:
            log_debug("📱", f"Tweet notified: @{username}")
        return success
    except Exception as e:
        log_debug("❌", f"Error notifying tweet: {e}")
        return False

def check_rate_limit():
    """Check API limits"""
    now = datetime.now()
    
    hour_ago = now - timedelta(hours=1)
    STATS['api_calls_twitter_last_hour'] = [
        t for t in STATS['api_calls_twitter_last_hour'] 
        if t > hour_ago
    ]
    
    if now.date() > STATS['last_reset'].date():
        STATS['api_calls_twitter_today'] = 0
        STATS['last_reset'] = now
    
    calls_last_hour = len(STATS['api_calls_twitter_last_hour'])
    
    if calls_last_hour >= CONFIG['max_twitter_calls_per_hour']:
        return False, "hourly"
    
    if STATS['api_calls_twitter_today'] >= CONFIG['max_twitter_calls_per_day']:
        return False, "daily"
    
    return True, None

def record_api_call():
    now = datetime.now()
    STATS['api_calls_twitter'] += 1
    STATS['api_calls_twitter_today'] += 1
    STATS['api_calls_twitter_last_hour'].append(now)

class TweetCache:
    def __init__(self):
        self.tweets = []
        # VERY short window: only 2 minutes
        self.max_age = CONFIG['correlation_window']
        self.seen_ids = set()
    
    def add(self, text, username, timestamp, twitter_id='', is_init=False):
        STATS['tweets_detected'] += 1
        cache_id = f"{username}_{timestamp}_{text[:50]}"
        
        if cache_id in self.seen_ids:
            return
        
        self.seen_ids.add(cache_id)
        keywords = self._extract_keywords(text)
        
        self.tweets.append({
            'text': text,
            'username': username,
            'timestamp': timestamp,
            'keywords': keywords,
            'age_at_detection': time.time() - timestamp,
            'twitter_id': twitter_id
        })
        
        age_seconds = time.time() - timestamp
        log_debug("📝", f"@{username} ({int(age_seconds)}s): {text[:50]}...")
        
        # Notify if enabled and not init
        if CONFIG['notify_new_tweets'] and not is_init:
            if not CONFIG['notify_only_after_init'] or STATS['initialization_complete']:
                # Build tweet URL
                clean_username = username.replace('@', '')
                tweet_url = f"https://twitter.com/{clean_username}/status/{twitter_id}" if twitter_id else ""
                
                # Create async task to not block
                asyncio.create_task(send_tweet_notification(clean_username, text, tweet_url, timestamp))
        
        self._cleanup()
    
    def _extract_keywords(self, text):
        text_lower = text.lower()
        words = re.findall(r'\b[a-z]{3,}\b', text_lower)
        stopwords = {'the', 'and', 'for', 'with', 'this', 'that', 'are', 'but', 'not', 'you', 'all', 'can', 'has', 'was', 'were', 'been', 'have', 'from', 'they', 'will'}
        keywords = [w for w in words if w not in stopwords]
        return set(keywords)
    
    def _cleanup(self):
        """Cleanup old tweets"""
        cutoff = time.time() - self.max_age
        before = len(self.tweets)
        self.tweets = [t for t in self.tweets if t['timestamp'] > cutoff]
        after = len(self.tweets)
        
        if before != after:
            log_debug("🧹", f"Cache: {before} → {after} tweets ({self.max_age}s)")
    
    def search(self, token_name, token_symbol, token_timestamp):
        """
        Search correlation ONLY with recent tweets
        token_timestamp: Token timestamp to calculate difference
        """
        self._cleanup()
        
        # Convert token timestamp to epoch
        try:
            token_time = datetime.fromisoformat(token_timestamp.replace('Z', '+00:00')).timestamp()
        except:
            token_time = time.time()
        
        if not self.tweets:
            log_debug("🔍", f"Empty cache - No correlation possible")
            return None, 0
        
        # FILTER: Only tweets that are earlier than the token
        # AND that are VERY recent (< max_tweet_age_for_correlation)
        eligible_tweets = []
        for tweet in self.tweets:
            tweet_age = token_time - tweet['timestamp']
            
            # Tweet must be BEFORE the token and RECENT
            if 0 <= tweet_age <= CONFIG['max_tweet_age_for_correlation']:
                eligible_tweets.append(tweet)
        
        if not eligible_tweets:
            log_debug("🔍", f"No eligible tweets (all > {CONFIG['max_tweet_age_for_correlation']}s)")
            return None, 0
        
        log_debug("🔍", f"Searching in {len(eligible_tweets)} eligible tweets")
        
        token_name_lower = token_name.lower()
        token_symbol_lower = token_symbol.lower()
        best_match = None
        best_score = 0
        
        for tweet in eligible_tweets:
            score = 0
            tweet_text_lower = tweet['text'].lower()
            tweet_age = token_time - tweet['timestamp']
            
            # Exact match: HIGH weight
            if token_name_lower in tweet_text_lower or token_symbol_lower in tweet_text_lower:
                score += 70  # Increased from 60
                log_debug("✨", f"Exact match on @{tweet['username']}")
            
            # Keywords
            token_keywords = self._extract_keywords(token_name + " " + token_symbol)
            matching_keywords = token_keywords & tweet['keywords']
            if matching_keywords:
                keyword_points = len(matching_keywords) * 15
                score += keyword_points
                log_debug("🔑", f"Keywords: {matching_keywords} (+{keyword_points})")
            
            # Similarity
            similarity = SequenceMatcher(None, token_name_lower, tweet_text_lower).ratio()
            if similarity > 0.3:
                sim_points = int(similarity * 30)  # Increased from 25
                score += sim_points
            
            # Crypto words
            crypto_words = {'moon', 'pump', 'gem', 'launch', 'bullish', 'meme', 'token', 'rocket', 'binance', 'new'}
            found = [w for w in crypto_words if w in tweet_text_lower]
            if found:
                score += 5
            
            # RECENCY: MUCH more important
            if tweet_age < CONFIG['recency_boost_threshold']:
                # If tweet is < 1 minute, +20 points
                recency_bonus = 20
                score += recency_bonus
                log_debug("⚡", f"FRESH tweet ({int(tweet_age)}s) +{recency_bonus}")
            elif tweet_age < 90:
                # If < 1.5 minutes, +10 points
                score += 10
            
            if score > best_score:
                best_score = score
                best_match = tweet
                log_debug("🏆", f"Best match: {score} pts with @{tweet['username']} ({int(tweet_age)}s)")
        
        final_score = min(best_score, 100)
        
        if best_match:
            tweet_age = token_time - best_match['timestamp']
            log_debug("📊", f"Final score: {final_score}% (tweet {int(tweet_age)}s ago)")
        
        return best_match, final_score

class TwitterMonitor:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.twitterapi.io/twitter/user/last_tweets"
        self.last_tweet_ids = {}
        self.check_count = 0
        self.stopped = False
        self.initialized = False
    
    async def start(self, tweet_cache):
        log_debug("📱", "=== TWITTER MONITOR ===")
        log_debug("⏱️", f"Check: every {CONFIG['twitter_check_interval']}s")
        log_debug("🪟", f"Startup window: {CONFIG['startup_window']}s")
        log_debug("🪟", f"Correlation window: {CONFIG['correlation_window']}s")
        
        if not self.api_key:
            log_debug("⚠️", "No API key")
            while True:
                await asyncio.sleep(60)
            return
        
        log_debug("🔍", "Testing...")
        if not await self._test_api():
            log_debug("❌", "Not available")
            while True:
                await asyncio.sleep(60)
            return
        
        log_debug("✅", "Connected!")
        
        # PHASE 1: INITIALIZATION (last startup window)
        log_debug("📥", f"PHASE 1: Loading last {CONFIG['startup_window']}s of tweets...")
        for account in CONFIG['twitter_accounts']:
            can_call, _ = check_rate_limit()
            if not can_call:
                break
            await self._initialize_account(account, tweet_cache)
        
        self.initialized = True
        STATS['initialization_complete'] = True
        log_debug("✅", "PHASE 1 complete - Base tweets loaded")
        
        # PHASE 2: CONTINUOUS MONITORING (only new tweets)
        log_debug("🔄", "PHASE 2: Monitoring only NEW tweets...")
        
        while True:
            try:
                if self.stopped:
                    await asyncio.sleep(300)
                    continue
                
                self.check_count += 1
                
                for account in CONFIG['twitter_accounts']:
                    can_call, reason = check_rate_limit()
                    
                    if not can_call:
                        if reason == "hourly":
                            await asyncio.sleep(60)
                            continue
                        elif reason == "daily":
                            await asyncio.sleep(3600)
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
    
    async def _initialize_account(self, account, tweet_cache):
        """Load tweets from startup window"""
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
                            
                            # Load only tweets from startup window
                            startup_cutoff = time.time() - CONFIG['startup_window']
                            loaded = 0
                            
                            for tweet in tweets:
                                created_at = tweet.get('createdAt', '')
                                text = tweet.get('text', '')
                                
                                if not text:
                                    continue
                                
                                try:
                                    if created_at:
                                        try:
                                            ts = datetime.fromisoformat(created_at.replace('Z', '+00:00')).timestamp()
                                        except:
                                            from datetime import datetime as dt
                                            ts = dt.strptime(created_at, '%a %b %d %H:%M:%S %z %Y').timestamp()
                                    else:
                                        continue
                                    
                                    # Only if within startup window
                                    if ts >= startup_cutoff:
                                        tid = tweet.get('id', '')
                                        tweet_cache.add(text, account, ts, twitter_id=tid, is_init=True)
                                        loaded += 1
                                
                                except:
                                    pass
                            
                            log_debug("✓", f"@{clean_account}: {loaded} tweets in window")
        except Exception as e:
            log_debug("❌", f"Init: {e}")
    
    async def _check_account(self, account, tweet_cache):
        """Detect ONLY new tweets (after last ID)"""
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
                            
                            # ONLY tweets with higher ID (NEW)
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
                                    
                                    tweet_cache.add(text, account, ts, twitter_id=tweet_id, is_init=False)
                                    new_tweets += 1
                                    self.last_tweet_ids[account] = tweet_id
                                    
                                except:
                                    pass
                        
                        if new_tweets > 0:
                            log_debug("🎉", f"{new_tweets} NEW from @{clean_account}")
                    
                    elif response.status == 402:
                        log_debug("🚨", "Out of credits!")
                        if CONFIG['emergency_stop_on_402']:
                            self.stopped = True
                            await send_telegram_message("🚨 Twitter out of credits - Paused")
        
        except:
            pass

class FourMemeMonitor:
    def __init__(self, api_key):
        self.api_key = api_key
        self.endpoint = "https://streaming.bitquery.io/graphql"
        self.check_count = 0
        self.seen_contracts = set()
        self.last_token_time = None
        self.initialized = False
    
    async def start(self, tweet_cache):
        log_debug("🔥", "=== FOUR.MEME MONITOR ===")
        log_debug("⏱️", f"Check: every {CONFIG['fourmeme_check_interval']}s")
        
        # Wait for Twitter to initialize
        log_debug("⏸️", "Waiting for Twitter initialization...")
        while not STATS['initialization_complete']:
            await asyncio.sleep(1)
        
        log_debug("✅", "Twitter ready - Starting Four.meme")
        
        # PHASE 1: Load tokens from startup window
        log_debug("📥", f"PHASE 1: Loading tokens from last {CONFIG['startup_window']}s...")
        await self._initialize_tokens(tweet_cache)
        
        self.initialized = True
        log_debug("✅", "PHASE 1 complete - Base tokens loaded")
        
        # PHASE 2: Continuous monitoring (only new tokens)
        log_debug("🔄", "PHASE 2: Monitoring only NEW tokens...")
        
        while True:
            try:
                self.check_count += 1
                await self._poll_new_tokens(tweet_cache)
                await asyncio.sleep(CONFIG['fourmeme_check_interval'])
                
            except Exception as e:
                log_debug("❌", f"Error: {e}")
                await asyncio.sleep(30)
    
    async def _initialize_tokens(self, tweet_cache):
        """Load tokens from startup window"""
        since_time = (datetime.now(timezone.utc) - timedelta(seconds=CONFIG['startup_window'])).strftime('%Y-%m-%dT%H:%M:%SZ')
        
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
              limit: {count: 20}
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
        
        await self._execute_query(query, since_time, tweet_cache, is_init=True)
    
    async def _poll_new_tokens(self, tweet_cache):
        """Detect ONLY new tokens (after last timestamp)"""
        if self.last_token_time:
            # Use last known timestamp
            since_time = self.last_token_time
        else:
            # Fallback: last 2 minutes
            since_time = (datetime.now(timezone.utc) - timedelta(minutes=2)).strftime('%Y-%m-%dT%H:%M:%SZ')
        
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
        
        await self._execute_query(query, since_time, tweet_cache, is_init=False)
    
    async def _execute_query(self, query, since_time, tweet_cache, is_init=False):
        try:
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
                        
                        if trades:
                            # Update last timestamp
                            latest_time = trades[0].get('Block', {}).get('Time', '')
                            if latest_time:
                                self.last_token_time = latest_time
                        
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
                            
                            log_debug("🪙", f"{'[INIT] ' if is_init else ''}{name} (${symbol})")
                            
                            # Search correlation (with token timestamp)
                            match, confidence = tweet_cache.search(name, symbol, timestamp)
                            
                            if match and confidence >= CONFIG['min_confidence']:
                                STATS['correlations_found'] += 1
                                log_debug("🎉", f"CORRELATION {confidence}%!")
                                
                                if not is_init:  # Only alert in phase 2
                                    log_debug("📤", "Sending alert to Telegram...")
                                    await self._send_alert(name, symbol, contract, timestamp, match, confidence)
                                else:
                                    log_debug("⏭️", "Init - Alert skipped")
                            elif confidence > 35:
                                log_debug("⚪", f"{confidence}%")
        
        except:
            pass
    
    async def _send_alert(self, name, symbol, contract, timestamp, match, confidence):
        try:
            # Convert timestamps to timezone-aware
            tweet_time = datetime.fromtimestamp(match['timestamp'], tz=timezone.utc)
            
            # Token timestamp already comes with timezone
            if isinstance(timestamp, str):
                token_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                token_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            
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
⏱️ <b>Time:</b> {minutes}m {seconds}s after tweet

🔗 <b>Four.meme:</b> https://four.meme/token/{contract}
📊 <b>PancakeSwap:</b> https://pancakeswap.finance/swap?outputCurrency={contract}
📈 <b>DexScreener:</b> https://dexscreener.com/bsc/{contract}

⚡ <b>Confidence:</b> {confidence}%
"""
            
            success = await send_telegram_message(message)
            if success:
                log_debug("✅", "Alert sent to Telegram!")
            else:
                log_debug("❌", "Error sending alert to Telegram")
        
        except Exception as e:
            log_debug("❌", f"Error in _send_alert: {e}")
            import traceback
            traceback.print_exc()

async def stats_reporter():
    await asyncio.sleep(300)
    
    while True:
        try:
            calls_last_hour = len(STATS['api_calls_twitter_last_hour'])
            
            log_debug("📊", "=== STATS ===")
            log_debug("📱", f"Twitter: {STATS['api_calls_twitter_today']}/day, {calls_last_hour}/hour")
            log_debug("🔥", f"Bitquery: {STATS['api_calls_bitquery']}")
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
    ║      🎯 OPTIMIZED LOGIC: NEW + NEW                       ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    log_debug("🔧", "=== OPTIMIZED CONFIGURATION ===")
    log_debug("📱", f"Telegram Chats: {len(TELEGRAM_CHAT_IDS)} configured")
    for i, chat_id in enumerate(TELEGRAM_CHAT_IDS, 1):
        chat_type = "Group" if chat_id < 0 else "Private"
        log_debug("  ", f"{i}. Chat ID {chat_id} ({chat_type})")
    log_debug("🪟", f"Startup window: {CONFIG['startup_window']}s (3 min)")
    log_debug("🪟", f"Correlation window: {CONFIG['correlation_window']}s (2 min)")
    log_debug("🪟", f"Max tweet age: {CONFIG['max_tweet_age_for_correlation']}s")
    log_debug("⏱️", f"Twitter check: {CONFIG['twitter_check_interval']}s")
    log_debug("⏱️", f"Four.meme check: {CONFIG['fourmeme_check_interval']}s")
    log_debug("🔔", f"Notify tweets: {'✅' if CONFIG['notify_new_tweets'] else '❌'}")
    print()
    
    calls_per_day = min((3600 / CONFIG['twitter_check_interval']) * len(CONFIG['twitter_accounts']) * 24, CONFIG['max_twitter_calls_per_day'])
    log_debug("💰", f"Max consumption: {int(calls_per_day)} calls/day")
    print()
    
    await send_telegram_message(f"🤖 <b>Optimized bot started</b>\n\n🎯 Priority: New tweets + New tokens\n🪟 Window: {CONFIG['correlation_window']}s\n💰 Max: {int(calls_per_day)}/day")
    
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
