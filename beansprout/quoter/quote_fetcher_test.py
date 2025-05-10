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

from beansprout.quoter import commodity_finder
from beansprout.quoter.quote_fetcher import QuoteFetcher


class TestQuoteFetcher(unittest.TestCase):
    """Test the QuoteFetcher class."""

    def setUp(self) -> None:
        """Set up test data with sample commodity definitions."""
        # Get the path to the testdata directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        test_file = os.path.join(current_dir, 'testdata',
                                 'test-commodities.beancount')

        # Load entries from the test file
        self.entries, self.errors, self.options_map = loader.load_file(
            filename=test_file)

        # Create a finder instance to get commodities
        self.finder = commodity_finder.CommodityFinder()
        self.commodities = self.finder.find_all_commodities(
            entries=self.entries)

        # Create a fetcher instance
        self.fetcher = QuoteFetcher(custom_only=False)

        # Mock the DispatchingSource instance
        self.mock_dispatch_source = mock.Mock()
        self.fetcher._dispatch_source = self.mock_dispatch_source

        # Setup common test data
        self.today = datetime.date.today()
        self.apple = next(c for c in self.commodities if c.currency == "AAPL")

        # Set up default returns for the mock
        self.mock_dispatch_source.get_latest_price.return_value = (
            Decimal('150.00'), self.today, 'USD')
        self.mock_dispatch_source.get_historical_price.return_value = (
            Decimal('145.00'), datetime.date(2025, 5, 1), 'USD')

    def test_fetch_latest_quote(self) -> None:
        """Test fetching the latest quote for a commodity."""
        # Configure the mock to return a price tuple for latest price
        price_tuple = (Decimal('150.00'), self.today, 'USD')
        self.mock_dispatch_source.get_latest_price.return_value = price_tuple

        # Fetch the quote
        price_entry = self.fetcher.fetch_quote(commodity=self.apple,
                                               quote_date=self.today)

        # Verify the mock was called with the expected parameters
        expected_ticker = f"{self.apple.currency}:{self.apple.meta['price']}"
        self.mock_dispatch_source.get_latest_price.assert_called_once_with(
            expected_ticker)

        # Verify the price entry
        self.assertIsInstance(price_entry, Price)
        self.assertEqual(price_entry.currency, "AAPL")
        self.assertEqual(price_entry.amount, Decimal('150.00'))
        self.assertEqual(price_entry.date, self.today)
        self.assertEqual(price_entry.meta['source'], 'dispatching')

    def test_fetch_historical_quote(self) -> None:
        """Test fetching a historical quote for a commodity."""
        # Configure the mock to return a price tuple for historical price
        historical_date = datetime.date(2025, 5, 1)
        price_tuple = (Decimal('145.00'), historical_date, 'USD')
        self.mock_dispatch_source.get_historical_price.return_value = price_tuple

        # Fetch the quote
        price_entry = self.fetcher.fetch_quote(commodity=self.apple,
                                               quote_date=historical_date)

        # Verify the mock was called with the expected parameters
        expected_ticker = f"{self.apple.currency}:{self.apple.meta['price']}"
        self.mock_dispatch_source.get_historical_price.assert_called_once_with(
            expected_ticker, historical_date)

        # Verify the price entry
        self.assertIsInstance(price_entry, Price)
        self.assertEqual(price_entry.currency, "AAPL")
        self.assertEqual(price_entry.amount, Decimal('145.00'))
        self.assertEqual(price_entry.date, historical_date)
        self.assertEqual(price_entry.meta['source'], 'dispatching')

    def test_fetch_quote_no_price_metadata(self) -> None:
        """Test fetching a quote for a commodity with no price metadata."""
        # Create a commodity with no price metadata
        no_price_metadata = data.Commodity(meta={
            'filename': 'test',
            'lineno': 1
        },
                                           date=datetime.date(2025, 5, 8),
                                           currency='XYZ')

        # Fetch the quote
        price_entry = self.fetcher.fetch_quote(commodity=no_price_metadata,
                                               quote_date=datetime.date(
                                                   2025, 5, 8))

        # Verify no price entry is returned
        self.assertIsNone(price_entry)
        # Verify that get_latest_price was not called
        self.mock_dispatch_source.get_latest_price.assert_not_called()

    def test_fetch_quote_no_price_found(self) -> None:
        """Test handling when no price is found."""
        # Configure the mock to return None for latest price
        self.mock_dispatch_source.get_latest_price.return_value = None

        # Fetch the quote
        price_entry = self.fetcher.fetch_quote(commodity=self.apple,
                                               quote_date=self.today)

        # Verify the mock was called
        expected_ticker = f"{self.apple.currency}:{self.apple.meta['price']}"
        self.mock_dispatch_source.get_latest_price.assert_called_once_with(
            expected_ticker)

        # Verify no price entry is returned
        self.assertIsNone(price_entry)

    def test_fetch_quote_exception_handling(self) -> None:
        """Test exception handling during price fetching."""
        # Configure the mock to raise an exception
        self.mock_dispatch_source.get_latest_price.side_effect = Exception(
            "Test error")

        # Fetch the quote - should not raise an exception
        price_entry = self.fetcher.fetch_quote(commodity=self.apple,
                                               quote_date=self.today)

        # Verify the mock was called
        expected_ticker = f"{self.apple.currency}:{self.apple.meta['price']}"
        self.mock_dispatch_source.get_latest_price.assert_called_once_with(
            expected_ticker)

        # Verify no price entry is returned
        self.assertIsNone(price_entry)

    def test_fetch_quote_custom_only(self) -> None:
        """Test fetching quotes with custom_only flag."""
        # Create a fetcher with custom_only=True
        custom_fetcher = QuoteFetcher(custom_only=True)

        # Check that the DispatchingSource was created with custom_only=True
        self.assertTrue(custom_fetcher.custom_only)
        self.assertTrue(custom_fetcher._dispatch_source.custom_only)


if __name__ == "__main__":
    unittest.main()
