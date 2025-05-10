#!/usr/bin/env python3
"""Module for fetching price quotes for commodities.

This module provides functionality to fetch price quotes for commodities using
both built-in price sources from beanprice and custom sources from the quoters
directory.
"""

import datetime
import logging
from typing import List, Optional, Tuple

from beancount.core import data
from beancount.core.data import Commodity, Price
from beanprice import source as beanprice_source

# Import from the new location directly
from beansprout.quoter.sources.dispatching import DispatchingSource


class QuoteFetcher:
    """Class for fetching price quotes for commodities.
    
    This class provides methods to fetch price quotes for commodities using
    the source information specified in their price metadata. It can use both
    custom sources from the quoters directory and built-in sources from beanprice.
    
    Internally, it uses the DispatchingSource to delegate price fetching to
    appropriate subsources.
    """

    def __init__(self, custom_only: bool = False) -> None:
        """Initialize the QuoteFetcher.
        
        Args:
            custom_only: If True, only use custom quoters from the beansprout.quoter.sources directory.
                         If False, also use built-in beanprice sources.
        """
        self.custom_only = custom_only
        self._logger = logging.getLogger(__name__)
        # Create a DispatchingSource instance to handle source delegation
        self._dispatch_source = DispatchingSource(custom_only=custom_only)

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
            # Format the ticker for DispatchingSource
            # The format is "COMMODITY:PRICE_META"
            ticker = f"{commodity.currency}:{commodity.meta['price']}"

            # Use DispatchingSource to get the price
            if quote_date == datetime.date.today():
                price_tuple = self._dispatch_source.get_latest_price(ticker)
            else:
                price_tuple = self._dispatch_source.get_historical_price(
                    ticker, quote_date)

            # If we got a price, create and return a Price directive
            if price_tuple:
                amount, price_date, currency = price_tuple

                # Create a metadata dictionary for the price entry
                meta = {
                    'filename': commodity.meta.get('filename', '<unknown>'),
                    'lineno': commodity.meta.get('lineno', 0),
                    'source': "dispatching"
                }

                # Create and return the Price directive
                return data.Price(meta=meta,
                                  date=price_date,
                                  currency=commodity.currency,
                                  amount=amount)
        except Exception as e:
            self._logger.warning(
                f"Error fetching quote for {commodity.currency}: {e}")

        return None
