#!/usr/bin/env python3
"""Tests for the SourceDispatcher class."""

import datetime
import unittest
from decimal import Decimal
from unittest import mock

from beancount.core.data import Commodity, Price, Amount
from beanprice.source import Source as SourceBase, SourcePrice

from beansprout.quoter.sources.dispatching import SourceDispatcher, SourceSpec, get_source
from beansprout.quoter.sources import cache_manager


class MockSource(SourceBase):
    """Mock source for testing."""

    def __init__(self, response=None, raises=False):
        self.response = response
        self.raises = raises
        self.calls = []

    def get_latest_price(self, ticker):
        """Return a test price."""
        self.calls.append(('get_latest_price', ticker))
        if self.raises:
            raise Exception("Test exception")
        return self.response

    def get_historical_price(self, ticker, time):
        """Return a test historical price."""
        self.calls.append(('get_historical_price', ticker, time))
        if self.raises:
            raise Exception("Test exception")
        return self.response

    def get_prices_series(self, ticker, time_begin, time_end):
        """Return a test price series."""
        self.calls.append(('get_prices_series', ticker, time_begin, time_end))
        if self.raises:
            raise Exception("Test exception")
        return self.response


class TestSourceDispatcher(unittest.TestCase):
    """Tests for the SourceDispatcher class."""

    def setUp(self):
        """Set up test fixtures."""
        # Create mock cache manager
        self.mock_cache = mock.MagicMock(spec=cache_manager.CacheManager)
        self.mock_cache.get.return_value = None  # Default to cache miss

        # Create the dispatching source with the mock cache
        self.source = SourceDispatcher(cache_manager=self.mock_cache,
                                       custom_only=True)

        # Create some test commodities
        self.apple = Commodity(meta={
            'filename': 'test',
            'lineno': 1,
            'price': 'USD:yahoo/AAPL'
        },
                               date=datetime.date(2025, 5, 8),
                               currency='AAPL')

        self.bitcoin = Commodity(meta={
            'filename': 'test',
            'lineno': 2,
            'price': 'USD:coinbase/BTC,coinmarketcap/BTC'
        },
                                 date=datetime.date(2025, 5, 8),
                                 currency='BTC')

        self.cad = Commodity(meta={
            'filename': 'test',
            'lineno': 3,
            'price': 'USD:yahoo/^CADUSD=X'
        },
                             date=datetime.date(2025, 5, 8),
                             currency='CAD')

        self.multi_currency = Commodity(meta={
            'filename':
            'test',
            'lineno':
            4,
            'price':
            'USD:yahoo/MSFT JPY:yahoo/MSFT.T'
        },
                                        date=datetime.date(2025, 5, 8),
                                        currency='MSFT')

        self.no_price_meta = Commodity(meta={
            'filename': 'test',
            'lineno': 5
        },
                                       date=datetime.date(2025, 5, 8),
                                       currency='XYZ')

        # Current date for testing
        self.today = datetime.date.today()

    def test_get_source_specs(self):
        """Test parsing of price metadata into source specifications."""
        # Test normal case
        specs = self.source._get_source_specs(self.apple)
        self.assertIn('USD', specs)
        self.assertEqual(1, len(specs['USD']))
        self.assertEqual(SourceSpec('USD', 'yahoo', 'AAPL', False),
                         specs['USD'][0])

        # Test multiple sources for same currency
        specs = self.source._get_source_specs(self.bitcoin)
        self.assertIn('USD', specs)
        self.assertEqual(2, len(specs['USD']))
        self.assertEqual(SourceSpec('USD', 'coinbase', 'BTC', False),
                         specs['USD'][0])
        self.assertEqual(SourceSpec('USD', 'coinmarketcap', 'BTC', False),
                         specs['USD'][1])

        # Test inversion notation
        specs = self.source._get_source_specs(self.cad)
        self.assertIn('USD', specs)
        self.assertEqual(1, len(specs['USD']))
        self.assertEqual(SourceSpec('USD', 'yahoo', 'CADUSD=X', True),
                         specs['USD'][0])

        # Test multiple currencies
        specs = self.source._get_source_specs(self.multi_currency)
        self.assertIn('USD', specs)
        self.assertIn('JPY', specs)
        self.assertEqual(1, len(specs['USD']))
        self.assertEqual(1, len(specs['JPY']))
        self.assertEqual(SourceSpec('USD', 'yahoo', 'MSFT', False),
                         specs['USD'][0])
        self.assertEqual(SourceSpec('JPY', 'yahoo', 'MSFT.T', False),
                         specs['JPY'][0])

        # Test no price metadata
        specs = self.source._get_source_specs(self.no_price_meta)
        self.assertEqual({}, specs)

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_latest_price_cached(self, mock_get_source):
        """Test fetching a price that is already in the cache."""
        # Set up the mock cache to return a cached result
        cached_price = Price(meta={'source': 'cache'},
                             date=self.today,
                             currency='AAPL',
                             amount=Amount(number=Decimal('150.00'),
                                           currency='USD'))
        self.mock_cache.get.return_value = cached_price

        # Call the method
        prices = list(self.source.get_latest_price(self.apple))

        # Verify that get_source was not called
        mock_get_source.assert_not_called()

        # Verify we got the cached result
        self.assertEqual(1, len(prices))
        self.assertEqual(cached_price, prices[0])

        # Verify cache was checked with correct parameters
        self.mock_cache.get.assert_called_once_with('USD', 'AAPL', self.today)
        self.mock_cache.put.assert_not_called()

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_latest_price_source_success(self, mock_get_source):
        """Test fetching a price from a source (not cached)."""
        # Set up the mock source to return a price
        mock_source = MockSource(
            response=SourcePrice(price=Decimal('160.00'),
                                 time=datetime.datetime.now(),
                                 quote_currency='USD'))
        mock_get_source.return_value = mock_source

        # Call the method
        prices = list(self.source.get_latest_price(self.apple))

        # Verify that get_source was called with the right parameter
        mock_get_source.assert_called_once_with(source_name='yahoo',
                                                custom_only=True)

        # Verify we got a price
        self.assertEqual(1, len(prices))
        price = prices[0]
        self.assertEqual('AAPL', price.currency)
        self.assertEqual('USD', price.amount.currency)
        self.assertEqual(Decimal('160.00'), price.amount.number)
        self.assertEqual(self.today, price.date)
        self.assertEqual('yahoo', price.meta['source'])

        # Verify cache was checked and updated
        self.mock_cache.get.assert_called_once_with('USD', 'AAPL', self.today)
        self.mock_cache.put.assert_called_once()
        self.assertEqual('USD', self.mock_cache.put.call_args[0][0])
        self.assertEqual('AAPL', self.mock_cache.put.call_args[0][1])
        self.assertEqual(self.today, self.mock_cache.put.call_args[0][2])
        self.assertEqual(price, self.mock_cache.put.call_args[0][3])

    @mock.patch(
        'beansprout.quoter.sources.dispatching.SourceDispatcher._try_sources')
    def test_get_latest_price_inversion(self, mock_try_sources):
        """Test price inversion when the invert flag is True."""
        # Mock the _try_sources method directly with a response that indicates source_spec.invert = True
        mock_try_sources.return_value = (SourceSpec(quote_currency='USD',
                                                    source='yahoo',
                                                    ticker='CADUSD=X',
                                                    invert=True),
                                         SourcePrice(
                                             price=Decimal('1.25'),
                                             time=datetime.datetime.now(),
                                             quote_currency='USD'))

        # Call the method with a commodity that has inversion notation
        prices = list(self.source.get_latest_price(self.cad))

        # Verify we got one price
        self.assertEqual(1, len(prices))
        price = prices[0]

        self.assertEqual('USD', price.currency)
        self.assertEqual('CAD', price.amount.currency)

        # The price should be inverted (1/1.25 = 0.8)
        expected = Decimal('1') / Decimal('1.25')
        self.assertAlmostEqual(float(expected),
                               float(price.amount.number),
                               places=6)

        self.assertEqual(self.today, price.date)
        self.assertEqual('yahoo', price.meta['source'])

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_latest_price_source_fallback(self, mock_get_source):
        """Test falling back to the second source when the first fails."""
        # Set up mock sources - first fails, second succeeds
        failing_source = MockSource(response=None)
        successful_source = MockSource(
            response=SourcePrice(price=Decimal('50000.00'),
                                 time=datetime.datetime.now(),
                                 quote_currency='USD'))

        # Configure get_source to return different sources based on name
        def side_effect(source_name, custom_only):
            if source_name == 'coinbase':
                return failing_source
            elif source_name == 'coinmarketcap':
                return successful_source
            return None

        mock_get_source.side_effect = side_effect

        # Call the method with a commodity that has multiple sources
        prices = list(self.source.get_latest_price(self.bitcoin))

        # Verify both sources were tried
        self.assertEqual(2, mock_get_source.call_count)
        mock_get_source.assert_any_call(source_name='coinbase',
                                        custom_only=True)
        mock_get_source.assert_any_call(source_name='coinmarketcap',
                                        custom_only=True)

        # Verify we got a price from the second source
        self.assertEqual(1, len(prices))
        price = prices[0]
        self.assertEqual('BTC', price.currency)
        self.assertEqual('USD', price.amount.currency)
        self.assertEqual(Decimal('50000.00'), price.amount.number)
        self.assertEqual('coinmarketcap', price.meta['source'])

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_latest_price_all_sources_fail(self, mock_get_source):
        """Test behavior when all sources fail to return a price."""
        # Set up mock source to return None
        mock_source = MockSource(response=None)
        mock_get_source.return_value = mock_source

        # Call the method
        prices = list(self.source.get_latest_price(self.apple))

        # Verify that get_source was called
        mock_get_source.assert_called_once_with(source_name='yahoo',
                                                custom_only=True)

        # Verify we got no prices
        self.assertEqual(0, len(prices))

        # Verify cache was checked but not updated
        self.mock_cache.get.assert_called_once()
        self.mock_cache.put.assert_not_called()

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_latest_price_source_exception(self, mock_get_source):
        """Test handling of exceptions from sources."""
        # Set up mock source to raise an exception
        mock_source = MockSource(raises=True)
        mock_get_source.return_value = mock_source

        # Call the method - should not raise an exception
        prices = list(self.source.get_latest_price(self.apple))

        # Verify that get_source was called
        mock_get_source.assert_called_once()

        # Verify we got no prices
        self.assertEqual(0, len(prices))

        # Verify cache was checked but not updated
        self.mock_cache.get.assert_called_once()
        self.mock_cache.put.assert_not_called()

    def test_get_latest_price_no_price_metadata(self):
        """Test fetching a price for a commodity with no price metadata."""
        # Call the method with a commodity that has no price metadata
        prices = list(self.source.get_latest_price(self.no_price_meta))

        # Verify we got no prices
        self.assertEqual(0, len(prices))

        # Verify cache was not checked or updated
        self.mock_cache.get.assert_not_called()
        self.mock_cache.put.assert_not_called()

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_latest_price_multiple_currencies(self, mock_get_source):
        """Test fetching prices in multiple currencies for a single commodity."""

        # Set up the mock source to return different prices for different currencies
        def side_effect(ticker):
            if ticker == 'MSFT':
                return SourcePrice(price=Decimal('300.00'),
                                   time=datetime.datetime.now(),
                                   quote_currency='USD')
            elif ticker == 'MSFT.T':
                return SourcePrice(price=Decimal('45000.00'),
                                   time=datetime.datetime.now(),
                                   quote_currency='JPY')
            return None

        mock_source = MockSource()
        mock_source.get_latest_price = side_effect
        mock_get_source.return_value = mock_source

        # Call the method with a commodity that has multiple currencies
        prices = list(self.source.get_latest_price(self.multi_currency))

        # Verify that get_source was called for each currency
        self.assertEqual(
            1, mock_get_source.call_count)  # Same source for both currencies

        # Verify we got prices for both currencies
        self.assertEqual(2, len(prices))

        # Sort prices by currency for consistent testing
        prices.sort(key=lambda p: p.amount.currency)

        # Check USD price
        usd_price = prices[1]
        self.assertEqual('MSFT', usd_price.currency)
        self.assertEqual('USD', usd_price.amount.currency)
        self.assertEqual(Decimal('300.00'), usd_price.amount.number)

        # Check JPY price
        jpy_price = prices[0]
        self.assertEqual('MSFT', jpy_price.currency)
        self.assertEqual('JPY', jpy_price.amount.currency)
        self.assertEqual(Decimal('45000.00'), jpy_price.amount.number)

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_historical_price_cached(self, mock_get_source):
        """Test fetching a historical price that is already in the cache."""
        # Set up test date
        historical_date = datetime.date(2025, 1, 1)
        historical_datetime = datetime.datetime(2025, 1, 1, 12, 0, 0)

        # Set up the mock cache to return a cached result
        cached_price = Price(meta={'source': 'cache'},
                             date=historical_date,
                             currency='AAPL',
                             amount=Amount(number=Decimal('140.00'),
                                           currency='USD'))
        self.mock_cache.get.return_value = cached_price

        # Call the method
        prices = list(
            self.source.get_historical_price(self.apple, historical_datetime))

        # Verify that get_source was not called
        mock_get_source.assert_not_called()

        # Verify we got the cached result
        self.assertEqual(1, len(prices))
        self.assertEqual(cached_price, prices[0])

        # Verify cache was checked with correct parameters
        self.mock_cache.get.assert_called_once_with('USD', 'AAPL',
                                                    historical_date)
        self.mock_cache.put.assert_not_called()

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_historical_price_source_success(self, mock_get_source):
        """Test fetching a historical price from a source (not cached)."""
        # Set up test date
        historical_date = datetime.date(2025, 1, 1)
        historical_datetime = datetime.datetime(2025, 1, 1, 12, 0, 0)

        # Set up the mock source to return a price
        mock_source = MockSource(response=SourcePrice(price=Decimal('140.00'),
                                                      time=historical_datetime,
                                                      quote_currency='USD'))
        mock_get_source.return_value = mock_source

        # Call the method
        prices = list(
            self.source.get_historical_price(self.apple, historical_datetime))

        # Verify that get_source was called with the right parameter
        mock_get_source.assert_called_once_with(source_name='yahoo',
                                                custom_only=True)

        # Verify we got a price
        self.assertEqual(1, len(prices))
        price = prices[0]
        self.assertEqual('AAPL', price.currency)
        self.assertEqual('USD', price.amount.currency)
        self.assertEqual(Decimal('140.00'), price.amount.number)
        self.assertEqual(historical_date, price.date)
        self.assertEqual('yahoo', price.meta['source'])

        # Verify cache was checked and updated
        self.mock_cache.get.assert_called_once_with('USD', 'AAPL',
                                                    historical_date)
        self.mock_cache.put.assert_called_once()
        self.assertEqual('USD', self.mock_cache.put.call_args[0][0])
        self.assertEqual('AAPL', self.mock_cache.put.call_args[0][1])
        self.assertEqual(historical_date, self.mock_cache.put.call_args[0][2])
        self.assertEqual(price, self.mock_cache.put.call_args[0][3])

    @mock.patch(
        'beansprout.quoter.sources.dispatching.SourceDispatcher._try_sources')
    def test_get_historical_price_inversion(self, mock_try_sources):
        """Test price inversion when the invert flag is True for historical prices."""
        # Set up test date
        historical_date = datetime.date(2025, 1, 1)
        historical_datetime = datetime.datetime(2025, 1, 1, 12, 0, 0)

        # Mock the _try_sources method directly with a response that indicates source_spec.invert = True
        mock_try_sources.return_value = (SourceSpec(quote_currency='USD',
                                                    source='yahoo',
                                                    ticker='CADUSD=X',
                                                    invert=True),
                                         SourcePrice(price=Decimal('1.25'),
                                                     time=historical_datetime,
                                                     quote_currency='USD'))

        # Call the method with a commodity that has inversion notation
        prices = list(
            self.source.get_historical_price(self.cad, historical_datetime))

        # Verify we got one price
        self.assertEqual(1, len(prices))
        price = prices[0]

        self.assertEqual('USD', price.currency)
        self.assertEqual('CAD', price.amount.currency)

        # The price should be inverted (1/1.25 = 0.8)
        expected = Decimal('1') / Decimal('1.25')
        self.assertAlmostEqual(float(expected),
                               float(price.amount.number),
                               places=6)

        self.assertEqual(historical_date, price.date)
        self.assertEqual('yahoo', price.meta['source'])

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_historical_price_source_fallback(self, mock_get_source):
        """Test falling back to the second source when the first fails for historical prices."""
        # Set up test date
        historical_date = datetime.date(2025, 1, 1)
        historical_datetime = datetime.datetime(2025, 1, 1, 12, 0, 0)

        # Set up mock sources - first fails, second succeeds
        failing_source = MockSource(response=None)
        successful_source = MockSource(
            response=SourcePrice(price=Decimal('45000.00'),
                                 time=historical_datetime,
                                 quote_currency='USD'))

        # Configure get_source to return different sources based on name
        def side_effect(source_name, custom_only):
            if source_name == 'coinbase':
                return failing_source
            elif source_name == 'coinmarketcap':
                return successful_source
            return None

        mock_get_source.side_effect = side_effect

        # Call the method with a commodity that has multiple sources
        prices = list(
            self.source.get_historical_price(self.bitcoin,
                                             historical_datetime))

        # Verify both sources were tried
        self.assertEqual(2, mock_get_source.call_count)
        mock_get_source.assert_any_call(source_name='coinbase',
                                        custom_only=True)
        mock_get_source.assert_any_call(source_name='coinmarketcap',
                                        custom_only=True)

        # Verify we got a price from the second source
        self.assertEqual(1, len(prices))
        price = prices[0]
        self.assertEqual('BTC', price.currency)
        self.assertEqual('USD', price.amount.currency)
        self.assertEqual(Decimal('45000.00'), price.amount.number)
        self.assertEqual('coinmarketcap', price.meta['source'])

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_historical_price_multiple_currencies(self, mock_get_source):
        """Test fetching historical prices in multiple currencies for a single commodity."""
        # Set up test date
        historical_date = datetime.date(2025, 1, 1)
        historical_datetime = datetime.datetime(2025, 1, 1, 12, 0, 0)

        # Set up the mock source to return different prices for different currencies
        def side_effect(ticker, time):
            if ticker == 'MSFT':
                return SourcePrice(price=Decimal('280.00'),
                                   time=historical_datetime,
                                   quote_currency='USD')
            elif ticker == 'MSFT.T':
                return SourcePrice(price=Decimal('42000.00'),
                                   time=historical_datetime,
                                   quote_currency='JPY')
            return None

        mock_source = MockSource()
        mock_source.get_historical_price = side_effect
        mock_get_source.return_value = mock_source

        # Call the method with a commodity that has multiple currencies
        prices = list(
            self.source.get_historical_price(self.multi_currency,
                                             historical_datetime))

        # Verify that get_source was called for each currency
        self.assertEqual(
            1, mock_get_source.call_count)  # Same source for both currencies

        # Verify we got prices for both currencies
        self.assertEqual(2, len(prices))

        # Sort prices by currency for consistent testing
        prices.sort(key=lambda p: p.amount.currency)

        # Check USD price
        usd_price = prices[1]
        self.assertEqual('MSFT', usd_price.currency)
        self.assertEqual('USD', usd_price.amount.currency)
        self.assertEqual(Decimal('280.00'), usd_price.amount.number)

        # Check JPY price
        jpy_price = prices[0]
        self.assertEqual('MSFT', jpy_price.currency)
        self.assertEqual('JPY', jpy_price.amount.currency)
        self.assertEqual(Decimal('42000.00'), jpy_price.amount.number)

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_historical_price_all_sources_fail(self, mock_get_source):
        """Test behavior when all sources fail to return a historical price."""
        # Set up test date
        historical_date = datetime.date(2025, 1, 1)
        historical_datetime = datetime.datetime(2025, 1, 1, 12, 0, 0)

        # Set up mock source to return None
        mock_source = MockSource(response=None)
        mock_get_source.return_value = mock_source

        # Call the method
        prices = list(
            self.source.get_historical_price(self.apple, historical_datetime))

        # Verify that get_source was called
        mock_get_source.assert_called_once_with(source_name='yahoo',
                                                custom_only=True)

        # Verify we got no prices
        self.assertEqual(0, len(prices))

        # Verify cache was checked but not updated
        self.mock_cache.get.assert_called_once()
        self.mock_cache.put.assert_not_called()

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_historical_price_source_exception(self, mock_get_source):
        """Test handling of exceptions from sources when fetching historical prices."""
        # Set up test date
        historical_date = datetime.date(2025, 1, 1)
        historical_datetime = datetime.datetime(2025, 1, 1, 12, 0, 0)

        # Set up mock source to raise an exception
        mock_source = MockSource(raises=True)
        mock_get_source.return_value = mock_source

        # Call the method - should not raise an exception
        prices = list(
            self.source.get_historical_price(self.apple, historical_datetime))

        # Verify that get_source was called
        mock_get_source.assert_called_once()

        # Verify we got no prices
        self.assertEqual(0, len(prices))

        # Verify cache was checked but not updated
        self.mock_cache.get.assert_called_once()
        self.mock_cache.put.assert_not_called()

    def test_get_historical_price_no_price_metadata(self):
        """Test fetching a historical price for a commodity with no price metadata."""
        # Set up test date
        historical_date = datetime.date(2025, 1, 1)
        historical_datetime = datetime.datetime(2025, 1, 1, 12, 0, 0)

        # Call the method with a commodity that has no price metadata
        prices = list(
            self.source.get_historical_price(self.no_price_meta,
                                             historical_datetime))

        # Verify we got no prices
        self.assertEqual(0, len(prices))

        # Verify cache was not checked or updated
        self.mock_cache.get.assert_not_called()
        self.mock_cache.put.assert_not_called()

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_prices_series_success(self, mock_get_source):
        """Test fetching a price series successfully."""
        # Set up test dates
        start_date = datetime.datetime(2025, 1, 1, 12, 0, 0)
        end_date = datetime.datetime(2025, 1, 5, 12, 0, 0)

        # Create a series of prices for different dates
        price_series = [
            SourcePrice(price=Decimal('150.00'),
                        time=datetime.datetime(2025, 1, 1, 12, 0, 0),
                        quote_currency='USD'),
            SourcePrice(price=Decimal('152.50'),
                        time=datetime.datetime(2025, 1, 2, 12, 0, 0),
                        quote_currency='USD'),
            SourcePrice(price=Decimal('155.00'),
                        time=datetime.datetime(2025, 1, 3, 12, 0, 0),
                        quote_currency='USD'),
            SourcePrice(price=Decimal('153.75'),
                        time=datetime.datetime(2025, 1, 4, 12, 0, 0),
                        quote_currency='USD'),
            SourcePrice(price=Decimal('157.25'),
                        time=datetime.datetime(2025, 1, 5, 12, 0, 0),
                        quote_currency='USD'),
        ]

        # Set up the mock source to return the price series
        mock_source = MockSource(response=price_series)
        mock_get_source.return_value = mock_source

        # Call the method
        prices = self.source.get_prices_series(self.apple, start_date,
                                               end_date)

        # Verify that get_source was called with the right parameter
        mock_get_source.assert_called_once_with(source_name='yahoo',
                                                custom_only=True)

        # Verify we got all prices in the series
        self.assertEqual(5, len(prices))

        # Verify prices are sorted by date
        self.assertEqual(datetime.date(2025, 1, 1), prices[0].date)
        self.assertEqual(datetime.date(2025, 1, 5), prices[4].date)

        # Check a sample price
        sample_price = prices[2]  # Jan 3
        self.assertEqual('AAPL', sample_price.currency)
        self.assertEqual('USD', sample_price.amount.currency)
        self.assertEqual(Decimal('155.00'), sample_price.amount.number)
        self.assertEqual('yahoo', sample_price.meta['source'])

        # Verify cache was updated for each price
        self.assertEqual(5, self.mock_cache.put.call_count)

    @mock.patch(
        'beansprout.quoter.sources.dispatching.SourceDispatcher._try_sources')
    def test_get_prices_series_inversion(self, mock_try_sources):
        """Test price inversion in a series."""
        # Set up test dates
        start_date = datetime.datetime(2025, 1, 1, 12, 0, 0)
        end_date = datetime.datetime(2025, 1, 3, 12, 0, 0)

        # Create a series of prices that need to be inverted
        price_series = [
            SourcePrice(price=Decimal('1.25'),
                        time=datetime.datetime(2025, 1, 1, 12, 0, 0),
                        quote_currency='USD'),
            SourcePrice(price=Decimal('1.26'),
                        time=datetime.datetime(2025, 1, 2, 12, 0, 0),
                        quote_currency='USD'),
            SourcePrice(price=Decimal('1.27'),
                        time=datetime.datetime(2025, 1, 3, 12, 0, 0),
                        quote_currency='USD'),
        ]

        # Mock the _try_sources method directly with a response that indicates source_spec.invert = True
        mock_try_sources.return_value = (SourceSpec(quote_currency='USD',
                                                    source='yahoo',
                                                    ticker='CADUSD=X',
                                                    invert=True), price_series)

        # Call the method with a commodity that has inversion notation
        prices = self.source.get_prices_series(self.cad, start_date, end_date)

        # Verify we got all prices in the series
        self.assertEqual(3, len(prices))

        # Verify prices are sorted by date
        self.assertEqual(datetime.date(2025, 1, 1), prices[0].date)
        self.assertEqual(datetime.date(2025, 1, 3), prices[2].date)

        # Check that all prices are inverted
        for i, price in enumerate(prices):
            self.assertEqual('USD', price.currency)
            self.assertEqual('CAD', price.amount.currency)

            # The price should be inverted (1/original)
            original_price = price_series[i].price
            expected = Decimal('1') / original_price
            self.assertAlmostEqual(float(expected),
                                   float(price.amount.number),
                                   places=6)

            self.assertEqual('yahoo', price.meta['source'])

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_prices_series_source_fallback(self, mock_get_source):
        """Test falling back to the second source when the first fails for price series."""
        # Set up test dates
        start_date = datetime.datetime(2025, 1, 1, 12, 0, 0)
        end_date = datetime.datetime(2025, 1, 3, 12, 0, 0)

        # Create a series of prices
        price_series = [
            SourcePrice(price=Decimal('50000.00'),
                        time=datetime.datetime(2025, 1, 1, 12, 0, 0),
                        quote_currency='USD'),
            SourcePrice(price=Decimal('51000.00'),
                        time=datetime.datetime(2025, 1, 2, 12, 0, 0),
                        quote_currency='USD'),
            SourcePrice(price=Decimal('52000.00'),
                        time=datetime.datetime(2025, 1, 3, 12, 0, 0),
                        quote_currency='USD'),
        ]

        # Set up mock sources - first fails, second succeeds
        failing_source = MockSource(response=None)
        successful_source = MockSource(response=price_series)

        # Configure get_source to return different sources based on name
        def side_effect(source_name, custom_only):
            if source_name == 'coinbase':
                return failing_source
            elif source_name == 'coinmarketcap':
                return successful_source
            return None

        mock_get_source.side_effect = side_effect

        # Call the method with a commodity that has multiple sources
        prices = self.source.get_prices_series(self.bitcoin, start_date,
                                               end_date)

        # Verify both sources were tried
        self.assertEqual(2, mock_get_source.call_count)
        mock_get_source.assert_any_call(source_name='coinbase',
                                        custom_only=True)
        mock_get_source.assert_any_call(source_name='coinmarketcap',
                                        custom_only=True)

        # Verify we got prices from the second source
        self.assertEqual(3, len(prices))

        # Check a sample price
        sample_price = prices[1]  # Jan 2
        self.assertEqual('BTC', sample_price.currency)
        self.assertEqual('USD', sample_price.amount.currency)
        self.assertEqual(Decimal('51000.00'), sample_price.amount.number)
        self.assertEqual('coinmarketcap', sample_price.meta['source'])

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_prices_series_source_exception(self, mock_get_source):
        """Test handling of exceptions from sources when fetching price series."""
        # Set up test dates
        start_date = datetime.datetime(2025, 1, 1, 12, 0, 0)
        end_date = datetime.datetime(2025, 1, 3, 12, 0, 0)

        # Set up mock source to raise an exception
        mock_source = MockSource(raises=True)
        mock_get_source.return_value = mock_source

        # Call the method - should not raise an exception
        prices = self.source.get_prices_series(self.apple, start_date,
                                               end_date)

        # Verify that get_source was called
        mock_get_source.assert_called_once()

        # Verify we got no prices
        self.assertEqual(0, len(prices))

        # Verify cache was not updated
        self.mock_cache.put.assert_not_called()

    def test_get_prices_series_no_price_metadata(self):
        """Test fetching a price series for a commodity with no price metadata."""
        # Set up test dates
        start_date = datetime.datetime(2025, 1, 1, 12, 0, 0)
        end_date = datetime.datetime(2025, 1, 3, 12, 0, 0)

        # Call the method with a commodity that has no price metadata
        prices = self.source.get_prices_series(self.no_price_meta, start_date,
                                               end_date)

        # Verify we got no prices
        self.assertEqual(0, len(prices))

        # Verify cache was not checked or updated
        self.mock_cache.get.assert_not_called()
        self.mock_cache.put.assert_not_called()

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_prices_series_multiple_currencies(self, mock_get_source):
        """Test fetching price series in multiple currencies for a single commodity."""
        # Set up test dates
        start_date = datetime.datetime(2025, 1, 1, 12, 0, 0)
        end_date = datetime.datetime(2025, 1, 3, 12, 0, 0)

        # Create price series for USD
        usd_series = [
            SourcePrice(price=Decimal('300.00'),
                        time=datetime.datetime(2025, 1, 1, 12, 0, 0),
                        quote_currency='USD'),
            SourcePrice(price=Decimal('305.00'),
                        time=datetime.datetime(2025, 1, 2, 12, 0, 0),
                        quote_currency='USD'),
            SourcePrice(price=Decimal('310.00'),
                        time=datetime.datetime(2025, 1, 3, 12, 0, 0),
                        quote_currency='USD'),
        ]

        # Create price series for JPY
        jpy_series = [
            SourcePrice(price=Decimal('45000.00'),
                        time=datetime.datetime(2025, 1, 1, 12, 0, 0),
                        quote_currency='JPY'),
            SourcePrice(price=Decimal('45750.00'),
                        time=datetime.datetime(2025, 1, 2, 12, 0, 0),
                        quote_currency='JPY'),
            SourcePrice(price=Decimal('46500.00'),
                        time=datetime.datetime(2025, 1, 3, 12, 0, 0),
                        quote_currency='JPY'),
        ]

        # Set up the mock source to return different price series for different currencies
        def side_effect(ticker, time_begin, time_end):
            if ticker == 'MSFT':
                return usd_series
            elif ticker == 'MSFT.T':
                return jpy_series
            return None

        mock_source = MockSource()
        mock_source.get_prices_series = side_effect
        mock_get_source.return_value = mock_source

        # Call the method with a commodity that has multiple currencies
        prices = self.source.get_prices_series(self.multi_currency, start_date,
                                               end_date)

        # Verify that get_source was called
        self.assertEqual(
            1, mock_get_source.call_count)  # Same source for both currencies

        # Verify we got prices for both currencies (3 dates x 2 currencies = 6 prices)
        self.assertEqual(6, len(prices))

        # Verify prices are sorted by date
        self.assertEqual(datetime.date(2025, 1, 1), prices[0].date)
        self.assertEqual(datetime.date(2025, 1, 1), prices[1].date)
        self.assertEqual(datetime.date(2025, 1, 3), prices[4].date)
        self.assertEqual(datetime.date(2025, 1, 3), prices[5].date)

        # Count prices by currency
        usd_prices = [p for p in prices if p.amount.currency == 'USD']
        jpy_prices = [p for p in prices if p.amount.currency == 'JPY']

        self.assertEqual(3, len(usd_prices))
        self.assertEqual(3, len(jpy_prices))

        # Check sample prices
        usd_sample = usd_prices[1]  # Jan 2
        self.assertEqual('MSFT', usd_sample.currency)
        self.assertEqual('USD', usd_sample.amount.currency)
        self.assertEqual(Decimal('305.00'), usd_sample.amount.number)

        jpy_sample = jpy_prices[1]  # Jan 2
        self.assertEqual('MSFT', jpy_sample.currency)
        self.assertEqual('JPY', jpy_sample.amount.currency)
        self.assertEqual(Decimal('45750.00'), jpy_sample.amount.number)


if __name__ == '__main__':
    unittest.main()
