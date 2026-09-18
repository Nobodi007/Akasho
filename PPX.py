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

# --- FIX #4: รองรับทั้ง Streamlit เก่า/ใหม่ (use_container_width ถูก deprecate ที่ 1.49) ---
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
    
    /* --- Gauge bars (หลอดพลัง) --- */
    .xs-gauge { margin:0 0 .35rem 0; }
    .xs-gauge .top { display:flex; justify-content:space-between; font-size:.8rem; color:#9CA3AF; margin-bottom:5px; }
    .xs-gauge .top b { color:#FAFAFA; font-variant-numeric:tabular-nums; }
    .xs-gauge .track { height:10px; background:#1f2937; border-radius:999px; overflow:hidden; }
    .xs-gauge .fill { height:100%; border-radius:999px; transition:width .4s ease; }
    .xs-gauge .sub { font-size:.74rem; color:#6B7280; margin-top:4px; }
    
    /* --- Timeline (เส้นเชื่อมด่านตรวจสอบ) --- */
    .xs-tl { position:relative; padding-left:34px; }
    .xs-tl::before { content:""; position:absolute; left:11px; top:14px; bottom:14px; width:2px;
                     background:linear-gradient(180deg,#00D26A 0%,#374151 100%); }
    .xs-tl .xs-step { position:relative; --c:#00D26A; border:1px solid #1f2937; border-radius:10px; padding:12px 16px; margin-bottom:10px; background:#0f1621; }
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
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="xs-hero">
  <h1>🏦 XSpring — Digital Asset Dealer Suite</h1>
  <p>Backtest 5 ปีย้อนหลัง + Liquidity &amp; Capital Planner + จำลองเส้นทางคำสั่งซื้อของลูกค้าทีละออเดอร์</p>
  <span class="xs-pill">Back-to-Back Hedging</span>
  <span class="xs-pill">FX Limit Engine</span>
  <span class="xs-pill">NCR Capital Planner</span>
  <span class="xs-pill">Customer Order Trace</span>
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

# เกณฑ์เงินกองทุนที่ประกาศไว้ตายตัว (ไม่เปิดให้ปรับ)
HOT_WALLET_NC_RATE = 1.00      # 100% ของมูลค่าที่เก็บใน hot wallet
COLD_DOMESTIC_NC_RATE = 0.01   # 1% ของมูลค่าที่ฝาก cold wallet ในประเทศ
HOT_WALLET_CAP = 0.50          # เพดาน hot wallet เมื่อทรัพย์สินลูกค้า < 1,000 ล้านบาท
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
    """จำนวนเหรียญ: เหรียญราคาแพงต้องการทศนิยมเยอะกว่าเหรียญราคาถูก"""
    v = abs(float(value))
    d = 6 if v < 1 else (4 if v < 1000 else 2)
    return f"{value:,.{d}f}" + (f" {symbol}" if symbol else "")

def _reformat_comma_key(key):
    """Callback: เมื่อผู้ใช้พิมพ์เสร็จ ให้จัดรูปเลขในช่องใหม่ให้มี comma คั่นหลักพัน"""
    raw = st.session_state.get(key, "")
    cleaned = raw.replace(",", "").replace(" ", "").strip()
    try:
        num = float(cleaned)
        st.session_state[key] = f"{num:,.0f}" if num == int(num) else f"{num:,.2f}"
    except ValueError:
        pass  # พิมพ์ไม่ครบ/ไม่ใช่ตัวเลข ปล่อยไว้เฉย ๆ จนกว่าจะแก้ให้ถูก

def comma_number_input(label, value, min_value=None, key=None, help=None):
    """ช่องกรอกตัวเลขที่โชว์ comma คั่นหลักพันในช่องเลย (เช่น 150,000,000) แทน number_input ธรรมดา"""
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
    """กล่องสรุปผล ✅/⚠️/🚨 ใช้ทั่วทั้งแอปสำหรับสื่อสารผลเชิงเกณฑ์"""
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
    """หลอดแสดงความจุที่ใช้ไป: เขียว < warn_at <= ส้ม < crit_at <= แดง"""
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

def step_card(number, title, status, note="", rows=None, total=None):
    st.markdown(step_html(number, title, status, note, rows, total), unsafe_allow_html=True)

def render_timeline(steps):
    """วาดทุกด่านใน div เดียว เพื่อให้เส้น timeline ต่อกันเป็นเส้นเดียว"""
    html = "".join(step_html(s["n"], s["t"], s["s"], s.get("note", ""), s.get("rows"), s.get("total"))
                   for s in sorted(steps, key=lambda x: x["n"]))
    st.markdown(f"<div class='xs-tl'>{html}</div>", unsafe_allow_html=True)

# --- FIX #2: รอจนกล่องมีความสูงจริงก่อนวาด (แท็บที่ซ่อนอยู่ = height 0 -> กราฟค้างเปล่า) ---
def render_tradingview(symbol: str, container_id: str, height: int = 500,
                       interval: str = "D", studies=None):
    """ฝังกราฟ TradingView — container_id ต้องไม่ซ้ำกันในหน้าเดียว"""
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


@st.cache_data(show_spinner=False)
def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv().encode("utf-8-sig")


# =========================================================
# DATA LAYER
# =========================================================
def _normalize_index(d: pd.DataFrame) -> pd.DataFrame:
    """FIX #5: yfinance บางเวอร์ชันคืน index tz-aware บ้าง naive บ้าง -> reindex ไม่ match"""
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
    # FIX: คริปโตเทรด 7 วัน / FX เทรด 5 วัน -> ffill แทนการ dropna ทิ้งเสาร์-อาทิตย์
    df["USDTHB"] = fx_raw["Close"].reindex(df.index).ffill().bfill()
    df = df.dropna()
    if df.empty:
        return pd.DataFrame(), "ข้อมูลที่ได้ว่างเปล่าหลังทำความสะอาด"
    df["Volatility_Pct"] = (df["Day_High"] - df["Day_Low"]) / df["Global_USD"]
    return df, None


def apply_fx_limit(hedge_usd: pd.Series, index: pd.DatetimeIndex, fx_limit: float):
    """วันที่ถูกบล็อก = ไม่กินโควตา + รีเซ็ตทุกต้นเดือน"""
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
# RISK ENGINE (ใช้ร่วมกันทั้ง Backtest / Capital Planner / Order Simulator)
# =========================================================
def _risk_stats(r: pd.Series) -> dict | None:
    """คำนวณสถิติความเสี่ยงจาก log-return series (ใช้ได้ทั้งเหรียญเดี่ยวและพอร์ต)"""
    r = r.replace([np.inf, -np.inf], np.nan).dropna()
    if len(r) < 30:
        return None
    q01 = np.percentile(r, 1)
    q05 = np.percentile(r, 5)
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
    }


def risk_profile(px: pd.Series) -> dict | None:
    """สกัดพารามิเตอร์ความเสี่ยงจากราคาจริงย้อนหลังของเหรียญเดียว"""
    r = np.log(px / px.shift(1))
    return _risk_stats(r)


def safety_stock_factor(net_bias: float, flow_cv: float, lag_days: int, z_alpha: float) -> float:
    """a = สต็อกที่ต้องดอง ต่อ 1 บาทของปริมาณธุรกรรมต่อเดือน"""
    return (max(0.0, net_bias) * lag_days + z_alpha * flow_cv * np.sqrt(lag_days)) / 30.0


def crypto_haircut(es99: float, lag_days: int) -> float:
    """Haircut จากข้อมูลจริง: ES99% ขยายด้วยรากที่สองของ settlement lag (cap 95%)"""
    return float(min(es99 * np.sqrt(lag_days), 0.95))


def blended_custody_rate(hot_pct: float, cold_domestic_pct: float, cold_foreign_rate: float) -> float:
    """อัตรา NC เฉลี่ยถ่วงน้ำหนักของการเก็บรักษาเหรียญ 1 บาท"""
    return (hot_pct * HOT_WALLET_NC_RATE
            + (1 - hot_pct) * (cold_domestic_pct * COLD_DOMESTIC_NC_RATE
                               + (1 - cold_domestic_pct) * cold_foreign_rate))


def nc_snapshot(stock_thb: float, total_capital: float, cex_margin: float, liab: float,
                h_crypto: float, h_cex: float, fixed_min_nc: float,
                trading_risk_rate: float, daily_volume_thb: float,
                custody_rate: float) -> dict:
    """เปรียบเทียบ NC ที่มีจริง กับ NC ขั้นต่ำที่ต้องดำรงตามเกณฑ์ ณ ขนาดสต็อกหนึ่ง ๆ"""
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
    st.caption("ใช้ร่วมกันทั้งแท็บ **5-Year Backtest**, โหมด Single-Asset ของ **Capital Planner** "
               "และ **Order Simulator**")

    asset = st.selectbox("เลือกเหรียญ", SUPPORTED_ASSETS, key="bt_asset")
    if asset in STABLECOINS:
        st.warning(f"⚠️ {asset} เป็น Stablecoin — ใช้กลยุทธ์ Depeg Arbitrage + Carry Yield แทน Slippage Model")

    with st.expander("🌐 กระดานซื้อขาย", expanded=True):
        global_exchange = st.selectbox("กระดานโลกที่ใช้ Hedge", list(GLOBAL_EXCHANGE_FEE_PRESET.keys()),
                                       key="bt_global_exchange")
        local_exchange = st.selectbox("กระดานไทยอ้างอิงราคาลูกค้า", LOCAL_EXCHANGES, key="bt_local_exchange")
        st.caption(f"Yahoo ไม่มีคู่ {asset}-THB ตรง ๆ ระบบจึงสร้างราคา synthetic จาก {asset}-USD × USD/THB "
                   f"แล้วปรับด้วย Local Premium เป็นตัวแทนราคา **{local_exchange}** "
                   f"(เทียบของจริงได้ในกราฟ TradingView หน้าแท็บ 1)")

    with st.expander("📅 ช่วงเวลา Backtest", expanded=True):
        today = pd.Timestamp.now().date()
        preset_days = {"1 เดือน": 30, "3 เดือน": 90, "6 เดือน": 180,
                       "1 ปี": 365, "3 ปี": 365*3, "5 ปี": 365*5}
        preset = st.radio("เลือกช่วงเวลาด่วน",
                          ["กำหนดเอง", "1 เดือน", "3 เดือน", "6 เดือน", "1 ปี", "3 ปี", "5 ปี"],
                          index=6, horizontal=True, key="bt_preset")

        if preset != "กำหนดเอง":
            preset_start, preset_end = today - pd.Timedelta(days=preset_days[preset]), today
        else:
            preset_start, preset_end = today - pd.Timedelta(days=365*5), today

        ca, cb = st.columns(2)
        with ca:
            start_date = st.date_input("วันเริ่มต้น", value=preset_start,
                                       min_value=pd.Timestamp("2015-01-01").date(), max_value=today,
                                       key="bt_start", disabled=(preset != "กำหนดเอง"), format="YYYY-MM-DD")
        with cb:
            end_date = st.date_input("วันสิ้นสุด", value=preset_end,
                                     min_value=pd.Timestamp("2015-01-01").date(), max_value=today,
                                     key="bt_end", disabled=(preset != "กำหนดเอง"), format="YYYY-MM-DD")

        if preset != "กำหนดเอง":
            start_date, end_date = preset_start, preset_end

        st.caption(f"ช่วงที่เลือก: {start_date} → {end_date} ({(end_date - start_date).days} วัน)")

    dates_ok = start_date < end_date
    if not dates_ok:
        st.error("❌ วันเริ่มต้นต้องอยู่ก่อนวันสิ้นสุด")

    with st.expander("💰 พารามิเตอร์ Dealer", expanded=True):
        trade_vol = comma_number_input("ปริมาณซื้อขายลูกค้า/วัน (USD eq.)", value=100000, key="bt_trade_vol")
        st.caption(f"≈ ${fmt_num(trade_vol)}")
        dealer_spread = st.number_input("Dealer Spread ที่เก็บจากลูกค้า (%)", value=0.5, step=0.1, key="bt_spread") / 100

        if "bt_prev_gx" not in st.session_state:
            st.session_state.bt_prev_gx = global_exchange
        if "bt_hedge_fee" not in st.session_state:
            st.session_state.bt_hedge_fee = GLOBAL_EXCHANGE_FEE_PRESET[global_exchange]
        if st.session_state.bt_prev_gx != global_exchange:
            st.session_state.bt_hedge_fee = GLOBAL_EXCHANGE_FEE_PRESET[global_exchange]
            st.session_state.bt_prev_gx = global_exchange

        hedge_fee = st.number_input("ค่าธรรมเนียม Global CEX (%)", key="bt_hedge_fee", step=0.01) / 100
        fx_limit_max = comma_number_input("FX Limit ต่อเดือน (USD)", value=5000000,
                                          min_value=1, key="bt_fx_limit")
        st.caption(f"≈ ${fmt_num(fx_limit_max)}")
        local_premium = st.number_input(
            "Local Premium/Discount ฝั่งไทย (%)", value=0.1, step=0.1, key="bt_local_premium",
            help="ส่วนต่างราคากระดานไทยเทียบราคาโลก ค่าเริ่มต้น 0.1% สะท้อนพรีเมียมที่มักพบช่วงตลาดปกติ") / 100

    with st.expander("💳 ค่าธรรมเนียมกระดานไทย"):
        st.caption("เราเป็นเจ้าของกระดานไทย ค่าธรรมเนียมซื้อขายจึงเป็น **รายได้** "
                   "ต่างจากค่าธรรมเนียม Global CEX ที่เป็นต้นทุนจริง")
        include_trading_fee_revenue = st.checkbox("รวมรายได้ค่าธรรมเนียมซื้อขาย 0.25%", value=True,
                                                  key="bt_include_fee_rev")
        withdrawal_fee_markup_pct = st.slider("Markup ค่าธรรมเนียมถอน (%)", 0, 200, 0, key="bt_wd_markup",
                                              help="0% = Pass-through เท่าต้นทุนจริง") / 100
        settlements_per_day = st.number_input("รอบถอนเหรียญให้ลูกค้า/วัน", value=1, min_value=1, step=1,
                                              key="bt_settlements")
        bank_type = st.selectbox("ธนาคารปลายทางถอนบาท", ["SCB", "ธนาคารอื่น", "KTB (กรุงไทย)"], key="bt_bank_type")
        st.caption(f"ขั้นต่ำซื้อขายจริง {MIN_TRADE_THB:,.0f} บาท/คำสั่ง — ต่ำกว่าปริมาณที่ตั้งไว้มาก จึงไม่กระทบผลจำลอง")

    with st.expander("🏦 สิทธิพิเศษ KTB (ความสัมพันธ์กับกรุงไทย)", expanded=(bank_type.startswith("KTB"))):
        st.caption("ใส่ตัวเลขจริงที่เจรจาได้กับ KTB ตรงนี้ — ค่าเริ่มต้นเป็นเพียงสมมติฐานเพื่อจำลอง "
                   "ไม่ใช่เรทที่ยืนยันแล้ว ต้องยืนยันกับ Relationship Manager ก่อนใช้จริง")
        use_ktb_fx = st.checkbox("ใช้เรทแลกเปลี่ยน USD/THB พิเศษจาก KTB", value=True, key="bt_use_ktb_fx",
                                 help="เรทพิเศษที่ดีกว่าตลาด จะลดต้นทุน/เพิ่มรายได้ตอนแปลงเงิน USD กลับเป็น THB")
        ktb_fx_spread_bps = st.number_input(
            "ส่วนต่างเรทที่ดีกว่าตลาด (bps)", value=15.0, step=1.0, min_value=0.0, key="bt_ktb_fx_bps",
            help="1 bps = 0.01% เช่น 15 bps บนปริมาณ 100,000 USD ≈ ประหยัด 150 USD เทียบเท่าเรทตลาด") if use_ktb_fx else 0.0
        ktb_wd_fee_thb = st.number_input(
            "ค่าธรรมเนียมถอนบาทของ KTB ต่อรายการ (บาท)", value=15.0, step=1.0, min_value=0.0, key="bt_ktb_wd_fee",
            help="ใช้แทนอัตรา SCB/ธนาคารอื่น เมื่อเลือก 'ธนาคารปลายทางถอนบาท' เป็น KTB ด้านบน")
        st.caption(f"ผลลัพธ์: เรทพิเศษ {ktb_fx_spread_bps:.1f} bps ({ktb_fx_spread_bps/100:.3f}%) "
                  + (f"· ค่าธรรมเนียมถอน KTB {ktb_wd_fee_thb:,.0f} บาท/รายการ (ใช้งานอยู่)"
                     if bank_type.startswith("KTB") else "· เลือกธนาคารปลายทางเป็น KTB ด้านบนเพื่อใช้ค่าธรรมเนียมนี้"))

    if asset in STABLECOINS:
        with st.expander("🪙 กลยุทธ์ Stablecoin", expanded=True):
            peg_target = st.number_input("Peg Target (USD)", value=1.00, step=0.01, key="bt_peg")
            depeg_capture_pct = st.slider("Depeg Arbitrage Capture (%)", 0, 100, 80, key="bt_depeg") / 100
            carry_apy = st.number_input("Carry Yield APY (%)", value=4.0, step=0.5, key="bt_carry") / 100
        slippage_sensitivity = 0.0
    else:
        with st.expander("📉 Execution Model", expanded=True):
            slippage_sensitivity = st.number_input(
                "Slippage Sensitivity (% ของ Volatility รายวัน)", value=10.0, step=1.0, key="bt_slip",
                help="ผูกต้นทุน Execution กับ Day High-Low Range จริงของเหรียญ") / 100
        peg_target, depeg_capture_pct, carry_apy = 1.0, 0.0, 0.0

    st.divider()
    st.markdown("### 🏛️ งบดุลและ Flow (ใช้ร่วม Tab 2 + Tab 3)")
    st.caption("ย้ายมาไว้ที่เดียว เพื่อให้ Capital Planner กับ Order Simulator "
               "พูดถึงบริษัทเดียวกันเสมอ")

    with st.expander("📥 Flow Assumptions", expanded=False):
        monthly_volume_thb = comma_number_input("ปริมาณธุรกรรมลูกค้าต่อเดือน (THB)",
                                                value=300_000_000, min_value=0, key="cp_volume")
        st.caption(f"≈ {fmt_baht(monthly_volume_thb)}")
        net_bias_pct = st.slider("Net Flow Bias — ลูกค้าซื้อสุทธิ(+) / ขายสุทธิ(-)", -100, 100, 20,
                                 key="cp_bias",
                                 help="ทิศทางสุทธิที่ทำให้ต้องดองคริปโตไว้เป็นสต็อก (ฝั่ง + เท่านั้นที่กินสต็อก)") / 100
        flow_cv_pct = st.slider("ความผันผวนของปริมาณต่อวัน (CV, %)", 10, 150, 40, key="cp_cv") / 100
        settlement_days = st.number_input("Settlement / Hedge Lag (วัน)", value=2, min_value=1, max_value=10,
                                          step=1, key="cp_lag",
                                          help="ระยะเวลาที่ต้องถือสต็อกไว้ก่อนจะ hedge/settle ได้ครบ")
        confidence = st.select_slider("Confidence Level ของ Safety Stock",
                                      options=[90, 95, 99, 99.9], value=99, key="cp_conf")
        z_alpha = Z_SCORE_MAP[confidence]

    with st.expander("💼 Capital Pool", expanded=False):
        total_capital_thb = comma_number_input(
            "เงินทุนสภาพคล่องรวม (THB)", value=300_000_000, min_value=0, key="cp_total_capital",
            help="เงินสดทั้งหมดก่อนจัดสรรไปเป็นสต็อกเหรียญ")
        st.caption(f"≈ {fmt_baht(total_capital_thb)}")
        cex_margin_thb = comma_number_input("เงินทุนบนกระดานโลก / CEX Margin (THB)",
                                            value=60_000_000, min_value=0, key="cp_cex_margin")
        st.caption(f"≈ {fmt_baht(cex_margin_thb)}")
        liab_thb = comma_number_input("หนี้สินต่อลูกค้า (THB)", value=250_000_000, min_value=1, key="cp_liab")
        st.caption(f"≈ {fmt_baht(liab_thb)}")
        cex_margin_asset = st.selectbox("สินทรัพย์ Margin บนกระดานโลก",
                                        ["Stablecoin (ความเสี่ยงต่ำ)",
                                         "เหรียญเดียวกับที่เทรด (ความเสี่ยงเท่าคริปโต)"], key="cp_cex_asset")
        cex_counterparty_haircut = st.number_input("Counterparty Haircut กรณี CEX Margin เป็น Stablecoin (%)",
                                                   value=2.0, step=0.5, min_value=0.0, key="cp_cex_hc") / 100

    with st.expander("⚖️ เกณฑ์เงินกองทุน ก.ล.ต.", expanded=False):
        is_custodian = st.checkbox("เก็บรักษาทรัพย์สินลูกค้า (Custody)", value=True, key="cp_is_custodian",
                                   help="ทุนขั้นต่ำคงที่ 25 ล้านบาทหากเก็บรักษาทรัพย์สินลูกค้า, 5 ล้านบาทหากไม่เก็บ")
        fixed_min_nc = 25_000_000.0 if is_custodian else 5_000_000.0
        trading_risk_rate = st.number_input(
            "อัตรา NC ความเสี่ยงบริการซื้อขาย (% ของมูลค่าซื้อขายเฉลี่ย/วัน)", value=2.0, step=0.1,
            min_value=0.0, key="cp_trading_risk_rate",
            help="ตามประกาศ กำหนดไม่น้อยกว่า 2% ของมูลค่าซื้อขายเฉลี่ยต่อวันย้อนหลัง 3 เดือน") / 100
        cold_foreign_rate = st.number_input(
            "อัตรา NC cold wallet ต่างประเทศ โดยประมาณ (%)", value=2.0, step=0.5, min_value=1.0,
            key="cp_cold_foreign_rate",
            help="ประกาศระบุเพียงว่าอัตรานี้สูงกว่ากรณีฝากในประเทศ (1%) แต่ไม่ได้เผยแพร่ตัวเลขแน่ชัด") / 100
        hot_wallet_pct = st.slider("สัดส่วนสต็อกเหรียญที่เก็บใน Hot Wallet (%)", 0, 100, 50,
                                   key="cp_hot_pct") / 100
        cold_domestic_split_pct = st.slider("สัดส่วน Cold Wallet ที่ฝากในประเทศ (%)", 0, 100, 100,
                                            key="cp_cold_domestic_pct") / 100
        st.caption(f"🔒 อัตราคงที่ตามประกาศ: Hot wallet {HOT_WALLET_NC_RATE*100:.0f}% · "
                   f"Cold wallet ในประเทศ {COLD_DOMESTIC_NC_RATE*100:.0f}% · "
                   f"ทุนขั้นต่ำคงที่ {fmt_baht(fixed_min_nc)}")

daily_volume_thb = monthly_volume_thb / 30.0
custody_rate_blended = blended_custody_rate(hot_wallet_pct, cold_domestic_split_pct, cold_foreign_rate)
hot_wallet_cap_breach = (liab_thb < HOT_WALLET_CAP_LIAB_THRESHOLD) and (hot_wallet_pct > HOT_WALLET_CAP)

# ===== โหลดข้อมูลครั้งเดียว ใช้ร่วมกันทุกแท็บ =====
data, data_err = (pd.DataFrame(), "ช่วงวันที่ไม่ถูกต้อง") if not dates_ok \
                 else fetch_price_data(asset, start_date, end_date)


# =========================================================
# TABS
# =========================================================
tab1, tab2, tab3 = st.tabs(["📊 5-Year Backtest Simulator",
                            "🧮 Liquidity & Capital Planner",
                            "🧾 Customer Order Simulator"])

# ---------------------------------------------------------
# TAB 1 — BACKTEST
# ---------------------------------------------------------
with tab1:
    if data.empty:
        st.error(f"⚠️ {data_err or 'ไม่สามารถโหลดข้อมูลได้'} — ลองเปลี่ยนช่วงวันที่หรือตรวจสอบการเชื่อมต่ออินเทอร์เน็ต")
    else:
        bt = data.copy()
        bt["Local_THB"] = bt["Global_USD"] * bt["USDTHB"] * (1 + local_premium)

        # ---------- P&L ENGINE ----------
        bt["Coin_Volume"] = trade_vol / bt["Global_USD"]
        bt["Gross_Notional_THB"] = bt["Coin_Volume"] * bt["Local_THB"]
        bt["Spread_Revenue_THB"] = bt["Gross_Notional_THB"] * dealer_spread
        bt["FX_Basis_PnL_THB"] = trade_vol * bt["USDTHB"] * local_premium
        bt["Hedge_Fee_Cost_THB"] = trade_vol * hedge_fee * bt["USDTHB"]
        bt["Hedge_Notional_USD"] = trade_vol * (1 + hedge_fee)
        # KTB: เรทแลกเปลี่ยน USD/THB พิเศษที่ดีกว่าตลาด (bps)
        bt["KTB_FX_Benefit_THB"] = trade_vol * bt["USDTHB"] * (ktb_fx_spread_bps / 10000.0)

        if asset in STABLECOINS:
            bt["Depeg_Deviation"] = peg_target - bt["Global_USD"]
            bt["Depeg_PnL_THB"] = (bt["Coin_Volume"] * bt["Depeg_Deviation"]
                                     * bt["USDTHB"] * depeg_capture_pct)
            bt["Carry_Yield_THB"] = trade_vol * (carry_apy / 365) * bt["USDTHB"]
            bt["Slippage_Cost_THB"] = 0.0
        else:
            bt["Depeg_Deviation"] = 0.0
            bt["Depeg_PnL_THB"] = 0.0
            bt["Carry_Yield_THB"] = 0.0
            bt["Slippage_Cost_THB"] = (trade_vol * bt["Volatility_Pct"]
                                         * slippage_sensitivity * bt["USDTHB"])

        bt["Trading_Fee_Revenue_THB"] = (bt["Gross_Notional_THB"] * LOCAL_TRADING_FEE_PCT
                                           if include_trading_fee_revenue else 0.0)

        wd_fee_per_coin = WITHDRAWAL_FEE_TABLE.get(asset, 0.0)
        wd_network_cost = wd_fee_per_coin * bt["Global_USD"] * bt["USDTHB"] * settlements_per_day
        bt["Withdrawal_Fee_Markup_Revenue_THB"] = wd_network_cost * withdrawal_fee_markup_pct

        bt["THB_WD_Fee"] = bt["USDTHB"].map(lambda fx: calc_thb_withdrawal_fee(trade_vol * fx, bank_type, ktb_wd_fee_thb))
        bt["THB_Fee_Markup_Revenue_THB"] = (bt["THB_WD_Fee"] * settlements_per_day
                                              * withdrawal_fee_markup_pct)

        bt["Fee_Revenue_THB"] = (bt["Trading_Fee_Revenue_THB"]
                                   + bt["Withdrawal_Fee_Markup_Revenue_THB"]
                                   + bt["THB_Fee_Markup_Revenue_THB"])

        bt["Revenue_THB"] = (bt["Spread_Revenue_THB"] + bt["FX_Basis_PnL_THB"]
                               + bt["Fee_Revenue_THB"] + bt["Depeg_PnL_THB"] + bt["Carry_Yield_THB"]
                               + bt["KTB_FX_Benefit_THB"])
        bt["Cost_THB"] = bt["Hedge_Fee_Cost_THB"] + bt["Slippage_Cost_THB"]
        bt["Daily_PnL_THB"] = bt["Revenue_THB"] - bt["Cost_THB"]

        # ---------- FX LIMIT ----------
        allowed, usage = apply_fx_limit(bt["Hedge_Notional_USD"], bt.index, fx_limit_max)
        bt["Trade_Allowed"], bt["Current_FX_Usage"] = allowed, usage
        bt["FX_Limit_Hit"] = 1 - allowed
        bt["Actual_Daily_PnL"] = np.where(allowed == 1, bt["Daily_PnL_THB"], 0.0)
        bt["Actual_Cum_PnL"] = bt["Actual_Daily_PnL"].cumsum()

        # ---------- STATS ----------
        traded = bt[bt["Trade_Allowed"] == 1]
        total_revenue_thb = traded["Revenue_THB"].sum()
        total_cost_thb = traded["Cost_THB"].sum()
        net_pnl_thb = bt["Actual_Cum_PnL"].iloc[-1]
        total_notional = traded["Gross_Notional_THB"].sum()
        margin_bps = (net_pnl_thb / total_notional * 10000) if total_notional else 0

        total_days, traded_days = len(bt), int(allowed.sum())
        limit_hit_days = int(bt["FX_Limit_Hit"].sum())
        win_days = int((bt["Actual_Daily_PnL"] > 0).sum())
        win_rate = win_days / traded_days * 100 if traded_days else 0
        avg_daily_pnl = traded["Daily_PnL_THB"].mean() if traded_days else 0
        best_day, worst_day = bt["Actual_Daily_PnL"].max(), bt["Actual_Daily_PnL"].min()

        running_max = bt["Actual_Cum_PnL"].cummax()
        max_drawdown = (bt["Actual_Cum_PnL"] - running_max).min()
        # FIX #3: คิด drawdown % เทียบ peak ของ "วันเดียวกัน"
        dd_series = (bt["Actual_Cum_PnL"] - running_max) / running_max.where(running_max > 0)
        dd_pct = dd_series.min() * 100
        dd_pct = 0.0 if pd.isna(dd_pct) else dd_pct

        st.success(f"✅ โหลดข้อมูล **{asset}** ช่วง {start_date} → {end_date} สำเร็จ "
                   f"({total_days} วัน | เทรดได้จริง {traded_days} วัน)")

        # ---------- LIVE TRADINGVIEW ----------
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
            st.info(f"💡 ใช้เทียบว่า **Local Premium {local_premium*100:.2f}%** ที่ตั้งไว้ใกล้ความจริงแค่ไหน — "
                    f"หารด้วยเรท USD/THB ปัจจุบัน (~{bt['USDTHB'].iloc[-1]:.2f}) แล้วเทียบกับราคาโลกได้เลย")
        st.caption("หมายเหตุ: บางคู่บนกระดานไทยอาจไม่มีฟีดบน TradingView — พิมพ์เปลี่ยนสัญลักษณ์ในกราฟได้โดยตรง")

        # ---------- KPI ----------
        section("📈 Performance Summary")
        r1 = st.columns(4)
        metric_card(r1[0], "Net P&L (THB)", fmt_baht(net_pnl_thb, True), net_pnl_thb,
                    f"{margin_bps:,.1f} bps ของ notional", "1.7rem")
        metric_card(r1[1], "Total Revenue", fmt_baht(total_revenue_thb), total_revenue_thb,
                    "Spread + Fee + Basis + Carry")
        metric_card(r1[2], "Total Cost", fmt_baht(total_cost_thb), -abs(total_cost_thb),
                    "Hedge Fee + Slippage")
        metric_card(r1[3], "Avg Daily P&L", fmt_baht(avg_daily_pnl, True), avg_daily_pnl,
                    f"เฉลี่ยจาก {traded_days} วันที่เทรดได้")

        r2 = st.columns(4)
        metric_card(r2[0], "Best Day", fmt_baht(best_day, True), best_day)
        metric_card(r2[1], "Worst Day", fmt_baht(worst_day, True), worst_day)
        metric_card(r2[2], "Max Drawdown", fmt_baht(max_drawdown),
                    max_drawdown if max_drawdown != 0 else -0.01, f"{dd_pct:.2f}% จาก peak")
        metric_card(r2[3], "Win Rate", f"{win_rate:.1f}%", None, f"{win_days}/{traded_days} วัน")

        r3 = st.columns(4)
        metric_card(r3[0], "Gross Notional หมุนเวียน", fmt_baht(total_notional), None, "มูลค่าธุรกรรมรวม (ไม่ใช่กำไร)")
        metric_card(r3[1], "FX Limit Hit", f"{limit_hit_days} วัน",
                    -1 if limit_hit_days else 0,
                    f"{(limit_hit_days/total_days*100) if total_days else 0:.1f}% ของช่วงเวลา")
        if asset in STABLECOINS:
            metric_card(r3[2], "Avg Depeg Deviation", f"{bt['Depeg_Deviation'].mean()*100:+.3f}%")
            metric_card(r3[3], "Total Carry Yield", fmt_baht(traded["Carry_Yield_THB"].sum()),
                        traded["Carry_Yield_THB"].sum())
        else:
            metric_card(r3[2], "Avg Daily Volatility", f"{bt['Volatility_Pct'].mean()*100:.2f}%")
            metric_card(r3[3], "Total Slippage Cost", fmt_baht(traded["Slippage_Cost_THB"].sum()),
                        -abs(traded["Slippage_Cost_THB"].sum()))

        # ---------- WATERFALL ----------
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

        # FIX #6: measure "total" ไม่ใช้ค่า y -> ใส่ text เอง
        wf_text = [fmt_baht(v, True) for v in wf_values[:-1]] + [fmt_baht(sum(wf_values[:-1]), True)]

        fig_wf = go.Figure(go.Waterfall(
            orientation="v",
            measure=["relative"] * (len(wf_labels) - 1) + ["total"],
            x=wf_labels, y=wf_values, text=wf_text, textposition="outside",
            connector={"line": {"color": "#374151"}},
            increasing={"marker": {"color": "#00D26A"}},
            decreasing={"marker": {"color": "#FF4B4B"}},
            totals={"marker": {"color": "#3B82F6"}},
        ))
        fig_wf.update_layout(template="plotly_dark", height=440, showlegend=False,
                             margin=dict(t=40, b=20), yaxis_title="THB")
        st.plotly_chart(fig_wf, **WIDE)

        # ---------- CUMULATIVE P&L ----------
        section("📊 Cumulative P&L")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=bt.index, y=bt["Actual_Cum_PnL"], name="Cumulative P&L",
                                 line=dict(color="#00D26A", width=2.2),
                                 fill="tozeroy", fillcolor="rgba(0,210,106,0.12)"))
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

        # ---------- MONTHLY HEATMAP ----------
        with st.expander("📅 P&L รายเดือน"):
            m = bt.groupby([bt.index.year, bt.index.month])["Actual_Daily_PnL"].sum().unstack(fill_value=0)
            m.columns = [f"{c:02d}" for c in m.columns]
            fig_hm = go.Figure(go.Heatmap(z=m.values, x=list(m.columns), y=[str(i) for i in m.index],
                                          colorscale=[[0, "#FF4B4B"], [0.5, "#111827"], [1, "#00D26A"]],
                                          zmid=0, texttemplate="%{z:,.0f}", textfont={"size": 9}))
            fig_hm.update_layout(template="plotly_dark", height=60 * len(m) + 120,
                                 margin=dict(t=20, b=20), xaxis_title="เดือน", yaxis_title="ปี")
            st.plotly_chart(fig_hm, **WIDE)

        # ---------- FEE BREAKDOWN ----------
        with st.expander("💳 สรุปรายได้ค่าธรรมเนียมกระดานไทย"):
            f = st.columns(4)
            metric_card(f[0], "ค่าธรรมเนียมซื้อขาย 0.25%", fmt_baht(traded["Trading_Fee_Revenue_THB"].sum()),
                        traded["Trading_Fee_Revenue_THB"].sum(), font_size="1.25rem")
            metric_card(f[1], "Markup ถอนเหรียญ", fmt_baht(traded["Withdrawal_Fee_Markup_Revenue_THB"].sum()),
                        traded["Withdrawal_Fee_Markup_Revenue_THB"].sum(), font_size="1.25rem")
            metric_card(f[2], "Markup ถอนเงินบาท", fmt_baht(traded["THB_Fee_Markup_Revenue_THB"].sum()),
                        traded["THB_Fee_Markup_Revenue_THB"].sum(), font_size="1.25rem")
            metric_card(f[3], "รวมรายได้ค่าธรรมเนียม", fmt_baht(traded["Fee_Revenue_THB"].sum()),
                        traded["Fee_Revenue_THB"].sum(), font_size="1.25rem")
            st.caption("ค่าธรรมเนียมถอนเป็น Pass-through เท่าต้นทุนจริงโดยดีฟอลต์ (ไม่กระทบกำไร) "
                       "ยกเว้นตั้ง Markup ไว้ในแถบซ้าย · ทุกตัวเลขนับเฉพาะวันที่เทรดผ่าน FX Limit")

        # ---------- LEDGER ----------
        with st.expander("🔍 Daily Ledger (100 วันล่าสุด)"):
            cols = ["Global_USD", "Local_THB", "USDTHB", "Volatility_Pct",
                    "Gross_Notional_THB", "Spread_Revenue_THB", "FX_Basis_PnL_THB",
                    "KTB_FX_Benefit_THB", "Hedge_Fee_Cost_THB", "Slippage_Cost_THB", "Fee_Revenue_THB"]
            if asset in STABLECOINS:
                cols += ["Depeg_Deviation", "Depeg_PnL_THB", "Carry_Yield_THB"]
            cols += ["Actual_Daily_PnL", "Current_FX_Usage", "FX_Limit_Hit"]
            ledger = bt[cols]
            st.dataframe(ledger.sort_index(ascending=False).head(100), height=400, **WIDE)
            st.download_button("⬇️ ดาวน์โหลด Ledger ทั้งหมด (CSV)",
                               to_csv_bytes(ledger),
                               f"xspring_ledger_{asset}_{start_date}_{end_date}.csv", "text/csv")


# ---------------------------------------------------------
# TAB 2 — LIQUIDITY & CAPITAL PLANNER
# ---------------------------------------------------------
with tab2:
    st.markdown("""
ตอบคำถามที่ผู้บริหารถามจริง:

> **"ถ้าธุรกรรมเดือนละ X ล้าน ต้องดำรงเหรียญเท่าไหร่ เงินสดเท่าไหร่ NC เหลือเท่าไหร่ ผ่านเกณฑ์ไหม และทุนที่มีรับได้สูงสุดกี่ล้าน"**

โดยดึงค่า Volatility / VaR / Expected Shortfall จาก **ราคาจริงย้อนหลัง** (ช่วงเวลาเดียวกับที่ตั้งไว้ในแถบซ้าย)
    """)

    if not dates_ok:
        st.error("❌ ช่วงวันที่ในแถบซ้ายไม่ถูกต้อง — แก้ก่อนถึงจะคำนวณความเสี่ยงได้")
    else:
        section("🎛️ โหมดคำนวณความเสี่ยง")
        cp_mode = st.radio("เลือกโหมด",
                           ["Single-Asset (ใช้เหรียญที่เลือกในแถบซ้าย)", "Multi-Asset Portfolio"],
                           horizontal=True, key="cp_mode")

        rp = None
        risk_label = ""

        if cp_mode.startswith("Single"):
            if data.empty:
                st.error(f"⚠️ โหลดข้อมูล {asset} ไม่สำเร็จ: {data_err}")
            else:
                rp = risk_profile(data["Global_USD"])
                risk_label = asset
                if rp is None:
                    st.error("ข้อมูลย้อนหลังน้อยกว่า 30 วัน — เลือกช่วงเวลายาวขึ้นในแถบซ้าย")
        else:
            ma_c1, ma_c2 = st.columns([2, 1])
            with ma_c1:
                selected_assets = st.multiselect("เลือกเหรียญในพอร์ต", SUPPORTED_ASSETS,
                                                 default=["BTC", "ETH", "USDT"], key="cp_ma_assets")
            with ma_c2:
                st.caption("ช่วงเวลาย้อนหลังใช้ค่าเดียวกับแถบซ้าย")
                st.write(f"`{start_date} → {end_date}`")

            if not selected_assets:
                st.info("เลือกอย่างน้อย 1 เหรียญเพื่อคำนวณพอร์ต")
            else:
                st.caption("กำหนดสัดส่วนพอร์ต (%) — ระบบ normalize ให้รวมเป็น 100% ให้อัตโนมัติ")
                wcols = st.columns(min(len(selected_assets), 6))
                default_w = round(100 / len(selected_assets))
                weights = {}
                for i, a_ in enumerate(selected_assets):
                    with wcols[i % len(wcols)]:
                        weights[a_] = st.number_input(f"{a_} (%)", value=default_w, min_value=0,
                                                       max_value=100, step=5, key=f"cp_w_{a_}")
                wsum = sum(weights.values())
                if wsum <= 0:
                    st.error("กรุณากำหนดสัดส่วนอย่างน้อย 1 เหรียญให้มากกว่า 0%")
                else:
                    norm_w = {k: v / wsum for k, v in weights.items()}
                    with st.spinner("กำลังโหลดราคาย้อนหลังของแต่ละเหรียญเพื่อคำนวณ correlation…"):
                        ret_map = {}
                        fail_list = []
                        for a_ in selected_assets:
                            d_, e_ = fetch_price_data(a_, start_date, end_date)
                            if d_.empty:
                                fail_list.append(a_)
                            else:
                                ret_map[a_] = np.log(d_["Global_USD"] / d_["Global_USD"].shift(1))
                    if fail_list:
                        st.warning(f"⚠️ โหลดข้อมูลไม่สำเร็จสำหรับ: {', '.join(fail_list)} — คำนวณจากเหรียญที่เหลือ")
                    if len(ret_map) == 0:
                        st.error("โหลดข้อมูลเหรียญในพอร์ตไม่สำเร็จเลยสักตัว")
                    else:
                        ret_df = pd.concat(ret_map, axis=1)
                        ret_df.columns = list(ret_map.keys())
                        ret_df = ret_df.dropna()
                        if len(ret_df) < 30:
                            st.error("ข้อมูลที่ overlap กันของทุกเหรียญมีน้อยกว่า 30 วัน — ลองลดจำนวนเหรียญหรือขยายช่วงเวลา")
                        else:
                            port_w = np.array([norm_w.get(c, 0) for c in ret_df.columns])
                            port_returns = (ret_df * port_w).sum(axis=1)
                            rp = _risk_stats(port_returns)
                            risk_label = " + ".join(f"{k} {norm_w[k]*100:.0f}%" for k in ret_df.columns)

                            if len(ret_df.columns) > 1:
                                with st.expander("🔗 Correlation Matrix ระหว่างเหรียญในพอร์ต", expanded=False):
                                    corr = ret_df.corr()
                                    fig_corr = go.Figure(go.Heatmap(
                                        z=corr.values, x=list(corr.columns), y=list(corr.columns),
                                        colorscale="RdYlGn", zmin=-1, zmax=1,
                                        texttemplate="%{z:.2f}", textfont={"size": 11}))
                                    fig_corr.update_layout(template="plotly_dark", height=320,
                                                           margin=dict(t=20, b=20))
                                    st.plotly_chart(fig_corr, **WIDE)
                                    st.caption("ยิ่งค่าใกล้ +1 = เคลื่อนไหวไปทางเดียวกัน (กระจายความเสี่ยงได้น้อย) "
                                               "ใกล้ -1 หรือ 0 = ช่วยกระจายความเสี่ยงของพอร์ตได้ดีกว่า")

        if rp is not None:
            usdthb_now = float(data["USDTHB"].iloc[-1]) if not data.empty else 35.5
            spot_usd = float(data["Global_USD"].iloc[-1]) if (not data.empty and cp_mode.startswith("Single")) else None

            section(f"📐 โปรไฟล์ความเสี่ยงจากข้อมูลจริง — {risk_label}")
            rk = st.columns(4)
            metric_card(rk[0], "Ann. Volatility", f"{rp['ann_vol']*100:.1f}%")
            metric_card(rk[1], "VaR 99% (1 วัน)", f"{rp['var99']*100:.2f}%")
            metric_card(rk[2], "Expected Shortfall 99%", f"{rp['es99']*100:.2f}%",
                        sub_text="ค่าเฉลี่ยของการขาดทุนใน 1% วันที่แย่ที่สุด")
            worst_dt = rp["worst_date"]
            worst_dt_str = worst_dt.strftime("%Y-%m-%d") if hasattr(worst_dt, "strftime") else str(worst_dt)
            metric_card(rk[3], "Worst Single Day", f"-{rp['worst']*100:.1f}%", sub_text=f"เกิดขึ้นเมื่อ {worst_dt_str}")

            st.caption("พารามิเตอร์ flow / งบดุล / เกณฑ์เงินกองทุน ย้ายไปอยู่ในแถบซ้ายแล้ว "
                       "(ใช้ค่าเดียวกับ Order Simulator ในแท็บ 3)")

            # ---------- CORE CALC ----------
            h_crypto = crypto_haircut(rp["es99"], settlement_days)
            h_cex = cex_counterparty_haircut if cex_margin_asset.startswith("Stablecoin") else h_crypto

            a_factor = safety_stock_factor(net_bias_pct, flow_cv_pct, settlement_days, z_alpha)
            required_stock_thb = a_factor * monthly_volume_thb

            nc = nc_snapshot(required_stock_thb, total_capital_thb, cex_margin_thb, liab_thb,
                             h_crypto, h_cex, fixed_min_nc, trading_risk_rate, daily_volume_thb,
                             custody_rate_blended)
            cash_after_stock_thb, nlc_thb = nc["cash"], nc["actual"]
            trading_service_risk_nc, custody_risk_nc = nc["trading_nc"], nc["custody_nc"]
            required_nc_total, nc_buffer_thb = nc["required"], nc["buffer"]
            ncr_pct = (nlc_thb / required_nc_total * 100.0) if required_nc_total > 0 else float("nan")

            hot_wallet_thb = required_stock_thb * hot_wallet_pct
            cold_wallet_thb = required_stock_thb * (1 - hot_wallet_pct)

            # ---------- MAX CAPACITY ----------
            slope = a_factor * (h_crypto + custody_rate_blended) + trading_risk_rate / 30.0
            if slope > 0:
                rhs = (total_capital_thb + cex_margin_thb * (1 - h_cex) - liab_thb - fixed_min_nc)
                v_nc_thb = max(0.0, rhs / slope)
            else:
                v_nc_thb = float("inf")
            v_cash_thb = (total_capital_thb / a_factor) if a_factor > 0 else float("inf")
            capital_max_v_thb = min(v_nc_thb, v_cash_thb)

            fx_max_v_thb = fx_limit_max * usdthb_now
            overall_max_v_thb = min(capital_max_v_thb, fx_max_v_thb)
            binding_side = "ทุน / NC" if capital_max_v_thb < fx_max_v_thb else "FX Limit"

            coin_price_thb = (spot_usd * usdthb_now) if spot_usd else None

            # ---------- SUMMARY VERDICT ----------
            section("🧾 สรุปผลสำหรับผู้บริหาร")
            ok_nc = (not pd.isna(nc_buffer_thb)) and (nc_buffer_thb >= 0)
            warn_nc = ok_nc and (ncr_pct < 150.0)
            verdict_box(
                ok_nc,
                f"NC จริง {fmt_baht(nlc_thb)} เทียบกับ NC ขั้นต่ำที่ต้องดำรง {fmt_baht(required_nc_total)} "
                f"→ {'ผ่านเกณฑ์' if ok_nc else 'ไม่ผ่านเกณฑ์'} (ส่วนเกิน/ขาด {fmt_baht(nc_buffer_thb, force_sign=True)})",
                f"NC ขั้นต่ำ = เงินกองทุนขั้นต่ำคงที่ {fmt_baht(fixed_min_nc)} + ความเสี่ยงบริการซื้อขาย "
                f"{fmt_baht(trading_service_risk_nc)} + ความเสี่ยงเก็บรักษาทรัพย์สิน {fmt_baht(custody_risk_nc)} "
                f"(ที่ปริมาณธุรกรรม {fmt_baht(monthly_volume_thb)}/เดือน ต้องดองสต็อกเหรียญ {fmt_baht(required_stock_thb)} "
                f"เหลือเงินสด {fmt_baht(cash_after_stock_thb)})"
                + (" — เงินสดติดลบ แปลว่าทุนไม่พอสำหรับปริมาณนี้!" if cash_after_stock_thb < 0 else ""),
                warn=warn_nc,
            )
            if hot_wallet_cap_breach:
                verdict_box(False, "ฝ่าฝืนเพดาน Hot Wallet 50%",
                           f"หนี้สินต่อลูกค้า {fmt_baht(liab_thb)} ต่ำกว่า 1,000 ล้านบาท "
                           f"แต่ตั้งสัดส่วน Hot Wallet ไว้ที่ {hot_wallet_pct*100:.0f}% (เกินเพดาน 50% ตามประกาศ)")
            cap_ok = monthly_volume_thb <= overall_max_v_thb
            verdict_box(
                cap_ok,
                f"เพดานธุรกรรมสูงสุดที่รับได้ ≈ {fmt_baht(overall_max_v_thb)}/เดือน (ติดที่: {binding_side})",
                f"ทุนรองรับได้ {fmt_baht(capital_max_v_thb)}/เดือน · FX Limit รองรับได้ {fmt_baht(fx_max_v_thb)}/เดือน"
                + (" — ปริมาณที่ตั้งไว้เกินเพดานแล้ว" if not cap_ok else " — ปริมาณที่ตั้งไว้ยังอยู่ในเพดาน"),
            )

            # ---------- KPI GRID ----------
            section("📊 รายละเอียดตัวเลข")
            k1 = st.columns(4)
            metric_card(k1[0], "Required Safety Stock", fmt_baht(required_stock_thb), None,
                        f"Haircut ที่ใช้ {h_crypto*100:.2f}%"
                        + (f" · ≈ {required_stock_thb/coin_price_thb:,.4f} {asset}" if coin_price_thb else ""))
            metric_card(k1[1], "เงินสดคงเหลือหลังจัดสรร", fmt_baht(cash_after_stock_thb), cash_after_stock_thb)
            metric_card(k1[2], "Net Capital (NC) จริง", fmt_baht(nlc_thb), nlc_thb)
            metric_card(k1[3], "NC ขั้นต่ำที่ต้องดำรง", fmt_baht(required_nc_total), nc_buffer_thb,
                        f"ส่วนเกิน/ขาด {fmt_baht(nc_buffer_thb, force_sign=True)} ({ncr_pct:.0f}% ของ NC ขั้นต่ำ)"
                        if not pd.isna(ncr_pct) else None)

            k2 = st.columns(4)
            metric_card(k2[0], "เงินกองทุนขั้นต่ำคงที่", fmt_baht(fixed_min_nc))
            metric_card(k2[1], "NC ความเสี่ยงบริการซื้อขาย", fmt_baht(trading_service_risk_nc),
                        sub_text=f"= {trading_risk_rate*100:.1f}% × มูลค่าซื้อขายเฉลี่ย/วัน")
            metric_card(k2[2], "NC ความเสี่ยงเก็บรักษาทรัพย์สิน", fmt_baht(custody_risk_nc),
                        sub_text=f"Hot {fmt_baht(hot_wallet_thb)} × {HOT_WALLET_NC_RATE*100:.0f}% + "
                                  f"Cold {fmt_baht(cold_wallet_thb)} × ~{(cold_domestic_split_pct*COLD_DOMESTIC_NC_RATE+(1-cold_domestic_split_pct)*cold_foreign_rate)*100:.2f}%")
            metric_card(k2[3], "เพดานฝั่ง FX Limit", fmt_baht(fx_max_v_thb),
                        sub_text=f"FX Limit {fx_limit_max:,.0f} USD × {usdthb_now:.2f}")

            k3 = st.columns(4)
            metric_card(k3[0], "Haircut คริปโต (h)", f"{h_crypto*100:.2f}%", sub_text=f"= ES99% × √{settlement_days} วัน")
            metric_card(k3[1], "Haircut CEX Margin", f"{h_cex*100:.2f}%")
            metric_card(k3[2], "เพดานฝั่งทุน/NC", fmt_baht(capital_max_v_thb))
            metric_card(k3[3], "สถานะ Hot Wallet Cap", "ฝ่าฝืน 🚨" if hot_wallet_cap_breach else "ปกติ ✅",
                        sub_text="เพดาน 50% ใช้เมื่อทรัพย์สินลูกค้ารวม < 1,000 ล้านบาท")

            with st.expander("📐 สูตรที่ใช้คำนวณ (สำหรับอ้างอิงในห้องประชุม)"):
                st.markdown(f"""
**Safety Stock** (สต็อกเหรียญที่ต้องดำรงไว้):
`I* = max(0, net_bias) × V/30 × L + z_α × (CV × V/30) × √L`

**Net Capital (NC) จริง — ประมาณจากงบดุลสภาพคล่อง:**
`NC_actual = Cash + I×(1−h_crypto) + M×(1−h_CEX) − L_liab`

**NC ขั้นต่ำที่ต้องดำรง (ตามประกาศ ก.ล.ต.):**
`NC_required = Fixed_Min_NC + (trading_risk_rate × Daily_Volume) + Custody_Risk_NC`
`Custody_Risk_NC = Hot×100% + Cold_domestic×1% + Cold_foreign×{cold_foreign_rate*100:.1f}%`
เกณฑ์ผ่าน: **NC_actual ≥ NC_required**

**Haircut จากข้อมูลจริง (ไม่ใช่เลขเดา):**
`h_crypto = ES99% × √L` (capped ที่ 95%)

**เพดานธุรกรรมสูงสุด:**
`V_max = min( [Capital + M(1−h_CEX) − L_liab − Fixed_Min_NC] / [a×(h_crypto+blended_custody_rate) + trading_risk_rate/30],  Capital/a,  FX_Limit×USDTHB )`
โดย `a = [max(0,net_bias)×L + z_α×CV×√L] / 30`, `blended_custody_rate = {custody_rate_blended*100:.3f}%`

ค่าที่ใช้ตอนนี้: L = {settlement_days} วัน, z_α = {z_alpha:.3f} ({confidence}%),
CV = {flow_cv_pct*100:.0f}%, net_bias = {net_bias_pct*100:+.0f}%, h_crypto = {h_crypto*100:.2f}%
                """)

            # ---------- HISTORICAL REPLAY ----------
            section("📼 Historical Replay — ย้อนดูว่าจะหลุดเกณฑ์กี่วันจริง")
            st.caption("นำ log-return รายวันจริงทั้งช่วงที่เลือกในแถบซ้าย มา shock ใส่สต็อกที่คำนวณได้ "
                       "(Historical Simulation) โดยคงเงินสด/CEX Margin/หนี้สินคงที่ตามที่ตั้งไว้")

            hist_returns = rp["returns"]
            crypto_val_series = required_stock_thb * np.exp(hist_returns)
            nlc_series = cash_after_stock_thb + crypto_val_series + cex_margin_thb - liab_thb
            custody_nc_series = crypto_val_series * custody_rate_blended
            required_nc_series = fixed_min_nc + trading_service_risk_nc + custody_nc_series
            nc_buffer_series = nlc_series - required_nc_series
            breach_mask = nc_buffer_series < 0
            breach_days = int(breach_mask.sum())
            breach_pct = breach_days / len(nc_buffer_series) * 100.0 if len(nc_buffer_series) else 0.0

            hr = st.columns(3)
            metric_card(hr[0], "จำนวนวันในประวัติศาสตร์ที่ทดสอบ", f"{len(nc_buffer_series):,} วัน")
            metric_card(hr[1], "วันที่ NC จะหลุดเกณฑ์ขั้นต่ำ", f"{breach_days:,} วัน",
                        -1 if breach_days else 0, f"{breach_pct:.2f}% ของวันทั้งหมด")
            metric_card(hr[2], "NC Buffer ต่ำสุดในประวัติศาสตร์ (จำลอง)",
                        fmt_baht(nc_buffer_series.min()) if len(nc_buffer_series) else "N/A",
                        nc_buffer_series.min() if len(nc_buffer_series) else None)

            if len(nc_buffer_series):
                fig_replay = go.Figure()
                fig_replay.add_trace(go.Scatter(x=nc_buffer_series.index, y=nc_buffer_series.values,
                                                name="NC Buffer (จำลองย้อนหลัง)",
                                                line=dict(color="#00D26A", width=1.6)))
                fig_replay.add_hline(y=0, line=dict(color="#FF4B4B", dash="dash"),
                                     annotation_text="เกณฑ์ขั้นต่ำ (NC Buffer = 0)")
                if breach_mask.any():
                    bd = nc_buffer_series[breach_mask]
                    fig_replay.add_trace(go.Scatter(x=bd.index, y=bd.values, mode="markers",
                                                    name="หลุดเกณฑ์", marker=dict(color="#FF4B4B", size=5, symbol="x")))
                fig_replay.update_layout(template="plotly_dark", height=420, hovermode="x unified",
                                         margin=dict(t=30, b=20), yaxis_title="NC Buffer (THB)",
                                         legend=dict(orientation="h", y=1.05, yanchor="bottom"))
                st.plotly_chart(fig_replay, **WIDE)

            # ---------- STRESS TEST ----------
            section("🧨 Stress Test — 6 สถานการณ์")

            def _scenario_nc_buffer(crypto_val, extra_haircut_mult=1.0, extra_stock=0.0):
                h_eff = min(h_crypto * extra_haircut_mult, 0.99)
                cv = crypto_val + extra_stock
                nlc_s = cash_after_stock_thb + cv * (1 - h_eff) + cex_margin_thb * (1 - h_cex) - liab_thb
                required_s = fixed_min_nc + trading_service_risk_nc + cv * custody_rate_blended
                return nlc_s - required_s

            extra_flow = daily_volume_thb * 3.0
            fx_stuck = min(monthly_volume_thb, fx_max_v_thb) * 0.5

            scenarios = [
                ("ราคาร่วง -10% ใน 1 วัน", _scenario_nc_buffer(required_stock_thb * 0.90)),
                ("ราคาร่วง -20% ใน 1 วัน", _scenario_nc_buffer(required_stock_thb * 0.80)),
                ("Worst Historical Day จริง", _scenario_nc_buffer(required_stock_thb * (1 - rp["worst"]))),
                ("Bank Run: ลูกค้าเทขาย 3× ปริมาณเฉลี่ย/วัน", _scenario_nc_buffer(required_stock_thb, extra_stock=extra_flow)),
                ("FX Limit ถูกตัดเหลือครึ่งหนึ่ง (โอนออกไม่ทัน)", _scenario_nc_buffer(required_stock_thb, extra_stock=fx_stuck)),
                ("Liquidity Crisis: Worst Day + Haircut เพิ่มเป็น 2×",
                 _scenario_nc_buffer(required_stock_thb * (1 - rp["worst"]), extra_haircut_mult=2.0)),
            ]

            sc_cols = st.columns(2)
            for i, (label, buf_s) in enumerate(scenarios):
                with sc_cols[i % 2]:
                    ok_s = (not pd.isna(buf_s)) and (buf_s >= 0)
                    warn_s = ok_s and (buf_s < 0.5 * required_nc_total)
                    verdict_box(ok_s,
                               f"{label} → NC Buffer {fmt_baht(buf_s, force_sign=True)}" if not pd.isna(buf_s) else f"{label} → N/A",
                               f"เกณฑ์ผ่าน: NC จริง ≥ NC ขั้นต่ำที่ต้องดำรง ({fmt_baht(required_nc_total)})", warn=warn_s)

            st.caption("Stress Test ใช้เงินสด/CEX Margin/หนี้สินคงที่ตามที่ตั้งไว้ แล้วช็อกเฉพาะฝั่งสต็อกเหรียญ/haircut "
                       "และคำนวณ NC ขั้นต่ำใหม่ตามมูลค่าคริปโตที่ถืออยู่จริงในแต่ละสถานการณ์")


# ---------------------------------------------------------
# TAB 3 — CUSTOMER ORDER SIMULATOR
# ---------------------------------------------------------

def _sim_defaults(asset_name, spot_usd, usdthb, target_stock_thb):
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
    }

def _sim_config_signature(ctx, target_stock_thb):
    keys = [
        "asset", "spot_usd", "usdthb", "local_premium", "spread", "hedge_fee",
        "fx_limit", "daily_vol", "slip_sens", "include_fee_rev",
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
    return tuple(values)

def _sim_normalize_state(sim, asset, spot_usd, usdthb, target_stock_thb):
    if not isinstance(sim, dict):
        return _sim_defaults(asset, spot_usd, usdthb, target_stock_thb)

    sim.setdefault("asset", asset)
    sim.setdefault("target_thb", target_stock_thb)
    sim.setdefault("fx_used_usd", 0.0)
    sim.setdefault("cex_used_thb", 0.0)
    sim.setdefault("pnl_thb", 0.0)
    sim.setdefault("unhedged_thb", 0.0)
    sim.setdefault("orders", [])

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

def execute_order(sim, side, amount_thb, ctx):
    p = ctx
    side = "buy" if side == "buy" else "sell"

    try:
        amount_thb = float(amount_thb)
    except (TypeError, ValueError):
        amount_thb = 0.0

    spot = float(p["spot_usd"])
    fx = float(p["usdthb"])
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

    # 1) Quote
    steps.append(dict(
        n=1, t="ตั้งราคาให้ลูกค้า", s="pass",
        note="ราคาลูกค้าถูกประกอบจาก Global Reference + Local Premium + Dealer Spread",
        rows=[
            ("ราคาโลก (USD)", f"$ {spot:,.2f}"),
            ("× อัตราแลกเปลี่ยน USD/THB", f"{fx:,.2f}"),
            (f"+ Local Premium {p['local_premium']*100:.2f}%", f"฿ {mid:,.2f}"),
            (f"{'+' if side == 'buy' else '−'} Dealer Spread {p['spread']*100:.2f}%", f"฿ {quote:,.2f}"),
        ],
        total=("ราคาที่ลูกค้าได้", f"฿ {quote:,.2f}"),
    ))

    # 2) Customer settlement
    trading_fee = amount_thb * LOCAL_TRADING_FEE_PCT
    settlement_thb = max(0.0, amount_thb - trading_fee)
    coins = settlement_thb / quote

    if coins <= 0:
        steps.append(dict(n=2, t="จับคู่และส่งมอบ", s="block", note="จำนวนเหรียญที่คำนวณได้ไม่เป็นบวก"))
        return steps, None

    inv_before = float(sim["inv_coins"])
    target_coins = float(sim["target_thb"]) / coin_price_global if coin_price_global > 0 else 0.0
    inv_after_customer = inv_before - coins if side == "buy" else inv_before + coins

    # ---------- Pre-check Buy: ต้องไม่ส่งมอบของที่ไม่มี ----------
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
                "ฝั่ง": "ซื้อ", "เหรียญ": sim["asset"], "มูลค่า (บาท)": amount_thb, "ราคาที่ลูกค้าได้": quote,
                "เหรียญที่ส่งมอบ": 0.0, "Hedge (เหรียญ)": 0.0, "Hedge (USD)": 0.0, "CEX Liquidity ใช้ (บาท)": 0.0,
                "Unhedged (บาท)": 0.0, "Market Edge": 0.0, "รายได้": 0.0, "ต้นทุน": 0.0, "กำไรออเดอร์": 0.0,
                "สต็อกคงเหลือ": inv_before, "FX ใช้สะสม (USD)": sim["fx_used_usd"],
                "CEX Liquidity ใช้สะสม (บาท)": sim["cex_used_thb"], "NC Buffer": np.nan,
                "ผลด่าน": "Reject — Inventory/FX ไม่พอ",
            }

    steps.append(dict(
        n=2, t="จับคู่และส่งมอบเข้ากระเป๋า", s="pass",
        note=("ลูกค้าชำระเงินบาทและได้รับเหรียญจาก inventory" if side == "buy" else "รับเหรียญจากลูกค้าและจ่ายเงินบาทตามราคาที่ quote"),
        rows=[
            ("มูลค่าที่ลูกค้าใส่", fmt_baht(amount_thb)),
            (f"ค่าธรรมเนียมซื้อขาย {LOCAL_TRADING_FEE_PCT*100:.2f}%", "− " + fmt_baht(trading_fee)),
            ("ฐาน settlement หลังค่าธรรมเนียม", fmt_baht(settlement_thb)),
        ],
        total=("เหรียญที่ลูกค้าได้" if side == "buy" else "เหรียญที่ลูกค้าส่งมอบ", fmt_coin(coins, sim["asset"])),
    ))

    # 3) Inventory movement
    sim["inv_coins"] = inv_after_customer
    short_coins = max(0.0, target_coins - sim["inv_coins"])
    excess_coins = max(0.0, sim["inv_coins"] - target_coins)

    steps.append(dict(
        n=3, t="ตัด/รับสต็อก", s="warn" if (short_coins > 0 or excess_coins > 0) else "pass",
        note=("Buy ลด inventory ก่อน แล้วค่อยเติมกลับด้วย hedge" if side == "buy" else "Sell เพิ่ม inventory ก่อน แล้วค่อยขายส่วนเกินบน CEX"),
        rows=[
            ("สต็อกก่อนออเดอร์", fmt_coin(inv_before, sim["asset"])),
            ("การเปลี่ยนแปลง", ("− " if side == "buy" else "+ ") + fmt_coin(coins, sim["asset"])),
            ("สต็อกหลังรับ/ส่งมอบ", fmt_coin(sim["inv_coins"], sim["asset"])),
            ("Target Stock", fmt_coin(target_coins, sim["asset"])),
            ("Short / Excess", fmt_coin(short_coins if side == "buy" else excess_coins, sim["asset"])),
        ],
        total=("มูลค่าสต็อกปัจจุบัน", fmt_baht(max(0.0, sim["inv_coins"]) * coin_price_global)),
    ))

    # 4) Hedge decision
    hedge_required_coins = short_coins if side == "buy" else excess_coins
    hedge_required_thb = hedge_required_coins * coin_price_global
    hedged_coins = 0.0
    residual_unhedged_coins = 0.0

    if side == "buy":
        fx_left_usd = max(0.0, float(p["fx_limit"]) - float(sim["fx_used_usd"]))
        max_hedge_by_fx = (fx_left_usd / (spot * (1 + p["hedge_fee"])) if spot > 0 and p["hedge_fee"] >= 0 else 0.0)
        hedged_coins = min(hedge_required_coins, max_hedge_by_fx)
        residual_unhedged_coins = max(0.0, hedge_required_coins - hedged_coins)
        hedge_usd = hedged_coins * spot * (1 + p["hedge_fee"])
        sim["fx_used_usd"] += hedge_usd

        if hedge_required_coins > 0:
            sim["inv_coins"] += hedged_coins
        sim["unhedged_thb"] += residual_unhedged_coins * coin_price_global

        fx_status = "pass" if residual_unhedged_coins <= 1e-12 else "warn"
        hedge_status = "pass" if residual_unhedged_coins <= 1e-12 else "warn"
        hedge_note = ("เติม inventory กลับถึง target ด้วยการซื้อบน Global CEX" if residual_unhedged_coins <= 1e-12 else "FX quota ไม่พอสำหรับเติม inventory ทั้งหมด จึงเหลือ exposure ค้างบางส่วน")
        cex_used_thb_this_order = 0.0
        cex_liquidity_left = max(0.0, float(p["cex_liquidity_thb"]) - float(sim["cex_used_thb"]))
    else:
        cex_liquidity_left = max(0.0, float(p["cex_liquidity_thb"]) - float(sim["cex_used_thb"]))
        max_hedge_by_cex = cex_liquidity_left / coin_price_global if coin_price_global > 0 else 0.0
        hedged_coins = min(hedge_required_coins, max_hedge_by_cex)
        residual_unhedged_coins = max(0.0, hedge_required_coins - hedged_coins)
        cex_used_thb_this_order = hedged_coins * coin_price_global
        sim["cex_used_thb"] += cex_used_thb_this_order
        sim["inv_coins"] -= hedged_coins
        sim["unhedged_thb"] += residual_unhedged_coins * coin_price_global

        fx_status = "pass"
        hedge_status = "pass" if residual_unhedged_coins <= 1e-12 else "warn"
        hedge_note = ("ขาย inventory ส่วนเกินบน Global CEX โดยใช้ CEX liquidity" if residual_unhedged_coins <= 1e-12 else "CEX liquidity ไม่พอขาย inventory ส่วนเกินทั้งหมด จึงเหลือ long exposure ค้าง")
        fx_left_usd = max(0.0, float(p["fx_limit"]) - float(sim["fx_used_usd"]))

    hedge_thb = hedged_coins * coin_price_global
    hedge_usd = hedged_coins * spot * (1 + p["hedge_fee"])
    steps.append(dict(
        n=4, t="ระบบตัดสินใจ Hedge อัตโนมัติ", s=hedge_status, note=hedge_note,
        rows=[
            ("ปริมาณที่ต้อง hedge", fmt_coin(hedge_required_coins, sim["asset"])),
            ("Hedge สำเร็จ", fmt_coin(hedged_coins, sim["asset"])),
            ("มูลค่า hedge", f"{fmt_baht(hedge_thb)}"),
            ("Residual Unhedged", fmt_coin(residual_unhedged_coins, sim["asset"])),
            ("Direction", "Buy บน CEX" if side == "buy" else "Sell บน CEX"),
        ],
        total=("สถานะ", "Hedge ครบ" if residual_unhedged_coins <= 1e-12 else "Hedge บางส่วน"),
    ))

    # 5) FX / CEX liquidity gate
    if side == "buy":
        steps.append(dict(
            n=5, t="ด่าน FX Limit — Outbound", s=fx_status,
            note=("Buy-side hedge ใช้ outbound FX quota" if residual_unhedged_coins <= 1e-12 else "โควตา outbound เหลือไม่พอ จึงเหลือ inventory exposure ที่ยังไม่ได้ hedge"),
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
            n=5, t="ด่าน CEX Liquidity — Sell-side", s=fx_status if residual_unhedged_coins <= 1e-12 else "warn",
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

    # 6) NC gate
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
        note=("NC/Capital เป็น planning model; ไม่ใช่ตัวรับรอง compliance อัตโนมัติ" if nc_status != "pass" else "หลังออเดอร์ยังมี NC buffer เป็นบวกตาม planning model"),
        rows=[
            ("สต็อกหลัง hedge", fmt_baht(stock_thb)),
            ("Cash ใน NC Model", fmt_baht(nc["cash"])),
            ("CEX Margin หลัง haircut", fmt_baht(p["cex_margin"] * (1 - p["h_cex"]))),
            ("NC ที่มีจริง", fmt_baht(nc["actual"])),
            ("NC ขั้นต่ำที่ต้องดำรง", fmt_baht(nc["required"])),
        ],
        total=("NC Buffer", fmt_baht(nc["buffer"], force_sign=True)),
    ))

    # 7) P&L
    market_edge = (coins * (quote - coin_price_global) if side == "buy" else coins * (coin_price_global - quote))
    fee_rev = trading_fee if p["include_fee_rev"] else 0.0

    wd_markup_rev = 0.0
    if side == "buy":
        wd_markup_rev = (p["wd_fee_per_coin"] * coins * coin_price_global + calc_thb_withdrawal_fee(amount_thb, p["bank_type"], p["ktb_wd_fee"])) * p["wd_markup"]

    ktb_fx_benefit = hedge_thb * (p["ktb_fx_bps"] / 10000.0) if hedged_coins > 0 else 0.0
    hedge_fee_cost = hedge_thb * p["hedge_fee"] if hedged_coins > 0 else 0.0
    slippage_cost = hedge_thb * p["daily_vol"] * p["slip_sens"] if hedged_coins > 0 else 0.0

    revenue = market_edge + fee_rev + wd_markup_rev + ktb_fx_benefit
    cost = hedge_fee_cost + slippage_cost
    net = revenue - cost
    sim["pnl_thb"] += net

    pnl_rows = [
        ("Market Edge จาก Quote vs Global", ("+ " if market_edge >= 0 else "− ") + fmt_baht(abs(market_edge))),
        ("ค่าธรรมเนียมซื้อขาย", "+ " + fmt_baht(fee_rev)),
        ("Markup ค่าธรรมเนียมถอน", "+ " + fmt_baht(wd_markup_rev)),
        ("KTB FX Benefit", "+ " + fmt_baht(ktb_fx_benefit)),
        ("ค่าธรรมเนียม CEX", "− " + fmt_baht(hedge_fee_cost)),
        ("Slippage", "− " + fmt_baht(slippage_cost)),
    ]

    steps.append(dict(
        n=7, t="กำไรขาดทุนของ Dealer ในออเดอร์นี้", s="pass" if net >= 0 else "warn",
        note=("P&L มาจาก realized quote-vs-global edge + fee หักต้นทุน hedge/slippage" if side == "buy" else "Sell-side P&L สะท้อนส่วนต่างระหว่างราคาที่รับซื้อจากลูกค้ากับราคาที่ขายต่อบน Global CEX"),
        rows=pnl_rows,
        total=("กำไรสุทธิ", f"{fmt_baht(net, force_sign=True)} ({net/amount_thb*10000:,.1f} bps)"),
    ))

    record = {
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
        "ผลด่าน": ("ผ่าน" if nc_status == "pass" and residual_unhedged_coins <= 1e-12 else ("เฝ้าระวัง" if nc_status != "block" else "NC ไม่พอ")),
    }
    sim["orders"].append(record)
    return steps, record


with tab3:
    st.markdown("""
**"ถ้ากูเป็นลูกค้าเดินเข้ามาซื้อเหรียญ ระบบทำงานยังไง"** — ใส่ออเดอร์เหมือนเป็นลูกค้า
แล้วดูหลังบ้านเดินทีละด่าน: ตั้งราคา → ตัด/รับสต็อก → ตัดสินใจ hedge
→ FX/CEX Liquidity → NC Planning Model → กำไรจริงของออเดอร์นั้น

สต็อก โควตา FX, CEX liquidity และกำไรสะสม **ต่อเนื่องข้ามออเดอร์**
ยิงหลาย ๆ ครั้งแล้วจะเห็นว่าอะไรตึงก่อนกัน
    """)

    if data.empty:
        st.error(f"⚠️ ต้องโหลดราคาจริงก่อนถึงจะจำลองได้: {data_err or 'ไม่สามารถโหลดข้อมูลได้'}")
    else:
        rp_sim = risk_profile(data["Global_USD"])
        if rp_sim is None:
            st.error("ข้อมูลย้อนหลังน้อยกว่า 30 วัน — เลือกช่วงเวลายาวขึ้นในแถบซ้าย "
                     "(ต้องใช้คำนวณ Expected Shortfall สำหรับ haircut)")
        else:
            spot_usd_now = float(data["Global_USD"].iloc[-1])
            usdthb_now_sim = float(data["USDTHB"].iloc[-1])
            daily_vol_now = float(data["Volatility_Pct"].tail(30).mean())
            h_crypto_sim = crypto_haircut(rp_sim["es99"], settlement_days)
            h_cex_sim = cex_counterparty_haircut if cex_margin_asset.startswith("Stablecoin") else h_crypto_sim
            a_factor_sim = safety_stock_factor(net_bias_pct, flow_cv_pct, settlement_days, z_alpha)
            target_stock_thb = a_factor_sim * monthly_volume_thb

            cex_liquidity_thb = max(0.0, float(cex_margin_thb))

            ctx = dict(
                asset=asset, spot_usd=spot_usd_now, usdthb=usdthb_now_sim, local_premium=local_premium,
                spread=dealer_spread, hedge_fee=hedge_fee, fx_limit=fx_limit_max, daily_vol=daily_vol_now,
                slip_sens=slippage_sensitivity, include_fee_rev=include_trading_fee_revenue,
                wd_markup=withdrawal_fee_markup_pct, wd_fee_per_coin=WITHDRAWAL_FEE_TABLE.get(asset, 0.0),
                bank_type=bank_type, ktb_wd_fee=ktb_wd_fee_thb, ktb_fx_bps=(ktb_fx_spread_bps if use_ktb_fx else 0.0),
                capital=total_capital_thb, cex_margin=cex_margin_thb, cex_liquidity_thb=cex_liquidity_thb,
                liab=liab_thb, h_crypto=h_crypto_sim, h_cex=h_cex_sim, fixed_min_nc=fixed_min_nc,
                trading_risk_rate=trading_risk_rate, daily_volume_thb=daily_volume_thb,
                custody_rate=custody_rate_blended, hot_breach=hot_wallet_cap_breach,
            )

            # ---------- STATE ----------
            sim_signature = _sim_config_signature(ctx, target_stock_thb)
            need_reset = (
                "sim" not in st.session_state
                or st.session_state.get("sim_signature") != sim_signature
            )

            if need_reset:
                st.session_state.sim = _sim_defaults(asset, spot_usd_now, usdthb_now_sim, target_stock_thb)
                st.session_state.sim_signature = sim_signature
                st.session_state.sim_steps = []

            sim = _sim_normalize_state(st.session_state.sim, asset, spot_usd_now, usdthb_now_sim, target_stock_thb)
            st.session_state.sim = sim

            coin_price_thb_now = spot_usd_now * usdthb_now_sim
            stock_thb_now = max(0.0, sim["inv_coins"]) * coin_price_thb_now
            nc_now = nc_snapshot(
                stock_thb_now, total_capital_thb, cex_margin_thb, liab_thb,
                h_crypto_sim, h_cex_sim, fixed_min_nc, trading_risk_rate,
                daily_volume_thb, custody_rate_blended,
            )

            section("📟 สถานะระบบตอนนี้")
            s1 = st.columns(4)
            stock_ratio = (stock_thb_now / target_stock_thb * 100) if target_stock_thb > 0 else 0
            metric_card(
                s1[0], f"สต็อก {asset} คงเหลือ", fmt_coin(sim["inv_coins"], asset),
                sim["inv_coins"],
                f"{fmt_baht(stock_thb_now)} · {stock_ratio:.0f}% ของเป้า {fmt_baht(target_stock_thb)}",
            )
            fx_left = max(0.0, fx_limit_max - sim["fx_used_usd"])
            metric_card(
                s1[1], "โควตา Outbound FX ที่ใช้", f"$ {sim['fx_used_usd']:,.0f}",
                fx_left,
                f"เหลือ $ {fx_left:,.0f} จาก $ {fx_limit_max:,.0f}",
            )
            metric_card(
                s1[2], "CEX Liquidity ที่ใช้", fmt_baht(sim["cex_used_thb"]),
                max(0.0, cex_liquidity_thb - sim["cex_used_thb"]),
                f"เหลือ {fmt_baht(max(0.0, cex_liquidity_thb - sim['cex_used_thb']))} จาก {fmt_baht(cex_liquidity_thb)}",
            )
            metric_card(
                s1[3], "กำไรสะสมของ Dealer", fmt_baht(sim["pnl_thb"], True), sim["pnl_thb"],
                (f"{len(sim['orders'])} ออเดอร์ · เฉลี่ย {fmt_baht(sim['pnl_thb']/len(sim['orders']), True)}/ออเดอร์"
                 if sim["orders"] else "ยังไม่มีออเดอร์"),
            )

            g_cols = st.columns(3)
            with g_cols[0]:
                gauge_bar("โควตา Outbound FX",
                          sim["fx_used_usd"], fx_limit_max,
                          value_text=f"{sim['fx_used_usd']/fx_limit_max*100:.0f}%" if fx_limit_max > 0 else "N/A",
                          sub=f"ใช้ $ {sim['fx_used_usd']:,.0f} / $ {fx_limit_max:,.0f}")
            with g_cols[1]:
                gauge_bar("CEX Liquidity",
                          sim["cex_used_thb"], cex_liquidity_thb,
                          value_text=f"{sim['cex_used_thb']/cex_liquidity_thb*100:.0f}%" if cex_liquidity_thb > 0 else "N/A",
                          sub=f"ใช้ {fmt_baht(sim['cex_used_thb'])} / {fmt_baht(cex_liquidity_thb)}")
            with g_cols[2]:
                nc_use = (nc_now["required"] / nc_now["actual"]) if nc_now["actual"] > 0 else 9.99
                gauge_bar("NC Utilization (NC ขั้นต่ำ ÷ NC จริง)",
                          nc_now["required"], max(nc_now["actual"], 0.0),
                          value_text=f"{nc_use*100:.0f}%" if nc_use < 9 else "เกิน 100%",
                          sub=f"Buffer {fmt_baht(nc_now['buffer'], True)}",
                          warn_at=2/3, crit_at=1.0)

            if sim["unhedged_thb"] > 0:
                verdict_box(
                    False, f"มี Unhedged Exposure สะสม {fmt_baht(sim['unhedged_thb'])}",
                    "เกิดจาก Buy-side FX quota หรือ Sell-side CEX liquidity ไม่พอ จึงยังมี inventory exposure ที่ยังไม่ได้ปิด",
                )

            if nc_now["buffer"] < 0:
                verdict_box(
                    False, "NC Buffer ติดลบใน Planning Model",
                    "หลังสถานะปัจจุบัน NC ต่ำกว่า NC ขั้นต่ำที่คำนวณไว้ ไม่ได้หมายความว่าเป็นการรับรอง/วินิจฉัย compliance อัตโนมัติ",
                )

            # ---------- ORDER TICKET ----------
            left, right = st.columns([1, 2], gap="large")

            with left:
                section("🧑‍💻 หน้าจอลูกค้า")
                with st.container(border=True):
                    order_side = st.radio("ฝั่ง", ["ซื้อ", "ขาย"], horizontal=True, key="sim_side")
                    side_key = "buy" if order_side == "ซื้อ" else "sell"
                    order_amt = comma_number_input(
                        "มูลค่า (บาท)", value=500_000, min_value=0, key="sim_amount",
                        help="Gross order notional ที่ลูกค้าระบุ; ค่าธรรมเนียม 0.25% ถูกหักแยกในขั้น settlement",
                    )
                    mid_now = coin_price_thb_now * (1 + local_premium)
                    quote_now = mid_now * (1 + dealer_spread) if side_key == "buy" else mid_now * (1 - dealer_spread)
                    st.caption(
                        f"ราคาที่ลูกค้าเห็นตอนนี้: **฿ {quote_now:,.2f}** / {asset} "
                        f"(ราคาโลก $ {spot_usd_now:,.2f} × {usdthb_now_sim:,.2f} "
                        f"+ premium {local_premium*100:.2f}% "
                        f"{'+' if side_key=='buy' else '−'} spread {dealer_spread*100:.2f}%)"
                    )
                    st.caption(
                        f"ประมาณ {fmt_coin(order_amt*(1-LOCAL_TRADING_FEE_PCT)/quote_now, asset)} "
                        f"หลังหักค่าธรรมเนียม {LOCAL_TRADING_FEE_PCT*100:.2f}%"
                    )
                    send = st.button("📤 ส่งคำสั่ง", type="primary", **WIDE)

                with st.expander("🤖 เครื่องมือสุ่มออเดอร์อัตโนมัติ", expanded=False):
                    st.caption("สุ่มออเดอร์ตาม Flow Assumptions ในแถบซ้าย เพื่อดูว่าอะไรตึงก่อนเมื่อมีออเดอร์หลายรายการ")
                    n_orders = st.number_input(
                        "จำนวนออเดอร์ที่จะสุ่ม", value=20, min_value=1,
                        max_value=500, step=10, key="sim_n"
                    )
                    seed = st.number_input("Random seed", value=42, step=1, key="sim_seed")
                    run_day = st.button("🎲 จำลองทั้งวัน", **WIDE)
                reset = st.button("♻️ เริ่มวันใหม่ (ล้างสถานะ)", **WIDE)

                if reset:
                    st.session_state.sim = _sim_defaults(asset, spot_usd_now, usdthb_now_sim, target_stock_thb)
                    st.session_state.sim_signature = sim_signature
                    st.session_state.sim_steps = []
                    st.rerun()

                if send:
                    steps, _ = execute_order(sim, side_key, float(order_amt), ctx)
                    st.session_state.sim_steps = steps
                    st.rerun()

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
                    st.rerun()

            with right:
                section("🔎 เส้นทางหลังบ้านของออเดอร์ล่าสุด")
                steps_now = st.session_state.get("sim_steps", [])
                if not steps_now:
                    st.info("ยังไม่มีออเดอร์ — กด **ส่งคำสั่ง** ทางซ้ายเพื่อดูระบบเดินงานทีละด่าน")
                else:
                    render_timeline(steps_now)

            # ---------- LEDGER + CHARTS ----------
            if sim["orders"]:
                section("📒 สมุดออเดอร์")
                led = pd.DataFrame(sim["orders"])
                led.index = range(1, len(led) + 1)
                led.index.name = "#"

                lc = st.columns(4)
                buys = int((led["ฝั่ง"] == "ซื้อ").sum())
                blocked = int((led["ผลด่าน"] != "ผ่าน").sum())
                metric_card(
                    lc[0], "จำนวนออเดอร์", f"{len(led):,}", None,
                    f"ซื้อ {buys} · ขาย {len(led)-buys}",
                )
                metric_card(
                    lc[1], "Notional รวม", fmt_baht(led["มูลค่า (บาท)"].sum()), None,
                    "มูลค่าธุรกรรมรวม (ไม่ใช่กำไร)",
                )
                total_notional = led["มูลค่า (บาท)"].sum()
                margin_bps = led["กำไรออเดอร์"].sum() / total_notional * 10000 if total_notional else 0.0
                metric_card(
                    lc[2], "มาร์จิ้นเฉลี่ย", f"{margin_bps:,.1f} bps",
                    led["กำไรออเดอร์"].sum(),
                    "P&L รวม ÷ Notional รวม",
                )
                metric_card(
                    lc[3], "ออเดอร์ที่ต้องเฝ้าระวัง/ติดด่าน", f"{blocked:,}",
                    -1 if blocked else 0,
                    f"{blocked/len(led)*100:.1f}% ของทั้งหมด",
                )

                g1, g2 = st.columns(2)
                with g1:
                    fig_pnl = go.Figure()
                    fig_pnl.add_trace(go.Scatter(
                        y=led["กำไรออเดอร์"].cumsum(), x=led.index,
                        name="กำไรสะสม", line=dict(color="#00D26A", width=2),
                        fill="tozeroy", fillcolor="rgba(0,210,106,.12)",
                    ))
                    fig_pnl.update_layout(
                        template="plotly_dark", height=320, margin=dict(t=40, b=20),
                        title="กำไรสะสมรายออเดอร์", xaxis_title="ออเดอร์ที่",
                        yaxis_title="THB", showlegend=False,
                    )
                    st.plotly_chart(fig_pnl, **WIDE)

                with g2:
                    fig_gate = go.Figure()
                    fig_gate.add_trace(go.Scatter(
                        y=led["FX ใช้สะสม (USD)"], x=led.index,
                        name="FX ใช้สะสม", line=dict(color="#3B82F6", width=2),
                    ))
                    fig_gate.add_hline(
                        y=fx_limit_max, line=dict(color="#FF4B4B", dash="dash"),
                        annotation_text="เพดาน FX Limit",
                    )
                    fig_gate.update_layout(
                        template="plotly_dark", height=320, margin=dict(t=40, b=20),
                        title="โควตา Outbound FX ที่ใช้ไป", xaxis_title="ออเดอร์ที่",
                        yaxis_title="USD", showlegend=False,
                    )
                    st.plotly_chart(fig_gate, **WIDE)

                fig_cex = go.Figure()
                fig_cex.add_trace(go.Scatter(
                    y=led["CEX Liquidity ใช้สะสม (บาท)"], x=led.index,
                    name="CEX Liquidity ใช้สะสม",
                    line=dict(color="#8B5CF6", width=2),
                ))
                fig_cex.add_hline(
                    y=cex_liquidity_thb, line=dict(color="#FF4B4B", dash="dash"),
                    annotation_text="CEX Liquidity",
                )
                fig_cex.update_layout(
                    template="plotly_dark", height=300, margin=dict(t=40, b=20),
                    title="CEX Liquidity ที่ใช้ไป", xaxis_title="ออเดอร์ที่",
                    yaxis_title="THB", showlegend=False,
                )
                st.plotly_chart(fig_cex, **WIDE)

                fig_nc = go.Figure()
                fig_nc.add_trace(go.Scatter(
                    y=led["NC Buffer"], x=led.index, name="NC Buffer",
                    line=dict(color="#F59E0B", width=2),
                ))
                fig_nc.add_hline(
                    y=0, line=dict(color="#FF4B4B", dash="dash"),
                    annotation_text="เกณฑ์ขั้นต่ำ",
                )
                fig_nc.update_layout(
                    template="plotly_dark", height=300, margin=dict(t=40, b=20),
                    title="NC Buffer หลังแต่ละออเดอร์", xaxis_title="ออเดอร์ที่",
                    yaxis_title="THB", showlegend=False,
                )
                st.plotly_chart(fig_nc, **WIDE)

                st.dataframe(
                    led.sort_index(ascending=False), height=380, **WIDE,
                    column_config={
                        "มูลค่า (บาท)": st.column_config.NumberColumn(format="%.0f"),
                        "ราคาที่ลูกค้าได้": st.column_config.NumberColumn(format="%.2f"),
                        "เหรียญที่ส่งมอบ": st.column_config.NumberColumn(format="%.6f"),
                        "Hedge (เหรียญ)": st.column_config.NumberColumn(format="%.6f"),
                        "Hedge (USD)": st.column_config.NumberColumn(format="%.0f"),
                        "CEX Liquidity ใช้ (บาท)": st.column_config.NumberColumn(format="%.0f"),
                        "Unhedged (บาท)": st.column_config.NumberColumn(format="%.0f"),
                        "Market Edge": st.column_config.NumberColumn(format="%.0f"),
                        "รายได้": st.column_config.NumberColumn(format="%.0f"),
                        "ต้นทุน": st.column_config.NumberColumn(format="%.0f"),
                        "กำไรออเดอร์": st.column_config.NumberColumn(format="%.0f"),
                        "สต็อกคงเหลือ": st.column_config.NumberColumn(format="%.6f"),
                        "FX ใช้สะสม (USD)": st.column_config.NumberColumn(format="%.0f"),
                        "CEX Liquidity ใช้สะสม (บาท)": st.column_config.NumberColumn(format="%.0f"),
                        "NC Buffer": st.column_config.NumberColumn(format="%.0f"),
                    }
                )
                st.download_button(
                    "⬇️ ดาวน์โหลดสมุดออเดอร์ (CSV)",
                    to_csv_bytes(led), f"xspring_orders_{asset}.csv", "text/csv"
                )

            with st.expander("📐 สมมติฐานของ Customer Order Simulator"):
                st.markdown(f"""
- ราคาอ้างอิง: ราคาปิดล่าสุดจริงของ **{asset}** = `$ {spot_usd_now:,.2f}` · USD/THB = `{usdthb_now_sim:,.2f}`
  (ข้อมูลชุดเดียวกับที่โหลดในช่วงวันที่ฝั่งซ้าย ไม่ใช่ realtime tick)
- เป้าสต็อกสำรอง `I* = a × V` → `{fmt_baht(target_stock_thb)}` ≈ `{fmt_coin(target_stock_thb/coin_price_thb_now, asset)}`
- **Buy-side:** หลังส่งมอบ ระบบเติม inventory กลับด้วยการซื้อบน Global CEX โดยกิน **Outbound FX quota**
- **Sell-side:** หลังรับเหรียญ ระบบขาย inventory ส่วนเกินบน Global CEX โดยใช้ **CEX liquidity เดิม** และ **ไม่กิน outbound FX quota**
- Buy-side สามารถ hedge ได้ **บางส่วน** เมื่อ FX quota ไม่พอ; inventory จะไม่ถูกปล่อยให้ติดลบ
- Sell-side สามารถ hedge ได้ **บางส่วน** เมื่อ CEX liquidity ไม่พอ; ส่วนเกินจะกลายเป็น inventory exposure
- P&L ของออเดอร์ใช้ **Market Edge จาก Quote เทียบ Global Reference แบบ direction-aware** + fee/benefit หักต้นทุน hedge/slippage
- NC/Capital ในหน้านี้ใช้ **planning model เดียวกับ Capital Planner** เพื่อดูสถานะหลังออเดอร์ ไม่ใช่ตัวรับรอง compliance อัตโนมัติ
- CEX liquidity ฝั่ง Customer ใช้ค่า **CEX Margin เดิม (`{fmt_baht(cex_margin_thb)}`)** เป็น proxy โดยไม่แก้สมการหรือค่าใน Tab 2
                """)
