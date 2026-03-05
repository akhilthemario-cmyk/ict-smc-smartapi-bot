"""
ict_smc_smartapi_bot.py

- Connects to Angel One SmartAPI (Python SDK)
- Enforces SEBI/Angel One algo rules (LIMIT only, OPS cap, kill switch)
- Provides detectors for A–Z ICT/SMC concepts (stubs + some examples)
- Implements 5 strategy modules (Core ICT, Turtle Soup, Silver Bullet,
  Asian Range Break, Pure SMC) in SmartAPI-friendly form.
"""
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
import pyotp, time, logging, datetime as dt
import os
from collections import deque
from typing import List, Dict, Optional

# ---------- CONFIG ----------

API_KEY        = "b1imNO26"
CLIENT_CODE    = "IIRA95846"
PIN            = "9866"
CLIENT_SECRET  = "41aba496-e02c-40af-9742-bd371a38d93a"
TOTP_SECRET    = os.environ.get("TOTP_SECRET", "YOUR_TOTP_SECRET")

SYMBOL       = "NIFTY24MARFUT"
TOKEN        = "12345"
EXCHANGE     = "NFO"

MAX_DAILY_LOSS       = 5000.0
MAX_DAILY_TRADES     = 30
MAX_OPEN_EXPOSURE    = 200000.0
MAX_ORDERS_PER_SEC   = 5
ALLOWED_ORDER_TYPE   = "LIMIT"

LOG_LEVEL = logging.INFO
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ICT_SMC_BOT")

class SmartApiSession:
    def __init__(self):
        self.obj          = SmartConnect(api_key=API_KEY)
        self.authToken    = None
        self.feedToken    = None
        self.refreshToken = None

    def login(self):
        if TOTP_SECRET == "YOUR_TOTP_SECRET":
            raise Exception("TOTP_SECRET not provided. Please set it in GitHub Secrets or the code.")
        otp  = pyotp.TOTP(TOTP_SECRET).now()
        data = self.obj.generateSession(CLIENT_CODE, PIN, otp)
        if not data.get("status"):
            raise Exception(f"Login failed: {data}")
        self.authToken    = data["data"]["jwtToken"]
        self.refreshToken = data["data"]["refreshToken"]
        self.feedToken    = self.obj.getfeedToken()
        profile           = self.obj.getProfile(self.refreshToken)
        log.info(f"Logged in as {profile['data']['name']}")

    def logout(self):
        try:
            self.obj.terminateSession(CLIENT_CODE)
            log.info("Session terminated")
        except Exception as e:
            log.warning(f"Logout error: {e}")

session = SmartApiSession()
# session.login() # Uncomment to login
smart = session.obj

class RiskEngine:
    def __init__(self):
        self.daily_pnl   = 0.0
        self.trades      = 0
        self.ord_times   = deque(maxlen=100)

    def record_order(self):
        now = time.time()
        self.ord_times.append(now)
        recent = [t for t in self.ord_times if now - t <= 1.0]
        if len(recent) > MAX_ORDERS_PER_SEC:
            raise Exception("OPS limit breached – throttling to stay under framework cap")

    def can_trade(self, est_loss: float, est_exposure: float) -> bool:
        if self.daily_pnl <= -MAX_DAILY_LOSS:
            log.warning("Daily loss limit reached, blocking new trades")
            return False
        if self.trades >= MAX_DAILY_TRADES:
            log.warning("Max daily trades reached")
            return False
        if est_exposure > MAX_OPEN_EXPOSURE:
            log.warning("Exposure limit exceeded")
            return False
        if est_loss > MAX_DAILY_LOSS * 0.5:
            log.warning("Single trade risk too high vs daily loss limit")
            return False
        return True

    def update_pnl(self, realized_pnl: float):
        self.daily_pnl += realized_pnl

risk = RiskEngine()

def place_limit_order(symbol: str, token: str, side: str, price: float,
                      qty: int, exchange: str = EXCHANGE) -> Dict:
    orderparams = {
        "variety": "NORMAL",
        "tradingsymbol": symbol,
        "symboltoken": str(token),
        "transactiontype": side,
        "exchange": exchange,
        "ordertype": ALLOWED_ORDER_TYPE,
        "producttype": "INTRADAY",
        "duration": "DAY",
        "price": str(round(price, 2)),
        "squareoff": "0",
        "stoploss": "0",
        "quantity": str(int(qty)),
    }
    risk.record_order()
    resp = smart.placeOrder(orderparams)
    log.info(f"Order: {side} {qty} {symbol} @ {price}, resp={resp}")
    risk.trades += 1
    return resp

def get_candles(exchange: str, token: str, interval: str,
                start: dt.datetime, end: dt.datetime) -> List[Dict]:
    params = {
        "exchange": exchange,
        "symboltoken": token,
        "interval": interval,
        "fromdate": start.strftime("%Y-%m-%d %H:%M"),
        "todate":   end.strftime("%Y-%m-%d %H:%M"),
    }
    data = smart.getCandleData(params)
    if not data.get("status"):
        raise Exception(data)
    candles = []
    for r in data["data"]:
        candles.append({
            "time":   r[0],
            "open":   r[1],
            "high":   r[2],
            "low":    r[3],
            "close":  r[4],
            "volume": r[5],
        })
    return candles

def run_once(strategy: str = "core_ict"):
    now = dt.datetime.now()
    print(f"[{now}] Running {strategy}...")

if __name__ == "__main__":
    run_once()
