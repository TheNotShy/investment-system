"""
Data Agent — единственный источник верифицированных данных.
Все остальные агенты берут данные только отсюда.
"""
import os
import requests
import feedparser
from datetime import datetime, timedelta, time
from typing import Optional
import pytz

TINVEST_TOKEN = os.getenv("TINVEST_TOKEN")
MOSCOW_TZ = pytz.timezone("Europe/Moscow")
TINVEST_HEADERS = {
    "Authorization": f"Bearer {TINVEST_TOKEN}",
    "Content-Type": "application/json",
}

RSS_FEEDS = [
    ("РБК", "https://rssexport.rbc.ru/rbcnews/news/30/full.rss"),
    ("Интерфакс", "https://www.interfax.ru/rss.asp"),
    ("MOEX Новости", "https://iss.moex.com/iss/news.rss"),
    ("MOEX Раскрытие", "https://www.moex.com/export/news.aspx?cat=100"),
    ("MOEX: Сбербанк", "https://iss.moex.com/iss/news.rss?security=SBER"),
    ("MOEX: Сургутнефтегаз", "https://iss.moex.com/iss/news.rss?security=SNGSP"),
    ("MOEX: Транснефть", "https://iss.moex.com/iss/news.rss?security=TRNFP"),
    ("MOEX: НМТП", "https://iss.moex.com/iss/news.rss?security=NMTP"),
    ("MOEX: X5", "https://iss.moex.com/iss/news.rss?security=X5"),
    ("MOEX: Новабев", "https://iss.moex.com/iss/news.rss?security=BELU"),
    ("MOEX: Эталон", "https://iss.moex.com/iss/news.rss?security=ETLN"),
    ("MOEX: ЕвроТранс", "https://iss.moex.com/iss/news.rss?security=EUTR"),
    ("ЦБ РФ", "https://cbr.ru/rss/RssPress"),
    ("Cbonds", "https://cbonds.ru/news/rss/"),
    ("Smart-Lab", "https://smart-lab.ru/rss.php"),
    ("Финам", "https://www.finam.ru/analysis/conews/rsspoint/"),
    ("БКС Экспресс", "https://bcs-express.ru/rss"),
]

TOP50_TICKERS = [
    "SBER","GAZP","LKOH","GMKN","NVTK","ROSN","SNGS","SNGSP","TATN","TATNP",
    "MTSS","MGNT","YNDX","OZON","AFLT","VTBR","MOEX","ALRS","PHOR","NLMK",
    "MAGN","CHMF","PIKK","AFKS","FEES","HYDR","IRAO","RUAL","TRNFP","NMTP",
    "X5","BELU","ETLN","EUTR","OZPH","SMLT","FIXP","VKCO","TCSG","FLOT",
    "GLTR","MDMG","MVID","LSRG","UPRO","MSNG","DSKY","SPBE","GEMC","OZPH",
]

def _to_float(money):
    if not money: return 0.0
    return int(money.get("units",0)) + int(money.get("nano",0)) / 1_000_000_000

def get_account_id():
    try:
        resp = requests.post(
            "https://invest-public-api.tinkoff.ru/rest/tinkoff.public.invest.api.contract.v1.UsersService/GetAccounts",
            headers=TINVEST_HEADERS, json={}, timeout=10)
        accounts = resp.json().get("accounts",[])
        return accounts[0]["id"] if accounts else None
    except: return None

def get_instrument_name(figi):
    try:
        resp = requests.post(
            "https://invest-public-api.tinkoff.ru/rest/tinkoff.public.invest.api.contract.v1.InstrumentsService/GetInstrumentBy",
            headers=TINVEST_HEADERS,
            json={"idType":"INSTRUMENT_ID_TYPE_FIGI","id":figi}, timeout=5)
        if resp.status_code == 200:
            return resp.json().get("instrument",{}).get("name", figi)
    except: pass
    return figi

def get_portfolio():
    """Портфель из T-Инвестиции с реальными ценами и P&L"""
    account_id = get_account_id()
    if not account_id: return {"success":False,"error":"Счёт не найден"}
    try:
        resp = requests.post(
            "https://invest-public-api.tinkoff.ru/rest/tinkoff.public.invest.api.contract.v1.OperationsService/GetPortfolio",
            headers=TINVEST_HEADERS,
            json={"accountId":account_id,"currency":"RUB"}, timeout=10)
        if resp.status_code != 200: return {"success":False,"error":f"Ошибка API: {resp.status_code}"}
        data = resp.json()
        raw = data.get("positions",[])
        total = _to_float(data.get("totalAmountPortfolio"))
        positions = []
        for pos in raw:
            figi = pos.get("figi","")
            name = get_instrument_name(figi)
            qty = _to_float(pos.get("quantity"))
            price = _to_float(pos.get("currentPrice"))
            avg = _to_float(pos.get("averagePositionPrice"))
            pl = _to_float(pos.get("expectedYield"))
            pl_pct = round((price-avg)/avg*100,2) if avg else 0
            positions.append({"figi":figi,"name":name,"qty":qty,"current_price":price,
                "avg_price":avg,"current_value":price*qty,"pl_rub":pl,"pl_pct":pl_pct})
        return {"success":True,"positions":positions,"total":total,
                "timestamp":datetime.now(MOSCOW_TZ).isoformat()}
    except Exception as e: return {"success":False,"error":str(e)}

