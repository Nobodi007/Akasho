"""
XSpring Dealer Suite — Single-File Build
=========================================
รวม engine (calculation core) + app (Streamlit UI) ไว้ในไฟล์เดียว
โดยยังแยก "ชั้น" ให้ชัดเจนและยังเทสได้โดยไม่ต้องเปิด Streamlit

LAYERS
------
  0. CONFIG & CONSTANTS      — ค่าคงที่ทั้งหมดของโมเดล
  1. ENGINE / PURE LOGIC     — คณิตศาสตร์ล้วน ไม่แตะ streamlit / network
  2. DATA LAYER              — yfinance / cache / CSV export
  3. UI THEME & COMPONENTS   — CSS, metric card, timeline, gauge, TradingView
  4. AUDIT TRAIL             — log การเปลี่ยนพารามิเตอร์
  5. APP (main)              — sidebar + 3 tabs

TESTABILITY
-----------
UI ทั้งหมดอยู่ใน main() และถูกเรียกใต้ `if __name__ == "__main__"` เท่านั้น
Streamlit รันไฟล์นี้เป็น __main__ → UI ทำงานปกติ
unittest ทำ `import xspring_suite as eng` → ได้เฉพาะ layer 0-1 ไม่มี side effect

MODEL_VERSION / CHANGELOG
-------------------------
Bump เมื่อ "ตัวเลขที่ผู้ใช้เคยเห็นจะเปลี่ยน" เท่านั้น (haircut, safety stock, NC, fee)

v1.0.0  baseline        safety_stock_factor, crypto_haircut, blended NC custody rate,
                        nc_snapshot, FX-limit gate, Time-Travel order state machine
v1.1.0  2026-xx-xx      แยก pure logic ออกจาก app.py → engine.py (structural only)
v1.2.0  2026-xx-xx      รวมกลับเป็นไฟล์เดียว + จัดชั้นโครงสร้าง/UI polish
                        *** ไม่มีสูตรใดเปลี่ยน — structural version bump only ***
"""

from __future__ import annotations

import json
import math  # noqa: F401  (ใช้ในเทส known-answer)
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd

MODEL_VERSION = "1.2.0"

# UI stack เป็น optional dependency: import ไม่ได้ก็ยังใช้ engine ได้
try:
    import plotly.graph_objects as go
    import streamlit as st
    import streamlit.components.v1 as components
    import yfinance as yf
    HAS_UI = True
except ImportError:  # pragma: no cover - เส้นทางสำหรับ unittest/notebook เท่านั้น
    go = st = components = yf = None
    HAS_UI = False

# =========================================================================
# LAYER 0 — CONFIG & CONSTANTS
# =========================================================================

# ---- Exchanges & assets --------------------------------------------------
GLOBAL_EXCHANGE_FEE_PRESET = {
    "Binance": 0.10, "Coinbase": 0.60, "Kraken": 0.26, "OKX": 0.10,
    "กำหนดเอง (Custom)": 0.10,
}
LOCAL_EXCHANGES = ["Bitkub"]
SUPPORTED_ASSETS = ["BTC", "ETH", "SOL", "DOGE", "ADA", "HBAR", "LINK", "XLM", "XRP", "USDT", "USDC"]
STABLECOINS = ["USDT", "USDC"]

# ---- Local venue fee schedule -------------------------------------------
LOCAL_TRADING_FEE_PCT = 0.0025
MIN_TRADE_THB = 50.0
WITHDRAWAL_FEE_TABLE = {
    "BTC": 0.00002, "ETH": 0.0004, "ADA": 1.5, "DOGE": 4, "LINK": 0.063,
    "USDT": 4, "XLM": 0.004, "SOL": 0.001, "HBAR": 0.06, "USDC": 1.2, "XRP": 0.2,
}

# ---- Chart symbol maps ---------------------------------------------------
TV_LOCAL_SYMBOL = {
    "BTC": "BITKUB:BTCTHB", "ETH": "BITKUB:ETHTHB", "SOL": "BITKUB:SOLTHB",
    "DOGE": "BITKUB:DOGETHB", "ADA": "BITKUB:ADATHB", "XRP": "BITKUB:XRPTHB",
    "LINK": "BITKUB:LINKTHB", "XLM": "BITKUB:XLMTHB", "HBAR": "BITKUB:HBARTHB",
    "USDT": "BITKUB:USDTTHB", "USDC": "BITKUB:USDCTHB",
}
TV_GLOBAL_SYMBOL = {a: f"BINANCE:{a}USDT" for a in SUPPORTED_ASSETS}
TV_GLOBAL_SYMBOL["USDT"] = "BINANCE:USDTTRY"
TV_GLOBAL_SYMBOL["USDC"] = "BINANCE:USDCUSDT"

# ---- Risk / capital parameters ------------------------------------------
Z_SCORE_MAP = {90: 1.2816, 95: 1.645, 99: 2.326, 99.9: 3.09}

HOT_WALLET_NC_RATE = 1.00
COLD_DOMESTIC_NC_RATE = 0.01
HOT_WALLET_CAP = 0.50
HOT_WALLET_CAP_LIAB_THRESHOLD = 1_000_000_000

# Fallback USDTHB ใช้เมื่อดึงเรทสดไม่ได้จริง ๆ เท่านั้น (เช่นเน็ตหลุดทั้งระบบ)
# เป็น last resort ไม่ใช่ normal code path — ดู get_reference_usdthb()
FALLBACK_USDTHB = 35.5

# ต่ำกว่า MIN_RISK_SAMPLE_DAYS = ไม่คำนวณเลย
# ต่ำกว่า RISK_SAMPLE_WARN_DAYS = คำนวณได้แต่ติดธง "insufficient_sample"
MIN_RISK_SAMPLE_DAYS = 30
RISK_SAMPLE_WARN_DAYS = 180

# =========================================================================
# LAYER 1 — ENGINE / PURE LOGIC
#   ห้ามมี streamlit / network / I/O ในโซนนี้เด็ดขาด
# =========================================================================

# -------------------------------------------------------------------------
# 1.1 Formatting helpers
# -------------------------------------------------------------------------

def fmt_num(value, force_sign=False):
    value = 0.0 if pd.isna(value) else float(value)
    sign = "- " if value < 0 else ("+ " if force_sign else "")
    v = abs(value)
    if v >= 1_000_000_000:
        num = f"{v/1_000_000_000:,.2f}B"
    elif v >= 1_000_000:
        num = f"{v/1_000_000:,.2f}M"
    elif v >= 1_000:
        num = f"{v/1_000:,.1f}K"
    else:
        num = f"{v:,.2f}"
    return f"{sign}{num}"

def fmt_baht(value, force_sign=False):
    return f"฿ {fmt_num(value, force_sign)}"

def fmt_coin(value, symbol=""):
    v = abs(float(value))
    d = 6 if v < 1 else (4 if v < 1000 else 2)
    return f"{value:,.{d}f}" + (f" {symbol}" if symbol else "")

# -------------------------------------------------------------------------
# 1.2 Fee rules
# -------------------------------------------------------------------------

def calc_thb_withdrawal_fee(amount_thb: float, bank_type: str, ktb_fee_thb: float = 15.0) -> float:
    if bank_type == "KTB (กรุงไทย)":
        return ktb_fee_thb
    if bank_type == "SCB":
        return 20.0
    return 20.0 if amount_thb <= 2_000_000 else 70.0

# -------------------------------------------------------------------------
# 1.3 FX limit gate
# -------------------------------------------------------------------------

def apply_fx_limit(hedge_usd: pd.Series, index: pd.DatetimeIndex, fx_limit: float):
    """จัดสรรโควตา outbound FX รายเดือนให้ time series ของต้นทุน hedge

    fx_limit <= 0 เป็น input ที่ถูกต้อง (โควตาหมด/ปิดใช้งาน) และต้อง block
    ทุกวันแทนที่จะ raise หรือหารด้วยศูนย์
    """
    allowed, usage, used, cur_month = [], [], 0.0, None
    for ts, cost in zip(index, hedge_usd.values):
        m = ts.to_period("M")
        if m != cur_month:
            cur_month, used = m, 0.0
        if used + cost <= fx_limit:
            used += cost
            allowed.append(1)
        else:
            allowed.append(0)
        usage.append(used)
    return np.array(allowed), np.array(usage)

# -------------------------------------------------------------------------
# 1.4 Risk engine
# -------------------------------------------------------------------------

def _risk_stats(r: pd.Series) -> dict | None:
    r = r.replace([np.inf, -np.inf], np.nan).dropna()
    if len(r) < MIN_RISK_SAMPLE_DAYS:
        return None
    q01, q05 = np.percentile(r, 1), np.percentile(r, 5)
    tail = r[r <= q01]
    return {
        "returns": r,
        "sigma_d": float(r.std()),
        "ann_vol": float(r.std() * np.sqrt(365)),
        "var95": float(max(-q05, 0)),
        "var99": float(max(-q01, 0)),
        "es99": float(max(-tail.mean(), 0)) if len(tail) else float(max(-q01, 0)),
        "worst": float(max(-r.min(), 0)),
        "worst_date": r.idxmin(),
        "n_obs": int(len(r)),
        "insufficient_sample": len(r) < RISK_SAMPLE_WARN_DAYS,
    }

def risk_profile(px: pd.Series) -> dict | None:
    return _risk_stats(np.log(px / px.shift(1)))

def safety_stock_factor(net_bias: float, flow_cv: float, lag_days: int, z_alpha: float) -> float:
    """a = (max(0, bias) × lag + z_α × CV × √lag) / 30"""
    return (max(0.0, net_bias) * lag_days + z_alpha * flow_cv * np.sqrt(lag_days)) / 30.0

def crypto_haircut(es99: float, lag_days: int) -> float:
    """h = min(ES99 × √lag, 95%)"""
    return float(min(es99 * np.sqrt(lag_days), 0.95))

