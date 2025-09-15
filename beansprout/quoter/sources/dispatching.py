#!/usr/bin/env python3
"""Dispatching price source for beancount.

This module provides a SourceDispatcher class that fetches price quotes for commodities
from various sources. It supports both built-in sources from beanprice and custom
sources from the beansprout.quoter.sources directory.

The dispatcher extracts source specifications from commodity metadata in the format:
"CURRENCY1:SOURCE1/TICKER1,SOURCE2/TICKER2 CURRENCY2:SOURCE3/TICKER3"

For example: "USD:yahoo/AAPL CAD:yahoo/AAPL.TO"

Price inversion is supported by prefixing the ticker with ^ symbol:
"USD:yahoo/^CADUSD=X" (inverts the CADUSD rate to get USD/CAD)

Multiple sources per currency are supported with comma separation and are tried in order:
"USD:source1/TICKER1,source2/TICKER2" 

The dispatcher tries each source in order until one succeeds and caches the results.

## Batch Interface for Source Implementations

Sources can optionally implement batch methods for improved performance when fetching
multiple tickers at once. If a source implements these methods, they will be used
automatically. If not, the source will be wrapped with BatchSourceWrapper to provide
batch capability.

Optional batch methods that sources can implement:

    def get_latest_prices_batch(self, tickers: List[str]) -> Dict[str, Optional[SourcePrice]]:
        \"\"\"Fetch latest prices for multiple tickers.
        
        Args:
            tickers: List of ticker symbols to fetch prices for.
            
        Returns:
            Dictionary mapping ticker -> SourcePrice (or None if failed).
        \"\"\"

    def get_historical_prices_batch(self, tickers: List[str], 
                                   time: datetime.datetime) -> Dict[str, Optional[SourcePrice]]:
        \"\"\"Fetch historical prices for multiple tickers.
        
        Args:
            tickers: List of ticker symbols to fetch prices for.
            time: The datetime to fetch historical prices for.
            
        Returns:
            Dictionary mapping ticker -> SourcePrice (or None if failed).
        \"\"\"

    def get_prices_series_batch(self, tickers: List[str], 
                               time_begin: datetime.datetime,
                               time_end: datetime.datetime) -> Dict[str, Optional[List[SourcePrice]]]:
        \"\"\"Fetch price series for multiple tickers.
        
        Args:
            tickers: List of ticker symbols to fetch price series for.
            time_begin: Start of the time range.
            time_end: End of the time range.
            
        Returns:
            Dictionary mapping ticker -> List[SourcePrice] (or None if failed).
        \"\"\"

See https://beancount.github.io/docs/fetching_prices_in_beancount.html for more
details of the price metadata format.
"""

import datetime
import importlib
import logging
from typing import Dict, List, Optional, Tuple, Iterable, Type, Set, Union, Callable, Any

from beansprout.quoter.sources import cache_manager
from beansprout.quoter.expression_parser import parse_price_expression, SourceSpec

from beancount.core.data import Commodity, Price, Amount
from beancount.core.number import Decimal
from beanprice.source import Source as SourceBase, SourcePrice

# SourceSpec is now imported from expression_parser

# Configure logging
_logger = logging.getLogger(__name__)

# Dictionary of source name -> source class
SOURCES: Dict[str, Type[SourceBase]] = {}


