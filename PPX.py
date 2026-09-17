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
  <p>Backtest 5 ปีย้อนหลัง + Trading Desk แบบ Interactive พร้อมกราฟ TradingView เรียลไทม์</p>
  <span class="xs-pill">Back-to-Back Hedging</span>
  <span class="xs-pill">FX Limit Engine</span>
  <span class="xs-pill">NCR Monitor</span>
  <span class="xs-pill">Live TradingView</span>
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


# =========================================================
# HELPERS
# =========================================================
def fmt_baht(value, force_sign=False):
    value = 0.0 if pd.isna(value) else float(value)
    sign = "- " if value < 0 else ("+ " if force_sign else "")
    v = abs(value)
    if v >= 1_000_000_000:   num = f"{v/1_000_000_000:,.2f}B"
    elif v >= 1_000_000:     num = f"{v/1_000_000:,.2f}M"
    elif v >= 1_000:         num = f"{v/1_000:,.1f}K"
    else:                    num = f"{v:,.2f}"
    return f"{sign}฿ {num}"


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


def calc_thb_withdrawal_fee(amount_thb: float, bank_type: str) -> float:
    if bank_type == "SCB":
        return 20.0
    return 20.0 if amount_thb <= 2_000_000 else 70.0


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
# SIDEBAR
# =========================================================
with st.sidebar:
    st.markdown("### ⚙️ Backtest Settings")
    st.caption("ตั้งค่าสำหรับแท็บ **5-Year Backtest** — แท็บ Trading Desk ตั้งค่าในหน้าแท็บเอง")

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
        trade_vol = st.number_input("ปริมาณซื้อขายลูกค้า/วัน (USD eq.)", value=100000, step=10000, key="bt_trade_vol")
        dealer_spread = st.number_input("Dealer Spread ที่เก็บจากลูกค้า (%)", value=0.5, step=0.1, key="bt_spread") / 100

        if "bt_prev_gx" not in st.session_state:
            st.session_state.bt_prev_gx = global_exchange
        if "bt_hedge_fee" not in st.session_state:
            st.session_state.bt_hedge_fee = GLOBAL_EXCHANGE_FEE_PRESET[global_exchange]
        if st.session_state.bt_prev_gx != global_exchange:
            st.session_state.bt_hedge_fee = GLOBAL_EXCHANGE_FEE_PRESET[global_exchange]
            st.session_state.bt_prev_gx = global_exchange

        hedge_fee = st.number_input("ค่าธรรมเนียม Global CEX (%)", key="bt_hedge_fee", step=0.01) / 100
        fx_limit_max = st.number_input("FX Limit ต่อเดือน (USD)", value=5000000, step=500000,
                                       min_value=1, key="bt_fx_limit")
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
        bank_type = st.selectbox("ธนาคารปลายทางถอนบาท", ["SCB", "ธนาคารอื่น"], key="bt_bank_type")
        st.caption(f"ขั้นต่ำซื้อขายจริง {MIN_TRADE_THB:,.0f} บาท/คำสั่ง — ต่ำกว่าปริมาณที่ตั้งไว้มาก จึงไม่กระทบผลจำลอง")

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


# =========================================================
# TABS
# =========================================================
tab1, tab2 = st.tabs(["📊 5-Year Backtest Simulator", "🕹️ Live Trading Desk Simulator"])

