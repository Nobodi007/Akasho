"""
XSpring Dealer Suite — Single-File Build
=========================================
รวม calculation engine + Streamlit UI ไว้ในไฟล์เดียว แต่ยังแยก "ชั้น" ชัดเจน

LAYERS
------
  0. CONFIG & CONSTANTS     ค่าคงที่ของโมเดล (override ได้ด้วย config.yaml)
  1. ENGINE / PURE LOGIC    คณิตศาสตร์ล้วน ไม่แตะ streamlit / network
  2. DATA LAYER             yfinance / cache / CSV export
  3. UI THEME & COMPONENTS  CSS, metric card, timeline, gauge, TradingView
  4. AUDIT TRAIL            log การเปลี่ยนพารามิเตอร์
  5. APP                    sidebar + 4 tabs (อยู่ใน main() ทั้งหมด)

TESTABILITY
-----------
UI ถูกเรียกใต้ `if __name__ == "__main__"` เท่านั้น
  - Streamlit รันไฟล์นี้เป็น __main__  -> UI ทำงานปกติ
  - unittest ทำ `import xspring_dealer_suite as eng`    -> ได้เฉพาะ LAYER 0-1 ไม่มี side effect

MODEL_VERSION / CHANGELOG
-------------------------
v1.5.27             + [FEATURE] ตรึงราคาในแผงออเดอร์ (15 วินาที) และใช้ st.fragment เพื่อรีเฟรชเฉพาะแผง
                    + [FEATURE] ระบบบันทึกรายการโปรด (Favorites) ลงไฟล์
                    + [FEATURE] ระบบสุ่มออเดอร์ข้ามหลายเหรียญพร้อมกัน (Multi-Asset Batch Run) แบบ Log-Uniform
                    + [FEATURE] เพิ่มระบบฝากเงินบาท (THB) แบบ Pop-up Dialog ในหน้า Wallet
                    + [FIX] อัปเดตข้อมูลราคาวันปัจจุบัน, Limit Order แผงเทรด, และการสุ่มวันที่
                      ใช้ Radio Button ทำระบบนำทางแทน Tabs เพื่อแก้ปัญหาเด้งเปลี่ยนหน้า 100%
                      ปรับ Native Columns ใน Tab 4 แทนตาราง HTML เดิมเพื่อแก้ปัญหาคลิกไม่ติด
v1.5.26             + [FIX] อัปเดตระบบ Logo เป็น Base64 SVG + Multi-layer Background
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

import numpy as np
import pandas as pd

MODEL_VERSION = "1.5.27"

try:
    import yaml
except ImportError:
    yaml = None

try:
    import plotly.graph_objects as go
    import streamlit as st
    import streamlit.components.v1 as components
    import yfinance as yf
    HAS_UI = True
except ImportError:
    go = st = components = yf = None
    HAS_UI = False

try:
    _HERE = Path(__file__).resolve().parent
except NameError:
    _HERE = Path.cwd()

HAS_FRAGMENT = bool(HAS_UI and hasattr(st, "fragment"))


def _fragment(fn):
    return st.fragment(fn) if HAS_FRAGMENT else fn


def _rerun_fragment() -> None:
    if HAS_FRAGMENT:
        try:
            st.rerun(scope="fragment")
        except Exception:
            st.rerun()
    else:
        st.rerun()


# =========================================================================
# LAYER 0 — CONFIG & CONSTANTS
# =========================================================================

GLOBAL_EXCHANGE_FEE_PRESET = {
    "Binance": 0.10,
    "Coinbase": 0.60,
    "Kraken": 0.26,
    "OKX": 0.10,
    "กำหนดเอง (Custom)": 0.10,
}
LOCAL_EXCHANGES = ["Bitkub"]

SUPPORTED_ASSETS = [
    "BTC", "ETH", "SOL", "DOGE", "ADA", "HBAR", "LINK", "XLM", "XRP", "USDT", "USDC",
]
STABLECOINS = ["USDT", "USDC"]

COIN_NAMES = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana",
    "DOGE": "Dogecoin", "ADA": "Cardano", "HBAR": "Hedera",
    "LINK": "Chainlink", "XLM": "Stellar", "XRP": "XRP",
    "USDT": "Tether", "USDC": "USD Coin", "THB": "Thai Baht"
}

# ใช้ Base64 SVG ธงชาติไทยที่ถูกต้อง (แดง-ขาว-น้ำเงิน-ขาว-แดง)
THB_LOGO_SVG = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIj48Y2xpcFBhdGggaWQ9ImMiPjxjaXJjbGUgY3g9IjUwIiBjeT0iNTAiIHI9IjUwIi8+PC9jbGlwUGF0aD48ZyBjbGlwLXBhdGg9InVybCgjYykiPjxyZWN0IHdpZHRoPSIxMDAiIGhlaWdodD0iMTciIGZpbGw9IiNFRDFDMjQiLz48cmVjdCB5PSIxNyIgd2lkdGg9IjEwMCIgaGVpZ2h0PSIxNyIgZmlsbD0iI2ZmZiIvPjxyZWN0IHk9IjM0IiB3aWR0aD0iMTAwIiBoZWlnaHQ9IjMyIiBmaWxsPSIjMjQxRDRGIi8+PHJlY3QgeT0iNjYiIHdpZHRoPSIxMDAiIGhlaWdodD0iMTciIGZpbGw9IiNmZmYiLz48cmVjdCB5PSI4MyIgd2lkdGg9IjEwMCIgaGVpZ2h0PSIxNyIgZmlsbD0iI0VEMUMyNCIvPjwvZz48L3N2Zz4="

COIN_LOGOS = {s: f"https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/128/color/{s.lower()}.png" for s in SUPPORTED_ASSETS}
COIN_LOGOS["THB"] = THB_LOGO_SVG

_LOGO_BG = {"BTC": "#F7931A", "ETH": "#627EEA", "SOL": "#9945FF", "DOGE": "#C2A633",
            "ADA": "#0033AD", "HBAR": "#3a3a3a", "LINK": "#2A5ADA", "XLM": "#14B6E7",
            "XRP": "#23292F", "USDT": "#26A17B", "USDC": "#2775CA"}

LOCAL_TRADING_FEE_PCT = 0.0025
MIN_TRADE_THB = 50.0
WITHDRAWAL_FEE_TABLE = {
    "BTC": 0.00002, "ETH": 0.0004, "ADA": 1.5, "DOGE": 4, "LINK": 0.063,
    "USDT": 4, "XLM": 0.004, "SOL": 0.001, "HBAR": 0.06, "USDC": 1.2, "XRP": 0.2,
}

TV_LOCAL_SYMBOL = {
    "BTC": "BITKUB:BTCTHB", "ETH": "BITKUB:ETHTHB", "SOL": "BITKUB:SOLTHB",
    "DOGE": "BITKUB:DOGETHB", "ADA": "BITKUB:ADATHB", "XRP": "BITKUB:XRPTHB",
    "LINK": "BITKUB:LINKTHB", "XLM": "BITKUB:XLMTHB", "HBAR": "BITKUB:HBARTHB",
    "USDT": "BITKUB:USDTTHB", "USDC": "BITKUB:USDCTHB",
}
TV_GLOBAL_SYMBOL = {a: f"BINANCE:{a}USDT" for a in SUPPORTED_ASSETS}
TV_GLOBAL_SYMBOL["USDT"] = "BINANCE:USDTTRY"
TV_GLOBAL_SYMBOL["USDC"] = "BINANCE:USDCUSDT"

Z_SCORE_MAP = {90: 1.2816, 95: 1.645, 99: 2.326, 99.9: 3.09}

HOT_WALLET_NC_RATE = 1.00
COLD_DOMESTIC_NC_RATE = 0.01
HOT_WALLET_CAP = 0.50
HOT_WALLET_CAP_LIAB_THRESHOLD = 1_000_000_000

FALLBACK_USDTHB = 35.5
MIN_RISK_SAMPLE_DAYS = 30
RISK_SAMPLE_WARN_DAYS = 180

THB_WD_FEE_SCB = 20.0
THB_WD_FEE_OTHER_SMALL = 20.0
THB_WD_FEE_OTHER_LARGE = 70.0
THB_WD_LARGE_THRESHOLD = 2_000_000.0

NC_FIXED_MIN_CUSTODIAN_THB = 25_000_000.0
NC_FIXED_MIN_NON_CUSTODIAN_THB = 5_000_000.0

GLOBAL_EXCHANGE_MAKER_FEE_PRESET: dict[str, float] = {}

UI_DEFAULTS: dict[str, float] = {
    "dealer_spread_pct": 0.5,
    "local_premium_pct": 0.1,
    "fx_limit_usd": 5_000_000.0,
    "impact_penalty_pct": 0.5,
}

FX_PROXY: dict[str, Any] = {
    "enabled": False,
    "url": "",
    "symbol": "USDT_THB",
    "resolution": "1D",
}

class ConfigError(ValueError):
    pass

CONFIG_ENV_VAR = "XSPRING_CONFIG"
DEFAULT_CONFIG_PATH = _HERE / "config.yaml"
CONFIG_INFO: dict[str, Any] = {"source": None, "sha256": None, "applied_keys": []}

_SCALAR_SPECS: dict[str, tuple[str, Optional[float], Optional[float]]] = {
    "local_trading_fee_pct": ("float", 0.0, 0.05),
    "min_trade_thb": ("float", 0.0, None),
    "hot_wallet_nc_rate": ("float", 0.0, 1.0),
    "cold_domestic_nc_rate": ("float", 0.0, 1.0),
    "hot_wallet_cap": ("float", 0.0, 1.0),
    "hot_wallet_cap_liab_threshold": ("float", 0.0, None),
    "fallback_usdthb": ("float", 1.0, None),
    "min_risk_sample_days": ("int", 2, None),
    "risk_sample_warn_days": ("int", 2, None),
    "thb_wd_fee_scb": ("float", 0.0, None),
    "thb_wd_fee_other_small": ("float", 0.0, None),
    "thb_wd_fee_other_large": ("float", 0.0, None),
    "thb_wd_large_threshold": ("float", 0.0, None),
    "nc_fixed_min_custodian_thb": ("float", 0.0, None),
    "nc_fixed_min_non_custodian_thb": ("float", 0.0, None),
}

_MAP_SPECS: dict[str, tuple[float, Optional[float]]] = {
    "global_exchange_fee_preset": (0.0, 100.0),
    "global_exchange_maker_fee_preset": (0.0, 100.0),
    "withdrawal_fee_table": (0.0, None),
}

_UI_DEFAULT_SPECS: dict[str, tuple[float, Optional[float]]] = {
    "dealer_spread_pct": (0.0, 100.0),
    "local_premium_pct": (-100.0, 100.0),
    "fx_limit_usd": (1.0, None),
    "impact_penalty_pct": (0.0, 100.0),
}
_FX_PROXY_KEYS = {"enabled", "url", "symbol", "resolution"}


def _num(name: str, v: Any, kind: str, lo: Optional[float], hi: Optional[float]) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ConfigError(f"{name}: ต้องเป็นตัวเลข (ได้ {v!r})")
    f = float(v)
    if not math.isfinite(f):
        raise ConfigError(f"{name}: ต้องเป็นตัวเลขจำกัด (ได้ {v!r})")
    if kind == "int" and f != int(f):
        raise ConfigError(f"{name}: ต้องเป็นจำนวนเต็ม (ได้ {v!r})")
    if lo is not None and f < lo:
        raise ConfigError(f"{name}: ต้อง >= {lo} (ได้ {v!r})")
    if hi is not None and f > hi:
        raise ConfigError(f"{name}: ต้อง <= {hi} (ได้ {v!r})")
    return int(f) if kind == "int" else f

def validate_config(doc: Mapping[str, Any]) -> dict[str, Any]:
    valid_keys = (set(_SCALAR_SPECS) | set(_MAP_SPECS) | {"ui_defaults", "fx_proxy"})
    unknown = sorted(set(doc) - valid_keys)
    if unknown:
        raise ConfigError(f"key ที่ไม่รู้จักใน config: {unknown} — key ที่ใช้ได้: {sorted(valid_keys)}")

    out: dict[str, Any] = {}
    for key, (kind, lo, hi) in _SCALAR_SPECS.items():
        if key in doc:
            out[key] = _num(key, doc[key], kind, lo, hi)

    for key, (lo, hi) in _MAP_SPECS.items():
        if key in doc:
            m = doc[key]
            if not isinstance(m, Mapping) or not m:
                raise ConfigError(f"{key}: ต้องเป็น map ที่ไม่ว่าง")
            out[key] = {str(k): _num(f"{key}.{k}", v, "float", lo, hi) for k, v in m.items()}

    if "ui_defaults" in doc:
        u = doc["ui_defaults"]
        if not isinstance(u, Mapping):
            raise ConfigError("ui_defaults: ต้องเป็น map")
        bad = sorted(set(u) - set(_UI_DEFAULT_SPECS))
        if bad:
            raise ConfigError(f"ui_defaults: key ไม่รู้จัก {bad} — ใช้ได้: {sorted(_UI_DEFAULT_SPECS)}")
        out["ui_defaults"] = {k: _num(f"ui_defaults.{k}", v, "float", *_UI_DEFAULT_SPECS[k]) for k, v in u.items()}

    if "fx_proxy" in doc:
        f = doc["fx_proxy"]
        if not isinstance(f, Mapping):
            raise ConfigError("fx_proxy: ต้องเป็น map")
        bad = sorted(set(f) - _FX_PROXY_KEYS)
        if bad:
            raise ConfigError(f"fx_proxy: key ไม่รู้จัก {bad} — ใช้ได้: {sorted(_FX_PROXY_KEYS)}")
        fx: dict[str, Any] = {}
        if "enabled" in f:
            if not isinstance(f["enabled"], bool):
                raise ConfigError("fx_proxy.enabled: ต้องเป็น true/false")
            fx["enabled"] = f["enabled"]
        for k in ("url", "symbol", "resolution"):
            if k in f:
                if not isinstance(f[k], str):
                    raise ConfigError(f"fx_proxy.{k}: ต้องเป็นข้อความ")
                fx[k] = f[k].strip()
        if fx.get("url") and not fx["url"].lower().startswith("https://"):
            raise ConfigError("fx_proxy.url: ต้องขึ้นต้นด้วย https://")
        if fx.get("enabled") and not (fx.get("url") or FX_PROXY["url"]):
            raise ConfigError("fx_proxy.enabled = true แต่ยังไม่ได้ระบุ fx_proxy.url")
        out["fx_proxy"] = fx

    lo_d = out.get("min_risk_sample_days", MIN_RISK_SAMPLE_DAYS)
    hi_d = out.get("risk_sample_warn_days", RISK_SAMPLE_WARN_DAYS)
    if hi_d < lo_d:
        raise ConfigError("risk_sample_warn_days ต้อง >= min_risk_sample_days")
    return out

def apply_config(overrides: Mapping[str, Any]) -> None:
    g = globals()
    for key in _SCALAR_SPECS:
        if key in overrides:
            g[key.upper()] = overrides[key]
    for key in _MAP_SPECS:
        if key in overrides:
            g[key.upper()].update(overrides[key])
    UI_DEFAULTS.update(overrides.get("ui_defaults", {}))
    FX_PROXY.update(overrides.get("fx_proxy", {}))

def load_external_config(path: Optional[str] = None) -> tuple[dict[str, Any], Optional[Path], Optional[str]]:
    explicit = path or os.environ.get(CONFIG_ENV_VAR)
    p = Path(explicit) if explicit else DEFAULT_CONFIG_PATH
    if not p.is_file():
        if explicit:
            raise ConfigError(f"ไม่พบไฟล์ config: {p}")
        return {}, None, None
    if yaml is None:
        raise ConfigError(f"พบ {p.name} แต่ยังไม่ได้ติดตั้ง PyYAML — pip install pyyaml")
    raw = p.read_bytes()
    try:
        doc = yaml.safe_load(raw) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"อ่าน {p.name} ไม่ได้ (YAML ผิดรูปแบบ): {e}") from e
    if not isinstance(doc, dict):
        raise ConfigError(f"{p.name}: ระดับบนสุดต้องเป็น map")
    return validate_config(doc), p, hashlib.sha256(raw).hexdigest()[:12]

def _bootstrap_config() -> None:
    overrides, path, sha = load_external_config()
    apply_config(overrides)
    CONFIG_INFO.update(source=str(path) if path else None, sha256=sha,
                       applied_keys=sorted(overrides))

_bootstrap_config()


# =========================================================================
# LAYER 1 — ENGINE / PURE LOGIC
# =========================================================================

def fmt_num(value: Any, force_sign: bool = False) -> str:
    value = 0.0 if pd.isna(value) else float(value)
    sign = "- " if value < 0 else ("+ " if force_sign else "")
    v = abs(value)
    if v >= 1_000_000_000:
        num = f"{v / 1_000_000_000:,.2f}B"
    elif v >= 1_000_000:
        num = f"{v / 1_000_000:,.2f}M"
    elif v >= 1_000:
        num = f"{v / 1_000:,.1f}K"
    else:
        num = f"{v:,.2f}"
    return f"{sign}{num}"

def fmt_baht(value: Any, force_sign: bool = False) -> str:
    return f"฿ {fmt_num(value, force_sign)}"

def fmt_coin(value: float, symbol: str = "") -> str:
    v = abs(float(value))
    d = 6 if v < 1 else (4 if v < 1000 else 2)
    return f"{value:,.{d}f}" + (f" {symbol}" if symbol else "")

def calc_thb_withdrawal_fee(amount_thb: float, bank_type: str,
                            ktb_fee_thb: float = 15.0) -> float:
    if bank_type == "KTB (กรุงไทย)":
        return ktb_fee_thb
    if bank_type == "SCB":
        return THB_WD_FEE_SCB
    if amount_thb <= THB_WD_LARGE_THRESHOLD:
        return THB_WD_FEE_OTHER_SMALL
    return THB_WD_FEE_OTHER_LARGE

def apply_fx_limit(hedge_usd: pd.Series, index: pd.DatetimeIndex,
                   fx_limit: float) -> tuple[np.ndarray, np.ndarray]:
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

def _risk_stats(r: pd.Series) -> Optional[dict[str, Any]]:
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

def risk_profile(px: pd.Series) -> Optional[dict[str, Any]]:
    return _risk_stats(np.log(px / px.shift(1)))

def safety_stock_factor(net_bias: float, flow_cv: float, lag_days: float,
                        z_alpha: float) -> float:
    return (max(0.0, net_bias) * lag_days
            + z_alpha * flow_cv * np.sqrt(lag_days)) / 30.0

def crypto_haircut(es99: float, lag_days: float) -> float:
    return float(min(es99 * np.sqrt(lag_days), 0.95))

def blended_custody_rate(hot_pct: float, cold_domestic_pct: float,
                         cold_foreign_rate: float) -> float:
    return (hot_pct * HOT_WALLET_NC_RATE
            + (1 - hot_pct) * (cold_domestic_pct * COLD_DOMESTIC_NC_RATE
                               + (1 - cold_domestic_pct) * cold_foreign_rate))

def nc_snapshot(stock_thb: float, total_capital: float, cex_margin: float,
                liab: float, h_crypto: float, h_cex: float, fixed_min_nc: float,
                trading_risk_rate: float, daily_volume_thb: float,
                custody_rate: float) -> dict[str, float]:
    cash = total_capital - stock_thb
    actual = cash + stock_thb * (1 - h_crypto) + cex_margin * (1 - h_cex) - liab
    trading_nc = trading_risk_rate * daily_volume_thb
    custody_nc = stock_thb * custody_rate
    required = fixed_min_nc + trading_nc + custody_nc
    return {
        "cash": cash,
        "actual": actual,
        "required": required,
        "buffer": actual - required,
        "trading_nc": trading_nc,
        "custody_nc": custody_nc,
    }

def blend_hedge_fee(taker_fee: float, maker_fee: float, maker_ratio: float) -> float:
    r = min(max(float(maker_ratio), 0.0), 1.0)
    return taker_fee * (1.0 - r) + maker_fee * r

def default_maker_fee_pct(exchange: str) -> float:
    return GLOBAL_EXCHANGE_MAKER_FEE_PRESET.get(
        exchange, GLOBAL_EXCHANGE_FEE_PRESET.get(exchange, 0.0))

def depth_participation(order_usd: float, market_depth_usd: float) -> float:
    if not market_depth_usd or market_depth_usd <= 0 or order_usd <= 0:
        return 0.0
    return float(order_usd) / float(market_depth_usd)

def market_impact_rate(order_usd: float, market_depth_usd: float,
                       impact_penalty: float) -> float:
    if impact_penalty is None or impact_penalty <= 0:
        return 0.0
    return depth_participation(order_usd, market_depth_usd) * float(impact_penalty)

def align_usdthb(official: pd.Series, index: pd.DatetimeIndex,
                 proxy: Optional[pd.Series] = None) -> tuple[pd.Series, pd.Series]:
    off = official.astype(float).reindex(index)
    is_official = off.notna().to_numpy()
    fx_arr = off.ffill().bfill().to_numpy(dtype=float).copy()
    src = np.where(is_official, "official", "stale").astype(object)

    if proxy is not None and len(proxy):
        px = proxy.astype(float).reindex(index).ffill().to_numpy(dtype=float)
        pos = np.where(is_official, np.arange(len(index), dtype=float), np.nan)
        anchor = pd.Series(pos).ffill().to_numpy()
        cand = np.where(~is_official & ~np.isnan(anchor))[0]
        if len(cand):
            a_idx = anchor[cand].astype(int)
            with np.errstate(divide="ignore", invalid="ignore"):
                ratio = px[cand] / px[a_idx]
            ok = np.isfinite(ratio) & (ratio > 0)
            fx_arr[cand[ok]] = fx_arr[a_idx[ok]] * ratio[ok]
            src[cand[ok]] = "proxy"

    return (pd.Series(fx_arr, index=index, name="USDTHB"),
            pd.Series(src, index=index, name="FX_Source"))

def parse_udf_history(payload: Any) -> pd.Series:
    if not isinstance(payload, Mapping) or payload.get("s") != "ok":
        raise ValueError("response ไม่ใช่รูปแบบ UDF history ที่ s == 'ok'")
    t, c = payload.get("t"), payload.get("c")
    if not t or not c or len(t) != len(c):
        raise ValueError("response ไม่มีข้อมูลเวลา/ราคาปิด หรือความยาวไม่เท่ากัน")
    idx = pd.to_datetime(list(t), unit="s", utc=True).tz_convert(None).normalize()
    s = pd.Series(pd.to_numeric(pd.Series(list(c)), errors="coerce").to_numpy(),
                  index=idx, dtype=float)
    s = s[~s.index.duplicated(keep="last")].dropna()
    s = s[s > 0].sort_index()
    if s.empty:
        raise ValueError("ไม่มีแถวราคาที่ใช้ได้หลังทำความสะอาด")
    return s

def sim_defaults(asset_name: str, start_date_val: Any, spot_usd: float,
                 usdthb: float, target_stock_thb: float) -> dict[str, Any]:
    coin_price = spot_usd * usdthb
    return {
        "asset": asset_name,
        "inv_coins": {asset_name: (target_stock_thb / coin_price) if coin_price > 0 else 0.0},
        "target_thb": target_stock_thb,
        "fx_used_usd": 0.0,
        "cex_used_thb": 0.0,
        "pnl_thb": 0.0,
        "unhedged_thb": 0.0,
        "orders": [],
        "current_date": start_date_val,
        "customer_coins": {},
        "customer_thb": 1000000.0, 
        "open_orders": [],
    }

def sim_config_signature(ctx: Mapping[str, Any], target_stock_thb: float,
                         start_date: Any, end_date: Any) -> tuple:
    keys = [
        "asset", "local_premium", "spread", "hedge_fee",
        "fx_limit", "slip_sens", "include_fee_rev",
        "wd_markup", "bank_type", "ktb_wd_fee", "ktb_fx_bps",
        "capital", "cex_margin", "cex_liquidity_thb", "liab",
        "fixed_min_nc", "trading_risk_rate", "daily_volume_thb", "custody_rate",
        "hot_breach", "market_depth_usd", "impact_penalty",
    ]
    values = []
    for key in keys:
        value = ctx.get(key)
        is_number = isinstance(value, (int, float, np.integer, np.floating))
        if is_number and not isinstance(value, bool):
            value = round(float(value), 10)
        values.append(value)
    values.append(round(float(target_stock_thb), 2))
    values.append(str(start_date))
    values.append(str(end_date))
    return tuple(values)

def sim_normalize_state(sim: Any, asset: str, start_date_val: Any,
                        spot_usd: float, usdthb: float,
                        target_stock_thb: float) -> dict[str, Any]:
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
    sim.setdefault("customer_coins", {})
    sim.setdefault("customer_thb", 1000000.0)
    sim.setdefault("open_orders", [])

    sim.setdefault("inv_coins", {})
    if not isinstance(sim["inv_coins"], dict):
        sim["inv_coins"] = {sim.get("asset", asset): float(sim["inv_coins"])}

    coin_price = spot_usd * usdthb
    if asset not in sim["inv_coins"]:
        sim["inv_coins"][asset] = target_stock_thb / coin_price if coin_price > 0 else 0.0

    if not isinstance(sim["customer_coins"], dict):
        sim["customer_coins"] = {}
    clean_coins: dict[str, float] = {}
    for sym, qty in sim["customer_coins"].items():
        try:
            q = float(qty)
            if np.isfinite(q) and q > 0:
                clean_coins[sym] = q
        except (TypeError, ValueError):
            continue
    sim["customer_coins"] = clean_coins

    for key in ("fx_used_usd", "cex_used_thb", "pnl_thb", "unhedged_thb"):
        try:
            sim[key] = float(sim[key])
            if not np.isfinite(sim[key]):
                sim[key] = 0.0
        except (TypeError, ValueError):
            sim[key] = 0.0

    sim["asset"] = asset
    sim["target_thb"] = float(target_stock_thb)
    return sim

def execute_order(
    sim: dict[str, Any], side: str, amount_thb: float, order_date: pd.Timestamp,
    px_row: pd.Series, ctx: Mapping[str, Any], affect_wallet: bool = True,
) -> tuple[list[dict[str, Any]], Optional[dict[str, Any]]]:
    p = ctx
    side = "buy" if side == "buy" else "sell"
    current_asset = sim["asset"]

    try:
        amount_thb = float(amount_thb)
    except (TypeError, ValueError):
        amount_thb = 0.0

    spot = float(px_row["Global_USD"])
    fx = float(px_row["USDTHB"])
    daily_vol = float(px_row["Volatility_Pct"])
    coin_price_global = spot * fx

    if spot <= 0 or fx <= 0 or coin_price_global <= 0:
        blocked = dict(n=1, t="ไม่สามารถสร้างราคาได้", s="block",
                       note="ราคา Global หรือ USD/THB ไม่ถูกต้อง")
        return [blocked], None

    mid = coin_price_global * (1 + p["local_premium"])
    quote = mid * (1 + p["spread"]) if side == "buy" else mid * (1 - p["spread"])
    steps = []

    if amount_thb < MIN_TRADE_THB:
        steps.append(dict(
            n=1, t="คำสั่งถูกปฏิเสธ", s="block",
            note=f"มูลค่าต่ำกว่าขั้นต่ำ {MIN_TRADE_THB:,.0f} บาท/คำสั่ง ระบบไม่รับออเดอร์",
        ))
        return steps, None

    steps.append(dict(
        n=1, t="ตั้งราคาให้ลูกค้า", s="pass",
        note=(f"ดึงราคาย้อนหลัง ณ วันที่ {order_date.strftime('%Y-%m-%d')} "
              "มาเป็นฐาน + Local Premium + Dealer Spread"),
        rows=[
            ("วันที่จำลองออเดอร์", order_date.strftime("%Y-%m-%d")),
            ("ราคาโลก (USD)", f"$ {spot:,.2f}"),
            ("x อัตราแลกเปลี่ยน USD/THB", f"{fx:,.2f}"),
            (f"+ Local Premium {p['local_premium'] * 100:.2f}%", f"฿ {mid:,.2f}"),
            (f"{'+' if side == 'buy' else '-'} Dealer Spread {p['spread'] * 100:.2f}%",
             f"฿ {quote:,.2f}"),
        ],
        total=("ราคาที่ลูกค้าได้", f"฿ {quote:,.2f}"),
    ))

    trading_fee = amount_thb * LOCAL_TRADING_FEE_PCT
    settlement_thb = max(0.0, amount_thb - trading_fee)
    # Buy : ค่าธรรมเนียมหักจากเงินที่จ่าย -> ได้เหรียญจาก settlement
    # Sell: amount_thb = มูลค่าเหรียญที่ขาย (gross) -> ส่งมอบเหรียญเต็มจำนวน
    #       แล้วได้เงินหลังหักค่าธรรมเนียม
    coins = (amount_thb if side == "sell" else settlement_thb) / quote

    if coins <= 0:
        steps.append(dict(n=2, t="จับคู่และส่งมอบ", s="block",
                          note="จำนวนเหรียญที่คำนวณได้ไม่เป็นบวก"))
        return steps, None

    inv_before = float(sim["inv_coins"].get(current_asset, 0.0))
    target_coins = (float(sim["target_thb"]) / coin_price_global
                    if coin_price_global > 0 else 0.0)
    inv_after_customer = inv_before - coins if side == "buy" else inv_before + coins

    if side == "buy":
        required_topup_coins = max(0.0, target_coins - inv_after_customer)
        fx_left_usd = max(0.0, float(p["fx_limit"]) - float(sim["fx_used_usd"]))
        if spot > 0 and p["hedge_fee"] >= 0:
            max_hedge_by_fx = fx_left_usd / (spot * (1 + p["hedge_fee"]))
        else:
            max_hedge_by_fx = 0.0
        feasible_hedge_coins = min(required_topup_coins, max_hedge_by_fx)

        if inv_after_customer + feasible_hedge_coins < -1e-12:
            steps.append(dict(
                n=2, t="จับคู่และส่งมอบเข้ากระเป๋า", s="block",
                note=("สต็อกที่มีอยู่ + ความสามารถ hedge ที่เหลือไม่เพียงพอ "
                      "จึงไม่ส่งมอบเหรียญที่ไม่มีอยู่จริง"),
                rows=[
                    ("มูลค่าคำสั่ง", fmt_baht(amount_thb)),
                    (f"ค่าธรรมเนียมซื้อขาย {LOCAL_TRADING_FEE_PCT * 100:.2f}%",
                     "- " + fmt_baht(trading_fee)),
                    ("เหรียญที่ต้องส่งมอบ", fmt_coin(coins, current_asset)),
                    ("สต็อกก่อน", fmt_coin(inv_before, current_asset)),
                    ("FX quotaเหลือ", f"$ {fx_left_usd:,.0f}"),
                    ("สูงสุดที่ hedge ได้ด้วย FX",
                     fmt_coin(feasible_hedge_coins, current_asset)),
                ],
                total=("สถานะ", "Reject — Inventory/FX ไม่พอ"),
            ))
            record = {
                "วันที่": order_date.strftime("%Y-%m-%d"),
                "ฝั่ง": "ซื้อ",
                "เหรียญ": current_asset,
                "มูลค่า (บาท)": amount_thb,
                "ราคาที่ลูกค้าได้": quote,
                "เหรียญที่ส่งมอบ": 0.0,
                "Hedge (เหรียญ)": 0.0,
                "Hedge (USD)": 0.0,
                "CEX Liquidity ใช้ (บาท)": 0.0,
                "Unhedged (บาท)": 0.0,
                "Market Edge": 0.0,
                "รายได้": 0.0,
                "ต้นทุน": 0.0,
                "กำไรออเดอร์": 0.0,
                "สต็อกคงเหลือ": inv_before,
                "FX ใช้สะสม (USD)": sim["fx_used_usd"],
                "CEX Liquidity ใช้สะสม (บาท)": sim["cex_used_thb"],
                "NC Buffer": np.nan,
                "ผลด่าน": "Reject — Inventory/FX ไม่พอ",
            }
            return steps, record

    steps.append(dict(
        n=2, t="จับคู่และส่งมอบเข้ากระเป๋า", s="pass",
        note=("ลูกค้าชำระเงินบาทและได้รับเหรียญจาก inventory" if side == "buy"
              else "รับเหรียญจากลูกค้าและจ่ายเงินบาทตามราคาที่ quote"),
        rows=[
            ("มูลค่าที่ลูกค้าใส่", fmt_baht(amount_thb)),
            (f"ค่าธรรมเนียมซื้อขาย {LOCAL_TRADING_FEE_PCT * 100:.2f}%",
             "- " + fmt_baht(trading_fee)),
            ("ฐาน settlementหลังค่าธรรมเนียม", fmt_baht(settlement_thb)),
        ],
        total=("เหรียญที่ลูกค้าได้" if side == "buy" else "เหรียญที่ลูกค้าส่งมอบ",
               fmt_coin(coins, current_asset)),
    ))

    sim["inv_coins"][current_asset] = inv_after_customer
    short_coins = max(0.0, target_coins - sim["inv_coins"][current_asset])
    excess_coins = max(0.0, sim["inv_coins"][current_asset] - target_coins)

    steps.append(dict(
        n=3, t="ตัด/รับสต็อก",
        s="warn" if (short_coins > 0 or excess_coins > 0) else "pass",
        note=("Buy ลด inventory ก่อน แล้วค่อยเติมกลับด้วย hedge" if side == "buy"
              else "Sell เพิ่ม inventory ก่อน แล้วค่อยขายส่วนเกินบน CEX"),
        rows=[
            ("สต็อกก่อนออเดอร์", fmt_coin(inv_before, current_asset)),
            ("การเปลี่ยนแปลง",
             ("- " if side == "buy" else "+ ") + fmt_coin(coins, current_asset)),
            ("สต็อกหลังรับ/ส่งมอบ", fmt_coin(sim["inv_coins"][current_asset], current_asset)),
            ("Target Stock", fmt_coin(target_coins, current_asset)),
            ("Short / Excess",
             fmt_coin(short_coins if side == "buy" else excess_coins, current_asset)),
        ],
        total=("มูลค่าสต็อกปัจจุบัน",
               fmt_baht(max(0.0, sim["inv_coins"][current_asset]) * coin_price_global)),
    ))

    hedge_required_coins = short_coins if side == "buy" else excess_coins
    cex_used_thb_this_order = 0.0

    if side == "buy":
        fx_left_usd = max(0.0, float(p["fx_limit"]) - float(sim["fx_used_usd"]))
        if spot > 0 and p["hedge_fee"] >= 0:
            max_hedge_by_fx = fx_left_usd / (spot * (1 + p["hedge_fee"]))
        else:
            max_hedge_by_fx = 0.0
        hedged_coins = min(hedge_required_coins, max_hedge_by_fx)
        residual_unhedged_coins = max(0.0, hedge_required_coins - hedged_coins)

        hedge_thb = hedged_coins * coin_price_global
        hedge_usd = hedged_coins * spot * (1 + p["hedge_fee"])
        sim["fx_used_usd"] += hedge_usd
        if hedge_required_coins > 0:
            sim["inv_coins"][current_asset] += hedged_coins
        sim["unhedged_thb"] += residual_unhedged_coins * coin_price_global

        fx_status = "pass" if residual_unhedged_coins <= 1e-12 else "warn"
        hedge_status = fx_status
        if residual_unhedged_coins <= 1e-12:
            hedge_note = "เติม inventory กลับถึง target ด้วยการซื้อบน Global CEX"
        else:
            hedge_note = ("FX quota ไม่พอสำหรับเติม inventory ทั้งหมด "
                          "จึงเหลือ exposure ค้างบางส่วน")
        cex_liquidity_left = max(
            0.0, float(p["cex_liquidity_thb"]) - float(sim["cex_used_thb"]))
    else:
        cex_liquidity_left = max(
            0.0, float(p["cex_liquidity_thb"]) - float(sim["cex_used_thb"]))
        max_hedge_by_cex = (cex_liquidity_left / coin_price_global
                            if coin_price_global > 0 else 0.0)
        hedged_coins = min(hedge_required_coins, max_hedge_by_cex)
        residual_unhedged_coins = max(0.0, hedge_required_coins - hedged_coins)

        hedge_thb = hedged_coins * coin_price_global
        hedge_usd = hedged_coins * spot * (1 + p["hedge_fee"])
        cex_used_thb_this_order = hedge_thb
        sim["cex_used_thb"] += cex_used_thb_this_order
        sim["inv_coins"][current_asset] -= hedged_coins
        sim["unhedged_thb"] += residual_unhedged_coins * coin_price_global

        fx_status = "pass"
        hedge_status = "pass" if residual_unhedged_coins <= 1e-12 else "warn"
        if residual_unhedged_coins <= 1e-12:
            hedge_note = "ขาย inventory ส่วนเกินบน Global CEX โดยใช้ CEX liquidity"
        else:
            hedge_note = ("CEX liquidity ไม่พอขาย inventory ส่วนเกินทั้งหมด "
                          "จึงเหลือ long exposure ค้าง")
        fx_left_usd = max(0.0, float(p["fx_limit"]) - float(sim["fx_used_usd"]))

    steps.append(dict(
        n=4, t="ระบบตัดสินใจ Hedge อัตโนมัติ", s=hedge_status, note=hedge_note,
        rows=[
            ("ปริมาณที่ต้อง hedge", fmt_coin(hedge_required_coins, current_asset)),
            ("Hedge สำเร็จ", fmt_coin(hedged_coins, current_asset)),
            ("มูลค่า hedge", fmt_baht(hedge_thb)),
            ("Residual Unhedged", fmt_coin(residual_unhedged_coins, current_asset)),
            ("Direction", "Buy บน CEX" if side == "buy" else "Sell บน CEX"),
        ],
        total=("สถานะ",
               "Hedge ครบ" if residual_unhedged_coins <= 1e-12 else "Hedge บางส่วน"),
    ))

    unhedged_thb_this_order = residual_unhedged_coins * coin_price_global

    if side == "buy":
        if residual_unhedged_coins <= 1e-12:
            gate_note = "Buy-side hedge ใช้ outbound FX quota"
        else:
            gate_note = ("โควตา outbound เหลือไม่พอ "
                         "จึงเหลือ inventory exposure ที่ยังไม่ได้ hedge")
        steps.append(dict(
            n=5, t="ด่าน FX Limit — Outbound", s=fx_status, note=gate_note,
            rows=[
                ("FX ใช้ก่อนออเดอร์", f"$ {sim['fx_used_usd'] - hedge_usd:,.0f}"),
                ("ออเดอร์นี้ใช้", f"$ {hedge_usd:,.0f}"),
                ("FX ใช้สะสมหลังออเดอร์", f"$ {sim['fx_used_usd']:,.0f}"),
                ("FX Limit", f"$ {p['fx_limit']:,.0f}"),
                ("FX เหลือ",
                 f"$ {max(0.0, p['fx_limit'] - sim['fx_used_usd']):,.0f}"),
            ],
            total=("ส่วนที่ยัง Unhedged", fmt_baht(unhedged_thb_this_order)),
        ))
    else:
        steps.append(dict(
            n=5, t="ด่าน CEX Liquidity — Sell-side",
            s=fx_status if residual_unhedged_coins <= 1e-12 else "warn",
            note="Sell-side hedge ใช้ CEX liquidity เดิม ไม่กิน outbound FX quota",
            rows=[
                ("CEX Liquidity ก่อนออเดอร์",
                 fmt_baht(cex_liquidity_left + cex_used_thb_this_order)),
                ("ใช้ hedge ออเดอร์นี้", fmt_baht(cex_used_thb_this_order)),
                ("ใช้สะสม", fmt_baht(sim["cex_used_thb"])),
                ("CEX Liquidity เหลือ",
                 fmt_baht(max(0.0, p["cex_liquidity_thb"] - sim["cex_used_thb"]))),
                ("FX ใช้สะสม", f"$ {sim['fx_used_usd']:,.0f}"),
            ],
            total=("ส่วนที่ยัง Unhedged", fmt_baht(unhedged_thb_this_order)),
        ))

    stock_thb = max(0.0, sim["inv_coins"][current_asset]) * coin_price_global
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

    if nc_status == "pass":
        nc_note = "หลังออเดอร์ยังมี NC buffer เป็นบวกตาม planning model"
    else:
        nc_note = "NC/Capital เป็น planning model; ไม่ใช่ตัวรับรอง compliance อัตโนมัติ"

    steps.append(dict(
        n=6, t="ด่านเงินกองทุนสภาพคล่องสุทธิ (Planning Model)", s=nc_status,
        note=nc_note,
        rows=[
            ("สต็อกหลัง hedge", fmt_baht(stock_thb)),
            ("Cash ใน NC Model", fmt_baht(nc["cash"])),
            ("CEX Margin หลัง haircut",
             fmt_baht(p["cex_margin"] * (1 - p["h_cex"]))),
            ("NC ที่มีจริง", fmt_baht(nc["actual"])),
            ("NC ขั้นต่ำที่ต้องดำรง", fmt_baht(nc["required"])),
        ],
        total=("NC Buffer", fmt_baht(nc["buffer"], force_sign=True)),
    ))

    if side == "buy":
        market_edge = coins * (quote - coin_price_global)
    else:
        market_edge = coins * (coin_price_global - quote)

    fee_rev = trading_fee if p["include_fee_rev"] else 0.0

    wd_markup_rev = 0.0
    if side == "buy":
        wd_base = (p["wd_fee_per_coin"] * coins * coin_price_global
                   + calc_thb_withdrawal_fee(amount_thb, p["bank_type"], p["ktb_wd_fee"]))
        wd_markup_rev = wd_base * p["wd_markup"]

    depth_usd = float(p.get("market_depth_usd") or 0.0)
    impact_pen = float(p.get("impact_penalty") or 0.0)
    depth_on = depth_usd > 0 and impact_pen > 0
    hedge_part = 0.0
    impact_cost = 0.0
    if hedged_coins > 0:
        ktb_fx_benefit = hedge_thb * (p["ktb_fx_bps"] / 10000.0)
        hedge_fee_cost = hedge_thb * p["hedge_fee"]
        hedge_order_usd = hedged_coins * spot
        hedge_part = depth_participation(hedge_order_usd, depth_usd)
        impact_cost = hedge_thb * market_impact_rate(hedge_order_usd, depth_usd,
                                                     impact_pen)
        slippage_cost = hedge_thb * daily_vol * p["slip_sens"] + impact_cost
    else:
        ktb_fx_benefit = 0.0
        hedge_fee_cost = 0.0
        slippage_cost = 0.0

    revenue = market_edge + fee_rev + wd_markup_rev + ktb_fx_benefit
    cost = hedge_fee_cost + slippage_cost
    net = revenue - cost
    sim["pnl_thb"] += net

    if side == "buy":
        pnl_note = "P&L มาจาก realized quote-vs-global edge + fee หักต้นทุน hedge/slippage"
    else:
        pnl_note = ("Sell-side P&L สะท้อนส่วนต่างระหว่างราคาที่รับซื้อจากลูกค้า"
                    "กับราคาที่ขายต่อบน Global CEX")

    net_bps = (net / amount_thb * 10000) if amount_thb else 0.0

    steps.append(dict(
        n=7, t="กำไรขาดทุนของ Dealer ในออเดอร์นี้",
        s="pass" if net >= 0 else "warn", note=pnl_note,
        rows=[
            ("Market Edge จาก Quote vs Global",
             ("+ " if market_edge >= 0 else "- ") + fmt_baht(abs(market_edge))),
            ("ค่าธรรมเนียมซื้อขาย", "+ " + fmt_baht(fee_rev)),
            ("Markup ค่าธรรมเนียมถอน", "+ " + fmt_baht(wd_markup_rev)),
            ("KTB FX Benefit", "+ " + fmt_baht(ktb_fx_benefit)),
            ("ค่าธรรมเนียม CEX", "- " + fmt_baht(hedge_fee_cost)),
            ("Slippage", "- " + fmt_baht(slippage_cost)),
        ] + ([
            (f"  └ ส่วน Market Impact (กิน depth {hedge_part * 100:,.1f}%)",
             "- " + fmt_baht(impact_cost)),
        ] if depth_on else []),
        total=("กำไรสุทธิ",
               f"{fmt_baht(net, force_sign=True)} ({net_bps:,.1f} bps)"),
    ))

    if nc_status == "pass" and residual_unhedged_coins <= 1e-12:
        gate_result = "ผ่าน"
    elif nc_status != "block":
        gate_result = "เฝ้าระวัง"
    else:
        gate_result = "NC ไม่พอ"

    if affect_wallet:
        coins_book = sim.setdefault("customer_coins", {})
        cash_now = float(sim.get("customer_thb", 1000000.0))
        if side == "buy":
            coins_book[current_asset] = coins_book.get(current_asset, 0.0) + coins
            sim["customer_thb"] = cash_now - amount_thb
        else:
            coins_book[current_asset] = max(0.0, coins_book.get(current_asset, 0.0) - coins)
            sim["customer_thb"] = cash_now + settlement_thb

    record = {
        "วันที่": order_date.strftime("%Y-%m-%d"),
        "ฝั่ง": "ซื้อ" if side == "buy" else "ขาย",
        "เหรียญ": current_asset,
        "มูลค่า (บาท)": amount_thb,
        "ราคาที่ลูกค้าได้": quote,
        "เหรียญที่ส่งมอบ": coins,
        "Hedge (เหรียญ)": hedged_coins,
        "Hedge (USD)": hedge_usd,
        "CEX Liquidity ใช้ (บาท)": cex_used_thb_this_order,
        "Unhedged (บาท)": unhedged_thb_this_order,
        "Market Edge": market_edge,
        "รายได้": revenue,
        "ต้นทุน": cost,
        "กำไรออเดอร์": net,
        "สต็อกคงเหลือ": sim["inv_coins"][current_asset],
        "FX ใช้สะสม (USD)": sim["fx_used_usd"],
        "CEX Liquidity ใช้สะสม (บาท)": sim["cex_used_thb"],
        "NC Buffer": nc["buffer"],
        "ผลด่าน": gate_result,
    }
    sim["orders"].append(record)
    return steps, record


def _letter_logo(sym: str) -> str:
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
           f"<circle cx='50' cy='50' r='50' fill='{_LOGO_BG.get(sym, '#5e6673')}'/>"
           f"<text x='50' y='50' text-anchor='middle' dominant-baseline='central' "
           f"font-family='Arial,sans-serif' font-size='{38 if len(sym) <= 3 else 28}' "
           f"font-weight='700' fill='#fff'>{sym[:4]}</text></svg>")
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()

def get_coin_logo(symbol: str) -> str:
    return COIN_LOGOS.get(symbol) or _letter_logo(symbol)

def coin_icon_html(sym: str, size: int = 28) -> str:
    layers = f"url({get_coin_logo(sym)}),url({_letter_logo(sym)})"
    return (f'<span style="display:inline-block;width:{size}px;height:{size}px;'
            f'min-width:{size}px;border-radius:50%;background-color:#2b3139;'
            f'background-image:{layers};background-size:cover;background-position:center;"></span>')


NAV_LABELS = [
    "📊 5-Year Backtest Simulator",
    "🧮 Liquidity & Capital Planner",
    "🛒 Exchange UI Simulator",
    "💼 กระเป๋าเงิน (Wallet)",
]
NAV_EXCHANGE = NAV_LABELS[2]

def _go_to_exchange(sym: str) -> None:
    st.session_state["bt_asset"] = sym
    st.session_state["main_nav"] = NAV_EXCHANGE


# =========================================================================
# LAYER 2 — DATA LAYER (network / IO / export)
# =========================================================================

def _cache_data(*dargs, **dkwargs):
    def decorator(fn):
        if HAS_UI:
            return st.cache_data(*dargs, **dkwargs)(fn)
        return fn

    if dargs and callable(dargs[0]) and not dkwargs:
        fn, dargs = dargs[0], ()
        return fn if not HAS_UI else st.cache_data(fn)
    return decorator


def _normalize_index(d: pd.DataFrame) -> pd.DataFrame:
    idx = pd.to_datetime(d.index)
    try:
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_convert(None)
    except (TypeError, AttributeError):
        pass
    d.index = idx.normalize()
    return d


@_cache_data(ttl=3600, show_spinner=False)
def fetch_fx_proxy_series(start: Any, end: Any) -> tuple[Optional[pd.Series], Optional[str]]:
    if not (FX_PROXY["enabled"] and FX_PROXY["url"]):
        return None, "FX proxy ไม่ได้เปิดใช้ใน config"
    try:
        t0 = int(pd.Timestamp(start).tz_localize("UTC").timestamp())
        t1 = int(pd.Timestamp(end).tz_localize("UTC").timestamp()) + 86400
        qs = urllib.parse.urlencode({
            "symbol": FX_PROXY["symbol"], "resolution": FX_PROXY["resolution"],
            "from": t0, "to": t1,
        })
        url = FX_PROXY["url"] + ("&" if "?" in FX_PROXY["url"] else "?") + qs
        req = urllib.request.Request(url, headers={"User-Agent": "XSpringDealerSuite"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return parse_udf_history(payload), None
    except Exception as e:
        return None, f"ดึง FX proxy ไม่สำเร็จ: {e}"


@_cache_data(ttl=60, show_spinner="กำลังโหลดข้อมูลราคาย้อนหลัง…")
def fetch_price_data(ticker: str, start: Any, end: Any,
                     use_fx_proxy: bool = False) -> tuple[pd.DataFrame, Optional[str]]:
    try:
        end_incl = pd.Timestamp(end) + pd.Timedelta(days=1)
        raw = yf.download(f"{ticker}-USD", start=start, end=end_incl,
                          auto_adjust=False, progress=False)
        fx_raw = yf.download("THB=X", start=start, end=end_incl,
                             auto_adjust=False, progress=False)
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
    proxy = None
    if use_fx_proxy:
        proxy, _proxy_err = fetch_fx_proxy_series(start, end)
    df["USDTHB"], df["FX_Source"] = align_usdthb(fx_raw["Close"].dropna(), df.index, proxy)
    df = df.dropna()
    if df.empty:
        return pd.DataFrame(), "ข้อมูลที่ได้ว่างเปล่าหลังทำความสะอาด"

    df["Volatility_Pct"] = (df["Day_High"] - df["Day_Low"]) / df["Global_USD"]
    return df, None


@_cache_data(ttl=60, show_spinner=False)
def fetch_market_overview(tickers: list[str]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        try:
            data = yf.download(f"{t}-USD", period="2d", interval="1h", progress=False)
            if data.empty:
                continue
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            last_price = float(data["Close"].iloc[-1])
            prev_price = float(data["Close"].iloc[0])
            pct_change = (last_price - prev_price) / prev_price * 100 if prev_price else 0
            volume_24h = float(data["Volume"].tail(24).sum())
            rows.append({
                "symbol": t,
                "price_usd": last_price,
                "pct_change": pct_change,
                "volume": volume_24h,
            })
        except Exception:
            continue
    return pd.DataFrame(rows)


@_cache_data(ttl=900, show_spinner=False)
def _fetch_latest_usdthb() -> Optional[float]:
    fx_raw = yf.download("THB=X", period="5d", auto_adjust=False, progress=False)
    if fx_raw is None or fx_raw.empty:
        return None
    if isinstance(fx_raw.columns, pd.MultiIndex):
        fx_raw.columns = fx_raw.columns.get_level_values(0)
    val = fx_raw["Close"].dropna()
    return float(val.iloc[-1]) if not val.empty else None


def get_reference_usdthb(preferred_df: Optional[pd.DataFrame] = None) -> tuple[float, bool]:
    if (preferred_df is not None and not preferred_df.empty
            and "USDTHB" in preferred_df):
        return float(preferred_df["USDTHB"].iloc[-1]), False
    try:
        rate = _fetch_latest_usdthb()
    except Exception:
        rate = None
    if rate is not None:
        return rate, False
    return FALLBACK_USDTHB, True


@_cache_data(show_spinner=False)
def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv().encode("utf-8-sig")


def to_csv_bytes_with_assumptions(df: pd.DataFrame, assumptions: Mapping[str, Any],
                                  report_title: str) -> bytes:
    exported_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        f"# {report_title}",
        f"# Model version,{MODEL_VERSION}",
        f"# Config file,{CONFIG_INFO['source'] or 'built-in defaults'}",
        f"# Config sha256,{CONFIG_INFO['sha256'] or '-'}",
        f"# Exported at (UTC),{exported_at}",
        "# --- Assumptions / Parameters used for this export ---",
    ]
    for k, v in assumptions.items():
        if isinstance(v, (dict, list)):
            v_str = json.dumps(v, ensure_ascii=False)
        else:
            v_str = str(v)
        lines.append(f"# {k},{v_str}")
    lines.append("# --- Data ---")
    return ("\n".join(lines) + "\n" + df.to_csv()).encode("utf-8-sig")


# =========================================================================
# LAYER 3 — UI THEME & COMPONENTS
# =========================================================================

THEME_CSS = """
<style>
    .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 98% !important; }
    .xs-hero {
        background: linear-gradient(135deg, #0b0e11 0%, #181a20 50%, #1e2329 100%);
        border: 1px solid #2b3139;
        border-radius: 12px; padding: 1.5rem 1.75rem; margin-bottom: 1.25rem;
    }
    .xs-hero h1 { margin:0; font-size:1.9rem; font-weight:800; color:#EAECEF;
                  letter-spacing:-0.5px; }
    .xs-hero p  { margin:.4rem 0 0 0; color:#848e9c; font-size:0.92rem; }
    .xs-pill {
        display:inline-block; background:rgba(14,203,129,0.1); color:#0ecb81;
        border:1px solid rgba(14,203,129,0.2); border-radius:4px;
        padding:2px 10px; font-size:0.75rem; font-weight:600;
        margin-right:6px; margin-top:10px;
    }
    .xs-ver { color:#5e6673; font-size:.7rem; margin-top:8px; }

    /* Sleek Exchange Tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 16px; border-bottom: 1px solid #2b3139; padding-bottom: 0px; }
    .stTabs [data-baseweb="tab"] {
        height: 36px; padding: 0 4px; background: transparent; border: none;
        border-radius: 0; font-weight: 600; color: #848e9c; margin-bottom: -1px;
    }
    .stTabs [aria-selected="true"] {
        background: transparent !important; color: #EAECEF !important; border-bottom: 2px solid #0ecb81 !important;
    }

    div[data-testid="stMetricValue"] { font-size:1.4rem; color: #EAECEF; }
    .xs-sec {
        font-size:1.05rem; font-weight:700; color:#EAECEF;
        border-left:3px solid #0ecb81; padding-left:10px; margin:1.2rem 0 .6rem 0;
    }
    iframe { border-radius: 8px; }

    .xs-gauge { margin:0 0 .35rem 0; }
    .xs-gauge .top { display:flex; justify-content:space-between; font-size:.8rem;
                     color:#848e9c; margin-bottom:5px; }
    .xs-gauge .top b { color:#EAECEF; font-variant-numeric:tabular-nums; }
    .xs-gauge .track { height:6px; background:#2b3139; border-radius:2px; overflow:hidden; }
    .xs-gauge .fill { height:100%; border-radius:2px; transition:width .4s ease; }
    .xs-gauge .sub { font-size:.74rem; color:#5e6673; margin-top:4px; }

    .xs-tl { position:relative; padding-left:24px; }
    .xs-tl::before { content:""; position:absolute; left:7px; top:14px; bottom:14px;
                     width:2px; background:#2b3139; }
    .xs-tl .xs-step { position:relative; --c:#0ecb81; border:1px solid #2b3139;
                      border-radius:8px; padding:12px 16px; margin-bottom:10px;
                      background:#181a20; }
    .xs-tl .xs-step.warn  { --c:#fcd535; }
    .xs-tl .xs-step.block { --c:#f6465d; }
    .xs-tl .xs-step::before {
        content:attr(data-n); position:absolute; left:-24px; top:11px;
        width:18px; height:18px; border-radius:50%; background:#181a20;
        border:2px solid var(--c); color:#EAECEF; font-size:.65rem; font-weight:700;
        display:flex; align-items:center; justify-content:center;
    }
    .xs-step h4 { margin:0 0 2px 0; font-size:.9rem; color:#EAECEF; font-weight:600;
                  display:flex; justify-content:space-between; gap:12px;
                  align-items:baseline; }
    .xs-step .xs-tag { font-size:.65rem; font-weight:600; padding:2px 8px;
                       border-radius:4px; white-space:nowrap; }
    .xs-step.pass  .xs-tag { background:rgba(14,203,129,.1);  color:#0ecb81; }
    .xs-step.warn  .xs-tag { background:rgba(252,213,53,.1); color:#fcd535; }
    .xs-step.block .xs-tag { background:rgba(246,70,93,.1);  color:#f6465d; }
    .xs-step p  { margin:4px 0 0 0; color:#848e9c; font-size:.8rem; }
    .xs-row { display:flex; justify-content:space-between; gap:14px; padding:3px 0;
              border-bottom:1px dashed #2b3139; font-size:.8rem; color:#b7bdc6; }
    .xs-row:last-child { border-bottom:none; }
    .xs-row b { color:#EAECEF; font-variant-numeric:tabular-nums; }
    .xs-tot { border-top:1px solid #2b3139; margin-top:6px; padding-top:7px; font-weight:600; }
    .xs-audit-row { font-size:.75rem; color:#b7bdc6; border-bottom:1px dashed #2b3139;
                    padding:4px 0; }
    .xs-audit-row b { color:#fcd535; }
    .xs-foot { color:#5e6673; font-size:.7rem; text-align:center; margin-top:2.5rem;
               padding-top:1rem; border-top:1px solid #2b3139; }

    /* Custom Exchange Simulator UI Styling */
    .ex-header { display: flex; justify-content: space-between; align-items: center; background: #181a20; padding: 12px 24px; border-bottom: 1px solid #2b3139; margin-bottom: 16px; border-radius: 8px; }
    .ex-stat { display: flex; flex-direction: column; }
    .ex-stat-label { font-size: 0.75rem; color: #848e9c; }
    .ex-stat-val { font-size: 0.9rem; font-weight: 600; color: #EAECEF; }
    .ex-green { color: #0ecb81 !important; }
    .ex-red { color: #f6465d !important; }

    .oe-tabs { display: flex; gap: 16px; border-bottom: 1px solid #2b3139; padding-bottom: 8px; margin-bottom: 16px; }
    .oe-tab { font-size: 0.9rem; font-weight: 600; color: #848e9c; cursor: pointer; }
    .oe-tab.active { color: #EAECEF; border-bottom: 2px solid #fcd535; padding-bottom: 6px; margin-bottom: -8px; }
    .oe-bal { display: flex; justify-content: space-between; font-size: 0.8rem; color: #848e9c; margin-bottom: 16px; }

    /* ---------- Market list (Bitkub style) ---------- */
    [class*="st-key-mkrow_"] {
        position: relative !important;
        border-bottom: 1px solid #1f2329;
        cursor: pointer;
    }
    [class*="st-key-mkrow_"]:hover { background: #2b3139; }
    [class*="st-key-mkrow_"] > [data-testid="stVerticalBlock"] { gap: 0 !important; }

    /* ปุ่มจริงถูกดึงออกจาก flow แล้วซ่อน วางทับแถว */
    [class*="st-key-fav_"], [class*="st-key-sel_"] {
        position: absolute !important;
        top: 0 !important; bottom: 0 !important; margin: 0 !important; height: 100% !important;
    }
    [class*="st-key-fav_"] { left: 0 !important; width: 36px !important; z-index: 10 !important; }
    [class*="st-key-sel_"] { left: 36px !important; right: 0 !important; width: auto !important; z-index: 9 !important; }

    /* ทำให้ overlay คลุมทั้งแถวจริง ๆ: กว้าง+สูง 100% ทุกชั้นของ wrapper ปุ่ม */
    [class*="st-key-fav_"] *, [class*="st-key-sel_"] * {
        width: 100% !important; height: 100% !important; margin: 0 !important; padding: 0 !important;
    }
    [class*="st-key-fav_"] button, [class*="st-key-sel_"] button {
        display: block !important; border: none !important; background: transparent !important;
        color: transparent !important; opacity: 0 !important; cursor: pointer !important;
    }
    
    /* บังคับไม่ให้ข้อความดักจับการคลิก */
    [class*="st-key-mkrow_"] .mk-row, [class*="st-key-mkrow_"] .mk-row * { 
        pointer-events: none !important; 
    }

    .mk-head, .mk-row { display: flex; align-items: center; }
    .mk-head { font-size: .72rem; color: #848e9c; padding: 6px 8px 6px 0; }
    .mk-row { padding: 8px 8px 8px 0; }
    .mk-star { width: 36px; flex-shrink: 0; text-align: center; font-size: 1.15rem; color: #5e6673; }
    .mk-star.on { color: #fcd535; }
    .mk-asset { flex: 1; min-width: 0; display: flex; align-items: center; gap: 8px; }
    .mk-asset > div { min-width: 0; }
    .mk-sym { font-weight: 700; color: #EAECEF; font-size: .9rem; line-height: 1.15; white-space: nowrap; }
    .mk-sym span { color: #848e9c; font-weight: 500; }
    .mk-name { font-size: .68rem; color: #848e9c; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .mk-vol { color: #b7bdc6; }
    .mk-right { flex-shrink: 0; margin-left: 8px; text-align: right; }
    .mk-price { font-weight: 700; color: #EAECEF; font-size: .88rem; line-height: 1.15;
                white-space: nowrap; font-variant-numeric: tabular-nums; }
    .mk-pct { font-size: .75rem; font-weight: 600; white-space: nowrap;
              font-variant-numeric: tabular-nums; }
    .mk-sel { background: #0a5c33 !important; }

    /* Wallet Tab Styles */
    .wl-box { background: #181a20; border: 1px solid #2b3139; border-radius: 8px; padding: 20px; }
    .wl-total-val { font-size: 2.2rem; font-weight: 700; color: #EAECEF; font-variant-numeric: tabular-nums; margin: 4px 0; }
    .st-key-wl_table { gap: 0 !important; }
    .st-key-wlhead { padding: 12px 16px 8px; background: #181a20; border: 1px solid #2b3139; border-radius: 8px 8px 0 0; }
    .wl-h { font-size: 0.75rem; color: #848e9c; }
    [class*="st-key-wlrow_"] { padding: 8px 16px; background: #181a20; border: 1px solid #2b3139; border-top: none; }
    [class*="st-key-wlrow_"]:hover { background: #2b3139; }
    [class*="st-key-wlbtn_"] button { justify-content: flex-start; padding: 0; color: #EAECEF !important; font-weight: 700; }
    .wl-cell { color: #EAECEF; font-size: 0.85rem; text-align: right; font-variant-numeric: tabular-nums; }
    .wl-acts { display: flex; justify-content: flex-end; gap: 16px; font-weight: 600; }
    .wl-acts span:not(:last-child) { color: #0ecb81; }
    .wl-name { line-height: 1.2; color: #EAECEF; font-weight: 600; font-size: 0.9rem; }
    .wl-name span { font-size: 0.7rem; color: #848e9c; font-weight: 500; }

    /* ---------- แปลง Main Navigation Radio ให้เป็น Tabs ตามรูป ---------- */
    .st-key-main_nav [role="radiogroup"] {
        gap: 16px !important; 
        flex-wrap: nowrap !important;
        border-bottom: 1px solid #2b3139 !important; 
        padding-bottom: 0px !important; 
        margin-bottom: 16px !important;
    }
    
    .st-key-main_nav label[data-baseweb="radio"] {
        background: transparent !important; 
        border: none !important;
        padding: 0 4px 6px 4px !important; 
        margin: 0 0 -1px 0 !important;
        border-radius: 0 !important; 
        border-bottom: 2px solid transparent !important;
        align-items: center !important;
        cursor: pointer !important;
    }
    
    /* ซ่อนปุ่มกลม (Radio Circle) เด็ดขาด 100% */
    .st-key-main_nav label[data-baseweb="radio"] > div:first-child {
        display: none !important;
        width: 0 !important;
        height: 0 !important;
        opacity: 0 !important;
    }
    
    /* ปรับแต่งข้อความเริ่มต้น (สีเทา) */
    .st-key-main_nav label[data-baseweb="radio"] p {
        font-weight: 600 !important; 
        color: #848e9c !important; 
        font-size: 0.95rem !important;
        margin: 0 !important;
    }
    
    /* Hover State (ข้อความสีแดงตอนเอาเมาส์ชี้แบบในรูป) */
    .st-key-main_nav label[data-baseweb="radio"]:hover p {
        color: #ff4b4b !important;
    }
    
    /* Active State (เส้นใต้สีเขียว ข้อความสีขาว สำหรับแท็บที่ถูกเลือก) */
    .st-key-main_nav label[data-baseweb="radio"]:has(input:checked) {
        border-bottom: 2px solid #0ecb81 !important;
    }
    .st-key-main_nav label[data-baseweb="radio"]:has(input:checked) p {
        color: #EAECEF !important;
    }
    
    /* ---------- แปลง Order Type Radio ให้เป็น Tabs แบบ Main Nav ---------- */
    .st-key-op_type [role="radiogroup"] {
        gap: 16px !important; 
        flex-wrap: nowrap !important;
        border-bottom: 1px solid #2b3139 !important; 
        padding-bottom: 0px !important; 
        margin-bottom: 16px !important;
    }
    .st-key-op_type label[data-baseweb="radio"] {
        background: transparent !important; 
        border: none !important;
        padding: 0 4px 6px 4px !important; 
        margin: 0 0 -1px 0 !important;
        border-radius: 0 !important; 
        border-bottom: 2px solid transparent !important;
        align-items: center !important;
        cursor: pointer !important;
    }
    .st-key-op_type label[data-baseweb="radio"] > div:first-child {
        display: none !important;
        width: 0 !important;
        height: 0 !important;
        opacity: 0 !important;
    }
    .st-key-op_type label[data-baseweb="radio"] p {
        font-weight: 600 !important; 
        color: #848e9c !important; 
        font-size: 0.95rem !important;
        margin: 0 !important;
    }
    .st-key-op_type label[data-baseweb="radio"]:hover p {
        color: #ff4b4b !important;
    }
    .st-key-op_type label[data-baseweb="radio"]:has(input:checked) {
        border-bottom: 2px solid #0ecb81 !important;
    }
    .st-key-op_type label[data-baseweb="radio"]:has(input:checked) p {
        color: #EAECEF !important;
    }

    /* ---------- Order panel (Bitkub-style) ---------- */
    .op-tabs { display:flex; gap:28px; border-bottom:1px solid #2b3139; margin-bottom:14px; }
    .op-tab { font-size:1rem; font-weight:600; color:#848e9c; padding:8px 4px; }
    .op-tab.active { color:#EAECEF; border-bottom:2px solid #0ecb81; margin-bottom:-1px; }
    .op-row { display:flex; justify-content:space-between; font-size:.85rem; color:#848e9c; margin-bottom:6px; }
    .op-row b { color:#0ecb81; font-weight:600; font-variant-numeric:tabular-nums; }
    .op-row.mut b { color:#848e9c; font-weight:500; }
    .op-ro { display:flex; justify-content:space-between; align-items:center; background:#181a20;
             border:1px solid #2b3139; border-radius:6px; padding:12px 14px; margin:8px 0;
             font-size:.88rem; color:#b7bdc6; }
    .op-ro b { color:#EAECEF; font-variant-numeric:tabular-nums; }
    .op-warn { color:#f6465d; font-size:.78rem; margin:2px 0 6px; }
    .st-key-op_buy_btn button, .st-key-op_sell_btn button {
        width:100% !important; padding:12px !important; font-weight:700 !important;
        color:#fff !important; border:none !important; }
    .st-key-op_buy_btn button  { background:#0ecb81 !important; }
    .st-key-op_sell_btn button { background:#f6465d !important; }
    .st-key-op_buy_btn button:disabled, .st-key-op_sell_btn button:disabled { opacity:.35 !important; }
    
    /* ปุ่ม ฝาก / ถอน / ••• ในตาราง Wallet */
    .wl-act { text-align:center; font-weight:600; font-size:.85rem; color:#0ecb81; }
    .wl-act.wl-more { color:#EAECEF; }
    .st-key-wl_deposit button { padding:0 !important; justify-content:center; background:transparent !important; border:none !important; }
    .st-key-wl_deposit button, .st-key-wl_deposit button p { color:#0ecb81 !important; font-weight:600 !important; font-size:.85rem !important; }
</style>
"""

def _sv_tuple():
    try:
        nums = re.findall(r"\d+", st.__version__)
        return (int(nums[0]), int(nums[1]))
    except Exception:
        return (1, 40)

if HAS_UI and _sv_tuple() >= (1, 49):
    WIDE = {"width": "stretch"}
else:
    WIDE = {"use_container_width": True}

def _reformat_comma_key(key):
    raw = st.session_state.get(key, "")
    cleaned = raw.replace(",", "").replace(" ", "").strip()
    try:
        num = float(cleaned)
        st.session_state[key] = f"{num:,.0f}" if num == int(num) else f"{num:,.2f}"
    except ValueError:
        pass

def comma_number_input(label, value, min_value=None, key=None, help=None):
    if key not in st.session_state:
        st.session_state[key] = f"{value:,.0f}"
    st.text_input(label, key=key, help=help,
                  on_change=_reformat_comma_key, args=(key,))
    cleaned = st.session_state[key].replace(",", "").replace(" ", "").strip()
    try:
        num = float(cleaned)
    except ValueError:
        num = float(value)
    if min_value is not None and num < min_value:
        num = float(min_value)
    return num

def colored_metric(label, display_value, raw_value=None, sub_text=None, font_size="1.5rem"):
    if raw_value is None:
        color = "#EAECEF"
    else:
        color = "#0ecb81" if raw_value >= 0 else "#f6465d"
    if sub_text:
        sub = (f'<div style="font-size:.75rem;color:{color};opacity:.85;'
               f'margin-top:3px;">{sub_text}</div>')
    else:
        sub = ""
    st.markdown(
        f'<div style="padding:.35rem 0 .6rem 0;">'
        f'<div style="font-size:.8rem;color:#848e9c;margin-bottom:4px;">{label}</div>'
        f'<div style="font-size:{font_size};font-weight:700;color:{color};'
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'
        f'line-height:1.25;">{display_value}</div>{sub}</div>',
        unsafe_allow_html=True,
    )

def metric_card(col, label, value, raw_value=None, sub_text=None, font_size="1.5rem"):
    with col:
        with st.container(border=True):
            colored_metric(label, value, raw_value, sub_text, font_size)

def section(title):
    st.markdown(f'<div class="xs-sec">{title}</div>', unsafe_allow_html=True)

def verdict_box(ok, title, detail, warn=False):
    if warn and ok:
        bg, bd, ic = "rgba(252,213,53,.1)", "#fcd535", "⚠️"
    elif ok:
        bg, bd, ic = "rgba(14,203,129,.1)", "#0ecb81", "✅"
    else:
        bg, bd, ic = "rgba(246,70,93,.1)", "#f6465d", "🚨"
    st.markdown(
        f"<div style='background:{bg};border-left:3px solid {bd};border-radius:4px;"
        f"padding:10px 14px;margin-bottom:10px;'>"
        f"<div style='font-weight:600;color:{bd};font-size:.9rem;'>{ic} {title}</div>"
        f"<div style='color:#b7bdc6;font-size:.8rem;margin-top:4px;'>{detail}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

def gauge_bar(label, used, limit, value_text="", sub="", warn_at=0.70, crit_at=0.90):
    if limit is None or limit <= 0:
        pct = 1.5 if used > 0 else 0.0
    else:
        pct = max(0.0, used / limit)
    if pct < warn_at:
        color = "#0ecb81"
    elif pct < crit_at:
        color = "#fcd535"
    else:
        color = "#f6465d"
    width = min(pct, 1.0) * 100
    text = value_text or f"{pct * 100:.0f}%"
    sub_html = f"<div class='sub'>{sub}</div>" if sub else ""
    st.markdown(
        f"<div class='xs-gauge'>"
        f"<div class='top'><span>{label}</span>"
        f"<b style='color:{color}'>{text}</b></div>"
        f"<div class='track'><div class='fill' "
        f"style='width:{width:.1f}%;background:{color};'></div></div>"
        f"{sub_html}</div>",
        unsafe_allow_html=True,
    )

def step_html(number, title, status, note="", rows=None, total=None):
    tag = {"pass": "ผ่าน", "warn": "เฝ้าระวัง", "block": "ติดด่าน"}[status]
    body = ""
    if rows:
        body += "".join(
            f"<div class='xs-row'><span>{k}</span><b>{v}</b></div>" for k, v in rows
        )
    if total:
        body += (f"<div class='xs-row xs-tot'><span>{total[0]}</span>"
                 f"<b>{total[1]}</b></div>")
    note_html = f"<p>{note}</p>" if note else ""
    body_html = f"<div style='margin-top:8px'>{body}</div>" if body else ""
    return (f"<div class='xs-step {status}' data-n='{number}'>"
            f"<h4><span>{title}</span><span class='xs-tag'>{tag}</span></h4>"
            f"{note_html}{body_html}</div>")

def render_timeline(steps):
    ordered = sorted(steps, key=lambda x: x["n"])
    html = "".join(
        step_html(s["n"], s["t"], s["s"], s.get("note", ""),
                  s.get("rows"), s.get("total"))
        for s in ordered
    )
    st.markdown(f"<div class='xs-tl'>{html}</div>", unsafe_allow_html=True)

def render_tradingview(symbol, container_id, height=500, interval="D", studies=None):
    studies_js = str(studies or []).replace("'", '"')
    html = f"""
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
          "toolbar_bg": "#181a20",
          "enable_publishing": false,
          "hide_side_toolbar": false,
          "allow_symbol_change": true,
          "studies": {studies_js},
          "overrides": {{
            "paneProperties.background": "#181a20",
            "paneProperties.backgroundType": "solid",
            "paneProperties.vertGridProperties.color": "#2b3139",
            "paneProperties.horzGridProperties.color": "#2b3139",
            "mainSeriesProperties.candleStyle.upColor": "#0ecb81",
            "mainSeriesProperties.candleStyle.downColor": "#f6465d",
            "mainSeriesProperties.candleStyle.borderUpColor": "#0ecb81",
            "mainSeriesProperties.candleStyle.borderDownColor": "#f6465d",
            "mainSeriesProperties.candleStyle.wickUpColor": "#0ecb81",
            "mainSeriesProperties.candleStyle.wickDownColor": "#f6465d"
          }}
        }});
      }})();
    </script>"""
    components.html(html, height=height + 8)

def render_tv_panel(asset: str) -> None:
    tv_mode = st.radio(
        "มุมมองกราฟ",
        ["กระดานไทย (Bitkub)", "กระดานโลก (Binance)", "เทียบ 2 กระดาน"],
        horizontal=True, key="tv_mode_bt",
    )
    local_sym = TV_LOCAL_SYMBOL.get(asset, f"BITKUB:{asset}THB")
    global_sym = TV_GLOBAL_SYMBOL.get(asset, f"BINANCE:{asset}USDT")

    if tv_mode == "กระดานไทย (Bitkub)":
        render_tradingview(local_sym, f"tv_bt_local_{asset}", 520,
                           studies=["RSI@tv-basicstudies"])
    elif tv_mode == "กระดานโลก (Binance)":
        render_tradingview(global_sym, f"tv_bt_global_{asset}", 520,
                           studies=["RSI@tv-basicstudies"])
    else:
        g1, g2 = st.columns(2)
        with g1:
            st.caption(f"🇹🇭 ราคาจริงฝั่งไทย — `{local_sym}`")
            render_tradingview(local_sym, f"tv_cmp_local_{asset}", 420)
        with g2:
            st.caption(f"🌐 ราคาโลก — `{global_sym}`")
            render_tradingview(global_sym, f"tv_cmp_global_{asset}", 420)


# =========================================================================
# LAYER 4 — AUDIT TRAIL
# =========================================================================

AUDIT_LOG_ENV_VAR = "XSPRING_AUDIT_LOG"
AUDIT_ACTOR_ENV_VAR = "XSPRING_USER"

def audit_log_path() -> Path:
    return Path(os.environ.get(AUDIT_LOG_ENV_VAR) or (_HERE / "audit_log.jsonl"))

def _json_safe(v: Any) -> Any:
    if v is None or isinstance(v, (str, bool)):
        return v
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return float(f"{f:.12g}") if math.isfinite(f) else None
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, Mapping):
        return {str(k): _json_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    return str(v)

def build_audit_records(prev: Optional[Mapping[str, Any]], current: Mapping[str, Any], *,
                        session_id: str, actor: str = "unknown",
                        now: Optional[datetime] = None) -> list[dict[str, Any]]:
    ts = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    base = {
        "ts": ts, "session_id": session_id, "actor": actor,
        "model_version": MODEL_VERSION, "config_sha256": CONFIG_INFO["sha256"],
    }
    if prev is None:
        return [{**base, "event": "session_start", "params": _json_safe(dict(current))}]
    records = []
    for key, new_val in current.items():
        old_val = prev.get(key)
        if old_val != new_val:
            records.append({**base, "event": "param_change", "param": key,
                            "old": _json_safe(old_val), "new": _json_safe(new_val)})
    return records

def append_audit_records(records: list[dict[str, Any]], path: Optional[Path] = None) -> None:
    if not records:
        return
    p = Path(path) if path else audit_log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())

def read_audit_records(path: Optional[Path] = None, limit: Optional[int] = None) -> list[dict[str, Any]]:
    p = Path(path) if path else audit_log_path()
    if not p.is_file():
        return []
    out = []
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out[-limit:] if limit else out

SIM_STATE_ENV_VAR = "XSPRING_SIM_STATE"

def sim_state_path() -> Path:
    return Path(os.environ.get(SIM_STATE_ENV_VAR) or (_HERE / "sim_state.json"))

def save_sim_state(sim: Any, path: Optional[Path] = None) -> None:
    if not isinstance(sim, dict):
        return
    p = Path(path) if path else sim_state_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(_json_safe(sim), ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)   # เขียนไฟล์ชั่วคราวก่อนแล้วสลับ กันไฟล์พังถ้าถูกปิดกลางคัน

def load_sim_state(path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    p = Path(path) if path else sim_state_path()
    if not p.is_file():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(d, dict):
        return None
    if d.get("current_date"):
        try:
            d["current_date"] = pd.to_datetime(d["current_date"])
        except (ValueError, TypeError):
            d.pop("current_date", None)
    return d

FAV_STATE_ENV_VAR = "XSPRING_FAV_STATE"

def fav_state_path() -> Path:
    return Path(os.environ.get(FAV_STATE_ENV_VAR) or (_HERE / "favorites.json"))

def save_favorites(favs: Any, path: Optional[Path] = None) -> None:
    p = Path(path) if path else fav_state_path()
    clean = [s for s in (favs or []) if s in SUPPORTED_ASSETS]
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean), encoding="utf-8")
    os.replace(tmp, p)

def load_favorites(path: Optional[Path] = None) -> list[str]:
    p = Path(path) if path else fav_state_path()
    if not p.is_file():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [s for s in d if s in SUPPORTED_ASSETS] if isinstance(d, list) else []

def _current_actor() -> str:
    try:
        email = getattr(st.user, "email", None)
        if email:
            return str(email)
    except Exception:
        pass
    return os.environ.get(AUDIT_ACTOR_ENV_VAR) or "unknown"

def _audit_log_param_changes(current_params: Mapping[str, Any]) -> None:
    prev = st.session_state.get("audit_prev_params")
    if "audit_log" not in st.session_state:
        st.session_state.audit_log = []
    if "audit_session_id" not in st.session_state:
        st.session_state.audit_session_id = uuid.uuid4().hex[:12]

    if prev is not None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for key, new_val in current_params.items():
            old_val = prev.get(key)
            if old_val != new_val:
                st.session_state.audit_log.append({
                    "เวลา": now,
                    "พารามิเตอร์": key,
                    "ค่าเดิม": old_val,
                    "ค่าใหม่": new_val,
                })

    records = build_audit_records(prev, current_params,
                                  session_id=st.session_state.audit_session_id,
                                  actor=_current_actor())
    try:
        append_audit_records(records)
        st.session_state.audit_write_error = None
    except OSError as e:
        st.session_state.audit_write_error = f"{audit_log_path()}: {e}"
    st.session_state.audit_prev_params = dict(current_params)

def render_audit_log_sidebar():
    log = st.session_state.get("audit_log", [])
    title = f"🧾 Audit Log — การเปลี่ยนพารามิเตอร์ ({len(log)})"
    with st.expander(title, expanded=False):
        st.caption(
            f"Model v{MODEL_VERSION} · บันทึกอัตโนมัติทุกครั้งที่พารามิเตอร์ที่มีผล"
            "ต่อการคำนวณเปลี่ยนค่า · ช่อง actor จะมีชื่อผู้ใช้ก็ต่อเมื่อแอปตั้ง "
            "authentication หรือกำหนด env XSPRING_USER (ไม่งั้นเป็น 'unknown')"
        )
        err = st.session_state.get("audit_write_error")
        if err:
            st.error(f"⚠️ เขียน audit log ลงไฟล์ไม่สำเร็จ — {err}")
        else:
            st.caption(f"💾 บันทึกถาวรที่ `{audit_log_path()}` (JSON Lines) · "
                       f"config: `{CONFIG_INFO['source'] or 'built-in defaults'}`")
        _p = audit_log_path()
        if _p.is_file():
            st.download_button(
                "⬇️ ดาวน์โหลดไฟล์ Audit Log ถาวรทั้งไฟล์ (JSONL)",
                _p.read_bytes(), "xspring_audit_log.jsonl",
                "application/x-ndjson", key="dl_audit_jsonl", **WIDE,
            )
        if not log:
            st.caption("ยังไม่มีการเปลี่ยนพารามิเตอร์ในเซสชันนี้")
            return
        for row in log[-10:][::-1]:
            st.markdown(
                f"<div class='xs-audit-row'>{row['เวลา']} — "
                f"<b>{row['พารามิเตอร์']}</b>: "
                f"{row['ค่าเดิม']} → {row['ค่าใหม่']}</div>",
                unsafe_allow_html=True,
            )
        st.download_button(
            "⬇️ ดาวน์โหลด Audit Log ฉบับเต็ม (CSV)",
            to_csv_bytes(pd.DataFrame(log)),
            "xspring_audit_log.csv",
            "text/csv",
            **WIDE,
        )


# =========================================================================
# LAYER 5 — APP
# =========================================================================

def build_sidebar() -> dict[str, Any]:
    with st.sidebar:
        st.markdown("### ⚙️ Backtest Settings")

        asset = st.selectbox("เลือกเหรียญ", SUPPORTED_ASSETS, key="bt_asset")
        if asset in STABLECOINS:
            st.warning(f"⚠️ {asset} เป็น Stablecoin — ใช้กลยุทธ์ Depeg Arbitrage + Carry Yield")

        with st.expander("🌐 กระดานซื้อขาย", expanded=True):
            global_exchange = st.selectbox(
                "กระดานโลกที่ใช้ Hedge",
                list(GLOBAL_EXCHANGE_FEE_PRESET.keys()),
                key="bt_global_exchange",
            )
            st.selectbox("กระดานไทยอ้างอิงราคาลูกค้า", LOCAL_EXCHANGES,
                         key="bt_local_exchange")

        with st.expander("📅 ช่วงเวลา Backtest", expanded=True):
            today = pd.Timestamp.now().date()
            preset_days = {
                "1 เดือน": 30, "3 เดือน": 90, "6 เดือน": 180,
                "1 ปี": 365, "3 ปี": 365 * 3, "5 ปี": 365 * 5,
            }
            preset = st.radio(
                "เลือกช่วงเวลาด่วน",
                ["กำหนดเอง", "1 เดือน", "3 เดือน", "6 เดือน", "1 ปี", "3 ปี", "5 ปี"],
                index=6, horizontal=True, key="bt_preset",
            )
            if preset != "กำหนดเอง":
                preset_start = today - pd.Timedelta(days=preset_days[preset])
                preset_end = today
            else:
                preset_start = today - pd.Timedelta(days=365 * 5)
                preset_end = today

            min_day = pd.Timestamp("2015-01-01").date()
            ca, cb = st.columns(2)
            with ca:
                start_date = st.date_input(
                    "เริ่มต้น", value=preset_start, min_value=min_day,
                    max_value=today, disabled=(preset != "กำหนดเอง"),
                )
            with cb:
                end_date = st.date_input(
                    "สิ้นสุด", value=preset_end, min_value=min_day,
                    max_value=today, disabled=(preset != "กำหนดเอง"),
                )
            if preset != "กำหนดเอง":
                start_date, end_date = preset_start, preset_end

        dates_ok = start_date < end_date
        if not dates_ok:
            st.error("❌ วันเริ่มต้นต้องมาก่อนวันสิ้นสุด")

        if FX_PROXY["enabled"] and FX_PROXY["url"]:
            use_fx_proxy = st.checkbox(
                f"ใช้ {FX_PROXY['symbol']} เป็น proxy ของ USD/THB ช่วงตลาด FX ปิด",
                value=False, key="bt_use_fx_proxy",
                help=("เสาร์-อาทิตย์/วันหยุดจะใช้ 'อัตราการเปลี่ยน' ของ proxy คูณเข้ากับ"
                      "เรทวันทำการล่าสุด (ไม่ใช้ระดับราคาของ proxy ตรง ๆ) · "
                      "ปิด = ใช้เรทค้างแบบเดิม"))
        else:
            use_fx_proxy = False

        with st.expander("💰 พารามิเตอร์ Dealer", expanded=True):
            trade_vol = comma_number_input(
                "ปริมาณซื้อขายลูกค้า/วัน (USD eq.)", value=100000, key="bt_trade_vol")
            dealer_spread = st.number_input(
                "Dealer Spread ที่เก็บจากลูกค้า (%)",
                value=float(UI_DEFAULTS["dealer_spread_pct"]), step=0.1,
                key="bt_spread") / 100

            if "bt_prev_gx" not in st.session_state:
                st.session_state.bt_prev_gx = global_exchange
            if "bt_hedge_fee" not in st.session_state:
                st.session_state.bt_hedge_fee = GLOBAL_EXCHANGE_FEE_PRESET[global_exchange]
            if "bt_hedge_fee_maker" not in st.session_state:
                st.session_state.bt_hedge_fee_maker = default_maker_fee_pct(global_exchange)
            if st.session_state.bt_prev_gx != global_exchange:
                st.session_state.bt_hedge_fee = GLOBAL_EXCHANGE_FEE_PRESET[global_exchange]
                st.session_state.bt_hedge_fee_maker = default_maker_fee_pct(global_exchange)
                st.session_state.bt_prev_gx = global_exchange

            hedge_fee_taker = st.number_input(
                "ค่าธรรมเนียม Global CEX — Taker (%)", key="bt_hedge_fee",
                step=0.01) / 100
            hedge_fee_maker = st.number_input(
                "ค่าธรรมเนียม Global CEX — Maker (%)", key="bt_hedge_fee_maker",
                step=0.01,
                help=("ค่าตั้งต้น = เท่า Taker จนกว่าจะตั้ง maker preset ใน config.yaml "
                      "หรือแก้ช่องนี้ตามเทียร์บัญชีจริง")) / 100
            maker_ratio = st.slider(
                "สัดส่วน Hedge ที่ทำเป็น Maker / Limit (%)", 0, 100, 0,
                key="bt_maker_ratio",
                help=("0 = hedgeแบบ Taker ทั้งหมด (โมเดลเดิม) · ยังไม่จำลองความเสี่ยง"
                      "ที่ Limit order ไม่ถูก fill จึงยิ่งสูงยิ่งมองโลกในแง่ดี")) / 100

            hedge_fee = blend_hedge_fee(hedge_fee_taker, hedge_fee_maker, maker_ratio)
            if maker_ratio > 0:
                st.caption(f"ค่าธรรมเนียม Hedge เฉลี่ยที่ใช้คำนวณ: **{hedge_fee * 100:.4f}%**")
            fx_limit_max = comma_number_input(
                "FX Limit ต่อเดือน (USD)", value=UI_DEFAULTS["fx_limit_usd"],
                min_value=1, key="bt_fx_limit")
            local_premium = st.number_input(
                "Local Premium/Discount ฝั่งไทย (%)",
                value=float(UI_DEFAULTS["local_premium_pct"]), step=0.1,
                key="bt_local_premium") / 100

        with st.expander("💳 ค่าธรรมเนียมกระดานไทย"):
            include_trading_fee_revenue = st.checkbox(
                "รวมรายได้ค่าธรรมเนียมซื้อขาย 0.25%", value=True, key="bt_inc_fee")
            withdrawal_fee_markup_pct = st.slider(
                "Markup ค่าธรรมเนียมถอน (%)", 0, 200, 0, key="bt_wd_markup") / 100
            settlements_per_day = st.number_input(
                "รอบถอนเหรียญให้ลูกค้า/วัน", value=1, min_value=1, step=1,
                key="bt_settle_per_day")
            bank_type = st.selectbox(
                "ธนาคารปลายทางถอนบาท", ["SCB", "ธนาคารอื่น", "KTB (กรุงไทย)"],
                key="bt_bank")

        with st.expander("🏦 สิทธิพิเศษ KTB", expanded=bank_type.startswith("KTB")):
            use_ktb_fx = st.checkbox(
                "ใช้เรทแลกเปลี่ยน USD/THB พิเศษจาก KTB", value=True, key="bt_use_ktb")
            if use_ktb_fx:
                ktb_fx_spread_bps = st.number_input(
                    "ส่วนต่างเรทที่ดีกว่าตลาด (bps)", value=15.0, step=1.0,
                    min_value=0.0, key="bt_ktb_bps")
            else:
                ktb_fx_spread_bps = 0.0
            ktb_wd_fee_thb = st.number_input(
                "ค่าธรรมเนียมถอนบาท KTB (บาท)", value=15.0, step=1.0,
                min_value=0.0, key="bt_ktb_wd")

        if asset in STABLECOINS:
            with st.expander("🪙 กลยุทธ์ Stablecoin", expanded=True):
                peg_target = st.number_input(
                    "Peg Target (USD)", value=1.00, step=0.01, key="bt_peg")
                depeg_capture_pct = st.slider(
                    "Depeg Arbitrage Capture (%)", 0, 100, 80, key="bt_depeg") / 100
                carry_apy = st.number_input(
                    "Carry Yield APY (%)", value=4.0, step=0.5, key="bt_carry") / 100
            slippage_sensitivity = 0.0
            market_depth_usd, impact_penalty = 0.0, 0.0
        else:
            with st.expander("📉 Execution Model", expanded=True):
                slippage_sensitivity = st.number_input(
                    "Slippage Sensitivity (% ของ Volatility)", value=10.0,
                    step=1.0, key="bt_slip") / 100
                market_depth_usd = comma_number_input(
                    "Market Depth ฝั่งที่ต้องกิน (USD) — 0 = ปิด", value=0,
                    min_value=0, key="bt_depth",
                    help=("มูลค่า order book บน Global CEX ภายในช่วงราคาที่ใช้ประเมิน "
                          "ต้องหาจากกระดานจริงของเหรียญนี้ — ไม่มีค่ามาตรฐาน · "
                          "0 = ใช้ slippage แบบเดิม (สัดส่วนของ volatility อย่างเดียว)"))
                impact_penalty = st.number_input(
                    "Impact Penalty (% ราคาเสียเพิ่ม เมื่อออเดอร์กิน depth 100%)",
                    value=float(UI_DEFAULTS["impact_penalty_pct"]), step=0.1,
                    min_value=0.0, key="bt_impact_pen",
                    help=("Slippage = Base + (Order ÷ Depth) × Penalty · ถ้านับ depth "
                          "ภายใน ±1% ของราคากลาง Penalty ≈ 0.5%")) / 100
            peg_target, depeg_capture_pct, carry_apy = 1.0, 0.0, 0.0

        st.divider()
        st.markdown("### 🏛️ งบดุลและ Flow")

        with st.expander("📥 Flow Assumptions", expanded=False):
            monthly_volume_thb = comma_number_input(
                "ปริมาณธุรกรรมลูกค้าต่อเดือน (THB)", value=300_000_000,
                min_value=0, key="fl_monthly_vol")
            net_bias_pct = st.slider(
                "Net Flow Bias (+/-)", -100, 100, 20, key="fl_bias") / 100
            flow_cv_pct = st.slider(
                "ความผันผวนของปริมาณต่อวัน (CV, %)", 10, 150, 40, key="fl_cv") / 100
            settlement_days = st.number_input(
                "Settlement Lag (วัน)", value=2, min_value=1, max_value=10,
                step=1, key="fl_lag")
            confidence = st.select_slider(
                "Confidence Level ของ Safety Stock",
                options=[90, 95, 99, 99.9], value=99, key="fl_conf")
            z_alpha = Z_SCORE_MAP[confidence]

        with st.expander("💼 Capital Pool", expanded=False):
            total_capital_thb = comma_number_input(
                "เงินทุนสภาพคล่องรวม (THB)", value=300_000_000,
                min_value=0, key="cp_total_capital")
            cex_margin_thb = comma_number_input(
                "เงินทุนบนกระดานโลก / CEX Margin (THB)", value=60_000_000,
                min_value=0, key="cp_cex_margin")
            liab_thb = comma_number_input(
                "หนี้สินต่อลูกค้า (THB)", value=250_000_000,
                min_value=1, key="cp_liab")
            cex_margin_asset = st.selectbox(
                "สินทรัพย์ Margin บนกระดานโลก",
                ["Stablecoin", "เหรียญเดียวกับที่เทรด"], key="cp_margin_asset")
            cex_counterparty_haircut = st.number_input(
                "Counterparty Haircut (%)", value=2.0, step=0.5,
                min_value=0.0, key="cp_cp_haircut") / 100

        with st.expander("⚖️ เกณฑ์เงินกองทุน ก.ล.ต.", expanded=False):
            is_custodian = st.checkbox(
                "เก็บรักษาทรัพย์สินลูกค้า", value=True, key="nc_custodian")
            fixed_min_nc = (NC_FIXED_MIN_CUSTODIAN_THB if is_custodian
                            else NC_FIXED_MIN_NON_CUSTODIAN_THB)
            trading_risk_rate = st.number_input(
                "อัตรา NC ความเสี่ยงซื้อขาย (%)", value=2.0, step=0.1,
                min_value=0.0, key="nc_trading_rate") / 100
            cold_foreign_rate = st.number_input(
                "อัตรา NC cold wallet ต่างประเทศ (%)", value=2.0, step=0.5,
                min_value=1.0, key="nc_cold_foreign") / 100
            hot_wallet_pct = st.slider(
                "สัดส่วนสต็อกใน Hot Wallet (%)", 0, 100, 50, key="nc_hot") / 100
            cold_domestic_split_pct = st.slider(
                "สัดส่วน Cold Wallet ฝากในประเทศ (%)", 0, 100, 100,
                key="nc_cold_dom") / 100

        st.divider()
        _audit_log_param_changes(dict(
            asset=asset, global_exchange=global_exchange,
            start_date=str(start_date), end_date=str(end_date),
            trade_vol=trade_vol, dealer_spread=dealer_spread,
            hedge_fee=hedge_fee, hedge_fee_taker=hedge_fee_taker,
            hedge_fee_maker=hedge_fee_maker, maker_ratio=maker_ratio,
            market_depth_usd=market_depth_usd, impact_penalty=impact_penalty,
            use_fx_proxy=use_fx_proxy, fx_limit_max=fx_limit_max,
            local_premium=local_premium,
            include_trading_fee_revenue=include_trading_fee_revenue,
            withdrawal_fee_markup_pct=withdrawal_fee_markup_pct,
            bank_type=bank_type, use_ktb_fx=use_ktb_fx,
            ktb_fx_spread_bps=ktb_fx_spread_bps, ktb_wd_fee_thb=ktb_wd_fee_thb,
            slippage_sensitivity=slippage_sensitivity,
            monthly_volume_thb=monthly_volume_thb, net_bias_pct=net_bias_pct,
            flow_cv_pct=flow_cv_pct, settlement_days=settlement_days,
            confidence=confidence, total_capital_thb=total_capital_thb,
            cex_margin_thb=cex_margin_thb, liab_thb=liab_thb,
            cex_margin_asset=cex_margin_asset,
            cex_counterparty_haircut=cex_counterparty_haircut,
            is_custodian=is_custodian, trading_risk_rate=trading_risk_rate,
            cold_foreign_rate=cold_foreign_rate, hot_wallet_pct=hot_wallet_pct,
            cold_domestic_split_pct=cold_domestic_split_pct,
        ))
        render_audit_log_sidebar()

    daily_volume_thb = monthly_volume_thb / 30.0
    custody_rate_blended = blended_custody_rate(
        hot_wallet_pct, cold_domestic_split_pct, cold_foreign_rate)
    hot_wallet_cap_breach = ((liab_thb < HOT_WALLET_CAP_LIAB_THRESHOLD)
                             and (hot_wallet_pct > HOT_WALLET_CAP))

    return dict(
        asset=asset, global_exchange=global_exchange,
        start_date=start_date, end_date=end_date, dates_ok=dates_ok,
        trade_vol=trade_vol, dealer_spread=dealer_spread, hedge_fee=hedge_fee,
        hedge_fee_taker=hedge_fee_taker, hedge_fee_maker=hedge_fee_maker,
        maker_ratio=maker_ratio, market_depth_usd=market_depth_usd,
        impact_penalty=impact_penalty, use_fx_proxy=use_fx_proxy,
        fx_limit_max=fx_limit_max, local_premium=local_premium,
        include_trading_fee_revenue=include_trading_fee_revenue,
        withdrawal_fee_markup_pct=withdrawal_fee_markup_pct,
        settlements_per_day=settlements_per_day, bank_type=bank_type,
        use_ktb_fx=use_ktb_fx, ktb_fx_spread_bps=ktb_fx_spread_bps,
        ktb_wd_fee_thb=ktb_wd_fee_thb,
        peg_target=peg_target, depeg_capture_pct=depeg_capture_pct,
        carry_apy=carry_apy, slippage_sensitivity=slippage_sensitivity,
        monthly_volume_thb=monthly_volume_thb, daily_volume_thb=daily_volume_thb,
        net_bias_pct=net_bias_pct, flow_cv_pct=flow_cv_pct,
        settlement_days=settlement_days, confidence=confidence, z_alpha=z_alpha,
        total_capital_thb=total_capital_thb, cex_margin_thb=cex_margin_thb,
        liab_thb=liab_thb, cex_margin_asset=cex_margin_asset,
        cex_counterparty_haircut=cex_counterparty_haircut,
        is_custodian=is_custodian, fixed_min_nc=fixed_min_nc,
        trading_risk_rate=trading_risk_rate, cold_foreign_rate=cold_foreign_rate,
        hot_wallet_pct=hot_wallet_pct,
        cold_domestic_split_pct=cold_domestic_split_pct,
        custody_rate_blended=custody_rate_blended,
        hot_wallet_cap_breach=hot_wallet_cap_breach,
    )


# ---- 5.2 TAB 1 — BACKTEST ----------------------------------------------

def render_tab1(cfg: dict[str, Any], data: pd.DataFrame, data_err: Optional[str]) -> None:
    if data.empty:
        st.error(f"⚠️ {data_err or 'ไม่สามารถโหลดข้อมูลได้'}")
        return

    asset = cfg["asset"]
    trade_vol = cfg["trade_vol"]
    hedge_fee = cfg["hedge_fee"]

    bt = data.copy()
    bt["Local_THB"] = bt["Global_USD"] * bt["USDTHB"] * (1 + cfg["local_premium"])
    bt["Coin_Volume"] = trade_vol / bt["Global_USD"]
    bt["Gross_Notional_THB"] = bt["Coin_Volume"] * bt["Local_THB"]
    bt["Spread_Revenue_THB"] = bt["Gross_Notional_THB"] * cfg["dealer_spread"]
    bt["FX_Basis_PnL_THB"] = trade_vol * bt["USDTHB"] * cfg["local_premium"]
    bt["Hedge_Fee_Cost_THB"] = trade_vol * hedge_fee * bt["USDTHB"]
    bt["Hedge_Notional_USD"] = trade_vol * (1 + hedge_fee)
    bt["KTB_FX_Benefit_THB"] = (trade_vol * bt["USDTHB"]
                                * (cfg["ktb_fx_spread_bps"] / 10000.0))

    if asset in STABLECOINS:
        bt["Depeg_Deviation"] = cfg["peg_target"] - bt["Global_USD"]
        bt["Depeg_PnL_THB"] = (bt["Coin_Volume"] * bt["Depeg_Deviation"]
                               * bt["USDTHB"] * cfg["depeg_capture_pct"])
        bt["Carry_Yield_THB"] = trade_vol * (cfg["carry_apy"] / 365) * bt["USDTHB"]
        bt["Slippage_Cost_THB"] = 0.0
    else:
        bt["Depeg_Deviation"] = 0.0
        bt["Depeg_PnL_THB"] = 0.0
        bt["Carry_Yield_THB"] = 0.0
        impact_rate = market_impact_rate(trade_vol, cfg["market_depth_usd"],
                                         cfg["impact_penalty"])
        bt["Slippage_Cost_THB"] = (trade_vol * bt["Volatility_Pct"]
                                   * cfg["slippage_sensitivity"] * bt["USDTHB"]
                                   + trade_vol * impact_rate * bt["USDTHB"])

    if cfg["include_trading_fee_revenue"]:
        bt["Trading_Fee_Revenue_THB"] = bt["Gross_Notional_THB"] * LOCAL_TRADING_FEE_PCT
    else:
        bt["Trading_Fee_Revenue_THB"] = 0.0

    wd_network_cost = (WITHDRAWAL_FEE_TABLE.get(asset, 0.0) * bt["Global_USD"]
                       * bt["USDTHB"] * cfg["settlements_per_day"])
    bt["Withdrawal_Fee_Markup_Revenue_THB"] = (wd_network_cost
                                               * cfg["withdrawal_fee_markup_pct"])
    bt["THB_WD_Fee"] = bt["USDTHB"].map(
        lambda fx: calc_thb_withdrawal_fee(trade_vol * fx, cfg["bank_type"],
                                           cfg["ktb_wd_fee_thb"])
    )
    bt["THB_Fee_Markup_Revenue_THB"] = (bt["THB_WD_Fee"] * cfg["settlements_per_day"]
                                        * cfg["withdrawal_fee_markup_pct"])
    bt["Fee_Revenue_THB"] = (bt["Trading_Fee_Revenue_THB"]
                             + bt["Withdrawal_Fee_Markup_Revenue_THB"]
                             + bt["THB_Fee_Markup_Revenue_THB"])
    bt["Revenue_THB"] = (bt["Spread_Revenue_THB"] + bt["FX_Basis_PnL_THB"]
                         + bt["Fee_Revenue_THB"] + bt["Depeg_PnL_THB"]
                         + bt["Carry_Yield_THB"] + bt["KTB_FX_Benefit_THB"])
    bt["Cost_THB"] = bt["Hedge_Fee_Cost_THB"] + bt["Slippage_Cost_THB"]
    bt["Daily_PnL_THB"] = bt["Revenue_THB"] - bt["Cost_THB"]

    allowed, usage = apply_fx_limit(bt["Hedge_Notional_USD"], bt.index,
                                    cfg["fx_limit_max"])
    bt["Trade_Allowed"] = allowed
    bt["Current_FX_Usage"] = usage
    bt["FX_Limit_Hit"] = 1 - allowed
    bt["Actual_Daily_PnL"] = np.where(allowed == 1, bt["Daily_PnL_THB"], 0.0)
    bt["Actual_Cum_PnL"] = bt["Actual_Daily_PnL"].cumsum()

    traded = bt[bt["Trade_Allowed"] == 1]
    total_revenue_thb = traded["Revenue_THB"].sum()
    total_cost_thb = traded["Cost_THB"].sum()
    net_pnl_thb = bt["Actual_Cum_PnL"].iloc[-1]
    total_notional = traded["Gross_Notional_THB"].sum()
    margin_bps = (net_pnl_thb / total_notional * 10000) if total_notional else 0
    total_days = len(bt)
    traded_days = int(allowed.sum())
    limit_hit_days = int(bt["FX_Limit_Hit"].sum())
    win_days = int((bt["Actual_Daily_PnL"] > 0).sum())
    win_rate = win_days / traded_days * 100 if traded_days else 0
    avg_daily_pnl = traded["Daily_PnL_THB"].mean() if traded_days else 0
    best_day = bt["Actual_Daily_PnL"].max()
    worst_day = bt["Actual_Daily_PnL"].min()
    running_max = bt["Actual_Cum_PnL"].cummax()
    max_drawdown = (bt["Actual_Cum_PnL"] - running_max).min()
    dd_series = (bt["Actual_Cum_PnL"] - running_max) / running_max.where(running_max > 0)
    dd_pct = dd_series.min() * 100
    dd_pct = 0.0 if pd.isna(dd_pct) else dd_pct

    st.success(f"✅ โหลดข้อมูล **{asset}** สำเร็จ ({total_days} วัน | เทรดได้จริง {traded_days} วัน)")

    # ---- ราคาเรียลไทม์ ----
    section(f"📉 ราคาเรียลไทม์ — {asset}")
    render_tv_panel(asset)

    # ---- 3D Interactive Chart Feature ----
    section("🌐 มุมมองกราฟ 3D พิเศษ (3D Price & Volatility Surface)")
    with st.expander("✨ เปิดดูกราฟ 3D สามมิติ (Interactive 3D Chart)", expanded=False):
        st.caption("หมุนและซูมเพื่อดูความสัมพันธ์ระหว่าง วันที่, ราคาโลก (USD), และความผันผวน (Volatility)")
        df_3d = bt.dropna().copy()
        if len(df_3d) > 0:
            fig_3d = go.Figure(data=[go.Scatter3d(
                x=list(range(len(df_3d))),
                y=df_3d["Global_USD"],
                z=df_3d["Volatility_Pct"] * 100,
                mode='markers',
                marker=dict(
                    size=5,
                    color=list(range(len(df_3d))), # ไล่สีรุ้งตามเวลา
                    colorscale='Rainbow',          
                    opacity=0.8,
                    line=dict(width=0)
                ),
                text=df_3d.index.strftime('%Y-%m-%d'),
                hovertemplate='วันที่: %{text}<br>ราคา: $%{y:,.2f}<br>ความผันผวน: %{z:.2f}%<extra></extra>'
            )])
            fig_3d.update_layout(
                title=dict(text=f"3D Trajectory — {asset} (Price vs Volatility vs Time)", font=dict(size=14)),
                scene=dict(
                    xaxis_title='ลำดับเวลา (Time Steps)',
                    yaxis_title='ราคาโลก (USD)',
                    zaxis_title='ความผันผวน (%)',
                    bgcolor='#181a20'
                ),
                template="plotly_dark",
                height=600,
                margin=dict(l=0, r=0, b=0, t=40),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_3d, **WIDE)

    # ---- Performance ----
    section("📈 Performance Summary")
    r1 = st.columns(4)
    metric_card(r1[0], "Net P&L (THB)", fmt_baht(net_pnl_thb, True), net_pnl_thb,
                f"{margin_bps:,.1f} bps ของ notional", "1.7rem")
    metric_card(r1[1], "Total Revenue", fmt_baht(total_revenue_thb),
                total_revenue_thb, "Spread + Fee + Basis + Carry")
    metric_card(r1[2], "Total Cost", fmt_baht(total_cost_thb),
                -abs(total_cost_thb), "Hedge Fee + Slippage")
    metric_card(r1[3], "Avg Daily P&L", fmt_baht(avg_daily_pnl, True),
                avg_daily_pnl, f"เฉลี่ยจาก {traded_days} วันที่เทรดได้")

    r2 = st.columns(4)
    metric_card(r2[0], "Best Day", fmt_baht(best_day, True), best_day)
    metric_card(r2[1], "Worst Day", fmt_baht(worst_day, True), worst_day)
    metric_card(r2[2], "Max Drawdown", fmt_baht(max_drawdown),
                max_drawdown if max_drawdown != 0 else -0.01,
                f"{dd_pct:.2f}% จาก peak")
    metric_card(r2[3], "Win Rate", f"{win_rate:.1f}%", None,
                f"{win_days}/{traded_days} วัน")

    r3 = st.columns(4)
    hit_pct = (limit_hit_days / total_days * 100) if total_days else 0
    metric_card(r3[0], "Gross Notional หมุนเวียน", fmt_baht(total_notional),
                None, "มูลค่าธุรกรรมรวม (ไม่ใช่กำไร)")
    metric_card(r3[1], "FX Limit Hit", f"{limit_hit_days} วัน",
                -1 if limit_hit_days else 0, f"{hit_pct:.1f}% ของช่วงเวลา")
    if asset in STABLECOINS:
        metric_card(r3[2], "Avg Depeg Deviation", f"{bt['Depeg_Deviation'].mean() * 100:+.3f}%")
        metric_card(r3[3], "Total Carry Yield", fmt_baht(traded["Carry_Yield_THB"].sum()), traded["Carry_Yield_THB"].sum())
    else:
        metric_card(r3[2], "Avg Daily Volatility", f"{bt['Volatility_Pct'].mean() * 100:.2f}%")
        metric_card(r3[3], "Total Slippage Cost", fmt_baht(traded["Slippage_Cost_THB"].sum()), -abs(traded["Slippage_Cost_THB"].sum()))

    # ---- Waterfall ----
    section("💧 Revenue & Cost Waterfall")
    wf_labels = ["Spread Revenue", "FX Basis P&L", "Fee Revenue"]
    wf_values = [
        traded["Spread_Revenue_THB"].sum(),
        traded["FX_Basis_PnL_THB"].sum(),
        traded["Fee_Revenue_THB"].sum(),
    ]
    if cfg["use_ktb_fx"]:
        wf_labels.append("KTB FX Benefit")
        wf_values.append(traded["KTB_FX_Benefit_THB"].sum())
    if asset in STABLECOINS:
        wf_labels += ["Depeg Arbitrage", "Carry Yield"]
        wf_values += [traded["Depeg_PnL_THB"].sum(), traded["Carry_Yield_THB"].sum()]
    else:
        wf_labels.append("Slippage Cost")
        wf_values.append(-traded["Slippage_Cost_THB"].sum())
    wf_labels += ["Hedge Fee Cost", "Net P&L"]
    wf_values += [-traded["Hedge_Fee_Cost_THB"].sum(), 0]

    wf_text = [fmt_baht(v, True) for v in wf_values[:-1]]
    wf_text.append(fmt_baht(sum(wf_values[:-1]), True))
    measures = ["relative"] * (len(wf_labels) - 1) + ["total"]

    fig_wf = go.Figure(go.Waterfall(
        orientation="v", measure=measures, x=wf_labels, y=wf_values,
        text=wf_text, textposition="outside",
        connector={"line": {"color": "#374151"}},
        increasing={"marker": {"color": "#0ecb81"}},
        decreasing={"marker": {"color": "#f6465d"}},
        totals={"marker": {"color": "#3B82F6"}},
    ))
    fig_wf.update_layout(template="plotly_dark", height=440, showlegend=False,
                         margin=dict(t=40, b=20), yaxis_title="THB", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig_wf, **WIDE)

    # ---- Cumulative P&L ----
    section("📊 Cumulative P&L")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=bt.index, y=bt["Actual_Cum_PnL"], name="Cumulative P&L",
        line=dict(color="#0ecb81", width=2.2), fill="tozeroy",
        fillcolor="rgba(14,203,129,0.12)",
    ))
    fig.add_trace(go.Scatter(
        x=bt.index, y=running_max, name="Peak Equity",
        line=dict(color="#848e9c", width=1, dash="dot"),
    ))
    hits = bt[bt["FX_Limit_Hit"] == 1]
    if not hits.empty:
        fig.add_trace(go.Scatter(
            x=hits.index, y=hits["Actual_Cum_PnL"], mode="markers",
            name="FX Limit Hit",
            marker=dict(color="#f6465d", size=5, symbol="x"),
        ))
    fig.update_layout(
        title=(f"{asset} @ {cfg['global_exchange']} · {cfg['start_date']} → {cfg['end_date']}"),
        template="plotly_dark", hovermode="x unified", height=480,
        margin=dict(t=50, b=20), yaxis_title="THB",
        legend=dict(orientation="h", y=1.02, yanchor="bottom"),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
    )
    st.plotly_chart(fig, **WIDE)

    with st.expander("📅 P&L รายเดือน"):
        grouped = bt.groupby([bt.index.year, bt.index.month])["Actual_Daily_PnL"]
        m = grouped.sum().unstack(fill_value=0)
        m.columns = [f"{c:02d}" for c in m.columns]
        fig_hm = go.Figure(go.Heatmap(
            z=m.values, x=list(m.columns), y=[str(i) for i in m.index],
            colorscale=[[0, "#f6465d"], [0.5, "#181a20"], [1, "#0ecb81"]],
            zmid=0, texttemplate="%{z:,.0f}", textfont={"size": 9},
        ))
        fig_hm.update_layout(template="plotly_dark", height=60 * len(m) + 120,
                             margin=dict(t=20, b=20),
                             xaxis_title="เดือน", yaxis_title="ปี", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_hm, **WIDE)

    with st.expander("🔍 Daily Ledger (100 วันล่าสุด)"):
        cols = [
            "Global_USD", "Local_THB", "USDTHB", "Volatility_Pct",
            "Gross_Notional_THB", "Spread_Revenue_THB", "FX_Basis_PnL_THB",
            "KTB_FX_Benefit_THB", "Hedge_Fee_Cost_THB", "Slippage_Cost_THB",
            "Fee_Revenue_THB",
        ]
        if asset in STABLECOINS:
            cols += ["Depeg_Deviation", "Depeg_PnL_THB", "Carry_Yield_THB"]
        cols += ["Actual_Daily_PnL", "Current_FX_Usage", "FX_Limit_Hit"]

        preview = bt[cols].sort_index(ascending=False).head(100)
        st.dataframe(preview, height=400, **WIDE)


# ---- 5.3 TAB 2 — LIQUIDITY & CAPITAL PLANNER ---------------------------

def render_tab2(cfg: dict[str, Any], data: pd.DataFrame, data_err: Optional[str]) -> None:
    st.markdown(
        "ตอบคำถามที่ผู้บริหารถามจริง:\n\n"
        "> **\"ถ้าธุรกรรมเดือนละ X ล้าน ต้องดำรงเหรียญเท่าไหร่ เงินสดเท่าไหร่ "
        "NC เหลือเท่าไหร่ ผ่านเกณฑ์ไหม และทุนที่มีรับได้สูงสุดกี่ล้าน\"**"
    )
    if not cfg["dates_ok"]:
        st.error("❌ ช่วงวันที่ในแถบซ้ายไม่ถูกต้อง")
        return

    asset = cfg["asset"]

    section("🎛️ โหมดคำนวณความเสี่ยง")
    cp_mode = st.radio(
        "เลือกโหมด",
        ["Single-Asset (ใช้เหรียญที่เลือกในแถบซ้าย)", "Multi-Asset Portfolio"],
        horizontal=True, key="cp_mode",
    )

    rp = None
    risk_label = ""
    portfolio_price_frame = data if cp_mode.startswith("Single") else None

    if cp_mode.startswith("Single"):
        if data.empty:
            st.error(f"⚠️ โหลดข้อมูลไม่สำเร็จ: {data_err}")
        else:
            rp = risk_profile(data["Global_USD"])
            risk_label = asset
    else:
        ma_c1, _ma_c2 = st.columns([2, 1])
        with ma_c1:
            selected_assets = st.multiselect(
                "เลือกเหรียญในพอร์ต", SUPPORTED_ASSETS,
                default=["BTC", "ETH", "USDT"], key="cp_ma_assets",
            )
        if not selected_assets:
            st.info("เลือกอย่างน้อย 1 เหรียญ")
        else:
            wcols = st.columns(min(len(selected_assets), 6))
            default_w = round(100 / len(selected_assets))
            weights = {}
            for i, a_ in enumerate(selected_assets):
                with wcols[i % len(wcols)]:
                    weights[a_] = st.number_input(
                        f"{a_} (%)", value=default_w, min_value=0,
                        max_value=100, step=5, key=f"cp_w_{a_}",
                    )
            wsum = sum(weights.values())
            if wsum > 0:
                norm_w = {k: v / wsum for k, v in weights.items()}
                ret_map, price_map = {}, {}
                with st.spinner("กำลังโหลดราคาย้อนหลัง…"):
                    for a_ in selected_assets:
                        d_, _err = fetch_price_data(a_, cfg["start_date"],
                                                    cfg["end_date"])
                        if not d_.empty:
                            ret_map[a_] = np.log(
                                d_["Global_USD"] / d_["Global_USD"].shift(1))
                            price_map[a_] = d_
                if ret_map:
                    ret_df = pd.concat(ret_map, axis=1).dropna()
                    if len(ret_df) >= MIN_RISK_SAMPLE_DAYS:
                        port_w = np.array([norm_w.get(c, 0) for c in ret_df.columns])
                        rp = _risk_stats((ret_df * port_w).sum(axis=1))
                        risk_label = " + ".join(
                            f"{k} {norm_w[k] * 100:.0f}%" for k in ret_df.columns)
                        if price_map:
                            portfolio_price_frame = next(iter(price_map.values()))

    if rp is None:
        return

    usdthb_now, usdthb_is_fallback = get_reference_usdthb(portfolio_price_frame)
    settlement_days = cfg["settlement_days"]
    h_crypto = crypto_haircut(rp["es99"], settlement_days)
    h_cex = cfg["cex_counterparty_haircut"] if cfg["cex_margin_asset"].startswith("Stablecoin") else h_crypto

    a_factor = safety_stock_factor(cfg["net_bias_pct"], cfg["flow_cv_pct"], settlement_days, cfg["z_alpha"])
    required_stock_thb = a_factor * cfg["monthly_volume_thb"]

    nc = nc_snapshot(
        required_stock_thb, cfg["total_capital_thb"], cfg["cex_margin_thb"],
        cfg["liab_thb"], h_crypto, h_cex, cfg["fixed_min_nc"],
        cfg["trading_risk_rate"], cfg["daily_volume_thb"],
        cfg["custody_rate_blended"],
    )
    cash_after_stock_thb = nc["cash"]
    nlc_thb = nc["actual"]
    required_nc_total = nc["required"]
    nc_buffer_thb = nc["buffer"]

    slope = (a_factor * (h_crypto + cfg["custody_rate_blended"]) + cfg["trading_risk_rate"] / 30.0)
    v_nc_thb = max(0.0, (cfg["total_capital_thb"] + cfg["cex_margin_thb"] * (1 - h_cex) - cfg["liab_thb"] - cfg["fixed_min_nc"]) / slope) if slope > 0 else float("inf")
    v_cash_thb = cfg["total_capital_thb"] / a_factor if a_factor > 0 else float("inf")

    capital_max_v_thb = min(v_nc_thb, v_cash_thb)
    fx_max_v_thb = cfg["fx_limit_max"] * usdthb_now
    overall_max_v_thb = min(capital_max_v_thb, fx_max_v_thb)
    binding_side = "ทุน / NC" if capital_max_v_thb < fx_max_v_thb else "FX Limit"

    section("🧾 สรุปผลสำหรับผู้บริหาร")
    ok_nc = (not pd.isna(nc_buffer_thb)) and (nc_buffer_thb >= 0)
    verdict_box(
        ok_nc,
        f"NC จริง {fmt_baht(nlc_thb)} (ต้องดำรงขั้นต่ำ {fmt_baht(required_nc_total)})",
        f"ต้องดองเหรียญ {fmt_baht(required_stock_thb)} เหลือเงินสด {fmt_baht(cash_after_stock_thb)}",
        warn=(nc_buffer_thb < 0.5 * required_nc_total),
    )

    section("📊 รายละเอียดตัวเลข")
    k1 = st.columns(4)
    metric_card(k1[0], "Required Safety Stock", fmt_baht(required_stock_thb), None, f"Haircut ที่ใช้ {h_crypto * 100:.2f}%")
    metric_card(k1[1], "เงินสดคงเหลือ", fmt_baht(cash_after_stock_thb), cash_after_stock_thb)
    metric_card(k1[2], "Net Capital (NC) จริง", fmt_baht(nlc_thb), nlc_thb)
    metric_card(k1[3], "NC ขั้นต่ำที่ต้องดำรง", fmt_baht(required_nc_total), nc_buffer_thb, f"ส่วนเกิน {fmt_baht(nc_buffer_thb, force_sign=True)}")


# ---- 5.4 TAB 3 — TIME-TRAVEL ORDER SIMULATOR ---------------------------

def _toggle_fav(sym: str) -> None:
    favs = list(st.session_state.get("favorite_tickers", []))
    if sym in favs:
        favs.remove(sym)
    else:
        favs.append(sym)
    st.session_state["favorite_tickers"] = favs
    try:
        save_favorites(favs)
    except OSError:
        pass

def _select_asset(sym: str) -> None:
    # ต้องเซ็ตใน callback เพราะ bt_asset เป็น key ของ selectbox ใน sidebar
    st.session_state["bt_asset"] = sym


def render_market_column_view(df: pd.DataFrame, mode: str, current_asset: str, usdthb: float) -> None:
    if df.empty:
        st.markdown('<div style="padding:16px;color:#848e9c;font-size:.85rem;text-align:center;">ไม่มีข้อมูลตลาด</div>', unsafe_allow_html=True)
        return

    favs = st.session_state.get("favorite_tickers", [])
    if mode == "favorite":
        view = df[df["symbol"].isin(favs)].sort_values("volume", ascending=False)
        if view.empty:
            st.markdown('<div style="padding:32px 8px;color:#848e9c;text-align:center;">ยังไม่มีรายการโปรด<br><span style="font-size:.8rem;">(กดรูปดาว ☆ ที่แถวเหรียญเพื่อเพิ่ม)</span></div>', unsafe_allow_html=True)
            return
    elif mode == "volume":
        view = df.sort_values("volume", ascending=False)
    elif mode == "top_gain":
        view = df.sort_values("pct_change", ascending=False)
    elif mode == "top_loss":
        view = df.sort_values("pct_change", ascending=True)
    else:
        view = df

    st.markdown(
        '<div class="mk-head"><span style="width:36px"></span>'
        '<span style="flex:1">สินทรัพย์'
        + (' · ปริมาณ 24 ชม. (THB)' if mode == "volume" else '') +
        '</span><span style="text-align:right">ราคา (THB) / %</span></div>',
        unsafe_allow_html=True,
    )

    for _, row in view.iterrows():
        sym = str(row["symbol"])
        p_thb = float(row["price_usd"]) * usdthb
        pct = float(row["pct_change"])
        p_str = f"{p_thb:,.2f}" if p_thb >= 1 else f"{p_thb:,.4f}"
        c_class = "ex-green" if pct >= 0 else "ex-red"
        star_on = sym in favs
        sel_cls = " mk-sel" if sym == current_asset else ""
        vol_thb = float(row["volume"]) * usdthb   # yfinance crypto: Volume เป็นมูลค่า USD อยู่แล้ว -> คูณเรทเป็นบาท
        if mode == "volume":
            sub = f'<span class="mk-vol">Vol ฿{fmt_num(vol_thb)}</span>'
        else:
            sub = COIN_NAMES.get(sym, sym)

        html = (
            f'<div class="mk-row{sel_cls}">'
            f'<div class="mk-star{" on" if star_on else ""}">{"★" if star_on else "☆"}</div>'
            f'<div class="mk-asset">{coin_icon_html(sym, 26)}'
            f'<div><div class="mk-sym">{sym}<span>/THB</span></div>'
            f'<div class="mk-name">{sub}</div></div></div>'
            f'<div class="mk-right"><div class="mk-price">{p_str}</div>'
            f'<div class="mk-pct {c_class}">{"+" if pct >= 0 else ""}{pct:.2f}%</div></div>'
            f'</div>'
        )

        with st.container(key=f"mkrow_{mode}_{sym}"):
            st.markdown(html, unsafe_allow_html=True)
            st.button("fav", key=f"fav_{mode}_{sym}",
                      on_click=_toggle_fav, args=(sym,))
            st.button("select", key=f"sel_{mode}_{sym}",
                      on_click=_select_asset, args=(sym,))


def _fmt_comma_val(v: float) -> str:
    return f"{v:,.0f}" if abs(v - round(v)) < 1e-9 else f"{v:,.2f}"


def _apply_pct(pct_key: str, target_key: str, base: float, kind: str) -> None:
    """ปุ่ม 25/50/75/100% -> ใส่จำนวนในช่อง แล้วเคลียร์ตัวเลือกให้กดซ้ำได้"""
    sel = st.session_state.get(pct_key)
    if not sel:
        return
    p = int(str(sel).rstrip("%")) / 100.0
    if kind == "buy":
        st.session_state[target_key] = _fmt_comma_val(math.floor(base * p * 100) / 100)
    else:
        st.session_state[target_key] = math.floor(base * p * 1e8) / 1e8
    st.session_state[pct_key] = None


def _submit_order(sim, side, amount_thb, data, order_date, ctx) -> None:
    steps, _rec = execute_order(sim, side, amount_thb, order_date,
                                data.loc[order_date], ctx)
    st.session_state.sim_steps = steps
    st.rerun(scope="app")


def _place_limit(side, amount_thb, qty, px) -> None:
    sim = st.session_state.sim
    sim.setdefault("open_orders", []).append(
        dict(id=uuid.uuid4().hex[:6], side=side, amount_thb=amount_thb, qty=qty, px=px))
    st.rerun(scope="app")


def _cancel_limit(oid: str) -> None:
    sim = st.session_state.sim
    sim["open_orders"] = [o for o in sim.get("open_orders", []) if o["id"] != oid]


def check_open_orders(sim, quote_buy, quote_sell, data, order_date, ctx) -> None:
    remaining = []
    for o in sim.get("open_orders", []):
        asset = ctx["asset"]
        if o["side"] == "buy":
            hit = quote_buy <= o["px"]
            amt = o["amount_thb"]
            ok = amt <= float(sim.get("customer_thb", 0.0)) + 1e-9
        else:
            hit = quote_sell >= o["px"]
            amt = o["qty"] * quote_sell
            ok = o["qty"] <= float(sim.get("customer_coins", {}).get(asset, 0.0)) + 1e-9

        if not hit:
            remaining.append(o)
        elif ok:
            execute_order(sim, o["side"], amt, order_date, data.loc[order_date], ctx)
        # hit แต่ยอดไม่พอ = ยกเลิกทิ้ง
    sim["open_orders"] = remaining

def run_random_batch(sim, cfg, ctx, target_stock_thb, coins, n_orders, seed,
                     amt_min, amt_max):
    """สุ่มออเดอร์ข้ามหลายเหรียญ: สุ่มเหรียญ + วันที่ + ฝั่ง + ยอดเงิน (THB)
    คืนค่า (steps ของออเดอร์สุดท้าย, จำนวนออเดอร์ต่อเหรียญ, เหรียญที่โหลดราคาไม่ได้)"""
    rng = np.random.default_rng(int(seed))
    lo = float(max(amt_min, MIN_TRADE_THB))
    hi = float(max(amt_max, lo))
    p_buy = 0.5 + cfg["net_bias_pct"] / 2.0
    frames, skipped = {}, []
    with st.spinner("กำลังโหลดราคาย้อนหลังของทุกเหรียญ…"):
        for c in coins:
            d, _err = fetch_price_data(c, cfg["start_date"], cfg["end_date"],
                                       use_fx_proxy=cfg["use_fx_proxy"])
            if d.empty:
                skipped.append(c)
            else:
                frames[c] = d
    if not frames:
        return [], {}, skipped

    # 1) วางแผนออเดอร์ทั้งหมดก่อน แล้วเรียงตามวันที่
    names = list(frames)
    plan = []
    for _ in range(int(n_orders)):
        c = names[int(rng.integers(len(names)))]
        idx = frames[c].index
        d = idx[int(rng.integers(len(idx)))]
        # สุ่มแบบ log-uniform ระหว่าง min-max จะได้มีทั้งออเดอร์เล็กและใหญ่
        amt = round(float(np.exp(rng.uniform(np.log(lo), np.log(hi)))), 2)
        amt = max(amt, MIN_TRADE_THB)
        side = "buy" if rng.random() < p_buy else "sell"
        plan.append((d, c, side, amt))
    plan.sort(key=lambda x: x[0])

    # 2) เตรียม ctx และ inventory ต่อเหรียญ
    coin_ctx = {}
    for c, df_c in frames.items():
        rp = risk_profile(df_c["Global_USD"])
        h_c = (crypto_haircut(rp["es99"], cfg["settlement_days"])
               if rp else ctx["h_crypto"])
        h_x = (cfg["cex_counterparty_haircut"]
               if cfg["cex_margin_asset"].startswith("Stablecoin") else h_c)
        over = dict(asset=c, wd_fee_per_coin=WITHDRAWAL_FEE_TABLE.get(c, 0.0),
                    h_crypto=h_c, h_cex=h_x)
        if c in STABLECOINS:
            over.update(slip_sens=0.0, market_depth_usd=0.0, impact_penalty=0.0)
        coin_ctx[c] = {**ctx, **over}
        if c not in sim["inv_coins"]:
            last = df_c.iloc[-1]
            px = float(last["Global_USD"] * last["USDTHB"])
            sim["inv_coins"][c] = target_stock_thb / px if px > 0 else 0.0

    # 3) ยิงออเดอร์ (ไม่แตะกระเป๋าของผู้ใช้)
    saved_asset, saved_target = sim["asset"], sim["target_thb"]
    counts, last_steps = {}, []
    try:
        for d, c, side, amt in plan:
            sim["asset"] = c
            sim["target_thb"] = target_stock_thb   # เหรียญละ 1 กอง target เท่ากัน
            last_steps, _rec = execute_order(
                sim, side, amt, d, frames[c].loc[d], coin_ctx[c],
                affect_wallet=False)
            counts[c] = counts.get(c, 0) + 1
    finally:
        sim["asset"], sim["target_thb"] = saved_asset, saved_target
    return last_steps, counts, skipped


QUOTE_REFRESH_SEC = 15   # ปรับตรงนี้ได้ เช่น 10 / 30

def _frozen_mid(asset: str, mid_now: float) -> float:
    """คืนราคากลางที่ตรึงไว้ จะอัปเดตเมื่อครบ QUOTE_REFRESH_SEC วินาที หรือเปลี่ยนเหรียญ"""
    snap = st.session_state.get("quote_snap")
    now = time.time()
    if (not snap or snap["asset"] != asset
            or now - snap["ts"] >= QUOTE_REFRESH_SEC):
        snap = {"asset": asset, "mid": float(mid_now), "ts": now}
        st.session_state["quote_snap"] = snap
    return float(snap["mid"])


def render_order_panel(cfg, sim, asset, mid_now, data, current_date_val, ctx) -> None:
    fee = LOCAL_TRADING_FEE_PCT
    quote_buy = mid_now * (1 + cfg["dealer_spread"])
    quote_sell = mid_now * (1 - cfg["dealer_spread"])
    cash = float(sim.get("customer_thb", 1_000_000.0))
    coin_bal = float(sim.get("customer_coins", {}).get(asset, 0.0))
    PCTS = ["25%", "50%", "75%", "100%"]

    order_type = st.radio("Order type", ["Limit", "Market"], horizontal=True,
                          key="op_type", label_visibility="collapsed")
    is_limit = order_type == "Limit"

    c_buy, c_sell = st.columns(2, gap="large")

    # ---------------- ฝั่งซื้อ ----------------
    with c_buy:
        st.markdown(
            f'<div class="op-row"><span>คงเหลือ</span><b>{cash:,.2f} THB</b></div>'
            f'<div class="op-row mut"><span>ค่าธรรมเนียม</span><b>{fee * 100:.2f}%</b></div>',
            unsafe_allow_html=True)
        buy_amt = comma_number_input("จำนวนที่ต้องจ่าย (THB)", value=500000,
                                     min_value=0, key="op_buy_amt")
        st.pills("สัดส่วนของเงินบาท", PCTS, key="op_pct_buy",
                 label_visibility="collapsed", on_change=_apply_pct,
                 args=("op_pct_buy", "op_buy_amt", cash, "buy"))
                 
        snap = st.session_state.get("quote_snap")
        if snap:
            st.caption(f"ราคาอัปเดตทุก {QUOTE_REFRESH_SEC} วินาที · ล่าสุด "
                       f"{pd.Timestamp.now(tz='Asia/Bangkok').strftime('%H:%M:%S')}")

        buy_px = quote_buy
        if is_limit:
            buy_px = st.number_input("Limit price (THB)", min_value=0.0, format="%.4f",
                                     value=float(round(quote_buy, 4)), key=f"op_buy_px_{asset}")
        est_coins = buy_amt * (1 - fee) / buy_px if buy_px > 0 else 0.0
        
        st.markdown(
            f'<div class="op-ro"><span>ราคาต่อ {asset}</span><b>{buy_px:,.2f} THB</b></div>'
            f'<div class="op-ro"><span>{asset} จำนวนที่จะได้รับ</span>'
            f'<b>≈ {est_coins:,.8f} {asset}</b></div>',
            unsafe_allow_html=True)
            
        over_cash = buy_amt > cash + 1e-9
        if over_cash:
            st.markdown('<div class="op-warn">ยอดเงินบาทในกระเป๋าไม่พอ</div>',
                        unsafe_allow_html=True)
        buy_clicked = st.button(f"ซื้อ (Buy) {asset}", key="op_buy_btn",
                                disabled=(buy_amt <= 0 or over_cash), **WIDE)

    # ---------------- ฝั่งขาย ----------------
    with c_sell:
        qty_key = f"op_sell_qty_{asset}"
        st.session_state.setdefault(qty_key, 0.0)
        st.markdown(
            f'<div class="op-row"><span>คงเหลือ</span><b>{coin_bal:,.8f} {asset}</b></div>'
            f'<div class="op-row mut"><span>ค่าธรรมเนียม</span><b>{fee * 100:.2f}%</b></div>',
            unsafe_allow_html=True)
        sell_qty = st.number_input(f"จำนวนที่ต้องขาย ({asset})", min_value=0.0,
                                   format="%.8f", key=qty_key)
        st.pills("สัดส่วนของเหรียญ", PCTS, key="op_pct_sell",
                 label_visibility="collapsed", on_change=_apply_pct,
                 args=("op_pct_sell", qty_key, coin_bal, "sell"))

        sell_px = quote_sell
        if is_limit:
            sell_px = st.number_input("Limit price (THB)", min_value=0.0, format="%.4f",
                                      value=float(round(quote_sell, 4)), key=f"op_sell_px_{asset}")
        net_thb = sell_qty * sell_px * (1 - fee)
        
        st.markdown(
            f'<div class="op-ro"><span>ราคาต่อ {asset}</span><b>{sell_px:,.2f} THB</b></div>'
            f'<div class="op-ro"><span>THB จำนวนที่จะได้รับ</span>'
            f'<b>≈ {net_thb:,.2f} THB</b></div>',
            unsafe_allow_html=True)
            
        over_coin = sell_qty > coin_bal + 1e-9
        if over_coin:
            st.markdown(f'<div class="op-warn">{asset} ในกระเป๋าไม่พอ</div>',
                        unsafe_allow_html=True)
        sell_clicked = st.button(f"ขาย (Sell) {asset}", key="op_sell_btn",
                                 disabled=(sell_qty <= 0 or over_coin), **WIDE)

    if buy_clicked:
        if is_limit:
            _place_limit("buy", float(buy_amt), 0.0, float(buy_px))
        else:
            _submit_order(sim, "buy", float(buy_amt), data, current_date_val, ctx)
    elif sell_clicked:
        if is_limit:
            _place_limit("sell", 0.0, float(sell_qty), float(sell_px))
        else:
            _submit_order(sim, "sell", float(sell_qty * quote_sell), data, current_date_val, ctx)

    # แสดงออเดอร์ที่รอจับคู่
    for o in sim.get("open_orders", []):
        c1, c2 = st.columns([5, 1])
        c1.caption(f"{o['side'].upper()} @ {o['px']:,.4f} — "
                   f"{o['amount_thb']:,.2f} THB" if o["side"] == "buy"
                   else f"SELL @ {o['px']:,.4f} — {o['qty']:.8f} {asset}")
        c2.button("Cancel", key=f"cx_{o['id']}", on_click=_cancel_limit, args=(o["id"],))


def _order_panel_live_body(cfg, sim, asset, mid_now, data, current_date_val, ctx):
    render_order_panel(cfg, sim, asset, _frozen_mid(asset, mid_now),
                       data, current_date_val, ctx)

if HAS_FRAGMENT:
    _order_panel_live = st.fragment(run_every=QUOTE_REFRESH_SEC)(_order_panel_live_body)
else:
    _order_panel_live = _order_panel_live_body


def render_tab3(cfg: dict[str, Any], data: pd.DataFrame, data_err: Optional[str],
                price_lookup: Optional[dict[str, float]] = None,
                market_df: Optional[pd.DataFrame] = None) -> None:

    if data.empty:
        st.error(f"⚠️ ต้องโหลดราคาจริงก่อนถึงจะจำลองได้: {data_err or 'ไม่สามารถโหลดข้อมูลได้'}")
        return

    asset = cfg["asset"]
    settlement_days = cfg["settlement_days"]

    rp_sim = risk_profile(data["Global_USD"])
    if rp_sim is None:
        st.error(f"ข้อมูลย้อนหลังน้อยกว่า {MIN_RISK_SAMPLE_DAYS} วัน — กรุณาเลือกช่วงเวลาให้ยาวขึ้น")
        return

    h_crypto_sim = crypto_haircut(rp_sim["es99"], settlement_days)
    h_cex_sim = cfg["cex_counterparty_haircut"] if cfg["cex_margin_asset"].startswith("Stablecoin") else h_crypto_sim

    a_factor_sim = safety_stock_factor(cfg["net_bias_pct"], cfg["flow_cv_pct"], settlement_days, cfg["z_alpha"])
    target_stock_thb = a_factor_sim * cfg["monthly_volume_thb"]
    cex_liquidity_thb = max(0.0, float(cfg["cex_margin_thb"]))

    ctx = dict(
        asset=asset, local_premium=cfg["local_premium"], spread=cfg["dealer_spread"],
        hedge_fee=cfg["hedge_fee"], fx_limit=cfg["fx_limit_max"], slip_sens=cfg["slippage_sensitivity"],
        market_depth_usd=cfg["market_depth_usd"], impact_penalty=cfg["impact_penalty"],
        include_fee_rev=cfg["include_trading_fee_revenue"], wd_markup=cfg["withdrawal_fee_markup_pct"],
        wd_fee_per_coin=WITHDRAWAL_FEE_TABLE.get(asset, 0.0), bank_type=cfg["bank_type"],
        ktb_wd_fee=cfg["ktb_wd_fee_thb"], ktb_fx_bps=cfg["ktb_fx_spread_bps"],
        capital=cfg["total_capital_thb"], cex_margin=cfg["cex_margin_thb"],
        cex_liquidity_thb=cex_liquidity_thb, liab=cfg["liab_thb"],
        h_crypto=h_crypto_sim, h_cex=h_cex_sim, fixed_min_nc=cfg["fixed_min_nc"],
        trading_risk_rate=cfg["trading_risk_rate"], daily_volume_thb=cfg["daily_volume_thb"],
        custody_rate=cfg["custody_rate_blended"], hot_breach=cfg["hot_wallet_cap_breach"],
    )

    signature = sim_config_signature(ctx, target_stock_thb, cfg["start_date"], cfg["end_date"])

    if "sim" not in st.session_state:
        first_day = pd.to_datetime(data.index[-1])
        st.session_state.sim = sim_defaults(
            asset, first_day, data.loc[first_day, "Global_USD"],
            data.loc[first_day, "USDTHB"], target_stock_thb)
        st.session_state.sim_steps = []

    current_date_val = pd.to_datetime(data.index[-1])   # ราคาปัจจุบันเสมอ
    st.session_state.sim["current_date"] = current_date_val

    spot_usd_current = float(data.loc[current_date_val, "Global_USD"])
    usdthb_current = float(data.loc[current_date_val, "USDTHB"])

    sim = sim_normalize_state(st.session_state.sim, asset, current_date_val, spot_usd_current, usdthb_current, target_stock_thb)
    st.session_state.sim = sim

    mid_now = spot_usd_current * usdthb_current * (1 + cfg["local_premium"])
    
    check_open_orders(sim, mid_now * (1 + cfg["dealer_spread"]),
                      mid_now * (1 - cfg["dealer_spread"]), data, current_date_val, ctx)

    row_now = data.loc[current_date_val]
    fx_adj = usdthb_current * (1 + cfg["local_premium"])
    high_24h = float(row_now["Day_High"]) * fx_adj
    low_24h = float(row_now["Day_Low"]) * fx_adj
    vol_24h_thb = cfg["daily_volume_thb"]
    if market_df is not None and not market_df.empty:
        _r = market_df[market_df["symbol"] == asset]
        if not _r.empty:
            vol_24h_thb = float(_r["volume"].iloc[0]) * usdthb_current

    pct_24h = None
    if market_df is not None and not market_df.empty:
        m_row = market_df[market_df["symbol"] == asset]
        if not m_row.empty:
            pct_24h = float(m_row["pct_change"].iloc[0])
    if pct_24h is None:
        pct_txt, pct_cls = "เปลี่ยน 24H —", ""
    else:
        pct_txt = f"เปลี่ยน 24H {'+' if pct_24h >= 0 else ''}{pct_24h:.2f}%"
        pct_cls = "ex-green" if pct_24h >= 0 else "ex-red"

    # --- TOP HEADER BAR ---
    top_bar_html = f"""<div class="ex-header">
        <div style="display:flex; align-items:center; gap:12px;">
            {coin_icon_html(asset, 40)}
            <div class="ex-stat">
                <span style="font-size:1.4rem; font-weight:700; color:#EAECEF;">{asset}/THB</span>
                <span style="font-size:0.8rem; font-weight:600;" class="{pct_cls}">{pct_txt}</span>
            </div>
        </div>
        <div class="ex-stat"><span class="ex-stat-label">ราคาล่าสุด (THB)</span><span class="ex-stat-val ex-green">{mid_now:,.2f}</span></div>
        <div class="ex-stat"><span class="ex-stat-label">สูงสุด 24H (THB)</span><span class="ex-stat-val">{high_24h:,.2f}</span></div>
        <div class="ex-stat"><span class="ex-stat-label">ต่ำสุด 24H (THB)</span><span class="ex-stat-val">{low_24h:,.2f}</span></div>
        <div class="ex-stat"><span class="ex-stat-label">ปริมาณ 24H (THB)</span><span class="ex-stat-val">{fmt_num(vol_24h_thb)}</span></div>
        <div class="ex-stat"><span class="ex-stat-label">วันที่ (ปัจจุบัน)</span><span class="ex-stat-val" style="color:#fcd535;">{current_date_val.strftime('%Y-%m-%d')}</span></div>
    </div>"""
    st.markdown(top_bar_html, unsafe_allow_html=True)

    # --- MAIN LAYOUT: Market | Chart + Order Panel + Tabs ---
    col_left, col_center = st.columns([2.6, 7.4], gap="small")

    with col_left:
        st.markdown('<div style="font-size:1.15rem; font-weight:700; color:#EAECEF; margin-bottom:12px; display:flex; align-items:center; gap:8px;">🌍 ภาพรวมตลาด (Market)</div>', unsafe_allow_html=True)
        m_df = market_df if market_df is not None else pd.DataFrame()
        sub1, sub2, sub3, sub4 = st.tabs(["⭐", "ปริมาณ", "▲ เพิ่ม", "▼ ลด"])
        for sub, mode in zip((sub1, sub2, sub3, sub4),
                             ("favorite", "volume", "top_gain", "top_loss")):
            with sub:
                try:
                    cont = st.container(height=480, border=False)
                except Exception:
                    cont = st.container()
                with cont:
                    render_market_column_view(m_df, mode, asset, usdthb_current)

    with col_center:
        local_sym = TV_LOCAL_SYMBOL.get(asset, f"BITKUB:{asset}THB")
        render_tradingview(local_sym, f"tv_center_{asset}", 460,
                           studies=["MAExp@tv-basicstudies"])

        with st.container(border=True):
            _order_panel_live(cfg, sim, asset, mid_now, data, current_date_val, ctx)

        with st.expander("🎲 เครื่องมือจำลอง — สุ่มออเดอร์ / รีเซ็ต", expanded=False):
            st.caption("สุ่มออเดอร์ = ลูกค้าคนอื่นในตลาด ไม่แตะกระเป๋าของคุณ · "
                       "สุ่มทั้งเหรียญ วันที่ ฝั่งซื้อ/ขาย และจำนวนเงิน · "
                       "รีเซ็ตจะล้างทุกอย่างรวมถึงกระเป๋า")
            coins_pick = st.multiselect("เหรียญที่ให้สุ่ม", SUPPORTED_ASSETS,
                                        default=SUPPORTED_ASSETS, key="sim_coins")
            b1, b2, b3 = st.columns(3)
            n_orders = b1.number_input("จำนวนออเดอร์สุ่ม", value=20, min_value=1,
                                       step=10, key="sim_n")
            seed = b2.number_input("Random seed", value=42, step=1, key="sim_seed")
            run_batch = b3.button("🎲 สุ่มออเดอร์ (Auto-Run)", key="sim_batch", **WIDE)
            a1, a2 = st.columns(2)
            amt_min = a1.number_input("ยอดต่ำสุด/ออเดอร์ (THB)", value=50.0,
                                      min_value=float(MIN_TRADE_THB), step=50.0,
                                      key="sim_amt_min")
            amt_max = a2.number_input("ยอดสูงสุด/ออเดอร์ (THB)", value=100000.0,
                                      min_value=float(MIN_TRADE_THB), step=1000.0,
                                      key="sim_amt_max")
            reset = st.button("♻️ ล้างระบบใหม่", key="sim_reset", **WIDE)
            summ = st.session_state.get("sim_batch_summary")
            if summ:
                st.caption(summ)

        if reset:
            first_day = pd.to_datetime(data.index[-1])
            st.session_state.sim = sim_defaults(
                asset, first_day, data.loc[first_day, "Global_USD"],
                data.loc[first_day, "USDTHB"], target_stock_thb)
            st.session_state.sim_signature = signature
            st.session_state.sim_steps = []
            
            st.session_state["favorite_tickers"] = []
            try:
                save_favorites([])
            except OSError:
                pass
                
            st.rerun()

        if run_batch:
            if not coins_pick:
                st.warning("เลือกอย่างน้อย 1 เหรียญ")
            else:
                steps_, counts, skipped = run_random_batch(
                    sim, cfg, ctx, target_stock_thb, coins_pick,
                    n_orders, seed, amt_min, amt_max)
                st.session_state.sim_steps = steps_
                txt = "สุ่มแล้ว: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
                if skipped:
                    txt += f" · โหลดราคาไม่ได้: {', '.join(skipped)}"
                st.session_state.sim_batch_summary = txt
                st.rerun()

        st.markdown('<div style="margin-top:14px;"></div>', unsafe_allow_html=True)
        t_route, t_ledger, t_wallet = st.tabs(
            ["🚀 System Routing (ออเดอร์ล่าสุด)", "📒 สมุดออเดอร์ (Ledger)", "💼 Wallet & Capital"])

        with t_route:
            steps_now = st.session_state.get("sim_steps", [])
            if not steps_now:
                st.info("ยังไม่มีออเดอร์ — กดซื้อ/ขายด้านบนเพื่อดูระบบเดินงานทีละด่าน")
            else:
                render_timeline(steps_now)

        with t_ledger:
            if not sim["orders"]:
                st.caption("ยังไม่มีข้อมูลการเทรด")
            else:
                led = pd.DataFrame(sim["orders"])
                if st.checkbox(f"แสดงเฉพาะ {asset}", key="led_only_asset"):
                    led = led[led["เหรียญ"] == asset]
                led.index = range(1, len(led) + 1)
                st.dataframe(led.sort_index(ascending=False), height=240, **WIDE)

        with t_wallet:
            stock_thb_now = (max(0.0, sim["inv_coins"].get(asset, 0.0))
                             * spot_usd_current * usdthb_current)
            fx_left = max(0.0, cfg["fx_limit_max"] - sim["fx_used_usd"])
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("สต็อกคงเหลือ (THB)", fmt_baht(stock_thb_now))
                st.metric("เหรียญคงเหลือ", fmt_coin(sim["inv_coins"].get(asset, 0.0), asset))
            with c2:
                st.metric("Outbound FX ใช้ไป ($)", f"{sim['fx_used_usd']:,.0f}")
                st.metric("FX โควตาคงเหลือ ($)", f"{fx_left:,.0f}")
            with c3:
                st.metric("กำไรสะสม Dealer (THB)", fmt_baht(sim["pnl_thb"], True))
                st.metric("ออเดอร์ทั้งหมด", f"{len(sim['orders'])} รายการ")


def _parse_amount(text: Any) -> float:
    try:
        v = float(str(text).replace(",", "").replace(" ", "").strip())
    except ValueError:
        return 0.0
    return v if math.isfinite(v) and v > 0 else 0.0


def _open_deposit() -> None:
    st.session_state["open_deposit"] = True
    st.session_state["dep_error"] = None


def _set_dep_amt(v: float) -> None:
    st.session_state["dep_amt"] = f"{v:,.0f}"


def _do_deposit() -> None:
    amt = _parse_amount(st.session_state.get("dep_amt", "0"))
    if amt <= 0:
        st.session_state["dep_error"] = "กรอกจำนวนเงินที่มากกว่า 0"
        return
    sim = st.session_state.get("sim")
    if not isinstance(sim, dict):
        sim = {"customer_thb": 1_000_000.0, "customer_coins": {}}
        st.session_state["sim"] = sim
    sim["customer_thb"] = float(sim.get("customer_thb", 1_000_000.0)) + amt
    st.session_state["dep_amt"] = "0"
    st.session_state["dep_error"] = None
    st.session_state["dep_done"] = amt


def _deposit_dialog_body() -> None:
    done = st.session_state.pop("dep_done", None)
    if done:
        st.session_state["dep_toast"] = done
        st.rerun()  # รีรันทั้งแอป: ปิดหน้าต่าง + อัปเดตยอดในตาราง

    sim = st.session_state.get("sim")
    cash = float(sim.get("customer_thb", 1_000_000.0)) if isinstance(sim, dict) else 1_000_000.0
    st.markdown(f"ยอดเงินบาทคงเหลือ: **{cash:,.2f} THB**")

    amt = comma_number_input("จำนวนเงินที่ต้องการฝาก (THB)", value=0,
                             min_value=0, key="dep_amt")
    quick = st.columns(4, gap="small")
    for col, v in zip(quick, (1_000, 10_000, 100_000, 1_000_000)):
        col.button(f"{v:,.0f}", key=f"dep_q_{v}", on_click=_set_dep_amt,
                   args=(float(v),), **WIDE)

    st.caption(f"ยอดหลังฝาก: {cash + amt:,.2f} THB · โหมดจำลอง เงินนี้ใช้ในกระเป๋าจำลองเท่านั้น")
    err = st.session_state.get("dep_error")
    if err:
        st.error(err)
    st.button("ยืนยันการฝาก", key="dep_confirm", type="primary",
              on_click=_do_deposit, **WIDE)


def deposit_dialog() -> None:
    # ห่อ st.dialog ตอนเรียกใช้ (ไม่ใช้ @decorator ระดับโมดูล)
    # เพื่อให้ import ไฟล์นี้ใน unittest ได้แม้ไม่มี streamlit
    st.dialog("ฝากเงินบาท")(_deposit_dialog_body)()


# ---- 5.5 TAB 4 — WALLET ------------------------------------------------

def render_tab4(cfg: dict[str, Any], data: pd.DataFrame, market_df: pd.DataFrame) -> None:
    if data.empty:
        st.error("⚠️ ไม่สามารถโหลดข้อมูลได้")
        return

    sim = st.session_state.get("sim", {})
    current_date_val = pd.to_datetime(data.index[-1])

    usdthb_current = float(data.loc[current_date_val, "USDTHB"])
    cust_thb = sim.get("customer_thb", 1000000.0)
    cust_coins = sim.get("customer_coins", {})

    price_thb_map = {"THB": 1.0}
    if market_df is not None and not market_df.empty:
        for _, row in market_df.iterrows():
            sym = str(row["symbol"])
            price_thb_map[sym] = float(row["price_usd"]) * usdthb_current
    price_thb_map[cfg["asset"]] = float(data.loc[current_date_val, "Global_USD"]) * usdthb_current

    total_thb = cust_thb
    for sym, qty in cust_coins.items():
        total_thb += qty * price_thb_map.get(sym, 0.0)

    total_usdt = total_thb / usdthb_current if usdthb_current > 0 else 0
    time_str = pd.Timestamp.now(tz="Asia/Bangkok").strftime("%H:%M:%S")

    # Header (ไม่มีปุ่มฝาก/ถอน/ประวัติ ตามที่ร้องขอ)
    st.markdown(
        f'<div style="margin-bottom:20px;">'
        f'<h2 style="margin:0; color:#EAECEF; font-size:1.8rem;">กระเป๋าเงิน</h2>'
        f'</div>',
        unsafe_allow_html=True
    )

    # Total Box
    st.markdown(
        f'<div class="wl-box" style="margin-bottom:20px;">'
        f'<div style="font-size:0.9rem; color:#848e9c; font-weight:600;">มูลค่าทั้งหมด</div>'
        f'<div class="wl-total-val">{total_thb:,.2f} <span style="font-size:1.2rem; color:#848e9c;">THB</span></div>'
        f'<div style="font-size:0.9rem; color:#848e9c;">≈ {total_usdt:,.2f} USDT <span style="float:right; font-size:0.8rem;">อัปเดตล่าสุด: {time_str}</span></div>'
        f'</div>',
        unsafe_allow_html=True
    )

    # Asset Table Title and Controls
    st.markdown(
        '<div style="display:flex; align-items:center; margin-bottom:16px; gap:8px;">'
        '<div style="width:3px; height:16px; background:#0ecb81; border-radius:2px;"></div>'
        '<div style="font-size:1.05rem; font-weight:700; color:#EAECEF;">สินทรัพย์</div>'
        '</div>',
        unsafe_allow_html=True
    )

    c_search, c_hide, c_pad = st.columns([2, 1.5, 6])
    with c_search:
        search_q = st.text_input("ค้นหา", label_visibility="collapsed", placeholder="🔍 ค้นหาสินทรัพย์")
    with c_hide:
        st.markdown('<div style="margin-top:8px;"></div>', unsafe_allow_html=True)
        hide_small = st.checkbox("ซ่อนเหรียญที่มูลค่า < 1 บาท", value=False)

    # Asset List Construction
    assets_to_show = [{"sym": "THB", "qty": cust_thb, "price": 1.0, "val": cust_thb}]
    for sym in SUPPORTED_ASSETS:
        qty = cust_coins.get(sym, 0.0)
        price = price_thb_map.get(sym, 0.0)
        assets_to_show.append({"sym": sym, "qty": qty, "price": price, "val": qty * price})
        
    WL = [2.2, 1.5, 1.5, 1.5, 1.3]
    with st.container(key="wl_table"):
        with st.container(key="wlhead"):
            hc = st.columns(WL, vertical_alignment="center", gap="small")
            heads = ["สินทรัพย์ ↕", "มูลค่าทั้งหมด ↕", "จำนวนที่ใช้ได้ ↕", "รอดำเนินการ ↕", ""]
            aligns = ["left", "right", "right", "right", "right"]
            for col, txt, al in zip(hc, heads, aligns):
                col.markdown(f'<div class="wl-h" style="text-align:{al}">{txt}</div>',
                             unsafe_allow_html=True)
        for a in assets_to_show:
            sym = a["sym"]
            sub_name = COIN_NAMES.get(sym, "Thai Baht")
            if hide_small and a["val"] < 1.0:
                continue
            if search_q and search_q.lower() not in sym.lower() \
                    and search_q.lower() not in sub_name.lower():
                continue
            with st.container(key=f"wlrow_{sym}"):
                c_ast, c_val, c_qty, c_pend, c_act = st.columns(
                    WL, vertical_alignment="center", gap="small")
                with c_ast:
                    c_ic, c_nm = st.columns([1, 6], vertical_alignment="center", gap="small")
                    c_ic.markdown(coin_icon_html(sym, 28), unsafe_allow_html=True)
                    if sym == "THB":
                        c_nm.markdown('<div class="wl-name">THB<br><span>Thai Baht</span></div>',
                                      unsafe_allow_html=True)
                    else:
                        c_nm.button(f"{sym}  ·  {sub_name}", key=f"wlbtn_{sym}",
                                    type="tertiary", on_click=_go_to_exchange, args=(sym,),
                                    help=f"เปิดกราฟและหน้าเทรด {sym}")
                c_val.markdown(f'<div class="wl-cell">{a["val"]:,.2f}</div>', unsafe_allow_html=True)
                c_qty.markdown(f'<div class="wl-cell">{a["qty"]:,.6f}</div>', unsafe_allow_html=True)
                c_pend.markdown('<div class="wl-cell" style="color:#848e9c;">0.00</div>',
                                unsafe_allow_html=True)
                
                a_dep, a_wd, a_more = c_act.columns([1, 1, 0.7],
                                                    vertical_alignment="center", gap="small")
                if sym == "THB":
                    a_dep.button("ฝาก", key="wl_deposit", type="tertiary",
                                 on_click=_open_deposit, **WIDE)
                else:
                    a_dep.markdown('<div class="wl-act">ฝาก</div>', unsafe_allow_html=True)
                a_wd.markdown('<div class="wl-act">ถอน</div>', unsafe_allow_html=True)
                a_more.markdown('<div class="wl-act wl-more">•••</div>', unsafe_allow_html=True)

    dep_toast = st.session_state.pop("dep_toast", None)
    if dep_toast:
        st.toast(f"ฝากเงิน {dep_toast:,.2f} THB สำเร็จ", icon="✅")
    if st.session_state.pop("open_deposit", False):
        deposit_dialog()

def _main_body() -> None:
    st.set_page_config(
        page_title="XSpring Dealer Suite",
        page_icon="\u267b\ufe0f",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(THEME_CSS, unsafe_allow_html=True)

    if "sim" not in st.session_state:
        saved = load_sim_state()
        if saved:
            st.session_state["sim"] = saved

    if "favorite_tickers" not in st.session_state:
        st.session_state["favorite_tickers"] = load_favorites()

    cfg = build_sidebar()

    if not cfg["dates_ok"]:
        data, data_err = pd.DataFrame(), "ช่วงวันที่ไม่ถูกต้อง"
    else:
        data, data_err = fetch_price_data(cfg["asset"], cfg["start_date"],
                                          cfg["end_date"],
                                          use_fx_proxy=cfg["use_fx_proxy"])

    market_df = fetch_market_overview(SUPPORTED_ASSETS)

    if "main_nav" not in st.session_state:
        st.session_state["main_nav"] = NAV_LABELS[0]

    nav = st.radio("เมนูหลัก", NAV_LABELS, horizontal=True, key="main_nav",
                   label_visibility="collapsed")

    if nav == NAV_LABELS[0]:
        render_tab1(cfg, data, data_err)
    elif nav == NAV_LABELS[1]:
        render_tab2(cfg, data, data_err)
    elif nav == NAV_LABELS[2]:
        render_tab3(cfg, data, data_err,
                    price_lookup={row["symbol"]: row["price_usd"] for _, row in market_df.iterrows()} if not market_df.empty else {},
                    market_df=market_df)
    else:
        render_tab4(cfg, data, market_df=market_df)

    st.markdown(
        f"<div class='xs-foot'>XSpring Dealer Suite · Model v{MODEL_VERSION} · "
        f"Config {CONFIG_INFO['sha256'] or 'built-in defaults'} · "
        "Planning model เพื่อการวางแผนภายในเท่านั้น "
        "ไม่ใช่เครื่องมือรับรอง compliance</div>",
        unsafe_allow_html=True,
    )

def main() -> None:
    try:
        _main_body()
    finally:
        # finally ทำงานแม้มี st.rerun() ทำให้ทุกออเดอร์ถูกเซฟเสมอ
        try:
            save_sim_state(st.session_state.get("sim"))
        except Exception:
            pass

if __name__ == "__main__":
    if not HAS_UI:
        raise SystemExit("ต้องติดตั้ง UI stack ก่อน: pip install streamlit plotly yfinance")
    main()
