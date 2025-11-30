from __future__ import annotations

import re
import time
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import httpx
from fastapi import HTTPException, status

from ..config import settings

_SEARCH_CACHE: Dict[str, Optional[str]] = {}
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_TOKEN_SYNONYMS: Dict[str, Sequence[str]] = {
    "bep2": ("binance", "bnb"),
    "bep20": ("binance", "bnb", "bsc"),
    "bnb": ("binance",),
    "erc20": ("ethereum", "eth"),
    "eth": ("ethereum",),
    "sol": ("solana",),
    "trx": ("tron",),
    "avax": ("avalanche",),
    "matic": ("polygon",),
    "polygon": ("matic",),
    "arb": ("arbitrum",),
    "op": ("optimism",),
}
_COIN_LIST_CACHE: Dict[str, Any] = {"items": [], "by_symbol": {}, "expires_at": 0.0}
_COIN_LIST_TTL = 60 * 60 * 6  # 6 hours
_MARKET_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
_MARKET_CACHE_TTL = 30.0


def _build_headers() -> Dict[str, str]:
    headers: Dict[str, str] = {"Accept": "application/json"}
    if settings.coingecko_api_key:
        headers["x-cg-pro-api-key"] = settings.coingecko_api_key
    elif settings.coingecko_demo_api_key:
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


def _tokenize(value: str) -> List[str]:
    if not value:
        return []
    return _TOKEN_PATTERN.findall(value.lower())


def _normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _build_search_keywords(symbol: str, asset_id_hint: Optional[str], asset_name: Optional[str]) -> Set[str]:
    tokens: List[str] = []
    for value in filter(None, (asset_id_hint, asset_name, symbol)):
        tokens.extend(_tokenize(value or ""))
    expanded = set(tokens)
    for token in list(expanded):
        expanded.update(_TOKEN_SYNONYMS.get(token, ()))
    return expanded


def _score_coin_candidate(
    coin: Dict[str, Any],
    keywords: Set[str],
    normalized_asset_name: str,
) -> int:
    tokens = set(
        _tokenize(str(coin.get("id") or ""))
        + _tokenize(str(coin.get("name") or ""))
        + _tokenize(str(coin.get("symbol") or ""))
    )
    score = sum(1 for token in tokens if token in keywords)
    if normalized_asset_name:
        coin_name = _normalize_text(str(coin.get("name") or ""))
        if coin_name == normalized_asset_name:
            score += 5
    return score


def _rank_value(coin: Dict[str, Any]) -> int:
    rank = coin.get("market_cap_rank")
    if isinstance(rank, int) and rank > 0:
        return rank
    return 10**9


def _cache_key(symbol: str, asset_id_hint: Optional[str], asset_name: Optional[str]) -> str:
    return f"{symbol.lower()}|{(asset_id_hint or '').lower()}|{(asset_name or '').lower()}"


async def _search_coin_id_remote(
    symbol: str,
    asset_id_hint: Optional[str] = None,
    asset_name: Optional[str] = None,
) -> Optional[str]:
    key = _cache_key(symbol, asset_id_hint, asset_name)
    if key in _SEARCH_CACHE:
        return _SEARCH_CACHE[key]

    queries: List[str] = []
    if asset_name:
        queries.append(asset_name)
    if asset_id_hint:
        queries.append(asset_id_hint)
    queries.append(symbol)

    candidates: Dict[str, Dict[str, Any]] = {}
    seen_queries: Set[str] = set()
    for query in queries:
        normalized = query.strip().lower()
        if not normalized or normalized in seen_queries:
            continue
        seen_queries.add(normalized)
        payload = await _get_from_coingecko("search", params={"query": normalized})
        if not isinstance(payload, dict):
            continue
        for coin in payload.get("coins", []) or []:
            coin_id = str(coin.get("id") or "")
            if not coin_id or coin_id in candidates:
                continue
            candidates[coin_id] = coin

    if not candidates:
        _SEARCH_CACHE[key] = None
        return None

    normalized_hint = (asset_id_hint or "").lower()
    if normalized_hint:
        for coin_id in candidates:
            if coin_id.lower() == normalized_hint:
                _SEARCH_CACHE[key] = coin_id
                return coin_id

    keywords = _build_search_keywords(symbol, asset_id_hint, asset_name)
    normalized_name = _normalize_text(asset_name)

    best_id: Optional[str] = None
    best_score = -1
    best_rank = 10**9
    for coin_id, coin in candidates.items():
        score = _score_coin_candidate(coin, keywords, normalized_name)
        rank = _rank_value(coin)
        if score > best_score or (score == best_score and rank < best_rank):
            best_score = score
            best_rank = rank
            best_id = coin_id

    _SEARCH_CACHE[key] = best_id
    return best_id