class BatchSourceWrapper:
    """Wrapper that adds batch capability to non-batch-aware sources.
    
    This wrapper implements batch methods by calling the underlying source's
    single-ticker methods multiple times. It provides a uniform batch interface
    for all sources, regardless of their native batch capabilities.
    """

    def __init__(self, source: SourceBase):
        """Initialize the wrapper with a source instance.
        
        Args:
            source: The source instance to wrap with batch capability.
        """
        self._source = source

    def get_latest_prices_batch(
            self, tickers: List[str]) -> Dict[str, Optional[SourcePrice]]:
        """Fetch latest prices for multiple tickers by calling single-ticker method.
        
        Args:
            tickers: List of ticker symbols to fetch prices for.
            
        Returns:
            Dictionary mapping ticker -> SourcePrice (or None if failed).
        """
        results = {}
        for ticker in tickers:
            try:
                result = self._source.get_latest_price(ticker)
                results[ticker] = result
            except Exception as e:
                _logger.debug(f"Failed to get latest price for {ticker}: {e}")
                results[ticker] = None
        return results

    def get_historical_prices_batch(
            self, tickers: List[str],
            time: datetime.datetime) -> Dict[str, Optional[SourcePrice]]:
        """Fetch historical prices for multiple tickers by calling single-ticker method.
        
        Args:
            tickers: List of ticker symbols to fetch prices for.
            time: The datetime to fetch historical prices for.
            
        Returns:
            Dictionary mapping ticker -> SourcePrice (or None if failed).
        """
        results = {}
        for ticker in tickers:
            try:
                result = self._source.get_historical_price(ticker, time)
                results[ticker] = result
            except Exception as e:
                _logger.debug(
                    f"Failed to get historical price for {ticker} at {time}: {e}"
                )
                results[ticker] = None
        return results

    def get_prices_series_batch(
            self, tickers: List[str], time_begin: datetime.datetime,
            time_end: datetime.datetime
    ) -> Dict[str, Optional[List[SourcePrice]]]:
        """Fetch price series for multiple tickers by calling single-ticker method.
        
        Args:
            tickers: List of ticker symbols to fetch price series for.
            time_begin: Start of the time range.
            time_end: End of the time range.
            
        Returns:
            Dictionary mapping ticker -> List[SourcePrice] (or None if failed).
        """
        results = {}
        for ticker in tickers:
            try:
                result = self._source.get_prices_series(
                    ticker, time_begin, time_end)
                results[ticker] = result
            except Exception as e:
                _logger.debug(
                    f"Failed to get price series for {ticker} from {time_begin} to {time_end}: {e}"
                )
                results[ticker] = None
        return results

    def __getattr__(self, name):
        """Delegate all other methods and attributes to the wrapped source.
        
        Args:
            name: The attribute or method name being accessed.
            
        Returns:
            The attribute or method from the wrapped source.
        """
        return getattr(self._source, name)


# Set to track modules we've already tried to import
_TRIED_MODULES: Set[str] = set()


def get_source(source_name: str) -> Optional[SourceBase]:
    """Get a price source instance by name.
    
    This function tries to load and instantiate a price source in the following order:
    1. Check if it's already loaded in SOURCES
    2. Try to load from beansprout.quoter.sources package with "beansprout.quoter.sources." prefix
    3. Try to load from beanprice.sources with "beanprice.sources." prefix
    4. Try to interpret the name as a full module path
    
    Args:
        source_name: The name of the source to load
        
    Returns:
        An instance of the Source class if found, None otherwise
    """
    # 1. Check if it's a source we've already loaded
    if source_name in SOURCES:
        return SOURCES[source_name]()

    # 2. Try to load from beansprout.quoter.sources package
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


