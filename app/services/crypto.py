from __future__ import annotations

from typing import Any, Dict, List

import httpx
from fastapi import HTTPException, status

from ..config import settings


async def _get_from_coingecko(endpoint: str, params: Dict[str, Any]) -> Any:
    url = f"{settings.coingecko_base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, params=params)

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
