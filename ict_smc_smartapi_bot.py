import os, time, pyotp, logging, json
from SmartApi import SmartConnect
from datetime import datetime as dt, timedelta

# ---------- LIVE CONFIG ----------
API_KEY = os.environ.get("API_KEY", "")
CLIENT_CODE = os.environ.get("CLIENT_CODE", "")
PIN = os.environ.get("PIN", "")
TOTP_SECRET = os.environ.get("TOTP_SECRET", "")

# SCAN LIST (Nifty 50 + Major Bank Stocks)
SCAN_LIST = [
    {"symbol": "NIFTY", "token": "99926000", "exchange": "NSE"},
    {"symbol": "RELIANCE-EQ", "token": "2885", "exchange": "NSE"},
    {"symbol": "HDFCBANK-EQ", "token": "1333", "exchange": "NSE"},
    {"symbol": "ICICIBANK-EQ", "token": "4963", "exchange": "NSE"},
    {"symbol": "SBIN-EQ", "token": "3045", "exchange": "NSE"},
    {"symbol": "INFY-EQ", "token": "1594", "exchange": "NSE"}
]

CAPITAL = 21000.0
RISK_PER_TRADE = 0.02 # 2% Risk

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("PRO_ICT_BOT")

class ICTSMCProBot:
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

    def get_data(self, token, exchange):
        to_date = dt.now().strftime('%Y-%m-%d %H:%M')
        from_date = (dt.now() - timedelta(days=5)).strftime('%Y-%m-%d %H:%M')
        res = self.smart.getCandleData({
            "exchange": exchange, "symboltoken": token,
            "interval": "FIVE_MINUTE", "fromdate": from_date, "todate": to_date
        })
        return res['data'] if res['status'] else []

    def calculate_fib_levels(self, candles):
        highs = [c[3] for c in candles[-20:]]
        lows = [c[2] for c in candles[-20:]]
        h, l = max(highs), min(lows)
        diff = h - l
        # ICT OTE (62% - 79%)
        return {
            "0.618": h - (diff * 0.618),
            "0.705": h - (diff * 0.705),
            "0.786": h - (diff * 0.786)
        }

    def detect_fvg(self, candles):
        if len(candles) < 3: return None
        c1, c2, c3 = candles[-3], candles[-2], candles[-1]
        if c3[2] > c1[3]: return {"type": "BULLISH", "entry": c1[3], "sl": c1[2]}
        if c3[3] < c1[2]: return {"type": "BEARISH", "entry": c1[2], "sl": c1[3]}
        return None

    def place_smart_order(self, stock, side, price, sl):
        # Position Sizing based on ₹21,000 capital and 2% risk
        risk_amt = CAPITAL * RISK_PER_TRADE
        sl_points = abs(price - sl)
        if sl_points == 0: return
        qty = int(risk_amt / sl_points)
        if qty < 1: qty = 1
        
        params = {
            "variety": "NORMAL", "tradingsymbol": stock['symbol'], "symboltoken": stock['token'],
            "transactiontype": side, "exchange": stock['exchange'], "ordertype": "LIMIT",
            "producttype": "INTRADAY", "duration": "DAY", "price": str(round(price, 2)), "quantity": str(qty)
        }
        res = self.smart.placeOrder(params)
        if res['status']: log.info(f"ORDER: {side} {stock['symbol']} QTY:{qty} @ {price}")

    def run(self):
        if not self.login(): return
        
        for stock in SCAN_LIST:
            candles = self.get_data(stock['token'], stock['exchange'])
            if not candles: continue
            
            fvg = self.detect_fvg(candles)
            fib = self.calculate_fib_levels(candles)
            curr_price = candles[-1][4]

            # CONFLUENCE: FVG + FIB OTE (70.5%)
            if fvg:
                if fvg['type'] == "BULLISH" and curr_price <= fib['0.705']:
                    self.place_smart_order(stock, "BUY", fvg['entry'], fvg['sl'])
                elif fvg['type'] == "BEARISH" and curr_price >= fib['0.618']:
                    self.place_smart_order(stock, "SELL", fvg['entry'], fvg['sl'])

if __name__ == "__main__":
    ICTSMCProBot().run()