# ---------------------------------------------------------
# TAB 1
# ---------------------------------------------------------
with tab1:
    data, err = (pd.DataFrame(), "ช่วงวันที่ไม่ถูกต้อง") if not dates_ok else fetch_price_data(asset, start_date, end_date)

    if data.empty:
        st.error(f"⚠️ {err or 'ไม่สามารถโหลดข้อมูลได้'} — ลองเปลี่ยนช่วงวันที่หรือตรวจสอบการเชื่อมต่ออินเทอร์เน็ต")
    else:
        data = data.copy()
        data["Local_THB"] = data["Global_USD"] * data["USDTHB"] * (1 + local_premium)

        # ---------- P&L ENGINE ----------
        data["Coin_Volume"] = trade_vol / data["Global_USD"]
        data["Gross_Notional_THB"] = data["Coin_Volume"] * data["Local_THB"]
        data["Spread_Revenue_THB"] = data["Gross_Notional_THB"] * dealer_spread
        data["FX_Basis_PnL_THB"] = trade_vol * data["USDTHB"] * local_premium
        data["Hedge_Fee_Cost_THB"] = trade_vol * hedge_fee * data["USDTHB"]
        data["Hedge_Notional_USD"] = trade_vol * (1 + hedge_fee)

        if asset in STABLECOINS:
            data["Depeg_Deviation"] = peg_target - data["Global_USD"]
            data["Depeg_PnL_THB"] = (data["Coin_Volume"] * data["Depeg_Deviation"]
                                     * data["USDTHB"] * depeg_capture_pct)
            data["Carry_Yield_THB"] = trade_vol * (carry_apy / 365) * data["USDTHB"]
            data["Slippage_Cost_THB"] = 0.0
        else:
            data["Depeg_Deviation"] = 0.0
            data["Depeg_PnL_THB"] = 0.0
            data["Carry_Yield_THB"] = 0.0
            data["Slippage_Cost_THB"] = (trade_vol * data["Volatility_Pct"]
                                         * slippage_sensitivity * data["USDTHB"])

        data["Trading_Fee_Revenue_THB"] = (data["Gross_Notional_THB"] * LOCAL_TRADING_FEE_PCT
                                           if include_trading_fee_revenue else 0.0)

        wd_fee_per_coin = WITHDRAWAL_FEE_TABLE.get(asset, 0.0)
        wd_network_cost = wd_fee_per_coin * data["Global_USD"] * data["USDTHB"] * settlements_per_day
        data["Withdrawal_Fee_Markup_Revenue_THB"] = wd_network_cost * withdrawal_fee_markup_pct

        data["THB_WD_Fee"] = data["USDTHB"].map(lambda fx: calc_thb_withdrawal_fee(trade_vol * fx, bank_type))
        data["THB_Fee_Markup_Revenue_THB"] = (data["THB_WD_Fee"] * settlements_per_day
                                              * withdrawal_fee_markup_pct)

        data["Fee_Revenue_THB"] = (data["Trading_Fee_Revenue_THB"]
                                   + data["Withdrawal_Fee_Markup_Revenue_THB"]
                                   + data["THB_Fee_Markup_Revenue_THB"])

        data["Revenue_THB"] = (data["Spread_Revenue_THB"] + data["FX_Basis_PnL_THB"]
                               + data["Fee_Revenue_THB"] + data["Depeg_PnL_THB"] + data["Carry_Yield_THB"])
        data["Cost_THB"] = data["Hedge_Fee_Cost_THB"] + data["Slippage_Cost_THB"]
        data["Daily_PnL_THB"] = data["Revenue_THB"] - data["Cost_THB"]

        # ---------- FX LIMIT ----------
        allowed, usage = apply_fx_limit(data["Hedge_Notional_USD"], data.index, fx_limit_max)
        data["Trade_Allowed"], data["Current_FX_Usage"] = allowed, usage
        data["FX_Limit_Hit"] = 1 - allowed
        data["Actual_Daily_PnL"] = np.where(allowed == 1, data["Daily_PnL_THB"], 0.0)
        data["Actual_Cum_PnL"] = data["Actual_Daily_PnL"].cumsum()

        # ---------- STATS ----------
        traded = data[data["Trade_Allowed"] == 1]
        total_revenue_thb = traded["Revenue_THB"].sum()
        total_cost_thb = traded["Cost_THB"].sum()
        net_pnl_thb = data["Actual_Cum_PnL"].iloc[-1]
        total_notional = traded["Gross_Notional_THB"].sum()
        margin_bps = (net_pnl_thb / total_notional * 10000) if total_notional else 0

        total_days, traded_days = len(data), int(allowed.sum())
        limit_hit_days = int(data["FX_Limit_Hit"].sum())
        win_days = int((data["Actual_Daily_PnL"] > 0).sum())
        win_rate = win_days / traded_days * 100 if traded_days else 0
        avg_daily_pnl = traded["Daily_PnL_THB"].mean() if traded_days else 0
        best_day, worst_day = data["Actual_Daily_PnL"].max(), data["Actual_Daily_PnL"].min()

        running_max = data["Actual_Cum_PnL"].cummax()
        max_drawdown = (data["Actual_Cum_PnL"] - running_max).min()
        # FIX #3: คิด drawdown % เทียบ peak ของ "วันเดียวกัน" ไม่ใช่เอา scalar หารทั้ง Series
        dd_series = (data["Actual_Cum_PnL"] - running_max) / running_max.where(running_max > 0)
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
                    f"หารด้วยเรท USD/THB ปัจจุบัน (~{data['USDTHB'].iloc[-1]:.2f}) แล้วเทียบกับราคาโลกได้เลย")
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
            metric_card(r3[2], "Avg Depeg Deviation", f"{data['Depeg_Deviation'].mean()*100:+.3f}%")
            metric_card(r3[3], "Total Carry Yield", fmt_baht(traded["Carry_Yield_THB"].sum()),
                        traded["Carry_Yield_THB"].sum())
        else:
            metric_card(r3[2], "Avg Daily Volatility", f"{data['Volatility_Pct'].mean()*100:.2f}%")
            metric_card(r3[3], "Total Slippage Cost", fmt_baht(traded["Slippage_Cost_THB"].sum()),
                        -abs(traded["Slippage_Cost_THB"].sum()))

        # ---------- WATERFALL ----------
        section("💧 Revenue & Cost Waterfall")
        wf_labels = ["Spread Revenue", "FX Basis P&L", "Fee Revenue"]
        wf_values = [traded["Spread_Revenue_THB"].sum(), traded["FX_Basis_PnL_THB"].sum(),
                     traded["Fee_Revenue_THB"].sum()]
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
        fig.add_trace(go.Scatter(x=data.index, y=data["Actual_Cum_PnL"], name="Cumulative P&L",
                                 line=dict(color="#00D26A", width=2.2),
                                 fill="tozeroy", fillcolor="rgba(0,210,106,0.12)"))
        fig.add_trace(go.Scatter(x=data.index, y=running_max, name="Peak Equity",
                                 line=dict(color="#6B7280", width=1, dash="dot")))
        hits = data[data["FX_Limit_Hit"] == 1]
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
            m = data.groupby([data.index.year, data.index.month])["Actual_Daily_PnL"].sum().unstack(fill_value=0)
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
                    "Hedge_Fee_Cost_THB", "Slippage_Cost_THB", "Fee_Revenue_THB"]
            if asset in STABLECOINS:
                cols += ["Depeg_Deviation", "Depeg_PnL_THB", "Carry_Yield_THB"]
            cols += ["Actual_Daily_PnL", "Current_FX_Usage", "FX_Limit_Hit"]
            ledger = data[cols]
            st.dataframe(ledger.sort_index(ascending=False).head(100), height=400, **WIDE)
            st.download_button("⬇️ ดาวน์โหลด Ledger ทั้งหมด (CSV)",
                               to_csv_bytes(ledger),
                               f"xspring_ledger_{asset}_{start_date}_{end_date}.csv", "text/csv")


