"""
TA Agent — технический анализ.
Работает только с реальными свечами из Data Agent.
Объясняет простым языком без терминов.
"""
import os
from anthropic import Anthropic
from agents.data_agent import get_candles, get_ticker_quote, get_current_datetime

claude = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def calculate_rsi(closes, period=14):
    if len(closes) < period + 1: return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0)); losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)

def calculate_ma(closes, period):
    if len(closes) < period: return None
    return round(sum(closes[-period:]) / period, 2)

def calculate_macd(closes):
    if len(closes) < 26: return None, None, None
    ema12 = calculate_ema(closes, 12)
    ema26 = calculate_ema(closes, 26)
    if not ema12 or not ema26: return None, None, None
    macd = ema12 - ema26
    return round(macd, 4), round(ema12, 4), round(ema26, 4)

def calculate_ema(closes, period):
    if len(closes) < period: return None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = price * k + ema * (1 - k)
    return ema

def analyze_ticker(ticker: str) -> dict:
    """Полный технический анализ по тикеру"""
    # Берём данные за разные периоды
    daily = get_candles(ticker, days=60, interval="day")
    weekly = get_candles(ticker, days=365, interval="week")
    quote = get_ticker_quote(ticker)

    if not daily["success"]:
        return {"success": False, "ticker": ticker, "error": daily.get("error")}

    candles = daily["candles"]
    if len(candles) < 15:
        return {"success": False, "ticker": ticker, "error": "Недостаточно данных"}

    closes = [c["close"] for c in candles if c.get("close")]
    highs = [c["high"] for c in candles if c.get("high")]
    lows = [c["low"] for c in candles if c.get("low")]

    rsi = calculate_rsi(closes)
    ma50 = calculate_ma(closes, 50) if len(closes) >= 50 else calculate_ma(closes, len(closes))
    ma20 = calculate_ma(closes, 20)
    macd_val, ema12, ema26 = calculate_macd(closes)

    current_price = quote["price"] if quote["success"] else closes[-1]
    change_pct = quote.get("change_pct") if quote["success"] else None
    change_text = f"{change_pct:+.2f}% за день" if change_pct is not None else "изменение за день неизвестно"

    # Уровни поддержки и сопротивления (упрощённые)
    recent_high = max(highs[-20:]) if len(highs) >= 20 else max(highs)
    recent_low = min(lows[-20:]) if len(lows) >= 20 else min(lows)

    # 52-недельный мин/макс — из недельных свечей за год, с запасным вариантом на дневные данные
    w52_highs = [c["high"] for c in weekly["candles"] if c.get("high")] if weekly["success"] else []
    w52_lows = [c["low"] for c in weekly["candles"] if c.get("low")] if weekly["success"] else []
    w52_high = max(w52_highs) if w52_highs else (max(highs) if highs else None)
    w52_low = min(w52_lows) if w52_lows else (min(lows) if lows else None)

    signals = []
    if rsi and rsi < 30: signals.append("перепродан_rsi")
    if rsi and rsi > 70: signals.append("перекуплен_rsi")
    if ma20 and ma50:
        if ma20 > ma50: signals.append("тренд_вверх")
        else: signals.append("тренд_вниз")
    if macd_val:
        if macd_val > 0: signals.append("macd_позитив")
        else: signals.append("macd_негатив")

    ta_data = {
        "ticker": ticker,
        "current_price": current_price,
        "change_pct": change_pct,
        "rsi": rsi,
        "ma20": ma20,
        "ma50": ma50,
        "macd": macd_val,
        "support": round(recent_low, 2),
        "resistance": round(recent_high, 2),
        "high_52w": round(w52_high, 2) if w52_high else None,
        "low_52w": round(w52_low, 2) if w52_low else None,
        "signals": signals,
    }

    # Claude интерпретирует простым языком
    prompt = f"""Объясни технический анализ акции простым языком без терминов.

Акция: {ticker}
Дата: {get_current_datetime()}
Текущая цена: {current_price} ₽ ({change_text})
RSI: {rsi} {'(сильно упала, может отскочить)' if rsi and rsi < 30 else '(сильно выросла, может откатиться)' if rsi and rsi > 70 else '(нейтрально)'}
MA20: {ma20} ₽, MA50: {ma50} ₽ {'(тренд вверх)' if ma20 and ma50 and ma20 > ma50 else '(тренд вниз)'}
MACD: {macd_val} {'(позитивный сигнал)' if macd_val and macd_val > 0 else '(негативный сигнал)'}
Поддержка: {recent_low:.2f} ₽, Сопротивление: {recent_high:.2f} ₽
52-нед. мин: {w52_low:.2f} ₽, макс: {w52_high:.2f} ₽

Напиши 3-4 предложения простым языком:
1. Что происходит с акцией сейчас
2. Стоит ли покупать/держать/продавать и почему
3. При какой цене входить (если покупать) и где выходить если не то

Без терминов RSI/MACD/MA — объясняй как человеку который не знает теханализ."""

    resp = claude.messages.create(
        model="claude-sonnet-4-5", max_tokens=300,
        messages=[{"role":"user","content":prompt}]
    )
    ta_data["analysis"] = resp.content[0].text
    ta_data["success"] = True
    return ta_data

def scan_portfolio_ta(tickers: list) -> list:
    """ТА анализ по всем бумагам портфеля. Возвращает только сильные сигналы."""
    strong_signals = []
    for ticker in tickers:
        result = analyze_ticker(ticker)
        if not result["success"]: continue
        signals = result.get("signals", [])
        is_strong = any(s in signals for s in ["перепродан_rsi","перекуплен_rsi"])
        if is_strong:
            strong_signals.append(result)
    return strong_signals
