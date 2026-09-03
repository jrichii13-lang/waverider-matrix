import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import json
import config
from alpaca.data.historical import OptionHistoricalDataClient
from alpaca.data.requests import OptionBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOptionContractsRequest

C_BLUE = "\033[94m"
C_GREEN = "\033[92m"
C_RED = "\033[91m"
C_RESET = "\033[0m"

print(f"{C_BLUE}🌊 Booting Wave Rider v38.0 OPTIONS Simulator (Hackathon Edition)...{C_RESET}")

# Initialize Clients
trading_client = TradingClient(config.API_KEY, config.SECRET_KEY, paper=config.PAPER_MODE)
option_data_client = OptionHistoricalDataClient(config.API_KEY, config.SECRET_KEY)

print("📡 Targeting underlying asset: XSP")

# Use timezone-aware UTC datetime
future_date = (datetime.now(timezone.utc) + timedelta(days=7)).date()

contract_req = GetOptionContractsRequest(
    underlying_symbols=["XSP"],
    status="active",
    type="call",
    expiration_date_gte=str(future_date), 
    limit=10  # Bumped to 10 to ensure we find contracts with high volume
)

print("🔍 Scanning Alpaca Master Options Chain for active XSP contracts...")
try:
    options_chain = trading_client.get_option_contracts(contract_req)
    contract_symbols = [contract.symbol for contract in options_chain.option_contracts]
    print(f"🎯 Locked onto {len(contract_symbols)} active XSP contracts: {contract_symbols}")
except Exception as e:
    print(f"{C_RED}Contract Fetch Error. Verify your API keys in config.py: {e}{C_RESET}")
    exit()

DAYS_TO_TEST = 5 
start_time = datetime.now(timezone.utc) - timedelta(days=DAYS_TO_TEST)

print(f"📡 Fetching {DAYS_TO_TEST} days of premium data...")
bars_req = OptionBarsRequest(
    symbol_or_symbols=contract_symbols,
    timeframe=TimeFrame.Minute,
    start=start_time
)

try:
    bars = option_data_client.get_option_bars(bars_req).df
except Exception as e:
    print(f"{C_RED}Data Fetch Error: {e}{C_RESET}")
    exit()

print("⚙️ Crunching DSP Mathematics...")
data_dict = {}
for sym in contract_symbols:
    if sym in bars.index:
        df = bars.loc[sym].copy()
        
        # Data Armor: Skip if there isn't enough data to calculate a 20-period Bollinger Band
        if df.empty or len(df) < config.BB_PERIOD:
            continue
            
        df['SMA_20'] = df['close'].rolling(window=config.BB_PERIOD).mean()
        delta = df['close'].diff()
        gain = delta.clip(lower=0).ewm(alpha=1/config.RSI_PERIOD, adjust=False).mean()
        loss = -1 * delta.clip(upper=0).ewm(alpha=1/config.RSI_PERIOD, adjust=False).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        rsi_min = df['RSI'].rolling(config.RSI_PERIOD).min()
        rsi_max = df['RSI'].rolling(config.RSI_PERIOD).max()
        df['StochRSI'] = (df['RSI'] - rsi_min) / (rsi_max - rsi_min + 1e-8)
        
        df['BB_mid'] = df['close'].rolling(window=config.BB_PERIOD).mean()
        df['BB_std'] = df['close'].rolling(window=config.BB_PERIOD).std()
        df['BB_upper'] = df['BB_mid'] + (df['BB_std'] * 2)
        df['BB_lower'] = df['BB_mid'] - (df['BB_std'] * 2)
        df['BB_pctB'] = (df['close'] - df['BB_lower']) / (df['BB_upper'] - df['BB_lower'] + 1e-8)
        
        df_clean = df.dropna()
        if not df_clean.empty:
            data_dict[sym] = df_clean

# Data Armor: Prevent crash if ALL contracts are empty
if not data_dict:
    print(f"{C_RED}⚠️ WARNING: No valid historical data found. The contracts pulled had zero volume over the last 5 days.{C_RESET}")
    print(f"{C_RED}Please run the test again during live market hours (9:30 AM - 4:00 PM ET).{C_RESET}")
    exit()

cash = config.INITIAL_CAPITAL
positions = {}
trade_history = []
peak_portfolio = config.INITIAL_CAPITAL
max_drawdown = 0.0

