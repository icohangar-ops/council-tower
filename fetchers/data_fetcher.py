"""Data fetchers for the Council pipeline.

Fetches real-world data to inform deliberations. Supports:
  - SEC filing data (via SEC EDGAR API)
  - Commodity price data (via Yahoo Finance)
  - Market news summaries
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx


@dataclass
class FetchedData:
    """A container for fetched data ready for deliberation."""
    source: str
    topic_context: str
    raw_data: dict | list
    fetched_at: datetime = None

    def __post_init__(self):
        self.fetched_at = self.fetched_at or datetime.utcnow()

    def to_context_string(self) -> str:
        """Format fetched data as a context string for the deliberation prompt."""
        return f"[{self.source}] {self.topic_context}"


async def fetch_sec_filing(
    ticker: str,
    filing_type: str = "10-K",
    year: Optional[int] = None,
) -> FetchedData:
    """Fetch the most recent SEC filing for a given ticker.

    Uses the SEC EDGAR full-text search API (no API key required).

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL").
        filing_type: Type of filing (10-K, 10-Q, 8-K, DEF 14A).
        year: Optional year to search for (defaults to most recent).

    Returns:
        FetchedData with the filing summary.
    """
    year = year or datetime.now().year
    query = f'{ticker} AND "{filing_type}" AND "{year}"'

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            "https://efts.sec.gov/LATEST/search-index?q=" + query,
            headers={
                "User-Agent": "Council Tower Pipeline council@tower.dev",
                "Accept": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()

    filings = data.get("filings", []) if isinstance(data, dict) else []
    if filings:
        latest = filings[0] if isinstance(filings, list) else filings
        context = (
            f"SEC {filing_type} filing for {ticker}. "
            f"File: {latest.get('fileNum', 'N/A')}. "
            f"Date: {latest.get('fileDate', 'N/A')}. "
            f"Description: "
            f"{latest.get('displayNames', [''])[0] if latest.get('displayNames') else 'N/A'}."
        )
        return FetchedData(
            source="SEC_EDGAR",
            topic_context=context,
            raw_data=data,
        )

    return FetchedData(
        source="SEC_EDGAR",
        topic_context=f"No recent {filing_type} filings found for {ticker} in {year}.",
        raw_data=data,
    )


async def fetch_commodity_prices(
    symbol: str = "GC=F",
    period: str = "5d",
) -> FetchedData:
    """Fetch recent commodity prices via Yahoo Finance.

    Args:
        symbol: Yahoo Finance symbol (GC=F for gold, SI=F for silver, CL=F for oil).
        period: Time period (1d, 5d, 1mo, 3mo, 6mo, 1y).

    Returns:
        FetchedData with price context.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            f"?interval=1d&range={period}"
        )
        response = await client.get(
            url,
            headers={
                "User-Agent": "Council Tower Pipeline council@tower.dev",
            },
        )
        response.raise_for_status()
        data = response.json()

    result = data.get("chart", {}).get("result", [])
    if result:
        meta = result[0].get("meta", {})
        price = meta.get("regularMarketPrice", 0)
        prev_close = meta.get("chartPreviousClose", 0)
        change = price - prev_close
        pct_change = (change / prev_close * 100) if prev_close else 0

        timestamps = result[0].get("timestamp", [])
        closes = (
            result[0]
            .get("indicators", {})
            .get("quote", [{}])[0]
            .get("close", [])
        )

        price_series = [
            f"  {datetime.fromtimestamp(t).strftime('%Y-%m-%d')}: {c:.2f}"
            for t, c in zip(timestamps[-5:], closes[-5:])
            if c is not None
        ]

        context = (
            f"Commodity {symbol}: Current price ${price:.2f}, "
            f"Previous close ${prev_close:.2f}, "
            f"Change ${change:+.2f} ({pct_change:+.2f}%).\n"
            f"Recent prices:\n" + "\n".join(price_series)
        )
        return FetchedData(
            source="YAHOO_FINANCE",
            topic_context=context,
            raw_data=data,
        )

    return FetchedData(
        source="YAHOO_FINANCE",
        topic_context=f"No price data found for {symbol}.",
        raw_data=data,
    )


async def fetch_market_news(
    symbols: str = "",
    limit: int = 5,
) -> FetchedData:
    """Fetch recent market news summaries.

    Args:
        symbols: Comma-separated stock symbols to filter by.
        limit: Maximum number of news items.

    Returns:
        FetchedData with news context.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        params: dict = {"count": limit}
        if symbols:
            params["symbols"] = symbols

        api_key = os.getenv("NEWS_API_KEY", "")
        if not api_key:
            return FetchedData(
                source="NEWS_API",
                topic_context="News API key not configured. Skipping news fetch.",
                raw_data={},
            )

        response = await client.get(
            "https://newsapi.org/v2/everything",
            params={**params, "apiKey": api_key, "language": "en"},
            headers={"User-Agent": "Council Tower Pipeline council@tower.dev"},
        )
        response.raise_for_status()
        data = response.json()

    articles = data.get("articles", [])
    headlines = []
    for article in articles[:limit]:
        title = article.get("title", "")
        description = article.get("description", "") or ""
        source = article.get("source", {}).get("name", "")
        headlines.append(f"- [{source}] {title}. {description[:200]}")

    context = (
        "Recent market news:\n" + "\n".join(headlines)
        if headlines
        else "No news available."
    )

    return FetchedData(
        source="NEWS_API",
        topic_context=context,
        raw_data=data,
    )


async def fetch_context_for_topic(
    topic: str, domain: str = "general"
) -> str:
    """Smart-fetch context data based on topic and domain keywords.

    Attempts to identify tickers/symbols in the topic and fetch relevant data.

    Args:
        topic: The deliberation topic string.
        domain: The domain (finance, strategy, general).

    Returns:
        A formatted context string combining all fetched data sources.
    """
    contexts: list[str] = []

    tickers = re.findall(r"\b([A-Z]{2,5})\b", topic)
    commodity_map = {
        "GOLD": "GC=F",
        "SILVER": "SI=F",
        "OIL": "CL=F",
        "COPPER": "HG=F",
        "NATURAL GAS": "NG=F",
    }

    # Try commodity fetch if topic mentions commodities
    topic_upper = topic.upper()
    for commodity, symbol in commodity_map.items():
        if commodity in topic_upper:
            try:
                data = await fetch_commodity_prices(symbol)
                contexts.append(data.topic_context)
            except Exception as e:
                contexts.append(f"[{commodity}] Price fetch failed: {e}")

    # Try SEC fetch if we detected a plausible ticker and domain is finance
    if domain == "finance" and tickers:
        for ticker in tickers[:1]:
            try:
                data = await fetch_sec_filing(ticker)
                contexts.append(data.topic_context)
            except Exception as e:
                contexts.append(f"[SEC:{ticker}] Filing fetch failed: {e}")

    if not contexts:
        contexts.append("No external data sources available for this topic.")

    return "\n\n".join(contexts)
