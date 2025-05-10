#!/usr/bin/env python3
"""Module for fetching price quotes for commodities.

This module provides functionality to fetch price quotes for commodities using
both built-in price sources from beanprice and custom sources from the quoters
directory.
"""

import datetime
import logging
from collections import namedtuple
from typing import List, Optional, Tuple

from beancount.core import data
from beancount.core.data import Commodity, Price
from beanprice import source as beanprice_source

# Import the get_source function from this package
from beansprout.quoter import get_source

# A namedtuple to represent price source specifications
PriceSource = namedtuple('PriceSource', ['currency', 'source', 'ticker'])


class QuoteFetcher:
    """Class for fetching price quotes for commodities.
    
    This class provides methods to fetch price quotes for commodities using
    the source information specified in their price metadata. It can use both
    custom sources from the quoters directory and built-in sources from beanprice.
    """

    def __init__(self, custom_only: bool = False) -> None:
        """Initialize the QuoteFetcher.
        
        Args:
            custom_only: If True, only use custom quoters from the beansprout.quoter.sources directory.
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

        price_sources = self._get_price_sources(commodity=commodity)

        # Try each price source in order
        for price_source in price_sources:
            try:
                price_entry = self._fetch_quote_for_source(
                    commodity=commodity,
                    quote_date=quote_date,
                    price_source=price_source)
                if price_entry:
                    return price_entry
            except Exception as e:
                self._logger.warning(
                    f"Error fetching quote for {commodity.currency} "
                    f"using {price_source.source}/{price_source.ticker}: {e}")
                continue

        # No price found for any source
        return None

    def _get_price_sources(self, commodity: Commodity) -> List[PriceSource]:
        """Extract price sources from commodity metadata.
        
        The price metadata format is: "CURRENCY1:SOURCE1/TICKER1 CURRENCY2:SOURCE2/TICKER2 ..."
        For example: "USD:yahoo/AAPL CAD:yahoo/AAPL.TO"
        
        Multiple sources for the same currency can be specified with comma separations:
        "USD:source1/TICKER1,source2/TICKER2"
        
        Args:
            commodity: Commodity directive to extract price sources from.
            
        Returns:
            List of PriceSource tuples with (currency, source, ticker) for each price source.
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
                sources.append(
                    PriceSource(currency=currency,
                                source=source,
                                ticker=ticker))

        return sources

    def _fetch_quote_for_source(self, commodity: Commodity,
                                quote_date: datetime.date,
                                price_source: PriceSource) -> Optional[Price]:
        """Fetch a quote for a commodity using a specific price source.
        
        Args:
            commodity: The commodity to fetch a price for.
            quote_date: The date to fetch the price for.
            price_source: The price source tuple (currency, source, ticker).
            
        Returns:
            A Price directive with the fetched price, or None if no price could be fetched.
        """
        source_name = price_source.source
        ticker = price_source.ticker

        # Get the appropriate source using the _get_source method
        # Explicitly pass the custom_only parameter for test compatibility
        source = self._get_source(source_name, self.custom_only)
        if not source:
            self._logger.warning(f"Source '{source_name}' not found, skipping")
            return None

        try:
            # Try to get the latest price first
            price_tuple = source.get_latest_price(ticker)

            # If that fails or we need a historical price, try get_historical_price
            if not price_tuple or quote_date < datetime.date.today():
                price_tuple = source.get_historical_price(ticker, quote_date)

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
                    'filename': commodity.meta.get('filename', '<unknown>'),
                    'lineno': commodity.meta.get('lineno', 0),
                    'source': f"{source_name}/{ticker}"
                }

                # Create and return the Price directive
                return data.Price(meta=meta,
                                  date=price_date,
                                  currency=commodity.currency,
                                  amount=amount)
        except Exception as e:
            self._logger.warning(f"Error using source {source_name}: {e}")
            return None

        # No price found
        return None

    def _get_source(
            self,
            source_name: str,
            custom_only: bool = None) -> Optional[beanprice_source.Source]:
        """Get a price source by name.
        
        This method is a wrapper around the global get_source function to maintain
        backwards compatibility with tests that mock this method.
        
        Args:
            source_name: The name of the source to get.
            custom_only: If True, only try to load from the beansprout.quoter.sources package.
                         If None, use the QuoteFetcher's custom_only setting.
            
        Returns:
            A Source instance that can fetch prices, or None if no source was found.
        """
        # If custom_only is explicitly provided, use it; otherwise use the instance setting
        use_custom_only = self.custom_only if custom_only is None else custom_only

        # Delegate to the global get_source function
        return get_source(source_name=source_name, custom_only=use_custom_only)