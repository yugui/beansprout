#!/usr/bin/env python3
"""Tests for the quote_fetcher module."""

import datetime
import os
import unittest
from unittest import mock

from beancount import loader
from beancount.core import data
from beancount.core.data import Commodity, Price, Amount
from beancount.core.number import Decimal

from beansprout.quoter import commodity_finder
from beansprout.quoter.quote_fetcher import QuoteFetcher
from beansprout.quoter.sources.dispatching import SourceDispatcher


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

        # Create a mock cache manager
        self.mock_cache_manager = mock.Mock()

        # Create a fetcher instance with the mock cache manager
        self.fetcher = QuoteFetcher(cache_mgr=self.mock_cache_manager)

        # Mock the SourceDispatcher instance
        self.mock_dispatch_source = mock.Mock()
        self.fetcher._dispatch_source = self.mock_dispatch_source

        # Setup common test data
        self.today = datetime.date.today()
        self.apple = next(c for c in self.commodities if c.currency == "AAPL")

        # Create sample price objects to return
        meta = {'source': 'test_source', 'time': self.today}
        latest_price = data.Price(meta=meta,
                                  date=self.today,
                                  currency="AAPL",
                                  amount=data.Amount(number=Decimal('150.00'),
                                                     currency='USD'))

        historical_date = datetime.date(2025, 5, 1)
        historical_meta = {'source': 'test_source', 'time': historical_date}
        historical_price = data.Price(meta=historical_meta,
                                      date=historical_date,
                                      currency="AAPL",
                                      amount=data.Amount(
                                          number=Decimal('145.00'),
                                          currency='USD'))

        # Set up default returns for the mock - now using batch methods
        self.mock_dispatch_source.fetch_latest_prices_batch.return_value = {
            'AAPL': latest_price
        }
        self.mock_dispatch_source.fetch_historical_prices_batch.return_value = {
            'AAPL': historical_price
        }

    def test_fetch_latest_quotes(self) -> None:
        """Test fetching the latest quotes for commodities using bulk method."""
        # Configure the mock to return a price object for latest price
        meta = {'source': 'mock_yahoo', 'time': self.today}
        latest_price = data.Price(meta=meta,
                                  date=self.today,
                                  currency="AAPL",
                                  amount=data.Amount(number=Decimal('150.00'),
                                                     currency='USD'))
        self.mock_dispatch_source.fetch_latest_prices_batch.return_value = {
            'AAPL': latest_price
        }

        # Fetch the latest quotes for a list of commodities
        price_entries = self.fetcher.fetch_latest_quotes(
            commodities=[self.apple])

        # Verify the mock was called - it should be called with spec-commodity pairs
        self.mock_dispatch_source.fetch_latest_prices_batch.assert_called_once(
        )
        call_args = self.mock_dispatch_source.fetch_latest_prices_batch.call_args
        spec_commodity_pairs = call_args[0][0]  # Get first positional argument

        # Verify the call parameters
        self.assertEqual(len(spec_commodity_pairs), 1)
        spec, commodity = spec_commodity_pairs[0]
        self.assertEqual(commodity, "AAPL")
        self.assertEqual(spec.source, "mock_yahoo")
        self.assertEqual(spec.ticker, "AAPL")
        self.assertEqual(spec.quote_currency, "USD")

        # Verify the price entries
        self.assertEqual(len(price_entries), 1)
        price_entry = price_entries[0]
        self.assertIsInstance(price_entry, Price)
        self.assertEqual(price_entry.currency, "AAPL")
        self.assertEqual(price_entry.amount.number, Decimal('150.00'))
        self.assertEqual(price_entry.amount.currency, 'USD')
        self.assertEqual(price_entry.date, self.today)
        # The source should match what's in the implementation
        self.assertEqual(price_entry.meta['source'], 'mock_yahoo')

    def test_fetch_historical_quotes(self) -> None:
        """Test fetching historical quotes for commodities using bulk method."""
        # Configure the mock to return a price object for historical price
        historical_date = datetime.date(2025, 5, 1)
        historical_meta = {'source': 'mock_yahoo', 'time': historical_date}
        historical_price = data.Price(meta=historical_meta,
                                      date=historical_date,
                                      currency="AAPL",
                                      amount=data.Amount(
                                          number=Decimal('145.00'),
                                          currency='USD'))
        self.mock_dispatch_source.fetch_historical_prices_batch.return_value = {
            'AAPL': historical_price
        }

        # Fetch the historical quotes for a list of commodities
        price_entries = self.fetcher.fetch_historical_quotes(
            commodities=[self.apple], quote_date=historical_date)

        # Verify the mock was called with the expected parameters
        self.mock_dispatch_source.fetch_historical_prices_batch.assert_called_once(
        )
        call_args = self.mock_dispatch_source.fetch_historical_prices_batch.call_args
        spec_commodity_pairs, dt = call_args[0]  # Get positional arguments

        # Verify the call parameters
        self.assertEqual(len(spec_commodity_pairs), 1)
        spec, commodity = spec_commodity_pairs[0]
        self.assertEqual(commodity, "AAPL")
        self.assertEqual(spec.source, "mock_yahoo")
        self.assertEqual(spec.ticker, "AAPL")
        self.assertEqual(
            dt, datetime.datetime.combine(historical_date, datetime.time()))

        # Verify the price entries
        self.assertEqual(len(price_entries), 1)
        price_entry = price_entries[0]
        self.assertIsInstance(price_entry, Price)
        self.assertEqual(price_entry.currency, "AAPL")
        self.assertEqual(price_entry.amount.number, Decimal('145.00'))
        self.assertEqual(price_entry.amount.currency, 'USD')
        self.assertEqual(price_entry.date, historical_date)
        # The source should match what's in the implementation
        self.assertEqual(price_entry.meta['source'], 'mock_yahoo')

    def test_fetch_quotes_no_price_metadata(self) -> None:
        """Test fetching quotes for commodities with no price metadata."""
        # Create a commodity with no price metadata
        no_price_metadata = data.Commodity(meta={
            'filename': 'test',
            'lineno': 1
        },
                                           date=datetime.date(2025, 5, 8),
                                           currency='XYZ')

        # Test latest quotes fetch
        latest_prices = self.fetcher.fetch_latest_quotes(
            commodities=[no_price_metadata])
        self.assertEqual(len(latest_prices), 0)

        # Test historical quotes fetch
        historical_prices = self.fetcher.fetch_historical_quotes(
            commodities=[no_price_metadata],
            quote_date=datetime.date(2025, 5, 8))
        self.assertEqual(len(historical_prices), 0)

        # Verify that dispatch methods were not called
        self.mock_dispatch_source.fetch_latest_prices_batch.assert_not_called()
        self.mock_dispatch_source.fetch_historical_prices_batch.assert_not_called(
        )

    def test_fetch_quotes_no_price_found(self) -> None:
        """Test handling when no price is found."""
        # Configure the mock to return empty dictionaries
        self.mock_dispatch_source.fetch_latest_prices_batch.return_value = {}
        self.mock_dispatch_source.fetch_historical_prices_batch.return_value = {}

        # Test latest quotes fetch
        latest_prices = self.fetcher.fetch_latest_quotes(
            commodities=[self.apple])
        self.assertEqual(len(latest_prices), 0)
        self.mock_dispatch_source.fetch_latest_prices_batch.assert_called_once(
        )

        # Test historical quotes fetch
        test_date = datetime.date(2025, 5, 8)
        historical_prices = self.fetcher.fetch_historical_quotes(
            commodities=[self.apple], quote_date=test_date)
        self.assertEqual(len(historical_prices), 0)
        self.mock_dispatch_source.fetch_historical_prices_batch.assert_called_once(
        )

    def test_fetch_quotes_exception_handling(self) -> None:
        """Test exception handling during price fetching."""
        # Configure the mock to raise exceptions
        self.mock_dispatch_source.fetch_latest_prices_batch.side_effect = Exception(
            "Test error")
        self.mock_dispatch_source.fetch_historical_prices_batch.side_effect = Exception(
            "Test error")

        # Test latest quotes fetch with exception
        latest_prices = self.fetcher.fetch_latest_quotes(
            commodities=[self.apple])
        self.assertEqual(len(latest_prices), 0)
        self.mock_dispatch_source.fetch_latest_prices_batch.assert_called_once(
        )

        # Test historical quotes fetch with exception
        test_date = datetime.date(2025, 5, 8)
        historical_prices = self.fetcher.fetch_historical_quotes(
            commodities=[self.apple], quote_date=test_date)
        self.assertEqual(len(historical_prices), 0)
        self.mock_dispatch_source.fetch_historical_prices_batch.assert_called_once(
        )


if __name__ == "__main__":
    unittest.main()
