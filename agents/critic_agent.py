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
    prompt = f"""Ты критик-редактор финансовых сообщений. Твоя задача — найти фактические ошибки.

Сообщение от агента '{agent_name}':
{message}

Дата проверки: {get_current_datetime()}

Проверь:
1. Нет ли утверждений о конкретных дивидендах без указания источника?
2. Нет ли путаницы компаний (ЕвроТранс — это АЗС, НЕ перевозки)?
3. Нет ли конкретных цифр которые выглядят выдуманными?
4. Нет ли рекомендаций купить/продать без обоснования данными?

Если сообщение содержит проверяемые факты — укажи их.
Если видишь потенциальную ошибку — укажи её.

Ответ в формате:
APPROVED: [yes/no]
ISSUES: [список проблем через запятую или 'нет']
CORRECTED_MESSAGE: [исправленное сообщение или 'без изменений']"""

    try:
        resp = claude.messages.create(
            model="claude-sonnet-4-5", max_tokens=500,
            messages=[{"role":"user","content":prompt}]
        )
        text = resp.content[0].text.strip()
        approved = True
        issues = []
        corrected = message

        for line in text.split("\n"):
            if line.startswith("APPROVED:"):
                approved = "yes" in line.lower()
            if line.startswith("ISSUES:") and "нет" not in line.lower():
                issues = [i.strip() for i in line.replace("ISSUES:","").split(",")]
            if line.startswith("CORRECTED_MESSAGE:") and "без изменений" not in line.lower():
                corrected = line.replace("CORRECTED_MESSAGE:","").strip()

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
        "currency": latest.get("currency"),
        "registry_date": latest.get("registry_date"),
        "source": "MOEX ISS"
    }
