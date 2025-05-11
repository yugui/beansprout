#!/usr/bin/env python3
"""Module for fetching price quotes for commodities.

This module provides functionality to fetch price quotes for commodities using
both built-in price sources from beanprice and custom sources from the quoters
directory.
"""

import datetime
import logging
from typing import List, Optional, Tuple, Iterable

from beancount.core import data
from beancount.core.data import Commodity, Price, Amount
from beancount.core.number import Decimal
from beanprice import source as beanprice_source
from beanprice.source import SourcePrice

# Import from the new location directly
from beansprout.quoter.sources.dispatching import SourceDispatcher
from beansprout.quoter.sources import cache_manager


class QuoteFetcher:
    """Class for fetching price quotes for commodities.
    
    This class provides methods to fetch price quotes for commodities using
    the source information specified in their price metadata. It can use both
    custom sources from the quoters directory and built-in sources from beanprice.
    
    Internally, it uses the SourceDispatcher to delegate price fetching to
    appropriate subsources.
    """

    def __init__(self,
                 cache_mgr: cache_manager.CacheManager,
                 custom_only: bool = False) -> None:
        """Initialize the QuoteFetcher.
        
        Args:
            cache_mgr: The cache manager to use for caching price quotes.
                       If None, a MemoryCacheManager will be used.
            custom_only: If True, only use custom quoters from the beansprout.quoter.sources directory.
                         If False, also use built-in beanprice sources.
        """
        self.custom_only = custom_only
        self._logger = logging.getLogger(__name__)
        # Create a SourceDispatcher instance to handle source delegation
        self._dispatch_source = SourceDispatcher(cache_manager=cache_mgr,
                                                 custom_only=custom_only)

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

        try:
            # Use SourceDispatcher to get the prices
            if quote_date == datetime.date.today():
                prices = self._dispatch_source.get_latest_price(commodity)
            else:
                # Convert date to datetime as required by the interface
                dt = datetime.datetime.combine(quote_date, datetime.time())
                prices = self._dispatch_source.get_historical_price(
                    commodity, dt)

            # If we got no prices, return None
            prices_list = list(prices)
            if not prices_list:
                return None

            # Use the first price in the list (for one commodity, there might be multiple prices in different currencies)
            price = prices_list[0]

            # Create a metadata dictionary with additional information
            meta = {
                'filename': commodity.meta.get('filename', '<unknown>'),
                'lineno': commodity.meta.get('lineno', 0),
                'source': 'dispatching',
            }
            if price.meta:
                meta.update(price.meta)

            # Create and return the Price directive with all the necessary information
            return data.Price(meta=meta,
                              date=price.date,
                              currency=price.currency,
                              amount=price.amount)
        except Exception as e:
            self._logger.warning(
                f"Error fetching quote for {commodity.currency}: {e}")

        return None
