from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

import httpx
from fastapi import HTTPException, status

from ..config import settings


def _build_headers() -> Dict[str, str]:
    headers: Dict[str, str] = {"Accept": "application/json"}
    if settings.coincap_api_key:
        headers["Authorization"] = f"Bearer {settings.coincap_api_key}"
    return headers


async def _get_from_rest(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
    url = f"{settings.coincap_base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=20.0, headers=_build_headers()) as client:
            response = await client.get(url, params=params)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to reach CoinCap REST: {exc}",
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"CoinCap REST HTTP error: {response.text}",
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="CoinCap REST returned invalid JSON",
        ) from exc
    return payload.get("data")


async def _get_from_rest_safe(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
    try:
        return await _get_from_rest(endpoint, params=params)
    except HTTPException:
        return None


async def _execute_graphql(query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = settings.coincap_graphql_url.rstrip("/")
    payload = {"query": query, "variables": variables or {}}
    headers = _build_headers()
    headers["Content-Type"] = "application/json"

    try:
        async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
            response = await client.post(url, json=payload)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to reach CoinCap GraphQL: {exc}",
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"CoinCap GraphQL HTTP error: {response.text}",
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="CoinCap GraphQL returned invalid JSON",
        ) from exc

    errors = data.get("errors")
    if errors:
        message = errors[0].get("message", "Unknown CoinCap GraphQL error")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"CoinCap GraphQL error: {message}",
        )

    payload_data = data.get("data")
    if not isinstance(payload_data, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="CoinCap GraphQL response missing data field",
        )

    return payload_data


def _extract_assets(connection: Any) -> List[Dict[str, Any]]:
    if not isinstance(connection, dict):
        return []

    items: List[Dict[str, Any]] = []
    for edge in connection.get("edges", []):
        if not isinstance(edge, dict):
            continue
        node = edge.get("node")
        if isinstance(node, dict):
            items.append(node)
    return items


async def fetch_top_assets(limit: int = 10) -> List[Dict[str, Any]]:
    query = """
    query ($limit: Int!) {
        assets(first: $limit, sort: rank, direction: ASC) {
            edges {
                node {
                    id
                    name
                    symbol
                    rank
                    priceUsd
                    changePercent24Hr
                    volumeUsd24Hr
                }
            }
        }
    }
    """
    rest_payload: Any = None
    try:
        data = await _execute_graphql(query, {"limit": limit})
        items = _extract_assets(data.get("assets"))
        if items:
            return items
    except HTTPException:
        pass

    rest_payload = await _get_from_rest_safe("assets", params={"limit": limit})
    items: List[Dict[str, Any]] = []
    if isinstance(rest_payload, list):
        for item in rest_payload:
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "symbol": item.get("symbol"),
                    "rank": item.get("rank"),
                    "priceUsd": item.get("priceUsd"),
                    "changePercent24Hr": item.get("changePercent24Hr"),
                    "volumeUsd24Hr": item.get("volumeUsd24Hr"),
                }
            )
    return items


async def fetch_assets(search: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    query = """
    query ($limit: Int!) {
        assets(first: $limit, sort: rank, direction: ASC) {
            edges {
                node {
                    id
                    name
                    symbol
                    rank
                    priceUsd
                    changePercent24Hr
                    volumeUsd24Hr
                }
            }
        }
    }
    """
    try:
        data = await _execute_graphql(query, {"limit": limit})
        items = _extract_assets(data.get("assets"))
    except HTTPException:
        rest_payload = await _get_from_rest_safe("assets", params={"limit": limit})
        items = rest_payload if isinstance(rest_payload, list) else []

    if search:
        search_lower = search.lower()
        items = [
            item
            for item in items
            if search_lower in str(item.get("name", "")).lower()
            or search_lower in str(item.get("symbol", "")).lower()
        ]
    return items


async def fetch_asset(asset_id: str) -> Dict[str, Any]:
    query = """
    query ($id: ID!) {
        asset(id: $id) {
            id
            name
            symbol
            rank
            priceUsd
            changePercent24Hr
            volumeUsd24Hr
        }
    }
    """
    try:
        data = await _execute_graphql(query, {"id": asset_id})
        payload = data.get("asset")
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Asset '{asset_id}' not found",
            )
        return payload
    except HTTPException:
        fallback = await _get_from_rest_safe(f"assets/{asset_id}")
        if isinstance(fallback, dict):
            return fallback
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset '{asset_id}' not found",
        )


async def fetch_assets_by_ids(asset_ids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    asset_list = list({asset_id for asset_id in asset_ids if asset_id})
    if not asset_list:
        return {}

    query = """
    query ($ids: [ID!]!, $limit: Int!) {
        assets(first: $limit, where: { id_in: $ids }, sort: rank) {
            edges {
                node {
                    id
                    name
                    symbol
                    rank
                    priceUsd
                    changePercent24Hr
                    volumeUsd24Hr
                }
            }
        }
    }
    """
    variables = {"ids": asset_list, "limit": len(asset_list)}
    try:
        data = await _execute_graphql(query, variables)
        assets = _extract_assets(data.get("assets"))
        return {str(asset.get("id")): asset for asset in assets if asset.get("id")}
    except HTTPException:
        fallback: Dict[str, Dict[str, Any]] = {}
        for asset_id in asset_list:
            payload = await _get_from_rest_safe(f"assets/{asset_id}")
            if isinstance(payload, dict):
                fallback[str(payload.get("id") or asset_id)] = payload
        return fallback


async def fetch_history(asset_id: str, days: int = 7) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)
    query = """
    query ($id: ID!, $start: Date!, $end: Date!, $interval: Interval!) {
        assetHistories(assetId: $id, start: $start, end: $end, interval: $interval) {
            priceUsd
            timestamp
        }
    }
    """
    variables = {
        "id": asset_id,
        "start": start.date().isoformat(),
        "end": now.date().isoformat(),
        "interval": "d1",
    }
    try:
        data = await _execute_graphql(query, variables)
        payload = data.get("assetHistories") or []
        history: List[Dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            timestamp = item.get("timestamp") or item.get("time")
            history.append(
                {
                    "time": int(timestamp or 0),
                    "priceUsd": item.get("priceUsd"),
                }
            )
        return history
    except HTTPException:
        rest_payload = await _get_from_rest_safe(
            f"assets/{asset_id}/history",
            params={"interval": "d1", "start": start_ms, "end": end_ms},
        )
        history: List[Dict[str, Any]] = []
        if isinstance(rest_payload, list):
            for item in rest_payload[-days:]:
                if not isinstance(item, dict):
                    continue
                history.append(
                    {
                        "time": int((item.get("time") or 0)),
                        "priceUsd": item.get("priceUsd"),
                    }
                )
        return history
