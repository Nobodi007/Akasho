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
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="xs-hero">
  <h1>🏦 XSpring — Digital Asset Dealer Suite</h1>
  <p>Backtest 5 ปีย้อนหลัง + Liquidity &amp; Capital Planner พร้อมกราฟ TradingView เรียลไทม์</p>
  <span class="xs-pill">Back-to-Back Hedging</span>
  <span class="xs-pill">FX Limit Engine</span>
  <span class="xs-pill">NCR Capital Planner</span>
  <span class="xs-pill">Multi-Asset Risk</span>
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
# RISK ENGINE (ใช้ร่วมกันทั้งโหมด Single-Asset และ Multi-Asset)
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


# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.markdown("### ⚙️ Backtest Settings")
    st.caption("ใช้ร่วมกันทั้งแท็บ **5-Year Backtest** และโหมด Single-Asset ของ **Capital Planner**")

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


# ===== โหลดข้อมูลครั้งเดียว ใช้ร่วมกันทั้ง Backtest และ Capital Planner =====
data, data_err = (pd.DataFrame(), "ช่วงวันที่ไม่ถูกต้อง") if not dates_ok \
                 else fetch_price_data(asset, start_date, end_date)


# =========================================================
# TABS
# =========================================================
tab1, tab2 = st.tabs(["📊 5-Year Backtest Simulator", "🧮 Liquidity & Capital Planner"])

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
        # KTB: เรทแลกเปลี่ยน USD/THB พิเศษที่ดีกว่าตลาด (bps) — ประหยัดทุกครั้งที่แปลงเงินก้อนที่ hedge กลับมาเป็นบาท
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
        # FIX #3: คิด drawdown % เทียบ peak ของ "วันเดียวกัน" ไม่ใช่เอา scalar หารทั้ง Series
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

        # FIX #6: measure "total" ไม่ใช้ค่า y -> ใส่ text เองเพื่อไม่ให้แท่งสุดท้ายโชว์ 0
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
# TAB 2 — LIQUIDITY & CAPITAL PLANNER (ใหม่ทั้งหมด)
# ---------------------------------------------------------
with tab2:
    st.markdown("""
ตอบคำถามที่ผู้บริหารถามจริง:

> **"ถ้าธุรกรรมเดือนละ X ล้าน ต้องดำรงเหรียญเท่าไหร่ เงินสดเท่าไหร่ NCR เหลือเท่าไหร่ ผ่านเกณฑ์ไหม และทุนที่มีรับได้สูงสุดกี่ล้าน"**

โดยดึงค่า Volatility / VaR / Expected Shortfall จาก **ราคาจริงย้อนหลัง** (ช่วงเวลาเดียวกับที่ตั้งไว้ในแถบซ้าย)
    """)

    if not dates_ok:
        st.error("❌ ช่วงวันที่ในแถบซ้ายไม่ถูกต้อง — แก้ก่อนถึงจะคำนวณความเสี่ยงได้")
    else:
        # =====================================================
        # 1) เลือกโหมดความเสี่ยง
        # =====================================================
        section("🎛️ โหมดคำนวณความเสี่ยง")
        cp_mode = st.radio("เลือกโหมด",
                           ["Single-Asset (ใช้เหรียญที่เลือกในแถบซ้าย)", "Multi-Asset Portfolio"],
                           horizontal=True, key="cp_mode")

        rp = None            # risk profile dict (returns, es99, worst, ...)
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

        # =====================================================
        # 2) พารามิเตอร์ธุรกรรม + งบดุล + คำนวณ
        # =====================================================
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

            section("📥 พารามิเตอร์ธุรกรรม (Flow Assumptions)")
            fc1, fc2 = st.columns(2)
            with fc1:
                monthly_volume_thb = comma_number_input("ปริมาณธุรกรรมลูกค้าต่อเดือน (THB)",
                                                        value=300_000_000, min_value=0,
                                                        key="cp_volume")
                st.caption(f"≈ {fmt_baht(monthly_volume_thb)}")
                net_bias_pct = st.slider("Net Flow Bias — ลูกค้าซื้อสุทธิ(+) / ขายสุทธิ(-)",
                                          -100, 100, 20, key="cp_bias",
                                          help="ทิศทางสุทธิที่ทำให้ต้องดองคริปโตไว้เป็นสต็อก (ฝั่ง + เท่านั้นที่กินสต็อก)") / 100
                flow_cv_pct = st.slider("ความผันผวนของปริมาณต่อวัน (Coefficient of Variation, %)",
                                         10, 150, 40, key="cp_cv") / 100
            with fc2:
                settlement_days = st.number_input("Settlement / Hedge Lag (วัน)", value=2, min_value=1,
                                                  max_value=10, step=1, key="cp_lag",
                                                  help="ระยะเวลาที่ต้องถือสต็อกไว้ก่อนจะ hedge/settle ได้ครบ")
                confidence = st.select_slider("Confidence Level ของ Safety Stock",
                                              options=[90, 95, 99, 99.9], value=99, key="cp_conf")
                z_alpha = Z_SCORE_MAP[confidence]
                cex_margin_asset = st.selectbox("สินทรัพย์ Margin บนกระดานโลก",
                                                ["Stablecoin (ความเสี่ยงต่ำ)", "เหรียญเดียวกับที่เทรด (ความเสี่ยงเท่าคริปโต)"],
                                                key="cp_cex_asset")

            section("⚖️ เกณฑ์เงินกองทุน (NC) — อ้างอิงประกาศ ก.ล.ต. จริง")
            st.caption("อ้างอิงประกาศ กธ. 28-30/2567 และ สธ. 30-32/2567 (มีผลบังคับ 1 พ.ย. 2567) "
                       "และอัตรา NC cold wallet ที่ปรับลดเหลือ 1% (จาก 2%) ตามการปรับปรุงปี 2568 "
                       "ตัวเลข 🔒 ด้านล่างเป็นอัตราที่ประกาศไว้จริง ส่วนตัวเลขที่ปรับได้เป็นค่าที่ยังไม่มีตัวเลขทางการ "
                       "เผยแพร่ครบถ้วน (เช่น อัตรา cold wallet ต่างประเทศ) — ใช้เป็นค่าประมาณการเพื่อจำลองเท่านั้น "
                       "โปรดตรวจสอบกับประกาศฉบับล่าสุดก่อนใช้อ้างอิงจริง")

            gc1, gc2, gc3 = st.columns(3)
            with gc1:
                is_custodian = st.checkbox("เก็บรักษาทรัพย์สินลูกค้า (Custody)", value=True,
                                           key="cp_is_custodian",
                                           help="กำหนดเงินกองทุนขั้นต่ำคงที่: 25 ล้านบาท หากเก็บรักษาทรัพย์สินลูกค้า, "
                                                "5 ล้านบาท หากไม่เก็บรักษา")
                fixed_min_nc = 25_000_000.0 if is_custodian else 5_000_000.0
                st.metric("🔒 เงินกองทุนขั้นต่ำคงที่ (Fixed Minimum NC)", fmt_baht(fixed_min_nc))
            with gc2:
                trading_risk_rate = st.number_input(
                    "อัตรา NC ความเสี่ยงบริการซื้อขาย (% ของมูลค่าซื้อขายเฉลี่ย/วัน ย้อนหลัง 3 เดือน)",
                    value=2.0, step=0.1, min_value=0.0, key="cp_trading_risk_rate",
                    help="ตามประกาศ กำหนดไม่น้อยกว่า 2% ของมูลค่าซื้อขายเฉลี่ยต่อวันย้อนหลัง 3 เดือน "
                         "(ใช้ปริมาณธุรกรรม/วันด้านล่างเป็นตัวแทนค่าเฉลี่ย 3 เดือน)") / 100
            with gc3:
                cold_foreign_rate = st.number_input(
                    "อัตรา NC cold wallet ต่างประเทศ โดยประมาณ (%)",
                    value=2.0, step=0.5, min_value=1.0, key="cp_cold_foreign_rate",
                    help="ประกาศระบุเพียงว่าอัตรานี้ 'สูงกว่า' กรณีฝากในประเทศ (1%) แต่ไม่ได้เผยแพร่ตัวเลขที่แน่นอน "
                         "— ค่านี้เป็นการประมาณเพื่อจำลองเท่านั้น ปรับได้ตามข้อมูลจริงที่หาเพิ่มเติมได้") / 100

            hot_wallet_nc_rate = 1.00      # 100% ของมูลค่า — ตามประกาศ (คงที่ ไม่ปรับ)
            cold_domestic_rate = 0.01      # 1% ของมูลค่า — อัตราปรับปรุงปี 2568 (คงที่ ไม่ปรับ)

            gc4, gc5 = st.columns(2)
            with gc4:
                hot_wallet_pct = st.slider("สัดส่วนสต็อกเหรียญที่เก็บใน Hot Wallet (%)", 0, 100, 50,
                                           key="cp_hot_pct",
                                           help="ส่วนที่เหลือถือเป็น Cold Wallet — ยิ่งเก็บใน Hot Wallet มาก "
                                                "ยิ่งต้องดำรง NC สูง (100% เทียบกับ 1% ของ Cold Wallet ในประเทศ)") / 100
            with gc5:
                cold_domestic_split_pct = st.slider("สัดส่วน Cold Wallet ที่ฝากในประเทศ (%)", 0, 100, 100,
                                                    key="cp_cold_domestic_pct",
                                                    help="ฝากในประเทศ = อัตรา NC 1% (🔒) / ฝากต่างประเทศ = อัตราประมาณการด้านบน") / 100
            cex_counterparty_haircut = st.number_input("Counterparty Haircut กรณี CEX Margin เป็น Stablecoin (%)",
                                                        value=2.0, step=0.5, min_value=0.0, key="cp_cex_hc") / 100

            st.caption(f"🔒 อัตราคงที่ตามประกาศ: Hot wallet NC = {hot_wallet_nc_rate*100:.0f}% ของมูลค่า · "
                      f"Cold wallet ในประเทศ NC = {cold_domestic_rate*100:.0f}% ของมูลค่า · "
                      f"เงินกองทุนขั้นต่ำคงที่ = {fmt_baht(fixed_min_nc)}")

            section("💼 เงินทุนที่มี (Capital Pool)")
            bc1, bc2, bc3 = st.columns(3)
            with bc1:
                total_capital_thb = comma_number_input(
                    "เงินทุนสภาพคล่องรวม (THB)", value=150_000_000, min_value=0,
                    key="cp_total_capital",
                    help="เงินสดทั้งหมดก่อนจัดสรรไปเป็นสต็อกเหรียญ (ระบบจะคำนวณให้ว่าควรแบ่งเป็นเงินสด/สต็อกเท่าไหร่)")
                st.caption(f"≈ {fmt_baht(total_capital_thb)}")
            with bc2:
                cex_margin_thb = comma_number_input("เงินทุนบนกระดานโลก / CEX Margin (THB)",
                                                     value=40_000_000, min_value=0, key="cp_cex_margin")
                st.caption(f"≈ {fmt_baht(cex_margin_thb)}")
            with bc3:
                liab_thb = comma_number_input("หนี้สินต่อลูกค้า (THB)", value=200_000_000,
                                              min_value=1, key="cp_liab")
                st.caption(f"≈ {fmt_baht(liab_thb)}")

            # ---------- CORE CALC ----------
            h_crypto = float(min(rp["es99"] * np.sqrt(settlement_days), 0.95))
            if cex_margin_asset.startswith("Stablecoin"):
                h_cex = float(cex_counterparty_haircut)
            else:
                h_cex = h_crypto

            daily_vol_thb = monthly_volume_thb / 30.0
            a_factor = (max(0.0, net_bias_pct) * settlement_days
                        + z_alpha * flow_cv_pct * np.sqrt(settlement_days)) / 30.0  # THB สต็อกที่ต้องดอง ต่อ 1 บาทของปริมาณ/เดือน

            required_stock_thb = a_factor * monthly_volume_thb
            cash_after_stock_thb = total_capital_thb - required_stock_thb

            nlc_thb = (cash_after_stock_thb + required_stock_thb * (1 - h_crypto)
                       + cex_margin_thb * (1 - h_cex) - liab_thb)

            # ---------- NC ตามเกณฑ์จริง: เงินกองทุนขั้นต่ำที่ต้องดำรง ----------
            hot_wallet_thb = required_stock_thb * hot_wallet_pct
            cold_wallet_thb = required_stock_thb * (1 - hot_wallet_pct)
            cold_domestic_thb = cold_wallet_thb * cold_domestic_split_pct
            cold_foreign_thb = cold_wallet_thb * (1 - cold_domestic_split_pct)

            custody_risk_nc = (hot_wallet_thb * hot_wallet_nc_rate
                                + cold_domestic_thb * cold_domestic_rate
                                + cold_foreign_thb * cold_foreign_rate)
            trading_service_risk_nc = trading_risk_rate * daily_vol_thb
            required_nc_total = fixed_min_nc + trading_service_risk_nc + custody_risk_nc

            nc_buffer_thb = nlc_thb - required_nc_total
            ncr_pct = (nlc_thb / required_nc_total * 100.0) if required_nc_total > 0 else float("nan")
            # หมายเหตุ: ncr_pct ที่นี่คือ "NC Coverage" = NC จริง / NC ขั้นต่ำที่ต้องดำรง × 100%
            # ไม่ใช่ NCR แบบร้อยละของหนี้สินแบบเดิม — ตัวชี้วัดที่ใช้ตัดสินผ่าน/ไม่ผ่านคือ nc_buffer_thb (ต้อง ≥ 0)

            hot_wallet_cap_breach = (liab_thb < 1_000_000_000) and (hot_wallet_pct > 0.50)

            # ---------- MAX CAPACITY ----------
            # แก้สมการ NLC(V) = Required_NC(V) แทนที่จะใช้เกณฑ์ NCR% แบบเดิม
            # ทั้ง custody NC และ trading-service NC ต่างก็แปรผันตามปริมาณธุรกรรม V
            blended_custody_rate = (hot_wallet_pct * hot_wallet_nc_rate
                                     + (1 - hot_wallet_pct) * (cold_domestic_split_pct * cold_domestic_rate
                                                                + (1 - cold_domestic_split_pct) * cold_foreign_rate))
            slope = a_factor * (h_crypto + blended_custody_rate) + trading_risk_rate / 30.0
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
            warn_nc = ok_nc and (ncr_pct < 150.0)   # ส่วนเกินเหลือน้อยกว่า 50% ของ NC ขั้นต่ำ = เข้าเขตเตือนภัย
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
                        sub_text=f"Hot {fmt_baht(hot_wallet_thb)} × {hot_wallet_nc_rate*100:.0f}% + "
                                  f"Cold {fmt_baht(cold_wallet_thb)} × ~{(cold_domestic_split_pct*cold_domestic_rate+(1-cold_domestic_split_pct)*cold_foreign_rate)*100:.2f}%")
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
เกณฑ์ผ่าน: **NC_actual ≥ NC_required** (เปรียบเทียบเป็นมูลค่าสัมบูรณ์ ไม่ใช่ร้อยละของหนี้สิน)

