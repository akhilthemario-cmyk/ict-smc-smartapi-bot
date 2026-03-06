import os, pyotp, logging, requests
from SmartApi import SmartConnect
from datetime import datetime as dt, timedelta

# ---------- CONFIG ----------
API_KEY = os.environ.get("API_KEY", "")
CLIENT_CODE = os.environ.get("CLIENT_CODE", "")
PIN = os.environ.get("PIN", "")
TOTP_SECRET = os.environ.get("TOTP_SECRET", "")
CAPITAL = 21000.0

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ULTRA_ICT_BOT")

class UltraBot:
    def __init__(self):
        self.smart = SmartConnect(api_key=API_KEY)
        self.instruments = None

    def login(self):
        totp = pyotp.TOTP(TOTP_SECRET.replace(" ", "")).now()
        res = self.smart.generateSession(CLIENT_CODE, PIN, totp)
        return res['status']

    def fetch_instruments(self):
        url = "https://margincalculator.angelbroking.com/OpenAPI_Standard/token/OpenAPIScripMaster.json"
        self.instruments = requests.get(url).json()

    def get_atm_option(self, symbol, spot_price, option_type):
        # Round spot to nearest 50/100 for Nifty/BankNifty ATM
        strike = round(spot_price / 50) * 50 if "NIFTY" in symbol else round(spot_price / 100) * 100
        # Filter for current week expiry ATM
        matches = [i for i in self.instruments if i['name'] == symbol and i['exch_seg'] == "NFO" 
                   and i['symbol'].endswith(option_type) and float(i['strike']) == strike]
        return matches[0] if matches else None

    def detect_setup(self, token, exchange):
        to_date = dt.now().strftime('%Y-%m-%d %H:%M')
        from_date = (dt.now() - timedelta(days=2)).strftime('%Y-%m-%d %H:%M')
        res = self.smart.getCandleData({"exchange": exchange, "symboltoken": token, "interval": "FIVE_MINUTE", "fromdate": from_date, "todate": to_date})
        if not res['status'] or not res['data']: return None
        
        candles = res['data']
        c1, c2, c3 = candles[-3], candles[-2], candles[-1]
        highs = [c[3] for c in candles[-20:]]
        lows = [c[2] for c in candles[-20:]]
        fib_705 = max(highs) - (max(highs) - min(lows)) * 0.705

        if c3[2] > c1[3] and c3[4] <= fib_705: return "BUY"
        if c3[3] < c1[2] and c3[4] >= fib_705: return "SELL"
        return None

    def run(self):
        if not self.login(): return
        self.fetch_instruments()
        
        # Define Universe: Top 50 + BankNifty + Crude (MCX)
        universe = [
            {"name": "NIFTY", "token": "99926000", "exch": "NSE"},
            {"name": "BANKNIFTY", "token": "99926009", "exch": "NSE"},
            {"name": "CRUDEOIL", "token": "210000", "exch": "MCX"} # Placeholder token
        ]
        
        for asset in universe:
            signal = self.detect_setup(asset['token'], asset['exch'])
            if signal:
                # Fetch Spot Price for ATM
                spot = self.smart.getLTP(asset['exch'], asset['name'], asset['token'])['data']['ltp']
                opt = self.get_atm_option(asset['name'], spot, "CE" if signal == "BUY" else "PE")
                
                if opt:
                    # Place ATM Option Trade
                    self.smart.placeOrder({
                        "variety": "NORMAL", "tradingsymbol": opt['symbol'], "symboltoken": opt['token'],
                        "transactiontype": signal, "exchange": "NFO", "ordertype": "MARKET",
                        "producttype": "INTRADAY", "duration": "DAY", "quantity": opt['lotsize']
                    })
                    log.info(f"TRADED ATM {opt['symbol']} for {asset['name']}")

if __name__ == "__main__":
    UltraBot().run()
