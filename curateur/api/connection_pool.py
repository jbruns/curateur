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
    - Persistent connections
    - Connection reuse across async tasks
    - Automatic retry logic
    - Timeout configuration
    
    Example:
        manager = ConnectionPoolManager(config)
        async with manager.get_client() as client:
            # Use client for requests
            response = await client.get('https://api.example.com/data')
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
        timeout = self.config.get('api', {}).get('request_timeout', 30)
        
        # Configure connection limits
        limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_connections,
            keepalive_expiry=60.0  # Keep connections alive for 60 seconds
        )
        
        # Configure timeout
        timeout_config = httpx.Timeout(
            connect=10.0,
            read=timeout,
            write=30.0,
            pool=None  # No timeout for acquiring connection from pool
        )
        
        # Configure transport with retries
        transport = httpx.AsyncHTTPTransport(
            limits=limits,
            retries=3
        )
        
        client = httpx.AsyncClient(
            timeout=timeout_config,
            transport=transport,
            follow_redirects=True
        )
        
        logger.info(
            f"Connection pool created: max_connections={max_connections}, "
            f"timeout={timeout}s"
        )
        
        return client
    
    async def get_client(self, max_connections: Optional[int] = None) -> httpx.AsyncClient:
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
    
    def get_stats(self) -> dict:
        """
        Get connection pool statistics
        
        Returns:
            Dictionary with pool statistics
        """
        return {
            'client_active': self.client is not None and not self.client.is_closed,
            'config_timeout': self.config.get('api', {}).get('request_timeout', 30)
        }