def blended_custody_rate(hot_pct: float, cold_domestic_pct: float, cold_foreign_rate: float) -> float:
    """NC *custody risk rate* ถ่วงน้ำหนัก — ใช้กับฝั่ง `required` ของ NC เท่านั้น

    จงใจให้เป็นคนละตัวกับ `h_crypto` / `crypto_haircut` ซึ่งใช้ตีมูลค่าสต็อกจริง
    ของโต๊ะเทรดในฝั่ง `actual` — สองตัวนี้ตอบคนละคำถาม (เงินกองทุนตามเกณฑ์
    สำหรับการเก็บรักษา vs. haircut mark-to-risk ของของที่ถืออยู่) และไม่ควร
    บรรจบกัน อย่า "ลดรูป" ให้เหลืออัตราเดียว
    """
    return (hot_pct * HOT_WALLET_NC_RATE
            + (1 - hot_pct) * (cold_domestic_pct * COLD_DOMESTIC_NC_RATE
                               + (1 - cold_domestic_pct) * cold_foreign_rate))

def nc_snapshot(stock_thb: float, total_capital: float, cex_margin: float, liab: float,
                h_crypto: float, h_cex: float, fixed_min_nc: float,
                trading_risk_rate: float, daily_volume_thb: float,
                custody_rate: float) -> dict:
    """actual   = NC แบบ mark-to-risk ที่โต๊ะมีจริง (haircut ด้วย h_crypto/h_cex)
    required = NC ขั้นต่ำสไตล์เกณฑ์กำกับ (ใช้ custody_rate ไม่ใช่ h_crypto)

    ไม่มี input ตัวไหนถูกสมมติว่าเป็นบวก: total_capital ติดลบได้ (ตั้งต้นล้มละลาย),
    fixed_min_nc / trading_risk_rate / daily_volume_thb เป็นศูนย์ได้ — เลขคณิต
    degrade อย่างนุ่มนวลทุกกรณีแทนที่จะ raise เพื่อให้ caller พึ่ง `buffer` ได้
    ว่าเป็นตัวเลขที่มีความหมาย (ต่อให้ติดลบหนัก) แทนที่จะแครช
    """
    cash = total_capital - stock_thb
    actual = cash + stock_thb * (1 - h_crypto) + cex_margin * (1 - h_cex) - liab
    trading_nc = trading_risk_rate * daily_volume_thb
    custody_nc = stock_thb * custody_rate
    required = fixed_min_nc + trading_nc + custody_nc
    return {
        "cash": cash, "actual": actual, "required": required,
        "buffer": actual - required, "trading_nc": trading_nc, "custody_nc": custody_nc,
    }

# -------------------------------------------------------------------------
# 1.5 Time-Travel order simulator — state machine
# -------------------------------------------------------------------------

def sim_defaults(asset_name, start_date_val, spot_usd, usdthb, target_stock_thb):
    coin_price = spot_usd * usdthb
    return {
        "asset": asset_name,
        "inv_coins": (target_stock_thb / coin_price) if coin_price > 0 else 0.0,
        "target_thb": target_stock_thb,
        "fx_used_usd": 0.0,
        "cex_used_thb": 0.0,
        "pnl_thb": 0.0,
        "unhedged_thb": 0.0,
        "orders": [],
        "current_date": start_date_val,
    }

def sim_config_signature(ctx, target_stock_thb, start_date, end_date):
    """ลายนิ้วมือของ config — ใช้ตรวจว่า 'พารามิเตอร์เปลี่ยน → ต้องรีเซ็ต sim'"""
    keys = [
        "asset", "local_premium", "spread", "hedge_fee",
        "fx_limit", "slip_sens", "include_fee_rev",
        "wd_markup", "wd_fee_per_coin", "bank_type", "ktb_wd_fee", "ktb_fx_bps",
        "capital", "cex_margin", "cex_liquidity_thb", "liab", "h_crypto", "h_cex",
        "fixed_min_nc", "trading_risk_rate", "daily_volume_thb", "custody_rate",
        "hot_breach",
    ]
    values = []
    for key in keys:
        value = ctx.get(key)
        if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
            value = round(float(value), 10)
        values.append(value)
    values.append(round(float(target_stock_thb), 2))
    values.append(str(start_date))
    values.append(str(end_date))
    return tuple(values)

def sim_normalize_state(sim, asset, start_date_val, spot_usd, usdthb, target_stock_thb):
    if not isinstance(sim, dict):
        return sim_defaults(asset, start_date_val, spot_usd, usdthb, target_stock_thb)

    sim.setdefault("asset", asset)
    sim.setdefault("target_thb", target_stock_thb)
    sim.setdefault("fx_used_usd", 0.0)
    sim.setdefault("cex_used_thb", 0.0)
    sim.setdefault("pnl_thb", 0.0)
    sim.setdefault("unhedged_thb", 0.0)
    sim.setdefault("orders", [])
    sim.setdefault("current_date", start_date_val)

    for key in ("fx_used_usd", "cex_used_thb", "pnl_thb", "unhedged_thb"):
        try:
            sim[key] = float(sim[key])
            if not np.isfinite(sim[key]):
                sim[key] = 0.0
        except (TypeError, ValueError):
            sim[key] = 0.0

    try:
        sim["inv_coins"] = float(sim.get("inv_coins", 0.0))
        if not np.isfinite(sim["inv_coins"]):
            raise ValueError
    except (TypeError, ValueError):
        coin_price = spot_usd * usdthb
        sim["inv_coins"] = target_stock_thb / coin_price if coin_price > 0 else 0.0

    sim["asset"] = asset
    sim["target_thb"] = float(target_stock_thb)
    return sim

