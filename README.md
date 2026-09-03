# Dual-Core WaveRider Matrix

An autonomous, multi-asset trading agent built for the Alpaca AI Trading Agents Hackathon. The WaveRider Matrix operates two simultaneous engines—a high-frequency Crypto Core and an Index Options Core—governed by strict, deterministic risk gates.

## ⚙️ Core Architecture
* **Alpaca Trading API:** Automated order execution, position sizing, and portfolio monitoring.
* **Alpaca Market Data API:** Real-time WebSocket streaming for zero-latency momentum detection.
* **Dual-Core Processing:** Independent asynchronous loops managing crypto momentum trades and cash-settled index options (XSP).

## 🛡️ Deterministic Risk Guardrails
1. **30-Minute Anti-Revenge Cooldown:** Prevents algorithmic overtrading.
2. **Flash Dump Ejection Protocol:** Hardcoded 5% crypto stop-loss.
3. **Flash Profit Evasion:** MACD histogram monitoring for early profit locking.
4. **Assignment-Proof Options:** Strategy specifically targets XSP cash-settled index options to eliminate early-assignment risks.

## 🚀 Setup & Execution
1. Clone the repository.
2. Install requirements: pip install -r requirements.txt
3. Configure your Alpaca Paper API keys in a .env file (ensure this is added to .gitignore).
4. Boot the matrix: python start.py
