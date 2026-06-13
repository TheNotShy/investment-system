"""
News Agent — мониторинг новостей 24/7.
Берёт новости только из Data Agent, оценивает через Claude.
Критичное — немедленно. Остальное — в порядке важности.
"""
import os
import sqlite3
from anthropic import Anthropic
from agents.data_agent import get_news, get_current_datetime

claude = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

PORTFOLIO_INFO = """Портфель:
- Сбербанк (SBER) — банк
- Сургутнефтегаз преф (SNGSP) — нефтедобыча, валютная кубышка
- Транснефть преф (TRNFP) — трубопроводный транспорт нефти
- НМТП (NMTP) — Новороссийский морской торговый порт
- X5 Group (X5) — продуктовый ритейл
- Озон Фармацевтика (OZPH) — производитель дженериков
- Новабев (BELU) — алкогольный холдинг
- Эталон (ETLN) — девелопер
- ЕвроТранс (EUTR) — сеть АЗС (НЕ перевозки!)
- ОФЗ — государственные облигации"""

PORTFOLIO_KEYWORDS = [
    "сбербанк","sber","сбер","сургутнефтегаз","surgut","транснефть","transneft",
    "нмтп","nmtp","x5","икс5","пятёрочка","перекрёсток","озон","ozon",
    "новабев","novabev","белуга","евротранс","eurotrans","эталон","etalon",
    "офз","ofz","ключевая ставка","цб рф","банк россии","центробанк",
    "дивиденд","buyback","байбек","санкции",
]

DB_PATH = "news_agent.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS seen_news (
        url TEXT PRIMARY KEY,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS scout_headlines (
        headline TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit(); conn.close()

def is_seen(url):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM seen_news WHERE url=?", (url,))
    found = c.fetchone() is not None
    conn.close(); return found

def mark_seen(url):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO seen_news (url) VALUES (?)", (url,))
    c.execute("DELETE FROM seen_news WHERE url NOT IN (SELECT url FROM seen_news ORDER BY created_at DESC LIMIT 2000)")
    conn.commit(); conn.close()

def save_headline(headline):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO scout_headlines (headline) VALUES (?)", (headline,))
    c.execute("DELETE FROM scout_headlines WHERE created_at < datetime('now','-1 day')")
    conn.commit(); conn.close()

def get_headlines():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT headline FROM scout_headlines WHERE created_at > datetime('now','-1 day')")
    rows = c.fetchall(); conn.close()
    return [r[0] for r in rows]

def score_and_analyze(source, title, summary=""):
    """Claude оценивает важность и влияние на портфель. Только факты из новости."""
    prompt = f"""Ты фильтр новостей. Оцени важность для инвестора.

{PORTFOLIO_INFO}

Источник: {source}
Заголовок: {title}
Описание: {summary[:400] if summary else '—'}
Дата анализа: {get_current_datetime()}

ВАЖНО: Опирайся ТОЛЬКО на то что написано в новости. Не додумывай факты.

Оцени по шкале 1-10:
- 9-10: критично (ставка ЦБ изменена, банкротство, крупные санкции, дивиденды отменены)
- 7-8: важно (отчётность, buyback, M&A, дивиденды объявлены)
- 5-6: интересно (общий рынок, макро)
- 1-4: не важно

Формат ответа СТРОГО:
SCORE: [число]
URGENCY: [critical/important/normal]
IMPACT: [2-3 предложения — что эта новость значит для портфеля, какие позиции затронуты]"""

    try:
        resp = claude.messages.create(
            model="claude-sonnet-4-5", max_tokens=250,
            messages=[{"role":"user","content":prompt}]
        )
        text = resp.content[0].text.strip()
        score, urgency, impact = 0, "normal", ""
        for line in text.split("\n"):
            if line.startswith("SCORE:"): score = int(line.replace("SCORE:","").strip())
            if line.startswith("URGENCY:"): urgency = line.replace("URGENCY:","").strip()
            if line.startswith("IMPACT:"): impact = line.replace("IMPACT:","").strip()
        return score, urgency, impact
    except:
        return 0, "normal", ""

def process_news():
    """
    Обработка новостей. Возвращает список важных новостей для отправки.
    [{score, urgency, source, title, impact, link}]
    """
    init_db()
    news_data = get_news(limit_per_feed=15)
    if not news_data["success"]: return []

    results = []
    for item in news_data["news"]:
        link = item["link"]
        if not link or is_seen(link): continue

        title = item["title"]
        summary = item["summary"]
        text_lower = (title + " " + summary).lower()
        is_ticker = item["is_ticker_feed"]

        if not is_ticker and not any(kw in text_lower for kw in PORTFOLIO_KEYWORDS):
            mark_seen(link); continue

        save_headline(title)
        score, urgency, impact = score_and_analyze(item["source"], title, summary)
        mark_seen(link)

        if score >= 7:
            results.append({
                "score": score,
                "urgency": urgency,
                "source": item["source"],
                "title": title,
                "impact": impact,
                "link": link,
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results

def format_news_message(news_item) -> str:
    """Форматирование сообщения о новости"""
    emoji = "🚨" if news_item["score"] >= 9 else "📢"
    short = f"{emoji} *{news_item['source']} | {news_item['score']}/10*\n*{news_item['title']}*\n\n📊 {news_item['impact']}\n\n🔗 {news_item['link']}"
    return short