def execute_order(sim, side, amount_thb, order_date, px_row, ctx):
    """รันออเดอร์ลูกค้า 1 รายการผ่าน quote → settlement → inventory → hedge
    → gates → P&L โดย mutate `sim` in place

    คืน (steps, record): `steps` คือ timeline สำหรับ UI, `record` คือแถวใน
    สมุดออเดอร์ (หรือ None ถ้าถูกปฏิเสธก่อนจะมีสถานะที่ควรลงบัญชี)
    """
    p = ctx
    side = "buy" if side == "buy" else "sell"

    try:
        amount_thb = float(amount_thb)
    except (TypeError, ValueError):
        amount_thb = 0.0

    spot = float(px_row["Global_USD"])
    fx = float(px_row["USDTHB"])
    daily_vol = float(px_row["Volatility_Pct"])

    coin_price_global = spot * fx
    if spot <= 0 or fx <= 0 or coin_price_global <= 0:
        return [dict(n=1, t="ไม่สามารถสร้างราคาได้", s="block",
                     note="ราคา Global หรือ USD/THB ไม่ถูกต้อง")], None

    mid = coin_price_global * (1 + p["local_premium"])
    quote = mid * (1 + p["spread"]) if side == "buy" else mid * (1 - p["spread"])
    steps = []

    if amount_thb < MIN_TRADE_THB:
        steps.append(dict(
            n=1, t="คำสั่งถูกปฏิเสธ", s="block",
            note=f"มูลค่าต่ำกว่าขั้นต่ำ {MIN_TRADE_THB:,.0f} บาท/คำสั่ง ระบบไม่รับออเดอร์",
        ))
        return steps, None

    # ---- ด่าน 1: ตั้งราคา ------------------------------------------------
    steps.append(dict(
        n=1, t="ตั้งราคาให้ลูกค้า", s="pass",
        note=f"ดึงราคาย้อนหลัง ณ วันที่ {order_date.strftime('%Y-%m-%d')} มาเป็นฐาน + Local Premium + Dealer Spread",
        rows=[
            ("วันที่จำลองออเดอร์", order_date.strftime('%Y-%m-%d')),
            ("ราคาโลก (USD)", f"$ {spot:,.2f}"),
            ("× อัตราแลกเปลี่ยน USD/THB", f"{fx:,.2f}"),
            (f"+ Local Premium {p['local_premium']*100:.2f}%", f"฿ {mid:,.2f}"),
            (f"{'+' if side == 'buy' else '−'} Dealer Spread {p['spread']*100:.2f}%", f"฿ {quote:,.2f}"),
        ],
        total=("ราคาที่ลูกค้าได้", f"฿ {quote:,.2f}"),
    ))

    # ---- ด่าน 2: settlement ---------------------------------------------
    trading_fee = amount_thb * LOCAL_TRADING_FEE_PCT
    settlement_thb = max(0.0, amount_thb - trading_fee)
    coins = settlement_thb / quote

    if coins <= 0:
        steps.append(dict(n=2, t="จับคู่และส่งมอบ", s="block", note="จำนวนเหรียญที่คำนวณได้ไม่เป็นบวก"))
        return steps, None

    inv_before = float(sim["inv_coins"])
    target_coins = float(sim["target_thb"]) / coin_price_global if coin_price_global > 0 else 0.0
    inv_after_customer = inv_before - coins if side == "buy" else inv_before + coins

    # Pre-check ฝั่ง Buy: ต้องไม่ส่งมอบของที่ไม่มี
    if side == "buy":
        required_topup_coins = max(0.0, target_coins - inv_after_customer)
        fx_left_usd = max(0.0, float(p["fx_limit"]) - float(sim["fx_used_usd"]))
        max_hedge_by_fx = (
            fx_left_usd / (spot * (1 + p["hedge_fee"]))
            if spot > 0 and p["hedge_fee"] >= 0 else 0.0
        )
        feasible_hedge_coins = min(required_topup_coins, max_hedge_by_fx)

        if inv_after_customer + feasible_hedge_coins < -1e-12:
            steps.append(dict(
                n=2, t="จับคู่และส่งมอบเข้ากระเป๋า", s="block",
                note="สต็อกที่มีอยู่ + ความสามารถ hedge ที่เหลือไม่เพียงพอ จึงไม่ส่งมอบเหรียญที่ไม่มีอยู่จริง",
                rows=[
                    ("มูลค่าคำสั่ง", fmt_baht(amount_thb)),
                    (f"ค่าธรรมเนียมซื้อขาย {LOCAL_TRADING_FEE_PCT*100:.2f}%", "− " + fmt_baht(trading_fee)),
                    ("เหรียญที่ต้องส่งมอบ", fmt_coin(coins, sim["asset"])),
                    ("สต็อกก่อน", fmt_coin(inv_before, sim["asset"])),
                    ("FX quota เหลือ", f"$ {fx_left_usd:,.0f}"),
                    ("สูงสุดที่ hedge ได้ด้วย FX", fmt_coin(feasible_hedge_coins, sim["asset"])),
                ],
                total=("สถานะ", "Reject — Inventory/FX ไม่พอ"),
            ))
            return steps, {
                "วันที่": order_date.strftime('%Y-%m-%d'),
                "ฝั่ง": "ซื้อ", "เหรียญ": sim["asset"], "มูลค่า (บาท)": amount_thb,
                "ราคาที่ลูกค้าได้": quote, "เหรียญที่ส่งมอบ": 0.0, "Hedge (เหรียญ)": 0.0,
                "Hedge (USD)": 0.0, "CEX Liquidity ใช้ (บาท)": 0.0, "Unhedged (บาท)": 0.0,
                "Market Edge": 0.0, "รายได้": 0.0, "ต้นทุน": 0.0, "กำไรออเดอร์": 0.0,
                "สต็อกคงเหลือ": inv_before, "FX ใช้สะสม (USD)": sim["fx_used_usd"],
                "CEX Liquidity ใช้สะสม (บาท)": sim["cex_used_thb"], "NC Buffer": np.nan,
                "ผลด่าน": "Reject — Inventory/FX ไม่พอ",
            }

    steps.append(dict(
        n=2, t="จับคู่และส่งมอบเข้ากระเป๋า", s="pass",
        note=("ลูกค้าชำระเงินบาทและได้รับเหรียญจาก inventory" if side == "buy"
              else "รับเหรียญจากลูกค้าและจ่ายเงินบาทตามราคาที่ quote"),
        rows=[
            ("มูลค่าที่ลูกค้าใส่", fmt_baht(amount_thb)),
            (f"ค่าธรรมเนียมซื้อขาย {LOCAL_TRADING_FEE_PCT*100:.2f}%", "− " + fmt_baht(trading_fee)),
            ("ฐาน settlement หลังค่าธรรมเนียม", fmt_baht(settlement_thb)),
        ],
        total=("เหรียญที่ลูกค้าได้" if side == "buy" else "เหรียญที่ลูกค้าส่งมอบ",
               fmt_coin(coins, sim["asset"])),
    ))

    # ---- ด่าน 3: ตัด/รับสต็อก -------------------------------------------
    sim["inv_coins"] = inv_after_customer
    short_coins = max(0.0, target_coins - sim["inv_coins"])
    excess_coins = max(0.0, sim["inv_coins"] - target_coins)

    steps.append(dict(
        n=3, t="ตัด/รับสต็อก", s="warn" if (short_coins > 0 or excess_coins > 0) else "pass",
        note=("Buy ลด inventory ก่อน แล้วค่อยเติมกลับด้วย hedge" if side == "buy"
              else "Sell เพิ่ม inventory ก่อน แล้วค่อยขายส่วนเกินบน CEX"),
        rows=[
            ("สต็อกก่อนออเดอร์", fmt_coin(inv_before, sim["asset"])),
            ("การเปลี่ยนแปลง", ("− " if side == "buy" else "+ ") + fmt_coin(coins, sim["asset"])),
            ("สต็อกหลังรับ/ส่งมอบ", fmt_coin(sim["inv_coins"], sim["asset"])),
            ("Target Stock", fmt_coin(target_coins, sim["asset"])),
            ("Short / Excess", fmt_coin(short_coins if side == "buy" else excess_coins, sim["asset"])),
        ],
        total=("มูลค่าสต็อกปัจจุบัน", fmt_baht(max(0.0, sim["inv_coins"]) * coin_price_global)),
    ))

    # ---- ด่าน 4: Hedge (single source of truth ของ hedged_coins/thb/usd) --
    hedge_required_coins = short_coins if side == "buy" else excess_coins
    cex_used_thb_this_order = 0.0

    if side == "buy":
        fx_left_usd = max(0.0, float(p["fx_limit"]) - float(sim["fx_used_usd"]))
        max_hedge_by_fx = (fx_left_usd / (spot * (1 + p["hedge_fee"]))
                           if spot > 0 and p["hedge_fee"] >= 0 else 0.0)
        hedged_coins = min(hedge_required_coins, max_hedge_by_fx)
        residual_unhedged_coins = max(0.0, hedge_required_coins - hedged_coins)

        hedge_thb = hedged_coins * coin_price_global
        hedge_usd = hedged_coins * spot * (1 + p["hedge_fee"])
        sim["fx_used_usd"] += hedge_usd
        if hedge_required_coins > 0:
            sim["inv_coins"] += hedged_coins
        sim["unhedged_thb"] += residual_unhedged_coins * coin_price_global

        fx_status = "pass" if residual_unhedged_coins <= 1e-12 else "warn"
        hedge_status = fx_status
        hedge_note = ("เติม inventory กลับถึง target ด้วยการซื้อบน Global CEX"
                      if residual_unhedged_coins <= 1e-12
                      else "FX quota ไม่พอสำหรับเติม inventory ทั้งหมด จึงเหลือ exposure ค้างบางส่วน")
        cex_liquidity_left = max(0.0, float(p["cex_liquidity_thb"]) - float(sim["cex_used_thb"]))
    else:
        cex_liquidity_left = max(0.0, float(p["cex_liquidity_thb"]) - float(sim["cex_used_thb"]))
        max_hedge_by_cex = cex_liquidity_left / coin_price_global if coin_price_global > 0 else 0.0
        hedged_coins = min(hedge_required_coins, max_hedge_by_cex)
        residual_unhedged_coins = max(0.0, hedge_required_coins - hedged_coins)

        hedge_thb = hedged_coins * coin_price_global
        # USD-equivalent สำหรับแสดงผลเท่านั้น — ไม่ได้ตัดจาก FX quota
        hedge_usd = hedged_coins * spot * (1 + p["hedge_fee"])
        cex_used_thb_this_order = hedge_thb
        sim["cex_used_thb"] += cex_used_thb_this_order
        sim["inv_coins"] -= hedged_coins
        sim["unhedged_thb"] += residual_unhedged_coins * coin_price_global

        fx_status = "pass"
        hedge_status = "pass" if residual_unhedged_coins <= 1e-12 else "warn"
        hedge_note = ("ขาย inventory ส่วนเกินบน Global CEX โดยใช้ CEX liquidity"
                      if residual_unhedged_coins <= 1e-12
                      else "CEX liquidity ไม่พอขาย inventory ส่วนเกินทั้งหมด จึงเหลือ long exposure ค้าง")
        fx_left_usd = max(0.0, float(p["fx_limit"]) - float(sim["fx_used_usd"]))

    steps.append(dict(
        n=4, t="ระบบตัดสินใจ Hedge อัตโนมัติ", s=hedge_status, note=hedge_note,
        rows=[
            ("ปริมาณที่ต้อง hedge", fmt_coin(hedge_required_coins, sim["asset"])),
            ("Hedge สำเร็จ", fmt_coin(hedged_coins, sim["asset"])),
            ("มูลค่า hedge", fmt_baht(hedge_thb)),
            ("Residual Unhedged", fmt_coin(residual_unhedged_coins, sim["asset"])),
            ("Direction", "Buy บน CEX" if side == "buy" else "Sell บน CEX"),
        ],
        total=("สถานะ", "Hedge ครบ" if residual_unhedged_coins <= 1e-12 else "Hedge บางส่วน"),
    ))

    # ---- ด่าน 5: FX / CEX liquidity gate --------------------------------
    if side == "buy":
        steps.append(dict(
            n=5, t="ด่าน FX Limit — Outbound", s=fx_status,
            note=("Buy-side hedge ใช้ outbound FX quota" if residual_unhedged_coins <= 1e-12
                  else "โควตา outbound เหลือไม่พอ จึงเหลือ inventory exposure ที่ยังไม่ได้ hedge"),
            rows=[
                ("FX ใช้ก่อนออเดอร์", f"$ {sim['fx_used_usd'] - hedge_usd:,.0f}"),
                ("ออเดอร์นี้ใช้", f"$ {hedge_usd:,.0f}"),
                ("FX ใช้สะสมหลังออเดอร์", f"$ {sim['fx_used_usd']:,.0f}"),
                ("FX Limit", f"$ {p['fx_limit']:,.0f}"),
                ("FX เหลือ", f"$ {max(0.0, p['fx_limit'] - sim['fx_used_usd']):,.0f}"),
            ],
            total=("ส่วนที่ยัง Unhedged", fmt_baht(residual_unhedged_coins * coin_price_global)),
        ))
    else:
        steps.append(dict(
            n=5, t="ด่าน CEX Liquidity — Sell-side",
            s=fx_status if residual_unhedged_coins <= 1e-12 else "warn",
            note="Sell-side hedge ใช้ CEX liquidity เดิม ไม่กิน outbound FX quota",
            rows=[
                ("CEX Liquidity ก่อนออเดอร์", fmt_baht(cex_liquidity_left + cex_used_thb_this_order)),
                ("ใช้ hedge ออเดอร์นี้", fmt_baht(cex_used_thb_this_order)),
                ("ใช้สะสม", fmt_baht(sim["cex_used_thb"])),
                ("CEX Liquidity เหลือ", fmt_baht(max(0.0, p["cex_liquidity_thb"] - sim["cex_used_thb"]))),
                ("FX ใช้สะสม", f"$ {sim['fx_used_usd']:,.0f}"),
            ],
            total=("ส่วนที่ยัง Unhedged", fmt_baht(residual_unhedged_coins * coin_price_global)),
        ))

    # ---- ด่าน 6: NC gate -------------------------------------------------
    stock_thb = max(0.0, sim["inv_coins"]) * coin_price_global
    nc = nc_snapshot(
        stock_thb, p["capital"], p["cex_margin"], p["liab"],
        p["h_crypto"], p["h_cex"], p["fixed_min_nc"],
        p["trading_risk_rate"], p["daily_volume_thb"], p["custody_rate"],
    )

    if nc["buffer"] < 0:
        nc_status = "block"
    elif nc["buffer"] < 0.5 * nc["required"] or p["hot_breach"]:
        nc_status = "warn"
    else:
        nc_status = "pass"

    steps.append(dict(
        n=6, t="ด่านเงินกองทุนสภาพคล่องสุทธิ (Planning Model)", s=nc_status,
        note=("NC/Capital เป็น planning model; ไม่ใช่ตัวรับรอง compliance อัตโนมัติ"
              if nc_status != "pass" else "หลังออเดอร์ยังมี NC buffer เป็นบวกตาม planning model"),
        rows=[
            ("สต็อกหลัง hedge", fmt_baht(stock_thb)),
            ("Cash ใน NC Model", fmt_baht(nc["cash"])),
            ("CEX Margin หลัง haircut", fmt_baht(p["cex_margin"] * (1 - p["h_cex"]))),
            ("NC ที่มีจริง", fmt_baht(nc["actual"])),
            ("NC ขั้นต่ำที่ต้องดำรง", fmt_baht(nc["required"])),
        ],
        total=("NC Buffer", fmt_baht(nc["buffer"], force_sign=True)),
    ))

    # ---- ด่าน 7: P&L -----------------------------------------------------
    market_edge = (coins * (quote - coin_price_global) if side == "buy"
                   else coins * (coin_price_global - quote))
    fee_rev = trading_fee if p["include_fee_rev"] else 0.0

    wd_markup_rev = 0.0
    if side == "buy":
        wd_markup_rev = (p["wd_fee_per_coin"] * coins * coin_price_global
                         + calc_thb_withdrawal_fee(amount_thb, p["bank_type"], p["ktb_wd_fee"])) * p["wd_markup"]

    ktb_fx_benefit = hedge_thb * (p["ktb_fx_bps"] / 10000.0) if hedged_coins > 0 else 0.0
    hedge_fee_cost = hedge_thb * p["hedge_fee"] if hedged_coins > 0 else 0.0
    slippage_cost = hedge_thb * daily_vol * p["slip_sens"] if hedged_coins > 0 else 0.0

    revenue = market_edge + fee_rev + wd_markup_rev + ktb_fx_benefit
    cost = hedge_fee_cost + slippage_cost
    net = revenue - cost
    sim["pnl_thb"] += net

    steps.append(dict(
        n=7, t="กำไรขาดทุนของ Dealer ในออเดอร์นี้", s="pass" if net >= 0 else "warn",
        note=("P&L มาจาก realized quote-vs-global edge + fee หักต้นทุน hedge/slippage" if side == "buy"
              else "Sell-side P&L สะท้อนส่วนต่างระหว่างราคาที่รับซื้อจากลูกค้ากับราคาที่ขายต่อบน Global CEX"),
        rows=[
            ("Market Edge จาก Quote vs Global", ("+ " if market_edge >= 0 else "− ") + fmt_baht(abs(market_edge))),
            ("ค่าธรรมเนียมซื้อขาย", "+ " + fmt_baht(fee_rev)),
            ("Markup ค่าธรรมเนียมถอน", "+ " + fmt_baht(wd_markup_rev)),
            ("KTB FX Benefit", "+ " + fmt_baht(ktb_fx_benefit)),
            ("ค่าธรรมเนียม CEX", "− " + fmt_baht(hedge_fee_cost)),
            ("Slippage", "− " + fmt_baht(slippage_cost)),
        ],
        total=("กำไรสุทธิ",
               f"{fmt_baht(net, force_sign=True)} ({(net/amount_thb*10000) if amount_thb else 0.0:,.1f} bps)"),
    ))

    record = {
        "วันที่": order_date.strftime('%Y-%m-%d'),
        "ฝั่ง": "ซื้อ" if side == "buy" else "ขาย",
        "เหรียญ": sim["asset"],
        "มูลค่า (บาท)": amount_thb,
        "ราคาที่ลูกค้าได้": quote,
        "เหรียญที่ส่งมอบ": coins,
        "Hedge (เหรียญ)": hedged_coins,
        "Hedge (USD)": hedge_usd,
        "CEX Liquidity ใช้ (บาท)": cex_used_thb_this_order,
        "Unhedged (บาท)": residual_unhedged_coins * coin_price_global,
        "Market Edge": market_edge,
        "รายได้": revenue,
        "ต้นทุน": cost,
        "กำไรออเดอร์": net,
        "สต็อกคงเหลือ": sim["inv_coins"],
        "FX ใช้สะสม (USD)": sim["fx_used_usd"],
        "CEX Liquidity ใช้สะสม (บาท)": sim["cex_used_thb"],
        "NC Buffer": nc["buffer"],
        "ผลด่าน": ("ผ่าน" if nc_status == "pass" and residual_unhedged_coins <= 1e-12
                   else ("เฝ้าระวัง" if nc_status != "block" else "NC ไม่พอ")),
    }
    sim["orders"].append(record)
    return steps, record

