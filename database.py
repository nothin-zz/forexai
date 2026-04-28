"""
database.py — FREE Forex AI Bot database layer
SQLite + self-learning system
"""

import sqlite3
import json
import os
from datetime import datetime

DB_PATH = "forex_ai.db"
JSON_PATH = "forex_memory.json"


# ─────────────────────────────────────────
# INIT DATABASE
# ─────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        pair TEXT,
        timeframe TEXT,
        signal TEXT,
        pattern TEXT,
        entry_price TEXT,
        stop_loss TEXT,
        tp1 TEXT,
        tp2 TEXT,
        tp3 TEXT,
        confidence INTEGER,
        result TEXT DEFAULT NULL,
        profit_loss REAL DEFAULT NULL,
        timestamp TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS user_stats (
        user_id INTEGER PRIMARY KEY,
        total INTEGER DEFAULT 0,
        wins INTEGER DEFAULT 0,
        win_rate REAL DEFAULT 0,
        joined TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS pattern_stats (
        pattern TEXT PRIMARY KEY,
        total INTEGER DEFAULT 0,
        wins INTEGER DEFAULT 0,
        win_rate REAL DEFAULT 0
    )
    """)

    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# USER INIT
# ─────────────────────────────────────────

def ensure_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
    INSERT OR IGNORE INTO user_stats (user_id, joined)
    VALUES (?, ?)
    """, (user_id, datetime.now().isoformat()))

    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# SAVE SIGNAL
# ─────────────────────────────────────────

def save_signal(
    user_id, pair, timeframe,
    signal, pattern,
    entry, sl, tp1, tp2, tp3,
    confidence, market_context="", indicators="",
    source="auto"
):

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
    INSERT INTO signals (
        user_id, pair, timeframe, signal, pattern,
        entry_price, stop_loss, tp1, tp2, tp3,
        confidence, timestamp
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        user_id, pair, timeframe, signal, pattern,
        entry, sl, tp1, tp2, tp3,
        confidence,
        datetime.now().isoformat()
    ))

    sid = c.lastrowid

    conn.commit()
    conn.close()

    _save_json(sid, user_id, pair, signal, pattern, confidence)

    return sid


# ─────────────────────────────────────────
# UPDATE RESULT (WIN/LOSS)
# ─────────────────────────────────────────

def update_signal_result(signal_id: int, result: str, profit_loss: float = 0):

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
    UPDATE signals
    SET result=?, profit_loss=?
    WHERE id=?
    """, (result, profit_loss, signal_id))

    c.execute("""
    SELECT user_id, pattern FROM signals WHERE id=?
    """, (signal_id,))

    row = c.fetchone()

    if row:
        uid, pattern = row
        _update_user_stats(c, uid, result)
        _update_pattern_stats(c, pattern, result)

    conn.commit()
    conn.close()

    _update_json(signal_id, result, profit_loss)


# ─────────────────────────────────────────
# USER STATS
# ─────────────────────────────────────────

def _update_user_stats(c, uid, result):
    is_win = 1 if result == "WIN" else 0

    c.execute("""
    SELECT total, wins FROM user_stats WHERE user_id=?
    """, (uid,))

    row = c.fetchone()

    if row:
        total = row[0] + 1
        wins = row[1] + is_win

        win_rate = (wins / total) * 100

        c.execute("""
        UPDATE user_stats
        SET total=?, wins=?, win_rate=?
        WHERE user_id=?
        """, (total, wins, win_rate, uid))


# ─────────────────────────────────────────
# PATTERN STATS
# ─────────────────────────────────────────

def _update_pattern_stats(c, pattern, result):
    is_win = 1 if result == "WIN" else 0

    c.execute("""
    SELECT total, wins FROM pattern_stats WHERE pattern=?
    """, (pattern,))

    row = c.fetchone()

    if row:
        total = row[0] + 1
        wins = row[1] + is_win
        win_rate = (wins / total) * 100

        c.execute("""
        UPDATE pattern_stats
        SET total=?, wins=?, win_rate=?
        WHERE pattern=?
        """, (total, wins, win_rate, pattern))

    else:
        c.execute("""
        INSERT INTO pattern_stats (pattern, total, wins, win_rate)
        VALUES (?, 1, ?, ?)
        """, (pattern, is_win, 100 if is_win else 0))


# ─────────────────────────────────────────
# AI KNOWLEDGE (SELF LEARNING)
# ─────────────────────────────────────────

def get_ai_knowledge():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
    SELECT pattern, win_rate, total
    FROM pattern_stats
    WHERE total >= 3
    ORDER BY win_rate DESC
    LIMIT 10
    """)

    rows = c.fetchall()
    conn.close()

    return [
        {
            "pattern": r[0],
            "win_rate": round(r[1], 1),
            "total": r[2]
        }
        for r in rows
    ]


# ─────────────────────────────────────────
# GLOBAL STATS
# ─────────────────────────────────────────

def get_global_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM signals")
    total = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM signals WHERE result='WIN'")
    wins = c.fetchone()[0]

    c.execute("SELECT COUNT(DISTINCT user_id) FROM signals")
    users = c.fetchone()[0]

    win_rate = round((wins / total * 100), 1) if total > 0 else 0

    conn.close()

    return {
        "total": total,
        "wins": wins,
        "users": users,
        "win_rate": win_rate
    }


# ─────────────────────────────────────────
# USER STATS
# ─────────────────────────────────────────

def get_user_stats(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
    SELECT total, wins, win_rate
    FROM user_stats
    WHERE user_id=?
    """, (user_id,))

    row = c.fetchone()
    conn.close()

    if row:
        return {
            "total": row[0],
            "wins": row[1],
            "win_rate": round(row[2], 1)
        }

    return {"total": 0, "wins": 0, "win_rate": 0}


# ─────────────────────────────────────────
# JSON MEMORY (backup learning)
# ─────────────────────────────────────────

def _save_json(sid, uid, pair, signal, pattern, confidence):
    data = {}

    if os.path.exists(JSON_PATH):
        with open(JSON_PATH, "r") as f:
            data = json.load(f)

    data[str(sid)] = {
        "user_id": uid,
        "pair": pair,
        "signal": signal,
        "pattern": pattern,
        "confidence": confidence,
        "result": None,
        "time": datetime.now().isoformat()
    }

    with open(JSON_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _update_json(sid, result, pl):
    if not os.path.exists(JSON_PATH):
        return

    with open(JSON_PATH, "r") as f:
        data = json.load(f)

    if str(sid) in data:
        data[str(sid)]["result"] = result
        data[str(sid)]["profit_loss"] = pl

    with open(JSON_PATH, "w") as f:
        json.dump(data, f, indent=2)
