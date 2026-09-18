import re
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import streamlit.components.v1 as components

# =========================================================
# PAGE CONFIG & THEME
# =========================================================
st.set_page_config(page_title="XSpring Dealer Suite", page_icon="♻️", layout="wide",
                   initial_sidebar_state="expanded")

def _sv_tuple():
    try:
        nums = re.findall(r"\d+", st.__version__)
        return (int(nums[0]), int(nums[1]))
    except Exception:
        return (1, 40)

WIDE = {"width": "stretch"} if _sv_tuple() >= (1, 49) else {"use_container_width": True}

st.markdown("""
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
    
    /* --- Pipeline / Timeline View สำหรับ Tab 3 --- */
    .timeline-container {
        border-left: 2px solid #374151;
        margin-left: 12px;
        padding-left: 24px;
        margin-top: 10px;
    }
    .xs-step { 
        position: relative;
        border:1px solid #1f2937; border-radius:10px; padding:16px 20px; margin-bottom:20px;
        background:#0f1621; transition: transform 0.2s, border-color 0.2s;
    }
    .xs-step:hover { transform: translateX(4px); border-color: #4B5563; }
    .xs-step::before {
        content: ''; position: absolute; left: -31px; top: 20px; width: 14px; height: 14px;
        border-radius: 50%; background: #374151; border: 3px solid #0E1117;
    }
    .xs-step.pass { border-left: 4px solid #00D26A; }
    .xs-step.pass::before { background: #00D26A; }
    .xs-step.warn { border-left: 4px solid #F59E0B; }
    .xs-step.warn::before { background: #F59E0B; }
    .xs-step.block { border-left: 4px solid #FF4B4B; }
    .xs-step.block::before { background: #FF4B4B; box-shadow: 0 0 10px rgba(255,75,75,0.6); }
    
    .xs-step h4 { margin:0 0 6px 0; font-size:1.05rem; color:#FAFAFA; font-weight:700;
                  display:flex; justify-content:space-between; align-items:center; }
    .xs-step .xs-tag { font-size:.75rem; font-weight:700; padding:4px 12px; border-radius:999px; }
    .xs-step.pass  .xs-tag { background:rgba(0,210,106,.15);  color:#00D26A; }
    .xs-step.warn  .xs-tag { background:rgba(245,158,11,.15); color:#F59E0B; }
    .xs-step.block .xs-tag { background:rgba(255,75,75,.15);  color:#FF4B4B; }
    .xs-step p  { margin:0 0 12px 0; color:#9CA3AF; font-size:.88rem; line-height:1.5; }
    .xs-row { display:flex; justify-content:space-between; padding:5px 0;
              border-bottom:1px dotted #1f2937; font-size:.9rem; color:#D1D5DB; }
    .xs-row:last-child { border-bottom:none; }
    .xs-row b { color:#FAFAFA; font-variant-numeric:tabular-nums; }
    .xs-tot { border-top:1px solid #374151; margin-top:8px; padding-top:10px; font-weight:700; color:#00D26A; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="xs-hero">
  <h1>🏦 XSpring — Digital Asset Dealer Suite</h1>
  <p>Backtest 5 ปีย้อนหลัง + Liquidity & Capital Planner + Customer Order Simulator</p>
  <span class="xs-pill">Back-to-Back Hedging</span>
  <span class="xs-pill">FX Limit Engine</span>
  <span class="xs-pill">NCR/NC Capital Planner</span>
  <span class="xs-pill">Customer Order Journey</span>
</div>
""", unsafe_allow_html=True)

# =========================================================
# CONSTANTS
# =========================================================
GLOBAL_EXCHANGE_FEE_PRESET = {
    "Binance": 0.10, "Coinbase": 0.60, "Kraken": 0.26, "OKX": 0.10, "กำหนดเอง (Custom)": 0.10,
}
LOCAL_EXCHANGES = ["Bitkub"]
SUPPORTED_ASSETS = ["BTC", "ETH", "SOL", "DOGE", "ADA", "HBAR", "LINK", "XLM", "XRP", "USDT", "USDC"]
STABLECOINS = ["USDT", "USDC"]

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

# =========================================================
# HELPERS
# =========================================================
def fmt_num(value, force_sign=False):
    value = 0.0 if pd.isna(value) else float(value)
    sign = "- " if value < 0 else ("+ " if force_sign else "")
    v = abs(value)
    if v >= 1_000_000_000:   num = f"{v/1_000_000_000:,.2f}B"
    elif v >= 1_000_000:     num = f"{v/1_000_000:,.2f}M"
    elif v >= 1_000:         num = f"{v/1_000:,.1f}K"
    else:                    num = f"{v:,.2f}"
    return f"{sign}{num}"

def fmt_baht(value, force_sign=False):
    return f"฿ {fmt_num(value, force_sign)}"

def fmt_coin(value, symbol=""):
    v = abs(float(value))
    d = 6 if v < 1 else (4 if v < 1000 else 2)
    return f"{value:,.{d}f}" + (f" {symbol}" if symbol else "")

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
    st.text_input(label, key=key, help=help, on_change=_reformat_comma_key, args=(key,))
    cleaned = st.session_state[key].replace(",", "").replace(" ", "").strip()
    try:
        num = float(cleaned)
    except ValueError:
        num = float(value)
    if min_value is not None and num < min_value:
        num = float(min_value)
    return num

def colored_metric(label, display_value, raw_value=None, sub_text=None, font_size="1.5rem"):
    color = "#FAFAFA" if raw_value is None else ("#00D26A" if raw_value >= 0 else "#FF4B4B")
    sub = f'<div style="font-size:.78rem;color:{color};opacity:.85;margin-top:3px;">{sub_text}</div>' if sub_text else ""
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

def calc_thb_withdrawal_fee(amount_thb: float, bank_type: str, ktb_fee_thb: float = 15.0) -> float:
    if bank_type == "KTB (กรุงไทย)":
        return ktb_fee_thb
    if bank_type == "SCB":
        return 20.0
    return 20.0 if amount_thb <= 2_000_000 else 70.0

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

def step_card(number, title, status, note="", rows=None, total=None):
    tag_map = {"pass": "✅ ผ่าน", "warn": "⚠️ เฝ้าระวัง", "block": "🚨 ติดด่าน"}
    tag = tag_map.get(status, status)
    body = ""
    if rows:
        body += "".join(f"<div class='xs-row'><span>{k}</span><b>{v}</b></div>" for k, v in rows)
    if total:
        body += f"<div class='xs-row xs-tot'><span>{total[0]}</span><b>{total[1]}</b></div>"
    st.markdown(
        f"<div class='xs-step {status}'>"
        f"<h4><span>{number}. {title}</span><span class='xs-tag'>{tag}</span></h4>"
        + (f"<p>{note}</p>" if note else "")
        + (f"<div style='background: rgba(0,0,0,0.25); padding: 10px 14px; border-radius: 8px;'>{body}</div>" if body else "")
        + "</div>", unsafe_allow_html=True)

