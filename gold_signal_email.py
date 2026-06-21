#!/usr/bin/env python3
"""
Gold Mini daily signal -> EMAIL.
Runs once (e.g. 09:00 IST via GitHub Actions / Task Scheduler), fetches free
market data, scores it with the SAME logic as the Excel calculator, and emails
the Total Score + Confidence + Signal to you. It also remembers the last signal
(state.json) and flags whenever the signal CHANGES (in the subject line too).

Auto-fetched inputs (free data): 20/50 DMA, Price vs 20DMA, RSI, ATR, USD/INR,
DXY, US 10Y yield, inflation expectations (10Y breakeven), crude, IV (GVZ).
Manual inputs (no free source) -> edit the CONSTANTS below when you check your
MCX option chain: OI Trend, PCR, Max Pain, FII. Central-bank buying is a slow
quarterly constant.

NOT financial advice. Technicals run on global gold (GC=F) as a proxy for MCX.
"""

import os, json, io, datetime, smtplib, ssl
from email.message import EmailMessage
from zoneinfo import ZoneInfo
import requests
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ------------------------------------------------------------------ CONFIG
# Email (set these as environment variables / repo secrets)
EMAIL_FROM = os.getenv("EMAIL_FROM")                 # your Gmail address
EMAIL_PASS = os.getenv("EMAIL_PASS")                 # Gmail 16-char App Password
EMAIL_TO   = os.getenv("EMAIL_TO", EMAIL_FROM)       # recipient (default: yourself)
SMTP_HOST  = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT  = int(os.getenv("SMTP_PORT", "465"))

# --- Manual inputs: update these when you look at your MCX option chain ---
CENTRAL_BANK = 5     # +5 net buying / -5 net selling (update each WGC quarter)
OI_TREND     = 0     # +15 strong long / +5 mild long / -5 mild short / -15 strong short / 0 = skip
PCR          = 0     # +10 bullish / 0 neutral / -10 bearish
MAX_PAIN     = 0     # +10 price below max-pain / 0 / -10 price above
FII          = 0     # +10 net long / 0 / -10 net short

TREND_DAYS = 5       # look-back (trading days) used for macro trend direction

TICKERS = {"gold": "GC=F", "usdinr": "INR=X", "dxy": "DX-Y.NYB",
           "tnx": "^TNX", "brent": "BZ=F", "gvz": "^GVZ"}

# ------------------------------------------------------------------ HELPERS
def rsi(close, period=14):
    d = close.diff()
    up = d.clip(lower=0); dn = -d.clip(upper=0)
    ag = up.ewm(alpha=1/period, min_periods=period).mean()
    al = dn.ewm(alpha=1/period, min_periods=period).mean()
    return 100 - 100/(1 + ag/al)

