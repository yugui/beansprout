#!/usr/bin/env python3
"""Tests for the bean_sprout module."""

import unittest
import datetime

from beancount.core.data import Commodity

from bean_sprout import parse_expressions_into_commodities


class TestExpressionParsing(unittest.TestCase):
    """Test the expression parsing functionality."""

    def test_parse_expression_valid(self) -> None:
        """Test parsing valid expressions."""
        # Test basic expression
        expression = "USD:yahoo/AAPL"
        commodities = parse_expressions_into_commodities(expression)

        self.assertEqual(len(commodities), 1)
        commodity = commodities[0]
        self.assertIsInstance(commodity, Commodity)
        self.assertEqual(commodity.currency, "AAPL")
        self.assertEqual(commodity.meta['price'], "USD:yahoo/AAPL")
        self.assertEqual(commodity.meta['filename'], "<expression>")
        self.assertEqual(commodity.meta['lineno'], 0)
        self.assertEqual(commodity.date, datetime.date.today())

    def test_parse_expression_with_special_symbols(self) -> None:
        """Test parsing expressions with special symbols."""
        # Test with ticker that has special characters
        expression = "USD:yahoo/CADUSD=X"
        commodities = parse_expressions_into_commodities(expression)

        self.assertEqual(len(commodities), 1)
        commodity = commodities[0]
        self.assertEqual(commodity.currency, "CADUSD=X")
        self.assertEqual(commodity.meta['price'], "USD:yahoo/CADUSD=X")

    def test_parse_expression_invalid_format(self) -> None:
        """Test parsing invalid expressions."""
        # Test missing colon
        with self.assertRaises(ValueError) as context:
            parse_expressions_into_commodities("USDyahoo/AAPL")
        self.assertIn("Invalid format", str(context.exception))

        # Test missing slash
        with self.assertRaises(ValueError) as context:
            parse_expressions_into_commodities("USD:yahooAAPL")
        self.assertIn("Invalid source/ticker format", str(context.exception))

        # Test empty string
        with self.assertRaises(ValueError) as context:
            parse_expressions_into_commodities("")
        self.assertIn("Empty price expression", str(context.exception))

    def test_parse_expression_edge_cases(self) -> None:
        """Test parsing edge cases."""
        # Test only colon
        with self.assertRaises(ValueError):
            parse_expressions_into_commodities(":")

        # Test only slash
        with self.assertRaises(ValueError):
            parse_expressions_into_commodities("/")

        # Test valid minimal expression
        expression = "A:B/C"
        commodities = parse_expressions_into_commodities(expression)
        self.assertEqual(len(commodities), 1)
        commodity = commodities[0]
        self.assertEqual(commodity.currency, "C")
        self.assertEqual(commodity.meta['price'], "A:B/C")

    def test_parse_expression_multiple_commodities(self) -> None:
        """Test parsing expressions with multiple commodities."""
        # Test multiple currencies
        expression = "USD:yahoo/AAPL CAD:yahoo/AAPL.TO"
        commodities = parse_expressions_into_commodities(expression)

        # Should have 2 commodities for the 2 different tickers
        self.assertEqual(len(commodities), 2)

        # Check that we get both tickers
        currencies = {c.currency for c in commodities}
        self.assertEqual(currencies, {"AAPL", "AAPL.TO"})

        # All should have the same expression in metadata
        for commodity in commodities:
            self.assertEqual(commodity.meta['price'], expression)

    def test_parse_expression_with_inversion(self) -> None:
        """Test parsing expressions with inversion notation."""
        expression = "USD:yahoo/^CADUSD=X"
        commodities = parse_expressions_into_commodities(expression)

        self.assertEqual(len(commodities), 1)
        commodity = commodities[0]
        self.assertEqual(commodity.currency, "CADUSD=X")
        self.assertEqual(commodity.meta['price'], expression)


if __name__ == "__main__":
    unittest.main()
