"""
4H 3% Displacement Fib Strategy - Telegram Alert Checker
----------------------------------------------------------
Replicates the exact logic from the final .pine strategy and checks
the most recently CLOSED 4H HYPEUSDT perpetual candle on Bybit.
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
INTERVAL_MINUTES = 240   # 4 hours
MIN_MOVE_PCT = 3.0       # minMovePct
FIB_ENTRY = 0.382        # fibEntry
FIB_EXTENSION = 0.618    # fibExtension
ENTRY_OFFSET_PCT = 0.001 # 0.1% buffer beyond the 0.382 level, matching the .pine script
VOL_LEN = 20             # volLen
VOL_MULTIPLIER = 1.5     # volMultiplier
ATR_LEN = 14             # atrLen
ATR_MULTIPLIER = 1.5     # atrMultiplier

STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")


def fetch_klines_okx(limit):
    """OKX public API - HYPE-USDT-SWAP, 4H candles."""
    url = "https://www.okx.com/api/v5/market/candles"
    params = {"instId": "HYPE-USDT-SWAP", "bar": "4H", "limit": limit}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "0":
        raise RuntimeError(f"OKX API error: {data}")
    raw = list(reversed(data["data"]))  # OKX returns newest-first
    return [
        {
            "open_time": int(k[0]),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        }
        for k in raw
    ]


def fetch_klines_bybit(limit):
    """Bybit public API - HYPEUSDT linear perpetual, 4H candles."""
    url = "https://api.bybit.com/v5/market/kline"
    params = {"category": "linear", "symbol": SYMBOL, "interval": str(INTERVAL_MINUTES), "limit": limit}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    raw = list(reversed(data["result"]["list"]))  # Bybit returns newest-first
    return [
        {
            "open_time": int(k[0]),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        }
        for k in raw
    ]


def fetch_klines_binance(limit):
    """Binance Futures public API - HYPEUSDT perpetual, 4H candles."""
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {"symbol": SYMBOL, "interval": "4h", "limit": limit}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    raw = resp.json()  # Binance returns oldest-first already
    return [
        {
            "open_time": int(k[0]),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        }
        for k in raw
    ]


def fetch_klines(limit=100):
    """Try multiple exchanges in order, since exchanges intermittently
    block requests from cloud/CI IP ranges (GitHub Actions included).
    Uses whichever one actually responds - self-heals if one gets
    blocked without needing another manual fix."""
    sources = [
        ("OKX", fetch_klines_okx),
        ("Bybit", fetch_klines_bybit),
        ("Binance", fetch_klines_binance),
    ]
    last_error = None
    for name, fn in sources:
        try:
            candles = fn(limit)
            if candles:
                print(f"Fetched candles from {name}.")
                return candles
        except Exception as e:
            print(f"{name} failed: {e}")
            last_error = e
    raise RuntimeError(f"All data sources failed. Last error: {last_error}")


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

    candles = fetch_klines(limit=max(VOL_LEN, ATR_LEN) + 10)

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

    bull_382 = h - candle_range * FIB_ENTRY
    bull_entry = bull_382 * (1 + ENTRY_OFFSET_PCT)
    bull_extension = h + candle_range * FIB_EXTENSION
    bull_qualified = bull_move and c > bull_382 and vol_confirmed

    bear_382 = l + candle_range * FIB_ENTRY
    bear_entry = bear_382 * (1 - ENTRY_OFFSET_PCT)
    bear_extension = l - candle_range * FIB_EXTENSION
    bear_qualified = bear_move and c < bear_382 and vol_confirmed

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