async def _load_coin_catalog() -> Dict[str, Any]:
    now = time.monotonic()
    if now < float(_COIN_LIST_CACHE.get("expires_at", 0.0)):
        return _COIN_LIST_CACHE

    payload = await _get_from_coingecko("coins/list")
    if not isinstance(payload, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="CoinGecko returned unexpected payload for coins list",
        )

    items: List[Dict[str, str]] = []
    by_symbol: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        coin_id = str(entry.get("id") or "").strip()
        symbol = str(entry.get("symbol") or "").strip().lower()
        name = str(entry.get("name") or "").strip()
        if not coin_id or not symbol:
            continue
        coin = {"id": coin_id, "symbol": symbol, "name": name}
        items.append(coin)
        by_symbol[symbol].append(coin)

    _COIN_LIST_CACHE["items"] = items
    _COIN_LIST_CACHE["by_symbol"] = dict(by_symbol)
    _COIN_LIST_CACHE["expires_at"] = now + _COIN_LIST_TTL
    return _COIN_LIST_CACHE


def _score_local_candidate(
    coin: Dict[str, str],
    symbol: str,
    keywords: Set[str],
    normalized_name: str,
    normalized_asset_id: str,
) -> int:
    score = 0
    symbol_lower = symbol.lower()
    if coin.get("symbol") == symbol_lower:
        score += 10

    coin_name_norm = _normalize_text(coin.get("name"))
    if normalized_name and coin_name_norm == normalized_name:
        score += 6

    coin_id = str(coin.get("id") or "")
    coin_id_norm = _normalize_text(coin_id)
    if normalized_asset_id and coin_id_norm == normalized_asset_id:
        score += 8

    coin_tokens = set(_tokenize(coin_id) + _tokenize(coin.get("name", "")))
    coin_tokens.update(_TOKEN_SYNONYMS.get(symbol_lower, ()))
    score += sum(1 for token in coin_tokens if token in keywords)
    return score


async def _resolve_coin_id_local(
    symbol: str,
    asset_id_hint: Optional[str],
    asset_name: Optional[str],
) -> Optional[str]:
    catalog = await _load_coin_catalog()
    keywords = _build_search_keywords(symbol, asset_id_hint, asset_name)
    normalized_name = _normalize_text(asset_name)
    normalized_asset_id = _normalize_text(asset_id_hint)

    by_symbol: Dict[str, List[Dict[str, str]]] = catalog["by_symbol"]
    items: List[Dict[str, str]] = catalog["items"]

    def _pick(candidates: Iterable[Dict[str, str]]) -> Optional[str]:
        best_id = None
        best_score = -1
        for entry in candidates:
            score = _score_local_candidate(
                entry,
                symbol,
                keywords,
                normalized_name,
                normalized_asset_id,
            )
            if score > best_score:
                best_score = score
                best_id = entry.get("id")
        if best_score >= 5:
            return best_id
        return None

    symbol_matches = by_symbol.get(symbol.lower() or "", [])
    candidate_id = _pick(symbol_matches)
    if candidate_id:
        return candidate_id

    # fall back to scanning full list only if symbol list failed
    return _pick(items)


async def fetch_price_usd(
    symbol: str,
    asset_id_hint: Optional[str] = None,
    asset_name: Optional[str] = None,
) -> float:
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

    resolved_id = await resolve_coin_id(symbol, asset_id_hint=asset_id_hint, asset_name=asset_name)
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


async def resolve_coin_id(
    symbol: str,
    asset_id_hint: Optional[str] = None,
    asset_name: Optional[str] = None,
) -> Optional[str]:
    key = _cache_key(symbol, asset_id_hint, asset_name)
    if key in _SEARCH_CACHE:
        return _SEARCH_CACHE[key]

    local_match = await _resolve_coin_id_local(symbol, asset_id_hint, asset_name)
    if local_match:
        _SEARCH_CACHE[key] = local_match
        return local_match

    resolved = await _search_coin_id_remote(symbol, asset_id_hint=asset_id_hint, asset_name=asset_name)
    _SEARCH_CACHE[key] = resolved
    return resolved


async def fetch_market_overview(
    limit: int = 6,
    vs_currency: str = "usd",
    ids: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    def _cache_key_for_market() -> str:
        if ids:
            normalized_ids = ",".join(sorted(str(i).strip() for i in ids if i))
            return f"{vs_currency.lower()}|ids|{normalized_ids}"
        return f"{vs_currency.lower()}|limit|{limit}"

    params: Dict[str, Any] = {
        "vs_currency": (vs_currency or "usd").lower(),
        "order": "market_cap_desc",
        "page": 1,
        "sparkline": "true",
        "price_change_percentage": "24h",
        "locale": "en",
    }

    if ids:
        id_list = [coin_id.strip() for coin_id in ids if coin_id and coin_id.strip()]
        if not id_list:
            return []
        params["ids"] = ",".join(id_list)
        params["per_page"] = len(id_list)
    else:
        effective_limit = max(1, min(limit, 250))
        params["per_page"] = effective_limit

    cache_key = _cache_key_for_market()
    cached_entry = _MARKET_CACHE.get(cache_key)
    now = time.monotonic()
    if cached_entry and now - cached_entry[0] < _MARKET_CACHE_TTL:
        return cached_entry[1]

    try:
        payload = await _get_from_coingecko("coins/markets", params=params)
    except HTTPException as exc:
        if (
            exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS
            and cached_entry is not None
        ):
            return cached_entry[1]
        raise
    if not isinstance(payload, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="CoinGecko returned unexpected payload for markets endpoint",
        )
    result = payload if ids else payload[:limit]
    _MARKET_CACHE[cache_key] = (now, result)
    return result
