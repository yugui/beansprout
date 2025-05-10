#!/usr/bin/env python3
"""Unit tests for the DispatchingSource class."""

import unittest
import datetime
from decimal import Decimal
from unittest import mock
from typing import Optional, Tuple, List, Iterable

from beancount.core.data import Commodity

from beansprout.quoter.sources.dispatching import DispatchingSource, Source, PriceSource


class MockSource:
    """Mock source for testing the DispatchingSource."""

    def __init__(self,
                 test_case,
                 latest_result=None,
                 historical_result=None,
                 series_result=None):
        self.test_case = test_case
        self.latest_result = latest_result
        self.historical_result = historical_result
        self.series_result = series_result
        self.get_latest_called = False
        self.get_historical_called = False
        self.get_series_called = False

    def get_latest_price(
            self, ticker: str) -> Optional[Tuple[Decimal, datetime.date, str]]:
        self.get_latest_called = True
        self.test_case.latest_ticker = ticker
        return self.latest_result

    def get_historical_price(
            self, ticker: str, time: datetime.date
    ) -> Optional[Tuple[Decimal, datetime.date, str]]:
        self.get_historical_called = True
        self.test_case.historical_ticker = ticker
        self.test_case.historical_time = time
        return self.historical_result

    def get_prices_series(
        self, ticker: str, time_begin: datetime.date, time_end: datetime.date
    ) -> Optional[Iterable[Tuple[datetime.date, Decimal, str]]]:
        self.get_series_called = True
        self.test_case.series_ticker = ticker
        self.test_case.series_time_begin = time_begin
        self.test_case.series_time_end = time_end
        return self.series_result


