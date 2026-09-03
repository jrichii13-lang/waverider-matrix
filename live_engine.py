import asyncio
import json
import websockets
import os
import builtins
import pandas as pd
import sys
import traceback
from datetime import datetime, timezone, timedelta
from models import init_db, Position, Strategy, ExecutionMode

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOptionContractsRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import CryptoHistoricalDataClient, OptionHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, OptionSnapshotRequest
from alpaca.data.timeframe import TimeFrame

# --- ANSI COLORS ---
C_BLUE = "\033[94m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_PURPLE = "\033[95m"
C_RESET = "\033[0m"

def custom_print(*args, **kwargs):
    local_time = datetime.now().strftime('%H:%M:%S')
    msg = " ".join(map(str, args))
    builtins.print(f"[{local_time}] {msg}", **kwargs)  
    with open("terminal.log", "a", encoding="utf-8") as f:
        f.write(f"[{local_time}] {msg}\n")
print = custom_print  

# ==========================================
# MASTER CLIENTS & KEYS
# ==========================================
import config
ALPACA_API_KEY = config.API_KEY
ALPACA_SECRET_KEY = config.SECRET_KEY

Session = init_db()
data_client = CryptoHistoricalDataClient()
option_data_client = OptionHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)

STOP_LOSS_PCT = -0.015    
VOLUME_THRESHOLD = 0.5   

# --- CAPITAL PARTITIONING ---
CRYPTO_MAX_PORTFOLIO_PCT = 0.50  
OPTIONS_MAX_PORTFOLIO_PCT = 0.50  

def get_dynamic_settings():
    defaults = {"take_profit_pct": 0.0075, "trade_allocation_pct": 0.02}
    if not os.path.exists("settings.json"): return defaults
    with open("settings.json", "r") as f:
        try: return json.load(f)
        except: return defaults

def check_strategy_budget(session, strategy_name, max_pct, current_portfolio_value):
    strat = session.query(Strategy).filter(Strategy.name == strategy_name).first()
    if not strat:
        strat = Strategy(name=strategy_name, execution_mode=ExecutionMode.FULLY_AUTO)
        session.add(strat)
        session.commit()
        return True, strat.id

    open_positions = session.query(Position).filter(Position.strategy_id == strat.id, Position.is_open == True).all()
    deployed_capital = 0.0
    for pos in open_positions:
        try:
            alpaca_pos = trading_client.get_open_position(pos.ticker.replace("USDT", "USD"))
            deployed_capital += float(alpaca_pos.market_value)
        except: pass

    max_budget = current_portfolio_value * max_pct
    has_funds = deployed_capital < max_budget
    return has_funds, strat.id

def sync_with_broker():
    session = Session()
    try:
        live_positions = trading_client.get_all_positions()
        live_symbols = [p.symbol for p in live_positions]
        open_db_pos = session.query(Position).filter(Position.is_open == True).all()
        for pos in open_db_pos:
            alpaca_sym = pos.ticker.replace("USDT", "USD")
            if alpaca_sym not in live_symbols:
                pos.is_open = False
                pos.closed_at = datetime.now(timezone.utc)
        session.commit()
    except Exception as e: print(f"⚠ [Sync Error] Broker reconciliation failed: {e}")
    finally: session.close()

