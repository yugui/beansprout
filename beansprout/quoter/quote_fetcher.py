#!/usr/bin/env python3
"""Module for fetching price quotes for commodities.

This module provides functionality to fetch price quotes for commodities using
both built-in price sources from beanprice and custom sources from the quoters
directory.
"""

import datetime
import logging
from typing import List, Optional, Tuple, Iterable, Dict, Set, Callable, NamedTuple, Union

from beancount.core import data
from beancount.core.data import Commodity, Price, Amount
from beancount.core.number import Decimal
from beanprice import source as beanprice_source
from beanprice.source import SourcePrice

# Import from the new location directly
from beansprout.quoter.sources.dispatching import SourceDispatcher
from beansprout.quoter.sources import cache_manager
from beansprout.quoter.expression_parser import parse_price_expression, SourceSpec

# Named tuples for the new systematic fallback algorithm
CommodityKey = NamedTuple(
    'CommodityKey',
    [
        ('commodity', str),  # e.g., "AAPL"
        ('base_currency', str)  # e.g., "USD"
    ])

SourceGroupKey = NamedTuple(
    'SourceGroupKey',
    [
        ('base_currency', str),  # e.g., "USD"
        ('source', str)  # e.g., "yahoo"
    ])

# Legacy named tuple - will be removed after migration
CommodityPair = NamedTuple('CommodityPair', [
    ('base_currency', str),
    ('commodity_currency', str),
])


