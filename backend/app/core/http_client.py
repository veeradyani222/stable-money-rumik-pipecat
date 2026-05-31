"""Shared httpx.AsyncClient for connection reuse across all outbound API calls.

Eliminates the ~500-800ms TCP+TLS handshake overhead that occurs when each
AI verification call, intent classifier call, and Rumik session creation
spins up a fresh httpx.AsyncClient.
"""
from __future__ import annotations

import httpx

_client: httpx.AsyncClient | None = None


def get_shared_http_client() -> httpx.AsyncClient:
    """Return the module-level shared async HTTP client.

    The client is created lazily on first call and reused for all subsequent
    requests.  Connection pooling is configured to keep warm connections to
    both ``api.openai.com`` and ``silk-api.rumik.ai``.
    """
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=120,
            ),
        )
    return _client


async def close_shared_http_client() -> None:
    """Close the shared client gracefully.  Call during application shutdown."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None
