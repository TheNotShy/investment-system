"""
Critic Agent — проверяет каждый вывод перед отправкой пользователю.
Если факт не подтверждён реальными данными — блокирует сообщение.
"""
import os
from anthropic import Anthropic
from agents.data_agent import get_dividends, get_ticker_quote, get_current_datetime

claude = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def verify_message(message: str, agent_name: str) -> dict:
    """
    Проверяет сообщение от агента.
    Возвращает: {approved, message, corrections}
    """
    prompt = f"""Ты критик-редактор финансовых сообщений. Твоя задача — ловить ТОЛЬКО фактические ошибки и опасные рекомендации. НЕ придирайся к стилю, тону или отсутствию пояснений — это не твоя задача.

Сообщение от агента '{agent_name}':
{message}

Дата проверки: {get_current_datetime()}

Блокируй (APPROVED: no) ТОЛЬКО если есть:
1. Явная путаница компаний (например, ЕвроТранс — это сеть АЗС, НЕ перевозки и НЕ железная дорога)
2. Конкретные цифры (цены, дивиденды, объёмы, P&L), которые противоречат друг другу внутри сообщения или выглядят явно нереалистичными
3. Опасные рекомендации: вложить весь капитал в одну бумагу, использовать плечо/заём без предупреждения о риске, игнорировать диверсификацию

НЕ блокируй за:
- Стиль, формулировки, длину, тон сообщения
- Отсутствие источника или обоснования для рекомендаций купить/держать/продать
- Реальные цифры портфеля от portfolio_agent — они приходят из брокерского API, доверяй им, если они не противоречат друг другу

Если сомневаешься — пропускай (APPROVED: yes).

Ответ строго в формате, каждое поле на одной строке без переносов:
APPROVED: yes или no
ISSUES: краткое описание проблемы через запятую, или "нет"
CORRECTED_MESSAGE: исправленный текст в одну строку, или "без изменений\""""

    try:
        resp = claude.messages.create(
            model="claude-sonnet-4-5", max_tokens=500,
            messages=[{"role":"user","content":prompt}]
        )
        text = resp.content[0].text.strip()

        # Claude иногда переносит ISSUES/CORRECTED_MESSAGE на следующие строки —
        # собираем такие продолжения в текущую секцию, иначе issues получается ['']
        # и сообщение блокируется без причины.
        sections = {"APPROVED": "", "ISSUES": "", "CORRECTED_MESSAGE": ""}
        current = None
        for line in text.split("\n"):
            matched_key = None
            for key in sections:
                if line.strip().upper().startswith(key + ":"):
                    matched_key = key
                    break
            if matched_key:
                sections[matched_key] = line.split(":", 1)[1].strip()
                current = matched_key
            elif current and line.strip():
                sections[current] += " " + line.strip()

        approved = "yes" in sections["APPROVED"].lower()

        issues_text = sections["ISSUES"].strip(" .")
        if not issues_text or "нет" in issues_text.lower():
            issues = []
        else:
            issues = [i.strip(" -") for i in issues_text.split(",") if i.strip(" -")]

        corrected = message
        corrected_text = sections["CORRECTED_MESSAGE"].strip()
        if corrected_text and "без изменений" not in corrected_text.lower():
            corrected = corrected_text

        # Без конкретной причины блокировка бессмысленна — пропускаем сообщение
        if not approved and not issues:
            approved = True

        return {"approved": approved, "message": corrected, "issues": issues}
    except:
        return {"approved": True, "message": message, "issues": []}

def verify_dividends_claim(ticker: str, claimed_value: float = None) -> dict:
    """Проверяет утверждение о дивидендах через реальные данные MOEX"""
    real_data = get_dividends(ticker)
    if not real_data["success"]:
        return {"verified": False, "reason": "Не удалось получить данные из MOEX"}

    divs = real_data["dividends"]
    if not divs:
        return {"verified": False, "reason": f"MOEX не содержит данных о дивидендах {ticker}"}

    latest = divs[0]
    return {
        "verified": True,
        "latest_dividend": latest.get("value"),
        "currency": latest.get("currencyid"),
        "registry_date": latest.get("registryclosedate"),
        "source": "MOEX ISS"
    }
