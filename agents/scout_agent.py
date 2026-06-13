"""
Scout Agent — поиск новых инвестиционных идей.
Срабатывает только при сильном комбинированном сигнале.
"""
import os
from anthropic import Anthropic
from agents.data_agent import get_ticker_quote, get_dividends, get_candles, get_current_datetime
from agents.news_agent import get_headlines
from agents.ta_agent import calculate_rsi, calculate_ma

claude = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

PORTFOLIO_TICKERS = {"SBER","SNGSP","TRNFP","NMTP","X5","OZPH","BELU","ETLN","EUTR"}

STRATEGY = """Стратегия инвестора:
- Цель: 20%+ годовых
- Горизонт: несколько месяцев
- Риск: умеренный, максимум 10% убытка в год
- DCA каждые 2 недели по 40-50 тыс. рублей
- Интерес: акции и облигации, все секторы, второй эшелон и IPO если есть сильная идея"""

def find_opportunities() -> list:
    """
    Ищет новые идеи на рынке.
    Возвращает список идей только при сильном комбинированном сигнале.
    """
    from agents.data_agent import TOP50_TICKERS
    headlines = get_headlines()
    candidates = []

    for ticker in TOP50_TICKERS:
        if ticker in PORTFOLIO_TICKERS: continue
        try:
            quote = get_ticker_quote(ticker)
            if not quote["success"] or not quote.get("price"): continue

            candles = get_candles(ticker, days=60, interval="day")
            if not candles["success"] or len(candles["candles"]) < 15: continue

            closes = [c["close"] for c in candles["candles"] if c.get("close")]
            lows = [c["low"] for c in candles["candles"] if c.get("low")]

            rsi = calculate_rsi(closes)
            ma20 = calculate_ma(closes, 20)
            ma50 = calculate_ma(closes, min(50, len(closes)))
            low_52w = min(lows) if lows else None

            signals = []
            if rsi and rsi < 35: signals.append("перепродан")
            if ma20 and ma50 and ma20 > ma50: signals.append("тренд_вверх")
            if low_52w and quote["price"] and quote["price"] < low_52w * 1.05:
                signals.append("52w_минимум")

            # Добавляем только если есть минимум 2 сигнала
            if len(signals) >= 2:
                candidates.append({
                    "ticker": ticker,
                    "price": quote["price"],
                    "change_pct": quote.get("change_pct"),
                    "rsi": rsi,
                    "signals": signals,
                })
        except: pass

    if not candidates and not headlines:
        return []

    headlines_text = "\n".join(f"- {h}" for h in headlines[:30]) if headlines else "Нет новостей"
    candidates_text = "\n".join(
        f"- {c['ticker']}: цена {c['price']} ₽, RSI {c['rsi']}, сигналы: {', '.join(c['signals'])}"
        for c in candidates[:10]
    ) if candidates else "Нет технических кандидатов"

    prompt = f"""Ты инвестиционный аналитик. Найди интересные идеи для инвестора.

{STRATEGY}

Технические кандидаты (бумаги с сигналами):
{candidates_text}

Новости за сегодня:
{headlines_text}

Дата: {get_current_datetime()}

Предложи максимум 3 идеи которых НЕТ в текущем портфеле инвестора.
Предлагай ТОЛЬКО если есть реально сильное обоснование — комбинация технического сигнала, новости или фундаментала.

Для каждой идеи:
1. Тикер и название компании
2. Почему интересно именно сейчас (конкретные факты)
3. Потенциал и целевая цена
4. Главный риск

Если сильных идей нет — так и скажи честно. Не выдумывай."""

    resp = claude.messages.create(
        model="claude-sonnet-4-5", max_tokens=700,
        messages=[{"role":"user","content":prompt}]
    )
    return [{"ideas": resp.content[0].text, "candidates": candidates}]
