#!/usr/bin/env python3
"""Tests for the commodity_finder module."""

import os
import unittest

from beancount.core.data import Commodity
from beancount import loader

from beansprout.quoter import commodity_finder


class TestCommodityFinder(unittest.TestCase):
    """Test the CommodityFinder class."""

    def setUp(self) -> None:
        """Set up test data with sample commodity definitions."""
        # Get the path to the testdata directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        test_file = os.path.join(current_dir, 'testdata',
                                 'test-commodities.beancount')

        # Load entries from the test file
        self.entries, self.errors, self.options_map = loader.load_file(
            filename=test_file)

        # Create a finder instance
        self.finder = commodity_finder.CommodityFinder()

    def test_find_all_commodities(self) -> None:
        """Test finding all commodities in the entries."""
        commodities = self.finder.find_all_commodities(entries=self.entries)

        # Check that we found the expected number of commodities
        self.assertEqual(len(commodities), 5)  # USD, AAPL, MSFT, GOOGL, BTC

        # Check that each item is a Commodity instance
        for commodity in commodities:
            self.assertIsInstance(commodity, Commodity)

        # Check that we found the specific commodities we expect
        currencies = {c.currency for c in commodities}
        self.assertEqual(currencies, {"USD", "AAPL", "MSFT", "GOOGL", "BTC"})

    def test_filter_active_commodities(self) -> None:
        """Test filtering active commodities."""
        # Find all commodities
        all_commodities = self.finder.find_all_commodities(
            entries=self.entries)

        # Filter active ones (commodities with price metadata and not disabled)
        active = self.finder.filter_active_commodities(
            commodities=all_commodities)

        # Only AAPL and MSFT have price metadata and aren't disabled
        # GOOGL has price metadata but is disabled with quote: "disabled"
        # USD and BTC don't have price metadata
        active_currencies = {c.currency for c in active}
        self.assertEqual(active_currencies, {"AAPL", "MSFT"})
        self.assertNotIn("GOOGL", active_currencies)
        self.assertNotIn("USD", active_currencies)
        self.assertNotIn("BTC", active_currencies)


if __name__ == "__main__":
    unittest.main()