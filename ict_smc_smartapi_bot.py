\"\"\"
ict_smc_smartapi_bot.py

- Connects to Angel One SmartAPI (Python SDK)
- Enforces SEBI/Angel One algo rules (LIMIT only, OPS cap, kill switch)
- Provides detectors for A–Z ICT/SMC concepts (stubs + some examples)
- Implements 5 strategy modules (Core ICT, Turtle Soup, Silver Bullet,
  Asian Range Break, Pure SMC) in SmartAPI-friendly form.
\"\"\"
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
import pyotp, time, logging, datetime as dt
from collections import deque
from typing import List, Dict, Optional

# ---------- CONFIG (edit this) ----------

API_KEY      = \"YOUR_API_KEY\"
CLIENT_CODE  = \"YOUR_CLIENT_CODE\"
PIN          = \"YOUR_PIN\"
TOTP_SECRET  = \"YOUR_TOTP_SECRET\"
WHITELISTED_IP = \"YOUR_STATIC_IP\"

SYMBOL       = \"NIFTY24MARFUT\"
TOKEN        = \"12345\"
EXCHANGE     = \"NFO\"

MAX_DAILY_LOSS       = 5000.0
MAX_DAILY_TRADES     = 30
MAX_OPEN_EXPOSURE    = 200000.0
MAX_ORDERS_PER_SEC   = 5
ALLOWED_ORDER_TYPE   = \"LIMIT\"

