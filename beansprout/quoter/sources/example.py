"""Example custom price quoter for beancount.

This is a template showing how to implement a custom price source for
beancount that can be used with both bean-price and bean-quote commands.
"""

import datetime
from typing import Optional, Tuple

import requests
from beanprice.source import Source as SourceBase
from beancount.core.number import Decimal


class Source(SourceBase):
    """Example price source implementation.
    
    This is an example template showing how to implement a custom price source.
    It doesn't actually fetch real prices but demonstrates the required interface.
    """

    def get_latest_price(
            self, ticker: str) -> Optional[Tuple[Decimal, datetime.date, str]]:
        """Get the latest available price for the given ticker.
        
        Args:
            ticker: A string representing the ticker to fetch a price for.
                   Example: 'AAPL' or '^USDEUR'
                   
        Returns:
            A tuple of (price, date, currency) if successful, or None if not.
            The price is a Decimal instance, the date is a datetime.date instance,
            and the currency is a string.
        """
        # This is just an example that returns a dummy price
        # Replace this with actual API calls in real implementations

        if ticker.startswith('^'):
            # Handle inverted rates
            ticker = ticker[1:]

        try:
            # Simulate an API call
            price = Decimal('100.00')  # Example fixed price
            date = datetime.date.today()
            currency = "USD"  # Default currency

            return price, date, currency
        except Exception as e:
            self.log_error(f"Error fetching price for {ticker}: {e}")
            return None

    def get_historical_price(
            self, ticker: str, time: datetime.date
    ) -> Optional[Tuple[Decimal, datetime.date, str]]:
        """Get a historical price for the given ticker and date.
        
        Args:
            ticker: A string representing the ticker to fetch a price for.
            time: The date to fetch prices for.
            
        Returns:
            A tuple of (price, date, currency) if successful, or None if not.
        """
        # This is just an example that returns a dummy historical price
        # Replace this with actual API calls in real implementations

        if ticker.startswith('^'):
            # Handle inverted rates
            ticker = ticker[1:]

        try:
            # Simulate an API call for historical data
            price = Decimal('95.00')  # Example fixed historical price
            date = time  # Use the requested date
            currency = "USD"

            return price, date, currency
        except Exception as e:
            self.log_error(
                f"Error fetching historical price for {ticker} on {time}: {e}")
            return None