index_sets = [set(data_dict[s].index) for s in data_dict]
master_index = sorted(list(set.union(*index_sets)))

for current_time in master_index:
    for sym in list(positions.keys()):
        if current_time in data_dict[sym].index:
            current_price = float(data_dict[sym].loc[current_time, 'close'])
            pos = positions[sym]
            pnl_pct = (current_price - pos['avg_price']) / pos['avg_price']
            
            if pnl_pct >= config.BASE_TP_PCT:
                profit_dollars = (pos['qty'] * current_price) - pos['invested']
                cash += (pos['qty'] * current_price)
                trade_history.append({'time': str(current_time), 'sym': sym, 'pnl': profit_dollars, 'type': 'WIN'})
                del positions[sym]
            
            elif pnl_pct <= config.RECOVERY_DROP_PCT and pos['dca_tier'] < 3:
                current_stoch = float(data_dict[sym].loc[current_time, 'StochRSI'])
                if current_stoch <= config.STOCH_LIMIT:
                    multiplier = 2 ** pos['dca_tier']
                    micro_stake = (config.INITIAL_CAPITAL * (config.ALLOC_PCT * 0.5)) * multiplier
                    if cash >= micro_stake:
                        qty_to_buy = micro_stake / current_price
                        pos['invested'] += micro_stake
                        pos['qty'] += qty_to_buy
                        pos['avg_price'] = pos['invested'] / pos['qty']
                        pos['dca_tier'] += 1
                        cash -= micro_stake

    if len(positions) < config.MAX_CONCURRENT:
        for sym in data_dict.keys():
            if sym in positions: continue
            if current_time in data_dict[sym].index:
                row = data_dict[sym].loc[current_time]
                is_wave_trough = float(row['StochRSI']) < config.STOCH_LIMIT and float(row['BB_pctB']) < config.BB_PCT_LIMIT
                
                if is_wave_trough:
                    stake = config.INITIAL_CAPITAL * config.ALLOC_PCT
                    if cash >= stake:
                        qty = stake / float(row['close'])
                        positions[sym] = {'qty': qty, 'avg_price': float(row['close']), 'invested': stake, 'dca_tier': 0}
                        cash -= stake

    current_portfolio_value = cash + sum([pos['qty'] * float(data_dict[sym].loc[current_time, 'close']) for sym, pos in positions.items() if current_time in data_dict[sym].index])
    if current_portfolio_value > peak_portfolio:
        peak_portfolio = current_portfolio_value
    drawdown = (peak_portfolio - current_portfolio_value) / peak_portfolio
    if drawdown > max_drawdown:
        max_drawdown = drawdown

final_portfolio_value = cash + sum([pos['invested'] for sym, pos in positions.items()])
total_trades = len(trade_history)
winning_trades = len([t for t in trade_history if t['pnl'] > 0])
win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
net_profit = final_portfolio_value - config.INITIAL_CAPITAL
roi_pct = (net_profit / config.INITIAL_CAPITAL) * 100

# JSON Export Matrix
json_output = {
    "hackathon_metadata": {
        "engine": "Wave Rider v38.0",
        "asset_class": "Options",
        "underlying": "XSP",
        "sim_days": DAYS_TO_TEST
    },
    "metrics": {
        "initial_capital": config.INITIAL_CAPITAL,
        "final_capital": round(final_portfolio_value, 2),
        "net_profit": round(net_profit, 2),
        "roi_pct": round(roi_pct, 2),
        "win_rate_pct": round(win_rate, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "total_trades_closed": total_trades
    },
    "trade_ledger": trade_history
}

with open("backtest_results.json", "w") as outfile:
    json.dump(json_output, outfile, indent=4)

print(f"{C_BLUE}========================================={C_RESET}")
print(f"📊 {C_GREEN}OPTIONS SIMULATION RESULTS (5 DAYS){C_RESET}")
print(f"{C_BLUE}========================================={C_RESET}")
print(f"Final Capital   : ${final_portfolio_value:,.2f}")
print(f"Net Profit      : ${net_profit:,.2f} ({roi_pct:.2f}%)")
print(f"Total Trades    : {total_trades}")
print(f"Win Rate        : {win_rate:.1f}%")
print(f"Max Drawdown    : {max_drawdown * 100:.2f}%")
print(f"{C_BLUE}========================================={C_RESET}")
print(f"💾 {C_GREEN}Full trade ledger saved to: backtest_results.json{C_RESET}")
