import os
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Flask Web Server-ஐ இயக்குகிறது
keep_alive()
import requests
import pandas as pd
import numpy as np
import time

TELEGRAM_TOKEN = "8926120243:AAEVZ3ilP8PD03bUeqmGzAE6v740PnQXtUI"
CHAT_ID = "6790526469"

def send_telegram_signal(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    res = requests.post(url, json=payload)
    return res.json()

def analyze_ict_full_suite():
    # 1. Binance Data Retrieval (15m Candles)
    url = "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=15m&limit=200"
    res = requests.get(url).json()
    
    df = pd.DataFrame(res).iloc[:, :6]
    df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)

    # Convert Timestamp to UTC DateTime for Sessions
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    
    # 2. Indicators: 200 EMA & 14 ATR
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()

    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(window=14).mean()

    # 3. Market Sessions High/Low Ranges (UTC Time)
    asian_df = df[(df['datetime'].dt.hour >= 0) & (df['datetime'].dt.hour < 8)]
    london_df = df[(df['datetime'].dt.hour >= 7) & (df['datetime'].dt.hour < 16)]
    ny_df = df[(df['datetime'].dt.hour >= 12) & (df['datetime'].dt.hour < 21)]

    asian_h = asian_df['high'].max() if not asian_df.empty else df['high'].max()
    asian_l = asian_df['low'].min() if not asian_df.empty else df['low'].min()

    london_h = london_df['high'].max() if not london_df.empty else df['high'].max()
    london_l = london_df['low'].min() if not london_df.empty else df['low'].min()

    ny_h = ny_df['high'].max() if not ny_df.empty else df['high'].max()
    ny_l = ny_df['low'].min() if not ny_df.empty else df['low'].min()

    # 4. Swing High/Low & Equilibrium (PD Arrays)
    swing_len = 20
    df['swing_high'] = df['high'].rolling(window=swing_len).max()
    df['swing_low'] = df['low'].rolling(window=swing_len).min()
    df['equilibrium'] = (df['swing_high'] + df['swing_low']) / 2.0

    curr = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]

    price = curr['close']
    ema200 = curr['ema_200']
    eq_level = curr['equilibrium']
    atr = curr['atr']

    in_discount = price < eq_level
    in_premium = price > eq_level

    # 5. FVG & Order Block (OB) Identification
    bull_fvg = curr['low'] > prev2['high'] and prev['close'] > prev2['high']
    bear_fvg = curr['high'] < prev2['low'] and prev['close'] < prev2['low']
    fvg_status = "Bullish FVG 🟢" if bull_fvg else ("Bearish FVG 🔴" if bear_fvg else "None ➖")

    # Order Block: Last opposing candle before an FVG movement
    bull_ob = prev2['low'] if bull_fvg else None
    bear_ob = prev2['high'] if bear_fvg else None
    ob_str = f"${bull_ob:,.2f} (Bullish OB)" if bull_ob else (f"${bear_ob:,.2f} (Bearish OB)" if bear_ob else "None ➖")

    # 6. Session Sweeps & CISD Detection
    recent_low = min(asian_l, london_l, ny_l)
    recent_high = max(asian_h, london_h, ny_h)

    sell_side_sweep = prev['low'] < recent_low
    buy_side_sweep = prev['high'] > recent_high

    is_down_candle = prev['close'] < prev['open']
    is_up_candle = prev['close'] > prev['open']

    bullish_cisd = sell_side_sweep and is_down_candle and (price > max(prev['open'], prev['high']))
    bearish_cisd = buy_side_sweep and is_up_candle and (price < min(prev['open'], prev['low']))

    # 7. Signal Logic with Dynamic Target & SL
    rr_ratio = 2.0
    if price > ema200 and (in_discount or bull_fvg) and bullish_cisd:
        signal = "STRONG BUY (T-Spot ICT) 🟢🚀"
        sl = min(curr['low'], prev['low']) - (1.5 * atr)
        tp = price + ((price - sl) * rr_ratio)
    elif price < ema200 and (in_premium or bear_fvg) and bearish_cisd:
        signal = "STRONG SELL (T-Spot ICT) 🔴📉"
        sl = max(curr['high'], prev['high']) + (1.5 * atr)
        tp = price - ((sl - price) * rr_ratio)
    elif in_discount:
        signal = "NEUTRAL ➖ (Discount Zone - Long Setup Watch)"
        sl = curr['low'] - (1.5 * atr)
        tp = price + ((price - sl) * rr_ratio)
    else:
        signal = "NEUTRAL ➖ (Premium Zone - Short Setup Watch)"
        sl = curr['high'] + (1.5 * atr)
        tp = price - ((sl - price) * rr_ratio)

    # Market Data
    fr_res = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT").json()
    oi_res = requests.get("https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT").json()
    funding_rate = float(fr_res['lastFundingRate']) * 100
    open_interest = float(oi_res['openInterest'])

    return price, signal, eq_level, ema200, funding_rate, open_interest, in_discount, sl, tp, asian_h, asian_l, london_h, london_l, ny_h, ny_l, fvg_status, ob_str, bullish_cisd, bearish_cisd

# ==========================================
# AUTO LOOP ENGINE (Runs continuously every 15 mins)
# ==========================================
print("🚀 ICT Engine Bot is running in continuous Auto-Loop mode...")

while True:
    try:
        price, signal, eq, ema200, fr, oi, in_discount, sl, tp, ah, al, lh, ll, nyh, nyl, fvg, ob, b_cisd, bear_cisd = analyze_ict_full_suite()
        zone_str = "Discount Zone 🟢" if in_discount else "Premium Zone 🔴"
        cisd_str = "Confirmed 🟢" if b_cisd else ("Confirmed 🔴" if bear_cisd else "None ➖")

        msg = (
            f"🎯 *BTC ICT FULL SUITE ENGINE*\n\n"
            f"🚦 *Signal:* {signal}\n"
            f"💰 *Current Price:* ${price:,.2f}\n"
            f"📍 *Zone:* {zone_str}\n\n"
            f"🎯 *Projected Target (TP):* ${tp:,.2f}\n"
            f"🛑 *Projected Stop Loss (SL):* ${sl:,.2f}\n"
            f"⚖️ *Risk to Reward:* 1:2 Ratio\n\n"
            f"📊 *ICT Core Analysis:*\n"
            f"• *Equilibrium (0.5 Fib):* ${eq:,.2f}\n"
            f"• *200 EMA Filter:* ${ema200:,.2f}\n"
            f"• *FVG Status:* {fvg}\n"
            f"• *Order Block (OB):* {ob}\n"
            f"• *CISD Status:* {cisd_str}\n\n"
            f"🌐 *Session Ranges (UTC):*\n"
            f"• *Asian Range:* ${al:,.2f} - ${ah:,.2f}\n"
            f"• *London Range:* ${ll:,.2f} - ${lh:,.2f}\n"
            f"• *NY Range:* ${nyl:,.2f} - ${nyh:,.2f}\n\n"
            f"📈 *Market Data:*\n"
            f"• *Funding Rate:* {fr:.4f}%\n"
            f"• *Open Interest:* {oi:,.2f} BTC"
        )
        
                res = send_telegram_signal(msg)
                  if res.get("ok"):
                print(f"[{time.strftime('%H:%M:%S')}] Signal sent!")
                else:
                print("Telegram Error:", res)

        # Telegram Test Message
                send_telegram_signal("🤖 Bot is active and checking markets!")

               except Exception as e:
                  print("Error occurred:", e)

        #Wait 15 minutes
               time.sleep(900) # Wait 15 minutes