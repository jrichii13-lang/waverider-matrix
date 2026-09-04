import asyncio
import json
import logging
import datetime
import os
import time
import random
import websockets
from sqlalchemy.orm import Session
from models import init_db, Position
from alpaca.trading.client import TradingClient
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
import config

logger = logging.getLogger(__name__)

# Authenticate both clients properly
trading_client = TradingClient(config.API_KEY, config.SECRET_KEY, paper=config.PAPER_MODE)
data_client = CryptoHistoricalDataClient(config.API_KEY, config.SECRET_KEY)

SessionLocal = init_db()
SETTINGS_FILE = "settings.json"

def get_dynamic_settings():
    defaults = {
        "take_profit_pct": config.TAKE_PROFIT_PCT,
        "stop_loss_pct": config.STOP_LOSS_PCT,
        "trade_stake_pct": config.TRADE_ALLOCATION_PCT
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
                defaults["stop_loss_pct"] = float(data.get("stop_loss_pct", defaults["stop_loss_pct"]))
                defaults["take_profit_pct"] = float(data.get("take_profit_pct", defaults["take_profit_pct"]))
                defaults["trade_stake_pct"] = float(data.get("trade_stake_pct", defaults["trade_stake_pct"]))
        except Exception:
            pass
    return defaults

async def run_crypto_matrix():
    HOT_ASSETS_URL = "wss://stream.binance.us:9443/ws/btcusdt@trade/ethusdt@trade/dogeusdt@trade/solusdt@trade/adausdt@trade/xrpusdt@trade"
    print(f"🪙 [Crypto Core] Connecting to Multi-Asset WebSocket...")
    
    # TTL Cache to prevent hammering Alpaca rate limits
    last_api_call = {}
    
    reconnect_attempts = 0
    while True:
        try:
            async with websockets.connect(HOT_ASSETS_URL, ping_interval=20, ping_timeout=20, open_timeout=30) as websocket:
                reconnect_attempts = 0
                print("✅ [Crypto Core] WebSocket Connected. Matrix Armed.")
                
                while True:
                    raw_message = await websocket.recv()
                    trade_data = json.loads(raw_message)
                    
                    raw_symbol = trade_data['s']  
                    current_price = float(trade_data['p'])
                    trade_volume = float(trade_data['q'])
                    data_symbol = raw_symbol.upper().replace("USDT", "/USD")
                    
                    now = time.time()
                    settings = get_dynamic_settings()
                    
                    # STRICT SCOPING: Reset variables per tick to prevent stale data leaks
                    bars = None
                    latest = None
                    price_change_pct = 0.0
                    
                    # Rate limiting: Max 1 REST call per symbol every 2 seconds
                    if trade_volume > 1.5 and (now - last_api_call.get(data_symbol, 0) > 2.0):
                        last_api_call[data_symbol] = now
                        
                        try:
                            # Offload blocking HTTP calls from the async event loop
                            account = await asyncio.to_thread(trading_client.get_account)
                            
                            req = CryptoBarsRequest(
                                symbol_or_symbols=data_symbol,
                                timeframe=TimeFrame.Minute,
                                start=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=60)
                            )
                            bars = await asyncio.to_thread(data_client.get_crypto_bars, req)
                            
                            if bars is not None and not bars.df.empty:
                                df = bars.df
                                macd_hist = (df['close'].ewm(span=12).mean() - df['close'].ewm(span=26).mean()) - (df['close'].ewm(span=12).mean() - df['close'].ewm(span=26).mean()).ewm(span=9).mean()
                                latest = {"MACD_Hist": float(macd_hist.iloc[-1])}
                                price_change_pct = (current_price - float(df['close'].iloc[-2])) / float(df['close'].iloc[-2])
                        except Exception as e:
                            logger.warning(f"[Crypto API Error for {data_symbol}]: {e}")
                    
                    # Scoped DB session to reduce overhead
                    with SessionLocal() as db:
                        pos = db.query(Position).filter(Position.ticker == raw_symbol, Position.status == "OPEN").first()
                        
                        if pos:
                            pnl_pct = (current_price - float(pos.entry_price)) / float(pos.entry_price)
                            
                            # Utilizing the live stop_loss_pct from settings.json
                            if pnl_pct <= settings["stop_loss_pct"] or pnl_pct >= settings["take_profit_pct"]:
                                logger.info(f"Closing {raw_symbol} at {current_price}. PnL: {pnl_pct:.2%}")
                                pos.status = "CLOSED"
                                pos.closed_at = datetime.datetime.now(datetime.timezone.utc)
                                pos.realized_pnl = pnl_pct
                                db.commit()
                            
                            # Safe flash-profit check relying strictly on current tick data
                            elif latest and price_change_pct > 0.002 and latest.get('MACD_Hist', 0) < -0.05:
                                logger.info(f"Flash profit condition met for {raw_symbol}. Closing position.")
                                pos.status = "CLOSED"
                                pos.closed_at = datetime.datetime.now(datetime.timezone.utc)
                                pos.realized_pnl = pnl_pct
                                db.commit()
                                
        except Exception as e:
            reconnect_attempts += 1
            backoff = min(60, (2 ** reconnect_attempts) + random.uniform(0, 1))
            print(f"⚠ [Crypto System] WebSocket crashed: {e}. Reconnecting in {backoff:.1f}s...")
            await asyncio.sleep(backoff)

async def run_options_matrix():
    print(f"📈 [Options Core] Initializing XSP Volatility Engine...")
    # Insert existing options logic here
    while True:
        await asyncio.sleep(60)

async def main():
    await asyncio.gather(
        run_crypto_matrix(),
        run_options_matrix()
    )

if __name__ == "__main__":
    asyncio.run(main())
