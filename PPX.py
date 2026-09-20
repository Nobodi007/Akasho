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
  5. APP                    sidebar + 3 tabs (อยู่ใน main() ทั้งหมด)

TESTABILITY
-----------
UI ถูกเรียกใต้ `if __name__ == "__main__"` เท่านั้น
  - Streamlit รันไฟล์นี้เป็น __main__  -> UI ทำงานปกติ
  - unittest ทำ `import xspring_dealer_suite as eng`    -> ได้เฉพาะ LAYER 0-1 ไม่มี side effect

MODEL_VERSION / CHANGELOG
-------------------------
v1.5.8              + รื้อระบบคลิกเหรียญ ซ่อนปุ่มเลือก 100% ให้คลิกที่แถวได้เลยโดยไม่ Reload หน้าเว็บ
                      + เพิ่มปุ่มรูปดาว (★/☆) ให้กดเพื่อเพิ่ม/ลดรายการโปรดได้จากหน้ารายการเหรียญโดยตรง
                      + อัปเดต CSS แท็บเมนู (Tabs) ให้มีขีดเส้นใต้สีเขียวสไตล์ Exchange
v1.5.5              + แก้ไข TypeError ตอนเรียก render_tab1 ในฟังก์ชัน main
v1.5.4              + ทำระบบ "คลิกเหรียญแล้วกราฟเปลี่ยนตาม"
v1.5.3              + ย้าย Market Overview มาไว้ด้านซ้าย และแก้ไข CDN รูปภาพเหรียญทั้งหมด
v1.5.2              + ลบฟังก์ชัน Orderbook และเหรียญที่ไม่ได้รองรับโลโก้ออกเพื่อลดการประมวลผลเครื่อง
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

import numpy as np
import pandas as pd

MODEL_VERSION = "1.5.8"

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

COIN_LOGOS = {
    "BTC": "https://assets.coingecko.com/coins/images/1/small/bitcoin.png",
    "ETH": "https://assets.coingecko.com/coins/images/279/small/ethereum.png",
    "USDT": "https://assets.coingecko.com/coins/images/325/small/Tether.png",
    "USDC": "https://assets.coingecko.com/coins/images/6319/small/usdc.png",
    "SOL": "https://assets.coingecko.com/coins/images/4128/small/solana.png",
    "ADA": "https://assets.coingecko.com/coins/images/975/small/cardano.png",
    "DOGE": "https://assets.coingecko.com/coins/images/5/small/dogecoin.png",
    "LINK": "https://assets.coingecko.com/coins/images/877/small/chainlinknew-bg.png",
    "XRP": "https://assets.coingecko.com/coins/images/44/small/xrp-symbol-white-128.png",
    "XLM": "https://assets.coingecko.com/coins/images/100/small/Stellar_symbol_black_RGB.png",
    "HBAR": "https://assets.coingecko.com/coins/images/3688/small/hbar.png",
    "THB": "https://cdn-icons-png.flaticon.com/512/197/197583.png",
}

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
    }

