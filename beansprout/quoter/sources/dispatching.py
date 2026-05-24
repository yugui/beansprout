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
automatically. If not, the FetchStrategy classes will fall back to calling single-ticker
methods multiple times.

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

# Set to track modules we've already tried to import
_TRIED_MODULES: Set[str] = set()

# ============================================================================
# Phase 1: New Helper Classes (Strategy Pattern and Support Classes)
# ============================================================================

from abc import ABC, abstractmethod


class FetchStrategy(ABC):
    """Strategy pattern for different types of price fetches.

    This abstraction allows different fetch operations (latest, historical, series)
    to be handled uniformly while delegating to the appropriate source methods.
    """

    @abstractmethod
    def fetch_batch(
        self, source: SourceBase, tickers: List[str]
    ) -> Union[Dict[str, Optional[SourcePrice]], Dict[
            str, Optional[List[SourcePrice]]]]:
        """Fetch prices using the appropriate source method.

        Args:
            source: The source instance to fetch from
            tickers: List of ticker symbols to fetch

        Returns:
            Dictionary mapping ticker to SourcePrice(s) or None if failed
        """
        pass

    @abstractmethod
    def is_series(self) -> bool:
        """Returns True if this fetches series, False for single prices."""
        pass

    @abstractmethod
    def get_cache_date(self) -> Optional[datetime.date]:
        """Get the date to use for caching, or None for no specific date."""
        pass


class LatestPriceFetchStrategy(FetchStrategy):
    """Strategy for fetching latest prices."""

    def fetch_batch(self, source: SourceBase,
                    tickers: List[str]) -> Dict[str, Optional[SourcePrice]]:
        """Fetch latest prices, trying batch method first."""
        if hasattr(source, 'get_latest_prices_batch'):
            return source.get_latest_prices_batch(tickers)

        # Fallback to single calls
        results = {}
        for ticker in tickers:
            try:
                results[ticker] = source.get_latest_price(ticker)
            except Exception as e:
                _logger.debug(f"Failed to get latest price for {ticker}: {e}")
                results[ticker] = None
        return results

    def is_series(self) -> bool:
        return False

    def get_cache_date(self) -> Optional[datetime.date]:
        return datetime.date.today()


class HistoricalPriceFetchStrategy(FetchStrategy):
    """Strategy for fetching historical prices."""

    def __init__(self, date: datetime.date):
        """Initialize with the target date.

        Args:
            date: The date to fetch historical prices for
        """
        self.date = date
        self.datetime = datetime.datetime.combine(date, datetime.time())

    def fetch_batch(self, source: SourceBase,
                    tickers: List[str]) -> Dict[str, Optional[SourcePrice]]:
        """Fetch historical prices, trying batch method first."""
        if hasattr(source, 'get_historical_prices_batch'):
            return source.get_historical_prices_batch(tickers, self.datetime)

        # Fallback to single calls
        results = {}
        for ticker in tickers:
            try:
                results[ticker] = source.get_historical_price(
                    ticker, self.datetime)
            except Exception as e:
                _logger.debug(
                    f"Failed to get historical price for {ticker} at {self.datetime}: {e}"
                )
                results[ticker] = None
        return results

    def is_series(self) -> bool:
        return False

    def get_cache_date(self) -> Optional[datetime.date]:
        return self.date


class PriceSeriesFetchStrategy(FetchStrategy):
    """Strategy for fetching price series."""

    def __init__(self, start_date: datetime.date, end_date: datetime.date):
        """Initialize with the date range.

        Args:
            start_date: Start of the date range
            end_date: End of the date range
        """
        self.start_date = start_date
        self.end_date = end_date
        self.start_datetime = datetime.datetime.combine(
            start_date, datetime.time())
        self.end_datetime = datetime.datetime.combine(end_date,
                                                      datetime.time())

    def fetch_batch(
            self, source: SourceBase,
            tickers: List[str]) -> Dict[str, Optional[List[SourcePrice]]]:
        """Fetch price series, trying batch method first."""
        if hasattr(source, 'get_prices_series_batch'):
            return source.get_prices_series_batch(tickers, self.start_datetime,
                                                  self.end_datetime)

        # Fallback to single calls
        results = {}
        for ticker in tickers:
            try:
                results[ticker] = source.get_prices_series(
                    ticker, self.start_datetime, self.end_datetime)
            except Exception as e:
                _logger.debug(
                    f"Failed to get price series for {ticker} "
                    f"from {self.start_datetime} to {self.end_datetime}: {e}")
                results[ticker] = None
        return results

    def is_series(self) -> bool:
        return True

    def get_cache_date(self) -> Optional[datetime.date]:
        return None  # Series don't use single-date caching


