import os, time, pyotp, logging, json
from SmartApi import SmartConnect
from datetime import datetime as dt, timedelta

# ---------- LIVE CONFIG ----------
API_KEY = os.environ.get("API_KEY", "")
CLIENT_CODE = os.environ.get("CLIENT_CODE", "")
PIN = os.environ.get("PIN", "")
TOTP_SECRET = os.environ.get("TOTP_SECRET", "")

SYMBOL = "NIFTY24MARFUT"
TOKEN = "12345"
EXCHANGE = "NFO"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
log = logging.getLogger("ICT_SMC_BOT")

class ICTSMCBot:
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
            return False
        except Exception as e:
            log.error(f"Login Error: {e}")
            return False

    def get_data(self, interval="FIVE_MINUTE"):
        to_date = dt.now().strftime('%Y-%m-%d %H:%M')
        from_date = (dt.now() - timedelta(days=5)).strftime('%Y-%m-%d %H:%M')
        res = self.smart.getCandleData({
            "exchange": EXCHANGE, "symboltoken": TOKEN,
            "interval": interval, "fromdate": from_date, "todate": to_date
        })
        return res['data'] if res['status'] else []

    # --- ICT/SMC MODULES ---
    def detect_fvg(self, candles):
        if len(candles) < 3: return None
        c1, c2, c3 = candles[-3], candles[-2], candles[-1]
        if c3[2] > c1[3]: return {"type": "BULLISH", "level": c1[3]} # Bull FVG
        if c3[3] < c1[2]: return {"type": "BEARISH", "level": c1[2]} # Bear FVG
        return None

    def detect_mss_choch(self, candles):
        # Simplistic MSS: Displacement breaking previous high/low
        if len(candles) < 5: return False
        curr_close = candles[-1][4]
        prev_high = max([c[3] for c in candles[-5:-1]])
        prev_low = min([c[2] for c in candles[-5:-1]])
        if curr_close > prev_high: return "BULLISH_MSS"
        if curr_close < prev_low: return "BEARISH_MSS"
        return False

    def is_killzone(self):
        now_ist = dt.now() + timedelta(hours=5, minutes=30)
        h, m = now_ist.hour, now_ist.minute
        # Silver Bullet (10 AM - 11 AM IST & 2 PM - 3 PM IST)
        if (10 <= h < 11) or (14 <= h < 15): return "SILVER_BULLET"
        # London Open (1:30 PM - 3:30 PM IST)
        if (13 <= h < 15) and (h > 13 or m >= 30): return "LONDON_OPEN"
        return "ANY"

    def place_order(self, side, price):
        params = {
            "variety": "NORMAL", "tradingsymbol": SYMBOL, "symboltoken": TOKEN,
            "transactiontype": side, "exchange": EXCHANGE, "ordertype": "LIMIT",
            "producttype": "INTRADAY", "duration": "DAY", "price": str(price), "quantity": "50"
        }
        res = self.smart.placeOrder(params)
        if res['status']: log.info(f"ORDER PLACED: {side} @ {price}")

    def run(self):
        if not self.login(): return
        
        candles = self.get_data()
        kz = self.is_killzone()
        fvg = self.detect_fvg(candles)
        mss = self.detect_mss_choch(candles)

        log.info(f"Scan Result - KZ: {kz}, MSS: {mss}, FVG: {fvg['type'] if fvg else 'None'}")

        # --- STRATEGY: LIQUIDITY SWEEP + MSS + FVG ---
        if kz != "ANY" and mss and fvg:
            if "BULLISH" in mss and fvg['type'] == "BULLISH":
                self.place_order("BUY", fvg['level'])
            elif "BEARISH" in mss and fvg['type'] == "BEARISH":
                self.place_order("SELL", fvg['level'])
        
        # --- STRATEGY: SILVER BULLET ---
        elif kz == "SILVER_BULLET" and fvg:
            side = "BUY" if fvg['type'] == "BULLISH" else "SELL"
            self.place_order(side, fvg['level'])

if __name__ == "__main__":
    ICTSMCBot().run()
