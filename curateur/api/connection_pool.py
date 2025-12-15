"""
HTTP connection pooling for efficient parallel requests

Provides persistent connections and automatic retry logic.
"""

import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class ConnectionPoolManager:
    """
    Manages HTTP connection pooling for efficient parallel requests

    Features:
    - Persistent connections with balanced keepalive (90s)
    - Connection reuse across async tasks
    - Automatic stale connection detection
    - Automatic pool reset after consecutive timeouts (threshold: 5)
    - Aggressive timeout configuration for fast failure

    Connection Health:
    - Tracks consecutive timeout failures
    - Automatically resets pool after 5 consecutive timeouts
    - Balances keepalive duration (90s) vs connection freshness
    - Self-healing: failed connections trigger automatic recovery

    Example:
        manager = ConnectionPoolManager(config)
        client = await manager.get_client()

        try:
            response = await client.get('https://api.example.com/data')
            manager.record_success()  # Reset timeout counter
        except httpx.TimeoutException:
            if manager.record_timeout():  # Returns True if threshold exceeded
                await manager.reset_client()  # Automatic reset triggered
                client = await manager.get_client()  # Get fresh client
    """

    def __init__(self, config: dict):
        """
        Initialize connection pool manager

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.client: Optional[httpx.AsyncClient] = None
        self.lock = asyncio.Lock()

        # Track connection health for automatic recovery
        self.consecutive_timeouts = 0
        self.timeout_threshold = 5  # Reset pool after N consecutive timeouts

    def create_client(self, max_connections: int = 10) -> httpx.AsyncClient:
        """
        Create httpx async client with connection pooling

        Configuration:
        - Connection pool size based on task count
        - Keep-alive enabled
        - Automatic retry with exponential backoff
        - Conservative timeouts

        Args:
            max_connections: Maximum number of connections in pool

        Returns:
            Configured httpx.AsyncClient
        """
        timeout = self.config.get("api", {}).get("request_timeout", 30)

        # Configure connection limits
        # Balance: 90s keepalive balances latency savings vs stale connection risk
        # For 150ms+ latency, this saves ~300ms per request (TLS handshake)
        # but refreshes often enough to avoid prolonged stale connection issues
        limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_connections,
            keepalive_expiry=90.0,  # 90s: balance between reuse and staleness
        )

        # Configure timeout with aggressive failure detection
        timeout_config = httpx.Timeout(
            connect=5.0,  # Allow time for high-latency connections (150ms+ RTT)
            read=timeout,
            write=5.0,
            pool=5.0,  # Allow time to acquire connection from pool under load
        )

        # Configure transport without built-in retries (handled by higher-level backoff)
        transport = httpx.AsyncHTTPTransport(limits=limits, retries=0)

        client = httpx.AsyncClient(
            timeout=timeout_config,
            transport=transport,
            follow_redirects=False,
            http2=False,  # Explicit HTTP/1.1 (ScreenScraper does not support HTTP/2)
        )

        logger.debug(
            f"Connection pool: max_connections={max_connections}, "
            f"timeout={timeout}s"
        )

        return client

    async def get_client(
        self, max_connections: Optional[int] = None
    ) -> httpx.AsyncClient:
        """
        Get or create async client (async-safe)

        Args:
            max_connections: Maximum connections (uses default if None)

        Returns:
            Shared httpx.AsyncClient
        """
        async with self.lock:
            if self.client is None or self.client.is_closed:
                conn_count = max_connections or 10
                self.client = self.create_client(conn_count)
            return self.client

    async def close_client(self) -> None:
        """Close client and release connections"""
        async with self.lock:
            if self.client and not self.client.is_closed:
                logger.debug("Closing connection pool...")
                await self.client.aclose()
                self.client = None
                logger.info("Connection pool closed")

    async def reset_client(
        self, max_connections: Optional[int] = None
    ) -> httpx.AsyncClient:
        """
        Reset client by closing and recreating connection pool.

        Useful for recovering from sustained connection issues or stale connections.

        Args:
            max_connections: Maximum connections for new pool

        Returns:
            Fresh httpx.AsyncClient
        """
        async with self.lock:
            if self.client and not self.client.is_closed:
                logger.warning(
                    "Resetting connection pool due to potential connection issues"
                )
                await self.client.aclose()

            conn_count = max_connections or 10
            self.client = self.create_client(conn_count)
            self.consecutive_timeouts = 0  # Reset counter
            return self.client

    def record_timeout(self) -> bool:
        """
        Record a timeout occurrence.

        Returns:
            True if threshold exceeded and pool should be reset
        """
        self.consecutive_timeouts += 1
        if self.consecutive_timeouts >= self.timeout_threshold:
            logger.warning(
                f"Detected {self.consecutive_timeouts} consecutive timeouts - "
                "connection pool may have stale connections"
            )
            return True
        return False

    def record_success(self) -> None:
        """Record a successful request (resets timeout counter)."""
        if self.consecutive_timeouts > 0:
            self.consecutive_timeouts = 0

    def get_stats(self) -> dict:
        """
        Get connection pool statistics

        Returns:
            Dictionary with pool statistics
        """
        return {
            "client_active": self.client is not None and not self.client.is_closed,
            "config_timeout": self.config.get("api", {}).get("request_timeout", 30),
            "consecutive_timeouts": self.consecutive_timeouts,
            "health_status": "healthy" if self.consecutive_timeouts < 3 else "degraded",
        }