def sim_config_signature(ctx: Mapping[str, Any], target_stock_thb: float,
                         start_date: Any, end_date: Any) -> tuple:
    keys = [
        "local_premium", "spread", "hedge_fee",
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
    px_row: pd.Series, ctx: Mapping[str, Any],
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
    coins = settlement_thb / quote

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
                    ("FX quota เหลือ", f"$ {fx_left_usd:,.0f}"),
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

    coins_book = sim.setdefault("customer_coins", {})
    if side == "buy":
        coins_book[current_asset] = coins_book.get(current_asset, 0.0) + coins
    else:
        coins_book[current_asset] = max(0.0, coins_book.get(current_asset, 0.0) - coins)

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


@_cache_data(ttl=3600, show_spinner="กำลังโหลดข้อมูลราคาย้อนหลัง…")
def fetch_price_data(ticker: str, start: Any, end: Any,
                     use_fx_proxy: bool = False) -> tuple[pd.DataFrame, Optional[str]]:
    try:
        raw = yf.download(f"{ticker}-USD", start=start, end=end,
                          auto_adjust=False, progress=False)
        fx_raw = yf.download("THB=X", start=start, end=end,
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

    /* Fix Streamlit Buttons to look like Exchange Action buttons */
    button[data-testid="baseButton-secondary"]:has(div:contains("ซื้อ")) {
        background-color: #0ecb81 !important; color: white !important; border: none !important; width: 100% !important; font-weight: bold; padding: 12px !important;
    }
    button[data-testid="baseButton-secondary"]:has(div:contains("ขาย")) {
        background-color: #f6465d !important; color: white !important; border: none !important; width: 100% !important; font-weight: bold; padding: 12px !important;
    }
    button[data-testid="baseButton-secondary"]:has(div:contains("สุ่มออเดอร์")) {
        background-color: #fcd535 !important; color: #181a20 !important; border: none !important; font-weight: bold; width: 100% !important;
    }

    /* MAGIC HACK: Market Row Select Button (Invisible Overlay) */
    div[data-testid="stVerticalBlock"]:has(button p:contains("‌")) {
        position: relative !important;
        gap: 0 !important;
    }
    button[data-testid="baseButton-secondary"]:has(p:contains("‌")) {
        position: absolute !important;
        top: 0 !important; left: 0 !important; right: 0 !important; bottom: 0 !important;
        width: 100% !important; height: 100% !important;
        opacity: 0 !important; z-index: 10 !important; cursor: pointer !important;
    }
    
    /* Star Button Styling */
    button[data-testid="baseButton-secondary"]:has(p:contains("★")),
    button[data-testid="baseButton-secondary"]:has(p:contains("☆")) {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        color: #fcd535 !important;
        font-size: 1.25rem !important;
        width: 100% !important;
        margin-top: 5px !important;
        min-height: 0 !important;
    }
    button[data-testid="baseButton-secondary"]:has(p:contains("☆")) {
        color: #5e6673 !important;
    }
    button[data-testid="baseButton-secondary"]:has(p:contains("★")):hover,
    button[data-testid="baseButton-secondary"]:has(p:contains("☆")):hover {
        transform: scale(1.15);
        color: #fcd535 !important;
    }

    /* Tighten Market List Rows */
    div[data-testid="stHorizontalBlock"]:has(.mk-row) {
        align-items: center !important;
        border-bottom: 1px solid #1f2329 !important;
        padding: 4px 8px !important;
        margin-bottom: 0 !important;
        gap: 0 !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.mk-row):hover {
        background-color: #2b3139 !important;
        border-radius: 4px;
    }
    div[data-testid="stHorizontalBlock"]:has(.mk-row) > div[data-testid="column"] {
        padding: 0 !important;
    }
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
        render_tradingview(local_sym, "tv_bt_local", 520,
                           studies=["RSI@tv-basicstudies"])
    elif tv_mode == "กระดานโลก (Binance)":
        render_tradingview(global_sym, "tv_bt_global", 520,
                           studies=["RSI@tv-basicstudies"])
    else:
        g1, g2 = st.columns(2)
        with g1:
            st.caption(f"🇹🇭 ราคาจริงฝั่งไทย — `{local_sym}`")
            render_tradingview(local_sym, "tv_cmp_local", 420)
        with g2:
            st.caption(f"🌐 ราคาโลก — `{global_sym}`")
            render_tradingview(global_sym, "tv_cmp_global", 420)

def get_coin_logo(symbol: str) -> str:
    return COIN_LOGOS.get(symbol, "https://cdn-icons-png.flaticon.com/512/1490/1490844.png")

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

def render_market_column_view(df: pd.DataFrame, mode: str, current_asset: str, usdthb: float) -> None:
    if df.empty:
        st.markdown('<div style="padding:16px; color:#848e9c; font-size:0.85rem; text-align:center;">ไม่มีข้อมูลตลาด</div>', unsafe_allow_html=True)
        return
    
    if mode == "favorite":
        favs = st.session_state.get("favorite_tickers", [])
        view = df[df["symbol"].isin(favs)]
        if view.empty:
            st.markdown('<div style="padding:32px 8px; color:#848e9c; font-size:0.9rem; text-align:center;">ยังไม่มีรายการโปรด<br><span style="font-size:0.8rem;">(กดรูปดาว ☆ ด้านล่างเพื่อเพิ่ม)</span></div>', unsafe_allow_html=True)
            return
        view = view.sort_values("volume", ascending=False)
    elif mode == "volume":
        view = df.sort_values("volume", ascending=False)
    elif mode == "top_gain":
        view = df.sort_values("pct_change", ascending=False)
    elif mode == "top_loss":
        view = df.sort_values("pct_change", ascending=True)
    else:
        view = df

    st.markdown('<div style="display:flex; justify-content:space-between; font-size:0.75rem; color:#848e9c; margin-bottom:8px; padding:0 12px;"><span>&nbsp;&nbsp;&nbsp;&nbsp;สินทรัพย์</span><span>ราคา (THB)</span></div>', unsafe_allow_html=True)
    
    for _, row in view.iterrows():
        sym = str(row["symbol"])
        name = COIN_NAMES.get(sym, sym)
        p_usd = float(row["price_usd"])
        p_thb = p_usd * usdthb
        pct = float(row["pct_change"])
        c_class = "ex-green" if pct >= 0 else "ex-red"
        sign = "+" if pct >= 0 else ""
        logo = get_coin_logo(sym)
        p_str = f"{p_thb:,.2f}" if p_thb >= 1 else f"{p_thb:,.4f}"
        
        c1, c2 = st.columns([1, 6])
        with c1:
            is_fav = sym in st.session_state.get("favorite_tickers", [])
            star = "★" if is_fav else "☆"
            if st.button(star, key=f"fav_{mode}_{sym}"):
                favs = st.session_state.get("favorite_tickers", [])
                if sym in favs: favs.remove(sym)
                else: favs.append(sym)
                st.session_state["favorite_tickers"] = favs
                st.rerun()
        with c2:
            active_style = "border-left: 3px solid #0ecb81; background: rgba(14,203,129,0.05);" if sym == current_asset else "border-left: 3px solid transparent;"
            html = f"""
            <div class="mk-row" style="display:flex; justify-content:space-between; align-items:center; width:100%; {active_style} padding:4px 0;">
                <div style="display:flex; align-items:center; gap:10px;">
                    <img src="{logo}" style="width:24px; height:24px; border-radius:50%; object-fit:contain; background:#181a20; padding:1px;">
                    <div style="line-height:1.2;">
                        <div style="font-weight:700; color:#EAECEF; font-size:0.9rem;">{sym}</div>
                        <div style="font-size:0.65rem; color:#848e9c;">{name}</div>
                    </div>
                </div>
                <div style="text-align:right; padding-right:8px;">
                    <div style="font-size:0.9rem; font-weight:700; color:#EAECEF;">{p_str}</div>
                    <div class="{c_class}" style="font-size:0.75rem; font-weight:600;">{sign}{pct:.2f}%</div>
                </div>
            </div>
            """
            st.markdown(html, unsafe_allow_html=True)
            if st.button(f"\u200C{sym}_{mode}", key=f"sel_{mode}_{sym}", use_container_width=True):
                st.session_state["bt_asset"] = sym
                st.rerun()

@_fragment
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
    need_reset = (("sim" not in st.session_state) or st.session_state.get("sim_signature") != signature)

    if need_reset:
        first_day = pd.to_datetime(data.index[0])
        st.session_state.sim = sim_defaults(asset, first_day, data.loc[first_day, "Global_USD"], data.loc[first_day, "USDTHB"], target_stock_thb)
        st.session_state.sim_signature = signature
        st.session_state.sim_steps = []

    current_date_val = pd.to_datetime(st.session_state.sim.get("current_date", data.index[0]))
    if current_date_val not in data.index:
        current_date_val = pd.to_datetime(data.index[0])
        st.session_state.sim["current_date"] = current_date_val

    spot_usd_current = float(data.loc[current_date_val, "Global_USD"])
    usdthb_current = float(data.loc[current_date_val, "USDTHB"])

    sim = sim_normalize_state(st.session_state.sim, asset, current_date_val, spot_usd_current, usdthb_current, target_stock_thb)
    st.session_state.sim = sim

    mid_now = spot_usd_current * usdthb_current * (1 + cfg["local_premium"])
    vol_24h_thb = cfg["daily_volume_thb"]
    high_24h = mid_now * 1.025
    low_24h = mid_now * 0.982

    # --- TOP HEADER BAR ---
    top_bar_html = f"""<div class="ex-header">
        <div style="display:flex; align-items:center; gap:12px;">
            <img src="{get_coin_logo(asset)}" onerror="this.src='https://cdn-icons-png.flaticon.com/512/1490/1490844.png'" style="width:40px; height:40px; border-radius:50%; background:#181a20; padding:2px;">
            <div class="ex-stat">
                <span style="font-size:1.4rem; font-weight:700; color:#EAECEF;">{asset}/THB</span>
                <span style="font-size:0.8rem; font-weight:600;" class="ex-green">เปลี่ยน 24H +1.26%</span>
            </div>
        </div>
        <div class="ex-stat"><span class="ex-stat-label">ราคาล่าสุด (THB)</span><span class="ex-stat-val ex-green">{mid_now:,.2f}</span></div>
        <div class="ex-stat"><span class="ex-stat-label">สูงสุด 24H (THB)</span><span class="ex-stat-val">{high_24h:,.2f}</span></div>
        <div class="ex-stat"><span class="ex-stat-label">ต่ำสุด 24H (THB)</span><span class="ex-stat-val">{low_24h:,.2f}</span></div>
        <div class="ex-stat"><span class="ex-stat-label">ปริมาณ 24H (THB)</span><span class="ex-stat-val">{vol_24h_thb/1e6:,.2f}M</span></div>
        <div class="ex-stat"><span class="ex-stat-label">Time-Travel Date</span><span class="ex-stat-val" style="color:#fcd535;">{current_date_val.strftime('%Y-%m-%d')}</span></div>
    </div>"""
    st.markdown(top_bar_html, unsafe_allow_html=True)

    # --- MAIN LAYOUT (Columns: Market Overview | Chart & Tabs | Order Entry) ---
    col_left, col_center, col_right = st.columns([2.6, 5, 2.6], gap="small")

    # --- LEFT COLUMN: Market Overview Tabs ---
    with col_left:
        st.markdown('<div style="font-size:1.15rem; font-weight:700; color:#EAECEF; margin-bottom:12px; display:flex; align-items:center; gap:8px;">🌍 ภาพรวมตลาด (Market)</div>', unsafe_allow_html=True)
        
        m_df = market_df if market_df is not None else pd.DataFrame()
        
        sub1, sub2, sub3, sub4 = st.tabs(["⭐ โปรด", "ปริมาณ", "% เพิ่ม", "% ลด"])
        
        with sub1:
            try: cont1 = st.container(height=480, border=False)
            except: cont1 = st.container()
            with cont1:
                render_market_column_view(m_df, "favorite", asset, usdthb_current)
        with sub2:
            try: cont2 = st.container(height=480, border=False)
            except: cont2 = st.container()
            with cont2:
                render_market_column_view(m_df, "volume", asset, usdthb_current)
        with sub3:
            try: cont3 = st.container(height=480, border=False)
            except: cont3 = st.container()
            with cont3:
                render_market_column_view(m_df, "top_gain", asset, usdthb_current)
        with sub4:
            try: cont4 = st.container(height=480, border=False)
            except: cont4 = st.container()
            with cont4:
                render_market_column_view(m_df, "top_loss", asset, usdthb_current)

    # --- CENTER COLUMN: Chart & Timeline ---
    with col_center:
        st.markdown('<div class="ex-panel" style="padding:0; overflow:hidden; border:none; background:transparent;">', unsafe_allow_html=True)
        local_sym = TV_LOCAL_SYMBOL.get(asset, f"BITKUB:{asset}THB")
        render_tradingview(local_sym, "tv_center", 460, studies=["MAExp@tv-basicstudies"])
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div style="margin-top:14px;"></div>', unsafe_allow_html=True)
        t_route, t_ledger, t_wallet = st.tabs(["🚀 System Routing (ออเดอร์ล่าสุด)", "📒 สมุดออเดอร์ (Ledger)", "💼 Wallet & Capital"])
        
        with t_route:
            steps_now = st.session_state.get("sim_steps", [])
            if not steps_now:
                st.info("ยังไม่มีออเดอร์ — กดสั่งซื้อ/ขาย ด้านขวามือเพื่อดูระบบเดินงานทีละด่าน")
            else:
                render_timeline(steps_now)
                
        with t_ledger:
            if not sim["orders"]:
                st.caption("ยังไม่มีข้อมูลการเทรด")
            else:
                led = pd.DataFrame(sim["orders"])
                led.index = range(1, len(led) + 1)
                st.dataframe(led.sort_index(ascending=False), height=240, use_container_width=True)

        with t_wallet:
            stock_thb_now = max(0.0, sim["inv_coins"].get(asset, 0.0)) * spot_usd_current * usdthb_current
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

    # --- RIGHT COLUMN: Order Entry ---
    with col_right:
        with st.container(border=True):
            st.markdown("""<div class="oe-tabs">
                <span class="oe-tab">ลิมิต</span>
                <span class="oe-tab active">มาร์เก็ต</span>
                <span class="oe-tab">สต็อปลิมิต</span>
            </div>""", unsafe_allow_html=True)

            cash_balance = nc_snapshot(0, cfg["total_capital_thb"], cfg["cex_margin_thb"], cfg["liab_thb"], 0, 0, 0, 0, 0, 0)["cash"]
            coin_balance = sim["customer_coins"].get(asset, 0.0)

            st.markdown(f"""<div class="oe-bal">
                <span>คงเหลือ: <b style="color:#EAECEF;">{cash_balance:,.0f} THB</b></span>
                <span><b style="color:#EAECEF;">{coin_balance:,.6f} {asset}</b></span>
            </div>""", unsafe_allow_html=True)

            order_side = st.radio("ฝั่ง", ["ซื้อ", "ขาย"], horizontal=True, label_visibility="collapsed", key="sim_side")
            side_key = "buy" if order_side == "ซื้อ" else "sell"
            
            order_amt = comma_number_input("จำนวนที่ต้องการจ่าย (THB)", value=500000, min_value=0, key="sim_amount")
            
            quote_now = mid_now * (1 + cfg["dealer_spread"]) if side_key == "buy" else mid_now * (1 - cfg["dealer_spread"])
            est_coins = order_amt * (1 - LOCAL_TRADING_FEE_PCT) / quote_now

            st.markdown(f'<div style="color:#848e9c; font-size:0.8rem; margin: 8px 0 16px 0; background:#181a20; padding:10px; border-radius:4px; border:1px solid #2b3139;">ราคาประเมิน: <b style="color:#EAECEF;">{quote_now:,.2f} THB</b><br>จะได้รับ: <b style="color:#EAECEF;">≈ {est_coins:,.6f} {asset}</b></div>', unsafe_allow_html=True)

            btn_label = f"ซื้อ (Buy) {asset}" if side_key == "buy" else f"ขาย (Sell) {asset}"
            send = st.button(btn_label, type="secondary", use_container_width=True)
            
            st.divider()
            
            n_orders = st.number_input("จำนวนออเดอร์สุ่ม", value=20, min_value=1, step=10, key="sim_n")
            seed = st.number_input("Random seed", value=42, step=1, key="sim_seed", label_visibility="collapsed")
            run_batch = st.button("🎲 สุ่มออเดอร์ (Auto-Run)", type="secondary", use_container_width=True)
            reset = st.button("♻️ ล้างระบบใหม่", use_container_width=True)

        if reset:
            first_day = pd.to_datetime(data.index[0])
            st.session_state.sim = sim_defaults(asset, first_day, data.loc[first_day, "Global_USD"], data.loc[first_day, "USDTHB"], target_stock_thb)
            st.session_state.sim_signature = signature
            st.session_state.sim_steps = []
            st.rerun()

        if send:
            steps, _rec = execute_order(sim, side_key, float(order_amt), current_date_val, data.loc[current_date_val], ctx)
            st.session_state.sim_steps = steps
            valid_dates = data[data.index >= current_date_val].index
            if len(valid_dates) > 1:
                sim["current_date"] = pd.to_datetime(np.random.choice(valid_dates))
            else:
                sim["current_date"] = pd.to_datetime(data.index[-1])
            st.rerun()

        if run_batch:
            rng = np.random.default_rng(int(seed))
            mean_amt = cfg["daily_volume_thb"] / max(1, int(n_orders))
            sigma = np.sqrt(np.log(1 + cfg["flow_cv_pct"] ** 2))
            mu = np.log(max(mean_amt, 1.0)) - 0.5 * sigma ** 2
            p_buy = 0.5 + cfg["net_bias_pct"] / 2.0
            last_steps = []

            valid_dates = data[data.index >= current_date_val].index
            if len(valid_dates) > 0:
                picked = rng.choice(valid_dates, size=int(n_orders), replace=True)
                chosen_dates = pd.to_datetime(sorted(picked))
            else:
                chosen_dates = [current_date_val] * int(n_orders)

            for d in chosen_dates:
                amt = float(rng.lognormal(mu, sigma))
                s_ = "buy" if rng.random() < p_buy else "sell"
                last_steps, _rec = execute_order(sim, s_, max(amt, MIN_TRADE_THB), d, data.loc[d], ctx)

            sim["current_date"] = pd.to_datetime(chosen_dates[-1])
            st.session_state.sim_steps = last_steps
            st.rerun()

def main() -> None:
    st.set_page_config(
        page_title="XSpring Dealer Suite",
        page_icon="\u267b\ufe0f",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(THEME_CSS, unsafe_allow_html=True)

    cfg = build_sidebar()

    if not cfg["dates_ok"]:
        data, data_err = pd.DataFrame(), "ช่วงวันที่ไม่ถูกต้อง"
    else:
        data, data_err = fetch_price_data(cfg["asset"], cfg["start_date"],
                                          cfg["end_date"],
                                          use_fx_proxy=cfg["use_fx_proxy"])

    market_df = fetch_market_overview(SUPPORTED_ASSETS)

    tab1, tab2, tab3 = st.tabs([
        "📊 5-Year Backtest Simulator",
        "🧮 Liquidity & Capital Planner",
        "🛒 Exchange UI Simulator",
    ])

    with tab1:
        render_tab1(cfg, data, data_err)
    with tab2:
        render_tab2(cfg, data, data_err)
    with tab3:
        render_tab3(cfg, data, data_err, price_lookup={row["symbol"]: row["price_usd"] for _, row in market_df.iterrows()} if not market_df.empty else {}, market_df=market_df)

    st.markdown(
        f"<div class='xs-foot'>XSpring Dealer Suite · Model v{MODEL_VERSION} · "
        f"Config {CONFIG_INFO['sha256'] or 'built-in defaults'} · "
        "Planning model เพื่อการวางแผนภายในเท่านั้น "
        "ไม่ใช่เครื่องมือรับรอง compliance</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    if not HAS_UI:
        raise SystemExit("ต้องติดตั้ง UI stack ก่อน: pip install streamlit plotly yfinance")
    main()
