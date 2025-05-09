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
from quoters.quote_fetcher import QuoteFetcher, PriceSource


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

        # Set up the basic mock for source that returns latest and historical prices
        self.mock_source = mock.Mock()
        self.mock_source.get_latest_price.return_value = (Decimal('150.00'),
                                                          datetime.date(
                                                              2025, 5,
                                                              8), 'USD')
        self.mock_source.get_historical_price.return_value = (
            Decimal('145.00'), datetime.date(2025, 5, 1), 'USD')

        # Replace the fetcher's _get_source method to return our mock
        self.original_get_source = self.fetcher._get_source
        self.fetcher._get_source = mock.Mock(return_value=self.mock_source)

    def tearDown(self) -> None:
        """Tear down test fixtures."""
        # Restore original _get_source method
        if hasattr(self, 'original_get_source'):
            self.fetcher._get_source = self.original_get_source

    def test_get_price_sources(self) -> None:
        """Test extracting price sources from commodity metadata."""
        # Find the Apple commodity
        apple = next(c for c in self.commodities if c.currency == "AAPL")

        # Get its price sources
        price_sources = self.fetcher._get_price_sources(commodity=apple)

        # Check that we got the expected sources
        self.assertEqual(len(price_sources), 1)
        self.assertEqual(price_sources[0].currency, "USD")
        self.assertEqual(price_sources[0].source, "mock_yahoo")
        self.assertEqual(price_sources[0].ticker, "AAPL")

        # Test with a commodity that has multiple price sources
        multi_source_commodity = data.Commodity(meta={
            'filename':
            'test',
            'lineno':
            1,
            'price':
            'USD:source1/TSLA JPY:source2/TSLA.T EUR:source3/TSLA.EU'
        },
                                                date=datetime.date(2025, 5, 8),
                                                currency='TSLA')

        price_sources = self.fetcher._get_price_sources(
            commodity=multi_source_commodity)
        self.assertEqual(len(price_sources), 3)

        self.assertEqual(price_sources[0].currency, "USD")
        self.assertEqual(price_sources[0].source, "source1")
        self.assertEqual(price_sources[0].ticker, "TSLA")

        self.assertEqual(price_sources[1].currency, "JPY")
        self.assertEqual(price_sources[1].source, "source2")
        self.assertEqual(price_sources[1].ticker, "TSLA.T")

        self.assertEqual(price_sources[2].currency, "EUR")
        self.assertEqual(price_sources[2].source, "source3")
        self.assertEqual(price_sources[2].ticker, "TSLA.EU")

        # Test with fallback sources
        fallback_commodity = data.Commodity(meta={
            'filename':
            'test',
            'lineno':
            1,
            'price':
            'USD:source1/BTC,source2/BTC'
        },
                                            date=datetime.date(2025, 5, 8),
                                            currency='BTC')

        price_sources = self.fetcher._get_price_sources(
            commodity=fallback_commodity)
        self.assertEqual(len(price_sources), 2)

        self.assertEqual(price_sources[0].currency, "USD")
        self.assertEqual(price_sources[0].source, "source1")
        self.assertEqual(price_sources[0].ticker, "BTC")

        self.assertEqual(price_sources[1].currency, "USD")
        self.assertEqual(price_sources[1].source, "source2")
        self.assertEqual(price_sources[1].ticker, "BTC")

        # Test with a commodity that has no price metadata
        no_price_commodity = data.Commodity(meta={
            'filename': 'test',
            'lineno': 1
        },
                                            date=datetime.date(2025, 5, 8),
                                            currency='BTC')

        price_sources = self.fetcher._get_price_sources(
            commodity=no_price_commodity)
        self.assertEqual(price_sources, [])

    def test_fetch_latest_quote(self) -> None:
        """Test fetching the latest quote for a commodity."""
        # Get Apple commodity
        apple = next(c for c in self.commodities if c.currency == "AAPL")

        # Directly patch the _fetch_quote_for_source method to return a known Price object
        original_method = self.fetcher._fetch_quote_for_source

        # Create a Price object that we'll have our patched method return
        price = data.Price(meta={'source': 'mock_yahoo/AAPL'},
                           date=datetime.date(2025, 5, 8),
                           currency='AAPL',
                           amount=Decimal('150.00'))

        try:
            # Replace the method with a mock that returns our Price object
            self.fetcher._fetch_quote_for_source = mock.Mock(
                return_value=price)

            # Fetch the quote
            price_entry = self.fetcher.fetch_quote(commodity=apple,
                                                   quote_date=datetime.date(
                                                       2025, 5, 8))

            # Verify the price entry
            self.assertIsInstance(price_entry, Price)
            self.assertEqual(price_entry.currency, "AAPL")
            self.assertEqual(price_entry.amount, Decimal('150.00'))
            self.assertEqual(price_entry.date, datetime.date(2025, 5, 8))
            self.assertEqual(price_entry.meta['source'], 'mock_yahoo/AAPL')
        finally:
            # Restore original method
            self.fetcher._fetch_quote_for_source = original_method

    def test_fetch_historical_quote(self) -> None:
        """Test fetching a historical quote for a commodity."""
        # Get Apple commodity
        apple = next(c for c in self.commodities if c.currency == "AAPL")

        # Directly patch the _fetch_quote_for_source method
        original_method = self.fetcher._fetch_quote_for_source

        # Create a Price object that we'll have our patched method return
        price = data.Price(meta={'source': 'mock_yahoo/AAPL'},
                           date=datetime.date(2025, 5, 1),
                           currency='AAPL',
                           amount=Decimal('145.00'))

        try:
            # Replace the method with a mock that returns our Price object
            self.fetcher._fetch_quote_for_source = mock.Mock(
                return_value=price)

            # Fetch the quote
            price_entry = self.fetcher.fetch_quote(commodity=apple,
                                                   quote_date=datetime.date(
                                                       2025, 5, 1))

            # Verify the price entry
            self.assertIsInstance(price_entry, Price)
            self.assertEqual(price_entry.currency, "AAPL")
            self.assertEqual(price_entry.amount, Decimal('145.00'))
            self.assertEqual(price_entry.date, datetime.date(2025, 5, 1))
            self.assertEqual(price_entry.meta['source'], 'mock_yahoo/AAPL')
        finally:
            # Restore original method
            self.fetcher._fetch_quote_for_source = original_method

    def test_fetch_quote_multiple_currencies(self) -> None:
        """Test fetching quotes with multiple currency options."""
        # Create a commodity with multiple currency options
        multi_currency = data.Commodity(meta={
            'filename':
            'test',
            'lineno':
            1,
            'price':
            'USD:source1/TSLA JPY:source2/TSLA.T EUR:source3/TSLA.EU'
        },
                                        date=datetime.date(2025, 5, 8),
                                        currency='TSLA')

        # Directly patch the _fetch_quote_for_source method
        original_method = self.fetcher._fetch_quote_for_source

        try:
            # Set up a side effect function that returns different values based on the source
            def side_effect(commodity, quote_date, price_source):
                if price_source.source == 'source1':
                    return data.Price(meta={'source': 'source1/TSLA'},
                                      date=datetime.date(2025, 5, 8),
                                      currency='TSLA',
                                      amount=Decimal('800.00'))
                elif price_source.source == 'source2':
                    return data.Price(meta={'source': 'source2/TSLA.T'},
                                      date=datetime.date(2025, 5, 8),
                                      currency='TSLA',
                                      amount=Decimal('120000.00'))
                else:
                    return None

            self.fetcher._fetch_quote_for_source = mock.Mock(
                side_effect=side_effect)

            # Test getting the first currency (USD)
            price_entry = self.fetcher.fetch_quote(commodity=multi_currency,
                                                   quote_date=datetime.date(
                                                       2025, 5, 8))

            # Verify first price entry (USD)
            self.assertIsInstance(price_entry, Price)
            self.assertEqual(price_entry.currency, "TSLA")
            self.assertEqual(price_entry.amount, Decimal('800.00'))
            self.assertEqual(price_entry.meta['source'], 'source1/TSLA')

            # Now modify the side effect to simulate USD source failing
            def fallback_side_effect(commodity, quote_date, price_source):
                if price_source.source == 'source1':
                    return None
                elif price_source.source == 'source2':
                    return data.Price(meta={'source': 'source2/TSLA.T'},
                                      date=datetime.date(2025, 5, 8),
                                      currency='TSLA',
                                      amount=Decimal('120000.00'))
                else:
                    return None

            self.fetcher._fetch_quote_for_source = mock.Mock(
                side_effect=fallback_side_effect)

            # Test with USD source failing, should fall back to JPY
            price_entry = self.fetcher.fetch_quote(commodity=multi_currency,
                                                   quote_date=datetime.date(
                                                       2025, 5, 8))

            # Verify fallback to JPY
            self.assertIsInstance(price_entry, Price)
            self.assertEqual(price_entry.currency, "TSLA")
            self.assertEqual(price_entry.amount, Decimal('120000.00'))
            self.assertEqual(price_entry.meta['source'], 'source2/TSLA.T')
        finally:
            # Restore original method
            self.fetcher._fetch_quote_for_source = original_method

    def test_fetch_quote_with_fallback(self) -> None:
        """Test fetching quotes with fallback sources."""
        # Create a commodity with multiple sources
        commodity_with_fallbacks = data.Commodity(meta={
            'filename':
            'test',
            'lineno':
            1,
            'price':
            'USD:source1/BTC,source2/BTC'
        },
                                                  date=datetime.date(
                                                      2025, 5, 8),
                                                  currency='BTC')

        # Directly patch the _fetch_quote_for_source method
        original_method = self.fetcher._fetch_quote_for_source

        try:
            # Set up a side effect function that returns None for first source, Price for second
            def side_effect(commodity, quote_date, price_source):
                if price_source.source == 'source1':
                    return None
                elif price_source.source == 'source2':
                    return data.Price(meta={'source': 'source2/BTC'},
                                      date=datetime.date(2025, 5, 8),
                                      currency='BTC',
                                      amount=Decimal('50000.00'))
                else:
                    return None

            self.fetcher._fetch_quote_for_source = mock.Mock(
                side_effect=side_effect)

            # Fetch the quote
            price_entry = self.fetcher.fetch_quote(
                commodity=commodity_with_fallbacks,
                quote_date=datetime.date(2025, 5, 8))

            # Verify fallback to second source
            self.assertIsInstance(price_entry, Price)
            self.assertEqual(price_entry.currency, "BTC")
            self.assertEqual(price_entry.amount, Decimal('50000.00'))
            self.assertEqual(price_entry.meta['source'], 'source2/BTC')
        finally:
            # Restore original method
            self.fetcher._fetch_quote_for_source = original_method

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

    def test_fetch_quote_invalid_price_format(self) -> None:
        """Test fetching a quote with invalid price metadata format."""
        # Create a commodity with invalid price metadata format
        invalid_price_format = data.Commodity(meta={
            'filename':
            'test',
            'lineno':
            1,
            'price':
            'invalid-format no-colon-separator'
        },
                                              date=datetime.date(2025, 5, 8),
                                              currency='BAD')

        # Fetch the quote
        price_entry = self.fetcher.fetch_quote(commodity=invalid_price_format,
                                               quote_date=datetime.date(
                                                   2025, 5, 8))

        # Verify no price entry is returned since no valid price sources were found
        self.assertIsNone(price_entry)

    def test_fetch_quote_no_source(self) -> None:
        """Test fetching a quote when no source is available."""
        # Get Bitcoin commodity (no price metadata)
        bitcoin = next(c for c in self.commodities if c.currency == "BTC")

        # Fetch the quote
        price_entry = self.fetcher.fetch_quote(commodity=bitcoin,
                                               quote_date=datetime.date(
                                                   2025, 5, 8))

        # Verify no price entry is returned
        self.assertIsNone(price_entry)

    def test_fetch_quote_custom_only(self) -> None:
        """Test fetching quotes with custom_only flag."""
        # Get Apple commodity
        apple = next(c for c in self.commodities if c.currency == "AAPL")

        # Create a fetcher with custom_only=True
        custom_fetcher = QuoteFetcher(custom_only=True)

        # Create a mock source that returns a price tuple
        mock_source = mock.Mock()
        mock_source.get_latest_price.return_value = (Decimal('150.00'),
                                                     datetime.date(2025, 5,
                                                                   8), 'USD')

        # Create a mock for _get_source that returns the mock_source
        mock_get_source = mock.Mock(return_value=mock_source)
        custom_fetcher._get_source = mock_get_source

        # Fetch the quote
        custom_fetcher.fetch_quote(commodity=apple,
                                   quote_date=datetime.date(2025, 5, 8))

        # Check that the fetcher used custom_only=True when called
        mock_get_source.assert_called_with('mock_yahoo', True)


if __name__ == "__main__":
    unittest.main()
