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

See https://beancount.github.io/docs/fetching_prices_in_beancount.html for more
details of the price metadata format.
"""

import datetime
import importlib
import logging
from typing import Dict, List, Optional, Tuple, Iterable, Type, Set, Union, NamedTuple

from beansprout.quoter.sources import cache_manager

from beancount.core.data import Commodity, Price, Amount
from beancount.core.number import Decimal
from beanprice.source import Source as SourceBase, SourcePrice

# A named tuple to represent the price source specification
#
# Fields:
# - quote_currency: The currency in which the price is quoted (e.g., USD)
# - source: The name of the price source module/provider (e.g., yahoo, coinbase)
# - ticker: The ticker symbol for the commodity in the source
# - invert: Boolean flag to invert the price (1/price), useful for currency pairs
SourceSpec = NamedTuple('SourceSpec', [
    ('quote_currency', str),
    ('source', str),
    ('ticker', str),
    ('invert', bool),
])

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

    def __init__(self,
                 cache_manager: cache_manager.CacheManager,
                 custom_only: bool = False) -> None:
        """Initialize the SourceDispatcher.
        
        Args:
            cache_manager: The cache manager to use for caching price quotes.
            custom_only: If True, only use custom quoters from the beansprout.quoter.sources directory.
                         If False, also use built-in beanprice sources.
        """
        self.custom_only = custom_only
        self._logger = logging.getLogger(__name__)
        self._sources_cache: Dict[str, SourceBase] = {}

        # Set the cache manager
        self._cache_manager = cache_manager

    def get_latest_price(self, commodity: Commodity) -> Iterable[Price]:
        """Get the latest price for a ticker.
        
        This implementation expects the ticker to be in the format:
        "COMMODITY:CURRENCY1:SOURCE1/TICKER1,SOURCE2/TICKER2 CURRENCY2:..."
        
        For inversion notation, prefix the ticker with ^ symbol:
        "COMMODITY:CURRENCY1:SOURCE1/^TICKER1" - will invert the price (1/price)
        
        Args:
            commodity: The commodity to get the price for
            
        Returns:
            An iterable of Price instances, or empty if we failed to fetch.
        """
        prices = self._fetch_prices(
            commodity=commodity,
            method_name='get_latest_price',
            reference_date=datetime.date.today(),
        )
        return prices.values()

    def get_historical_price(self, commodity: Commodity,
                             time: datetime.datetime) -> Iterable[Price]:
        """Get a historical price for a ticker.
        
        This implementation expects the ticker to be in the format:
        "COMMODITY:CURRENCY1:SOURCE1/TICKER1,SOURCE2/TICKER2 CURRENCY2:..."
        
        For inversion notation, prefix the ticker with ^ symbol:
        "COMMODITY:CURRENCY1:SOURCE1/^TICKER1" - will invert the price (1/price)
        
        Args:
            commodity: The commodity to get the price for
            time: A datetime.datetime instance at which to query for the price
            
        Returns:
            An iterable of Price instances, or empty if we failed to fetch.
        """
        date = time.date() if isinstance(time, datetime.datetime) else time
        prices = self._fetch_prices(
            commodity=commodity,
            method_name='get_historical_price',
            args=(time, ),
            reference_date=date,
        )
        return prices.values()

    def get_prices_series(self, commodity: Commodity,
                          time_begin: datetime.datetime,
                          time_end: datetime.datetime) -> List[Price]:
        """Get a series of prices for a ticker over a range of dates.
        
        This implementation expects the ticker to be in the format:
        "COMMODITY:CURRENCY1:SOURCE1/TICKER1,SOURCE2/TICKER2 CURRENCY2:..."
        
        For inversion notation, prefix the ticker with ^ symbol:
        "COMMODITY:CURRENCY1:SOURCE1/^TICKER1" - will invert all prices in the series (1/price)
        
        Args:
            commodity: The commodity to get prices for
            time_begin: The earliest timestamp whose prices to include
            time_end: The latest timestamp whose prices to include
            
        Returns:
            A list of Price instances, sorted by date/time, or empty if we failed to fetch
        """
        return self._fetch_price_series(commodity, time_begin, time_end)

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

    def _get_source_specs(self,
                          commodity: Commodity) -> Dict[str, List[SourceSpec]]:
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
            List of SourceSpec tuples with (currency, source, ticker, invert) for each price source.
            The invert flag indicates whether the price should be inverted (1/price).
        """
        if 'price' not in commodity.meta:
            return {}

        price_meta = commodity.meta['price']
        sources = {}

        # Split by spaces to get each currency:source/ticker pair
        for pair in price_meta.split():
            if ':' not in pair:
                continue

            currency, source_spec = pair.split(':', 1)
            if currency not in sources:
                sources[currency] = []

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

                sources[currency].append(
                    SourceSpec(quote_currency=currency,
                               source=source,
                               ticker=ticker,
                               invert=invert))

        return sources

    def _try_sources(
        self,
        source_specs: List[SourceSpec],
        method_name: str,
        args: tuple = (),
        is_series: bool = False
    ) -> Optional[Tuple[SourceSpec, Union[SourcePrice, List[SourcePrice]]]]:
        """Generic method to try multiple price sources with a specified method.
        
        Args:
            source_specs: List of price sources to try
            method_name: Name of the method to call on the source
            args: Arguments to pass to the method
            is_series: Whether the method returns a price series
            
        Returns:
            The result from the first successful price source call
        """
        for source_spec in source_specs:
            source = self._get_or_create_source(source_spec.source)
            if not source:
                continue

            try:
                # Check if the source implements the required method
                if not hasattr(source, method_name):
                    if is_series:  # Only log for series, as it's optional
                        continue
                    else:
                        self._logger.warning(
                            f"Source {source_spec.source} does not implement {method_name}"
                        )
                        continue

                # Get the method and call it with the appropriate arguments
                method = getattr(source, method_name)
                full_args = (source_spec.ticker, ) + args
                result = method(*full_args)

                if not result:
                    continue

                if not source_spec.invert:
                    return (source_spec, result)

                if is_series:
                    # Convert to our own SourcePrice instances with inverted prices and updated currency
                    return (source_spec, [
                        SourcePrice(
                            price=Decimal('1') / source_price.price
                            if source_price.price != Decimal('0') else None,
                            time=source_price.time,
                            quote_currency=source_spec.currency)
                        for source_price in result
                        if source_price.price != Decimal('0')
                    ])
                else:
                    # We need to handle the possibility of zero value
                    if result.price == Decimal('0'):
                        self._logger.warning(
                            f"Cannot invert zero value from {source_spec.source}/{source_spec.ticker}"
                        )
                        continue

                    # Return with the requested currency
                    return (source_spec,
                            SourcePrice(
                                price=Decimal('1') / result.price,
                                time=result.time,
                                quote_currency=result.quote_currency,
                            ))

            except Exception as e:
                self._logger.warning(
                    f"Error fetching price using {method_name} from {source_spec.source}/{source_spec.ticker}: {e}"
                )
                continue

        return None

    def _process_single_price_result(self, source_spec: SourceSpec,
                                     source_price: SourcePrice,
                                     commodity: Commodity, base_currency: str,
                                     date: datetime.date) -> Price:
        """Process a single price result into a Price object.
        
        Args:
            source_spec: The source specification used to fetch the price
            source_price: The price result from the source
            commodity: The commodity being priced
            base_currency: The base currency for the price
            date: The date for the price
            
        Returns:
            A Price object
        """
        meta = {
            'source': source_spec.source,
            'time': source_price.time.isoformat(),
        }

        if source_spec.invert:
            # For inverted prices, the source already inverted them in _try_sources for series,
            # but we need to invert here for single prices
            quote_currency = source_price.quote_currency if source_price.quote_currency else base_currency
            return Price(
                meta=meta,
                date=date,
                currency=quote_currency,
                amount=Amount(number=Decimal('1') / source_price.price,
                              currency=commodity.currency),
            )
        else:
            quote_currency = source_price.quote_currency if source_price.quote_currency else base_currency
            return Price(
                meta=meta,
                date=date,
                currency=commodity.currency,
                amount=Amount(number=source_price.price,
                              currency=base_currency),
            )

    def _fetch_prices(
            self,
            commodity: Commodity,
            method_name: str,
            reference_date: datetime.date,
            args: tuple = (),
    ) -> Dict[str, Price]:
        """Fetch prices for a commodity using the specified method.
        
        This method handles the common logic for fetching prices:
        1. Extract source specs from commodity metadata
        2. Check cache for each currency
        3. Try sources until one succeeds
        4. Process and cache results
        
        Args:
            commodity: The commodity to fetch prices for
            method_name: The method name to call on the source
            reference_date: A reference date to use for cache lookups
            args: Arguments to pass to the method
            
        Returns:
            A dictionary of base_currency -> Price
        """
        # Get source specs from commodity metadata
        source_specs = self._get_source_specs(commodity)

        prices = {}
        for base_currency, price_sources in source_specs.items():
            # Check cache first
            cached_result = self._cache_manager.get(base_currency,
                                                    commodity.currency,
                                                    reference_date)
            if cached_result:
                self._logger.debug(
                    f"Using cached price for {base_currency}/{commodity.currency} on {reference_date}"
                )
                prices[base_currency] = cached_result
                continue

            # Try sources until one works
            result_pair = self._try_sources(price_sources,
                                            method_name,
                                            args=args)
            if not result_pair:
                self._logger.warning(
                    f"Failed to get {method_name} for {base_currency}/{commodity.currency}"
                )
                continue

            source_spec, result = result_pair

            # Get the actual date from the result if available
            date = reference_date
            if result.time:
                date = result.time.date() if isinstance(
                    result.time, datetime.datetime) else result.time

            # Process the result into a Price object
            price = self._process_single_price_result(
                source_spec=source_spec,
                source_price=result,
                commodity=commodity,
                base_currency=base_currency,
                date=date)

            # Store in our result dictionary
            prices[base_currency] = price

            # Log the result
            self._logger.debug(
                f"Got {method_name} from {source_spec.source}/{source_spec.ticker} "
                f"for {base_currency}/{commodity.currency}")

            # Cache the result
            self._cache_manager.put(base_currency, commodity.currency, date,
                                    price)

        return prices

    def _fetch_price_series(self, commodity: Commodity,
                            time_begin: datetime.datetime,
                            time_end: datetime.datetime) -> List[Price]:
        """Fetch a price series for a commodity.
        
        This method handles the specific logic for fetching price series:
        1. Extract source specs from commodity metadata
        2. Try sources until one succeeds for each currency
        3. Process results into Price objects and cache them
        
        Args:
            commodity: The commodity to fetch prices for
            time_begin: The start of the time range
            time_end: The end of the time range
            
        Returns:
            A list of Price objects sorted by date
        """
        source_specs = self._get_source_specs(commodity)

        all_prices = []
        for base_currency, price_sources in source_specs.items():
            result_pair = self._try_sources(price_sources,
                                            'get_prices_series',
                                            args=(time_begin, time_end),
                                            is_series=True)

            if not result_pair:
                self._logger.warning(
                    f"Failed to get price series for {base_currency}/{commodity.currency}"
                )
                continue

            source_spec, results = result_pair

            for source_price in results:
                date = source_price.time.date() if isinstance(
                    source_price.time,
                    datetime.datetime) else source_price.time

                price = self._process_single_price_result(
                    source_spec=source_spec,
                    source_price=source_price,
                    commodity=commodity,
                    base_currency=base_currency,
                    date=date)

                all_prices.append(price)

                # Cache each price
                if self._cache_manager:
                    self._cache_manager.put(base_currency, commodity.currency,
                                            date, price)

            # Add debug logging
            self._logger.debug(
                f"Got {len(results)} prices from {source_spec.source}/{source_spec.ticker} "
                f"for {base_currency}/{commodity.currency}")

        # Sort prices by date and return
        all_prices.sort(key=lambda p: p.date)
        return all_prices
