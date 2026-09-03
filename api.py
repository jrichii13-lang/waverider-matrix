from fastapi import FastAPI, Depends, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session as SQLAlchemySession
from models import init_db, Position
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
import datetime, json, os, re

app = FastAPI(title="Pro Options Terminal API")
SessionLocal = init_db()

ALPACA_API_KEY = "PKNIOXW4PEG2UD5N2BZFKAPQYO"
ALPACA_SECRET_KEY = "E44ZbqufhP9iUZvSkus3zbSCAesgVX5DavobF7GfzYAb"
trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
data_client = CryptoHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

@app.get("/")
def get_dashboard_ui(): return FileResponse("index.html")

@app.get("/api/chart/history/{ticker}")
def get_chart(ticker: str):
    try:
        sym = f"{ticker}/USD" if "USD" not in ticker else ticker
        req = CryptoBarsRequest(
            symbol_or_symbols=[sym], 
            timeframe=TimeFrame.Minute,
            start=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=180)
        )
        bars = data_client.get_crypto_bars(req)
        if bars.df.empty: return []
        return [{"time": i[1].timestamp(), "open": r['open'], "high": r['high'], "low": r['low'], "close": r['close']} 
                for i, r in bars.df.iterrows()]
    except Exception as e:
        return [] # Return empty gracefully if Alpaca doesn't support the coin

@app.get("/api/positions/active")
def get_active(db: SQLAlchemySession = Depends(get_db)):
    db_positions = db.query(Position).filter(Position.is_open == True).all()
    try: alpaca_positions = trading_client.get_all_positions()
    except: alpaca_positions = []
    
    results = []
    for pos in db_positions:
        target_sym = pos.ticker.replace("USDT", "USD")
        a_pos = next((p for p in alpaca_positions if p.symbol == target_sym), None)
        
        safe_entry = float(pos.entry_price) if pos.entry_price else 0.0
        safe_current = float(a_pos.current_price) if a_pos else safe_entry
        
        results.append({
            "id": pos.id, 
            "ticker": pos.ticker, 
            "entry": safe_entry,
            "current": safe_current,
            "allocated": float(a_pos.market_value) if a_pos else 0.0,
            "pnl": float(a_pos.unrealized_pl) if a_pos else 0.0,
            "pnl_pct": float(a_pos.unrealized_plpc) * 100.0 if a_pos else 0.0
        })
    return results

@app.get("/api/positions/closed")
def get_closed(db: SQLAlchemySession = Depends(get_db)):
    return [{"ticker": p.ticker, 
             "pnl": float(p.realized_pnl) if p.realized_pnl else 0.0, 
             "closed_at": p.closed_at.strftime('%m-%d %H:%M:%S') if p.closed_at else "Unknown"} 
            for p in db.query(Position).filter(Position.is_open == False).order_by(Position.closed_at.desc()).limit(30)]

@app.get("/api/portfolio/stats")
def get_stats(db: SQLAlchemySession = Depends(get_db)):
    try:
        acc = trading_client.get_account()
        total = float(acc.portfolio_value)
        cash = float(acc.buying_power)
        alpaca_positions = trading_client.get_all_positions()
        deployed = sum(float(p.market_value) for p in alpaca_positions)
        pnl = float(acc.equity) - float(acc.last_equity)
    except: 
        total, cash, deployed, pnl = 0.0, 0.0, 0.0, 0.0
        
    closed = db.query(Position).filter(Position.is_open == False).all()
    wins = len([t for t in closed if t.realized_pnl and t.realized_pnl > 0])
    win_rate = round((wins / len(closed) * 100), 1) if closed else 0.0
    
    return {"total": total, "cash": cash, "deployed": deployed, "pnl": pnl, "total_trades": len(closed), "win_rate": win_rate}

@app.post("/api/positions/{id}/close")
def close_pos(id: str, db: SQLAlchemySession = Depends(get_db)):
    pos = db.query(Position).filter(Position.ticker == id, Position.is_open == True).first()
    if pos:
        try:
            sym = pos.ticker.replace("USDT", "USD")
            alpaca_pos = trading_client.get_open_position(sym)
            pos.realized_pnl = float(alpaca_pos.unrealized_pl)
            trading_client.close_position(sym)
        except: pos.realized_pnl = 0.0
        pos.is_open = False
        pos.closed_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()
    return {"status": "success"}

@app.get("/api/settings")
def get_s():
    defaults = {"take_profit_pct": 0.0075, "trade_allocation_pct": 0.02}
    if not os.path.exists("settings.json"): return defaults
    with open("settings.json", "r") as f:
        try: return json.load(f)
        except: return defaults

@app.post("/api/settings")
async def set_s(req: Request):
    data = await req.json()
    with open("settings.json", "w") as f: json.dump(data, f)
    return {"status": "ok"}

@app.get("/api/logs")
def get_logs():
    if not os.path.exists("terminal.log"): return []
    with open("terminal.log", "r", encoding="utf-8") as f:
        ansi = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return [ansi.sub('', line) for line in f.readlines()][-60:]
