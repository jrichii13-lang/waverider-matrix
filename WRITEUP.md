**Project Title:** Dual-Core WaveRider Matrix: Autonomous Options & Crypto Agent
**Account ID:** PA3FQ6CGEU2V

**I. AI Logic & Strategy Architecture**
The Dual-Core WaveRider Matrix is a fully autonomous trading agent designed to execute simultaneous, non-correlated strategies across both equities (Index Options) and cryptocurrencies. Instead of relying on a single large language model to guess market direction, the agent utilizes a deterministic technical engine analyzing real-time WebSocket data for momentum acceleration. The Crypto Core detects high-frequency momentum bursts using RSI and MACD histograms. The Options Core focuses strictly on XSP, scanning real-time options chains to select contracts specifically targeting a delta range of 0.40 to 0.65 with an implied volatility under 60%.

**II. Hard-Coded Risk Gates & Infrastructure**
To prevent catastrophic drawdowns and emotional execution loops, the agent is governed by strict, deterministic mathematical guardrails that completely override entry signals:
* **Anti-Revenge Cooldown Timer:** A 30-minute system-wide lockout is triggered immediately after any closed position to prevent rapid-fire revenge trading.
* **30% Dynamic Stop-Loss (Options):** Options positions are given a wide 30% runway to survive intraday chop.
* **5% Flash Dump Ejection (Crypto):** A specialized evasion protocol that instantly liquidates crypto assets if a sudden 5% drop is detected.
* **Flash Profit Evasion:** The agent actively monitors the MACD histogram of open crypto positions and automatically locks in early profits the millisecond momentum begins to decay.

**III. Alpaca Infrastructure Implementation**
The system is built natively on Alpaca's Trading API and Market Data API. Real-time data is ingested via asynchronous WebSocket streams to maintain a zero-polling latency edge. To eliminate the risk of physical share assignment and early exercise paths entirely, the Options Core is engineered to trade XSP cash-settled index options, utilizing Alpaca's paper trading environment to execute, monitor, and liquidate positions autonomously with zero human intervention.