# ==========================================
# CORE 1: OPTIONS MATRIX  
# ==========================================
async def run_options_matrix():
    print(f"📈 [Options Core] Initializing XSP Volatility Engine...")
    while True:
        try:
            clock = trading_client.get_clock()
            if not clock.is_open:
                await asyncio.sleep(60)
                continue

            session = Session()
            account = trading_client.get_account()
            total_portfolio = float(account.portfolio_value)
            has_funds, strat_id = check_strategy_budget(session, "Options_Matrix", OPTIONS_MAX_PORTFOLIO_PCT, total_portfolio)
            settings = get_dynamic_settings()
            
            OPT_TAKE_PROFIT = 0.30
            OPT_STOP_LOSS = -0.30

            # 1. Manage Active Option Positions
            open_opt_positions = session.query(Position).filter(Position.strategy_id == strat_id, Position.is_open == True).all()
            for pos in open_opt_positions:
                try:
                    alpaca_pos = trading_client.get_open_position(pos.ticker)
                    current_price = float(alpaca_pos.current_price)
                    price_change_pct = float(alpaca_pos.unrealized_plpc)
                    
                    if price_change_pct >= OPT_TAKE_PROFIT or price_change_pct <= OPT_STOP_LOSS:
                        exact_sell_qty = float(alpaca_pos.qty)
                        trading_client.submit_order(MarketOrderRequest(symbol=pos.ticker, qty=exact_sell_qty, side=OrderSide.SELL, time_in_force=TimeInForce.DAY))
                        
                        pos.is_open = False
                        pos.closed_at = datetime.now(timezone.utc)
                        pos.realized_pnl = float(alpaca_pos.unrealized_pl)
                        session.commit()
                        
                        status_color = C_GREEN if pos.realized_pnl > 0 else C_RED
                        print(f"   🎫 {status_color}[OPTIONS CLOSED]{C_RESET} PnL: ${pos.realized_pnl:.2f} on {pos.ticker}")
                except Exception as e:
                    if "not found" in str(e).lower():
                        pos.is_open = False
                        pos.closed_at = datetime.now(timezone.utc)
                        session.commit()

            # 2. Scan and Buy New Contracts
            if has_funds and len(open_opt_positions) < 3:
                future_date = (datetime.now(timezone.utc) + timedelta(days=7)).date()
                contract_req = GetOptionContractsRequest(
                    underlying_symbols=["XSP"],
                    status="active",
                    type="call",
                    expiration_date_gte=str(future_date),
                    limit=100
                )
                chain = trading_client.get_option_contracts(contract_req)
                contracts = [c.symbol for c in chain.option_contracts]

                for sym in contracts:
                    if session.query(Position).filter(Position.ticker == sym, Position.is_open == True).first():
                        continue

                    snap_req = OptionSnapshotRequest(symbol_or_symbols=[sym])
                    snapshot = option_data_client.get_option_snapshot(snap_req).get(sym)
                    
                    if not snapshot or not snapshot.greeks or snapshot.greeks.delta is None or not snapshot.latest_quote:
                        continue
                        
                    delta = float(snapshot.greeks.delta)
                    iv = float(snapshot.implied_volatility) if snapshot.implied_volatility else 0.0
                    ask_price = float(snapshot.latest_quote.ask_price)
                    
                    # 30-Minute Anti-Revenge Cooldown for Options
                    recent_opt_close = session.query(Position).filter(Position.strategy_id == strat_id, Position.is_open == False).order_by(Position.closed_at.desc()).first()
                    opt_cooled_down = True
                    if recent_opt_close and recent_opt_close.closed_at:
                        if (datetime.now(timezone.utc).replace(tzinfo=None) - recent_opt_close.closed_at.replace(tzinfo=None)).total_seconds() < 1800:
                            opt_cooled_down = False

                    if opt_cooled_down and 0.40 <= delta <= 0.65 and iv < 0.60 and ask_price > 0:
                        qty = 1 
                        cost = ask_price * 100 * qty
                        
                        try:
                            trading_client.submit_order(MarketOrderRequest(symbol=sym, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.DAY))
                            session.add(Position(strategy_id=strat_id, ticker=sym, is_open=True, entry_price=ask_price))
                            session.commit()
                            print(f"   🎯 {C_PURPLE}[OPTIONS BOUGHT]{C_RESET} {sym} (Delta: {delta:.2f}) | Cost: ${cost:.2f}")
                            break 
                        except Exception as e:
                            print(f"   ❌ [OPT BUY ERROR] {e}")
                
            session.close()
        except Exception as e:
            print(f"⚠ [OPTIONS ERROR] {e}")
            
        await asyncio.sleep(45)