**Haircut จากข้อมูลจริง (ไม่ใช่เลขเดา):**
`h_crypto = ES99% × √L` (capped ที่ 95%)

**เพดานธุรกรรมสูงสุด** (ให้ NC_actual ≥ NC_required พร้อมกันกับเงินสดไม่ติดลบ):
`V_max = min( [Capital + M(1−h_CEX) − L_liab − Fixed_Min_NC] / [a×(h_crypto+blended_custody_rate) + trading_risk_rate/30],  Capital/a,  FX_Limit×USDTHB )`
โดย `a = [max(0,net_bias)×L + z_α×CV×√L] / 30`, `blended_custody_rate = {blended_custody_rate*100:.3f}%`

ค่าที่ใช้ตอนนี้: L = {settlement_days} วัน, z_α = {z_alpha:.3f} ({confidence}%), 
CV = {flow_cv_pct*100:.0f}%, net_bias = {net_bias_pct*100:+.0f}%, h_crypto = {h_crypto*100:.2f}%
                """)

            # =====================================================
            # 3) HISTORICAL REPLAY — Replay 5 ปี นับวันที่หลุดเกณฑ์จริง
            # =====================================================
            section("📼 Historical Replay — ย้อนดูว่าจะหลุดเกณฑ์กี่วันจริง")
            st.caption("นำ log-return รายวันจริงทั้งช่วงที่เลือกในแถบซ้าย มา shock ใส่สต็อกที่คำนวณได้ "
                       "(Historical Simulation) โดยคงเงินสด/CEX Margin/หนี้สินคงที่ตามที่ตั้งไว้ด้านบน")

            hist_returns = rp["returns"]
            crypto_val_series = required_stock_thb * np.exp(hist_returns)
            nlc_series = cash_after_stock_thb + crypto_val_series + cex_margin_thb - liab_thb
            # custody NC ขั้นต่ำก็แปรผันตามมูลค่าคริปโตที่ถืออยู่จริงในแต่ละวันด้วย (ไม่ใช่ค่าคงที่)
            custody_nc_series = crypto_val_series * blended_custody_rate
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

            # =====================================================
            # 4) STRESS TEST — 6 สถานการณ์
            # =====================================================
            section("🧨 Stress Test — 6 สถานการณ์")

            def _scenario_nc_buffer(crypto_val, extra_haircut_mult=1.0, extra_stock=0.0):
                h_eff = min(h_crypto * extra_haircut_mult, 0.99)
                cv = crypto_val + extra_stock
                nlc_s = cash_after_stock_thb + cv * (1 - h_eff) + cex_margin_thb * (1 - h_cex) - liab_thb
                custody_nc_s = cv * blended_custody_rate  # NC ขั้นต่ำฝั่ง custody ก็เปลี่ยนตามมูลค่าคริปโตที่ถืออยู่จริง
                required_s = fixed_min_nc + trading_service_risk_nc + custody_nc_s
                return nlc_s - required_s

            extra_flow = daily_vol_thb * 3.0     # bank run: ลูกค้าเทขาย 3 เท่าปริมาณเฉลี่ยรายวัน ในวันเดียว
            fx_stuck = min(monthly_volume_thb, fx_max_v_thb) * 0.5  # FX limit ลดครึ่งหนึ่ง = โอนออกไม่ทันครึ่งหนึ่ง

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

            st.caption("Stress Test ใช้เงินสด/CEX Margin/หนี้สินคงที่ตามที่ตั้งไว้ด้านบน แล้วช็อกเฉพาะฝั่งสต็อกเหรียญ/haircut "
                       "และคำนวณ NC ขั้นต่ำใหม่ตามมูลค่าคริปโตที่ถืออยู่จริงในแต่ละสถานการณ์ "
                       "เพื่อดูว่า NC Buffer จะยังเป็นบวกอยู่หรือไม่")
