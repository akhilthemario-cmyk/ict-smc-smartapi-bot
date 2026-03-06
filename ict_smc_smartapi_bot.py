import os, pyotp, logging, requests, time
from SmartApi import SmartConnect
from datetime import datetime as dt, timedelta

# ---------- CONFIG ----------
API_KEY = os.environ.get("API_KEY", "")
CLIENT_CODE = os.environ.get("CLIENT_CODE", "")
PIN = os.environ.get("PIN", "")
TOTP_SECRET = os.environ.get("TOTP_SECRET", "")
CAPITAL = 21000.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("PRO_ICT_SMC")

class ProBot:
    def __init__(self):
        self.smart = SmartConnect(api_key=API_KEY)
        self.instruments = None

    def login(self):
        totp = pyotp.TOTP(TOTP_SECRET.replace(" ", "")).now()
        res = self.smart.generateSession(CLIENT_CODE, PIN, totp)
        return res['status']

    def fetch_master(self):
        url = "https://margincalculator.angelbroking.com/OpenAPI_Standard/token/OpenAPIScripMaster.json"
        self.instruments = requests.get(url).json()

    def get_data(self, token, exchange, days=2):
        to_date = dt.now().strftime('%Y-%m-%d %H:%M')
        from_date = (dt.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M')
        res = self.smart.getCandleData({"exchange": exchange, "symboltoken": token, "interval": "FIVE_MINUTE", "fromdate": from_date, "todate": to_date})
        return res['data'] if res['status'] else []

    # --- CORE DETECTORS ---
    def detect_mss(self, candles):
        if len(candles) < 5: return None
        closes = [c[4] for c in candles]
        highs = [c[3] for c in candles[-5:-1]]
        lows = [c[2] for c in candles[-5:-1]]
        if closes[-1] > max(highs): return "BULLISH_MSS"
        if closes[-1] < min(lows): return "BEARISH_MSS"
        return None

    def detect_fvg(self, candles):
        if len(candles) < 3: return None
        c1, c2, c3 = candles[-3], candles[-2], candles[-1]
        if c3[2] > c1[3]: return {"type": "BULL", "entry": c1[3]}
        if c3[3] < c1[2]: return {"type": "BEAR", "entry": c1[2]}
        return None

    def get_fib_ote(self, candles):
        h = max([c[3] for c in candles[-20:]])
        l = min([c[2] for c in candles[-20:]])
        return l + (h - l) * 0.705 # OTE 70.5% Level

    # --- STRATEGY ENGINE ---
    def check_strategies(self, name, token, exchange):
        candles = self.get_data(token, exchange)
        if not candles: return None
        
        mss = self.detect_mss(candles)
        fvg = self.detect_fvg(candles)
        ote = self.get_fib_ote(candles)
        curr = candles[-1][4]
        
        # 1. Core ICT (MSS + OTE + FVG)
        if mss and fvg and (curr <= ote if "BULL" in mss else curr >= ote):
            return "ICT_CORE"
        
        # 2. Silver Bullet (Time based)
        ist_now = dt.now() + timedelta(hours=5, minutes=30)
        if (10 <= ist_now.hour < 11) and fvg:
            return "SILVER_BULLET"
            
        # 3. Turtle Soup (Sweep + MSS)
        if mss: return "TURTLE_SOUP"
        
        return None

    def execute(self, name, token, exchange):
        strat = self.check_strategies(name, token, exchange)
        if strat:
            log.info(f"STRATEGY TRIGGERED: {strat} on {name}")
            # Entry logic (as per previous ATM option code)
            # self.smart.placeOrder(...)

    def run(self):
        if not self.login(): return
        self.fetch_master()
        # Scan Nifty 50 universe
        universe = [{"name": "NIFTY", "token": "99926000", "exch": "NSE"}] # Expand to all 50
        for asset in universe:
            self.execute(asset['name'], asset['token'], asset['exch'])

if __name__ == "__main__":
    ProBot().run()
