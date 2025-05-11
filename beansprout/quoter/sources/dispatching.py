#!/usr/bin/env python3
"""Dispatching price source for beancount.

This module provides a Source class that implements the Composite Pattern.
It delegates price quotes to the appropriate subsource based on the ticker format
and commodity metadata.
"""

import datetime
import importlib
import logging
from typing import Dict, List, Optional, Tuple, Iterable, Type, Set
from collections import namedtuple

from beansprout.quoter.sources import cache_manager

from beancount.core.data import Commodity
from beancount.core.number import Decimal
from beanprice.source import Source as SourceBase

# A namedtuple to represent price source specifications
PriceSource = namedtuple('PriceSource',
                         ['currency', 'source', 'ticker', 'invert'])

# Configure logging
_logger = logging.getLogger(__name__)

# Dictionary of source name -> source class
SOURCES: Dict[str, Type[SourceBase]] = {}

# Set to track modules we've already tried to import
_TRIED_MODULES: Set[str] = set()


def get_source(source_name: str,
               custom_only: bool = False) -> Optional[SourceBase]:
    """Get a price source instance by name.
    
    This function tries to load and instantiate a price source in the following order:
    1. Check if it's already loaded in SOURCES
    2. Try to load from beansprout.quoter.sources package with "beansprout.quoter.sources." prefix
    3. Try to load from quoters package with "quoters." prefix (legacy support)
    4. Try to load from beanprice.sources with "beanprice.sources." prefix (if custom_only is False)
    5. Try to interpret the name as a full module path (if custom_only is False)
    
    Args:
        source_name: The name of the source to load
        custom_only: If True, only try to load from the beansprout.quoter.sources package
        
    Returns:
        An instance of the Source class if found, None otherwise
    """
    # First check if it's a source we've already loaded
    if source_name in SOURCES:
        return SOURCES[source_name]()

    # 1. Try to load from beansprout.quoter.sources package
    sources_module_name = f"beansprout.quoter.sources.{source_name}"
    if sources_module_name not in _TRIED_MODULES:
        _TRIED_MODULES.add(sources_module_name)
        try:
            module = importlib.import_module(sources_module_name)
            if hasattr(module, 'Source'):
                source_class = getattr(module, 'Source')
                SOURCES[source_name] = source_class
                return source_class()
        except ImportError:
            _logger.debug(f"No source found in {sources_module_name}")

    # 2. Try to load from legacy quoters package with "quoters." prefix (for backward compatibility)
    legacy_module_name = f"quoters.{source_name}"
    if legacy_module_name not in _TRIED_MODULES:
        _TRIED_MODULES.add(legacy_module_name)
        try:
            module = importlib.import_module(legacy_module_name)
            if hasattr(module, 'Source'):
                source_class = getattr(module, 'Source')
                SOURCES[source_name] = source_class
                _logger.warning(
                    f"Using legacy source from {legacy_module_name}. "
                    f"Consider migrating to {sources_module_name}.")
                return source_class()
        except ImportError:
            _logger.debug(f"No source found in {legacy_module_name}")

    # If custom_only is True, we stop here
    if custom_only:
        _logger.warning(f"No custom price source found for '{source_name}'")
        return None

    # 3. Try to load from beanprice.sources with "beanprice.sources." prefix
    beanprice_module_name = f"beanprice.sources.{source_name}"
    if beanprice_module_name not in _TRIED_MODULES:
        _TRIED_MODULES.add(beanprice_module_name)
        try:
            module = importlib.import_module(beanprice_module_name)
            if hasattr(module, 'Source'):
                source_class = getattr(module, 'Source')
                SOURCES[source_name] = source_class
                return source_class()
        except ImportError:
            _logger.debug(f"No source found in {beanprice_module_name}")

    # 4. Try to interpret the name as a full module path
    if source_name not in _TRIED_MODULES:
        _TRIED_MODULES.add(source_name)
        try:
            module = importlib.import_module(source_name)
            if hasattr(module, 'Source'):
                source_class = getattr(module, 'Source')
                SOURCES[source_name] = source_class
                return source_class()
        except ImportError:
            _logger.debug(f"Could not import module: {source_name}")

    # No source found
    _logger.warning(f"No price source found for '{source_name}'")
    return None