def render_tradingview(symbol: str, container_id: str, height: int = 500, interval: str = "D", studies=None):
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
            "mainSeriesProperties.candleStyle.upColor": "#00D26A",
            "mainSeriesProperties.candleStyle.downColor": "#FF4B4B",
          }}
        }});
      }})();
    </script>""", height=height + 8)

@st.cache_data(show_spinner=False)
def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv().encode("utf-8-sig")

# =========================================================
# DATA LAYER
# =========================================================
def _normalize_index(d: pd.DataFrame) -> pd.DataFrame:
    idx = pd.to_datetime(d.index)
    try:
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_convert(None)
    except (TypeError, AttributeError):
        pass
    d.index = idx.normalize()
    return d

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

def apply_fx_limit(hedge_usd: pd.Series, index: pd.DatetimeIndex, fx_limit: float):
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

# =========================================================
# RISK ENGINE
# =========================================================
def _risk_stats(r: pd.Series) -> dict | None:
    r = r.replace([np.inf, -np.inf], np.nan).dropna()
    if len(r) < 30: return None
    q01, q05 = np.percentile(r, 1), np.percentile(r, 5)
    tail = r[r <= q01]
    return {
        "returns": r, "sigma_d": float(r.std()), "ann_vol": float(r.std() * np.sqrt(365)),
        "var95": float(max(-q05, 0)), "var99": float(max(-q01, 0)),
        "es99": float(max(-tail.mean(), 0)) if len(tail) else float(max(-q01, 0)),
        "worst": float(max(-r.min(), 0)), "worst_date": r.idxmin(),
    }

def risk_profile(px: pd.Series) -> dict | None:
    r = np.log(px / px.shift(1))
    return _risk_stats(r)

def safety_stock_factor(net_bias: float, flow_cv: float, lag_days: int, z_alpha: float) -> float:
    return (max(0.0, net_bias) * lag_days + z_alpha * flow_cv * np.sqrt(lag_days)) / 30.0

def crypto_haircut(es99: float, lag_days: int) -> float:
    return float(min(es99 * np.sqrt(lag_days), 0.95))

def blended_custody_rate(hot_pct: float, cold_domestic_pct: float, cold_foreign_rate: float) -> float:
    return (hot_pct * HOT_WALLET_NC_RATE
            + (1 - hot_pct) * (cold_domestic_pct * COLD_DOMESTIC_NC_RATE
                               + (1 - cold_domestic_pct) * cold_foreign_rate))

def nc_snapshot(stock_thb: float, total_capital: float, cex_margin: float, liab: float,
                h_crypto: float, h_cex: float, fixed_min_nc: float,
                trading_risk_rate: float, daily_volume_thb: float,
                custody_rate: float) -> dict:
    cash = total_capital - stock_thb
    actual = cash + stock_thb * (1 - h_crypto) + cex_margin * (1 - h_cex) - liab
    trading_nc = trading_risk_rate * daily_volume_thb
    custody_nc = stock_thb * custody_rate
    required = fixed_min_nc + trading_nc + custody_nc
    return {"cash": cash, "actual": actual, "required": required, "buffer": actual - required,
            "trading_nc": trading_nc, "custody_nc": custody_nc}

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.markdown("### ⚙️ Backtest Settings")
    
    asset = st.selectbox("เลือกเหรียญ", SUPPORTED_ASSETS, key="bt_asset")
    if asset in STABLECOINS:
        st.warning(f"⚠️ {asset} เป็น Stablecoin — ใช้กลยุทธ์ Depeg Arbitrage + Carry Yield")

    with st.expander("🌐 กระดานซื้อขาย", expanded=True):
        global_exchange = st.selectbox("กระดานโลกที่ใช้ Hedge", list(GLOBAL_EXCHANGE_FEE_PRESET.keys()), key="bt_global_exchange")
        local_exchange = st.selectbox("กระดานไทยอ้างอิงราคาลูกค้า", LOCAL_EXCHANGES, key="bt_local_exchange")
        
    with st.expander("📅 ช่วงเวลา Backtest", expanded=True):
        today = pd.Timestamp.now().date()
        preset_days = {"1 เดือน": 30, "3 เดือน": 90, "6 เดือน": 180, "1 ปี": 365, "3 ปี": 365*3, "5 ปี": 365*5}
        preset = st.radio("เลือกช่วงเวลาด่วน", ["กำหนดเอง", "1 เดือน", "3 เดือน", "6 เดือน", "1 ปี", "3 ปี", "5 ปี"], index=6, horizontal=True)

        if preset != "กำหนดเอง":
            preset_start, preset_end = today - pd.Timedelta(days=preset_days[preset]), today
        else:
            preset_start, preset_end = today - pd.Timedelta(days=365*5), today

        ca, cb = st.columns(2)
        with ca:
            start_date = st.date_input("เริ่มต้น", value=preset_start, min_value=pd.Timestamp("2015-01-01").date(), max_value=today, disabled=(preset != "กำหนดเอง"))
        with cb:
            end_date = st.date_input("สิ้นสุด", value=preset_end, min_value=pd.Timestamp("2015-01-01").date(), max_value=today, disabled=(preset != "กำหนดเอง"))
        if preset != "กำหนดเอง":
            start_date, end_date = preset_start, preset_end

    dates_ok = start_date < end_date

    with st.expander("💰 พารามิเตอร์ Dealer", expanded=True):
        trade_vol = comma_number_input("ปริมาณซื้อขายลูกค้า/วัน (USD eq.)", value=100000, key="bt_trade_vol")
        dealer_spread = st.number_input("Dealer Spread ที่เก็บจากลูกค้า (%)", value=0.5, step=0.1, key="bt_spread") / 100
        
        if "bt_prev_gx" not in st.session_state: st.session_state.bt_prev_gx = global_exchange
        if "bt_hedge_fee" not in st.session_state: st.session_state.bt_hedge_fee = GLOBAL_EXCHANGE_FEE_PRESET[global_exchange]
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
        ktb_fx_spread_bps = st.number_input("ส่วนต่างเรทที่ดีกว่าตลาด (bps)", value=15.0, step=1.0, min_value=0.0) if use_ktb_fx else 0.0
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
        reg_type = st.radio("ประเภทใบอนุญาต", ["ผู้ประกอบธุรกิจสินทรัพย์ดิจิทัลเฉพาะ (เกณฑ์ NC)", "บล. / บธ. (เกณฑ์ NCR)"], horizontal=True)
        is_ncr_mode = "บล." in reg_type
        if is_ncr_mode:
            ncr_min = st.number_input("เกณฑ์ NCR ขั้นต่ำ (%)", value=7.0, step=0.5, min_value=0.1)
            ncr_warn = st.number_input("เกณฑ์เตือนภัย NCR (%)", value=10.5, step=0.5, min_value=ncr_min)
        else:
            ncr_min, ncr_warn = 7.0, 10.5
            
        is_custodian = st.checkbox("เก็บรักษาทรัพย์สินลูกค้า", value=True)
        fixed_min_nc = 25_000_000.0 if is_custodian else 5_000_000.0
        trading_risk_rate = st.number_input("อัตรา NC ความเสี่ยงซื้อขาย (%)", value=2.0, step=0.1, min_value=0.0) / 100
        cold_foreign_rate = st.number_input("อัตรา NC cold wallet ต่างประเทศ (%)", value=2.0, step=0.5, min_value=1.0) / 100
        hot_wallet_pct = st.slider("สัดส่วนสต็อกใน Hot Wallet (%)", 0, 100, 50) / 100
        cold_domestic_split_pct = st.slider("สัดส่วน Cold Wallet ฝากในประเทศ (%)", 0, 100, 100) / 100

daily_volume_thb = monthly_volume_thb / 30.0
custody_rate_blended = blended_custody_rate(hot_wallet_pct, cold_domestic_split_pct, cold_foreign_rate)
hot_wallet_cap_breach = (liab_thb < HOT_WALLET_CAP_LIAB_THRESHOLD) and (hot_wallet_pct > HOT_WALLET_CAP)

data, data_err = (pd.DataFrame(), "ช่วงวันที่ไม่ถูกต้อง") if not dates_ok else fetch_price_data(asset, start_date, end_date)

tab1, tab2, tab3 = st.tabs(["📊 5-Year Backtest Simulator", "🧮 Liquidity & Capital Planner", "🛒 Customer Order Simulator"])

# ---------------------------------------------------------
# TAB 1 — BACKTEST
# ---------------------------------------------------------
with tab1:
    if data.empty:
        st.error(f"⚠️ {data_err or 'ไม่สามารถโหลดข้อมูลได้'}")
    else:
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
            bt["Depeg_Deviation"] = 0.0; bt["Depeg_PnL_THB"] = 0.0; bt["Carry_Yield_THB"] = 0.0
            bt["Slippage_Cost_THB"] = trade_vol * bt["Volatility_Pct"] * slippage_sensitivity * bt["USDTHB"]

        bt["Trading_Fee_Revenue_THB"] = bt["Gross_Notional_THB"] * LOCAL_TRADING_FEE_PCT if include_trading_fee_revenue else 0.0
        wd_network_cost = WITHDRAWAL_FEE_TABLE.get(asset, 0.0) * bt["Global_USD"] * bt["USDTHB"] * settlements_per_day
        bt["Withdrawal_Fee_Markup_Revenue_THB"] = wd_network_cost * withdrawal_fee_markup_pct
        bt["THB_WD_Fee"] = bt["USDTHB"].map(lambda fx: calc_thb_withdrawal_fee(trade_vol * fx, bank_type, ktb_wd_fee_thb))
        bt["THB_Fee_Markup_Revenue_THB"] = bt["THB_WD_Fee"] * settlements_per_day * withdrawal_fee_markup_pct
        bt["Fee_Revenue_THB"] = bt["Trading_Fee_Revenue_THB"] + bt["Withdrawal_Fee_Markup_Revenue_THB"] + bt["THB_Fee_Markup_Revenue_THB"]
        bt["Revenue_THB"] = bt["Spread_Revenue_THB"] + bt["FX_Basis_PnL_THB"] + bt["Fee_Revenue_THB"] + bt["Depeg_PnL_THB"] + bt["Carry_Yield_THB"] + bt["KTB_FX_Benefit_THB"]
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
        
        section(f"📉 ราคาเรียลไทม์ — {asset}")
        tv_mode = st.radio("มุมมองกราฟ", ["กระดานไทย (Bitkub)", "กระดานโลก (Binance)", "เทียบ 2 กระดาน"], horizontal=True, key="tv_mode_bt")
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

        section("📈 Performance Summary")
        r1 = st.columns(4)
        metric_card(r1[0], "Net P&L (THB)", fmt_baht(net_pnl_thb, True), net_pnl_thb, f"{margin_bps:,.1f} bps ของ notional", "1.7rem")
        metric_card(r1[1], "Total Revenue", fmt_baht(total_revenue_thb), total_revenue_thb, "Spread + Fee + Basis + Carry")
        metric_card(r1[2], "Total Cost", fmt_baht(total_cost_thb), -abs(total_cost_thb), "Hedge Fee + Slippage")
        metric_card(r1[3], "Avg Daily P&L", fmt_baht(avg_daily_pnl, True), avg_daily_pnl, f"เฉลี่ยจาก {traded_days} วันที่เทรดได้")

        r2 = st.columns(4)
        metric_card(r2[0], "Best Day", fmt_baht(best_day, True), best_day)
        metric_card(r2[1], "Worst Day", fmt_baht(worst_day, True), worst_day)
        metric_card(r2[2], "Max Drawdown", fmt_baht(max_drawdown), max_drawdown if max_drawdown != 0 else -0.01, f"{dd_pct:.2f}% จาก peak")
        metric_card(r2[3], "Win Rate", f"{win_rate:.1f}%", None, f"{win_days}/{traded_days} วัน")

        r3 = st.columns(4)
        metric_card(r3[0], "Gross Notional หมุนเวียน", fmt_baht(total_notional), None, "มูลค่าธุรกรรมรวม (ไม่ใช่กำไร)")
        metric_card(r3[1], "FX Limit Hit", f"{limit_hit_days} วัน", -1 if limit_hit_days else 0, f"{(limit_hit_days/total_days*100) if total_days else 0:.1f}% ของช่วงเวลา")
        if asset in STABLECOINS:
            metric_card(r3[2], "Avg Depeg Deviation", f"{bt['Depeg_Deviation'].mean()*100:+.3f}%")
            metric_card(r3[3], "Total Carry Yield", fmt_baht(traded["Carry_Yield_THB"].sum()), traded["Carry_Yield_THB"].sum())
        else:
            metric_card(r3[2], "Avg Daily Volatility", f"{bt['Volatility_Pct'].mean()*100:.2f}%")
            metric_card(r3[3], "Total Slippage Cost", fmt_baht(traded["Slippage_Cost_THB"].sum()), -abs(traded["Slippage_Cost_THB"].sum()))

        section("💧 Revenue & Cost Waterfall")
        wf_labels = ["Spread Revenue", "FX Basis P&L", "Fee Revenue"]
        wf_values = [traded["Spread_Revenue_THB"].sum(), traded["FX_Basis_PnL_THB"].sum(), traded["Fee_Revenue_THB"].sum()]
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
            increasing={"marker": {"color": "#00D26A"}}, decreasing={"marker": {"color": "#FF4B4B"}}, totals={"marker": {"color": "#3B82F6"}},
        ))
        fig_wf.update_layout(template="plotly_dark", height=440, showlegend=False, margin=dict(t=40, b=20), yaxis_title="THB")
        st.plotly_chart(fig_wf, **WIDE)

        section("📊 Cumulative P&L")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=bt.index, y=bt["Actual_Cum_PnL"], name="Cumulative P&L", line=dict(color="#00D26A", width=2.2), fill="tozeroy", fillcolor="rgba(0,210,106,0.12)"))
        fig.add_trace(go.Scatter(x=bt.index, y=running_max, name="Peak Equity", line=dict(color="#6B7280", width=1, dash="dot")))
        hits = bt[bt["FX_Limit_Hit"] == 1]
        if not hits.empty:
            fig.add_trace(go.Scatter(x=hits.index, y=hits["Actual_Cum_PnL"], mode="markers", name="FX Limit Hit", marker=dict(color="#FF4B4B", size=5, symbol="x")))
        fig.update_layout(title=f"{asset} @ {global_exchange} · {start_date} → {end_date}", template="plotly_dark", hovermode="x unified", height=480, margin=dict(t=50, b=20), yaxis_title="THB", legend=dict(orientation="h", y=1.02, yanchor="bottom"))
        st.plotly_chart(fig, **WIDE)

        with st.expander("📅 P&L รายเดือน"):
            m = bt.groupby([bt.index.year, bt.index.month])["Actual_Daily_PnL"].sum().unstack(fill_value=0)
            m.columns = [f"{c:02d}" for c in m.columns]
            fig_hm = go.Figure(go.Heatmap(z=m.values, x=list(m.columns), y=[str(i) for i in m.index], colorscale=[[0, "#FF4B4B"], [0.5, "#111827"], [1, "#00D26A"]], zmid=0, texttemplate="%{z:,.0f}", textfont={"size": 9}))
            fig_hm.update_layout(template="plotly_dark", height=60 * len(m) + 120, margin=dict(t=20, b=20), xaxis_title="เดือน", yaxis_title="ปี")
            st.plotly_chart(fig_hm, **WIDE)

        with st.expander("🔍 Daily Ledger (100 วันล่าสุด)"):
            cols = ["Global_USD", "Local_THB", "USDTHB", "Volatility_Pct", "Gross_Notional_THB", "Spread_Revenue_THB", "FX_Basis_PnL_THB", "Hedge_Fee_Cost_THB", "Slippage_Cost_THB", "Fee_Revenue_THB"]
            if asset in STABLECOINS: cols += ["Depeg_Deviation", "Depeg_PnL_THB", "Carry_Yield_THB"]
            cols += ["Actual_Daily_PnL", "Current_FX_Usage", "FX_Limit_Hit"]
            ledger = bt[cols]
            st.dataframe(ledger.sort_index(ascending=False).head(100), height=400, **WIDE)

# ---------------------------------------------------------
# TAB 2 — LIQUIDITY & CAPITAL PLANNER (อัปเดต ก.ล.ต. พ.ย. 67)
# ---------------------------------------------------------
with tab2:
    st.markdown("""