# =========================================================================
# LAYER 2 — DATA LAYER (network / IO / export)
# =========================================================================

def _normalize_index(d: pd.DataFrame) -> pd.DataFrame:
    idx = pd.to_datetime(d.index)
    try:
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_convert(None)
    except (TypeError, AttributeError):
        pass
    d.index = idx.normalize()
    return d

if HAS_UI:

    @st.cache_data(ttl=3600, show_spinner="กำลังโหลดข้อมูลราคาย้อนหลัง…")
    def fetch_price_data(ticker, start, end):
        try:
            raw = yf.download(f"{ticker}-USD", start=start, end=end, auto_adjust=False, progress=False)
            fx_raw = yf.download("THB=X", start=start, end=end, auto_adjust=False, progress=False)
        except Exception as e:
            return pd.DataFrame(), f"ดึงข้อมูลไม่สำเร็จ: {e}"

        if raw is None or raw.empty:
            return pd.DataFrame(), f"ไม่พบข้อมูลราคาของ {ticker}-USD ในช่วงที่เลือก"
        if fx_raw is None or fx_raw.empty:
            return pd.DataFrame(), "ไม่พบข้อมูลเรท USD/THB (THB=X) ในช่วงที่เลือก"

        for d in (raw, fx_raw):
            if isinstance(d.columns, pd.MultiIndex):
                d.columns = d.columns.get_level_values(0)

        raw, fx_raw = _normalize_index(raw), _normalize_index(fx_raw)
        raw = raw[~raw.index.duplicated(keep="last")]
        fx_raw = fx_raw[~fx_raw.index.duplicated(keep="last")]

        df = raw[["Close", "High", "Low"]].copy()
        df.columns = ["Global_USD", "Day_High", "Day_Low"]
        df["USDTHB"] = fx_raw["Close"].reindex(df.index).ffill().bfill()
        df = df.dropna()
        if df.empty:
            return pd.DataFrame(), "ข้อมูลที่ได้ว่างเปล่าหลังทำความสะอาด"
        df["Volatility_Pct"] = (df["Day_High"] - df["Day_Low"]) / df["Global_USD"]
        return df, None

    @st.cache_data(ttl=900, show_spinner=False)
    def _fetch_latest_usdthb():
        fx_raw = yf.download("THB=X", period="5d", auto_adjust=False, progress=False)
        if fx_raw is None or fx_raw.empty:
            return None
        if isinstance(fx_raw.columns, pd.MultiIndex):
            fx_raw.columns = fx_raw.columns.get_level_values(0)
        val = fx_raw["Close"].dropna()
        return float(val.iloc[-1]) if not val.empty else None

    def get_reference_usdthb(preferred_df: pd.DataFrame | None = None) -> tuple[float, bool]:
        """คืน (usdthb_rate, is_fallback)

        ใช้แถวสุดท้ายของ `preferred_df` ก่อนถ้ามีข้อมูลอยู่แล้ว (เลี่ยง network
        call ซ้ำ) ไม่งั้นค่อยดึงเรทล่าสุดตรง ๆ และใช้ค่าคงที่ (พร้อมติดธง
        fallback) เฉพาะเมื่อทั้งสองทางล้มเหลว
        """
        if preferred_df is not None and not preferred_df.empty and "USDTHB" in preferred_df:
            return float(preferred_df["USDTHB"].iloc[-1]), False
        try:
            rate = _fetch_latest_usdthb()
        except Exception:
            rate = None
        if rate is not None:
            return rate, False
        return FALLBACK_USDTHB, True

    @st.cache_data(show_spinner=False)
    def to_csv_bytes(df: pd.DataFrame) -> bytes:
        return df.to_csv().encode("utf-8-sig")

def to_csv_bytes_with_assumptions(df: pd.DataFrame, assumptions: dict, report_title: str) -> bytes:
    """แนบ header สมมติฐาน/พารามิเตอร์ไว้บนหัวไฟล์ export

    ข้อกำหนด compliance/audit: ทุกชุดตัวเลขที่ export ต้องพกค่าพารามิเตอร์ที่
    ใช้ผลิตมันมาด้วย พร้อม model version เพื่อให้คนรีวิวอีก 6 เดือนข้างหน้าอ่าน
    CSV แล้วรู้ทันทีว่าสมมติฐานคืออะไร โดยไม่ต้องถามว่า "วันนั้นตั้งค่าอะไรไว้"
    """
    lines = [
        f"# {report_title}",
        f"# Model version,{MODEL_VERSION}",
        f"# Exported at (UTC),{datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "# --- Assumptions / Parameters used for this export ---",
    ]
    for k, v in assumptions.items():
        v_str = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
        lines.append(f"# {k},{v_str}")
    lines.append("# --- Data ---")
    return ("\n".join(lines) + "\n" + df.to_csv()).encode("utf-8-sig")

# =========================================================================
# LAYER 3 — UI THEME & COMPONENTS
# =========================================================================

