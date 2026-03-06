import os, pyotp, logging, requests, time
import pandas as pd
from SmartApi import SmartConnect
from datetime import datetime as dt, timedelta

# ---------- CONFIG ----------
API_KEY = os.environ.get("API_KEY", "")
CLIENT_CODE = os.environ.get("CLIENT_CODE", "")
PIN = os.environ.get("PIN", "")
TOTP_SECRET = os.environ.get("TOTP_SECRET", "")
CAPITAL = 21000.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("MASTER_ICT_SMC")

class MasterICTBot:
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

    # --- 1. CORE ICT (MSS + OTE + FVG) ---
    def detect_ict_core(self, df):
        # 0.705 OTE Calculation
        h, l = df['high'].max(), df['low'].min()
        ote_705 = l + (h - l) * 0.705
        # MSS + FVG Confluence
        c1, c2, c3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
        if c3['low'] > c1['high'] and c3['close'] <= ote_705: return "BUY"
        if c3['high'] < c1['low'] and c3['close'] >= ote_705: return "SELL"
        return None

    # --- 2. TURTLE SOUP (SWEEP + MSS) ---
    def detect_turtle_soup(self, df):
        prev_h = df['high'].iloc[-20:-1].max()
        prev_l = df['low'].iloc[-20:-1].min()
        curr_h, curr_l = df['high'].iloc[-1], df['low'].iloc[-1]
        if curr_h > prev_h and df['close'].iloc[-1] < prev_h: return "SELL" # Fake Break High
        if curr_l < prev_l and df['close'].iloc[-1] > prev_l: return "BUY" # Fake Break Low
        return None

    # --- 3. SILVER BULLET (NY PM FVG) ---
    def detect_silver_bullet(self):
        now_ist = dt.now() + timedelta(hours=5, minutes=30)
        h = now_ist.hour
        if (10 <= h <= 11) or (14 <= h <= 15): return "BULLET_WINDOW"
        return None

    # --- 4. PURE SMC (BOS + OB) ---
    def detect_smc_pure(self, df):
        # Simplistic BOS: New swing high/low break
        if df['close'].iloc[-1] > df['high'].iloc[-2]: return "BOS_BULL"
        if df['close'].iloc[-1] < df['low'].iloc[-2]: return "BOS_BEAR"
        return None

    def run(self):
        if not self.login(): return
        self.fetch_master()
        
        scan_list = [{"name": "NIFTY", "token": "99926000", "exch": "NSE"},
                     {"name": "BANKNIFTY", "token": "99926009", "exch": "NSE"},
                     {"name": "CRUDEOIL", "token": "210000", "exch": "MCX"}]
        
        for asset in scan_list:
            df = self.get_data(asset['token'], asset['exch'])
            if df is None: continue
            
            # --- CONFLUENCE CHECKER ---
            ict = self.detect_ict_core(df)
            soup = self.detect_turtle_soup(df)
            bullet = self.detect_silver_bullet()
            smc = self.detect_smc_pure(df)
            
            # MASTER TRIGGER: MULTI-STRATEGY ALIGNMENT
            if (ict and soup) or (bullet and ict) or (smc and ict):
                log.info(f"MASTER SIGNAL on {asset['name']}: ICT Confluence Detected")
                # ATM Option Logic...

if __name__ == "__main__":
    MasterICTBot().run()