class TestDispatchingSource(unittest.TestCase):
    """Test the DispatchingSource class."""

    def setUp(self):
        """Set up the test case."""
        self.source = DispatchingSource()
        self.today = datetime.date.today()
        self.yesterday = self.today - datetime.timedelta(days=1)
        self.latest_ticker = None
        self.historical_ticker = None
        self.historical_time = None
        self.series_ticker = None
        self.series_time_begin = None
        self.series_time_end = None

    def test_get_price_sources(self):
        """Test extracting price sources from commodity metadata."""
        # Test with a simple price source
        simple_commodity = Commodity(meta={'price': 'USD:yahoo/AAPL'},
                                     date=self.today,
                                     currency='AAPL')
        price_sources = self.source._get_price_sources(simple_commodity)
        self.assertEqual(len(price_sources), 1)
        self.assertEqual(price_sources[0].currency, "USD")
        self.assertEqual(price_sources[0].source, "yahoo")
        self.assertEqual(price_sources[0].ticker, "AAPL")

        # Test with multiple price sources
        multi_commodity = Commodity(
            meta={'price': 'USD:yahoo/AAPL CAD:yahoo/AAPL.TO'},
            date=self.today,
            currency='AAPL')
        price_sources = self.source._get_price_sources(multi_commodity)
        self.assertEqual(len(price_sources), 2)
        self.assertEqual(price_sources[0].currency, "USD")
        self.assertEqual(price_sources[0].source, "yahoo")
        self.assertEqual(price_sources[0].ticker, "AAPL")
        self.assertEqual(price_sources[1].currency, "CAD")
        self.assertEqual(price_sources[1].source, "yahoo")
        self.assertEqual(price_sources[1].ticker, "AAPL.TO")

        # Test with fallback sources
        fallback_commodity = Commodity(
            meta={'price': 'USD:source1/BTC,source2/BTC'},
            date=self.today,
            currency='BTC')
        price_sources = self.source._get_price_sources(fallback_commodity)
        self.assertEqual(len(price_sources), 2)
        self.assertEqual(price_sources[0].currency, "USD")
        self.assertEqual(price_sources[0].source, "source1")
        self.assertEqual(price_sources[0].ticker, "BTC")
        self.assertEqual(price_sources[1].currency, "USD")
        self.assertEqual(price_sources[1].source, "source2")
        self.assertEqual(price_sources[1].ticker, "BTC")

    def test_get_price_sources_with_inversion(self):
        """Test extracting price sources with inversion notation from commodity metadata."""
        # Test with inversion notation
        inversion_commodity = Commodity(meta={'price': 'USD:yahoo/^CADUSD=X'},
                                        date=self.today,
                                        currency='CAD')
        price_sources = self.source._get_price_sources(inversion_commodity)
        self.assertEqual(len(price_sources), 1)
        self.assertEqual(price_sources[0].currency, "USD")
        self.assertEqual(price_sources[0].source, "yahoo")
        self.assertEqual(price_sources[0].ticker, "CADUSD=X")
        self.assertTrue(price_sources[0].invert)

        # Test with non-inversion ticker
        normal_commodity = Commodity(meta={'price': 'USD:yahoo/AAPL'},
                                     date=self.today,
                                     currency='AAPL')
        price_sources = self.source._get_price_sources(normal_commodity)
        self.assertEqual(len(price_sources), 1)
        self.assertEqual(price_sources[0].currency, "USD")
        self.assertEqual(price_sources[0].source, "yahoo")
        self.assertEqual(price_sources[0].ticker, "AAPL")
        self.assertFalse(price_sources[0].invert)

        # Test with mixed inversion and non-inversion
        mixed_commodity = Commodity(
            meta={'price': 'USD:yahoo/^CADUSD=X CAD:yahoo/AAPL.TO'},
            date=self.today,
            currency='CAD')
        price_sources = self.source._get_price_sources(mixed_commodity)
        self.assertEqual(len(price_sources), 2)
        self.assertEqual(price_sources[0].currency, "USD")
        self.assertEqual(price_sources[0].source, "yahoo")
        self.assertEqual(price_sources[0].ticker, "CADUSD=X")
        self.assertTrue(price_sources[0].invert)
        self.assertEqual(price_sources[1].currency, "CAD")
        self.assertEqual(price_sources[1].source, "yahoo")
        self.assertEqual(price_sources[1].ticker, "AAPL.TO")
        self.assertFalse(price_sources[1].invert)

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_latest_price(self, mock_get_source):
        """Test getting the latest price."""
        # Set up the mock source
        mock_source = MockSource(self,
                                 latest_result=(Decimal('150.00'), self.today,
                                                'USD'))
        mock_get_source.return_value = mock_source

        # Test getting the latest price
        result = self.source.get_latest_price('AAPL:USD:yahoo/AAPL')

        # Verify results
        self.assertEqual(result, (Decimal('150.00'), self.today, 'USD'))
        self.assertEqual(self.latest_ticker, 'AAPL')
        self.assertTrue(mock_source.get_latest_called)
        mock_get_source.assert_called_once_with(source_name='yahoo',
                                                custom_only=False)

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_latest_price_with_fallbacks(self, mock_get_source):
        """Test getting the latest price with fallback sources."""
        # First source returns None
        first_mock_source = MockSource(self, latest_result=None)
        # Second source returns a price
        second_mock_source = MockSource(self,
                                        latest_result=(Decimal('45000.00'),
                                                       self.today, 'USD'))

        # Configure mock_get_source to return different values based on input
        def side_effect(source_name, custom_only):
            if source_name == 'source1':
                return first_mock_source
            elif source_name == 'source2':
                return second_mock_source
            return None

        mock_get_source.side_effect = side_effect

        # Test getting the latest price
        result = self.source.get_latest_price(
            'BTC:USD:source1/BTC,source2/BTC')

        # Verify results
        self.assertEqual(result, (Decimal('45000.00'), self.today, 'USD'))
        self.assertTrue(first_mock_source.get_latest_called)
        self.assertTrue(second_mock_source.get_latest_called)
        self.assertEqual(mock_get_source.call_count, 2)

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_latest_price_with_inversion(self, mock_get_source):
        """Test getting the latest price with inversion notation."""
        # Set up the mock source with a price of 0.75 CAD per USD
        mock_source = MockSource(self,
                                 latest_result=(Decimal('0.75'), self.today,
                                                'USD'))
        mock_get_source.return_value = mock_source

        # Test getting the latest price with inversion
        # This should invert 0.75 to get 1.33333... USD per CAD
        result = self.source.get_latest_price('CAD:USD:yahoo/^CADUSD=X')

        # Verify results - price should be inverted (1/0.75 = 1.33333...)
        self.assertEqual(result[0], Decimal('1') / Decimal('0.75'))
        self.assertEqual(result[1], self.today)
        self.assertEqual(result[2], 'USD')
        self.assertEqual(self.latest_ticker,
                         'CADUSD=X')  # Ticker should have ^ removed
        self.assertTrue(mock_source.get_latest_called)
        mock_get_source.assert_called_once_with(source_name='yahoo',
                                                custom_only=False)

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_historical_price(self, mock_get_source):
        """Test getting a historical price."""
        # Set up the mock source
        mock_source = MockSource(self,
                                 historical_result=(Decimal('145.00'),
                                                    self.yesterday, 'USD'))
        mock_get_source.return_value = mock_source

        # Test getting the historical price
        result = self.source.get_historical_price('AAPL:USD:yahoo/AAPL',
                                                  self.yesterday)

        # Verify results
        self.assertEqual(result, (Decimal('145.00'), self.yesterday, 'USD'))
        self.assertEqual(self.historical_ticker, 'AAPL')
        self.assertEqual(self.historical_time, self.yesterday)
        self.assertTrue(mock_source.get_historical_called)
        mock_get_source.assert_called_once_with(source_name='yahoo',
                                                custom_only=False)

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_historical_price_with_inversion(self, mock_get_source):
        """Test getting a historical price with inversion notation."""
        # Set up the mock source with a historical price of 0.78 CAD per USD
        mock_source = MockSource(self,
                                 historical_result=(Decimal('0.78'),
                                                    self.yesterday, 'USD'))
        mock_get_source.return_value = mock_source

        # Test getting the historical price with inversion
        # This should invert 0.78 to get 1.28205... USD per CAD
        result = self.source.get_historical_price('CAD:USD:yahoo/^CADUSD=X',
                                                  self.yesterday)

        # Verify results - price should be inverted (1/0.78 = 1.28205...)
        self.assertEqual(result[0], Decimal('1') / Decimal('0.78'))
        self.assertEqual(result[1], self.yesterday)
        self.assertEqual(result[2], 'USD')
        self.assertEqual(self.historical_ticker, 'CADUSD=X')
        self.assertEqual(self.historical_time, self.yesterday)
        self.assertTrue(mock_source.get_historical_called)
        mock_get_source.assert_called_once_with(source_name='yahoo',
                                                custom_only=False)

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_prices_series(self, mock_get_source):
        """Test getting a price series."""
        # Set up the mock source
        start_date = self.today - datetime.timedelta(days=5)
        end_date = self.today
        series_data = [
            (start_date, Decimal('140.00'), 'USD'),
            (start_date + datetime.timedelta(days=1), Decimal('142.00'),
             'USD'),
            (start_date + datetime.timedelta(days=2), Decimal('145.00'),
             'USD'),
            (end_date, Decimal('150.00'), 'USD'),
        ]

        mock_source = MockSource(self, series_result=series_data)
        mock_get_source.return_value = mock_source

        # Test getting the price series
        result = self.source.get_prices_series('AAPL:USD:yahoo/AAPL',
                                               start_date, end_date)

        # Convert result to list for comparison
        result_list = list(result)

        # Verify results
        self.assertEqual(len(result_list), 4)
        self.assertEqual(result_list[0],
                         (start_date, Decimal('140.00'), 'USD'))
        self.assertEqual(result_list[-1], (end_date, Decimal('150.00'), 'USD'))
        self.assertEqual(self.series_ticker, 'AAPL')
        self.assertEqual(self.series_time_begin, start_date)
        self.assertEqual(self.series_time_end, end_date)
        self.assertTrue(mock_source.get_series_called)
        mock_get_source.assert_called_once_with(source_name='yahoo',
                                                custom_only=False)

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_prices_series_with_inversion(self, mock_get_source):
        """Test getting a price series with inversion notation."""
        # Set up the mock source with a series of prices
        series_data = [(self.yesterday, Decimal('0.76'), 'USD'),
                       (self.today, Decimal('0.75'), 'USD')]
        mock_source = MockSource(self, series_result=series_data)
        mock_get_source.return_value = mock_source

        # Test getting the price series with inversion
        result = self.source.get_prices_series('CAD:USD:yahoo/^CADUSD=X',
                                               self.yesterday, self.today)

        # Convert result to list for easier assertion
        result_list = list(result)

        # Verify results - prices should be inverted
        self.assertEqual(len(result_list), 2)
        # Check first entry: (1/0.76 = 1.31578...)
        self.assertEqual(result_list[0][0], self.yesterday)
        self.assertEqual(result_list[0][1], Decimal('1') / Decimal('0.76'))
        self.assertEqual(result_list[0][2], 'USD')
        # Check second entry: (1/0.75 = 1.33333...)
        self.assertEqual(result_list[1][0], self.today)
        self.assertEqual(result_list[1][1], Decimal('1') / Decimal('0.75'))
        self.assertEqual(result_list[1][2], 'USD')

        self.assertEqual(self.series_ticker, 'CADUSD=X')
        self.assertEqual(self.series_time_begin, self.yesterday)
        self.assertEqual(self.series_time_end, self.today)
        self.assertTrue(mock_source.get_series_called)
        mock_get_source.assert_called_once_with(source_name='yahoo',
                                                custom_only=False)

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_invalid_ticker_format(self, mock_get_source):
        """Test handling of invalid ticker formats."""
        # Test with an invalid ticker (missing colon)
        result = self.source.get_latest_price('AAPL')
        self.assertIsNone(result)
        mock_get_source.assert_not_called()

        # Test with an invalid ticker (no source/ticker)
        result = self.source.get_latest_price('AAPL:USD')
        self.assertIsNone(result)
        mock_get_source.assert_not_called()

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_source_not_found(self, mock_get_source):
        """Test handling when a source is not found."""
        mock_get_source.return_value = None

        # Test getting the latest price
        result = self.source.get_latest_price('AAPL:USD:unknown/AAPL')

        # Verify results
        self.assertIsNone(result)
        mock_get_source.assert_called_once_with(source_name='unknown',
                                                custom_only=False)

    @mock.patch('beansprout.quoter.sources.dispatching.get_source')
    def test_get_latest_price_with_zero_inversion(self, mock_get_source):
        """Test getting the latest price with inversion when value is zero."""
        # Set up the mock source with a price of 0.0
        mock_source = MockSource(self,
                                 latest_result=(Decimal('0.0'), self.today,
                                                'USD'))
        mock_get_source.return_value = mock_source

        # Test getting the latest price with inversion on zero value
        # This should skip the source as we can't invert zero
        result = self.source.get_latest_price('CAD:USD:yahoo/^CADUSD=X')

        # Verify results - no result should be returned as we can't invert 0
        self.assertIsNone(result)
        self.assertEqual(self.latest_ticker, 'CADUSD=X')
        self.assertTrue(mock_source.get_latest_called)

    def test_try_sources_latest(self):
        """Test trying multiple sources to get the latest price."""
        # Create a mock source
        mock_source = mock.MagicMock()
        mock_source.get_latest_price.return_value = (Decimal('150.00'),
                                                     self.today, 'USD')

        # Set up price sources
        price_sources = [
            PriceSource(currency='USD',
                        source='yahoo',
                        ticker='AAPL',
                        invert=False),
            PriceSource(currency='CAD',
                        source='yahoo',
                        ticker='AAPL.TO',
                        invert=False)
        ]

        # Patch _get_or_create_source
        with mock.patch.object(self.source,
                               '_get_or_create_source',
                               return_value=mock_source):
            result = self.source._try_sources_latest(price_sources)

        # Verify result
        self.assertEqual(result, (Decimal('150.00'), self.today, 'USD'))
        mock_source.get_latest_price.assert_called_once_with('AAPL')

    def test_try_sources_latest_with_inversion(self):
        """Test trying sources to get the latest price with inversion."""
        # Create a mock source
        mock_source = mock.MagicMock()
        mock_source.get_latest_price.return_value = (Decimal('0.75'),
                                                     self.today, 'USD')

        # Set up price source with inversion
        price_source = PriceSource(currency='USD',
                                   source='yahoo',
                                   ticker='CADUSD=X',
                                   invert=True)

        # Patch _get_or_create_source
        with mock.patch.object(self.source,
                               '_get_or_create_source',
                               return_value=mock_source):
            result = self.source._try_sources_latest([price_source])

        # Verify result - price should be inverted
        expected_price = Decimal('1') / Decimal('0.75')  # 1.33333...
        self.assertEqual(result[0], expected_price)
        self.assertEqual(result[1], self.today)
        self.assertEqual(result[2], 'USD')
        mock_source.get_latest_price.assert_called_once_with('CADUSD=X')

    def test_try_sources_latest_with_zero_inversion(self):
        """Test trying sources to get the latest price with zero inversion."""
        # Create a mock source
        mock_source = mock.MagicMock()
        mock_source.get_latest_price.return_value = (Decimal('0'), self.today,
                                                     'USD')

        # Set up price source with inversion
        price_source = PriceSource(currency='USD',
                                   source='yahoo',
                                   ticker='CADUSD=X',
                                   invert=True)

        # Patch _get_or_create_source
        with mock.patch.object(self.source,
                               '_get_or_create_source',
                               return_value=mock_source):
            result = self.source._try_sources_latest([price_source])

        # Verify result - should be None since we can't invert zero
        self.assertIsNone(result)
        mock_source.get_latest_price.assert_called_once_with('CADUSD=X')


if __name__ == '__main__':
    unittest.main()