class SourceLoader:
    """Handles source instantiation and caching.

    This class encapsulates the logic for loading price sources from different
    locations (beansprout.quoter.sources, beanprice.sources, or full module paths).
    """

    def __init__(self):
        """Initialize the source loader."""
        self._cache: Dict[str, SourceBase] = {}

    def load(self, source_name: str) -> Optional[SourceBase]:
        """Load and instantiate a price source by name.

        This function tries to load and instantiate a price source in the following order:
        1. Check if it's already loaded in SOURCES
        2. Try to load from beansprout.quoter.sources package
        3. Try to load from beanprice.sources
        4. Try to interpret the name as a full module path

        Args:
            source_name: The name of the source to load

        Returns:
            An instance of the Source class if found, None otherwise
        """
        # Check cache first
        if source_name in self._cache:
            return self._cache[source_name]

        # Try to get source class
        source_class = self._get_source_class(source_name)
        if source_class:
            # Instantiate and cache
            source_instance = source_class()
            self._cache[source_name] = source_instance
            return source_instance

        return None

    def _get_source_class(self,
                          source_name: str) -> Optional[Type[SourceBase]]:
        """Get the source class (not instance) by name.

        Args:
            source_name: The name of the source to load

        Returns:
            The Source class if found, None otherwise
        """
        # 1. Check if it's already loaded in SOURCES
        if source_name in SOURCES:
            return SOURCES[source_name]

        # 2. Try to load from beansprout.quoter.sources package
        sources_module_name = f"beansprout.quoter.sources.{source_name}"
        if sources_module_name not in _TRIED_MODULES:
            _TRIED_MODULES.add(sources_module_name)
            try:
                module = importlib.import_module(sources_module_name)
                if hasattr(module, 'Source'):
                    source_class = getattr(module, 'Source')
                    SOURCES[source_name] = source_class
                    return source_class
            except ImportError:
                _logger.debug(f"No source found in {sources_module_name}")

        # 3. Try to load from beanprice.sources
        beanprice_module_name = f"beanprice.sources.{source_name}"
        if beanprice_module_name not in _TRIED_MODULES:
            _TRIED_MODULES.add(beanprice_module_name)
            try:
                module = importlib.import_module(beanprice_module_name)
                if hasattr(module, 'Source'):
                    source_class = getattr(module, 'Source')
                    SOURCES[source_name] = source_class
                    return source_class
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
                    return source_class
            except ImportError:
                _logger.debug(f"Could not import module: {source_name}")

        # No source found
        _logger.warning(f"No price source found for '{source_name}'")
        return None


