#!/usr/bin/env python3
"""Tests for the quote_fetcher module."""

import datetime
import os
import unittest
from unittest import mock

from beancount import loader
from beancount.core import data
from beancount.core.data import Commodity, Price
from beancount.core.number import Decimal

from quoters import commodity_finder
from quoters import quote_fetcher


class TestQuoteFetcher(unittest.TestCase):
    """Test the QuoteFetcher class."""

    def setUp(self) -> None:
        """Set up test data with sample commodity definitions."""
        # Get the path to the testdata directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        test_file = os.path.join(current_dir, 'testdata', 'test-commodities.beancount')
        
        # Load entries from the test file
        self.entries, self.errors, self.options_map = loader.load_file(
            filename=test_file)
        
        # Create a finder instance to get commodities
        self.finder = commodity_finder.CommodityFinder()
        self.commodities = self.finder.find_all_commodities(entries=self.entries)
        
        # Set up a mock for the source
        self.mock_source = mock.Mock()
        self.mock_source.get_latest_price.return_value = (Decimal('150.00'), 
                                                         datetime.date(2025, 5, 8), 
                                                         'USD')
        self.mock_source.get_historical_price.return_value = (Decimal('145.00'), 
                                                             datetime.date(2025, 5, 1), 
                                                             'USD')
        
        # Create a fetcher instance
        self.fetcher = quote_fetcher.QuoteFetcher(custom_only=False)
        
        # Replace the fetcher's _get_source method to return our mock
        self.original_get_source = self.fetcher._get_source
        self.fetcher._get_source = mock.Mock(return_value=self.mock_source)

    def tearDown(self) -> None:
        """Tear down test fixtures."""
        # Restore original _get_source method
        if hasattr(self, 'original_get_source'):
            self.fetcher._get_source = self.original_get_source

    def test_fetch_latest_quote(self) -> None:
        """Test fetching the latest quote for a commodity."""
        # Get Apple commodity
        apple = next(c for c in self.commodities if c.currency == "AAPL")
        
        # Fetch the latest quote
        price_entry = self.fetcher.fetch_quote(
            commodity=apple, 
            quote_date=datetime.date(2025, 5, 8)
        )
        
        # Verify the price entry
        self.assertIsInstance(price_entry, Price)
        self.assertEqual(price_entry.currency, "AAPL")
        self.assertEqual(price_entry.amount, Decimal('150.00'))
        self.assertEqual(price_entry.date, datetime.date(2025, 5, 8))
        self.assertEqual(price_entry.meta['source'], 'mock_yahoo/AAPL')

    def test_fetch_historical_quote(self) -> None:
        """Test fetching a historical quote for a commodity."""
        # Get Apple commodity
        apple = next(c for c in self.commodities if c.currency == "AAPL")
        
        # Mock to ensure historical price is used
        self.fetcher._get_source().get_latest_price.return_value = None
        
        # Fetch a historical quote
        price_entry = self.fetcher.fetch_quote(
            commodity=apple, 
            quote_date=datetime.date(2025, 5, 1)
        )
        
        # Verify the price entry
        self.assertIsInstance(price_entry, Price)
        self.assertEqual(price_entry.currency, "AAPL")
        self.assertEqual(price_entry.amount, Decimal('145.00'))
        self.assertEqual(price_entry.date, datetime.date(2025, 5, 1))
        self.assertEqual(price_entry.meta['source'], 'mock_yahoo/AAPL')

    def test_fetch_quote_with_fallback(self) -> None:
        """Test fetching quotes with fallback sources."""
        # Create a commodity with multiple sources
        commodity_with_fallbacks = data.Commodity(
            meta={'filename': 'test', 'lineno': 1, 
                 'price': 'USD:source1/BTC,source2/BTC'},
            date=datetime.date(2025, 5, 8),
            currency='BTC'
        )
        
        # First source fails, second succeeds
        failed_source = mock.Mock()
        # Configure the mock to return None for get_latest_price
        failed_source.get_latest_price.return_value = None
        failed_source.get_historical_price.return_value = None
        
        success_source = mock.Mock()
        # Configure the mock to return a properly formatted price tuple
        success_source.get_latest_price.return_value = (
            Decimal('50000.00'), 
            datetime.date(2025, 5, 8), 
            'USD'
        )
        
        # Override the _get_source method to return different sources based on the source name
        def mock_get_source(source_name, custom_only=False):
            if source_name == 'source1':
                return failed_source
            else:
                return success_source
            
        self.fetcher._get_source = mock_get_source
        
        # Fetch the quote
        price_entry = self.fetcher.fetch_quote(
            commodity=commodity_with_fallbacks, 
            quote_date=datetime.date(2025, 5, 8)
        )
        
        # Verify the price entry uses the fallback source
        self.assertIsInstance(price_entry, Price)
        self.assertEqual(price_entry.currency, "BTC")
        self.assertEqual(price_entry.amount, Decimal('50000.00'))
        self.assertEqual(price_entry.date, datetime.date(2025, 5, 8))
        self.assertEqual(price_entry.meta['source'], 'source2/BTC')

    def test_fetch_quote_no_source(self) -> None:
        """Test fetching a quote when no source is available."""
        # Get Bitcoin commodity (no price metadata)
        bitcoin = next(c for c in self.commodities if c.currency == "BTC")
        
        # Fetch the quote
        price_entry = self.fetcher.fetch_quote(
            commodity=bitcoin, 
            quote_date=datetime.date(2025, 5, 8)
        )
        
        # Verify no price entry is returned
        self.assertIsNone(price_entry)

    def test_fetch_quote_custom_only(self) -> None:
        """Test fetching quotes with custom_only flag."""
        # Get Apple commodity
        apple = next(c for c in self.commodities if c.currency == "AAPL")
        
        # Create a fetcher with custom_only=True
        custom_fetcher = quote_fetcher.QuoteFetcher(custom_only=True)
        
        # Create a mock source that returns a price tuple
        mock_source = mock.Mock()
        mock_source.get_latest_price.return_value = (
            Decimal('150.00'), 
            datetime.date(2025, 5, 8), 
            'USD'
        )
        
        # Create a mock for _get_source that returns the mock_source
        mock_get_source = mock.Mock(return_value=mock_source)
        custom_fetcher._get_source = mock_get_source
        
        # Fetch the quote
        custom_fetcher.fetch_quote(
            commodity=apple, 
            quote_date=datetime.date(2025, 5, 8)
        )
        
        # Check that the fetcher used custom_only=True when called
        mock_get_source.assert_called_with('mock_yahoo', True)


if __name__ == "__main__":
    unittest.main()