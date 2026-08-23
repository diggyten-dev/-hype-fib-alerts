"""
4H 3% Displacement Fib Strategy - Telegram Alert Checker
----------------------------------------------------------
Replicates the exact logic from the final .pine strategy and checks
the most recently CLOSED 4H HYPEUSDT.P candle on Binance Futures.
If a long or short setup qualifies, sends a Telegram message with
entry / stop / target - the same numbers your strategy would show
on the chart.

Meant to run on a schedule (e.g. every 4 hours, via GitHub Actions)
so you don't have to watch the chart yourself.

Config comes from environment variables (set as GitHub Actions
secrets - never hardcode your bot token in this file):
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID

State (which candle we last alerted on) is stored in state.json in
the same folder, so re-runs don't send duplicate alerts for the
same candle.
"""

import os
import json
import time
import requests
from datetime import datetime, timezone

# ============================================================
# STRATEGY PARAMETERS - must match your final .pine file exactly.
# If you change the .pine inputs, update these to match.
# ============================================================

SYMBOL = "HYPEUSDT"
INTERVAL = "4h"
MIN_MOVE_PCT = 3.0       # minMovePct
FIB_ENTRY = 0.382        # fibEntry
FIB_EXTENSION = 0.382    # fibExtension
VOL_LEN = 20             # volLen
VOL_MULTIPLIER = 1.5     # volMultiplier
ATR_LEN = 14             # atrLen
ATR_MULTIPLIER = 1.5     # atrMultiplier

BINANCE_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")


def fetch_klines(symbol, interval, limit=100):
    """Fetch recent klines from Binance Futures public API (no key needed)."""
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    resp = requests.get(BINANCE_KLINES_URL, params=params, timeout=15)
    resp.raise_for_status()
    raw = resp.json()
    candles = []
    for k in raw:
        candles.append({
            "open_time": k[0],
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "close_time": k[6],
        })
    return candles


def wilder_atr(candles, length):
    """Wilder's ATR (RMA of True Range), matching Pine's ta.atr()."""
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        trs.append(tr)

    if len(trs) < length:
        return None

    # Seed with simple average of the first `length` true ranges,
    # then apply Wilder smoothing for the rest - this matches
    # Pine's ta.atr() behavior closely enough for alerting purposes.
    atr = sum(trs[:length]) / length
    for tr in trs[length:]:
        atr = (atr * (length - 1) + tr) / length
    return atr


def sma(values, length):
    if len(values) < length:
        return None
    return sum(values[-length:]) / length


def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"last_alerted_open_time": None}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variables.")

    candles = fetch_klines(SYMBOL, INTERVAL, limit=max(VOL_LEN, ATR_LEN) + 10)

    # The LAST candle from Binance may still be forming (not closed yet).
    # Use the second-to-last one as "the most recently closed candle".
    if len(candles) < 2:
        print("Not enough candle data yet.")
        return

    qualifying_candle = candles[-2]
    history_up_to_qualifying = candles[:-1]  # everything through the qualifying candle

    state = load_state()
    if state.get("last_alerted_open_time") == qualifying_candle["open_time"]:
        print("Already alerted on this candle. Skipping.")
        return

    o = qualifying_candle["open"]
    h = qualifying_candle["high"]
    l = qualifying_candle["low"]
    c = qualifying_candle["close"]
    v = qualifying_candle["volume"]

    candle_move_pct = ((c - o) / o) * 100.0
    candle_range = h - l

    bull_move = candle_move_pct >= MIN_MOVE_PCT
    bear_move = candle_move_pct <= -MIN_MOVE_PCT

    volumes = [x["volume"] for x in history_up_to_qualifying]
    avg_volume = sma(volumes, VOL_LEN)
    vol_confirmed = avg_volume is not None and v >= avg_volume * VOL_MULTIPLIER

    atr_value = wilder_atr(history_up_to_qualifying, ATR_LEN)

    if candle_range <= 0 or avg_volume is None or atr_value is None:
        print("Not enough data or zero range candle. Skipping.")
        return

    bull_entry = l + candle_range * FIB_ENTRY
    bull_extension = h + candle_range * FIB_EXTENSION
    bull_qualified = bull_move and c > bull_entry and vol_confirmed

    bear_entry = h - candle_range * FIB_ENTRY
    bear_extension = l - candle_range * FIB_EXTENSION
    bear_qualified = bear_move and c < bear_entry and vol_confirmed

    message = None

    candle_time_str = datetime.fromtimestamp(
        qualifying_candle["open_time"] / 1000, tz=timezone.utc
    ).strftime("%H:%M UTC")

    if bull_qualified:
        stop = l - atr_value * ATR_MULTIPLIER
        message = (
            f"Candle detected: {candle_time_str}\n"
            f"Candle moved: {candle_move_pct:.2f}%\n"
            f"Entry trade at level {FIB_ENTRY}: ${bull_entry:.4f}\n"
            f"Take profit: ${bull_extension:.4f}\n"
            f"Stop loss: ${stop:.4f}\n"
            f"Direction: LONG | Valid for next candle only - place a LIMIT order at entry."
        )
    elif bear_qualified:
        stop = h + atr_value * ATR_MULTIPLIER
        message = (
            f"Candle detected: {candle_time_str}\n"
            f"Candle moved: {candle_move_pct:.2f}%\n"
            f"Entry trade at level {FIB_ENTRY}: ${bear_entry:.4f}\n"
            f"Take profit: ${bear_extension:.4f}\n"
            f"Stop loss: ${stop:.4f}\n"
            f"Direction: SHORT | Valid for next candle only - place a LIMIT order at entry."
        )

    if message:
        send_telegram(token, chat_id, message)
        print("Alert sent:\n" + message)
    else:
        print(f"No qualifying setup on this candle. Move={candle_move_pct:.2f}% VolConfirmed={vol_confirmed}")

    state["last_alerted_open_time"] = qualifying_candle["open_time"]
    save_state(state)


if __name__ == "__main__":
    main()