class PriceConverter:
    """Handles conversion from SourcePrice to Price directives.

    This class encapsulates the logic for:
    - Handling price inversion for currency pairs
    - Converting SourcePrice to Beancount Price directives
    - Caching converted prices
    """

    def convert_single_price_results(
            self,
            spec_commodity_pairs: List[Tuple[SourceSpec, str]],
            results: Dict[str, Optional[SourcePrice]],
            cache_mgr: Optional[cache_manager.CacheManager],
            date: Optional[datetime.date] = None) -> Dict[str, Price]:
        """Convert single price results to Price directives.

        Args:
            spec_commodity_pairs: List of (SourceSpec, commodity) tuples
            results: Results from source batch method (ticker -> SourcePrice)
            cache_mgr: Cache manager for storing results
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
                price = self._convert_single(source_spec=spec,
                                             source_price=source_price,
                                             commodity=commodity,
                                             base_currency=spec.quote_currency,
                                             date=date)
                prices[spec.ticker] = price

                # Cache the result
                if cache_mgr:
                    cache_mgr.put(spec.quote_currency, commodity, date, price)

        return prices

    def convert_series_results(
        self, spec_commodity_pairs: List[Tuple[SourceSpec, str]],
        results: Dict[str, Optional[List[SourcePrice]]],
        cache_mgr: Optional[cache_manager.CacheManager]
    ) -> Dict[str, List[Price]]:
        """Convert price series results to Price directives.

        Args:
            spec_commodity_pairs: List of (SourceSpec, commodity) tuples
            results: Results from source batch method (ticker -> List[SourcePrice])
            cache_mgr: Cache manager for storing results

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
                    price = self._convert_single(
                        source_spec=spec,
                        source_price=source_price,
                        commodity=commodity,
                        base_currency=spec.quote_currency,
                        date=date)
                    price_list.append(price)

                    # Cache each result
                    if cache_mgr:
                        cache_mgr.put(spec.quote_currency, commodity, date,
                                      price)

                # Sort by date
                price_list.sort(key=lambda p: p.date)
                prices_by_ticker[spec.ticker] = price_list

        return prices_by_ticker

    def _convert_single(self, source_spec: SourceSpec,
                        source_price: SourcePrice, commodity: str,
                        base_currency: str, date: datetime.date) -> Price:
        """Convert a single SourcePrice to Price directive.

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

        # Note: Inversion is handled in the calling methods before this is called
        return Price(
            meta=meta,
            date=source_price.time.date(),
            currency=commodity,
            amount=Amount(number=source_price.price, currency=base_currency),
        )


# ============================================================================
# End of Phase 1 Helper Classes
# ============================================================================

# ============================================================================
# Phase 2: Composite Pattern for Source Fallback
# ============================================================================


class SourceNode(ABC):
    """Base class for composite pattern - represents a node in the fallback tree.

    This abstraction allows us to build an explicit tree structure for the
    systematic fallback algorithm, making it easier to test and extend.
    """

    @abstractmethod
    def fetch(
        self, commodity_specs: Dict[str,
                                    List[SourceSpec]], strategy: FetchStrategy,
        cache_mgr: Optional[cache_manager.CacheManager]
    ) -> Dict[str, Union[Price, List[Price]]]:
        """Fetch prices for given commodities using this node's strategy.

        Args:
            commodity_specs: Map of commodity symbol to list of SourceSpecs to try
            strategy: The fetch strategy to use
            cache_mgr: Cache manager for storing results

        Returns:
            Map of commodity symbol to Price or List[Price]
        """
        pass


class LeafSourceNode(SourceNode):
    """Leaf node - represents a single source attempt.

    Fetches from one specific source for a group of commodities.
    """

    def __init__(self, source_name: str, source_loader: SourceLoader,
                 price_converter: PriceConverter):
        """Initialize the leaf node.

        Args:
            source_name: Name of the source to fetch from
            source_loader: Loader instance for getting source instances
            price_converter: Converter instance for SourcePrice → Price conversion
        """
        self.source_name = source_name
        self.source_loader = source_loader
        self.price_converter = price_converter
        self._logger = logging.getLogger(__name__)

    def fetch(
        self, commodity_specs: Dict[str,
                                    List[SourceSpec]], strategy: FetchStrategy,
        cache_mgr: Optional[cache_manager.CacheManager]
    ) -> Dict[str, Union[Price, List[Price]]]:
        """Fetch from this specific source."""
        # Load source
        source = self.source_loader.load(self.source_name)
        if not source:
            return {}

        # Extract specs that match this source
        relevant_specs = []
        for commodity, specs in commodity_specs.items():
            for spec in specs:
                if spec.source == self.source_name:
                    relevant_specs.append((spec, commodity))
                    break  # Only take first matching spec per commodity

        if not relevant_specs:
            return {}

        # Use strategy to fetch
        tickers = [spec.ticker for spec, _ in relevant_specs]
        try:
            source_results = strategy.fetch_batch(source, tickers)
        except Exception as e:
            self._logger.warning(
                f"Error fetching from {self.source_name}: {e}")
            return {}

        # Convert to Price objects
        if strategy.is_series():
            prices = self.price_converter.convert_series_results(
                relevant_specs, source_results, cache_mgr)
        else:
            date = strategy.get_cache_date()
            prices = self.price_converter.convert_single_price_results(
                relevant_specs, source_results, cache_mgr, date)

        # Return with commodity keys (not ticker keys)
        result = {}
        for spec, commodity in relevant_specs:
            if spec.ticker in prices:
                result[commodity] = prices[spec.ticker]

        return result


class FallbackSourceNode(SourceNode):
    """Composite node - tries multiple sources in sequence.

    Implements the systematic fallback algorithm by trying each child
    node in order until all commodities are satisfied.
    """

    def __init__(self, children: List[SourceNode]):
        """Initialize the fallback node.

        Args:
            children: List of child nodes to try in order
        """
        self.children = children
        self._logger = logging.getLogger(__name__)

    def fetch(
        self, commodity_specs: Dict[str,
                                    List[SourceSpec]], strategy: FetchStrategy,
        cache_mgr: Optional[cache_manager.CacheManager]
    ) -> Dict[str, Union[Price, List[Price]]]:
        """Try each child source in order until all commodities are satisfied."""
        all_results = {}
        pending_specs = commodity_specs.copy()

        for i, child in enumerate(self.children):
            if not pending_specs:
                break

            self._logger.debug(
                f"Fallback level {i+1}: trying {len(pending_specs)} commodities"
            )

            # Try this child
            results = child.fetch(pending_specs, strategy, cache_mgr)

            # Collect successful results
            all_results.update(results)

            # Remove successful commodities from pending
            for commodity in results.keys():
                pending_specs.pop(commodity, None)

        if pending_specs:
            self._logger.debug(
                f"Fallback complete: {len(pending_specs)} commodities remain unfetched"
            )

        return all_results


class ParallelSourceNode(SourceNode):
    """Composite node - groups commodities by source and fetches in parallel.

    Used within a single fallback level to batch requests to the same source.
    """

    def __init__(self, source_nodes: Dict[str, LeafSourceNode]):
        """Initialize the parallel node.

        Args:
            source_nodes: Map of source_name -> LeafSourceNode
        """
        self.source_nodes = source_nodes
        self._logger = logging.getLogger(__name__)

    def fetch(
        self, commodity_specs: Dict[str,
                                    List[SourceSpec]], strategy: FetchStrategy,
        cache_mgr: Optional[cache_manager.CacheManager]
    ) -> Dict[str, Union[Price, List[Price]]]:
        """Group commodities by their first source and fetch in parallel batches."""
        # Group by source
        groups_by_source: Dict[str, Dict[str, List[SourceSpec]]] = {}
        for commodity, specs in commodity_specs.items():
            if not specs:
                continue

            first_spec = specs[0]
            source_name = first_spec.source

            if source_name not in groups_by_source:
                groups_by_source[source_name] = {}

            groups_by_source[source_name][commodity] = [first_spec]

        # Fetch from each source group
        all_results = {}
        for source_name, group_specs in groups_by_source.items():
            if source_name in self.source_nodes:
                self._logger.debug(
                    f"Fetching {len(group_specs)} commodities from {source_name}"
                )
                node = self.source_nodes[source_name]
                results = node.fetch(group_specs, strategy, cache_mgr)
                all_results.update(results)

        return all_results


# ============================================================================
# End of Phase 2 Composite Pattern
# ============================================================================

# For backward compatibility, keep get_source as a module-level function
# that delegates to SourceLoader
_source_loader_instance = SourceLoader()


def get_source(source_name: str) -> Optional[SourceBase]:
    """Get a price source instance by name (backward compatibility wrapper).

    This function delegates to SourceLoader for actual implementation.
    Kept for backward compatibility with existing code.

    Args:
        source_name: The name of the source to load

    Returns:
        An instance of the Source class if found, None otherwise
    """
    return _source_loader_instance.load(source_name)


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

        # Phase 3: Initialize new helper classes
        self._source_loader = SourceLoader()
        self._price_converter = PriceConverter()

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
        """Get or create a source by name.

        Phase 5: Batch wrapping removed - FetchStrategy handles batch/single fallback.

        Args:
            source_name: The name of the source to get

        Returns:
            A Source instance if found, None otherwise
        """
        if source_name in self._sources_cache:
            return self._sources_cache[source_name]

        source = get_source(source_name=source_name)
        if source:
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

        Phase 3: Delegate to PriceConverter for consistent processing.

        Args:
            spec_commodity_pairs: List of (SourceSpec, commodity) tuples
            results: Results from source batch method
            date: The date for the prices, or None to use today's date

        Returns:
            Dictionary mapping ticker to Price objects
        """
        # Phase 3: Use PriceConverter
        return self._price_converter.convert_single_price_results(
            spec_commodity_pairs, results, self._cache_manager, date)

    def _process_series_results(
            self, spec_commodity_pairs: List[Tuple[SourceSpec, str]],
            results: Dict[str, List[SourcePrice]]) -> Dict[str, List[Price]]:
        """Process price series results.

        Phase 3: Delegate to PriceConverter for consistent processing.

        Args:
            spec_commodity_pairs: List of (SourceSpec, commodity) tuples
            results: Results from source batch method

        Returns:
            Dictionary mapping ticker to list of Price objects
        """
        # Phase 3: Use PriceConverter
        return self._price_converter.convert_series_results(
            spec_commodity_pairs, results, self._cache_manager)