def atr(high, low, close, period=14):
    pc = close.shift(1)
    tr = pd.concat([high-low, (high-pc).abs(), (low-pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, min_periods=period).mean()

def hist(sym, period="1y"):
    df = yf.Ticker(sym).history(period=period)
    if df.empty:
        raise RuntimeError("no data for " + sym)
    return df

def chg(series, days):
    return series.iloc[-1] - series.iloc[-1-days] if len(series) > days else 0.0

def fred_breakeven_trend():
    """10Y breakeven inflation (T10YIE) from FRED CSV -> +5 rising / -5 falling."""
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=T10YIE"
    r = requests.get(url, timeout=30); r.raise_for_status()
    vals = []
    for line in r.text.strip().splitlines()[1:]:
        parts = line.split(",")
        if len(parts) == 2 and parts[1] not in (".", ""):
            try: vals.append(float(parts[1]))
            except ValueError: pass
    if len(vals) <= TREND_DAYS:
        return 0, "n/a"
    return (5 if vals[-1] - vals[-1-TREND_DAYS] > 0 else -5), f"{vals[-1]:.2f}%"

# ------------------------------------------------------------------ SCORING
def build_scores():
    rows = []   # (name, score, note)

    # ---- technicals on gold (proxy for MCX Gold Mini) ----
    try:
        g = hist(TICKERS["gold"], "1y")
        c, h, l = g["Close"], g["High"], g["Low"]
        s20, s50 = c.rolling(20).mean(), c.rolling(50).mean()
        rv = rsi(c).iloc[-1]; a = atr(h, l, c)
        rows.append(("20DMA vs 50DMA", 10 if s20.iloc[-1] > s50.iloc[-1] else -10,
                     "20>50" if s20.iloc[-1] > s50.iloc[-1] else "20<50"))
        rows.append(("Price vs 20DMA", 10 if c.iloc[-1] > s20.iloc[-1] else -10,
                     f"{c.iloc[-1]:.0f}"))
        rows.append(("RSI(14)", 10 if rv > 55 else (-10 if rv < 45 else 0), f"{rv:.0f}"))
        an, ap = a.iloc[-1], a.iloc[-1-TREND_DAYS]
        rows.append(("ATR trend", 10 if an > ap*1.02 else (-10 if an < ap*0.98 else 0),
                     "rising" if an > ap else "falling"))
    except Exception as e:
        for nm in ("20DMA vs 50DMA", "Price vs 20DMA", "RSI(14)", "ATR trend"):
            rows.append((nm, 0, "data err"))
        print("technicals error:", e)

    # ---- macro (trend over TREND_DAYS) ----
    def macro(name, sym, up_score, down_score):
        try:
            s = hist(sym)["Close"]; d = chg(s, TREND_DAYS)
            rows.append((name, up_score if d > 0 else down_score,
                         ("up" if d > 0 else "down")))
        except Exception as e:
            rows.append((name, 0, "data err")); print(name, "error:", e)

    macro("USD/INR", TICKERS["usdinr"], +15, -15)   # weaker rupee (up) lifts INR gold
    macro("DXY",     TICKERS["dxy"],     -5,  +5)    # inverse to gold
    macro("US 10Y",  TICKERS["tnx"],     -5,  +5)    # rising yields bearish gold
    macro("Crude",   TICKERS["brent"],   +2,  -2)

    # ---- inflation expectations (FRED breakeven) ----
    try:
        sc, note = fred_breakeven_trend(); rows.append(("Inflation exp", sc, note))
    except Exception as e:
        rows.append(("Inflation exp", 0, "data err")); print("breakeven error:", e)

    # ---- IV via GVZ percentile (proxy for gold IV rank) ----
    try:
        gvz = hist(TICKERS["gvz"], "1y")["Close"]
        pct = float((gvz < gvz.iloc[-1]).mean())
        iv = 15 if pct < 0.30 else (-15 if pct > 0.70 else 0)   # low IV favours buying, high favours spreads
        rows.append(("IV (GVZ)", iv, f"{gvz.iloc[-1]:.1f}/{pct*100:.0f}%ile"))
    except Exception as e:
        rows.append(("IV (GVZ)", 0, "data err")); print("gvz error:", e)

    # ---- manual / slow constants ----
    rows.append(("Central bank", CENTRAL_BANK, "manual"))
    rows.append(("OI trend",  OI_TREND,  "manual"))
    rows.append(("PCR",       PCR,       "manual"))
    rows.append(("Max Pain",  MAX_PAIN,  "manual"))
    rows.append(("FII",       FII,       "manual"))
    return rows

def signal_for(total):
    if total >= 70:  return "BUY CALL"
    if total >= 40:  return "BULL CALL SPREAD"
    if total >= 20:  return "LONG FUTURE + HEDGE"
    if total > -20:  return "NO TRADE"
    if total > -70:  return "BUY PUT"
    return "BEAR PUT SPREAD"

def confidence_for(total):
    a = abs(total)
    if a >= 70: return "Very High"
    if a >= 40: return "High"
    if a >= 20: return "Moderate"
    return "Low"

# ------------------------------------------------------------------ HTML EMAIL
CHART_CID = "goldchart"

def signal_color(sig):
    if sig in ("BUY CALL", "BULL CALL SPREAD", "LONG FUTURE + HEDGE"): return "#1b8a5a"
    if sig in ("BUY PUT", "BEAR PUT SPREAD"): return "#c0392b"
    return "#6b6b76"

def build_chart():
    """6-month gold price chart with 20/50 DMA, returned as PNG bytes (None on failure)."""
    try:
        c = hist(TICKERS["gold"], "6mo")["Close"]
        s20, s50 = c.rolling(20).mean(), c.rolling(50).mean()
        fig, ax = plt.subplots(figsize=(7, 3), dpi=130)
        ax.plot(c.index, c.values, color="#1a1a2e", linewidth=1.6, label="Gold (GC=F)")
        ax.plot(s20.index, s20.values, color="#e94560", linewidth=1.1, label="20DMA")
        ax.plot(s50.index, s50.values, color="#0f8b8d", linewidth=1.1, label="50DMA")
        ax.legend(loc="upper left", fontsize=8, frameon=False)
        ax.set_title("Gold (COMEX proxy) - last 6 months", fontsize=10)
        ax.tick_params(labelsize=8)
        ax.grid(alpha=0.25)
        fig.tight_layout()
        buf = io.BytesIO(); fig.savefig(buf, format="png"); plt.close(fig)
        return buf.getvalue()
    except Exception as e:
        print("chart error:", e); return None

def build_html(date, total, sig, conf, prev, changed, rows, has_chart):
    color = signal_color(sig)
    changed_line = f" &nbsp;&middot;&nbsp; changed from <b>{prev}</b>" if changed else ""
    chart_tag = (f'<img src="cid:{CHART_CID}" style="width:100%;display:block;" />'
                 if has_chart else "")

    def row(nm, s, note):
        rc = "#1b8a5a" if s > 0 else ("#c0392b" if s < 0 else "#9a9aa3")
        return (f'<tr><td style="padding:5px 10px;color:#333;font-size:13px;">{nm}</td>'
                f'<td style="padding:5px 10px;text-align:right;color:{rc};font-weight:600;'
                f'font-size:13px;">{s:+d}</td>'
                f'<td style="padding:5px 10px;color:#9a9aa3;font-size:12px;">{note}</td></tr>')

    rows_html = "".join(row(*r) for r in rows)
    return f"""\
<html><body style="margin:0;padding:16px;background:#f2f2f6;font-family:Segoe UI,Arial,sans-serif;">
<div style="max-width:560px;margin:0 auto;background:#fff;border-radius:10px;overflow:hidden;
            border:1px solid #e8e8ee;">
  <div style="background:{color};color:#fff;padding:18px 20px;">
    <div style="font-size:12px;opacity:.85;">GOLD MINI SIGNAL &nbsp;&middot;&nbsp; {date} &nbsp;&middot;&nbsp; 09:00 IST</div>
    <div style="font-size:24px;font-weight:700;margin-top:4px;">{sig}</div>
    <div style="font-size:13px;margin-top:3px;opacity:.95;">Total {total:+d} &nbsp;&middot;&nbsp; Confidence: {conf}{changed_line}</div>
  </div>
  {chart_tag}
  <table style="width:100%;border-collapse:collapse;margin-top:2px;">{rows_html}</table>
  <div style="padding:12px 20px;color:#a0a0aa;font-size:11px;border-top:1px solid #eee;">
    Auto inputs from free data; OI/PCR/MaxPain/FII are manual. Not financial advice.
  </div>
</div>
</body></html>"""

# ------------------------------------------------------------------ STATE
STATE = "state.json"
def load_state():
    try:
        with open(STATE) as f: return json.load(f)
    except Exception:
        return {}
def save_state(sig, total, date):
    with open(STATE, "w") as f:
        json.dump({"signal": sig, "total": total, "date": date}, f)

# ------------------------------------------------------------------ SEND
def send_email(subject, body, html_body=None, chart_png=None):
    if not (EMAIL_FROM and EMAIL_PASS):
        print("Email not configured. Subject:", subject, "\n" + body); return
    msg = EmailMessage()
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
        if chart_png:
            msg.get_payload()[-1].add_related(chart_png, "image", "png", cid=f"<{CHART_CID}>")
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as s:
            s.login(EMAIL_FROM, EMAIL_PASS)
            s.send_message(msg)
        print("Email sent to", EMAIL_TO)
    except Exception as e:
        print("Email send failed:", e)

# ------------------------------------------------------------------ MAIN
def main():
    now = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
    date = now.strftime("%d %b %Y")
    rows = build_scores()
    total = sum(s for _, s, _ in rows)
    sig, conf = signal_for(total), confidence_for(total)

    prev = load_state().get("signal")
    changed = bool(prev) and prev != sig
    subject = (f"[SIGNAL CHANGED] {sig} ({conf})" if changed
               else f"Gold Signal: {sig} ({conf})")
    change_line = f"\n*** SIGNAL CHANGED: {prev} -> {sig} ***" if changed else ""

    breakdown = "\n".join(f"{nm}: {s:+d} ({note})" for nm, s, note in rows)
    body = (f"GOLD MINI SIGNAL  {date} 09:00 IST\n"
            f"Total Score: {total}\n"
            f"Signal: {sig}\n"
            f"Confidence: {conf}{change_line}\n"
            f"--------------------\n{breakdown}\n"
            f"--------------------\n"
            f"Auto inputs from free data; OI/PCR/MaxPain/FII are manual. "
            f"Not financial advice.")

    chart_png = build_chart()
    html = build_html(date, total, sig, conf, prev, changed, rows, has_chart=bool(chart_png))

    print(subject); print(body)
    send_email(subject, body, html, chart_png)
    save_state(sig, total, date)

if __name__ == "__main__":
    main()
