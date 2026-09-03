import subprocess
import time
import sys
import os

print("🚀 Booting up the Pro Options Terminal...")

try:
    current_folder = os.path.dirname(os.path.abspath(__file__))
    os.chdir(current_folder)

    print("-> Igniting API Server...")
    api_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api:app", "--port", "8000", "--log-level", "warning"]
    )

    print("-> Connecting to the Live Market Matrix...")
    engine_process = subprocess.Popen([sys.executable, "live_engine.py"])

    print("-> Warming up the engines...")
    time.sleep(5)

    print("-> 🌐 Engines are running! The auto-launcher has been disabled.")
    print("-> 🔗 Please open your web browser manually and navigate to: http://127.0.0.1:8000")

    print("\n✅ System is ONLINE. Press CTRL+C here to safely shut everything down.")
    
    api_process.wait()
    engine_process.wait()

except KeyboardInterrupt:
    print("\n🛑 Shutting down all trading systems...")
    api_process.terminate()
    engine_process.terminate()
    print("System safely offline. See you next time!")
