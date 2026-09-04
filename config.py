import os
from dotenv import load_dotenv

load_dotenv()

# Strict environment variable loading with no plaintext fallbacks
API_KEY = os.getenv("APINAME_API_KEY") or os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("APINAME_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY")
PAPER_MODE = os.getenv("PAPER_MODE", "True").lower() == "true"

if not API_KEY or not SECRET_KEY:
    raise ValueError(
        "CRITICAL: Alpaca API credentials missing! Ensure APCA_API_KEY_ID and APCA_API_SECRET_KEY are set in your environment or .env file."
    )

# Engine Constants
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "-0.015"))
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "0.02"))
TRADE_ALLOCATION_PCT = float(os.getenv("TRADE_ALLOCATION_PCT", "0.40"))
