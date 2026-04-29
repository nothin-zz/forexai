“””
twelve_data_engine.py
Twelve Data API + Gemini AI - config.env dan kalitlar o’qiladi
“””

import requests
import json
import re
import os
import google.generativeai as genai
from datetime import datetime

# config.env faylidan kalitlarni o’qish (tirnoq muammosi yo’q!)

def load_config():
cfg = {}
try:
path = os.path.join(os.path.dirname(os.path.abspath(**file**)), “config.env”)
with open(path) as f:
for line in f:
line = line.strip()
if line and “=” in line:
k, v = line.split(”=”, 1)
cfg[k.strip()] = v.strip()
except Exception as e:
print(“config.env o’qilmadi:”, e)
return cfg

_cfg           = load_config()
TWELVE_API_KEY = _cfg.get(“TWELVE_API_KEY”, “”)
GEMINI_API_KEY = _cfg.get(“GEMINI_API_KEY”, “”)

TWELVE_BASE_URL = “https://api.twelvedata.com”

genai.configure(api_key=GEMINI_API_KEY)
gemini = genai.GenerativeModel(“gemini-1.5-flash”)

# Kuzatiladigan Forex juftliklar

WATCH_PAIRS = [
“EUR/USD”, “GBP/USD”, “USD/JPY”,
“USD/CHF”, “AUD/USD”, “XAU/USD”,
“GBP/JPY”, “EUR/GBP”, “NZD/USD”,
“USD/CAD”, “EUR/JPY”, “GBP/CHF”
]

TF_MAP = {
“M15”: “15min”,
“H1”:  “1h”,
“H4”:  “4h”,
“D1”:  “1day”,
}

def get_candles(pair, timeframe=“H1”, count=100):
tf  = TF_MAP.get(timeframe, “1h”)
url = TWELVE_BASE_URL + “/time_series”
params = {
“symbol”:     pair,
“interval”:   tf,
“outputsize”: count,
“apikey”:     TWELVE_API_KEY,
“format”:     “JSON”
}
try:
resp = requests.get(url, params=params, timeout=15)
data = resp.json()
if data.get(“status”) == “error”:
print(“Twelve Data xato:”, data.get(“message”))
return []
candles = []
for v in reversed(data.get(“values”, [])):
candles.append({
“time”:   v.get(“datetime”, “”),
“open”:   float(v.get(“open”, 0)),
“high”:   float(v.get(“high”, 0)),
“low”:    float(v.get(“low”, 0)),
“close”:  float(v.get(“close”, 0)),
“volume”: float(v.get(“volume”, 0)),
})
return candles
except Exception as e:
print(“get_candles xato:”, e)
return []

def get_current_price(pair):
url    = TWELVE_BASE_URL + “/price”
params = {“symbol”: pair, “apikey”: TWELVE_API_KEY}
try:
resp  = requests.get(url, params=params, timeout=10)
data  = resp.json()
price = float(data.get(“price”, 0))
is_jpy = “JPY” in pair
spread = round(price * 0.0001 if not is_jpy else price * 0.001, 5)
return {
“price”:  price,
“bid”:    round(price - spread / 2, 5),
“ask”:    round(price + spread / 2, 5),
“spread”: spread
}
except Exception as e:
print(“get_current_price xato:”, e)
return {}

def calc_ema(closes, period):
if len(closes) < period:
return []
k   = 2 / (period + 1)
ema = [sum(closes[:period]) / period]
for price in closes[period:]:
ema.append(price * k + ema[-1] * (1 - k))
return ema

def calc_rsi(closes, period=14):
if len(closes) < period + 1:
return 50.0
gains, losses = [], []
for i in range(1, len(closes)):
diff = closes[i] - closes[i - 1]
gains.append(max(diff, 0))
losses.append(max(-diff, 0))
ag = sum(gains[-period:]) / period
al = sum(losses[-period:]) / period
if al == 0:
return 100.0
return round(100 - (100 / (1 + ag / al)), 2)

