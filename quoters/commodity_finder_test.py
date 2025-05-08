#!/usr/bin/env python3
"""Tests for the commodity_finder module."""

import os
import unittest

from beancount.core.data import Commodity
from beancount import loader

from quoters import commodity_finder


class TestCommodityFinder(unittest.TestCase):
    """Test the CommodityFinder class."""

    def setUp(self) -> None:
        """Set up test data with sample commodity definitions."""
        # Get the path to the testdata directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        test_file = os.path.join(current_dir, 'testdata', 'test-commodities.beancount')
        
        # Load entries from the test file
        self.entries, self.errors, self.options_map = loader.load_file(
            filename=test_file)
        
        # Create a finder instance
        self.finder = commodity_finder.CommodityFinder()

    def test_find_all_commodities(self) -> None:
        """Test finding all commodities from entries."""
        commodities = self.finder.find_all_commodities(entries=self.entries)
        symbols = [c.currency for c in commodities]
        self.assertEqual(sorted(symbols), ["AAPL", "BTC", "GOOGL", "MSFT", "USD"])

    def test_filter_active_commodities(self) -> None:
        """Test filtering active commodities based on metadata criteria."""
        commodities = self.finder.find_all_commodities(entries=self.entries)
        active = self.finder.filter_active_commodities(commodities=commodities)
        symbols = [c.currency for c in active]
        self.assertEqual(sorted(symbols), ["AAPL", "MSFT"])

    def test_get_price_sources(self) -> None:
        """Test extracting price sources from commodity metadata."""
        # Find Apple's commodity directive
        commodities = self.finder.find_all_commodities(entries=self.entries)
        apple = next(c for c in commodities if c.currency == "AAPL")
        
        sources = self.finder.get_price_sources(commodity=apple)
        self.assertEqual(sources, {"USD": "yahoo/AAPL"})


if __name__ == "__main__":
    unittest.main()