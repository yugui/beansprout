"""Cache manager for price quoters.

This module provides caching capabilities for price quotes to reduce
network calls and improve performance. It implements the Strategy pattern
to allow different caching implementations.
"""

import abc
import datetime
import dbm  # Using the generic dbm instead of dbm.gnu for portability
import logging
import os
import pickle
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple, TypeVar, Union

# Type variables for better type hints
T = TypeVar('T')
CacheValue = Tuple[float, T]  # (timestamp, data)


class CacheManager(abc.ABC):
    """Abstract base class defining the interface for price quote cache managers.
    
    This class defines the interface for all cache manager implementations.
    Concrete implementations should inherit from this class and implement
    the required methods.
    """

    @abc.abstractmethod
    def get(self, ticker: str, base_ticker: str,
            date: datetime.date) -> Optional[Any]:
        """Retrieve a cached quote if available.
        
        Args:
            ticker: The ticker symbol of the quote
            base_ticker: The base ticker (currency) of the quote
            date: Date of the quote
            
        Returns:
            Quote object if found and valid, None otherwise.
        """
        pass

    @abc.abstractmethod
    def put(self, ticker: str, base_ticker: str, date: datetime.date,
            quote_result: Any) -> None:
        """Store a quote result in the cache.
        
        Args:
            ticker: The ticker symbol
            base_ticker: The base ticker (currency)
            date: Date of the quote
            quote_result: The quote result to cache
        """
        pass

    @abc.abstractmethod
    def get_stats(self) -> Dict[str, Union[int, float]]:
        """Return cache statistics.
        
        Returns:
            Dictionary containing hit/miss statistics
        """
        pass

    @abc.abstractmethod
    def close(self) -> None:
        """Close the cache resources."""
        pass

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensure resources are closed."""
        self.close()


class DBMCacheManager(CacheManager):
    """Manages caching of price quotes using DBM storage.
    
    This class provides persistent caching of price quotes using DBM as the
    underlying storage mechanism. It handles serialization/deserialization,
    expiration based on TTL, and cache size limits.
    """

    def __init__(self,
                 cache_file_path: Optional[str] = None,
                 ttl_seconds: int = 86400,
                 max_entries: int = 10000):
        """Initialize the cache manager.
        
        Args:
            cache_file_path: Path to the GDBM file. If None, uses default path.
            ttl_seconds: Time-to-live for cached entries in seconds. Default 24h.
            max_entries: Maximum number of entries to store in the cache.
        """
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries

        # Set up default cache path if not provided
        if cache_file_path is None:
            home_dir = os.path.expanduser('~')
            cache_dir = os.path.join(home_dir, '.cache', 'beansprout')
            cache_file_path = os.path.join(cache_dir, 'quote-cache.gdbm')

        self.cache_file_path = cache_file_path

        # Ensure the cache directory exists
        cache_dir = os.path.dirname(self.cache_file_path)
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)

        # Initialize database
        self._db = self._safe_open_db()

        # Initialize statistics
        self._stats = {'hits': 0, 'misses': 0}

    def get(self, ticker: str, base_ticker: str,
            date: datetime.date) -> Optional[Any]:
        """Retrieve a cached quote if available and not expired.
        
        Args:
            ticker: The ticker symbol of the quote
            base_ticker: The base ticker (currency) of the quote
            date: Date of the quote
            
        Returns:
            Quote object if found and valid, None otherwise.
        """
        key = self._get_cache_key(ticker, base_ticker, date)

        try:
            if key.encode() in self._db:
                cached_data = pickle.loads(self._db[key.encode()])
                timestamp, quote_data = cached_data

                # Check if entry is expired
                if not self._is_expired(timestamp):
                    logging.debug("Cache hit for key %s", key)
                    self._stats['hits'] += 1
                    return quote_data

            # Either key not found or entry expired
            logging.debug("Cache miss for key %s", key)
            self._stats['misses'] += 1
            return None
        except Exception as e:
            # Log but don't fail on cache errors
            logging.warning("Error retrieving from cache: %s", str(e))
            self._stats['misses'] += 1
            return None

    def put(self, ticker: str, base_ticker: str, date: datetime.date,
            quote_result: Any) -> None:
        """Store a quote result in the cache.
        
        Args:
            ticker: The ticker symbol
            base_ticker: The base ticker (currency)
            date: Date of the quote
            quote_result: The quote result to cache
        """
        key = self._get_cache_key(ticker, base_ticker, date)

        try:
            # Create cache entry with current timestamp
            timestamp = datetime.datetime.now().timestamp()
            cache_value = (timestamp, quote_result)

            # Store in database
            self._db[key.encode()] = pickle.dumps(cache_value)
            self._db.sync()  # Ensure data is written

            # Check if we need to enforce size limits
            self._enforce_size_limit()
        except Exception as e:
            # Log but don't fail on cache errors
            logging.warning("Error storing in cache: %s", str(e))

    def _get_cache_key(self, ticker: str, base_ticker: str,
                       date: datetime.date) -> str:
        """Generate a cache key from the quote parameters.
        
        Args:
            ticker: The ticker symbol
            base_ticker: The base ticker (currency)
            date: The date of the quote
            
        Returns:
            String key in format 'TICKER:BASE:YYYY-MM-DD'
        """
        return f"{ticker}:{base_ticker}:{date.isoformat()}"

    def _is_expired(self, timestamp: float) -> bool:
        """Check if a cached entry is expired based on TTL.
        
        Args:
            timestamp: The timestamp when the entry was cached
            
        Returns:
            True if the entry is expired, False otherwise
        """
        current_time = datetime.datetime.now().timestamp()
        return (current_time - timestamp) > self.ttl_seconds

    def _enforce_size_limit(self) -> None:
        """Remove oldest entries if cache exceeds size limit."""
        try:
            # Get all keys and their timestamps
            entries = []
            for key, value in self._db.items():
                try:
                    timestamp, _ = pickle.loads(value)
                    entries.append((key, timestamp))
                except (pickle.PickleError, ValueError, TypeError):
                    # If we can't unpickle, consider it as an old entry
                    entries.append((key, 0))

            # If we're over the limit, remove oldest entries
            if len(entries) > self.max_entries:
                # Sort by timestamp (oldest first)
                entries.sort(key=lambda x: x[1])

                # Remove oldest entries to get under the limit
                entries_to_remove = entries[:len(entries) - self.max_entries]
                for key, _ in entries_to_remove:
                    del self._db[key]

                # Sync to ensure changes are persisted
                self._db.sync()

                logging.debug(
                    "Removed %d entries from cache to enforce size limit",
                    len(entries_to_remove))
        except Exception as e:
            logging.warning("Error enforcing cache size limit: %s", str(e))

    def _safe_open_db(self):
        """Safely open the database with corruption handling.
        
        Returns:
            DBM database object
        """
        try:
            # Try to open existing database
            return dbm.open(self.cache_file_path, 'c')
        except Exception as e:
            # If opening fails (e.g., due to corruption), create a new one
            logging.warning("Error opening cache file, creating new one: %s",
                            str(e))
            try:
                return dbm.open(self.cache_file_path, 'n')
            except Exception as e2:
                # If that also fails, use in-memory fallback
                logging.error("Failed to create new cache file: %s", str(e2))
                raise RuntimeError(
                    f"Could not create cache file: {str(e2)}") from e2

    def get_stats(self) -> Dict[str, Union[int, float]]:
        """Return cache statistics.
        
        Returns:
            Dictionary containing hit/miss statistics
        """
        stats = dict(self._stats)
        total = stats['hits'] + stats['misses']
        stats['hit_ratio'] = stats['hits'] / total if total > 0 else 0
        return stats

    def close(self) -> None:
        """Close the cache database."""
        try:
            self._db.close()
        except Exception as e:
            logging.warning("Error closing cache database: %s", str(e))


class NullCacheManager(CacheManager):
    """A no-op cache manager implementation that doesn't perform any caching.
    
    This implementation can be used when caching should be disabled. All operations
    are no-ops, and the get method always indicates a cache miss.
    """

    def __init__(self):
        """Initialize the NullCacheManager."""
        self._stats = {'hits': 0, 'misses': 0}

    def get(self, ticker: str, base_ticker: str,
            date: datetime.date) -> Optional[Any]:
        """Always return None (cache miss).
        
        Args:
            ticker: The ticker symbol of the quote
            base_ticker: The base ticker (currency) of the quote
            date: Date of the quote
            
        Returns:
            Always None to indicate cache miss.
        """
        # Increment miss counter for consistency
        self._stats['misses'] += 1
        return None

    def put(self, ticker: str, base_ticker: str, date: datetime.date,
            quote_result: Any) -> None:
        """No-op for putting items in cache.
        
        Args:
            ticker: The ticker symbol
            base_ticker: The base ticker (currency)
            date: Date of the quote
            quote_result: The quote result that would be cached
        """
        # No-op, we don't cache anything
        pass

    def get_stats(self) -> Dict[str, Union[int, float]]:
        """Return cache statistics.
        
        Returns:
            Dictionary containing hit/miss statistics. For NullCacheManager,
            there will only be misses.
        """
        stats = dict(self._stats)
        total = stats['hits'] + stats['misses']
        stats['hit_ratio'] = stats['hits'] / total if total > 0 else 0
        return stats

    def close(self) -> None:
        """No-op for closing resources."""
        # No resources to close
        pass


class MemoryCacheManager(CacheManager):
    """Manages caching of price quotes using in-memory storage.
    
    This class provides in-memory caching of price quotes using an OrderedDict
    as the underlying storage mechanism. It handles expiration based on TTL
    and cache size limits. This implementation is suitable for short-lived
    processes where persistence isn't required.
    """

    def __init__(self, ttl_seconds: int = 86400, max_entries: int = 10000):
        """Initialize the memory cache manager.
        
        Args:
            ttl_seconds: Time-to-live for cached entries in seconds. Default 24h.
            max_entries: Maximum number of entries to store in the cache.
        """
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries

        # Use OrderedDict to maintain insertion order for LRU eviction
        self._cache = OrderedDict()
        self._stats = {'hits': 0, 'misses': 0}

    def get(self, ticker: str, base_ticker: str,
            date: datetime.date) -> Optional[Any]:
        """Retrieve a cached quote if available and not expired.
        
        Args:
            ticker: The ticker symbol of the quote
            base_ticker: The base ticker (currency) of the quote
            date: Date of the quote
            
        Returns:
            Quote object if found and valid, None otherwise.
        """
        key = self._get_cache_key(ticker, base_ticker, date)

        try:
            if key in self._cache:
                timestamp, quote_data = self._cache[key]

                # Check if entry is expired
                if not self._is_expired(timestamp):
                    # Move item to the end (most recently used)
                    # This helps with LRU eviction policy
                    self._cache.move_to_end(key, last=True)

                    logging.debug("Cache hit for key %s", key)
                    self._stats['hits'] += 1
                    return quote_data
                else:
                    # Entry expired, remove it and count as a miss
                    del self._cache[key]
                    logging.debug("Cache miss (expired) for key %s", key)
                    self._stats['misses'] += 1
                    return None

            # Key not found
            logging.debug("Cache miss (not found) for key %s", key)
            self._stats['misses'] += 1
            return None
        except Exception as e:
            # Log but don't fail on cache errors
            logging.warning("Error retrieving from memory cache: %s", str(e))
            self._stats['misses'] += 1
            return None

    def put(self, ticker: str, base_ticker: str, date: datetime.date,
            quote_result: Any) -> None:
        """Store a quote result in the cache.
        
        Args:
            ticker: The ticker symbol
            base_ticker: The base ticker (currency)
            date: Date of the quote
            quote_result: The quote result to cache
        """
        key = self._get_cache_key(ticker, base_ticker, date)

        try:
            # Create cache entry with current timestamp
            timestamp = datetime.datetime.now().timestamp()

            # Check if we need to enforce size limit before adding
            self._enforce_size_limit()

            # Store in memory cache
            self._cache[key] = (timestamp, quote_result)

            # Move to end (most recently used)
            self._cache.move_to_end(key, last=True)
        except Exception as e:
            # Log but don't fail on cache errors
            logging.warning("Error storing in memory cache: %s", str(e))

    def _get_cache_key(self, ticker: str, base_ticker: str,
                       date: datetime.date) -> str:
        """Generate a cache key from the quote parameters.
        
        Args:
            ticker: The ticker symbol
            base_ticker: The base ticker (currency)
            date: The date of the quote
            
        Returns:
            String key in format 'TICKER:BASE:YYYY-MM-DD'
        """
        return f"{ticker}:{base_ticker}:{date.isoformat()}"

    def _is_expired(self, timestamp: float) -> bool:
        """Check if a cached entry is expired based on TTL.
        
        Args:
            timestamp: The timestamp when the entry was cached
            
        Returns:
            True if the entry is expired, False otherwise
        """
        current_time = datetime.datetime.now().timestamp()
        return (current_time - timestamp) > self.ttl_seconds

    def _enforce_size_limit(self) -> None:
        """Remove oldest entries if cache exceeds size limit."""
        try:
            # Since we're using OrderedDict with move_to_end,
            # the oldest entries are at the beginning
            while len(self._cache) >= self.max_entries:
                # Remove oldest item (first item in OrderedDict)
                self._cache.popitem(last=False)
                logging.debug(
                    "Removed oldest entry from memory cache to enforce size limit"
                )
        except Exception as e:
            logging.warning("Error enforcing memory cache size limit: %s",
                            str(e))

    def get_stats(self) -> Dict[str, Union[int, float]]:
        """Return cache statistics.
        
        Returns:
            Dictionary containing hit/miss statistics
        """
        stats = dict(self._stats)
        total = stats['hits'] + stats['misses']
        stats['hit_ratio'] = stats['hits'] / total if total > 0 else 0
        return stats

    def close(self) -> None:
        """Clear the memory cache."""
        try:
            self._cache.clear()
        except Exception as e:
            logging.warning("Error closing memory cache: %s", str(e))
