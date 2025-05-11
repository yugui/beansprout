#!/usr/bin/env python3
"""Unit tests for the QuoteWriter class."""

import os
import tempfile
import unittest
import datetime
from decimal import Decimal
from unittest import mock

from beancount import loader
from beancount.core.number import D
from beancount.core.amount import Amount
from beancount.core.data import Price

from beansprout.quoter.quote_writer import QuoteWriter


class QuoteWriterTest(unittest.TestCase):
    """Test cases for the QuoteWriter class."""

    def setUp(self):
        """Set up a temporary directory for testing file output."""
        self.temp_dir = tempfile.mkdtemp()
        self.writer = QuoteWriter(self.temp_dir)

    def tearDown(self):
        """Clean up temporary files and directories."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_destination_path(self):
        """Test generating destination paths."""
        self.assertEqual(
            os.path.join(self.temp_dir, 'quotes', 'USD', '202504.beancount'),
            self.writer.get_destination_path('USD', '202504'))

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

        # Use loader.load_file to parse the file
        entries, errors, _ = loader.load_file(usd_apr_path)
        self.assertEqual(0, len(errors),
                         f"Found errors in USD April file: {errors}")

        # Verify we have all the expected price entries for USD April
        self.assertEqual(3, len(entries))

        # Check the specific price entries
        for entry in entries:
            self.assertEqual('USD', entry.currency)
            self.assertEqual('JPY', entry.amount.currency)

        # Check specific dates and values
        dates = sorted([entry.date for entry in entries])
        self.assertEqual(datetime.date(2025, 4, 10), dates[0])
        self.assertEqual(datetime.date(2025, 4, 15), dates[1])
        self.assertEqual(datetime.date(2025, 4, 20), dates[2])

        # Check USD/202505.beancount
        usd_may_path = os.path.join(self.temp_dir, 'quotes', 'USD',
                                    '202505.beancount')
        self.assertTrue(os.path.exists(usd_may_path))

        # Use loader.load_file to parse the file
        may_entries, may_errors, _ = loader.load_file(usd_may_path)
        self.assertEqual(0, len(may_errors),
                         f"Found errors in USD May file: {may_errors}")

        # Verify we have all the expected price entries for USD May
        self.assertEqual(1, len(may_entries))

        # Check the specific price entries
        may_entry = may_entries[0]
        self.assertEqual('USD', may_entry.currency)
        self.assertEqual(datetime.date(2025, 5, 1), may_entry.date)
        self.assertEqual('JPY', may_entry.amount.currency)
        self.assertEqual(D('126.00'), may_entry.amount.number)

        # Check EUR/202504.beancount
        eur_apr_path = os.path.join(self.temp_dir, 'quotes', 'EUR',
                                    '202504.beancount')
        self.assertTrue(os.path.exists(eur_apr_path))

        # Use loader.load_file to parse the file
        eur_entries, eur_errors, _ = loader.load_file(eur_apr_path)
        self.assertEqual(0, len(eur_errors),
                         f"Found errors in EUR April file: {eur_errors}")

        # Verify we have all the expected price entries for EUR April
        self.assertEqual(1, len(eur_entries))

        # Check the specific price entry
        eur_entry = eur_entries[0]
        self.assertEqual('EUR', eur_entry.currency)
        self.assertEqual(datetime.date(2025, 4, 10), eur_entry.date)
        self.assertEqual('JPY', eur_entry.amount.currency)
        self.assertEqual(D('130.00'), eur_entry.amount.number)


if __name__ == '__main__':
    unittest.main()
