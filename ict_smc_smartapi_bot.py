import os, time, pyotp, logging, json
from SmartApi import SmartConnect
from datetime import datetime as dt, timedelta

# ---------- LIVE CONFIG ----------
API_KEY = os.environ.get("API_KEY", "")
CLIENT_CODE = os.environ.get("CLIENT_CODE", "")
PIN = os.environ.get("PIN", "")
TOTP_SECRET = os.environ.get("TOTP_SECRET", "")

# ICT/SMC Risk Config
SYMBOL = "NIFTY24MARFUT" # Update to current expiry
TOKEN = "12345"
EXCHANGE = "NFO"
MAX_LOSS = 10.0
TARGET = 50.0

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ICT_BOT")

class ICTBot:
    def __init__(self):
        self.smart = SmartConnect(api_key=API_KEY)
        self.session = None

    def login(self):
        try:
            totp = pyotp.TOTP(TOTP_SECRET.replace(" ", "")).now()
            res = self.smart.generateSession(CLIENT_CODE, PIN, totp)
            if res['status']:
                self.session = res['data']
                log.info(f"Logged in: {res['data']['name']}")
                return True
            log.error(f"Login Failed: {res['message']}")
            return False
        except Exception as e:
            log.error(f"Login Error: {e}")
            return False

    def get_live_data(self):
        # Fetching last 100 5min candles for SMC analysis
        to_date = dt.now().strftime('%Y-%m-%d %H:%M')
        from_date = (dt.now() - timedelta(days=5)).strftime('%Y-%m-%d %H:%M')
        params = {
            "exchange": EXCHANGE, "symboltoken": TOKEN,
            "interval": "FIVE_MINUTE", "fromdate": from_date, "todate": to_date
        }
        res = self.smart.getCandleData(params)
        return res['data'] if res['status'] else []

    def detect_fvg(self, candles):
        # SMC Fair Value Gap Detection
        if len(candles) < 3: return None
        c1, c2, c3 = candles[-3], candles[-2], candles[-1]
        # Bullish FVG: Low of candle 3 > High of candle 1
        if c3[2] > c1[3]: return {"type": "BULLISH", "gap": [c1[3], c3[2]]}
        # Bearish FVG: High of candle 3 < Low of candle 1
        if c3[3] < c1[2]: return {"type": "BEARISH", "gap": [c3[3], c1[2]]}
        return None

    def place_ict_order(self, side, price):
        order_params = {
            "variety": "NORMAL", "tradingsymbol": SYMBOL, "symboltoken": TOKEN,
            "transactiontype": side, "exchange": EXCHANGE, "ordertype": "LIMIT",
            "producttype": "INTRADAY", "duration": "DAY", "price": price,
            "quantity": "50"
        }
        res = self.smart.placeOrder(order_params)
        if res['status']:
            log.info(f"ICT Order Placed: {side} @ {price}")
            return res['data']['orderid']
        return None

    def run(self):
        if not self.login(): return
        candles = self.get_live_data()
        fvg = self.detect_fvg(candles)
        
        if fvg:
            log.info(f"FVG Detected: {fvg['type']} {fvg['gap']}")
            side = "BUY" if fvg['type'] == "BULLISH" else "SELL"
            price = fvg['gap'][0] # Entry at FVG start
            self.place_ict_order(side, str(price))
        else:
            log.info("No ICT setup found in current candles.")

if __name__ == "__main__":
    ICTBot().run()