class SourceDispatcher:
    """A dispatcher that fetches prices from multiple sources based on commodity metadata.
    
    This class handles:
    - Parsing price source specifications from commodity metadata
    - Loading and instantiating price source implementations
    - Trying multiple sources in a fallback sequence
    - Caching price results to avoid redundant fetches
    - Supporting price inversions for currency pairs
    - Fetching both latest, historical and series of prices
    
    The dispatcher reads source specifications from the 'price' metadata field in
    commodity directives, following the format described in the module docstring.
    """

    def __init__(self, cache_manager: cache_manager.CacheManager) -> None:
        """Initialize the SourceDispatcher.
        
        Args:
            cache_manager: The cache manager to use for caching price quotes.
        """
        self._logger = logging.getLogger(__name__)
        self._sources_cache: Dict[str, SourceBase] = {}

        # Set the cache manager
        self._cache_manager = cache_manager

    def fetch_latest_prices_batch(
        self, spec_commodity_pairs: List[Tuple[SourceSpec,
                                               str]]) -> Dict[str, Price]:
        """Fetch latest prices for multiple SourceSpecs from same source.
        
        Args:
            spec_commodity_pairs: List of (SourceSpec, commodity) tuples for the same source
            
        Returns:
            Dictionary mapping ticker to Price directive
        """

        def fetch_latest(source: SourceBase,
                         tickers: List[str]) -> Dict[str, SourcePrice]:
            return source.get_latest_prices_batch(tickers)

        return self._fetch_prices_batch_generic(spec_commodity_pairs,
                                                fetch_latest,
                                                is_series=False)

    def fetch_historical_prices_batch(
            self, spec_commodity_pairs: List[Tuple[SourceSpec, str]],
            time: datetime.datetime) -> Dict[str, Price]:
        """Fetch historical prices for multiple SourceSpecs from same source.
        
        Args:
            spec_commodity_pairs: List of (SourceSpec, commodity) tuples for the same source
            time: The datetime to fetch historical prices for
            
        Returns:
            Dictionary mapping ticker to Price directive
        """

        def fetch_historical(source: SourceBase,
                             tickers: List[str]) -> Dict[str, SourcePrice]:
            return source.get_historical_prices_batch(tickers, time)

        date = time.date() if isinstance(time, datetime.datetime) else time
        return self._fetch_prices_batch_generic(spec_commodity_pairs,
                                                fetch_historical,
                                                is_series=False,
                                                date=date)

    def fetch_prices_series_batch(
            self, spec_commodity_pairs: List[Tuple[SourceSpec, str]],
            time_begin: datetime.datetime,
            time_end: datetime.datetime) -> Dict[str, List[Price]]:
        """Fetch price series for multiple SourceSpecs from same source.
        
        Args:
            spec_commodity_pairs: List of (SourceSpec, commodity) tuples for the same source
            time_begin: Start of the time range
            time_end: End of the time range
            
        Returns:
            Dictionary mapping ticker to list of Price directives
        """

        def fetch_series(source: SourceBase,
                         tickers: List[str]) -> Dict[str, List[SourcePrice]]:
            return source.get_prices_series_batch(tickers, time_begin,
                                                  time_end)

        return self._fetch_prices_batch_generic(spec_commodity_pairs,
                                                fetch_series,
                                                is_series=True)

    def _get_or_create_source(self, source_name: str) -> Optional[SourceBase]:
        """Get or create a source by name, wrapping with batch capability if needed.
        
        Args:
            source_name: The name of the source to get
            
        Returns:
            A Source instance (possibly wrapped with batch capability) if found, None otherwise
        """
        if source_name in self._sources_cache:
            return self._sources_cache[source_name]

        source = get_source(source_name=source_name)
        if source:
            # Wrap the source with batch capability if it doesn't have native batch methods
            if not hasattr(source, 'get_latest_prices_batch'):
                source = BatchSourceWrapper(source)

            self._sources_cache[source_name] = source

        return source

    def _fetch_prices_batch_generic(
        self,
        spec_commodity_pairs: List[Tuple[SourceSpec, str]],
        source_method_func: Callable[[SourceBase, List[str]],
                                     Union[Dict[str, SourcePrice],
                                           Dict[str, List[SourcePrice]]]],
        is_series: bool = False,
        date: Optional[datetime.date] = None
    ) -> Dict[str, Union[Price, List[Price]]]:
        """Generic method to fetch prices using batch operations.
        
        Args:
            spec_commodity_pairs: List of (SourceSpec, commodity) tuples for the same source
            source_method_func: Function that takes (source, tickers) and returns source results
            is_series: Whether this is a series fetch (returns List[Price]) or single fetch (returns Price)
            date: Optional date for historical prices (None for latest prices)
            
        Returns:
            Dictionary mapping ticker to Price or List[Price] objects
        """
        if not spec_commodity_pairs:
            return {}

        # All specs should be for the same source
        source_name = spec_commodity_pairs[0][0].source
        source = self._get_or_create_source(source_name)
        if not source:
            return {}

        try:
            # Extract tickers from specs
            tickers = [spec.ticker for spec, _ in spec_commodity_pairs]

            # Call the provided function with source and tickers
            results = source_method_func(source, tickers)

            # Process results based on type
            if is_series:
                return self._process_series_results(spec_commodity_pairs,
                                                    results)
            else:
                return self._process_single_price_results(
                    spec_commodity_pairs, results, date)

        except Exception as e:
            self._logger.warning(
                f"Error fetching prices from {source_name}: {e}")
            return {}

    def _process_single_price_results(
            self,
            spec_commodity_pairs: List[Tuple[SourceSpec, str]],
            results: Dict[str, SourcePrice],
            date: Optional[datetime.date] = None) -> Dict[str, Price]:
        """Process single price results (latest or historical).
        
        Args:
            spec_commodity_pairs: List of (SourceSpec, commodity) tuples
            results: Results from source batch method
            date: The date for the prices, or None to use today's date
            
        Returns:
            Dictionary mapping ticker to Price objects
        """
        prices = {}

        # Use provided date or default to today
        if date is None:
            date = datetime.date.today()

        for spec, commodity in spec_commodity_pairs:
            source_price = results.get(spec.ticker)
            if source_price:
                # Handle inversion if needed
                if spec.invert and source_price.price != Decimal('0'):
                    source_price = SourcePrice(
                        price=Decimal('1') / source_price.price,
                        time=source_price.time,
                        quote_currency=spec.quote_currency)

                # Convert to Price directive
                price = self._process_single_price_result(
                    source_spec=spec,
                    source_price=source_price,
                    commodity=commodity,
                    base_currency=spec.quote_currency,
                    date=date)
                prices[spec.ticker] = price

                # Cache the result
                if self._cache_manager:
                    self._cache_manager.put(spec.quote_currency, commodity,
                                            date, price)

        return prices

    def _process_series_results(
            self, spec_commodity_pairs: List[Tuple[SourceSpec, str]],
            results: Dict[str, List[SourcePrice]]) -> Dict[str, List[Price]]:
        """Process price series results.
        
        Args:
            spec_commodity_pairs: List of (SourceSpec, commodity) tuples
            results: Results from source batch method
            
        Returns:
            Dictionary mapping ticker to list of Price objects
        """
        prices_by_ticker = {}

        for spec, commodity in spec_commodity_pairs:
            source_prices = results.get(spec.ticker)
            if source_prices:
                price_list = []

                for source_price in source_prices:
                    # Handle inversion if needed
                    if spec.invert and source_price.price != Decimal('0'):
                        source_price = SourcePrice(
                            price=Decimal('1') / source_price.price,
                            time=source_price.time,
                            quote_currency=spec.quote_currency)

                    # Get the date from the source price
                    date = source_price.time.date() if isinstance(
                        source_price.time,
                        datetime.datetime) else source_price.time

                    # Convert to Price directive
                    price = self._process_single_price_result(
                        source_spec=spec,
                        source_price=source_price,
                        commodity=commodity,
                        base_currency=spec.quote_currency,
                        date=date)
                    price_list.append(price)

                    # Cache each result
                    if self._cache_manager:
                        self._cache_manager.put(spec.quote_currency, commodity,
                                                date, price)

                # Sort by date
                price_list.sort(key=lambda p: p.date)
                prices_by_ticker[spec.ticker] = price_list

        return prices_by_ticker

    def _process_single_price_result(self, source_spec: SourceSpec,
                                     source_price: SourcePrice, commodity: str,
                                     base_currency: str,
                                     date: datetime.date) -> Price:
        """Process a single price result into a Price object.
        
        Args:
            source_spec: The source specification used to fetch the price
            source_price: The price result from the source
            commodity: The commodity symbol being priced (e.g., "AAPL")
            base_currency: The base currency for the price
            date: The date for the price
            
        Returns:
            A Price object
        """
        meta = {
            'source': source_spec.source,
            'time': source_price.time.isoformat(),
        }

        quote_currency = source_price.quote_currency if source_price.quote_currency else base_currency

        # Note: Inversion is now handled in the calling methods before this is called
        return Price(
            meta=meta,
            date=date,
            currency=commodity,
            amount=Amount(number=source_price.price, currency=base_currency),
        )
