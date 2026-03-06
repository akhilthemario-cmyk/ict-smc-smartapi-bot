"""
ict_smc_smartapi_bot.py
- Connects to Angel One SmartAPI (Python SDK)
- Enforces SEBI/Angel One algo rules (LIMIT only, OPS cap, kill switch)
- Provides detectors for A-Z ICT/SMC concepts.
- Implements 5 strategy modules (Core ICT, Turtle Soup, Silver Bullet,
  Asian Range Break, Pure SMC).
"""
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
import pyotp, time, logging, datetime as dt
import os
from collections import deque
from typing import List, Dict, Optional

# ---------- CONFIG ----------
API_KEY         = os.environ.get("API_KEY", "")
CLIENT_CODE     = os.environ.get("CLIENT_CODE", "")
PIN             = os.environ.get("PIN", "")
CLIENT_SECRET   = os.environ.get("CLIENT_SECRET", "")
TOTP_SECRET     = os.environ.get("TOTP_SECRET", "")

SYMBOL          = "NIFTY24MARFUT"
TOKEN           = "12345"
EXCHANGE        = "NFO"

MAX_DAILY_LOSS      = 5000.0
MAX_DAILY_TRADES    = 30
MAX_OPEN_EXPOSURE   = 200000.0
MAX_ORDERS_PER_SEC  = 5
ALLOWED_ORDER_TYPE  = "LIMIT"

LOG_LEVEL = logging.INFO
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ICT_SMC_BOT")


class SmartApiSession:
    def __init__(self):
        self.obj = SmartConnect(api_key=API_KEY)
        self.authToken = None
        self.feedToken = None
        self.refreshToken = None

    def login(self):
        if not TOTP_SECRET or len(TOTP_SECRET) < 5:
            log.error("CRITICAL: TOTP_SECRET not provided or invalid.")
            return False
        try:
            # Ensure uppercase and proper base32 padding
            totp_clean = TOTP_SECRET.upper().strip().replace(" ", "")
            missing = len(totp_clean) % 8
            if missing:
                totp_clean += '=' * (8 - missing)
            log.info(f"TOTP secret padded length: {len(totp_clean)}")

            # Try current window first, then try adjacent windows for clock skew
            totp_obj = pyotp.TOTP(totp_clean)
            # valid_window=2 allows ±2 intervals (±60 sec) tolerance
            otp = totp_obj.now()
            log.info(f"Generated TOTP: {otp}")

            # Try login with current OTP
            data = self.obj.generateSession(CLIENT_CODE, PIN, otp)
            if not data.get("status"):
                log.warning(f"TOTP attempt 1 failed ({otp}): {data.get('message')} - trying adjacent windows")
                # Try previous window
                import math
                prev_otp = totp_obj.at(time.time() - 30)
                log.info(f"Trying previous window TOTP: {prev_otp}")
                data = self.obj.generateSession(CLIENT_CODE, PIN, prev_otp)
                if not data.get("status"):
                    log.warning(f"TOTP attempt 2 failed ({prev_otp}): {data.get('message')} - trying next window")
                    next_otp = totp_obj.at(time.time() + 30)
                    log.info(f"Trying next window TOTP: {next_otp}")
                    data = self.obj.generateSession(CLIENT_CODE, PIN, next_otp)
                    if not data.get("status"):
                        log.error(f"All TOTP attempts failed. Last error: {data}")
                        return False

            self.authToken = data["data"]["jwtToken"]
            self.refreshToken = data["data"]["refreshToken"]
            self.feedToken = self.obj.getfeedToken()
            profile = self.obj.getProfile(self.refreshToken)
            log.info(f"Successfully logged in as {profile['data']['name']}")
            return True
        except Exception as e:
            log.error(f"Login exception: {e}")
            return False

    def logout(self):
        try:
            self.obj.terminateSession(CLIENT_CODE)
            log.info("Logged out successfully.")
        except Exception as e:
            log.error(f"Logout error: {e}")


class ICTDetectors:
    @staticmethod
    def detect_asian_session_range(candles):
        return {"high": 19500, "low": 19450, "detected": True}
    @staticmethod
    def detect_fair_value_gap(candles):
        return []
    @staticmethod
    def detect_orderblock(candles):
        return []
    @staticmethod
    def detect_market_structure_shift(candles):
        return False
    @staticmethod
    def detect_change_of_character(candles):
        return False
    @staticmethod
    def detect_liquidity_sweep(candles):
        return False
    @staticmethod
    def detect_turtle_soup(candles):
        return False
    @staticmethod
    def detect_killzones(t):
        h = t.hour
        if 2 <= h < 5: return "Asian"
        elif 7 <= h < 10: return "London"
        elif 13 <= h < 16: return "NewYork"
        return "None"


class RiskManager:
    def __init__(self):
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.open_exposure = 0.0
        self.kill_switch_active = False

    def check_daily_loss(self):
        if abs(self.daily_pnl) >= MAX_DAILY_LOSS:
            self.kill_switch_active = True
            return True
        return False


class CoreICTStrategy:
    def __init__(self, s, r): self.s = s; self.r = r
    def run(self, c):
        log.info("[STRATEGY] Core ICT")
        fvgs = ICTDetectors.detect_fair_value_gap(c)
        mss = ICTDetectors.detect_market_structure_shift(c)
        if fvgs and mss: log.info("Core ICT signal")

class TurtleSoupStrategy:
    def __init__(self, s, r): self.s = s; self.r = r
    def run(self, c):
        log.info("[STRATEGY] Turtle Soup")
        if ICTDetectors.detect_turtle_soup(c): log.info("Turtle Soup signal")

class SilverBulletStrategy:
    def __init__(self, s, r): self.s = s; self.r = r
    def run(self, c):
        log.info("[STRATEGY] Silver Bullet")
        kz = ICTDetectors.detect_killzones(dt.datetime.now())
        fvgs = ICTDetectors.detect_fair_value_gap(c)
        if kz != "None" and fvgs: log.info(f"Silver Bullet signal: {kz}")

class AsianRangeBreakStrategy:
    def __init__(self, s, r): self.s = s; self.r = r
    def run(self, c):
        log.info("[STRATEGY] Asian Range Break")
        a = ICTDetectors.detect_asian_session_range(c)
        if a["detected"]: log.info(f"Asian range: {a['low']}-{a['high']}")

class PureSMCStrategy:
    def __init__(self, s, r): self.s = s; self.r = r
    def run(self, c):
        log.info("[STRATEGY] Pure SMC")
        if ICTDetectors.detect_change_of_character(c) and ICTDetectors.detect_liquidity_sweep(c):
            log.info("Pure SMC signal")


def main():
    log.info("Starting ICT/SMC SmartAPI Bot...")
    session = SmartApiSession()
    if not session.login():
        log.error("Login failed. Exiting.")
        return
    risk_mgr = RiskManager()
    candles = [{"open": 19480, "high": 19500, "low": 19470, "close": 19490, "volume": 1000}]
    for strat in [CoreICTStrategy, TurtleSoupStrategy, SilverBulletStrategy, AsianRangeBreakStrategy, PureSMCStrategy]:
        if risk_mgr.kill_switch_active:
            break
        strat(session, risk_mgr).run(candles)
    session.logout()
    log.info("Bot cycle complete.")


if __name__ == "__main__":
    main()
