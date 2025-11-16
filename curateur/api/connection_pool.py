"""
HTTP connection pooling for efficient parallel requests

Provides persistent connections and automatic retry logic.
"""

import logging
import threading
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class ConnectionPoolManager:
    """
    Manages HTTP connection pooling for efficient parallel requests
    
    Features:
    - Persistent connections
    - Connection reuse across threads
    - Automatic retry logic
    - Timeout configuration
    
    Example:
        manager = ConnectionPoolManager(config)
        session = manager.get_session()
        
        # Use session for requests
        response = session.get('https://api.example.com/data')
        
        # Clean up
        manager.close_session()
    """
    
    def __init__(self, config: dict):
        """
        Initialize connection pool manager
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.session: Optional[requests.Session] = None
        self.lock = threading.Lock()
    
    def create_session(self, max_connections: int = 10) -> requests.Session:
        """
        Create requests session with connection pooling
        
        Configuration:
        - Connection pool size based on thread count
        - Keep-alive enabled
        - Automatic retry with exponential backoff
        - Conservative timeouts
        
        Args:
            max_connections: Maximum number of connections in pool
        
        Returns:
            Configured requests.Session
        """
        session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        
        # Configure adapter with connection pooling
        adapter = HTTPAdapter(
            pool_connections=max_connections,
            pool_maxsize=max_connections * 2,
            max_retries=retry_strategy,
            pool_block=False
        )
        
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Set default timeout (connect, read)
        timeout = self.config.get('api', {}).get('request_timeout', 30)
        session.timeout = (10, timeout)
        
        logger.info(
            f"Connection pool created: max_connections={max_connections}, "
            f"timeout={timeout}s"
        )
        
        return session
    
    def get_session(self, max_connections: Optional[int] = None) -> requests.Session:
        """
        Get or create session (thread-safe)
        
        Args:
            max_connections: Maximum connections (uses default if None)
        
        Returns:
            Shared requests.Session
        """
        with self.lock:
            if self.session is None:
                conn_count = max_connections or 10
                self.session = self.create_session(conn_count)
            return self.session
    
    def close_session(self) -> None:
        """Close session and release connections"""
        with self.lock:
            if self.session:
                logger.debug("Closing connection pool...")
                self.session.close()
                self.session = None
                logger.info("Connection pool closed")
    
    def get_stats(self) -> dict:
        """
        Get connection pool statistics
        
        Returns:
            Dictionary with pool statistics
        """
        return {
            'session_active': self.session is not None,
            'config_timeout': self.config.get('api', {}).get('request_timeout', 30)
        }