ตอบคำถามที่ผู้บริหารถามจริง:
> **"ถ้าธุรกรรมเดือนละ X ล้าน ต้องดำรงเหรียญเท่าไหร่ เงินสดเท่าไหร่ NC เหลือเท่าไหร่ ผ่านเกณฑ์ไหม และทุนที่มีรับได้สูงสุดกี่ล้าน"**
    """)
    if not dates_ok: st.error("❌ ช่วงวันที่ในแถบซ้ายไม่ถูกต้อง")
    else:
        section("🎛️ โหมดคำนวณความเสี่ยง")
        cp_mode = st.radio("เลือกโหมด", ["Single-Asset (ใช้เหรียญที่เลือกในแถบซ้าย)", "Multi-Asset Portfolio"], horizontal=True, key="cp_mode")
        rp = None
        risk_label = ""

        if cp_mode.startswith("Single"):
            if data.empty: st.error(f"⚠️ โหลดข้อมูลไม่สำเร็จ: {data_err}")
            else:
                rp = risk_profile(data["Global_USD"])
                risk_label = asset
        else:
            ma_c1, ma_c2 = st.columns([2, 1])
            with ma_c1: selected_assets = st.multiselect("เลือกเหรียญในพอร์ต", SUPPORTED_ASSETS, default=["BTC", "ETH", "USDT"], key="cp_ma_assets")
            if not selected_assets: st.info("เลือกอย่างน้อย 1 เหรียญ")
            else:
                wcols = st.columns(min(len(selected_assets), 6))
                default_w = round(100 / len(selected_assets))
                weights = {a_: st.number_input(f"{a_} (%)", value=default_w, min_value=0, max_value=100, step=5, key=f"cp_w_{a_}") for a_ in selected_assets}
                wsum = sum(weights.values())
                if wsum > 0:
                    norm_w = {k: v / wsum for k, v in weights.items()}
                    with st.spinner("กำลังโหลดราคาย้อนหลัง…"):
                        ret_map = {}
                        for a_ in selected_assets:
                            d_, _ = fetch_price_data(a_, start_date, end_date)
                            if not d_.empty: ret_map[a_] = np.log(d_["Global_USD"] / d_["Global_USD"].shift(1))
                    if ret_map:
                        ret_df = pd.concat(ret_map, axis=1).dropna()
                        if len(ret_df) >= 30:
                            port_w = np.array([norm_w.get(c, 0) for c in ret_df.columns])
                            rp = _risk_stats((ret_df * port_w).sum(axis=1))
                            risk_label = " + ".join(f"{k} {norm_w[k]*100:.0f}%" for k in ret_df.columns)

        if rp is not None:
            usdthb_now = float(data["USDTHB"].iloc[-1]) if not data.empty else 35.5
            spot_usd = float(data["Global_USD"].iloc[-1]) if (not data.empty and cp_mode.startswith("Single")) else None

            section(f"📐 โปรไฟล์ความเสี่ยงจากข้อมูลจริง — {risk_label}")
            rk = st.columns(4)
            metric_card(rk[0], "Ann. Volatility", f"{rp['ann_vol']*100:.1f}%")
            metric_card(rk[1], "VaR 99% (1 วัน)", f"{rp['var99']*100:.2f}%")
            metric_card(rk[2], "Expected Shortfall 99%", f"{rp['es99']*100:.2f}%")
            metric_card(rk[3], "Worst Single Day", f"-{rp['worst']*100:.1f}%")
            st.caption("พารามิเตอร์ Flow / งบดุล ย้ายไปปรับในแถบซ้ายได้เลยครับ เพื่อให้ใช้ค่าร่วมกับหน้า Order Simulator")

            h_crypto = crypto_haircut(rp["es99"], settlement_days)
            h_cex = cex_counterparty_haircut if cex_margin_asset.startswith("Stablecoin") else h_crypto
            a_factor = safety_stock_factor(net_bias_pct, flow_cv_pct, settlement_days, z_alpha)
            required_stock_thb = a_factor * monthly_volume_thb

            nc = nc_snapshot(required_stock_thb, total_capital_thb, cex_margin_thb, liab_thb, h_crypto, h_cex, fixed_min_nc, trading_risk_rate, daily_volume_thb, custody_rate_blended)
            cash_after_stock_thb, nlc_thb = nc["cash"], nc["actual"]
            required_nc_total, nc_buffer_thb = nc["required"], nc["buffer"]
            ncr_pct = (nlc_thb / required_nc_total * 100.0) if required_nc_total > 0 else float("nan")

            slope = a_factor * (h_crypto + custody_rate_blended) + trading_risk_rate / 30.0
            if slope > 0:
                rhs = (total_capital_thb + cex_margin_thb * (1 - h_cex) - liab_thb - fixed_min_nc)
                v_nc_thb = max(0.0, rhs / slope)
            else: v_nc_thb = float("inf")
            v_cash_thb = (total_capital_thb / a_factor) if a_factor > 0 else float("inf")
            capital_max_v_thb = min(v_nc_thb, v_cash_thb)
            fx_max_v_thb = fx_limit_max * usdthb_now
            overall_max_v_thb = min(capital_max_v_thb, fx_max_v_thb)
            binding_side = "ทุน / NC" if capital_max_v_thb < fx_max_v_thb else "FX Limit"
            coin_price_thb = (spot_usd * usdthb_now) if spot_usd else None

            section("🧾 สรุปผลสำหรับผู้บริหาร (เกณฑ์ ก.ล.ต. ล่าสุด)")
            ok_nc = (not pd.isna(nc_buffer_thb)) and (nc_buffer_thb >= 0)
            if is_ncr_mode:
                ncr_value_pct = (nlc_thb / liab_thb * 100) if liab_thb > 0 else 0
                ok_ncr = ok_nc and ncr_value_pct >= ncr_min
                verdict_box(ok_ncr, f"NCR {ncr_value_pct:.2f}% | NC จริง {fmt_baht(nlc_thb)} (ต้องดำรงขั้นต่ำ {fmt_baht(required_nc_total)})",
                            f"ต้องดองเหรียญ {fmt_baht(required_stock_thb)} เหลือเงินสด {fmt_baht(cash_after_stock_thb)}", warn=(ncr_value_pct < ncr_warn))
            else:
                verdict_box(ok_nc, f"NC จริง {fmt_baht(nlc_thb)} (ต้องดำรงขั้นต่ำ {fmt_baht(required_nc_total)})",
                            f"ที่ธุรกรรม {fmt_baht(monthly_volume_thb)}/เดือน ต้องดองเหรียญ {fmt_baht(required_stock_thb)} เหลือเงินสด {fmt_baht(cash_after_stock_thb)}", warn=(nc_buffer_thb < 0.5*required_nc_total))
            if hot_wallet_cap_breach: verdict_box(False, "ฝ่าฝืนเพดาน Hot Wallet 50%", "หนี้สินลูกค้าต่ำกว่า 1,000 ลบ. ห้ามเก็บ Hot Wallet เกิน 50%")
            
            cap_ok = monthly_volume_thb <= overall_max_v_thb
            verdict_box(cap_ok, f"เพดานธุรกรรมสูงสุด ≈ {fmt_baht(overall_max_v_thb)}/เดือน (ติดที่: {binding_side})",
                        f"ทุนรองรับได้ {fmt_baht(capital_max_v_thb)}/เดือน · FX Limit รองรับได้ {fmt_baht(fx_max_v_thb)}/เดือน")

            section("📊 รายละเอียดตัวเลข")
            k1 = st.columns(4)
            metric_card(k1[0], "Required Safety Stock", fmt_baht(required_stock_thb), None, f"Haircut ที่ใช้ {h_crypto*100:.2f}%")
            metric_card(k1[1], "เงินสดคงเหลือ", fmt_baht(cash_after_stock_thb), cash_after_stock_thb)
            metric_card(k1[2], "Net Capital (NC) จริง", fmt_baht(nlc_thb), nlc_thb)
            metric_card(k1[3], "NC ขั้นต่ำที่ต้องดำรง", fmt_baht(required_nc_total), nc_buffer_thb, f"ส่วนเกิน {fmt_baht(nc_buffer_thb, force_sign=True)}")

# ---------------------------------------------------------
# TAB 3 — CUSTOMER ORDER SIMULATOR (UI ใหม่)
# ---------------------------------------------------------
def _sim_defaults(asset_name, spot_usd, usdthb, target_stock_thb):
    coin_price = spot_usd * usdthb
    return {
        "asset": asset_name,
        "inv_coins": (target_stock_thb / coin_price) if coin_price > 0 else 0.0,
        "target_thb": target_stock_thb,
        "fx_used_usd": 0.0,
        "pnl_thb": 0.0,
        "unhedged_thb": 0.0,
        "orders": [],
    }

def execute_order(sim, side, amount_thb, ctx):
    p = ctx
    spot, fx = p["spot_usd"], p["usdthb"]
    coin_price_global = spot * fx
    mid = coin_price_global * (1 + p["local_premium"])
    quote = mid * (1 + p["spread"]) if side == "buy" else mid * (1 - p["spread"])
    steps = []

    if amount_thb < MIN_TRADE_THB:
        steps.append(dict(n=1, t="คำสั่งถูกปฏิเสธ", s="block", note=f"มูลค่าต่ำกว่าขั้นต่ำ {MIN_TRADE_THB:,.0f} บาท"))
        return steps, None

    steps.append(dict(n=1, t="ตั้งราคาให้ลูกค้า", s="pass", note="ราคาอ้างอิงจาก Global CEX + ต้นทุนส่วนเพิ่ม",
                      rows=[("ราคาโลก (USD)", f"$ {spot:,.2f}"), ("× เรท USD/THB", f"{fx:,.2f}"),
                            (f"+ Local Premium {p['local_premium']*100:.2f}%", f"฿ {mid:,.2f}"),
                            (f"{'+' if side=='buy' else '−'} Spread {p['spread']*100:.2f}%", f"฿ {quote:,.2f}")],
                      total=("ราคาที่ลูกค้าได้", f"฿ {quote:,.2f}")))

    trading_fee = amount_thb * LOCAL_TRADING_FEE_PCT
    net_thb = amount_thb - trading_fee
    coins = net_thb / quote
    steps.append(dict(n=2, t="จับคู่และส่งมอบเข้ากระเป๋า", s="pass",
                      note=("หักค่าธรรมเนียมฝั่งไทยแล้วโอนเหรียญเข้ากระเป๋าลูกค้าทันที" if side == "buy" else "รับเหรียญจากลูกค้า จ่ายเงินบาทออก"),
                      rows=[("มูลค่าที่ลูกค้าใส่", fmt_baht(amount_thb)), (f"หักค่าธรรมเนียม {LOCAL_TRADING_FEE_PCT*100:.2f}%", "− " + fmt_baht(trading_fee))],
                      total=("เหรียญที่ลูกค้าได้" if side == "buy" else "เหรียญที่ลูกค้าส่งมอบ", fmt_coin(coins, sim["asset"]))))

    inv_before = sim["inv_coins"]
    sim["inv_coins"] += (-coins if side == "buy" else coins)
    target_coins = sim["target_thb"] / coin_price_global if coin_price_global > 0 else 0.0
    short_coins = max(0.0, target_coins - sim["inv_coins"])
    excess_coins = max(0.0, sim["inv_coins"] - target_coins)
    
    steps.append(dict(n=3, t="ตัดของจากสต็อกสำรอง" if side == "buy" else "รับของเข้าสต็อก",
                      s="block" if sim["inv_coins"] < 0 else ("warn" if short_coins > 0 else "pass"),
                      note=("ดึงของจาก Inventory โดยตรง ลูกค้าไม่ต้องรอ" if side == "buy" else "ของเข้ามาเติมในสต็อก"),
                      rows=[("สต็อกก่อนหน้า", fmt_coin(inv_before)), ("การเปลี่ยนแปลง", ("− " if side == "buy" else "+ ") + fmt_coin(coins)),
                            ("สต็อกปัจจุบัน", fmt_coin(sim["inv_coins"]))],
                      total=("เป้าหมายสต็อก (Target)", f"{fmt_coin(target_coins)}")))

    hedge_coins = short_coins if side == "buy" else excess_coins
    hedge_thb = hedge_coins * coin_price_global
    hedge_usd = hedge_coins * spot * (1 + p["hedge_fee"])
    hedged, gate = hedge_coins > 0, "ผ่าน"

    if side == "buy" and hedge_coins > 0:
        if sim["fx_used_usd"] + hedge_usd > p["fx_limit"]:
            hedged, gate = False, "FX Limit เต็ม"
            fx_step = dict(n=5, t="ด่าน FX Limit (เพดานโอนเงินออก)", s="block",
                           note="โควตาเต็ม ไม่สามารถโอนเงินไป Hedge ได้ ระบบต้องแบกรับความเสี่ยงราคา",
                           rows=[("โควตาที่ใช้ไป", f"$ {sim['fx_used_usd']:,.0f}"), ("ออเดอร์นี้ต้องการใช้", f"$ {hedge_usd:,.0f}")],
                           total=("ส่วนที่เกินเพดาน", f"$ {sim['fx_used_usd']+hedge_usd-p['fx_limit']:,.0f}"))
        else:
            sim["fx_used_usd"] += hedge_usd
            fx_step = dict(n=5, t="ด่าน FX Limit (เพดานโอนเงินออก)", s="pass",
                           note="แปลงบาทเป็นดอลลาร์เพื่อส่งออกไปซื้อคืนบนกระดานโลก",
                           rows=[("ออเดอร์นี้ใช้โควตา", f"$ {hedge_usd:,.0f}"), ("ใช้ไปแล้วรวม", f"$ {sim['fx_used_usd']:,.0f}")],
                           total=("โควตาคงเหลือ", f"$ {p['fx_limit']-sim['fx_used_usd']:,.0f}"))
    else:
        fx_step = dict(n=5, t="ด่าน FX Limit", s="pass", note="ฝั่งขายไม่กินโควตาโอนออก", 
                       total=("โควตาคงเหลือ", f"$ {p['fx_limit']-sim['fx_used_usd']:,.0f}"))

    if hedged: sim["inv_coins"] += (hedge_coins if side == "buy" else -hedge_coins)
    elif hedge_coins > 0 and side == "buy": sim["unhedged_thb"] += hedge_thb

    steps.append(dict(n=4, t="ระบบตัดสินใจ Hedge อัตโนมัติ", s="pass" if (hedge_coins == 0 or hedged) else "block",
                      note="สต็อกพร่องจึงส่งคำสั่งซื้อคืนบน Global CEX" if side == "buy" else "สต็อกล้นจึงขายทิ้ง",
                      rows=[("ปริมาณที่ส่งคำสั่ง", fmt_coin(hedge_coins, sim["asset"])), ("คิดเป็นมูลค่า", f"{fmt_baht(hedge_thb)}")],
                      total=("สถานะ", "ไม่ต้องส่ง" if hedge_coins == 0 else ("ส่งสำเร็จ" if hedged else "ถูกบล็อกที่ FX Limit"))))
    steps.append(fx_step)

    spread_rev, premium_rev = coins * mid * p["spread"], coins * coin_price_global * p["local_premium"]
    wd_markup_rev = (p["wd_fee_per_coin"] * coin_price_global + calc_thb_withdrawal_fee(amount_thb, p["bank_type"], p["ktb_wd_fee"])) * p["wd_markup"]
    ktb_fx_benefit = hedge_thb * (p["ktb_fx_bps"] / 10000.0) if hedged else 0.0
    hedge_fee_cost, slippage_cost = (hedge_thb * p["hedge_fee"] if hedged else 0.0), (hedge_thb * p["daily_vol"] * p["slip_sens"] if hedged else 0.0)
    net = spread_rev + premium_rev + (trading_fee if p["include_fee_rev"] else 0.0) + wd_markup_rev + ktb_fx_benefit - hedge_fee_cost - slippage_cost
    sim["pnl_thb"] += net

    stock_thb = max(0.0, sim["inv_coins"]) * coin_price_global
    nc = nc_snapshot(stock_thb, p["capital"], p["cex_margin"], p["liab"], p["h_crypto"], p["h_cex"], p["fixed_min_nc"], p["trading_risk_rate"], p["daily_volume_thb"], p["custody_rate"])
    
    nc_status = "block" if nc["buffer"] < 0 else ("warn" if nc["buffer"] < 0.5 * nc["required"] or p["hot_breach"] else "pass")
    steps.append(dict(n=6, t="ด่านตรวจสอบเงินกองทุน (ก.ล.ต.)", s=nc_status,
                      note="ผ่านเกณฑ์เงินกองทุน" if nc_status == "pass" else "เงินกองทุนไม่เพียงพอหรือละเมิดเกณฑ์ Hot Wallet",
                      rows=[("NC ที่มีจริง", fmt_baht(nc["actual"])), ("NC ที่ต้องดำรงขั้นต่ำ", fmt_baht(nc["required"]))],
                      total=("ส่วนเกิน (Buffer)", fmt_baht(nc["buffer"], force_sign=True))))

    steps.append(dict(n=7, t="สรุปกำไร/ขาดทุน (P&L)", s="pass" if net >= 0 else "block",
                      note="รายได้หักลบกับต้นทุน Hedge ของบริษัท",
                      rows=[("Dealer Spread & Premium", "+ " + fmt_baht(spread_rev + premium_rev)),
                            ("ค่าธรรมเนียมบนกระดานโลก", "− " + fmt_baht(hedge_fee_cost)),
                            ("ค่าเสียโอกาส (Slippage)", "− " + fmt_baht(slippage_cost))],
                      total=("กำไรสุทธิ", f"{fmt_baht(net, force_sign=True)} ({net/amount_thb*10000:,.1f} bps)")))

    sim["orders"].append({
        "ฝั่ง": "ซื้อ" if side == "buy" else "ขาย", "เหรียญ": sim["asset"], "มูลค่า (บาท)": amount_thb, "ราคาที่ลูกค้าได้": quote,
        "เหรียญที่ส่งมอบ": coins, "Hedge (USD)": hedge_usd if hedged else 0.0, "รายได้": net + hedge_fee_cost + slippage_cost,
        "ต้นทุน": hedge_fee_cost + slippage_cost, "กำไรออเดอร์": net, "สต็อกคงเหลือ": sim["inv_coins"],
        "FX ใช้สะสม (USD)": sim["fx_used_usd"], "NC Buffer": nc["buffer"], "ผลด่าน": gate,
    })
    return steps, None

with tab3:
    st.markdown("""