THEME_CSS = """
<style>
    .block-container { padding-top: 2rem; padding-bottom: 3rem; }
    .xs-hero {
        background: linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%);
        border: 1px solid rgba(0,210,106,0.25);
        border-radius: 16px; padding: 1.5rem 1.75rem; margin-bottom: 1.25rem;
    }
    .xs-hero h1 { margin:0; font-size:1.9rem; font-weight:800; color:#FAFAFA; letter-spacing:-0.5px; }
    .xs-hero p  { margin:.4rem 0 0 0; color:#9CA3AF; font-size:0.92rem; }
    .xs-pill {
        display:inline-block; background:rgba(0,210,106,0.12); color:#00D26A;
        border:1px solid rgba(0,210,106,0.35); border-radius:999px;
        padding:2px 12px; font-size:0.72rem; font-weight:600; margin-right:6px; margin-top:10px;
    }
    .xs-ver { color:#6B7280; font-size:.7rem; margin-top:8px; }
    .stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom:1px solid #1f2937; }
    .stTabs [data-baseweb="tab"] {
        height: 46px; padding: 0 20px; background:#111827;
        border-radius: 10px 10px 0 0; font-weight:600;
    }
    .stTabs [aria-selected="true"] { background:#1f2937 !important; color:#00D26A !important; }
    div[data-testid="stMetricValue"] { font-size:1.4rem; }
    .xs-sec {
        font-size:1.05rem; font-weight:700; color:#FAFAFA;
        border-left:3px solid #00D26A; padding-left:10px; margin:1.2rem 0 .6rem 0;
    }
    iframe { border-radius: 12px; }

    .xs-gauge { margin:0 0 .35rem 0; }
    .xs-gauge .top { display:flex; justify-content:space-between; font-size:.8rem; color:#9CA3AF; margin-bottom:5px; }
    .xs-gauge .top b { color:#FAFAFA; font-variant-numeric:tabular-nums; }
    .xs-gauge .track { height:10px; background:#1f2937; border-radius:999px; overflow:hidden; }
    .xs-gauge .fill { height:100%; border-radius:999px; transition:width .4s ease; }
    .xs-gauge .sub { font-size:.74rem; color:#6B7280; margin-top:4px; }

    .xs-tl { position:relative; padding-left:34px; }
    .xs-tl::before { content:""; position:absolute; left:11px; top:14px; bottom:14px; width:2px;
                     background:linear-gradient(180deg,#00D26A 0%,#374151 100%); }
    .xs-tl .xs-step { position:relative; --c:#00D26A; border:1px solid #1f2937; border-radius:10px;
                      padding:12px 16px; margin-bottom:10px; background:#0f1621; }
    .xs-tl .xs-step.warn  { --c:#F59E0B; }
    .xs-tl .xs-step.block { --c:#FF4B4B; }
    .xs-tl .xs-step::before {
        content:attr(data-n); position:absolute; left:-34px; top:11px; width:24px; height:24px;
        border-radius:50%; background:#0f1621; border:2px solid var(--c); color:#FAFAFA;
        font-size:.72rem; font-weight:700; display:flex; align-items:center; justify-content:center;
        box-shadow:0 0 0 4px #0E1117;
    }
    .xs-step h4 { margin:0 0 2px 0; font-size:.95rem; color:#FAFAFA; font-weight:700;
                  display:flex; justify-content:space-between; gap:12px; align-items:baseline; }
    .xs-step .xs-tag { font-size:.7rem; font-weight:700; padding:2px 10px; border-radius:999px; white-space:nowrap; }
    .xs-step.pass  .xs-tag { background:rgba(0,210,106,.12);  color:#00D26A; }
    .xs-step.warn  .xs-tag { background:rgba(245,158,11,.12); color:#F59E0B; }
    .xs-step.block .xs-tag { background:rgba(255,75,75,.12);  color:#FF4B4B; }
    .xs-step p  { margin:6px 0 0 0; color:#9CA3AF; font-size:.84rem; }
    .xs-row { display:flex; justify-content:space-between; gap:14px; padding:3px 0;
              border-bottom:1px dotted #1f2937; font-size:.85rem; color:#D1D5DB; }
    .xs-row:last-child { border-bottom:none; }
    .xs-row b { color:#FAFAFA; font-variant-numeric:tabular-nums; }
    .xs-tot { border-top:1px solid #374151; margin-top:6px; padding-top:7px; font-weight:700; }
    .xs-audit-row { font-size:.78rem; color:#D1D5DB; border-bottom:1px dotted #1f2937; padding:4px 0; }
    .xs-audit-row b { color:#F59E0B; }
    .xs-foot { color:#4B5563; font-size:.72rem; text-align:center; margin-top:2.5rem;
               padding-top:1rem; border-top:1px solid #1f2937; }
</style>
"""

HERO_HTML = f"""
<div class="xs-hero">
  <h1>🏦 XSpring — Digital Asset Dealer Suite</h1>
  <p>Backtest 5 ปีย้อนหลัง + Liquidity &amp; Capital Planner + Time-Travel Order Journey</p>
  <span class="xs-pill">Back-to-Back Hedging</span>
  <span class="xs-pill">FX Limit Engine</span>
  <span class="xs-pill">NCR/NC Capital Planner</span>
  <span class="xs-pill">Time-Travel Simulation</span>
  <div class="xs-ver">Model v{MODEL_VERSION} · สูตรคำนวณทั้งหมดอยู่ใน LAYER 1 ของไฟล์นี้ (ดู "Methodology" ในแท็บ Capital Planner)</div>
</div>
"""

def _sv_tuple():
    try:
        nums = re.findall(r"\d+", st.__version__)
        return (int(nums[0]), int(nums[1]))
    except Exception:
        return (1, 40)

WIDE = ({"width": "stretch"} if (HAS_UI and _sv_tuple() >= (1, 49))
        else {"use_container_width": True})

# ---- 3.1 Input helpers ---------------------------------------------------

def _reformat_comma_key(key):
    raw = st.session_state.get(key, "")
    cleaned = raw.replace(",", "").replace(" ", "").strip()
    try:
        num = float(cleaned)
        st.session_state[key] = f"{num:,.0f}" if num == int(num) else f"{num:,.2f}"
    except ValueError:
        pass

def comma_number_input(label, value, min_value=None, key=None, help=None):
    """Text input ที่รับ/คงรูปแบบตัวเลขมีคอมมา แล้วคืนค่าเป็น float

    NOTE: `key` ต้องไม่ซ้ำและคงที่ต่อ widget — ดู naming convention ของ sidebar
    (`<tab-prefix>_<field>`) ที่กันไม่ให้ state ชนกันเงียบ ๆ ข้ามแท็บ
    """
    if key not in st.session_state:
        st.session_state[key] = f"{value:,.0f}"
    st.text_input(label, key=key, help=help, on_change=_reformat_comma_key, args=(key,))
    cleaned = st.session_state[key].replace(",", "").replace(" ", "").strip()
    try:
        num = float(cleaned)
    except ValueError:
        num = float(value)
    if min_value is not None and num < min_value:
        num = float(min_value)
    return num

# ---- 3.2 Display components ---------------------------------------------

def colored_metric(label, display_value, raw_value=None, sub_text=None, font_size="1.5rem"):
    color = "#FAFAFA" if raw_value is None else ("#00D26A" if raw_value >= 0 else "#FF4B4B")
    sub = (f'<div style="font-size:.78rem;color:{color};opacity:.85;margin-top:3px;">{sub_text}</div>'
           if sub_text else "")
    st.markdown(f"""
    <div style="padding:.35rem 0 .6rem 0;">
      <div style="font-size:.82rem;color:#9CA3AF;margin-bottom:4px;">{label}</div>
      <div style="font-size:{font_size};font-weight:700;color:{color};white-space:nowrap;
                  overflow:hidden;text-overflow:ellipsis;line-height:1.25;">{display_value}</div>
      {sub}
    </div>""", unsafe_allow_html=True)

def metric_card(col, label, value, raw_value=None, sub_text=None, font_size="1.5rem"):
    with col:
        with st.container(border=True):
            colored_metric(label, value, raw_value, sub_text, font_size)

def section(title):
    st.markdown(f'<div class="xs-sec">{title}</div>', unsafe_allow_html=True)

def verdict_box(ok: bool, title: str, detail: str, warn: bool = False):
    if warn and ok:
        bg, bd, ic = "rgba(245,158,11,.10)", "#F59E0B", "⚠️"
    elif ok:
        bg, bd, ic = "rgba(0,210,106,.10)", "#00D26A", "✅"
    else:
        bg, bd, ic = "rgba(255,75,75,.10)", "#FF4B4B", "🚨"
    st.markdown(
        f"<div style='background:{bg};border-left:4px solid {bd};border-radius:8px;"
        f"padding:12px 16px;margin-bottom:10px;'>"
        f"<div style='font-weight:700;color:{bd};font-size:.95rem;'>{ic} {title}</div>"
        f"<div style='color:#D1D5DB;font-size:.84rem;margin-top:4px;'>{detail}</div></div>",
        unsafe_allow_html=True)

def gauge_bar(label, used, limit, value_text="", sub="", warn_at=0.70, crit_at=0.90):
    if limit is None or limit <= 0:
        pct = 1.5 if used > 0 else 0.0
    else:
        pct = max(0.0, used / limit)
    color = "#00D26A" if pct < warn_at else ("#F59E0B" if pct < crit_at else "#FF4B4B")
    width = min(pct, 1.0) * 100
    st.markdown(
        f"<div class='xs-gauge'>"
        f"<div class='top'><span>{label}</span><b style='color:{color}'>{value_text or f'{pct*100:.0f}%'}</b></div>"
        f"<div class='track'><div class='fill' style='width:{width:.1f}%;background:{color};'></div></div>"
        + (f"<div class='sub'>{sub}</div>" if sub else "")
        + "</div>", unsafe_allow_html=True)

def step_html(number, title, status, note="", rows=None, total=None) -> str:
    tag = {"pass": "ผ่าน", "warn": "เฝ้าระวัง", "block": "ติดด่าน"}[status]
    body = ""
    if rows:
        body += "".join(f"<div class='xs-row'><span>{k}</span><b>{v}</b></div>" for k, v in rows)
    if total:
        body += f"<div class='xs-row xs-tot'><span>{total[0]}</span><b>{total[1]}</b></div>"
    return (f"<div class='xs-step {status}' data-n='{number}'>"
            f"<h4><span>{title}</span><span class='xs-tag'>{tag}</span></h4>"
            + (f"<p>{note}</p>" if note else "")
            + (f"<div style='margin-top:8px'>{body}</div>" if body else "")
            + "</div>")

def render_timeline(steps):
    html = "".join(step_html(s["n"], s["t"], s["s"], s.get("note", ""), s.get("rows"), s.get("total"))
                   for s in sorted(steps, key=lambda x: x["n"]))
    st.markdown(f"<div class='xs-tl'>{html}</div>", unsafe_allow_html=True)