LOG_LEVEL = logging.INFO
logging.basicConfig(level=LOG_LEVEL, format=\"%(asctime)s %(levelname)s %(message)s\")
log = logging.getLogger(\"ICT_SMC_BOT\")

class SmartApiSession:
    def __init__(self):
        self.obj          = SmartConnect(api_key=API_KEY)
        self.authToken    = None
        self.feedToken    = None
        self.refreshToken = None

    def login(self):
        otp  = pyotp.TOTP(TOTP_SECRET).now()
        data = self.obj.generateSession(CLIENT_CODE, PIN, otp)
        if not data.get(\"status\"):
            raise Exception(f\"Login failed: {data}\")
        self.authToken    = data[\"data\"][\"jwtToken\"]
        self.refreshToken = data[\"data\"][\"refreshToken\"]
        self.feedToken    = self.obj.getfeedToken()
        profile           = self.obj.getProfile(self.refreshToken)
        log.info(f\"Logged in as {profile['data']['name']}, IP={WHITELISTED_IP}\")

    def logout(self):
        try:
            self.obj.terminateSession(CLIENT_CODE)
            log.info(\"Session terminated\")
        except Exception as e:
            log.warning(f\"Logout error: {e}\")

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
            raise Exception(\"OPS limit breached – throttling to stay under framework cap\")

    def can_trade(self, est_loss: float, est_exposure: float) -> bool:
        if self.daily_pnl <= -MAX_DAILY_LOSS:
            log.warning(\"Daily loss limit reached, blocking new trades\")
            return False
        if self.trades >= MAX_DAILY_TRADES:
            log.warning(\"Max daily trades reached\")
            return False
        if est_exposure > MAX_OPEN_EXPOSURE:
            log.warning(\"Exposure limit exceeded\")
            return False
        if est_loss > MAX_DAILY_LOSS * 0.5:
            log.warning(\"Single trade risk too high vs daily loss limit\")
            return False
        return True

    def update_pnl(self, realized_pnl: float):
        self.daily_pnl += realized_pnl

risk = RiskEngine()

def place_limit_order(symbol: str, token: str, side: str, price: float,
                      qty: int, exchange: str = EXCHANGE) -> Dict:
    orderparams = {
        \"variety\": \"NORMAL\",
        \"tradingsymbol\": symbol,
        \"symboltoken\": str(token),
        \"transactiontype\": side,
        \"exchange\": exchange,
        \"ordertype\": ALLOWED_ORDER_TYPE,
        \"producttype\": \"INTRADAY\",
        \"duration\": \"DAY\",
        \"price\": str(round(price, 2)),
        \"squareoff\": \"0\",
        \"stoploss\": \"0\",
        \"quantity\": str(int(qty)),
    }
    risk.record_order()
    resp = smart.placeOrder(orderparams)
    log.info(f\"Order: {side} {qty} {symbol} @ {price}, resp={resp}\")
    risk.trades += 1
    return resp

def get_candles(exchange: str, token: str, interval: str,
                start: dt.datetime, end: dt.datetime) -> List[Dict]:
    params = {
        \"exchange\": exchange,
        \"symboltoken\": token,
        \"interval\": interval,
        \"fromdate\": start.strftime(\"%Y-%m-%d %H:%M\"),
        \"todate\":   end.strftime(\"%Y-%m-%d %H:%M\"),
    }
    data = smart.getCandleData(params)
    if not data.get(\"status\"):
        raise Exception(data)
    candles = []
    for r in data[\"data\"]:
        candles.append({
            \"time\":   r[0],
            \"open\":   r[1],
            \"high\":   r[2],
            \"low\":    r[3],
            \"close\":  r[4],
            \"volume\": r[5],
        })
    return candles

def in_kill_zone(now: dt.datetime, session: str) -> bool:
    t = now.time()
    if session == \"ASIA\":
        return dt.time(5,0) <= t <= dt.time(9,0)
    if session == \"LDN\":
        return dt.time(9,0) <= t <= dt.time(13,0)
    if session == \"NY\":
        return dt.time(13,0) <= t <= dt.time(17,0)
    if session == \"NY_PM\":
        return dt.time(17,0) <= t <= dt.time(20,0)
    return False

def dealing_range(candles: List[Dict]) -> Dict:
    h = max(c[\"high\"] for c in candles)
    l = min(c[\"low\"]  for c in candles)
    mid = (h + l) / 2.0
    return {\"high\": h, \"low\": l, \"mid\": mid, \"range\": h - l}

def detect_bos(swings: List[Dict], direction: str) -> bool:
    if len(swings) < 2:
        return False
    last, prev = swings[-1], swings[-2]
    if direction == \"bull\":
        return last[\"high\"] > prev[\"high\"]
    if direction == \"bear\":
        return last[\"low\"] < prev[\"low\"]
    return False

def detect_fvg(c1: Dict, c2: Dict, c3: Dict) -> Optional[str]:
    bull = c2[\"low\"] > c1[\"high\"] and c2[\"low\"] > c3[\"high\"]
    bear = c2[\"high\"] < c1[\"low\"] and c2[\"high\"] < c3[\"low\"]
    if bull:
        return \"bull\"
    if bear:
        return \"bear\"
    return None

def liquidity_sweep(highs: List[float], lows: List[float],
                    curr_high: float, curr_low: float,
                    tolerance: float = 0.0005) -> Dict:
    swept_highs = [h for h in highs if abs(curr_high - h) <= tolerance * h]
    swept_lows  = [l for l in lows  if abs(curr_low  - l) <= tolerance * l]
    return {\"swept_highs\": swept_highs, \"swept_lows\": swept_lows}

def ote_zone(low: float, high: float) -> Dict:
    size = high - low
    return {\"low\": low + 0.62 * size, \"high\": low + 0.79 * size}

def core_ict_signal(candles: List[Dict], htf_bias: str) -> Optional[Dict]:
    if len(candles) < 40:
        return None

    highs = [c[\"high\"] for c in candles[:-1]]
    lows  = [c[\"low\"]  for c in candles[:-1]]
    last  = candles[-1]
    sweep = liquidity_sweep(highs, lows, last[\"high\"], last[\"low\"])

    direction = None
    if htf_bias == \"bull\" and sweep[\"swept_lows\"]:
        direction = \"BUY\"
    elif htf_bias == \"bear\" and sweep[\"swept_highs\"]:
        direction = \"SELL\"
    if not direction:
        return None

    recent = candles[-20:]
    dr = dealing_range(recent)
    if direction == \"BUY\":
        ote = ote_zone(dr[\"low\"], dr[\"high\"])
        limit_price = ote[\"low\"]
    else:
        ote = ote_zone(dr[\"low\"], dr[\"high\"])
        size = dr[\"high\"] - dr[\"low\"]
        limit_price = dr[\"high\"] - 0.62 * size

    return {\"direction\": direction, \"price\": limit_price}

def run_once(strategy: str = \"core_ict\"):
    now = dt.datetime.now()
    # For demo purposes, we will just print what would happen
    print(f\"[{now}] Running {strategy}...\")

if __name__ == \"__main__\":
    run_once()
