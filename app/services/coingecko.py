from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException, status

from ..config import settings

_SEARCH_CACHE: Dict[str, Optional[str]] = {}


def _build_headers() -> Dict[str, str]:
    headers: Dict[str, str] = {"Accept": "application/json"}
    if settings.coingecko_demo_api_key:
        headers["x-cg-demo-api-key"] = settings.coingecko_demo_api_key
    return headers


async def _get_from_coingecko(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
    url = f"{settings.coingecko_base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=20.0, headers=_build_headers()) as client:
            response = await client.get(url, params=params)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to reach CoinGecko: {exc}",
        ) from exc

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


async def _search_coin_id(symbol: str) -> Optional[str]:
    symbol_lower = symbol.lower()
    if symbol_lower in _SEARCH_CACHE:
        return _SEARCH_CACHE[symbol_lower]

    payload = await _get_from_coingecko("search", params={"query": symbol_lower})
    coins = payload.get("coins", []) if isinstance(payload, dict) else []
    match = next(
        (coin for coin in coins if str(coin.get("symbol", "")).lower() == symbol_lower),
        None,
    )
    cg_id = str(match.get("id")) if match else None
    _SEARCH_CACHE[symbol_lower] = cg_id
    return cg_id


async def fetch_price_usd(symbol: str, asset_id_hint: Optional[str] = None) -> float:
    """Get USD price from CoinGecko by symbol with optional id hint."""
    cg_id = asset_id_hint.lower() if asset_id_hint else None
    if cg_id:
        try:
            payload = await _get_from_coingecko(
                f"coins/{cg_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "true",
                    "community_data": "false",
                    "developer_data": "false",
                    "sparkline": "false",
                },
            )
            price = (
                payload.get("market_data", {})
                .get("current_price", {})
                .get("usd")  # type: ignore[arg-type]
            )
            if price is not None:
                return float(price)
        except HTTPException:
            cg_id = None

    resolved_id = await _search_coin_id(symbol)
    if not resolved_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CoinGecko asset not found for symbol '{symbol}'",
        )

    payload = await _get_from_coingecko(
        f"coins/{resolved_id}",
        params={
            "localization": "false",
            "tickers": "false",
            "market_data": "true",
            "community_data": "false",
            "developer_data": "false",
            "sparkline": "false",
        },
    )
    price = payload.get("market_data", {}).get("current_price", {}).get("usd")
    if price is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="CoinGecko did not return USD price",
        )
    return float(price)
