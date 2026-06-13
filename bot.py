"""
Telegram Bot — точка входа для всей системы.
"""
import os
import time as time_module
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from datetime import time
import pytz

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "1404413954"))
MOSCOW_TZ = pytz.timezone("Europe/Moscow")

from orchestrator import (
    run_news_cycle, run_volume_cycle, run_ta_cycle,
    run_morning_briefing, run_evening_scout, run_weekly_report, handle_dca_request
)
from agents.portfolio_agent import analyze_portfolio
from agents.ta_agent import analyze_ticker
from agents.data_agent import get_current_datetime

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я твой инвестиционный ИИ 📈\n\n"
        "/portfolio — портфель\n"
        "/report — брифинг\n"
        "/ta SBER — теханализ\n"
        "/dca — что купить\n"
        "/week — недельный отчёт\n"
        "/scout — новые идеи"
    )

async def portfolio_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Загружаю портфель... ⏳")
    data = analyze_portfolio()
    if not data["success"]:
        await update.message.reply_text(f"❌ {data['error']}")
        return
    text = f"📊 *Портфель — {get_current_datetime()}*\n\n💼 *{data['total']:,.0f} ₽*\nP&L: *{data['total_pl_rub']:+,.0f} ₽*\n\n"
    for pos in data["positions"]:
        em = "🟢" if pos["pl_pct"] >= 0 else "🔴"
        text += f"{em} *{pos['name']}*: {pos['pl_pct']:+.1f}%\n"
    if data["alerts"]:
        text += "\n⚠️ " + "\n".join(data["alerts"])
    await update.message.reply_text(text, parse_mode="Markdown")

async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Готовлю брифинг... ⏳")
    await run_morning_briefing(context.application.bot)

async def ta_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Укажи тикер: /ta SBER")
        return
    ticker = context.args[0].upper()
    await update.message.reply_text(f"Анализирую {ticker}... ⏳")
    result = analyze_ticker(ticker)
    if not result["success"]:
        await update.message.reply_text(f"❌ {result.get('error')}")
        return
    await update.message.reply_text(f"📈 *{ticker}*\n\n{result['analysis']}", parse_mode="Markdown")

async def dca_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Готовлю DCA рекомендации... ⏳")
    await handle_dca_request(context.application.bot)

async def week_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Готовлю недельный отчёт... ⏳")
    await run_weekly_report(context.application.bot)

async def scout_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Ищу новые идеи... ⏳")
    await run_evening_scout(context.application.bot)

async def free_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from anthropic import Anthropic
    claude = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    question = update.message.text
    await update.message.reply_text("Думаю... 🧠")
    data = analyze_portfolio()
    portfolio_text = f"\nПортфель: {data['total']:,.0f} ₽" if data["success"] else ""
    resp = claude.messages.create(
        model="claude-sonnet-4-5", max_tokens=700,
        system=f"Ты инвестиционный помощник. Дата: {get_current_datetime()}{portfolio_text}",
        messages=[{"role": "user", "content": question}]
    )
    await update.message.reply_text(f"🤖 {resp.content[0].text}")

async def job_news(context: ContextTypes.DEFAULT_TYPE):
    await run_news_cycle(context.bot)

async def job_volume_ta(context: ContextTypes.DEFAULT_TYPE):
    await run_volume_cycle(context.bot)
    await run_ta_cycle(context.bot)

async def job_morning(context: ContextTypes.DEFAULT_TYPE):
    await run_morning_briefing(context.bot)

async def job_evening_scout(context: ContextTypes.DEFAULT_TYPE):
    await run_evening_scout(context.bot)

async def job_weekly(context: ContextTypes.DEFAULT_TYPE):
    from datetime import datetime
    if datetime.now(MOSCOW_TZ).weekday() == 4:
        await run_weekly_report(context.bot)

def main():
    print("Запуск мульти-агентной системы...")
    time_module.sleep(3)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    jq = app.job_queue
    jq.run_daily(job_morning, time=time(9, 0, tzinfo=MOSCOW_TZ), name="morning")
    jq.run_daily(job_evening_scout, time=time(18, 0, tzinfo=MOSCOW_TZ), chat_id=OWNER_ID, name="scout")
    jq.run_daily(job_weekly, time=time(18, 30, tzinfo=MOSCOW_TZ), chat_id=OWNER_ID, name="weekly")
    jq.run_repeating(job_news, interval=120, first=30, chat_id=OWNER_ID, name="news")
    jq.run_repeating(job_volume_ta, interval=900, first=60, chat_id=OWNER_ID, name="volume_ta")

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("portfolio", portfolio_cmd))
    app.add_handler(CommandHandler("report", report_cmd))
    app.add_handler(CommandHandler("ta", ta_cmd))
    app.add_handler(CommandHandler("dca", dca_cmd))
    app.add_handler(CommandHandler("week", week_cmd))
    app.add_handler(CommandHandler("scout", scout_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, free_message))

    print("Мульти-агентная система запущена!")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()