"""
Volume Agent — мониторинг аномальных объёмов торгов.
Работает только в торговые часы. Топ-50 акций MOEX.
"""
import os
import sqlite3
from anthropic import Anthropic
from agents.data_agent import get_ticker_quote, is_trading_hours, TOP50_TICKERS, get_current_datetime

claude = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
DB_PATH = "volume_agent.db"

PORTFOLIO_INFO = """Портфель инвестора:
Сбербанк (SBER), Сургутнефтегаз преф (SNGSP), Транснефть преф (TRNFP),
НМТП (NMTP), X5 Group (X5), Озон Фармацевтика (OZPH), Новабев (BELU),
Эталон (ETLN), ЕвроТранс (EUTR — сеть АЗС, НЕ перевозки), ОФЗ"""

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS volume_history (
        ticker TEXT, volume REAL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit(); conn.close()

def save_volume(ticker, volume):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO volume_history (ticker,volume) VALUES (?,?)", (ticker, volume))
    c.execute("DELETE FROM volume_history WHERE created_at < datetime('now','-7 days')")
    conn.commit(); conn.close()

def get_avg_volume(ticker):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT AVG(volume) FROM volume_history
        WHERE ticker=? AND created_at < datetime('now','-1 day')
        AND created_at > datetime('now','-6 days')""", (ticker,))
    row = c.fetchone(); conn.close()
    return row[0] if row and row[0] else None

def check_volume_anomalies() -> list:
    """Проверка аномальных объёмов. Только в торговые часы."""
    if not is_trading_hours(): return []
    init_db()
    anomalies = []
    for ticker in TOP50_TICKERS:
        try:
            quote = get_ticker_quote(ticker)
            if not quote["success"]: continue
            vol = quote.get("volume_rub")
            if not vol or vol == 0: continue
            save_volume(ticker, vol)
            avg = get_avg_volume(ticker)
            if avg and avg > 0:
                ratio = vol / avg
                if ratio >= 3.0:
                    anomalies.append({
                        "ticker": ticker,
                        "volume": vol,
                        "avg_volume": avg,
                        "ratio": round(ratio, 1),
                        "price": quote.get("price"),
                        "change_pct": quote.get("change_pct"),
                    })
        except: pass

    if not anomalies: return []

    # Claude анализирует только если есть фундаментальная причина
    anomaly_text = "\n".join(
        f"- {a['ticker']}: объём {a['volume']/1e6:.1f}M ₽ (норма {a['avg_volume']/1e6:.1f}M ₽), x{a['ratio']}, цена {a['price']} ₽ ({a['change_pct']:+.1f}%)"
        for a in anomalies
    )
    prompt = f"""Аномальные объёмы торгов на Московской бирже:

{anomaly_text}

{PORTFOLIO_INFO}

Дата: {get_current_datetime()}

Для каждой бумаги оцени:
1. Есть ли вероятная фундаментальная причина (событие, новость) или это случайный шум?
2. Есть ли бумага в портфеле инвестора — если да, что это значит для него?
3. Если нет в портфеле — стоит ли обратить внимание как на новую идею?

Отвечай только по бумагам где есть реальный повод для внимания.
Простым языком без терминов."""

    resp = claude.messages.create(
        model="claude-sonnet-4-5", max_tokens=500,
        messages=[{"role":"user","content":prompt}]
    )
    return [{"anomalies": anomalies, "analysis": resp.content[0].text}]
