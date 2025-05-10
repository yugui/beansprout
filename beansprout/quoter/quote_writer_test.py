#!/usr/bin/env python3
"""Unit tests for the QuoteWriter class."""

import os
import tempfile
import unittest
import datetime
from decimal import Decimal
from unittest import mock

from beancount.core.number import D
from beancount.core.amount import Amount
from beancount.core.data import Price

from beansprout.quoter.quote_writer import QuoteWriter


class QuoteWriterTest(unittest.TestCase):
    """Test cases for the QuoteWriter class."""

    def setUp(self):
        """Set up a temporary directory for testing file output."""
        self.temp_dir = tempfile.mkdtemp()
        self.writer = QuoteWriter(self.temp_dir, verbose=0)

    def tearDown(self):
        """Clean up temporary files and directories."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_destination_path(self):
        """Test generating destination paths."""
        self.assertEqual(
            os.path.join(self.temp_dir, 'quotes', 'USD', '202504.beancount'),
            self.writer.get_destination_path('USD', '202504'))

    def test_format_price_for_display(self):
        """Test formatting a price for display."""
        price = Price(meta=None,
                      date=datetime.date(2025, 4, 15),
                      currency='USD',
                      amount=Amount(D('123.45'), 'JPY'))
        self.assertEqual("2025-04-15 price USD 123.45 JPY",
                         self.writer.format_price_for_display(price))

    def test_write_prices_empty(self):
        """Test writing when there are no prices."""
        self.assertEqual({}, self.writer.write_prices([]))

    def test_write_prices(self):
        """Test writing prices to files."""
        prices = [
            Price(meta=None,
                  date=datetime.date(2025, 4, 10),
                  currency='USD',
                  amount=Amount(D('120.00'), 'JPY')),
            Price(meta=None,
                  date=datetime.date(2025, 4, 15),
                  currency='USD',
                  amount=Amount(D('123.45'), 'JPY')),
            Price(meta=None,
                  date=datetime.date(2025, 4, 20),
                  currency='USD',
                  amount=Amount(D('125.67'), 'JPY')),
            # Different month
            Price(meta=None,
                  date=datetime.date(2025, 5, 1),
                  currency='USD',
                  amount=Amount(D('126.00'), 'JPY')),
            # Different commodity
            Price(meta=None,
                  date=datetime.date(2025, 4, 10),
                  currency='EUR',
                  amount=Amount(D('130.00'), 'JPY')),
        ]

        written_files = self.writer.write_prices(prices)

        # Check the return value
        self.assertIn('USD', written_files)
        self.assertIn('EUR', written_files)
        self.assertEqual(2, len(written_files['USD']))
        self.assertEqual(1, len(written_files['EUR']))

        # Check USD/202504.beancount
        usd_apr_path = os.path.join(self.temp_dir, 'quotes', 'USD',
                                    '202504.beancount')
        self.assertTrue(os.path.exists(usd_apr_path))
        with open(usd_apr_path, 'r') as f:
            content = f.read()
            self.assertIn('2025-04-10 price USD 120.00 JPY', content)
            self.assertIn('2025-04-15 price USD 123.45 JPY', content)
            self.assertIn('2025-04-20 price USD 125.67 JPY', content)
            self.assertNotIn('2025-05-01',
                             content)  # Should be in a different file

        # Check USD/202505.beancount
        usd_may_path = os.path.join(self.temp_dir, 'quotes', 'USD',
                                    '202505.beancount')
        self.assertTrue(os.path.exists(usd_may_path))
        with open(usd_may_path, 'r') as f:
            content = f.read()
            self.assertIn('2025-05-01 price USD 126.00 JPY', content)
            self.assertNotIn('2025-04',
                             content)  # Should not contain April prices

        # Check EUR/202504.beancount
        eur_apr_path = os.path.join(self.temp_dir, 'quotes', 'EUR',
                                    '202504.beancount')
        self.assertTrue(os.path.exists(eur_apr_path))
        with open(eur_apr_path, 'r') as f:
            content = f.read()
            self.assertIn('2025-04-10 price EUR 130.00 JPY', content)
            self.assertNotIn('USD', content)  # Should not contain USD prices


if __name__ == '__main__':
    unittest.main()