class DispatchingSource(SourceBase):
    """A price source that dispatches requests to multiple subsources.
    
    This class implements the Composite Pattern for the beanprice Source interface.
    It parses commodity metadata to determine which child sources should be used,
    and then delegates price fetching to those sources.
    """

    def __init__(self,
                 custom_only: bool = False,
                 cache_manager: 'cache_manager.CacheManager' = None) -> None:
        """Initialize the DispatchingSource.
        
        Args:
            custom_only: If True, only use custom quoters from the beansprout.quoter.sources directory.
                         If False, also use built-in beanprice sources.
            cache_manager: The cache manager to use for caching price quotes.
                          If None, no caching is performed.
        """
        self.custom_only = custom_only
        self._logger = logging.getLogger(__name__)
        self._sources_cache: Dict[str, SourceBase] = {}

        # Set the cache manager
        self._cache_manager = cache_manager

    def get_latest_price(
            self, ticker: str) -> Optional[Tuple[Decimal, datetime.date, str]]:
        """Get the latest price for a ticker.
        
        This implementation expects the ticker to be in the format:
        "COMMODITY:CURRENCY1:SOURCE1/TICKER1,SOURCE2/TICKER2 CURRENCY2:..."
        
        For inversion notation, prefix the ticker with ^ symbol:
        "COMMODITY:CURRENCY1:SOURCE1/^TICKER1" - will invert the price (1/price)
        
        Args:
            ticker: The ticker string containing commodity and source information
            
        Returns:
            A tuple with (price, date, currency) if a price is found, None otherwise
        """
        # Parse the combined ticker to extract commodity and source information
        parts = ticker.split(':', 1)
        if len(parts) != 2:
            self._logger.warning(f"Invalid ticker format: {ticker}")
            return None

        commodity_currency, price_meta = parts

        # Create a minimal commodity directive to parse
        meta = {'price': price_meta}
        commodity = Commodity(meta=meta,
                              currency=commodity_currency,
                              date=datetime.date.today())

        # Extract price sources and try each one
        price_sources = self._get_price_sources(commodity)

        # Check cache first if we have a cache manager
        if self._cache_manager:
            today = datetime.date.today()
            cached_result = self._cache_manager.get(commodity_currency,
                                                    price_meta, today)
            if cached_result:
                self._logger.debug(f"Using cached price for {ticker}")
                return cached_result

        # Try each price source in order
        result = self._try_sources_latest(price_sources)

        # Cache the result if successful and we have a cache manager
        if result and self._cache_manager:
            self._cache_manager.put(commodity_currency, price_meta,
                                    datetime.date.today(), result)

        return result

    def _try_sources_latest(
        self, price_sources: List[PriceSource]
    ) -> Optional[Tuple[Decimal, datetime.date, str]]:
        """Try each price source to get the latest price.
        
        Args:
            price_sources: List of price sources to try
            
        Returns:
            A tuple with (price, date, currency) if a price is found, None otherwise
        """
        for price_source in price_sources:
            source = self._get_or_create_source(price_source.source)
            if not source:
                continue

            try:
                result = source.get_latest_price(price_source.ticker)
                if result:
                    amount, price_date, source_currency = result

                    # If inversion is required, calculate 1/amount
                    if price_source.invert:
                        # We need to handle the possibility of zero value
                        if amount == Decimal('0'):
                            self._logger.warning(
                                f"Cannot invert zero value from {price_source.source}/{price_source.ticker}"
                            )
                            continue
                        amount = Decimal('1') / amount

                    # Return with the requested currency
                    return (amount, price_date, price_source.currency)
            except Exception as e:
                self._logger.warning(
                    f"Error fetching latest price using {price_source.source}/{price_source.ticker}: {e}"
                )
                continue

        return None

    def get_historical_price(
            self, ticker: str, time: datetime.date
    ) -> Optional[Tuple[Decimal, datetime.date, str]]:
        """Get a historical price for a ticker.
        
        This implementation expects the ticker to be in the format:
        "COMMODITY:CURRENCY1:SOURCE1/TICKER1,SOURCE2/TICKER2 CURRENCY2:..."
        
        For inversion notation, prefix the ticker with ^ symbol:
        "COMMODITY:CURRENCY1:SOURCE1/^TICKER1" - will invert the price (1/price)
        
        Args:
            ticker: The ticker string containing commodity and source information
            time: The date to fetch the price for
            
        Returns:
            A tuple with (price, date, currency) if a price is found, None otherwise
        """
        # Parse the combined ticker to extract commodity and source information
        parts = ticker.split(':', 1)
        if len(parts) != 2:
            self._logger.warning(f"Invalid ticker format: {ticker}")
            return None

        commodity_currency, price_meta = parts

        # Create a minimal commodity directive to parse
        meta = {'price': price_meta}
        commodity = Commodity(meta=meta,
                              currency=commodity_currency,
                              date=time)

        # Extract price sources and try each one
        price_sources = self._get_price_sources(commodity)

        # Check cache first if we have a cache manager
        if self._cache_manager:
            cached_result = self._cache_manager.get(commodity_currency,
                                                    price_meta, time)
            if cached_result:
                self._logger.debug(
                    f"Using cached historical price for {ticker} on {time}")
                return cached_result

        # Try each price source in order
        result = self._try_sources_historical(price_sources, time)

        # Cache the result if successful and we have a cache manager
        if result and self._cache_manager:
            self._cache_manager.put(commodity_currency, price_meta, time,
                                    result)

        return result

    def _try_sources_historical(
            self, price_sources: List[PriceSource], time: datetime.date
    ) -> Optional[Tuple[Decimal, datetime.date, str]]:
        """Try each price source to get a historical price.
        
        Args:
            price_sources: List of price sources to try
            time: The date to fetch the price for
            
        Returns:
            A tuple with (price, date, currency) if a price is found, None otherwise
        """
        for price_source in price_sources:
            source = self._get_or_create_source(price_source.source)
            if not source:
                continue

            try:
                result = source.get_historical_price(price_source.ticker, time)
                if result:
                    amount, price_date, source_currency = result

                    # If inversion is required, calculate 1/amount
                    if price_source.invert:
                        # We need to handle the possibility of zero value
                        if amount == Decimal('0'):
                            self._logger.warning(
                                f"Cannot invert zero value from {price_source.source}/{price_source.ticker}"
                            )
                            continue
                        amount = Decimal('1') / amount

                    # Return with the requested currency
                    return (amount, price_date, price_source.currency)
            except Exception as e:
                self._logger.warning(
                    f"Error fetching historical price using {price_source.source}/{price_source.ticker}: {e}"
                )
                continue

        return None

    def get_prices_series(
        self, ticker: str, time_begin: datetime.date, time_end: datetime.date
    ) -> Optional[Iterable[Tuple[datetime.date, Decimal, str]]]:
        """Get a series of prices for a ticker over a range of dates.
        
        This implementation expects the ticker to be in the format:
        "COMMODITY:CURRENCY1:SOURCE1/TICKER1,SOURCE2/TICKER2 CURRENCY2:..."
        
        For inversion notation, prefix the ticker with ^ symbol:
        "COMMODITY:CURRENCY1:SOURCE1/^TICKER1" - will invert all prices in the series (1/price)
        
        Args:
            ticker: The ticker string containing commodity and source information
            time_begin: Start date for the price series
            time_end: End date for the price series
            
        Returns:
            An iterable of (date, price, currency) tuples if prices are found, None otherwise
        """
        # Parse the combined ticker to extract commodity and source information
        parts = ticker.split(':', 1)
        if len(parts) != 2:
            self._logger.warning(f"Invalid ticker format: {ticker}")
            return None

        commodity_currency, price_meta = parts

        # Create a minimal commodity directive to parse
        meta = {'price': price_meta}
        commodity = Commodity(meta=meta,
                              currency=commodity_currency,
                              date=time_begin)

        # Extract price sources and try each one
        price_sources = self._get_price_sources(commodity)

        # For a price series, we don't use caching since it's more complex
        # to cache and retrieve an entire series with multiple dates.
        # Each individual price can still be cached via get_historical_price.

        # Try each price source in order
        return self._try_sources_series(price_sources, time_begin, time_end)

    def _try_sources_series(
        self, price_sources: List[PriceSource], time_begin: datetime.date,
        time_end: datetime.date
    ) -> Optional[Iterable[Tuple[datetime.date, Decimal, str]]]:
        """Try each price source to get a series of prices.
        
        Args:
            price_sources: List of price sources to try
            time_begin: Start date for the price series
            time_end: End date for the price series
            
        Returns:
            An iterable of (date, price, currency) tuples if prices are found, None otherwise
        """
        for price_source in price_sources:
            source = self._get_or_create_source(price_source.source)
            if not source:
                continue

            try:
                # Check if the source implements get_prices_series
                if not hasattr(source, 'get_prices_series'):
                    continue

                result = source.get_prices_series(price_source.ticker,
                                                  time_begin, time_end)
                if result:
                    # Adjust the currency to match what was requested
                    # The original result format is [(date, price, currency), ...]
                    # We need to transform it to use the requested currency

                    # If inversion is required, calculate 1/price for each entry
                    if price_source.invert:
                        return [(date, Decimal('1') /
                                 price if price != Decimal('0') else None,
                                 price_source.currency)
                                for date, price, _ in result
                                if price != Decimal('0')]
                    else:
                        return [(date, price, price_source.currency)
                                for date, price, _ in result]
            except Exception as e:
                self._logger.warning(
                    f"Error fetching price series using {price_source.source}/{price_source.ticker}: {e}"
                )
                continue

        return None

    def _get_or_create_source(self, source_name: str) -> Optional[SourceBase]:
        """Get or create a source by name.
        
        Args:
            source_name: The name of the source to get
            
        Returns:
            A Source instance if found, None otherwise
        """
        if source_name in self._sources_cache:
            return self._sources_cache[source_name]

        source = get_source(source_name=source_name,
                            custom_only=self.custom_only)
        if source:
            self._sources_cache[source_name] = source

        return source

    def _get_price_sources(self, commodity: Commodity) -> List[PriceSource]:
        """Extract price sources from commodity metadata.
        
        The price metadata format is: "CURRENCY1:SOURCE1/TICKER1 CURRENCY2:SOURCE2/TICKER2 ..."
        For example: "USD:yahoo/AAPL CAD:yahoo/AAPL.TO"
        
        Multiple sources for the same currency can be specified with comma separations:
        "USD:source1/TICKER1,source2/TICKER2"
        
        Inversion notation is supported by prefixing the ticker with ^ symbol:
        "USD:yahoo/^CADUSD=X" (inverts the CADUSD rate to get USD/CAD)
        
        Args:
            commodity: Commodity directive to extract price sources from.
            
        Returns:
            List of PriceSource tuples with (currency, source, ticker, invert) for each price source.
            The invert flag indicates whether the price should be inverted (1/price).
        """
        if 'price' not in commodity.meta:
            return []

        price_meta = commodity.meta['price']
        sources = []

        # Split by spaces to get each currency:source/ticker pair
        for pair in price_meta.split():
            if ':' not in pair:
                continue

            currency, source_spec = pair.split(':', 1)

            # Handle multiple sources for the same currency (comma-separated)
            for source_ticker in source_spec.split(','):
                if '/' not in source_ticker:
                    self._logger.warning(
                        f"Invalid source/ticker format: {source_ticker}")
                    continue

                source, ticker = source_ticker.split('/', 1)

                # Check if ticker has the inversion notation (^)
                invert = ticker.startswith('^')
                if invert:
                    # Remove the ^ symbol from the ticker
                    ticker = ticker[1:]

                sources.append(
                    PriceSource(currency=currency,
                                source=source,
                                ticker=ticker,
                                invert=invert))

        return sources


# Create a singleton instance as the Source class
Source = DispatchingSource
