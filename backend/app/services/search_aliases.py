"""검색 alias — 영문/별명을 종목코드로 매핑.

사용자가 'apple'이라고 쳐도 '애플(AAPL)'이 잡히도록.
"""
from __future__ import annotations

# 소문자 alias → ticker code
EN_TO_CODE: dict[str, str] = {
    # 메가캡 테크
    "apple": "AAPL",
    "microsoft": "MSFT",
    "nvidia": "NVDA",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "meta": "META",
    "facebook": "META",
    "tesla": "TSLA",
    "broadcom": "AVGO",
    "oracle": "ORCL",
    "netflix": "NFLX",
    "adobe": "ADBE",
    "intel": "INTC",
    "qualcomm": "QCOM",
    "amd": "AMD",
    "ibm": "IBM",
    "salesforce": "CRM",
    "palantir": "PLTR",
    "shopify": "SHOP",
    "uber": "UBER",
    "airbnb": "ABNB",
    "spotify": "SPOT",
    "reddit": "RDDT",
    "snowflake": "SNOW",
    "datadog": "DDOG",
    "cloudflare": "NET",
    "asml": "ASML",
    "tsmc": "TSM",
    "arm": "ARM",
    "micron": "MU",
    # 금융
    "jpmorgan": "JPM",
    "visa": "V",
    "mastercard": "MA",
    "berkshire": "BRK-B",
    "blackrock": "BLK",
    "goldman": "GS",
    "paypal": "PYPL",
    "coinbase": "COIN",
    "robinhood": "HOOD",
    # 소비/유통/헬스
    "walmart": "WMT",
    "costco": "COST",
    "nike": "NKE",
    "starbucks": "SBUX",
    "mcdonald": "MCD",
    "disney": "DIS",
    "coca": "KO",
    "pepsi": "PEP",
    "lilly": "LLY",
    "pfizer": "PFE",
    "moderna": "MRNA",
    # 에너지
    "exxon": "XOM",
    "chevron": "CVX",
    # 항공
    "delta": "DAL",
    "united": "UAL",
    "boeing": "BA",
    # 자동차
    "ford": "F",
    "rivian": "RIVN",
    # 게임
    "ea": "EA",
    # ETF
    "spy": "SPY",
    "qqq": "QQQ",
    "voo": "VOO",
    "ibit": "IBIT",
    "gld": "GLD",
    # 한글로도 검색되게 자주 쓰이는 영문 줄임말
    "bitcoin": "KRW-BTC",
    "btc": "KRW-BTC",
    "ethereum": "KRW-ETH",
    "eth": "KRW-ETH",
    "ripple": "KRW-XRP",
    "xrp": "KRW-XRP",
    "solana": "KRW-SOL",
    "sol": "KRW-SOL",
    "doge": "KRW-DOGE",
}
