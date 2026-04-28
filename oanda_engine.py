"""
oanda_engine.py (FREE VERSION)
Twelve Data + Gemini AI integration uchun moslashtirilgan Forex engine
"""

import requests
import json
import google.generativeai as genai
from datetime import datetime

# ─────────────────────────────────────────
# FREE API SETTINGS (OANDA o‘rniga)
# ─────────────────────────────────────────

TWELVE_API_KEY = "0bfaff2b15804663ae9d9536c6cf0cac"

# Gemini AI (Claude o‘rniga)
GEMINI_API_KEY = "AIzaSyDQ2oUz2d-2ZpIM0sAc1F4oOPmSQxl3sYE"

genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel("gemini-1.5-flash")

# Watch list
WATCH_PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY",
    "USD/CHF", "AUD/USD", "XAU/USD",
    "GBP/JPY", "EUR/GBP", "NZD/USD"
]

# ─────────────────────────────────────────
# PRICE DATA (Twelve Data)
# ─────────────────────────────────────────

def get_candles(pair: str, timeframe="1h", count=100):
    """
    Twelve Data dan candle olish
    """
    url = "https://api.twelvedata.com/time_series"

    params = {
        "symbol": pair,
        "interval": timeframe,
        "outputsize": count,
        "apikey": TWELVE_API_KEY,
        "format": "JSON"
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        if "values" not in data:
            return []

        candles = []

        for c in reversed(data["values"]):
            candles.append({
                "time": c["datetime"],
                "open": float(c["open"]),
                "high": float(c["high"]),
                "low": float(c["low"]),
                "close": float(c["close"]),
                "volume": 0
            })

        return candles

    except Exception as e:
        print("Candle error:", e)
        return []


# ─────────────────────────────────────────
# CURRENT PRICE
# ─────────────────────────────────────────

def get_current_price(pair: str):
    url = "https://api.twelvedata.com/price"

    params = {
        "symbol": pair,
        "apikey": TWELVE_API_KEY
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        price = float(data.get("price", 0))

        return {
            "bid": price,
            "ask": price + 0.0002,
            "spread": 0.0002
        }

    except Exception as e:
        print("Price error:", e)
        return {}


# ─────────────────────────────────────────
# INDICATORS (SIMPLE VERSION)
# ─────────────────────────────────────────

def ema(values, period):
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    ema_list = [sum(values[:period]) / period]

    for v in values[period:]:
        ema_list.append(v * k + ema_list[-1] * (1 - k))

    return ema_list


def rsi(values, period=14):
    if len(values) < period + 1:
        return 50

    gains, losses = [], []

    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# ─────────────────────────────────────────
# PATTERN DETECTION
# ─────────────────────────────────────────

def detect_pattern(candles):
    if len(candles) < 3:
        return "Unknown"

    c = candles[-1]
    o, h, l, cl = c["open"], c["high"], c["low"], c["close"]

    body = abs(cl - o)
    range_ = h - l if h != l else 0.0001

    if body / range_ < 0.1:
        return "Doji"

    if cl > o:
        return "Bullish Candle"
    else:
        return "Bearish Candle"


# ─────────────────────────────────────────
# GEMINI AI ANALYSIS (Claude o‘rniga)
# ─────────────────────────────────────────

def analyze_with_ai(pair, timeframe, candles, knowledge=None):

    if not candles:
        return {}

    closes = [c["close"] for c in candles]
    current = closes[-1]

    ema20 = ema(closes, 20)
    rsi_val = rsi(closes)
    pattern = detect_pattern(candles)

    last_candles = "\n".join([
        f"O:{c['open']} H:{c['high']} L:{c['low']} C:{c['close']}"
        for c in candles[-5:]
    ])

    prompt = f"""
You are a Forex AI analyst.

PAIR: {pair}
TIMEFRAME: {timeframe}
PRICE: {current}

RSI: {rsi_val}
Pattern: {pattern}

Last candles:
{last_candles}

Return ONLY JSON:
{{
"signal": "BUY | SELL | WAIT",
"confidence": 0-100,
"entry": number,
"stop_loss": number,
"tp1": number,
"tp2": number,
"tp3": number,
"risk_reward": "1:2",
"reasoning": "short reason"
}}
"""

    try:
        resp = model.generate_content(prompt)
        text = resp.text

        import re
        match = re.search(r"\{.*\}", text, re.DOTALL)

        if not match:
            return {}

        data = json.loads(match.group())

        data["pair"] = pair
        data["timeframe"] = timeframe
        data["pattern"] = pattern

        return data

    except Exception as e:
        print("AI error:", e)
        return {}


# ─────────────────────────────────────────
# SCAN ALL PAIRS
# ─────────────────────────────────────────

def scan_all_pairs(timeframe="1h", knowledge=None):
    results = []

    for pair in WATCH_PAIRS:
        try:
            candles = get_candles(pair, timeframe, 100)

            if not candles:
                continue

            result = analyze_with_ai(pair, timeframe, candles, knowledge)

            if result and result.get("signal") in ["BUY", "SELL"]:
                if result.get("confidence", 0) >= 65:
                    results.append(result)

        except Exception as e:
            print("Scan error:", pair, e)

    return results
