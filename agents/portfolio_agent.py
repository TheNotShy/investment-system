"""
Portfolio Agent — следит за портфелем, считает риски, P&L, дивиденды.
Данные берёт только из Data Agent.
"""
import os
from anthropic import Anthropic
from agents.data_agent import get_portfolio, get_dividends, get_imoex, get_candles, get_current_datetime

claude = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

PORTFOLIO_TICKERS = ["SBER","SNGSP","TRNFP","NMTP","X5","OZPH","BELU","ETLN","EUTR"]

PORTFOLIO_INFO = """Портфель инвестора:
- Сбербанк (SBER) — банк
- Сургутнефтегаз преф (SNGSP) — нефтедобыча, валютная кубышка
- Транснефть преф (TRNFP) — трубопроводный транспорт нефти
- НМТП (NMTP) — Новороссийский морской торговый порт
- X5 Group (X5) — продуктовый ритейл, Пятёрочка и Перекрёсток
- Озон Фармацевтика (OZPH) — производитель дженериков
- Новабев (BELU) — алкогольный холдинг, Белуга
- Эталон (ETLN) — девелопер жилой недвижимости
- ЕвроТранс (EUTR) — сеть АЗС и топливный ритейл (НЕ перевозки!)
- ОФЗ — государственные облигации РФ"""

def analyze_portfolio() -> dict:
    """Полный анализ портфеля с реальными данными"""
    portfolio = get_portfolio()
    if not portfolio["success"]:
        return {"success": False, "error": portfolio["error"]}

    imoex = get_imoex()
    positions = portfolio["positions"]
    total = portfolio["total"]

    total_pl = sum(p["pl_rub"] for p in positions)
    total_pl_pct = round(sum(p["pl_pct"] for p in positions) / len(positions), 2) if positions else 0

    # Концентрация
    alerts = []
    for pos in positions:
        share = pos["current_value"] / total * 100 if total else 0
        pos["portfolio_share_pct"] = round(share, 2)
        if share > 20:
            alerts.append(f"⚠️ {pos['name']} занимает {share:.1f}% портфеля — превышен лимит 20%")
        if pos["pl_pct"] <= -10:
            alerts.append(f"🔴 {pos['name']} в убытке {pos['pl_pct']}% — рассмотреть действия")
        if pos["pl_pct"] >= 15:
            alerts.append(f"🟢 {pos['name']} +{pos['pl_pct']}% — достигнут порог фиксации прибыли")

    return {
        "success": True,
        "positions": positions,
        "total": total,
        "total_pl_rub": total_pl,
        "total_pl_pct": total_pl_pct,
        "imoex": imoex,
        "alerts": alerts,
        "timestamp": get_current_datetime(),
    }

def get_dca_recommendations() -> str:
    """Рекомендации что купить при пополнении на 40-50к"""
    portfolio = get_portfolio()
    if not portfolio["success"]:
        return "Ошибка получения портфеля"

    positions = portfolio["positions"]
    total = portfolio["total"]

    portfolio_text = f"Портфель ({total:,.0f} ₽):\n"
    for pos in positions:
        share = pos["current_value"] / total * 100 if total else 0
        portfolio_text += f"- {pos['name']}: {share:.1f}%, P&L {pos['pl_pct']:+.1f}%\n"

    prompt = f"""Инвестор делает DCA пополнение на 40-50 тыс. рублей.

{PORTFOLIO_INFO}

{portfolio_text}

Стратегия: умеренный риск, цель 20%+ годовых, максимум 20% на одну бумагу.

Предложи конкретный список что купить при пополнении на 40-50 тыс. рублей.
Учти текущие доли в портфеле. Объясни почему именно эти бумаги.
Ответ простым языком без терминов."""

    resp = claude.messages.create(
        model="claude-sonnet-4-5", max_tokens=600,
        messages=[{"role":"user","content":prompt}]
    )
    return resp.content[0].text

def get_dividend_calendar() -> dict:
    """Дивидендный календарь по бумагам портфеля"""
    results = {}
    for ticker in PORTFOLIO_TICKERS:
        div_data = get_dividends(ticker)
        if div_data["success"] and div_data["dividends"]:
            results[ticker] = div_data["dividends"][:3]
    return {"success": True, "calendar": results, "timestamp": get_current_datetime()}

def morning_briefing() -> str:
    """Утренний брифинг с реальными данными"""
    data = analyze_portfolio()
    if not data["success"]:
        return f"❌ Ошибка: {data['error']}"

    imoex_text = ""
    if data["imoex"]["success"]:
        imoex_val = data["imoex"]["value"]
        imoex_chg = data["imoex"]["change_pct"]
        imoex_text = f"IMOEX: {imoex_val:,.0f} ({imoex_chg:+.2f}%)" if imoex_chg else f"IMOEX: {imoex_val:,.0f}"

    portfolio_text = f"Портфель: {data['total']:,.0f} ₽ | P&L: {data['total_pl_rub']:+,.0f} ₽ ({data['total_pl_pct']:+.1f}%)\n{imoex_text}\n\nПозиции:\n"
    for pos in data["positions"]:
        emoji = "🟢" if pos["pl_pct"] >= 0 else "🔴"
        portfolio_text += f"{emoji} {pos['name']}: {pos['pl_pct']:+.1f}% ({pos['pl_rub']:+,.0f} ₽)\n"

    prompt = f"""Ты инвестиционный помощник. Составь краткий утренний брифинг.

Дата: {get_current_datetime()}
{portfolio_text}

Алерты:
{chr(10).join(data['alerts']) if data['alerts'] else 'Нет алертов'}

Напиши коротко: что важно сегодня, на что обратить внимание.
Максимум 5 пунктов. Простым языком без терминов."""

    resp = claude.messages.create(
        model="claude-sonnet-4-5", max_tokens=500,
        messages=[{"role":"user","content":prompt}]
    )
    return resp.content[0].text

def weekly_report() -> str:
    """Еженедельный отчёт с P&L и сравнением с IMOEX"""
    data = analyze_portfolio()
    if not data["success"]:
        return f"❌ Ошибка: {data['error']}"

    portfolio_text = f"Портфель: {data['total']:,.0f} ₽\nP&L: {data['total_pl_rub']:+,.0f} ₽ ({data['total_pl_pct']:+.1f}%)\n\n"

    imoex_chg = data["imoex"].get("change_pct") if data["imoex"]["success"] else None

    div_cal = get_dividend_calendar()
    div_text = ""
    for ticker, divs in div_cal.get("calendar", {}).items():
        if divs:
            last = divs[0]
            div_text += f"- {ticker}: {last.get('value')} {last.get('currencyid')} (отсечка: {last.get('registryclosedate')})\n"

    prompt = f"""Составь еженедельный инвестиционный отчёт.

{portfolio_text}
Индекс IMOEX за период: {imoex_chg:+.2f}% (сегодня)

Дивиденды (последние данные из MOEX):
{div_text or 'Нет данных'}

Алерты недели:
{chr(10).join(data['alerts']) if data['alerts'] else 'Нет алертов'}

Напиши структурированный недельный отчёт:
1. P&L за неделю и сравнение с IMOEX
2. Лучшие и худшие позиции
3. Ожидаемые дивиденды
4. Что сделать на следующей неделе

Простым языком. Цифры в рублях и процентах."""

    resp = claude.messages.create(
        model="claude-sonnet-4-5", max_tokens=800,
        messages=[{"role":"user","content":prompt}]
    )
    return resp.content[0].text