### 🛒 Customer Order Journey
จำลองสถานการณ์จริง: **"เมื่อลูกค้าส่งคำสั่งซื้อ/ขาย ระบบหลังบ้านต้องวิ่งผ่านด่านอะไรบ้าง?"**
ทดลองใส่ออเดอร์ด้านซ้าย แล้วดูเส้นทางการทำงานของระบบ (ตั้งราคา → ตัดสต็อก → สั่ง Hedge → ตรวจ FX Limit → ตรวจเงินกองทุน ก.ล.ต. → สรุปกำไร) 

*💡 สถานะสต็อก โควตา FX และกำไร จะถูกสะสมต่อเนื่องไปเรื่อยๆ เพื่อทดสอบว่าถ้ารับลูกค้าเยอะๆ ด่านไหนจะแตกก่อนกัน*
    """)

    if data.empty:
        st.error("⚠️ ต้องโหลดราคาจริงก่อนถึงจะจำลองได้")
    else:
        rp_sim = risk_profile(data["Global_USD"])
        if rp_sim is None:
            st.error("ข้อมูลย้อนหลังน้อยกว่า 30 วัน — เลือกช่วงเวลายาวขึ้นในแถบซ้าย")
        else:
            spot_usd_now = float(data["Global_USD"].iloc[-1])
            usdthb_now_sim = float(data["USDTHB"].iloc[-1])
            daily_vol_now = float(data["Volatility_Pct"].tail(30).mean())
            h_crypto_sim = crypto_haircut(rp_sim["es99"], settlement_days)
            h_cex_sim = cex_counterparty_haircut if cex_margin_asset.startswith("Stablecoin") else h_crypto_sim
            a_factor_sim = safety_stock_factor(net_bias_pct, flow_cv_pct, settlement_days, z_alpha)
            target_stock_thb = a_factor_sim * monthly_volume_thb

            ctx = dict(spot_usd=spot_usd_now, usdthb=usdthb_now_sim, local_premium=local_premium, spread=dealer_spread, hedge_fee=hedge_fee,
                       fx_limit=fx_limit_max, daily_vol=daily_vol_now, slip_sens=slippage_sensitivity, include_fee_rev=include_trading_fee_revenue, 
                       wd_markup=withdrawal_fee_markup_pct, wd_fee_per_coin=WITHDRAWAL_FEE_TABLE.get(asset, 0.0), bank_type=bank_type,
                       ktb_wd_fee=ktb_wd_fee_thb, ktb_fx_bps=(ktb_fx_spread_bps if use_ktb_fx else 0.0), capital=total_capital_thb, 
                       cex_margin=cex_margin_thb, liab=liab_thb, h_crypto=h_crypto_sim, h_cex=h_cex_sim, fixed_min_nc=fixed_min_nc,
                       trading_risk_rate=trading_risk_rate, daily_volume_thb=daily_volume_thb, custody_rate=custody_rate_blended, hot_breach=hot_wallet_cap_breach)

            need_reset = ("sim" not in st.session_state or st.session_state.sim["asset"] != asset or st.session_state.get("sim_target_key") != round(target_stock_thb, 2))
            if need_reset:
                st.session_state.sim = _sim_defaults(asset, spot_usd_now, usdthb_now_sim, target_stock_thb)
                st.session_state.sim_target_key = round(target_stock_thb, 2)
                st.session_state.sim_steps = []
            sim = st.session_state.sim
            sim["target_thb"] = target_stock_thb

            coin_price_thb_now = spot_usd_now * usdthb_now_sim
            stock_thb_now = max(0.0, sim["inv_coins"]) * coin_price_thb_now
            nc_now = nc_snapshot(stock_thb_now, total_capital_thb, cex_margin_thb, liab_thb, h_crypto_sim, h_cex_sim, fixed_min_nc, trading_risk_rate, daily_volume_thb, custody_rate_blended)

            # ==========================================
            # แผงควบคุมสถานะ (Dashboard)
            # ==========================================
            st.divider()
            st.markdown("#### 📟 สถานะระบบแบบ Real-time")
            s1, s2, s3, s4 = st.columns(4)
            
            stock_ratio = float(np.clip((stock_thb_now / target_stock_thb) if target_stock_thb > 0 else 0, 0, 1))
            fx_ratio = float(np.clip((sim["fx_used_usd"] / fx_limit_max) if fx_limit_max > 0 else 0, 0, 1))
            nc_ratio = float(np.clip((nc_now['actual'] / nc_now['required']) if nc_now['required'] > 0 else 0, 0, 1))
            
            with s1:
                with st.container(border=True):
                    st.markdown("<div style='font-size:0.85rem; color:#9CA3AF'>📦 สต็อกเหรียญคงเหลือ</div>", unsafe_allow_html=True)
                    st.markdown(f"<div style='font-size:1.6rem; font-weight:700; color:#00D26A'>{fmt_coin(sim['inv_coins'], asset)}</div>", unsafe_allow_html=True)
                    st.progress(stock_ratio)
                    st.caption(f"{stock_ratio*100:.0f}% ของเป้าหมาย ({fmt_baht(target_stock_thb)})")
                    
            with s2:
                with st.container(border=True):
                    fx_color = "#FF4B4B" if fx_ratio > 0.9 else ("#F59E0B" if fx_ratio > 0.7 else "#3B82F6")
                    st.markdown("<div style='font-size:0.85rem; color:#9CA3AF'>🌐 โควตา FX Limit</div>", unsafe_allow_html=True)
                    st.markdown(f"<div style='font-size:1.6rem; font-weight:700; color:{fx_color}'>$ {sim['fx_used_usd']:,.0f}</div>", unsafe_allow_html=True)
                    st.progress(fx_ratio)
                    st.caption(f"ใช้ไป {fx_ratio*100:.1f}% จากเพดาน $ {fx_limit_max:,.0f}")
                    
            with s3:
                with st.container(border=True):
                    nc_color = "#00D26A" if nc_ratio >= 1.0 else "#FF4B4B"
                    st.markdown("<div style='font-size:0.85rem; color:#9CA3AF'>⚖️ เงินกองทุนสุทธิ (NC)</div>", unsafe_allow_html=True)
                    st.markdown(f"<div style='font-size:1.6rem; font-weight:700; color:{nc_color}'>{fmt_baht(nc_now['actual'])}</div>", unsafe_allow_html=True)
                    st.progress(nc_ratio)
                    st.caption(f"ส่วนเกิน (Buffer): {fmt_baht(nc_now['buffer'], force_sign=True)}")
                    
            with s4:
                with st.container(border=True):
                    pnl_color = "#00D26A" if sim["pnl_thb"] >= 0 else "#FF4B4B"
                    st.markdown("<div style='font-size:0.85rem; color:#9CA3AF'>💰 กำไรสะสมดีลเลอร์</div>", unsafe_allow_html=True)
                    st.markdown(f"<div style='font-size:1.6rem; font-weight:700; color:{pnl_color}'>{fmt_baht(sim['pnl_thb'], True)}</div>", unsafe_allow_html=True)
                    st.progress(1.0 if sim["pnl_thb"] >= 0 else 0.0)
                    avg_pnl = sim['pnl_thb']/len(sim['orders']) if sim["orders"] else 0
                    st.caption(f"จาก {len(sim['orders'])} คำสั่ง (เฉลี่ย {fmt_baht(avg_pnl, force_sign=True)}/คำสั่ง)")

            if sim["unhedged_thb"] > 0:
                verdict_box(False, f"⚠️ อันตราย! มีความเสี่ยงราคาที่ไม่ได้ป้องกัน (Unhedged Risk): {fmt_baht(sim['unhedged_thb'])}",
                            "เกิดจากคำสั่งที่ถูกบล็อกการโอนเงิน (FX Limit เต็ม) ทำให้ดีลเลอร์ต้องแบกรับความเสี่ยงราคาเหรียญผันผวนเอง")

            # ==========================================
            # พื้นที่จำลองคำสั่งซื้อ และ เส้นทางการทำงาน
            # ==========================================
            left, right = st.columns([1.2, 2], gap="large")

            with left:
                st.markdown("#### 🧑‍💻 ส่งคำสั่งซื้อ/ขาย")
                with st.container(border=True):
                    order_side = st.radio("ประเภทคำสั่ง", ["ซื้อเหรียญ (Buy)", "ขายเหรียญ (Sell)"], horizontal=True, key="sim_side")
                    side_key = "buy" if "ซื้อ" in order_side else "sell"
                    order_amt = comma_number_input(f"มูลค่าที่ต้องการเทรด (บาท)", value=500_000, min_value=0, key="sim_amount")
                    
                    mid_now = coin_price_thb_now * (1 + local_premium)
                    quote_now = mid_now * (1 + dealer_spread) if side_key == "buy" else mid_now * (1 - dealer_spread)
                    
                    st.info(f"**ราคาบนจอ:** ฿ {quote_now:,.2f} / {asset}\n\n"
                            f"<small>(อ้างอิงราคาโลก + premium {local_premium*100:.2f}% {'+' if side_key=='buy' else '-'} spread {dealer_spread*100:.2f}%)</small>", 
                            icon="💡")
                    
                    send = st.button("📤 ยืนยันคำสั่ง", type="primary", use_container_width=True)
                    reset = st.button("♻️ เริ่มวันใหม่ (ล้างข้อมูลทั้งหมด)", use_container_width=True)

                with st.expander("🤖 เครื่องมือสุ่มออเดอร์อัตโนมัติ (Batch Simulation)"):
                    st.caption("จำลองออเดอร์รัวๆ ตามค่าความผันผวน (CV) ที่ตั้งไว้ในแถบซ้าย")
                    n_orders = st.number_input("จำนวนออเดอร์ที่จะสุ่ม", value=20, min_value=1, max_value=500, step=10, key="sim_n")
                    seed = st.number_input("Random seed", value=42, step=1, key="sim_seed")
                    run_day = st.button("🎲 รันอัตโนมัติ", use_container_width=True)

                if reset:
                    st.session_state.sim = _sim_defaults(asset, spot_usd_now, usdthb_now_sim, target_stock_thb)
                    st.session_state.sim_steps = []
                    st.rerun()

                if send:
                    steps, _ = execute_order(sim, side_key, float(order_amt), ctx)
                    st.session_state.sim_steps = steps

                if run_day:
                    rng = np.random.default_rng(int(seed))
                    mean_amt = daily_volume_thb / max(1, int(n_orders))
                    sigma = np.sqrt(np.log(1 + flow_cv_pct ** 2))
                    mu = np.log(max(mean_amt, 1.0)) - 0.5 * sigma ** 2
                    p_buy = 0.5 + net_bias_pct / 2.0
                    last_steps = []
                    for _ in range(int(n_orders)):
                        amt = float(rng.lognormal(mu, sigma))
                        s_ = "buy" if rng.random() < p_buy else "sell"
                        last_steps, _ = execute_order(sim, s_, max(amt, MIN_TRADE_THB), ctx)
                    st.session_state.sim_steps = last_steps

            with right:
                st.markdown("#### 🔎 เส้นทางการทำงาน (Order Journey)")
                steps_now = st.session_state.get("sim_steps", [])
                
                if not steps_now:
                    st.info("👋 ยินดีต้อนรับ! ลองพิมพ์ตัวเลขแล้วกด **ยืนยันคำสั่ง** ทางซ้ายมือ เพื่อดูว่าระบบหลังบ้านทำงานผ่านด่านอะไรบ้าง")
                else:
                    st.markdown("<div class='timeline-container'>", unsafe_allow_html=True)
                    for s in sorted(steps_now, key=lambda x: x["n"]):
                        step_card(s["n"], s["t"], s["s"], s.get("note", ""), s.get("rows"), s.get("total"))
                    st.markdown("</div>", unsafe_allow_html=True)

            # ---------- LEDGER + CHARTS ----------
            if sim["orders"]:
                st.divider()
                st.markdown("#### 📒 สมุดบัญชีและสถิติออเดอร์ (Order Ledger)")
                led = pd.DataFrame(sim["orders"])
                led.index = range(1, len(led) + 1)
                led.index.name = "#"

                lc = st.columns(4)
                buys = (led["ฝั่ง"] == "ซื้อ").sum()
                blocked = (led["ผลด่าน"] != "ผ่าน").sum()
                metric_card(lc[0], "จำนวนออเดอร์", f"{len(led):,}", None, f"ซื้อ {buys} · ขาย {len(led)-buys}")
                metric_card(lc[1], "Notional รวม", fmt_baht(led["มูลค่า (บาท)"].sum()), None, "มูลค่าธุรกรรมรวม (ไม่ใช่กำไร)")
                metric_card(lc[2], "มาร์จิ้นเฉลี่ย", f"{led['กำไรออเดอร์'].sum()/led['มูลค่า (บาท)'].sum()*10000:,.1f} bps", led["กำไรออเดอร์"].sum())
                metric_card(lc[3], "ออเดอร์ที่ติดด่าน", f"{blocked:,}", -1 if blocked else 0, f"{blocked/len(led)*100:.1f}% ของทั้งหมด")

                g1, g2 = st.columns(2)
                with g1:
                    fig_pnl = go.Figure()
                    fig_pnl.add_trace(go.Scatter(y=led["กำไรออเดอร์"].cumsum(), x=led.index, name="กำไรสะสม", line=dict(color="#00D26A", width=2), fill="tozeroy", fillcolor="rgba(0,210,106,.12)"))
                    fig_pnl.update_layout(template="plotly_dark", height=320, margin=dict(t=40, b=20), title="กำไรสะสมรายออเดอร์", xaxis_title="ออเดอร์ที่", yaxis_title="THB", showlegend=False)
                    st.plotly_chart(fig_pnl, **WIDE)
                with g2:
                    fig_gate = go.Figure()
                    fig_gate.add_trace(go.Scatter(y=led["FX ใช้สะสม (USD)"], x=led.index, name="FX ใช้สะสม", line=dict(color="#3B82F6", width=2)))
                    fig_gate.add_hline(y=fx_limit_max, line=dict(color="#FF4B4B", dash="dash"), annotation_text="เพดาน FX Limit")
                    fig_gate.update_layout(template="plotly_dark", height=320, margin=dict(t=40, b=20), title="โควตาโอนเงินออกที่ใช้ไป", xaxis_title="ออเดอร์ที่", yaxis_title="USD", showlegend=False)
                    st.plotly_chart(fig_gate, **WIDE)

                fig_nc = go.Figure()
                fig_nc.add_trace(go.Scatter(y=led["NC Buffer"], x=led.index, name="NC Buffer", line=dict(color="#F59E0B", width=2)))
                fig_nc.add_hline(y=0, line=dict(color="#FF4B4B", dash="dash"), annotation_text="เกณฑ์ขั้นต่ำ")
                fig_nc.update_layout(template="plotly_dark", height=300, margin=dict(t=40, b=20), title="NC Buffer หลังแต่ละออเดอร์", xaxis_title="ออเดอร์ที่", yaxis_title="THB", showlegend=False)
                st.plotly_chart(fig_nc, **WIDE)

                st.dataframe(led.sort_index(ascending=False), height=360, **WIDE,
                             column_config={
                                 "มูลค่า (บาท)": st.column_config.NumberColumn(format="%.0f"),
                                 "ราคาที่ลูกค้าได้": st.column_config.NumberColumn(format="%.2f"),
                                 "เหรียญที่ส่งมอบ": st.column_config.NumberColumn(format="%.6f"),
                                 "Hedge (USD)": st.column_config.NumberColumn(format="%.0f"),
                                 "รายได้": st.column_config.NumberColumn(format="%.0f"),
                                 "ต้นทุน": st.column_config.NumberColumn(format="%.0f"),
                                 "กำไรออเดอร์": st.column_config.NumberColumn(format="%.0f"),
                                 "สต็อกคงเหลือ": st.column_config.NumberColumn(format="%.6f"),
                                 "FX ใช้สะสม (USD)": st.column_config.NumberColumn(format="%.0f"),
                                 "NC Buffer": st.column_config.NumberColumn(format="%.0f"),
                             })
                st.download_button("⬇️ ดาวน์โหลดสมุดออเดอร์ (CSV)", to_csv_bytes(led), f"xspring_orders_{asset}.csv", "text/csv")
