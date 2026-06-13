"""
Orchestrator — управляет всеми агентами.
Решает приоритеты, собирает отчёты, форматирует сообщения.
"""
import os
import asyncio
from telegram import Bot
from agents.data_agent import is_trading_hours, get_current_datetime
from agents.portfolio_agent import morning_briefing, weekly_report, get_dca_recommendations, analyze_portfolio
from agents.news_agent import process_news, format_news_message
from agents.ta_agent import scan_portfolio_ta
from agents.volume_agent import check_volume_anomalies
from agents.scout_agent import find_opportunities
from agents.critic_agent import verify_message

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "1404413954"))

PORTFOLIO_TICKERS = ["SBER","SNGSP","TRNFP","NMTP","X5","OZPH","BELU","ETLN","EUTR"]

async def send(bot: Bot, text: str):
    """Отправить сообщение с проверкой через Critic Agent"""
    try:
        await bot.send_message(chat_id=OWNER_ID, text=text, parse_mode="Markdown")
    except Exception as e:
        print(f"Ошибка отправки: {e}")

async def run_news_cycle(bot: Bot):
    """Цикл новостей — каждые 2 минуты"""
    news_items = process_news()
    for item in news_items:
        msg = format_news_message(item)
        verified = verify_message(msg, "news_agent")
        final_msg = verified["message"]
        await send(bot, final_msg)
        await asyncio.sleep(1)

async def run_volume_cycle(bot: Bot):
    """Цикл объёмов — каждые 15 минут в торговые часы"""
    if not is_trading_hours(): return
    results = check_volume_anomalies()
    for r in results:
        msg = f"📊 *Аномальные объёмы*\n\n{r['analysis']}"
        verified = verify_message(msg, "volume_agent")
        await send(bot, verified["message"])

async def run_ta_cycle(bot: Bot):
    """ТА анализ — каждые 15 минут в торговые часы"""
    if not is_trading_hours(): return
    signals = scan_portfolio_ta(PORTFOLIO_TICKERS)
    for signal in signals:
        msg = f"📈 *Технический сигнал: {signal['ticker']}*\n\n{signal['analysis']}"
        verified = verify_message(msg, "ta_agent")
        await send(bot, verified["message"])

async def run_morning_briefing(bot: Bot):
    """Утренний брифинг — 9:00 МСК"""
    text = morning_briefing()
    verified = verify_message(text, "portfolio_agent")
    await send(bot, f"☀️ *Утренний брифинг — {get_current_datetime()}*\n\n{verified['message']}")

async def run_evening_scout(bot: Bot):
    """Вечерний скаутинг — 18:00 МСК"""
    results = find_opportunities()
    if results:
        msg = f"💡 *Вечерний скаутинг идей*\n\n{results[0]['ideas']}"
        verified = verify_message(msg, "scout_agent")
        await send(bot, verified["message"])

async def run_weekly_report(bot: Bot):
    """Еженедельный отчёт — пятница 18:00 МСК"""
    text = weekly_report()
    verified = verify_message(text, "portfolio_agent")
    await send(bot, f"📊 *Недельный отчёт — {get_current_datetime()}*\n\n{verified['message']}")

async def handle_dca_request(bot: Bot):
    """DCA рекомендации по запросу"""
    text = get_dca_recommendations()
    verified = verify_message(text, "portfolio_agent")
    await send(bot, f"💰 *Рекомендации для DCA*\n\n{verified['message']}")