def render_tradingview(symbol: str, container_id: str, height: int = 500, interval: str = "D", studies=None):
    """ฝัง TradingView widget

    NOTE เรื่องต้นทุน: widget นี้ re-render (และโหลด tv.js ใหม่) ทุกครั้งที่
    Streamlit rerun รวมถึง rerun ที่เกิดจาก widget อื่นในหน้าเดียวกัน (เช่นทุก
    ออเดอร์ใน Tab 3) ดังนั้น `container_id` ควรคงที่ต่อจุดเรียกเพื่อให้เบราว์เซอร์
    ใช้ script cache ของตัวเองได้ การเลี่ยง re-mount จริง ๆ ต้องย้ายการวาดกราฟ
    ออกจาก hot-rerun path ซึ่งใหญ่เกินขอบเขตรอบนี้
    """
    studies_js = str(studies or []).replace("'", '"')
    components.html(f"""
    <div id="{container_id}" style="height:{height}px;width:100%;"></div>
    <script src="https://s3.tradingview.com/tv.js"></script>
    <script>
      (function draw() {{
        var el = document.getElementById("{container_id}");
        if (!el || el.offsetHeight === 0 || typeof TradingView === "undefined") {{
          return setTimeout(draw, 300);
        }}
        new TradingView.widget({{
          "container_id": "{container_id}",
          "symbol": "{symbol}",
          "interval": "{interval}",
          "timezone": "Asia/Bangkok",
          "theme": "dark",
          "style": "1",
          "locale": "th_TH",
          "width": "100%",
          "height": {height},
          "toolbar_bg": "#0E1117",
          "enable_publishing": false,
          "hide_side_toolbar": false,
          "allow_symbol_change": true,
          "studies": {studies_js},
          "overrides": {{
            "paneProperties.background": "#0E1117",
            "paneProperties.backgroundType": "solid",
            "paneProperties.vertGridProperties.color": "#1f2937",
            "paneProperties.horzGridProperties.color": "#1f2937",
            "mainSeriesProperties.candleStyle.upColor": "#00D26A",
            "mainSeriesProperties.candleStyle.downColor": "#FF4B4B",
            "mainSeriesProperties.candleStyle.borderUpColor": "#00D26A",
            "mainSeriesProperties.candleStyle.borderDownColor": "#FF4B4B",
            "mainSeriesProperties.candleStyle.wickUpColor": "#00D26A",
            "mainSeriesProperties.candleStyle.wickDownColor": "#FF4B4B"
          }}
        }});
      }})();
    </script>""", height=height + 8)

# =========================================================================
# LAYER 4 — AUDIT TRAIL
#   ข้อกำหนด compliance: "Log การเปลี่ยนพารามิเตอร์ (ใครปรับอะไร เมื่อไหร่)"
#   เรายังไม่รู้ "ใคร" ถ้าไม่มี auth layer (อยู่นอกขอบเขตตามที่ตกลง) แต่รู้
#   "อะไร" และ "เมื่อไหร่" ได้ ซึ่งเป็นส่วนที่ใช้จริงตอนไล่ย้อนว่า "ทำไมตัวเลข
#   ระหว่าง export สองครั้งถึงต่างกัน" — append เฉพาะตอนค่าเปลี่ยนจริง
#   เพื่อไม่ให้ log ท่วมจาก rerun เปล่า ๆ
# =========================================================================

def _audit_log_param_changes(current_params: dict):
    prev = st.session_state.get("audit_prev_params")
    if "audit_log" not in st.session_state:
        st.session_state.audit_log = []

    if prev is not None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for key, new_val in current_params.items():
            old_val = prev.get(key)
            if old_val != new_val:
                st.session_state.audit_log.append({
                    "เวลา": now, "พารามิเตอร์": key,
                    "ค่าเดิม": old_val, "ค่าใหม่": new_val,
                })
    st.session_state.audit_prev_params = dict(current_params)

def render_audit_log_sidebar():
    log = st.session_state.get("audit_log", [])
    with st.expander(f"🧾 Audit Log — การเปลี่ยนพารามิเตอร์ ({len(log)})", expanded=False):
        st.caption(
            f"Model v{MODEL_VERSION} · บันทึกอัตโนมัติทุกครั้งที่พารามิเตอร์ที่มีผลต่อการคำนวณเปลี่ยนค่า "
            "(ไม่บันทึก 'ใคร' เพราะแอปนี้ยังไม่มีระบบ authentication แยกผู้ใช้)"
        )
        if not log:
            st.caption("ยังไม่มีการเปลี่ยนพารามิเตอร์ในเซสชันนี้")
            return
        for row in log[-10:][::-1]:
            st.markdown(
                f"<div class='xs-audit-row'>{row['เวลา']} — <b>{row['พารามิเตอร์']}</b>: "
                f"{row['ค่าเดิม']} → {row['ค่าใหม่']}</div>",
                unsafe_allow_html=True,
            )
        st.download_button(
            "⬇️ ดาวน์โหลด Audit Log ฉบับเต็ม (CSV)",
            to_csv_bytes(pd.DataFrame(log)), "xspring_audit_log.csv", "text/csv", **WIDE,
        )

# =========================================================================
# LAYER 5 — APP
# =========================================================================

