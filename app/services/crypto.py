from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

import httpx
from fastapi import HTTPException, status

from ..config import settings
from ..schemas import CryptoDashboardResponse, MarketChartPoint, MarketMover, PortfolioAsset

_DASHBOARD_CACHE: Dict[str, Tuple[datetime, CryptoDashboardResponse]] = {}
_DASHBOARD_CACHE_TTL = timedelta(minutes=3)

_CHART_COIN_ID = "bitcoin"
_CHART_DAYS = 7
_PORTFOLIO_ALLOCATION: Dict[str, float] = {
    "bitcoin": 0.45,
    "ethereum": 2.1,
    "solana": 18.0,
    "ripple": 950.0,
}
_MARKET_MOVER_IDS = [
    "bitcoin",
    "ethereum",
    "solana",
    "ripple",
    "cardano",
    "dogecoin",
]


async def _get_from_coingecko(endpoint: str, params: Dict[str, Any]) -> Any:
    url = f"{settings.coingecko_base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    headers: Dict[str, str] = {}
    if settings.coingecko_demo_api_key:
        headers["x-cg-demo-api-key"] = settings.coingecko_demo_api_key

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, params=params, headers=headers)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to reach CoinGecko: {exc}",
        )

    if response.status_code == 429:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="CoinGecko rate limit exceeded, please retry later",
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"CoinGecko API error: {response.text}",
        )

    return response.json()


async def fetch_simple_prices(ids: List[str], vs_currency: str) -> Dict[str, Any]:
    if not ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one asset id must be provided",
        )

    params = {"ids": ",".join(ids), "vs_currencies": vs_currency}
    data = await _get_from_coingecko("simple/price", params=params)

    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pricing data returned for the requested assets",
        )
    return data


async def fetch_ohlc(coin_id: str, vs_currency: str, days: int) -> List[List[float]]:
    endpoint = f"coins/{coin_id}/ohlc"
    params = {"vs_currency": vs_currency, "days": days}
    data = await _get_from_coingecko(endpoint, params=params)

    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No OHLC data returned for the requested asset",
        )
    return data


async def fetch_dashboard(vs_currency: str) -> CryptoDashboardResponse:
    cache_key = vs_currency.lower()
    now = datetime.now(timezone.utc)
    cached = _DASHBOARD_CACHE.get(cache_key)
    if cached is not None:
        expires_at, cached_payload = cached
        if now < expires_at:
            return cached_payload

    target_ids = sorted(
        set(_MARKET_MOVER_IDS)
        .union(_PORTFOLIO_ALLOCATION.keys())
        .union({_CHART_COIN_ID})
    )
    markets_params = {
        "vs_currency": cache_key,
        "ids": ",".join(target_ids),
        "order": "market_cap_desc",
        "per_page": len(target_ids),
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "24h",
    }
    chart_params = {
        "vs_currency": cache_key,
        "days": _CHART_DAYS,
    }

    markets_task = asyncio.create_task(
        _get_from_coingecko("coins/markets", params=markets_params)
    )
    chart_task = asyncio.create_task(
        _get_from_coingecko(
            f"coins/{_CHART_COIN_ID}/market_chart", params=chart_params
        )
    )
    markets_data, chart_data = await asyncio.gather(markets_task, chart_task)

    if not markets_data:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="CoinGecko returned an empty markets payload",
        )

    markets_by_id = {item["id"]: item for item in markets_data}
    missing_assets = [coin_id for coin_id in target_ids if coin_id not in markets_by_id]
    if missing_assets:
        missing = ", ".join(missing_assets)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"CoinGecko response missing assets: {missing}",
        )

    chart_points = [
        MarketChartPoint(timestamp=int(point[0]), price=float(point[1]))
        for point in chart_data.get("prices", [])
    ]

    movers_source = [
        markets_by_id[coin_id] for coin_id in _MARKET_MOVER_IDS if coin_id in markets_by_id
    ]
    movers_sorted = sorted(
        movers_source,
        key=lambda item: item.get("price_change_percentage_24h") or float("-inf"),
        reverse=True,
    )
    market_movers = [
        MarketMover(
            id=item["id"],
            name=item["name"],
            symbol=item["symbol"].upper(),
            pair=f"{item['symbol'].upper()}/{cache_key.upper()}",
            current_price=float(item.get("current_price") or 0.0),
            change_24h_pct=float(item.get("price_change_percentage_24h") or 0.0),
            volume_24h=float(item.get("total_volume") or 0.0),
            image_url=item.get("image"),
        )
        for item in movers_sorted[:4]
    ]

    portfolio_items: List[PortfolioAsset] = []
    current_balance = 0.0
    previous_balance = 0.0
    for coin_id, quantity in _PORTFOLIO_ALLOCATION.items():
        market = markets_by_id.get(coin_id)
        if market is None:
            continue

        price = float(market.get("current_price") or 0.0)
        change_pct = float(market.get("price_change_percentage_24h") or 0.0)
        value = quantity * price

        current_balance += value
        if change_pct > -100.0:
            previous_balance += value / (1 + change_pct / 100)

        portfolio_items.append(
            PortfolioAsset(
                id=market["id"],
                name=market["name"],
                symbol=market["symbol"].upper(),
                quantity=float(quantity),
                current_price=price,
                value=value,
                change_24h_pct=change_pct,
                image_url=market.get("image"),
            )
        )

    balance_change_pct = 0.0
    if previous_balance > 0:
        balance_change_pct = (current_balance / previous_balance - 1) * 100

    response = CryptoDashboardResponse(
        currency=cache_key.upper(),
        portfolio_balance=current_balance,
        balance_change_pct=balance_change_pct,
        chart=chart_points,
        market_movers=market_movers,
        portfolio=portfolio_items,
        last_updated=now,
    )

    _DASHBOARD_CACHE[cache_key] = (now + _DASHBOARD_CACHE_TTL, response)
    return response