class QuoteFetcher:
    """Class for fetching price quotes for commodities.
    
    This class provides methods to fetch price quotes for commodities using
    the source information specified in their price metadata. It can use both
    custom sources from the quoters directory and built-in sources from beanprice.
    
    Internally, it uses the SourceDispatcher to delegate price fetching to
    appropriate subsources.
    """

    def __init__(self, cache_mgr: cache_manager.CacheManager) -> None:
        """Initialize the QuoteFetcher.
        
        Args:
            cache_mgr: The cache manager to use for caching price quotes.
                       If None, a MemoryCacheManager will be used.
        """
        self._logger = logging.getLogger(__name__)
        # Create a SourceDispatcher instance to handle source delegation
        self._dispatch_source = SourceDispatcher(cache_manager=cache_mgr)

    def fetch_latest_quotes(self, commodities: List[Commodity]) -> List[Price]:
        """Fetch latest price quotes for multiple commodities using source-first iteration.
        
        Args:
            commodities: List of commodities to fetch quotes for.
            
        Returns:
            List of Price directives for all successfully fetched quotes.
        """

        def call_dispatcher(
            spec_commodity_pairs: List[Tuple[SourceSpec, str]]
        ) -> Dict[str, Price]:
            return self._dispatch_source.fetch_latest_prices_batch(
                spec_commodity_pairs)

        return self._fetch_quotes_with_systematic_fallback(
            commodities, call_dispatcher)

    def fetch_historical_quotes(self, commodities: List[Commodity],
                                quote_date: datetime.date) -> List[Price]:
        """Fetch historical price quotes for multiple commodities using source-first iteration.
        
        Args:
            commodities: List of commodities to fetch quotes for.
            quote_date: The specific date to fetch prices for.
            
        Returns:
            List of Price directives for all successfully fetched quotes.
        """

        def call_dispatcher(
            spec_commodity_pairs: List[Tuple[SourceSpec, str]]
        ) -> Dict[str, Price]:
            dt = datetime.datetime.combine(quote_date, datetime.time())
            return self._dispatch_source.fetch_historical_prices_batch(
                spec_commodity_pairs, dt)

        return self._fetch_quotes_with_systematic_fallback(
            commodities, call_dispatcher)

    def fetch_quote_series_bulk(self, commodities: List[Commodity],
                                start_date: datetime.date,
                                end_date: datetime.date) -> List[Price]:
        """Fetch price series for multiple commodities using source-first iteration.
        
        Args:
            commodities: List of commodities to fetch quotes for.
            start_date: The starting date for the price series.
            end_date: The ending date for the price series.
            
        Returns:
            List of Price directives for all successfully fetched quotes.
        """

        def call_dispatcher(
            spec_commodity_pairs: List[Tuple[SourceSpec, str]]
        ) -> Dict[str, List[Price]]:
            start_dt = datetime.datetime.combine(start_date, datetime.time())
            end_dt = datetime.datetime.combine(end_date, datetime.time())
            return self._dispatch_source.fetch_prices_series_batch(
                spec_commodity_pairs, start_dt, end_dt)

        return self._fetch_quotes_with_systematic_fallback(
            commodities, call_dispatcher)

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
            Dict mapping currency -> List[SourceSpec] for each price source.
            The invert flag indicates whether the price should be inverted (1/price).
        """
        if 'price' not in commodity.meta:
            return {}

        price_meta = commodity.meta['price']

        try:
            # Use the shared parser for consistent parsing logic
            return parse_price_expression(price_meta)
        except ValueError as e:
            self._logger.warning(
                f"Failed to parse price metadata '{price_meta}' for commodity {commodity.currency}: {e}"
            )
            return {}

    def _parse_commodities_to_specs(
            self, commodities: List[Commodity]
    ) -> Dict[CommodityKey, List[SourceSpec]]:
        """Parse commodities into SourceSpec lists with fallback order.
        
        Args:
            commodities: List of commodities to process.
            
        Returns:
            Dictionary mapping CommodityKey to list of SourceSpec objects ordered by priority.
        """
        commodity_specs = {}

        for commodity in commodities:
            if 'price' not in commodity.meta:
                continue

            try:
                # Parse the price expression once per commodity
                source_specs_by_currency = self._get_source_specs(commodity)

                # Create CommodityKey for each base currency
                for base_currency, source_specs in source_specs_by_currency.items(
                ):
                    key = CommodityKey(commodity=commodity.currency,
                                       base_currency=base_currency)
                    commodity_specs[key] = source_specs

            except ValueError as e:
                self._logger.warning(
                    f"Failed to parse price metadata for {commodity.currency}: {e}"
                )
                continue

        return commodity_specs

    def _group_by_source(
        self, pending_specs: Dict[CommodityKey, List[SourceSpec]]
    ) -> Dict[SourceGroupKey, List[Tuple[CommodityKey, SourceSpec]]]:
        """Group by (base_currency, source) using first element of each SourceSpec list.
        
        Args:
            pending_specs: Dictionary mapping CommodityKey to SourceSpec lists.
            
        Returns:
            Dictionary mapping SourceGroupKey to lists of (CommodityKey, SourceSpec) pairs.
        """
        source_groups = {}

        for commodity_key, source_specs in pending_specs.items():
            if source_specs:  # Only process non-empty lists
                first_spec = source_specs[0]
                group_key = SourceGroupKey(
                    base_currency=first_spec.quote_currency,
                    source=first_spec.source)

                if group_key not in source_groups:
                    source_groups[group_key] = []

                source_groups[group_key].append((commodity_key, first_spec))

        return source_groups

    def _remove_successful_specs(self, pending_specs: Dict[CommodityKey,
                                                           List[SourceSpec]],
                                 successful_keys: Set[CommodityKey]) -> None:
        """Remove SourceSpec lists for successful fetches.
        
        Args:
            pending_specs: Dictionary to modify by removing successful keys.
            successful_keys: Set of CommodityKey objects that were successfully fetched.
        """
        for key in successful_keys:
            pending_specs.pop(key, None)

    def _advance_to_next_fallback(
            self, pending_specs: Dict[CommodityKey, List[SourceSpec]]) -> None:
        """Remove first element from each SourceSpec list and clean up empty lists.
        
        Args:
            pending_specs: Dictionary to modify by advancing to next fallback.
        """
        empty_keys = []

        for key, source_specs in pending_specs.items():
            if source_specs:
                source_specs.pop(
                    0)  # Remove the first element (we just tried it)
                if not source_specs:  # If list is now empty, mark for removal
                    empty_keys.append(key)

        # Remove empty lists
        for key in empty_keys:
            del pending_specs[key]

    def _fetch_quotes_with_systematic_fallback(
        self, commodities: List[Commodity],
        dispatcher_func: Callable[[List[Tuple[SourceSpec, str]]],
                                  Dict[str, Union[Price, List[Price]]]]
    ) -> List[Price]:
        """Main algorithm implementation using systematic fallback.
        
        Args:
            commodities: List of commodities to fetch quotes for.
            dispatcher_func: Function that takes List[Tuple[SourceSpec, str]] and returns results.
            
        Returns:
            List of Price directives for all successfully fetched quotes.
        """
        # Step 1: Parse commodities into SourceSpec lists
        pending_specs = self._parse_commodities_to_specs(commodities)
        all_prices = []

        self._logger.debug(
            f"Starting systematic fallback for {len(pending_specs)} commodity/currency pairs"
        )

        # Continue until no more specs to try
        iteration = 0
        while pending_specs:
            iteration += 1
            self._logger.debug(
                f"Fallback iteration {iteration}: {len(pending_specs)} remaining pairs"
            )

            # Step 2: Group by (base_currency, source) using first element
            source_groups = self._group_by_source(pending_specs)

            if not source_groups:
                break

            successful_keys = set()

            # Step 3: Process each source group
            for group_key, commodity_spec_pairs in source_groups.items():
                self._logger.debug(
                    f"Processing source group {group_key} with {len(commodity_spec_pairs)} specs"
                )

                # Create spec-commodity pairs for the entire source group
                spec_commodity_pairs = []
                commodity_keys = []

                for commodity_key, spec in commodity_spec_pairs:
                    commodity = commodity_key.commodity
                    spec_commodity_pairs.append((spec, commodity))
                    commodity_keys.append(commodity_key)

                # Make ONE bulk call for the entire source group
                try:
                    results = dispatcher_func(spec_commodity_pairs)

                    if results:
                        # Mark ALL commodity keys in this source group as successful
                        for commodity_key in commodity_keys:
                            successful_keys.add(commodity_key)

                        # Collect prices
                        for ticker, price_or_prices in results.items():
                            if isinstance(price_or_prices, list):
                                all_prices.extend(price_or_prices)
                            else:
                                all_prices.append(price_or_prices)

                        self._logger.debug(
                            f"Successfully fetched {len(results)} price(s) from {group_key.source} for source group"
                        )

                except Exception as e:
                    self._logger.warning(
                        f"Error fetching quotes from {group_key.source}: {e}")

            # Step 4: Remove successful specs
            self._remove_successful_specs(pending_specs, successful_keys)

            # Step 5: Advance to next fallback level
            self._advance_to_next_fallback(pending_specs)

        self._logger.debug(
            f"Systematic fallback completed after {iteration} iterations, fetched {len(all_prices)} total prices"
        )
        return all_prices