def main():
    st.set_page_config(page_title="XSpring Dealer Suite", page_icon="\u267b\ufe0f",
                       layout="wide", initial_sidebar_state="expanded")
    st.markdown(THEME_CSS, unsafe_allow_html=True)
    st.markdown(HERO_HTML, unsafe_allow_html=True)

    # =====================================================================
    # 5.1 SIDEBAR
    # =====================================================================
    with st.sidebar:
        st.markdown("### ⚙️ Backtest Settings")

        asset = st.selectbox("เลือกเหรียญ", SUPPORTED_ASSETS, key="bt_asset")
        if asset in STABLECOINS:
            st.warning(f"⚠️ {asset} เป็น Stablecoin — ใช้กลยุทธ์ Depeg Arbitrage + Carry Yield")

        with st.expander("🌐 กระดานซื้อขาย", expanded=True):
            global_exchange = st.selectbox("กระดานโลกที่ใช้ Hedge",
                                           list(GLOBAL_EXCHANGE_FEE_PRESET.keys()), key="bt_global_exchange")
            local_exchange = st.selectbox("กระดานไทยอ้างอิงราคาลูกค้า", LOCAL_EXCHANGES, key="bt_local_exchange")

        with st.expander("📅 ช่วงเวลา Backtest", expanded=True):
            today = pd.Timestamp.now().date()
            preset_days = {"1 เดือน": 30, "3 เดือน": 90, "6 เดือน": 180,
                           "1 ปี": 365, "3 ปี": 365 * 3, "5 ปี": 365 * 5}
            preset = st.radio("เลือกช่วงเวลาด่วน",
                              ["กำหนดเอง", "1 เดือน", "3 เดือน", "6 เดือน", "1 ปี", "3 ปี", "5 ปี"],
                              index=6, horizontal=True)

            if preset != "กำหนดเอง":
                preset_start, preset_end = today - pd.Timedelta(days=preset_days[preset]), today
            else:
                preset_start, preset_end = today - pd.Timedelta(days=365 * 5), today

            ca, cb = st.columns(2)
            with ca:
                start_date = st.date_input("เริ่มต้น", value=preset_start,
                                           min_value=pd.Timestamp("2015-01-01").date(),
                                           max_value=today, disabled=(preset != "กำหนดเอง"))
            with cb:
                end_date = st.date_input("สิ้นสุด", value=preset_end,
                                         min_value=pd.Timestamp("2015-01-01").date(),
                                         max_value=today, disabled=(preset != "กำหนดเอง"))
            if preset != "กำหนดเอง":
                start_date, end_date = preset_start, preset_end

        dates_ok = start_date < end_date
        if not dates_ok:
            st.error("❌ วันเริ่มต้นต้องมาก่อนวันสิ้นสุด")

        with st.expander("💰 พารามิเตอร์ Dealer", expanded=True):
            trade_vol = comma_number_input("ปริมาณซื้อขายลูกค้า/วัน (USD eq.)", value=100000, key="bt_trade_vol")
            dealer_spread = st.number_input("Dealer Spread ที่เก็บจากลูกค้า (%)", value=0.5, step=0.1, key="bt_spread") / 100

            if "bt_prev_gx" not in st.session_state:
                st.session_state.bt_prev_gx = global_exchange
            if "bt_hedge_fee" not in st.session_state:
                st.session_state.bt_hedge_fee = GLOBAL_EXCHANGE_FEE_PRESET[global_exchange]
            if st.session_state.bt_prev_gx != global_exchange:
                st.session_state.bt_hedge_fee = GLOBAL_EXCHANGE_FEE_PRESET[global_exchange]
                st.session_state.bt_prev_gx = global_exchange

            hedge_fee = st.number_input("ค่าธรรมเนียม Global CEX (%)", key="bt_hedge_fee", step=0.01) / 100
            fx_limit_max = comma_number_input("FX Limit ต่อเดือน (USD)", value=5000000, min_value=1, key="bt_fx_limit")
            local_premium = st.number_input("Local Premium/Discount ฝั่งไทย (%)", value=0.1, step=0.1) / 100

        with st.expander("💳 ค่าธรรมเนียมกระดานไทย"):
            include_trading_fee_revenue = st.checkbox("รวมรายได้ค่าธรรมเนียมซื้อขาย 0.25%", value=True)
            withdrawal_fee_markup_pct = st.slider("Markup ค่าธรรมเนียมถอน (%)", 0, 200, 0) / 100
            settlements_per_day = st.number_input("รอบถอนเหรียญให้ลูกค้า/วัน", value=1, min_value=1, step=1)
            bank_type = st.selectbox("ธนาคารปลายทางถอนบาท", ["SCB", "ธนาคารอื่น", "KTB (กรุงไทย)"])

        with st.expander("🏦 สิทธิพิเศษ KTB", expanded=(bank_type.startswith("KTB"))):
            use_ktb_fx = st.checkbox("ใช้เรทแลกเปลี่ยน USD/THB พิเศษจาก KTB", value=True)
            ktb_fx_spread_bps = st.number_input("ส่วนต่างเรทที่ดีกว่าตลาด (bps)", value=15.0,
                                                step=1.0, min_value=0.0) if use_ktb_fx else 0.0
            ktb_wd_fee_thb = st.number_input("ค่าธรรมเนียมถอนบาท KTB (บาท)", value=15.0, step=1.0, min_value=0.0)

        if asset in STABLECOINS:
            with st.expander("🪙 กลยุทธ์ Stablecoin", expanded=True):
                peg_target = st.number_input("Peg Target (USD)", value=1.00, step=0.01)
                depeg_capture_pct = st.slider("Depeg Arbitrage Capture (%)", 0, 100, 80) / 100
                carry_apy = st.number_input("Carry Yield APY (%)", value=4.0, step=0.5) / 100
            slippage_sensitivity = 0.0
        else:
            with st.expander("📉 Execution Model", expanded=True):
                slippage_sensitivity = st.number_input("Slippage Sensitivity (% ของ Volatility)", value=10.0, step=1.0) / 100
            peg_target, depeg_capture_pct, carry_apy = 1.0, 0.0, 0.0

        st.divider()
        st.markdown("### 🏛️ งบดุลและ Flow")

        with st.expander("📥 Flow Assumptions", expanded=False):
            monthly_volume_thb = comma_number_input("ปริมาณธุรกรรมลูกค้าต่อเดือน (THB)", value=300_000_000, min_value=0)
            net_bias_pct = st.slider("Net Flow Bias (+/-)", -100, 100, 20) / 100
            flow_cv_pct = st.slider("ความผันผวนของปริมาณต่อวัน (CV, %)", 10, 150, 40) / 100
            settlement_days = st.number_input("Settlement Lag (วัน)", value=2, min_value=1, max_value=10, step=1)
            confidence = st.select_slider("Confidence Level ของ Safety Stock", options=[90, 95, 99, 99.9], value=99)
            z_alpha = Z_SCORE_MAP[confidence]

        with st.expander("💼 Capital Pool", expanded=False):
            total_capital_thb = comma_number_input("เงินทุนสภาพคล่องรวม (THB)", value=300_000_000, min_value=0)
            cex_margin_thb = comma_number_input("เงินทุนบนกระดานโลก / CEX Margin (THB)", value=60_000_000, min_value=0)
            liab_thb = comma_number_input("หนี้สินต่อลูกค้า (THB)", value=250_000_000, min_value=1)
            cex_margin_asset = st.selectbox("สินทรัพย์ Margin บนกระดานโลก", ["Stablecoin", "เหรียญเดียวกับที่เทรด"])
            cex_counterparty_haircut = st.number_input("Counterparty Haircut (%)", value=2.0, step=0.5, min_value=0.0) / 100

        with st.expander("⚖️ เกณฑ์เงินกองทุน ก.ล.ต.", expanded=False):
            is_custodian = st.checkbox("เก็บรักษาทรัพย์สินลูกค้า", value=True)
            fixed_min_nc = 25_000_000.0 if is_custodian else 5_000_000.0
            trading_risk_rate = st.number_input("อัตรา NC ความเสี่ยงซื้อขาย (%)", value=2.0, step=0.1, min_value=0.0) / 100
            cold_foreign_rate = st.number_input("อัตรา NC cold wallet ต่างประเทศ (%)", value=2.0, step=0.5, min_value=1.0) / 100
            hot_wallet_pct = st.slider("สัดส่วนสต็อกใน Hot Wallet (%)", 0, 100, 50) / 100
            cold_domestic_split_pct = st.slider("สัดส่วน Cold Wallet ฝากในประเทศ (%)", 0, 100, 100) / 100

        st.divider()
        _audit_log_param_changes(dict(
            asset=asset, global_exchange=global_exchange, start_date=str(start_date), end_date=str(end_date),
            trade_vol=trade_vol, dealer_spread=dealer_spread, hedge_fee=hedge_fee, fx_limit_max=fx_limit_max,
            local_premium=local_premium, include_trading_fee_revenue=include_trading_fee_revenue,
            withdrawal_fee_markup_pct=withdrawal_fee_markup_pct, bank_type=bank_type,
            use_ktb_fx=use_ktb_fx, ktb_fx_spread_bps=ktb_fx_spread_bps, ktb_wd_fee_thb=ktb_wd_fee_thb,
            slippage_sensitivity=slippage_sensitivity,
            monthly_volume_thb=monthly_volume_thb, net_bias_pct=net_bias_pct, flow_cv_pct=flow_cv_pct,
            settlement_days=settlement_days, confidence=confidence,
            total_capital_thb=total_capital_thb, cex_margin_thb=cex_margin_thb, liab_thb=liab_thb,
            cex_margin_asset=cex_margin_asset, cex_counterparty_haircut=cex_counterparty_haircut,
            is_custodian=is_custodian, trading_risk_rate=trading_risk_rate, cold_foreign_rate=cold_foreign_rate,
            hot_wallet_pct=hot_wallet_pct, cold_domestic_split_pct=cold_domestic_split_pct,
        ))
        render_audit_log_sidebar()

    # ---- derived values shared by every tab -----------------------------
    daily_volume_thb = monthly_volume_thb / 30.0
    custody_rate_blended = blended_custody_rate(hot_wallet_pct, cold_domestic_split_pct, cold_foreign_rate)
    hot_wallet_cap_breach = (liab_thb < HOT_WALLET_CAP_LIAB_THRESHOLD) and (hot_wallet_pct > HOT_WALLET_CAP)

    data, data_err = ((pd.DataFrame(), "ช่วงวันที่ไม่ถูกต้อง") if not dates_ok
                      else fetch_price_data(asset, start_date, end_date))

    tab1, tab2, tab3 = st.tabs([
        "📊 5-Year Backtest Simulator",
        "🧮 Liquidity & Capital Planner",
        "🛒 Time-Travel Order Simulator",
    ])

    # =====================================================================
    # 5.2 TAB 1 — BACKTEST
    # =====================================================================
    def _render_tab1():
        if data.empty:
            st.error(f"⚠️ {data_err or 'ไม่สามารถโหลดข้อมูลได้'}")
            return

        bt = data.copy()
        bt["Local_THB"] = bt["Global_USD"] * bt["USDTHB"] * (1 + local_premium)
        bt["Coin_Volume"] = trade_vol / bt["Global_USD"]
        bt["Gross_Notional_THB"] = bt["Coin_Volume"] * bt["Local_THB"]
        bt["Spread_Revenue_THB"] = bt["Gross_Notional_THB"] * dealer_spread
        bt["FX_Basis_PnL_THB"] = trade_vol * bt["USDTHB"] * local_premium
        bt["Hedge_Fee_Cost_THB"] = trade_vol * hedge_fee * bt["USDTHB"]
        bt["Hedge_Notional_USD"] = trade_vol * (1 + hedge_fee)
        bt["KTB_FX_Benefit_THB"] = trade_vol * bt["USDTHB"] * (ktb_fx_spread_bps / 10000.0)

        if asset in STABLECOINS:
            bt["Depeg_Deviation"] = peg_target - bt["Global_USD"]
            bt["Depeg_PnL_THB"] = bt["Coin_Volume"] * bt["Depeg_Deviation"] * bt["USDTHB"] * depeg_capture_pct
            bt["Carry_Yield_THB"] = trade_vol * (carry_apy / 365) * bt["USDTHB"]
            bt["Slippage_Cost_THB"] = 0.0
        else:
            bt["Depeg_Deviation"] = 0.0
            bt["Depeg_PnL_THB"] = 0.0
            bt["Carry_Yield_THB"] = 0.0
            bt["Slippage_Cost_THB"] = trade_vol * bt["Volatility_Pct"] * slippage_sensitivity * bt["USDTHB"]

        bt["Trading_Fee_Revenue_THB"] = (bt["Gross_Notional_THB"] * LOCAL_TRADING_FEE_PCT
                                         if include_trading_fee_revenue else 0.0)
        wd_network_cost = WITHDRAWAL_FEE_TABLE.get(asset, 0.0) * bt["Global_USD"] * bt["USDTHB"] * settlements_per_day
        bt["Withdrawal_Fee_Markup_Revenue_THB"] = wd_network_cost * withdrawal_fee_markup_pct
        bt["THB_WD_Fee"] = bt["USDTHB"].map(lambda fx: calc_thb_withdrawal_fee(trade_vol * fx, bank_type, ktb_wd_fee_thb))
        bt["THB_Fee_Markup_Revenue_THB"] = bt["THB_WD_Fee"] * settlements_per_day * withdrawal_fee_markup_pct
        bt["Fee_Revenue_THB"] = (bt["Trading_Fee_Revenue_THB"] + bt["Withdrawal_Fee_Markup_Revenue_THB"]
                                 + bt["THB_Fee_Markup_Revenue_THB"])
        bt["Revenue_THB"] = (bt["Spread_Revenue_THB"] + bt["FX_Basis_PnL_THB"] + bt["Fee_Revenue_THB"]
                             + bt["Depeg_PnL_THB"] + bt["Carry_Yield_THB"] + bt["KTB_FX_Benefit_THB"])
        bt["Cost_THB"] = bt["Hedge_Fee_Cost_THB"] + bt["Slippage_Cost_THB"]
        bt["Daily_PnL_THB"] = bt["Revenue_THB"] - bt["Cost_THB"]

        allowed, usage = apply_fx_limit(bt["Hedge_Notional_USD"], bt.index, fx_limit_max)
        bt["Trade_Allowed"], bt["Current_FX_Usage"] = allowed, usage
        bt["FX_Limit_Hit"] = 1 - allowed
        bt["Actual_Daily_PnL"] = np.where(allowed == 1, bt["Daily_PnL_THB"], 0.0)
        bt["Actual_Cum_PnL"] = bt["Actual_Daily_PnL"].cumsum()

        traded = bt[bt["Trade_Allowed"] == 1]
        total_revenue_thb, total_cost_thb = traded["Revenue_THB"].sum(), traded["Cost_THB"].sum()
        net_pnl_thb, total_notional = bt["Actual_Cum_PnL"].iloc[-1], traded["Gross_Notional_THB"].sum()
        margin_bps = (net_pnl_thb / total_notional * 10000) if total_notional else 0
        total_days, traded_days = len(bt), int(allowed.sum())
        limit_hit_days = int(bt["FX_Limit_Hit"].sum())
        win_days = int((bt["Actual_Daily_PnL"] > 0).sum())
        win_rate = win_days / traded_days * 100 if traded_days else 0
        avg_daily_pnl = traded["Daily_PnL_THB"].mean() if traded_days else 0
        best_day, worst_day = bt["Actual_Daily_PnL"].max(), bt["Actual_Daily_PnL"].min()
        running_max = bt["Actual_Cum_PnL"].cummax()
        max_drawdown = (bt["Actual_Cum_PnL"] - running_max).min()
        dd_series = (bt["Actual_Cum_PnL"] - running_max) / running_max.where(running_max > 0)
        dd_pct = dd_series.min() * 100
        dd_pct = 0.0 if pd.isna(dd_pct) else dd_pct

        st.success(f"✅ โหลดข้อมูล **{asset}** สำเร็จ ({total_days} วัน | เทรดได้จริง {traded_days} วัน)")
        if total_days < RISK_SAMPLE_WARN_DAYS:
            st.warning(
                f"⚠️ ช่วงข้อมูลมีแค่ {total_days} วัน ({RISK_SAMPLE_WARN_DAYS} วันขึ้นไปจึงจะเรียกว่านิ่งพอสำหรับสรุปผล) "
                "ตัวเลข P&L/สถิติด้านล่างอาจแกว่งแรงถ้าเลือกช่วงเวลาสั้น"
            )

        # ---- ราคาเรียลไทม์ ----
        section(f"📉 ราคาเรียลไทม์ — {asset}")
        tv_mode = st.radio("มุมมองกราฟ", ["กระดานไทย (Bitkub)", "กระดานโลก (Binance)", "เทียบ 2 กระดาน"],
                           horizontal=True, key="tv_mode_bt")
        local_sym = TV_LOCAL_SYMBOL.get(asset, f"BITKUB:{asset}THB")
        global_sym = TV_GLOBAL_SYMBOL.get(asset, f"BINANCE:{asset}USDT")

        if tv_mode == "กระดานไทย (Bitkub)":
            render_tradingview(local_sym, "tv_bt_local", 520, studies=["RSI@tv-basicstudies"])
        elif tv_mode == "กระดานโลก (Binance)":
            render_tradingview(global_sym, "tv_bt_global", 520, studies=["RSI@tv-basicstudies"])
        else:
            g1, g2 = st.columns(2)
            with g1:
                st.caption(f"🇹🇭 ราคาจริงฝั่งไทย — `{local_sym}`")
                render_tradingview(local_sym, "tv_cmp_local", 420)
            with g2:
                st.caption(f"🌐 ราคาโลก — `{global_sym}`")
                render_tradingview(global_sym, "tv_cmp_global", 420)

        # ---- Performance ----
        section("📈 Performance Summary")
        r1 = st.columns(4)
        metric_card(r1[0], "Net P&L (THB)", fmt_baht(net_pnl_thb, True), net_pnl_thb,
                    f"{margin_bps:,.1f} bps ของ notional", "1.7rem")
        metric_card(r1[1], "Total Revenue", fmt_baht(total_revenue_thb), total_revenue_thb,
                    "Spread + Fee + Basis + Carry")
        metric_card(r1[2], "Total Cost", fmt_baht(total_cost_thb), -abs(total_cost_thb), "Hedge Fee + Slippage")
        metric_card(r1[3], "Avg Daily P&L", fmt_baht(avg_daily_pnl, True), avg_daily_pnl,
                    f"เฉลี่ยจาก {traded_days} วันที่เทรดได้")

        r2 = st.columns(4)
        metric_card(r2[0], "Best Day", fmt_baht(best_day, True), best_day)
        metric_card(r2[1], "Worst Day", fmt_baht(worst_day, True), worst_day)
        metric_card(r2[2], "Max Drawdown", fmt_baht(max_drawdown),
                    max_drawdown if max_drawdown != 0 else -0.01, f"{dd_pct:.2f}% จาก peak")
        metric_card(r2[3], "Win Rate", f"{win_rate:.1f}%", None, f"{win_days}/{traded_days} วัน")

        r3 = st.columns(4)
        metric_card(r3[0], "Gross Notional หมุนเวียน", fmt_baht(total_notional), None,
                    "มูลค่าธุรกรรมรวม (ไม่ใช่กำไร)")
        metric_card(r3[1], "FX Limit Hit", f"{limit_hit_days} วัน", -1 if limit_hit_days else 0,
                    f"{(limit_hit_days/total_days*100) if total_days else 0:.1f}% ของช่วงเวลา")
        if asset in STABLECOINS:
            metric_card(r3[2], "Avg Depeg Deviation", f"{bt['Depeg_Deviation'].mean()*100:+.3f}%")
            metric_card(r3[3], "Total Carry Yield", fmt_baht(traded["Carry_Yield_THB"].sum()),
                        traded["Carry_Yield_THB"].sum())
        else:
            metric_card(r3[2], "Avg Daily Volatility", f"{bt['Volatility_Pct'].mean()*100:.2f}%")
            metric_card(r3[3], "Total Slippage Cost", fmt_baht(traded["Slippage_Cost_THB"].sum()),
                        -abs(traded["Slippage_Cost_THB"].sum()))

        # ---- Waterfall ----
        section("💧 Revenue & Cost Waterfall")
        wf_labels = ["Spread Revenue", "FX Basis P&L", "Fee Revenue"]
        wf_values = [traded["Spread_Revenue_THB"].sum(), traded["FX_Basis_PnL_THB"].sum(),
                     traded["Fee_Revenue_THB"].sum()]
        if use_ktb_fx:
            wf_labels += ["KTB FX Benefit"]
            wf_values += [traded["KTB_FX_Benefit_THB"].sum()]
        if asset in STABLECOINS:
            wf_labels += ["Depeg Arbitrage", "Carry Yield"]
            wf_values += [traded["Depeg_PnL_THB"].sum(), traded["Carry_Yield_THB"].sum()]
        else:
            wf_labels += ["Slippage Cost"]
            wf_values += [-traded["Slippage_Cost_THB"].sum()]
        wf_labels += ["Hedge Fee Cost", "Net P&L"]
        wf_values += [-traded["Hedge_Fee_Cost_THB"].sum(), 0]

        wf_text = [fmt_baht(v, True) for v in wf_values[:-1]] + [fmt_baht(sum(wf_values[:-1]), True)]
        fig_wf = go.Figure(go.Waterfall(
            orientation="v", measure=["relative"] * (len(wf_labels) - 1) + ["total"],
            x=wf_labels, y=wf_values, text=wf_text, textposition="outside",
            connector={"line": {"color": "#374151"}},
            increasing={"marker": {"color": "#00D26A"}},
            decreasing={"marker": {"color": "#FF4B4B"}},
            totals={"marker": {"color": "#3B82F6"}},
        ))
        fig_wf.update_layout(template="plotly_dark", height=440, showlegend=False,
                             margin=dict(t=40, b=20), yaxis_title="THB")
        st.plotly_chart(fig_wf, **WIDE)

        # ---- Cumulative P&L ----
        section("📊 Cumulative P&L")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=bt.index, y=bt["Actual_Cum_PnL"], name="Cumulative P&L",
                                 line=dict(color="#00D26A", width=2.2), fill="tozeroy",
                                 fillcolor="rgba(0,210,106,0.12)"))
        fig.add_trace(go.Scatter(x=bt.index, y=running_max, name="Peak Equity",
                                 line=dict(color="#6B7280", width=1, dash="dot")))
        hits = bt[bt["FX_Limit_Hit"] == 1]
        if not hits.empty:
            fig.add_trace(go.Scatter(x=hits.index, y=hits["Actual_Cum_PnL"], mode="markers",
                                     name="FX Limit Hit", marker=dict(color="#FF4B4B", size=5, symbol="x")))
        fig.update_layout(title=f"{asset} @ {global_exchange} · {start_date} → {end_date}",
                          template="plotly_dark", hovermode="x unified", height=480,
                          margin=dict(t=50, b=20), yaxis_title="THB",
                          legend=dict(orientation="h", y=1.02, yanchor="bottom"))
        st.plotly_chart(fig, **WIDE)

        with st.expander("📅 P&L รายเดือน"):
            m = bt.groupby([bt.index.year, bt.index.month])["Actual_Daily_PnL"].sum().unstack(fill_value=0)
            m.columns = [f"{c:02d}" for c in m.columns]
            fig_hm = go.Figure(go.Heatmap(
                z=m.values, x=list(m.columns), y=[str(i) for i in m.index],
                colorscale=[[0, "#FF4B4B"], [0.5, "#111827"], [1, "#00D26A"]], zmid=0,
                texttemplate="%{z:,.0f}", textfont={"size": 9}))
            fig_hm.update_layout(template="plotly_dark", height=60 * len(m) + 120,
                                 margin=dict(t=20, b=20), xaxis_title="เดือน", yaxis_title="ปี")
            st.plotly_chart(fig_hm, **WIDE)

        with st.expander("🔍 Daily Ledger (100 วันล่าสุด)"):
            cols = ["Global_USD", "Local_THB", "USDTHB", "Volatility_Pct", "Gross_Notional_THB",
                    "Spread_Revenue_THB", "FX_Basis_PnL_THB", "KTB_FX_Benefit_THB",
                    "Hedge_Fee_Cost_THB", "Slippage_Cost_THB", "Fee_Revenue_THB"]
            if asset in STABLECOINS:
                cols += ["Depeg_Deviation", "Depeg_PnL_THB", "Carry_Yield_THB"]
            cols += ["Actual_Daily_PnL", "Current_FX_Usage", "FX_Limit_Hit"]
            st.dataframe(bt[cols].sort_index(ascending=False).head(100), height=400, **WIDE)

            st.download_button(
                "⬇️ ดาวน์โหลด Daily Ledger ทั้งหมด พร้อม Assumptions (CSV)",
                to_csv_bytes_with_assumptions(
                    bt.sort_index(ascending=False),
                    dict(asset=asset, global_exchange=global_exchange,
                         start_date=str(start_date), end_date=str(end_date),
                         trade_vol_usd_per_day=trade_vol, dealer_spread_pct=dealer_spread * 100