def calc_macd(closes):
e12 = calc_ema(closes, 12)
e26 = calc_ema(closes, 26)
if not e12 or not e26:
return {“macd”: 0, “signal”: 0, “histogram”: 0}
mn  = min(len(e12), len(e26))
ml  = [e12[i] - e26[i] for i in range(-mn, 0)]
sl  = calc_ema(ml, 9)
if not sl:
return {“macd”: 0, “signal”: 0, “histogram”: 0}
m = round(ml[-1], 6)
s = round(sl[-1], 6)
return {“macd”: m, “signal”: s, “histogram”: round(m - s, 6)}

def calc_atr(candles, period=14):
if len(candles) < period:
return 0.0
trs = []
for i in range(1, len(candles)):
h, l, pc = candles[i][“high”], candles[i][“low”], candles[i-1][“close”]
trs.append(max(h - l, abs(h - pc), abs(l - pc)))
return round(sum(trs[-period:]) / period, 5)

def calc_bollinger(closes, period=20):
if len(closes) < period:
return {“upper”: 0, “middle”: 0, “lower”: 0}
sma = sum(closes[-period:]) / period
std = (sum((x - sma) ** 2 for x in closes[-period:]) / period) ** 0.5
return {
“upper”:  round(sma + 2 * std, 5),
“middle”: round(sma, 5),
“lower”:  round(sma - 2 * std, 5)
}

def find_support_resistance(candles, lookback=30):
recent = candles[-lookback:] if len(candles) >= lookback else candles
highs  = sorted([c[“high”] for c in recent])
lows   = sorted([c[“low”]  for c in recent])
return {
“strong_resistance”: round(highs[-1], 5),
“mid_resistance”:    round((highs[-1] + highs[-3]) / 2, 5),
“mid_support”:       round((lows[0] + lows[2]) / 2, 5),
“strong_support”:    round(lows[0], 5),
}

def detect_pattern(candles):
if len(candles) < 3:
return “Unknown”
c1, c2, c = candles[-3], candles[-2], candles[-1]
o, h, l, cl = c[“open”], c[“high”], c[“low”], c[“close”]
body  = abs(cl - o)
rng   = h - l if h != l else 0.0001
upper = h - max(o, cl)
lower = min(o, cl) - l

```
if body / rng < 0.1:                                               return "Doji"
if lower > 2 * body and upper < body:                              return "Hammer"
if upper > 2 * body and lower < body:                              return "Shooting Star"
if lower > 3 * body:                                               return "Bullish Pin Bar"
if upper > 3 * body:                                               return "Bearish Pin Bar"
if body / rng > 0.9:
    return "Bullish Marubozu" if cl > o else "Bearish Marubozu"
if c2["close"] < c2["open"] and cl > o and o < c2["close"] and cl > c2["open"]:
    return "Bullish Engulfing"
if c2["close"] > c2["open"] and cl < o and o > c2["close"] and cl < c2["open"]:
    return "Bearish Engulfing"
if (c1["close"] < c1["open"]
        and abs(c2["close"] - c2["open"]) < (c1["open"] - c1["close"]) * 0.3
        and cl > o and cl > (c1["open"] + c1["close"]) / 2):
    return "Morning Star"
if (c1["close"] > c1["open"]
        and abs(c2["close"] - c2["open"]) < (c1["close"] - c1["open"]) * 0.3
        and cl < o and cl < (c1["open"] + c1["close"]) / 2):
    return "Evening Star"
if h < candles[-2]["high"] and l > candles[-2]["low"]:
    return "Inside Bar"
return "No Clear Pattern"
```

def analyze_with_ai(pair, timeframe, candles, knowledge=None):
if not candles or len(candles) < 20:
return {}

