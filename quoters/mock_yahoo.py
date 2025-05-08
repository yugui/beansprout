#!/usr/bin/env python3
"""Mock Yahoo price source for testing purposes.

This is a mock implementation of a Yahoo price source used specifically for testing
the bean-quote command. It returns predetermined values rather than making actual
network requests. It can be referenced in commodity definitions with
'price: "USD:mock_yahoo/TICKER"'.
"""

import datetime
import logging
from typing import Optional, Tuple

from beancount.core.number import Decimal
from beanprice.source import Source as PriceSource


class Source(PriceSource):
    """Mock Yahoo price source implementation for testing purposes."""

    def get_latest_price(
            self, ticker: str) -> Optional[Tuple[Decimal, datetime.date, str]]:
        """Get the latest price for the given ticker.

        Args:
            ticker: The ticker symbol to get the price for.
            
        Returns:
            A tuple of (price, date, currency) or None if no price could be found.
        """
        logging.info(f"Mock Yahoo: Getting latest price for {ticker}")

        # For test purposes, just return a hardcoded price
        # In a real implementation, this would fetch data from Yahoo Finance
        if ticker.upper() == 'AAPL':
            return Decimal('188.92'), datetime.date.today(), 'USD'
        elif ticker.upper() == 'MSFT':
            return Decimal('414.47'), datetime.date.today(), 'USD'
        elif ticker.upper() == 'GOOGL':
            return Decimal('172.17'), datetime.date.today(), 'USD'

        # No price found for the ticker
        return None

    def get_historical_price(
            self, ticker: str, date: datetime.date
    ) -> Optional[Tuple[Decimal, datetime.date, str]]:
        """Get a historical price for the given ticker and date.
        
        Args:
            ticker: The ticker symbol to get the price for.
            date: The date to get the price for.
            
        Returns:
            A tuple of (price, date, currency) or None if no price could be found.
        """
        logging.info(
            f"Mock Yahoo: Getting historical price for {ticker} on {date}")

        # For test purposes, just return a hardcoded price based on date
        # In a real implementation, this would fetch historical data from Yahoo Finance
        if ticker.upper() == 'AAPL':
            if date.year == 2025 and date.month == 5:
                return Decimal('185.56'), date, 'USD'
            else:
                return Decimal('155.30'), date, 'USD'
        elif ticker.upper() == 'MSFT':
            if date.year == 2025 and date.month == 5:
                return Decimal('410.21'), date, 'USD'
            else:
                return Decimal('395.87'), date, 'USD'
        elif ticker.upper() == 'GOOGL':
            if date.year == 2025 and date.month == 5:
                return Decimal('169.78'), date, 'USD'
            else:
                return Decimal('150.45'), date, 'USD'

        # No historical price found for the ticker and date
        return None