def get_candles(ticker, days=30, interval="day"):
    """Свечи по тикеру через MOEX ISS"""
    imap = {"hour":60,"day":24,"week":7}
    mi = imap.get(interval,24)
    dt = datetime.now(MOSCOW_TZ)
    df = (dt-timedelta(days=days)).strftime("%Y-%m-%d")
    dt_str = dt.strftime("%Y-%m-%d")
    try:
        url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{ticker}/candles.json?from={df}&till={dt_str}&interval={mi}&iss.meta=off"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200: return {"success":False,"ticker":ticker,"error":f"MOEX: {resp.status_code}"}
        data = resp.json()
        cols = data["candles"]["columns"]
        rows = data["candles"]["data"]
        candles = [dict(zip(cols,r)) for r in rows]
        return {"success":True,"ticker":ticker,"candles":candles,"interval":interval}
    except Exception as e: return {"success":False,"ticker":ticker,"error":str(e)}

def get_ticker_quote(ticker):
    """Текущая цена, изменение за день и объём"""
    try:
        url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{ticker}.json?iss.only=securities,marketdata&iss.meta=off&securities.columns=SECID,PREVPRICE&marketdata.columns=SECID,LAST,VALTODAY"
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200: return {"success":False,"ticker":ticker,"error":f"MOEX: {resp.status_code}"}
        data = resp.json()
        sec = data.get("securities",{}).get("data",[])
        mkt = data.get("marketdata",{}).get("data",[])
        if not sec or not mkt: return {"success":False,"ticker":ticker,"error":"Нет данных"}
        prev = sec[0][1]; cur = mkt[0][1]; vol = mkt[0][2]
        chg = round((cur-prev)/prev*100,2) if prev and cur else None
        return {"success":True,"ticker":ticker,"price":cur,"prev_price":prev,
                "change_pct":chg,"volume_rub":vol,"timestamp":datetime.now(MOSCOW_TZ).isoformat()}
    except Exception as e: return {"success":False,"ticker":ticker,"error":str(e)}

def get_dividends(ticker):
    """История дивидендов из MOEX ISS — только реальные данные"""
    try:
        url = f"https://iss.moex.com/iss/securities/{ticker}/dividends.json?iss.meta=off"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200: return {"success":False,"ticker":ticker,"error":f"MOEX: {resp.status_code}"}
        data = resp.json()
        cols = data["dividends"]["columns"]
        rows = data["dividends"]["data"]
        divs = [dict(zip(cols,r)) for r in rows]
        divs.sort(key=lambda x: x.get("registryclosedate") or "", reverse=True)
        return {"success":True,"ticker":ticker,"dividends":divs}
    except Exception as e: return {"success":False,"ticker":ticker,"error":str(e)}

def get_imoex():
    """Текущее значение индекса IMOEX"""
    try:
        url = "https://iss.moex.com/iss/engines/stock/markets/index/boards/SNDX/securities/IMOEX.json?iss.only=marketdata&iss.meta=off&marketdata.columns=SECID,CURRENTVALUE,LASTTOPREVPRICE"
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200: return {"success":False,"error":f"MOEX: {resp.status_code}"}
        rows = resp.json().get("marketdata",{}).get("data",[])
        if not rows: return {"success":False,"error":"Нет данных"}
        return {"success":True,"value":rows[0][1],"change_pct":round(rows[0][2],2) if rows[0][2] else None,
                "timestamp":datetime.now(MOSCOW_TZ).isoformat()}
    except Exception as e: return {"success":False,"error":str(e)}

def get_news(limit_per_feed=10):
    """Свежие новости из всех RSS-лент"""
    all_news = []
    for source_name, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:limit_per_feed]:
                all_news.append({"source":source_name,"title":entry.get("title",""),
                    "link":entry.get("link",""),"summary":entry.get("summary","")[:300],
                    "is_ticker_feed":"security=" in url})
        except: pass
    return {"success":True,"news":all_news,"count":len(all_news)}

def get_cbr_news():
    """Последние новости ЦБ РФ"""
    try:
        feed = feedparser.parse("https://cbr.ru/rss/RssPress")
        news = [{"title":e.get("title",""),"link":e.get("link","")} for e in feed.entries[:10]]
        return {"success":True,"news":news}
    except Exception as e: return {"success":False,"error":str(e)}

def is_trading_hours():
    """Торговые часы MOEX: 10:00-18:50 МСК пн-пт"""
    now = datetime.now(MOSCOW_TZ)
    if now.weekday() >= 5: return False
    return time(10,0) <= now.time() <= time(18,50)

def get_current_datetime():
    return datetime.now(MOSCOW_TZ).strftime("%d.%m.%Y %H:%M МСК")
