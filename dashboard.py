from flask import Flask, render_template_string, request, jsonify
import json
import os
import config

app = Flask(__name__)

# Dashboard HTML Template with Sliders, Live Stats, and Controls
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Wave Rider Hybrid Control Center</title>
    <meta http-equiv="refresh" content="3">
    <style>
        body { background-color: #0b0f19; color: #00ffcc; font-family: 'Courier New', monospace; padding: 20px; }
        h1 { color: #00ffcc; border-bottom: 2px solid #00ffcc; padding-bottom: 10px; }
        .grid { display: flex; gap: 20px; margin-top: 20px; }
        .card { background: #131a2b; border: 1px solid #1f293d; padding: 20px; border-radius: 8px; flex: 1; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        .card h3 { margin-top: 0; color: #38bdf8; border-bottom: 1px solid #1f293d; padding-bottom: 8px; }
        .metric-val { font-size: 24px; font-weight: bold; color: #ffffff; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 8px; text-align: left; border-bottom: 1px solid #1f293d; font-size: 13px; }
        th { color: #94a3b8; }
        pre { background: #080c14; padding: 15px; border-radius: 5px; color: #00ffcc; overflow-x: auto; border: 1px solid #1f293d; font-size: 12px; max-height: 250px; }
        .control-group { margin-bottom: 15px; }
        label { display: block; color: #94a3b8; margin-bottom: 5px; font-size: 12px; }
        input[type=range] { width: 100%; accent-color: #00ffcc; }
        button { background: #00ffcc; color: #0b0f19; border: none; padding: 8px 15px; font-weight: bold; cursor: pointer; border-radius: 4px; }
        button:hover { background: #38bdf8; }
    </style>
</head>
<body>
    <h1>🌊 WAVE RIDER V38.0 — HYBRID MATRIX CONTROL CENTER</h1>
    
    <div class="grid">
        <div class="card">
            <h3>💰 Hackathon Portfolio Metrics</h3>
            <p>Initial Capital: <span class="metric-val">${{ "%.2f"|format(metrics.initial_capital) }}</span></p>
            <p>Final / Current Value: <span class="metric-val" style="color: #22c55e;">${{ "%.2f"|format(metrics.final_capital) }}</span></p>
            <p>Net Profit / ROI: <span style="color: #22c55e;">${{ "%.2f"|format(metrics.net_profit) }} ({{ metrics.roi_pct }}%)</span></p>
            <p>Win Rate: <b>{{ metrics.win_rate_pct }}%</b> | Max Drawdown: <b>{{ metrics.max_drawdown_pct }}%</b></p>
        </div>

        <div class="card">
            <h3>🎛️ Live Strategy Parameters (Sliders)</h3>
            <form action="/update_params" method="POST">
                <div class="control-group">
                    <label>Allocation Per Trade (%): <span id="alloc_val">{{ config_vals.alloc_pct * 100 }}</span>%</label>
                    <input type="range" name="alloc_pct" min="0.01" max="0.20" step="0.01" value="{{ config_vals.alloc_pct }}" oninput="document.getElementById('alloc_val').innerText = (this.value * 100).toFixed(1)">
                </div>
                <div class="control-group">
                    <label>Base Take Profit (%): <span id="tp_val">{{ config_vals.base_tp_pct * 100 }}</span>%</label>
                    <input type="range" name="base_tp_pct" min="0.01" max="0.50" step="0.01" value="{{ config_vals.base_tp_pct }}" oninput="document.getElementById('tp_val').innerText = (this.value * 100).toFixed(1)">
                </div>
                <button type="submit">Update Engine Parameters</button>
            </form>
        </div>
    </div>

    <div class="card" style="margin-top: 20px;">
        <h3>📜 Live Trade & Matrix Execution Ledger</h3>
        <table>
            <tr><th>Timestamp</th><th>Asset / Contract</th><th>Type</th><th>PnL ($)</th></tr>
            {% for trade in trades %}
            <tr>
                <td>{{ trade.time }}</td>
                <td>{{ trade.sym }}</td>
                <td style="color: #22c55e;">{{ trade.type }}</td>
                <td style="color: {% if trade.pnl >= 0 %}#22c55e{% else %}#ef4444{% endif %};">${{ "%.2f"|format(trade.pnl) }}</td>
            </tr>
            {% else %}
            <tr><td colspan="4" style="color: #94a3b8;">No closed trades recorded in current matrix cycle yet. (Crypto running 24/7, Options waiting for market bell).</td></tr>
            {% endfor %}
        </table>
    </div>
</body>
</html>
"""

@app.route("/")
def index():
    # Load backend JSON ledger if available
    data = {
        "metrics": {
            "initial_capital": config.INITIAL_CAPITAL,
            "final_capital": config.INITIAL_CAPITAL,
            "net_profit": 0.0,
            "roi_pct": 0.0,
            "win_rate_pct": 0.0,
            "max_drawdown_pct": 0.0
        },
        "trade_ledger": []
    }
    if os.path.exists("backtest_results.json"):
        with open("backtest_results.json", "r") as f:
            data = json.load(f)
            
    config_vals = {
        "alloc_pct": config.ALLOC_PCT,
        "base_tp_pct": config.BASE_TP_PCT
    }
    
    return render_template_string(
        DASHBOARD_HTML, 
        metrics=data.get("metrics", {}), 
        trades=data.get("trade_ledger", []),
        config_vals=config_vals
    )

@app.route("/update_params", methods=["POST"])
def update_params():
    try:
        new_alloc = float(request.form.get("alloc_pct"))
        new_tp = float(request.form.get("base_tp_pct"))
        
        # Update config runtime values
        config.ALLOC_PCT = new_alloc
        config.BASE_TP_PCT = new_tp
    except Exception as e:
        print(f"Error updating params: {e}")
        
    return index()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
