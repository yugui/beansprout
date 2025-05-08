#!/usr/bin/env python3
"""Module for fetching price quotes for commodities.

This module provides functionality to fetch price quotes for commodities using
both built-in price sources from beanprice and custom sources from the quoters
directory.
"""

import datetime
import importlib
import logging
from typing import Dict, List, Optional, Tuple, Set

from beancount.core import data
from beancount.core.data import Commodity, Price
from beancount.core.number import Decimal, ZERO
from beanprice import source as beanprice_source

# Import commodity_finder for finding price sources
from quoters import commodity_finder
# Import SOURCES from the quoters package
from quoters import SOURCES

# Dictionary of custom source modules available in this package
CUSTOM_SOURCES: Set[str] = set(k for k in SOURCES.keys() if k != 'example')


class QuoteFetcher:
    """Class for fetching price quotes for commodities.
    
    This class provides methods to fetch price quotes for commodities using
    the source information specified in their price metadata. It can use both
    custom sources from the quoters directory and built-in sources from beanprice.
    """

    def __init__(self, custom_only: bool = False) -> None:
        """Initialize the QuoteFetcher.
        
        Args:
            custom_only: If True, only use custom quoters from the quoters directory.
                         If False, also use built-in beanprice sources.
        """
        self.custom_only = custom_only
        self._logger = logging.getLogger(__name__)

    def fetch_quote(self, commodity: Commodity,
                    quote_date: datetime.date) -> Optional[Price]:
        """Fetch a price quote for a commodity on a specific date.
        
        Args:
            commodity: The commodity to fetch a price for.
            quote_date: The date to fetch the price for.
            
        Returns:
            A Price directive with the fetched price, or None if no price could be fetched.
        """
        if 'price' not in commodity.meta:
            return None

        finder = commodity_finder.CommodityFinder()
        source_specs = finder.get_price_sources(commodity=commodity)

        # Try each currency-source pair
        for quote_currency, source_spec in source_specs.items():
            try:
                price_entry = self._fetch_quote_for_currency(
                    commodity=commodity,
                    quote_date=quote_date,
                    quote_currency=quote_currency,
                    source_spec=source_spec)
                if price_entry:
                    return price_entry
            except Exception as e:
                self._logger.warning(
                    f"Error fetching quote for {commodity.currency} "
                    f"using {source_spec}: {e}")
                continue

        # No price found for any currency-source pair
        return None

    def _fetch_quote_for_currency(self, commodity: Commodity,
                                  quote_date: datetime.date,
                                  quote_currency: str,
                                  source_spec: str) -> Optional[Price]:
        """Fetch a quote for a commodity in a specific currency.
        
        Args:
            commodity: The commodity to fetch a price for.
            quote_date: The date to fetch the price for.
            quote_currency: The currency to get the price in.
            source_spec: The source specification string (may include multiple sources).
            
        Returns:
            A Price directive with the fetched price, or None if no price could be fetched.
        """
        # Split multiple sources (comma-separated)
        for source_ticker in source_spec.split(','):
            source_name, ticker = self._parse_source_ticker(source_ticker)

            # Get the appropriate source
            source = self._get_source(source_name, self.custom_only)
            if not source:
                self._logger.warning(
                    f"Source '{source_name}' not found, skipping")
                continue

            try:
                # Try to get the latest price first
                price_tuple = source.get_latest_price(ticker)

                # If that fails or we need a historical price, try get_historical_price
                if not price_tuple or quote_date < datetime.date.today():
                    price_tuple = source.get_historical_price(
                        ticker, quote_date)

                # If we got a price, create and return a Price directive
                if price_tuple:
                    amount, price_date, currency = price_tuple

                    # Make sure the date matches our requested date
                    if price_date != quote_date:
                        self._logger.info(
                            f"Requested price for {quote_date} but got {price_date}"
                        )

                    # Create a metadata dictionary for the price entry
                    meta = {
                        'filename': commodity.meta.get('filename',
                                                       '<unknown>'),
                        'lineno': commodity.meta.get('lineno', 0),
                        'source': source_ticker
                    }

                    # Create and return the Price directive
                    return data.Price(meta=meta,
                                      date=price_date,
                                      currency=commodity.currency,
                                      amount=amount)
            except Exception as e:
                self._logger.warning(f"Error using source {source_name}: {e}")
                continue

        # No price found with any source
        return None

    def _parse_source_ticker(self, source_ticker: str) -> Tuple[str, str]:
        """Parse a source/ticker string into source name and ticker.
        
        Args:
            source_ticker: A string in the format "source/ticker".
            
        Returns:
            A tuple of (source_name, ticker).
        """
        parts = source_ticker.split('/', 1)
        if len(parts) != 2:
            return (source_ticker, "")  # Invalid format

        return (parts[0], parts[1])

    def _get_source(
            self,
            source_name: str,
            custom_only: bool = False) -> Optional[beanprice_source.Source]:
        """Get a price source by name.
        
        This method tries to get a source from:
        1. Custom sources defined in this package (if available)
        2. Built-in sources from beanprice (if custom_only is False)
        
        Args:
            source_name: The name of the source to get.
            custom_only: If True, only check custom sources.
            
        Returns:
            A Source instance that can fetch prices, or None if no source was found.
        """
        # First try to get a custom source from our package
        if source_name in CUSTOM_SOURCES:
            return self._get_custom_source(source_name)

        # If we couldn't find a custom source and we're allowed to use built-in sources,
        # try to get a built-in source from beanprice
        if not custom_only:
            try:
                # This follows the same approach as beanprice.source.get_source
                module_name = f"beanprice.sources.{source_name}"
                module = importlib.import_module(module_name)
                if hasattr(module, 'Source'):
                    return module.Source()
            except ImportError:
                self._logger.info(
                    f"No built-in source found for '{source_name}'")

        return None

    def _get_custom_source(
            self, source_name: str) -> Optional[beanprice_source.Source]:
        """Get a custom price source from this package.
        
        Args:
            source_name: The name of the custom source to get.
            
        Returns:
            A Source instance from the custom sources, or None if not found.
        """
        source_class = SOURCES.get(source_name)
        if source_class:
            return source_class()
        return None