# ---------------------------------------------------------
# TAB 2
# ---------------------------------------------------------
with tab2:
    st.markdown("สวมบทบาททีม Treasury บริหารสภาพคล่องให้รอดจาก **NCR** และ **FX Limit** "
                "โดยหักค่าธรรมเนียมจริงตาม Fee Schedule ของกระดานไทยและกระดานโลก")

    if "ktb_fiat" not in st.session_state:
        st.session_state.update(ktb_fiat=5_000_000, crypto_pool=0, cex_margin=1_000_000,
                                fx_used=0, fx_limit=3_000_000, logs=[])

    def add_log(msg):
        st.session_state.logs.insert(0, msg)
        del st.session_state.logs[6:]

    def cb_customer_sells(amount):
        if st.session_state.ktb_fiat >= amount:
            st.session_state.ktb_fiat -= amount
            st.session_state.crypto_pool += amount
            add_log(f"🔴 ลูกค้าเทขาย {amount:,.0f} USDT → เงินสดลด, คริปโตเต็มพอร์ต (ระวัง NCR ร่วง!)")
        else:
            add_log("❌ ล้มเหลว: เงินสด (Fiat) ไม่พอจ่ายลูกค้า!")

    def cb_back_to_back(amount, venue):
        fee_pct = GLOBAL_EXCHANGE_FEE_PRESET[venue] / 100
        total_cost = amount * (1 + fee_pct)
        if st.session_state.fx_used + amount > st.session_state.fx_limit:
            add_log("❌ ล้มเหลว: FX Limit เต็มเพดาน! ไม่สามารถโอนเงินออกได้")
        elif st.session_state.ktb_fiat >= total_cost:
            st.session_state.ktb_fiat -= total_cost
            st.session_state.cex_margin += amount
            st.session_state.fx_used += amount
            add_log(f"🌐 โอนเข้า {venue} {amount:,.0f} USD "
                    f"(ค่าธรรมเนียม {fee_pct*100:.2f}% = ${total_cost-amount:,.2f} | กินโควตา FX)")
        else:
            add_log("❌ ล้มเหลว: เงินสดไม่พอโอน (รวมค่าธรรมเนียมกระดานโลกแล้ว)")

    def cb_bridge(amount):
        wd_fee_coin = WITHDRAWAL_FEE_TABLE["USDT"]
        rate = st.session_state.get("td_usdthb_rate", 35.5)
        bank = st.session_state.get("td_bank_type", "SCB")
        thb_fee = calc_thb_withdrawal_fee(amount * rate, bank)
        total_fee_usd = wd_fee_coin + thb_fee / rate
        if st.session_state.crypto_pool >= amount:
            st.session_state.crypto_pool -= amount
            net = amount - total_fee_usd
            st.session_state.ktb_fiat += net
            add_log(f"✅ Liquidity Bridge: ดึงกลับ KTB {amount:,.0f} USD "
                    f"(เหรียญ {wd_fee_coin} USDT + THB ฿{thb_fee:,.0f} ≈ ${total_fee_usd:,.2f} | "
                    f"สุทธิ ${net:,.2f} · NCR ฟื้น — หมายเหตุ: โควตา FX ที่ใช้ไปแล้วไม่คืน)")
        else:
            add_log("❌ ล้มเหลว: ไม่มีคริปโตให้แปลงกลับ")

    def cb_reset():
        st.session_state.update(ktb_fiat=5_000_000, crypto_pool=0, cex_margin=1_000_000,
                                fx_used=0, logs=["🔄 รีเซ็ตสถานะเดสก์เรียบร้อย"])

    c_a, c_b = st.columns([1, 2])
    with c_a:
        td_global_exchange = st.selectbox("🌐 กระดานโลก (Back-to-Back Venue)",
                                          list(GLOBAL_EXCHANGE_FEE_PRESET.keys()), key="td_global_exchange")
    with c_b:
        st.caption(f"ทุกครั้งที่โอนเงินออก ระบบบันทึกว่าใช้ **{td_global_exchange}** "
                   f"ในการ hedge (ค่าธรรมเนียม {GLOBAL_EXCHANGE_FEE_PRESET[td_global_exchange]}%)")

    with st.expander("⚙️ ตั้งค่า Fee Schedule จริง"):
        fc1, fc2 = st.columns(2)
        with fc1:
            st.selectbox("ธนาคารปลายทางถอนบาท", ["SCB", "ธนาคารอื่น"], key="td_bank_type",
                         help="SCB คงที่ 20 บาท | ธนาคารอื่น 20 บาท (≤2M) หรือ 70 บาท (>2M)")
        with fc2:
            st.number_input("เรทอ้างอิง USD/THB", value=35.5, step=0.1, min_value=0.01, key="td_usdthb_rate")
        st.caption(f"ค่าธรรมเนียมถอน USDT คงที่ {WITHDRAWAL_FEE_TABLE['USDT']} USDT/ครั้ง · "
                   f"ค่าธรรมเนียมกระดานโลกเป็นต้นทุนจริงเพราะเราไม่ได้เป็นเจ้าของ")

    section("📡 Market Context (Live)")
    td_sym = st.selectbox("คู่เหรียญที่ต้องการมอนิเตอร์", list(TV_LOCAL_SYMBOL.values()),
                          index=list(TV_LOCAL_SYMBOL.keys()).index("USDT"), key="td_tv_symbol")
    render_tradingview(td_sym, "tv_desk", 420, interval="60")

    section("💼 Balance Sheet")
    penalty = (st.session_state.crypto_pool / 100_000) * 5
    ncr_score = max(0, 100 - penalty)
    fx_limit_val = max(st.session_state.fx_limit, 1)
    fx_percent = st.session_state.fx_used / fx_limit_val

    b1, b2, b3 = st.columns(3)
    with b1:
        with st.container(border=True):
            st.info("🏦 1. Fiat Pool (KTB Bank)")
            colored_metric("เงินสดพักรับดอกเบี้ย (USD)", f"$ {st.session_state.ktb_fiat:,.0f}",
                           st.session_state.ktb_fiat, "สภาพคล่องความเสี่ยงต่ำ")
    with b2:
        with st.container(border=True):
            st.warning("🪙 2. Crypto Pool (Inventory)")
            colored_metric("เหรียญที่ดองไว้ (USDT)", f"₮ {st.session_state.crypto_pool:,.0f}",
                           -st.session_state.crypto_pool if st.session_state.crypto_pool else 0,
                           "⚠️ เงินจม: เสียโอกาส + โดนหัก NCR")
    with b3:
        with st.container(border=True):
            st.success(f"🌐 3. Working Capital ({td_global_exchange})")
            colored_metric("เงินทุนบนกระดานโลก (USD)", f"$ {st.session_state.cex_margin:,.0f}",
                           st.session_state.cex_margin,
                           f"ค่าธรรมเนียมโอนเข้า {GLOBAL_EXCHANGE_FEE_PRESET[td_global_exchange]}%/ครั้ง")

    section("⚖️ Regulatory & Position Limits")
    l1, l2 = st.columns(2)
    with l1:
        st.write(f"**FX Limit (โควตาโอนข้ามประเทศ)** — {fx_percent*100:.1f}% "
                 f"(${st.session_state.fx_used:,.0f} / ${st.session_state.fx_limit:,.0f})")
        st.progress(min(fx_percent, 1.0))
        if fx_percent >= 1.0:
            st.error("🚨 เพดาน FX เต็ม! ธุรกิจชะงัก โอนไปกระดานนอกไม่ได้")
        elif fx_percent >= 0.8:
            st.warning("⚠️ ใช้โควตาไปเกิน 80% แล้ว — วางแผนรอบถัดไปให้ดี")
    with l2:
        st.write(f"**Net Capital Rule (NCR Score)** — {ncr_score:.1f}%")
        st.progress(ncr_score / 100.0)
        if ncr_score < 50:
            st.error("🚨 NCR ต่ำกว่าเกณฑ์! ก.ล.ต. สั่งเตรียมหยุดรับลูกค้า")
        elif ncr_score < 70:
            st.warning("⚠️ NCR เริ่มตึง — ควรทำ Liquidity Bridge ระบายคริปโตออก")

    section("🕹️ Trading Desk Controls")
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown("**สถานการณ์ตลาด**")
        st.button("🔴 ลูกค้าแห่เทขาย 500K USDT", key="td_sell",
                  on_click=cb_customer_sells, args=(500_000,), **WIDE)
    with k2:
        st.markdown("**Treasury โอนเงิน**")
        st.button(f"💸 โอนไป {td_global_exchange} 1M USD", key="td_transfer",
                  on_click=cb_back_to_back, args=(1_000_000, td_global_exchange), **WIDE)
    with k3:
        st.markdown("**กลยุทธ์แก้เกม**")
        st.button("🌉 Liquidity Bridge กลับ KTB 500K", type="primary",
                  key="td_bridge", on_click=cb_bridge, args=(500_000,), **WIDE)
    with k4:
        st.markdown("**จัดการเกม**")
        st.button("🔄 Reset Desk", key="td_reset", on_click=cb_reset, **WIDE)

    section("📝 Transaction Logs")
    if st.session_state.logs:
        for log in st.session_state.logs:
            st.markdown(f"<div style='background:#111827;border-left:3px solid #374151;"
                        f"padding:8px 12px;border-radius:6px;margin-bottom:6px;"
                        f"font-size:.86rem;'>{log}</div>", unsafe_allow_html=True)
    else:
        st.caption("ยังไม่มีรายการ — กดปุ่มด้านบนเพื่อเริ่มจำลอง")
