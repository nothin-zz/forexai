import requests
import json
import google.generativeai as genai
import re  # RE modulini qo'shdik
from datetime import datetime

# API SETTINGS
TWELVE_API_KEY = "0bfaff2b15804663ae9d9536c6cf0cac"
GEMINI_API_KEY = "AIzaSyDQ2oUz2d-2ZpIM0sAc1F4oOPmSQxl3sYE"

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

WATCH_PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY",
    "USD/CHF", "AUD/USD", "XAU/USD",
    "GBP/JPY", "EUR/GBP", "NZD/USD"
]

def get_candles(pair: str, timeframe="1h", count=100):
    url = "https://api.twelvedata.com/time_series"
    
    interval_map = {
        "H1": "1h", "H4": "4h", "D1": "1day",
        "1h": "1h", "4h": "4h", "1d": "1day"
    }
    interval = interval_map.get(timeframe, timeframe)

    params = {
        "symbol": pair,
        "interval": interval,
        "outputsize": count,
        "apikey": TWELVE_API_KEY,
    }

    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()

        if "values" not in data:
            error_msg = data.get("message", "Unknown error")
            print(f"❌ Error [{pair}]: {error_msg}")
            return []

        candles = []
        for c in reversed(data["values"]):
            candles.append({
                "time": c["datetime"],
                "open": float(c["open"]),
                "high": float(c["high"]),
                "low": float(c["low"]),
                "close": float(c["close"])
            })
        return candles
    except Exception as e:
        print(f"❌ Connection error {pair}: {e}")
        return []

def ema(values, period):
    if len(values) < period: return []
    k = 2 / (period + 1)
    ema_list = [sum(values[:period]) / period]
    for v in values[period:]:
        ema_list.append(v * k + ema_list[-1] * (1 - k))
    return ema_list

def rsi(values, period=14):
    if len(values) < period + 1: return 50
    gains = [max(values[i] - values[i-1], 0) for i in range(1, len(values))]
    losses = [max(values[i-1] - values[i], 0) for i in range(1, len(values))]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def detect_pattern(candles):
    if len(candles) < 3: return "Neutral"
    c = candles[-1]
    o, h, l, cl = c["open"], c["high"], c["low"], c["close"]
    body = abs(cl - o)
    total_range = (h - l) if h != l else 0.0001
    if body / total_range < 0.15: return "Doji"
    if cl > o and body > (total_range * 0.6): return "Strong Bullish"
    if cl < o and body > (total_range * 0.6): return "Strong Bearish"
    return "Bullish" if cl > o else "Bearish"

def analyze_with_ai(pair, timeframe, candles):
    if not candles: return None
    closes = [c["close"] for c in candles]
    current = closes[-1]
    rsi_val = rsi(closes)
    pattern = detect_pattern(candles)
    
    prompt = f"""
    Act as a Forex Expert. Analyze {pair} on {timeframe}.
    Price: {current}, RSI: {rsi_val:.2f}, Pattern: {pattern}.
    Last 5 candles: {closes[-5:]}
    Return ONLY JSON:
    {{"signal": "BUY/SELL/WAIT", "confidence": 0-100, "entry": {current}, "stop_loss": 0, "tp": 0, "reason": ""}}
    """
    try:
        resp = model.generate_content(prompt)
        # JSONni tozalash
        match = re.search(r'\{.*\}', resp.text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except:
        return None

def scan_all_pairs():
    all_signals = []
    print(f"🚀 Skan boshlandi: {datetime.now().strftime('%H:%M:%S')}")
    for pair in WATCH_PAIRS:
        candles = get_candles(pair)
        if candles:
            res = analyze_with_ai(pair, "1h", candles)
            if res and res.get("signal") in ["BUY", "SELL"]:
                print(f"🎯 Signal topildi: {pair} | {res['signal']}")
                all_signals.append({"pair": pair, "data": res})
    return all_signals

# ISHGA TUSHIRISH
if __name__ == "__main__":
    results = scan_all_pairs()
    print(f"\n✅ Jami {len(results)} ta signal topildi.")
