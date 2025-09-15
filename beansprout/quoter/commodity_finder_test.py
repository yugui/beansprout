#!/usr/bin/env python3
"""Tests for the commodity_finder module."""

import os
import unittest
import re

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

    def test_filter_by_pattern(self) -> None:
        """Test filtering commodities by regex pattern."""
        # Find all commodities
        all_commodities = self.finder.find_all_commodities(
            entries=self.entries)

        # Test pattern matching for stocks starting with 'A'
        pattern = r"^A.*"
        filtered = self.finder.filter_by_pattern(all_commodities, pattern)
        filtered_currencies = {c.currency for c in filtered}
        self.assertEqual(filtered_currencies, {"AAPL"})

        # Test pattern matching for stocks starting with 'M' or 'G'
        pattern = r"^[MG].*"
        filtered = self.finder.filter_by_pattern(all_commodities, pattern)
        filtered_currencies = {c.currency for c in filtered}
        self.assertEqual(filtered_currencies, {"MSFT", "GOOGL"})

        # Test pattern matching for 3-letter currencies
        pattern = r"^[A-Z]{3}$"
        filtered = self.finder.filter_by_pattern(all_commodities, pattern)
        filtered_currencies = {c.currency for c in filtered}
        self.assertEqual(filtered_currencies, {"USD", "BTC"})

        # Test pattern that matches nothing
        pattern = r"^XYZ$"
        filtered = self.finder.filter_by_pattern(all_commodities, pattern)
        self.assertEqual(len(filtered), 0)

        # Test invalid regex pattern
        with self.assertRaises(re.error):
            self.finder.filter_by_pattern(all_commodities, "[invalid")

    def test_filter_by_source(self) -> None:
        """Test filtering commodities by source name."""
        # Find all commodities
        all_commodities = self.finder.find_all_commodities(
            entries=self.entries)

        # Test filtering by mock_yahoo source
        sources = {"mock_yahoo"}
        filtered = self.finder.filter_by_source(all_commodities, sources)
        filtered_currencies = {c.currency for c in filtered}
        self.assertEqual(filtered_currencies, {"AAPL", "MSFT", "GOOGL"})

        # Test filtering by nonexistent source
        sources = {"nonexistent"}
        filtered = self.finder.filter_by_source(all_commodities, sources)
        self.assertEqual(len(filtered), 0)

        # Test filtering by multiple sources
        sources = {"mock_yahoo", "coinbase"}
        filtered = self.finder.filter_by_source(all_commodities, sources)
        filtered_currencies = {c.currency for c in filtered}
        self.assertEqual(filtered_currencies, {"AAPL", "MSFT", "GOOGL"})

    def test_parse_source_names(self) -> None:
        """Test parsing source names from commodity price metadata."""
        # Find all commodities
        all_commodities = self.finder.find_all_commodities(
            entries=self.entries)

        # Test parsing source from AAPL (USD:mock_yahoo/AAPL)
        aapl = next(c for c in all_commodities if c.currency == "AAPL")
        sources = self.finder.parse_source_names(aapl)
        self.assertEqual(sources, {"mock_yahoo"})

        # Test parsing source from commodity without price metadata
        usd = next(c for c in all_commodities if c.currency == "USD")
        sources = self.finder.parse_source_names(usd)
        self.assertEqual(sources, set())

        # Test parsing source from MSFT (USD:mock_yahoo/MSFT)
        msft = next(c for c in all_commodities if c.currency == "MSFT")
        sources = self.finder.parse_source_names(msft)
        self.assertEqual(sources, {"mock_yahoo"})

    def test_parse_source_names_complex(self) -> None:
        """Test parsing source names from complex price metadata."""
        from beancount.core.data import Commodity
        import datetime

        # Create test commodities with complex price metadata

        # Test multiple sources for same currency
        meta1 = {'price': 'USD:yahoo/AAPL,coinbase/AAPL'}
        commodity1 = Commodity(meta=meta1,
                               date=datetime.date.today(),
                               currency='AAPL')
        sources = self.finder.parse_source_names(commodity1)
        self.assertEqual(sources, {"yahoo", "coinbase"})

        # Test multiple currencies
        meta2 = {'price': 'USD:yahoo/MSFT JPY:yahoo/MSFT.T'}
        commodity2 = Commodity(meta=meta2,
                               date=datetime.date.today(),
                               currency='MSFT')
        sources = self.finder.parse_source_names(commodity2)
        self.assertEqual(sources, {"yahoo"})

        # Test with inversion symbol
        meta3 = {'price': 'USD:yahoo/^CADUSD=X'}
        commodity3 = Commodity(meta=meta3,
                               date=datetime.date.today(),
                               currency='CAD')
        sources = self.finder.parse_source_names(commodity3)
        self.assertEqual(sources, {"yahoo"})

        # Test complex combination
        meta4 = {'price': 'USD:yahoo/BTC,coinbase/BTC EUR:kraken/BTC'}
        commodity4 = Commodity(meta=meta4,
                               date=datetime.date.today(),
                               currency='BTC')
        sources = self.finder.parse_source_names(commodity4)
        self.assertEqual(sources, {"yahoo", "coinbase", "kraken"})


if __name__ == "__main__":
    unittest.main()