# ==========================================
# CORE 2: CRYPTO MATRIX
# ==========================================
async def run_crypto_matrix():
    HOT_ASSETS_URL = "wss://stream.binance.us:9443/ws/btcusdt@trade/ethusdt@trade/dogeusdt@trade/solusdt@trade/adausdt@trade/xrpusdt@trade"
    print(f"🪙 [Crypto Core] Connecting to Multi-Asset WebSocket...")
    
    while True:
        try:
            async with websockets.connect(HOT_ASSETS_URL, ping_interval=None, ping_timeout=None) as websocket:
                while True:
                    raw_message = await websocket.recv()
                    trade_data = json.loads(raw_message)
                    
                    raw_symbol = trade_data['s']  
                    color_sym = f"{C_BLUE}{raw_symbol}{C_RESET}"
                    current_price = float(trade_data['p'])
                    trade_volume = float(trade_data['q'])
                    
                    # Splitting symbols cleanly: data needs the slash, trading rejects the slash
                    data_symbol = raw_symbol.upper().replace("USDT", "/USD")
                    trade_symbol = raw_symbol.upper().replace("USDT", "USD")
                    
                    session = Session()
                    settings = get_dynamic_settings()
                    TAKE_PROFIT_PCT = settings.get("take_profit_pct", 0.0075)
                    TRADE_ALLOCATION_PCT = settings.get("trade_allocation_pct", 0.02)
                    
                    account = trading_client.get_account()
                    total_portfolio = float(account.portfolio_value)
                    
                    has_funds, strat_id = check_strategy_budget(session, "Crypto_Matrix", CRYPTO_MAX_PORTFOLIO_PCT, total_portfolio)
                    
                    if trade_volume > VOLUME_THRESHOLD and has_funds:  
                        req = CryptoBarsRequest(symbol_or_symbols=[data_symbol], timeframe=TimeFrame.Minute,
                            start=datetime.now(timezone.utc) - timedelta(minutes=100))
                        bars = data_client.get_crypto_bars(req).df
                        
                        if not bars.empty:
                            df = bars.copy()
                            df['SMA_50'] = df['close'].rolling(window=50).mean()
                            delta = df['close'].diff()
                            gain = delta.clip(lower=0).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
                            loss = -1 * delta.clip(upper=0).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
                            rs = gain / loss
                            df['RSI'] = 100 - (100 / (1 + rs))
                            
                            macd_line = df['close'].ewm(span=12, adjust=False).mean() - df['close'].ewm(span=26, adjust=False).mean()
                            df['MACD_Hist'] = macd_line - macd_line.ewm(span=9, adjust=False).mean()
                            latest = df.iloc[-1]
                            
                            is_uptrend = current_price > latest['SMA_50']
                            is_healthy_momentum = 55 < latest['RSI'] < 75  
                            is_accelerating = latest['MACD_Hist'] > 0
                            
                            already_open = session.query(Position).filter(Position.ticker == raw_symbol, Position.is_open == True).first()
                           
                            # 30-Minute Anti-Revenge Cooldown Check
                            recent_close = session.query(Position).filter(Position.ticker == raw_symbol, Position.is_open == False).order_by(Position.closed_at.desc()).first()
                            is_cooled_down = True
                            if recent_close and recent_close.closed_at:
                                if (datetime.now(timezone.utc).replace(tzinfo=None) - recent_close.closed_at.replace(tzinfo=None)).total_seconds() < 1800:
                                    is_cooled_down = False


                            if not already_open and is_cooled_down and is_uptrend and is_healthy_momentum and is_accelerating:
                                dynamic_stake = float(account.buying_power) * TRADE_ALLOCATION_PCT
                                trade_qty = round(dynamic_stake / current_price, 4)
                                
                                if dynamic_stake >= 5.0:
                                    try:
                                        trading_client.submit_order(MarketOrderRequest(symbol=trade_symbol, qty=trade_qty, side=OrderSide.BUY, time_in_force=TimeInForce.GTC))
                                        session.add(Position(strategy_id=strat_id, ticker=raw_symbol, is_open=True, entry_price=current_price))
                                        session.commit()
                                        print(f"   🏦 [CRYPTO BUY] Filled {trade_qty} {f'{C_GREEN}{raw_symbol}{C_RESET}'} (${dynamic_stake:,.2f})")
                                    except Exception as e: print(f"   ❌ [BUY ERROR] {e}")

                    # --- CRYPTO SELL LOGIC ---
                    open_positions = session.query(Position).filter(Position.ticker == raw_symbol, Position.is_open == True).all()
                    for pos in open_positions:
                        if not pos.entry_price: continue
                        price_change_pct = (current_price - pos.entry_price) / pos.entry_price
                        
                        dump_triggered = price_change_pct <= -0.05  
                        tp_triggered = price_change_pct >= TAKE_PROFIT_PCT
                        sl_triggered = price_change_pct <= STOP_LOSS_PCT
                        
                        flash_profit = False
                        if price_change_pct > 0.002 and 'bars' in locals() and hasattr(bars, 'empty') and not bars.empty and 'latest' in locals() and latest['MACD_Hist'] < -0.05:
                            flash_profit = True
                        
                        if tp_triggered or sl_triggered or dump_triggered or flash_profit:
                            try:
                                alpaca_pos = trading_client.get_open_position(trade_symbol)
                                exact_sell_qty = float(alpaca_pos.qty)
                                trading_client.submit_order(MarketOrderRequest(symbol=trade_symbol, qty=exact_sell_qty, side=OrderSide.SELL, time_in_force=TimeInForce.GTC))
                                
                                pos.is_open = False
                                pos.closed_at = datetime.now(timezone.utc)
                                pos.realized_pnl = round((current_price - pos.entry_price) * exact_sell_qty, 2)
                                session.commit()
                                
                                if tp_triggered:
                                    print(f"   🤑 [TAKE PROFIT] +${pos.realized_pnl} on {color_sym}")
                                elif flash_profit:
                                    print(f"   ⚡ [FLASH PROFIT] Evaded crash, locked +${pos.realized_pnl} on {color_sym}")
                                elif dump_triggered and not sl_triggered:
                                    print(f"   ⚠ [FLASH DUMP] Ejected {color_sym} early: -${abs(pos.realized_pnl)}")
                                else:
                                    print(f"   🛡 [STOP LOSS] -${abs(pos.realized_pnl)} on {color_sym}")
                            except Exception as e:
                                if "not found" in str(e).lower():
                                    pos.is_open = False
                                    pos.closed_at = datetime.now(timezone.utc)
                                    pos.realized_pnl = 0.0
                                    session.commit()
                                else:
                                    print(f"   ❌ [SELL ERROR] {e}")
                    session.close()

        except Exception as e:
            print(f"⚠ [Crypto System] Crash Detected: {e}. Reconnecting...")
            await asyncio.sleep(5)

# ==========================================
# MASTER ORCHESTRATOR
# ==========================================
async def background_sync_loop():
    print("🔄 [Sync Engine] Background reconciliation loop armed.")
    while True:
        await asyncio.sleep(180)
        sync_with_broker()

async def main():
    print(f"🌐 Booting Dual-Core Wave Rider Matrix...")
    sync_with_broker()
    await asyncio.gather(
        run_crypto_matrix(),
        run_options_matrix(),
        background_sync_loop()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"🛑 [FATAL SYSTEM CRASH] Engine halted!")
        print(error_details)
        
        with open("error.log", "a", encoding="utf-8") as f:
            f.write(f"\n--- CRASH @ {datetime.now()} ---\n{error_details}\n")
            
        with open("terminal.log", "a", encoding="utf-8") as f:
            f.write(f"🛑 [FATAL SYSTEM ERROR] Check error.log!\n{error_details}\n")
            
        sys.exit(1)
