"""
Orchestrator — управляет всеми агентами.
Все тяжёлые операции запускаются в thread pool чтобы не блокировать event loop.
"""
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from telegram import Bot
from agents.data_agent import is_trading_hours, get_current_datetime
from agents.portfolio_agent import morning_briefing, weekly_report, get_dca_recommendations, analyze_portfolio
from agents.news_agent import process_news, format_news_message
from agents.ta_agent import scan_portfolio_ta
from agents.volume_agent import check_volume_anomalies
from agents.scout_agent import find_opportunities
from agents.critic_agent import verify_message

OWNER_ID = int(os.getenv("OWNER_ID", "1404413954"))
PORTFOLIO_TICKERS = ["SBER","SNGSP","TRNFP","NMTP","X5","OZPH","BELU","ETLN","EUTR"]

executor = ThreadPoolExecutor(max_workers=4)

async def run_in_thread(func, *args):
    """Запускает синхронную функцию в thread pool"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, func, *args)

async def send(bot: Bot, text: str):
    try:
        # Разбиваем длинные сообщения
        if len(text) > 4000:
            text = text[:4000] + "..."
        await bot.send_message(chat_id=OWNER_ID, text=text, parse_mode="Markdown")
    except Exception as e:
        try:
            await bot.send_message(chat_id=OWNER_ID, text=text)
        except Exception as e2:
            print(f"Ошибка отправки: {e2}")

async def run_news_cycle(bot: Bot):
    """Цикл новостей — каждые 2 минуты"""
    try:
        news_items = await run_in_thread(process_news)
        for item in news_items[:3]:  # Максимум 3 новости за цикл
            msg = format_news_message(item)
            await send(bot, msg)
            await asyncio.sleep(1)
    except Exception as e:
        print(f"Ошибка news_cycle: {e}")

async def run_volume_cycle(bot: Bot):
    """Цикл объёмов — каждые 15 минут в торговые часы"""
    try:
        if not is_trading_hours():
            return
        results = await run_in_thread(check_volume_anomalies)
        for r in results:
            msg = f"📊 *Аномальные объёмы*\n\n{r['analysis']}"
            await send(bot, msg)
    except Exception as e:
        print(f"Ошибка volume_cycle: {e}")

async def run_ta_cycle(bot: Bot):
    """ТА анализ — каждые 15 минут в торговые часы"""
    try:
        if not is_trading_hours():
            return
        signals = await run_in_thread(scan_portfolio_ta, PORTFOLIO_TICKERS)
        for signal in signals[:2]:  # Максимум 2 сигнала
            msg = f"📈 *Технический сигнал: {signal['ticker']}*\n\n{signal['analysis']}"
            await send(bot, msg)
    except Exception as e:
        print(f"Ошибка ta_cycle: {e}")

async def run_morning_briefing(bot: Bot):
    """Утренний брифинг — 9:00 МСК"""
    try:
        text = await run_in_thread(morning_briefing)
        await send(bot, f"☀️ *Утренний брифинг — {get_current_datetime()}*\n\n{text}")
    except Exception as e:
        await send(bot, f"❌ Ошибка брифинга: {e}")

async def run_evening_scout(bot: Bot):
    """Вечерний скаутинг — 18:00 МСК"""
    try:
        results = await run_in_thread(find_opportunities)
        if results:
            msg = f"💡 *Вечерний скаутинг идей*\n\n{results[0]['ideas']}"
            await send(bot, msg)
        else:
            await send(bot, "💡 *Скаутинг*: Сильных идей на сегодня нет.")
    except Exception as e:
        print(f"Ошибка scout: {e}")

async def run_weekly_report(bot: Bot):
    """Еженедельный отчёт — пятница 18:30"""
    try:
        text = await run_in_thread(weekly_report)
        await send(bot, f"📊 *Недельный отчёт — {get_current_datetime()}*\n\n{text}")
    except Exception as e:
        await send(bot, f"❌ Ошибка отчёта: {e}")

async def handle_dca_request(bot: Bot):
    """DCA рекомендации"""
    try:
        text = await run_in_thread(get_dca_recommendations)
        await send(bot, f"💰 *Рекомендации для DCA*\n\n{text}")
    except Exception as e:
        await send(bot, f"❌ Ошибка DCA: {e}")