```
closes  = [c["close"] for c in candles]
current = closes[-1]

ema20   = calc_ema(closes, 20)
ema50   = calc_ema(closes, 50)
ema200  = calc_ema(closes, 200)
rsi     = calc_rsi(closes)
macd    = calc_macd(closes)
atr     = calc_atr(candles)
bb      = calc_bollinger(closes)
levels  = find_support_resistance(candles)
pattern = detect_pattern(candles)

recent_str = ""
for c in candles[-10:]:
    d = "UP" if c["close"] > c["open"] else "DN"
    recent_str += "%s O:%.5f H:%.5f L:%.5f C:%.5f\n" % (
        d, c["open"], c["high"], c["low"], c["close"])

know_block = ""
if knowledge:
    know_block = "\nO'RGANILGAN BILIMLAR:\n"
    for k in knowledge[:5]:
        know_block += "  %s: %.1f%% win | best: %s\n" % (
            k["pattern"], k["win_rate"], k["best_pair"])

is_jpy   = "JPY" in pair
pip_val  = 0.01 if is_jpy else 0.0001
atr_pips = round(atr / pip_val)

prompt = (
    "Sen professional Forex tahlilchisisisan." + know_block + "\n\n"
    "Juftlik: " + pair + "  Timeframe: " + timeframe + "\n"
    "Narx: %.5f\n" % current +
    "EMA20: %.5f  EMA50: %.5f  EMA200: %.5f\n" % (
        ema20[-1] if ema20 else 0,
        ema50[-1] if ema50 else 0,
        ema200[-1] if ema200 else 0) +
    "RSI: %.1f  MACD: %.6f  Hist: %.6f\n" % (rsi, macd["macd"], macd["histogram"]) +
    "BB Upper: %.5f  Lower: %.5f\n" % (bb["upper"], bb["lower"]) +
    "ATR: %.5f (~%d pips)\n" % (atr, atr_pips) +
    "Support: %.5f  Resistance: %.5f\n" % (
        levels["strong_support"], levels["strong_resistance"]) +
    "Pattern: " + pattern + "\n\n"
    "So'nggi 10 sham:\n" + recent_str + "\n"
    "Faqat JSON formatida javob ber:\n"
    '{"signal":"BUY or SELL or WAIT","confidence":80,'
    '"trend":"UPTREND or DOWNTREND or SIDEWAYS",'
    '"entry":' + "%.5f" % current + ","
    '"stop_loss":0.0,"tp1":0.0,"tp2":0.0,"tp3":0.0,'
    '"sl_pips":' + str(atr_pips) + ',"tp1_pips":0,"tp2_pips":0,"tp3_pips":0,'
    '"risk_reward":"1:3",'
    '"sl_reason":"sabab","tp_reason":"sabab",'
    '"market_structure":"struktura",'
    '"session":"London or New York or Tokyo",'
    '"indicators_summary":"qisqacha",'
    '"reasoning":"3 jumlada sabab",'
    '"risk_warning":"ogohlantirish"}'
)

try:
    resp  = gemini.generate_content(prompt)
    raw   = resp.text
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {}
    result = json.loads(match.group())
    result["pair"]      = pair
    result["timeframe"] = timeframe
    result["pattern"]   = pattern
    result["atr"]       = atr
    result["levels"]    = levels
    return result
except Exception as e:
    print("AI tahlil xato:", e)
    return {}
```

def scan_all_pairs(timeframe=“H1”, knowledge=None):
signals = []
for pair in WATCH_PAIRS:
try:
candles = get_candles(pair, timeframe, count=100)
if not candles:
continue
result = analyze_with_ai(pair, timeframe, candles, knowledge)
if result and result.get(“signal”) in [“BUY”, “SELL”]:
if result.get(“confidence”, 0) >= 70:
signals.append(result)
print(“Signal: %s -> %s (%d%%)” % (
pair, result[“signal”], result[“confidence”]))
except Exception as e:
print(“Skan xato (%s): %s” % (pair, e))
return signals
