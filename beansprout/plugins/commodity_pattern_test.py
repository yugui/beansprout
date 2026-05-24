#!/usr/bin/env python3
"""Tests for commodity_pattern plugin."""

import datetime
import unittest
from decimal import Decimal

from beancount.core import data
from beansprout.plugins import commodity_pattern


class CommodityPatternTest(unittest.TestCase):
    """Test cases for commodity_pattern plugin."""

    def test_no_patterns(self):
        """Test with no commodity-pattern metadata on any account."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Bank",
                currencies=["USD"],
                booking=None,
            ),
            data.Transaction(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2
                },
                date=datetime.date(2020, 1, 2),
                flag="*",
                payee="Test",
                narration="Test transaction",
                tags=frozenset(),
                links=frozenset(),
                postings=[
                    data.Posting(
                        account="Assets:Bank",
                        units=data.Amount(Decimal("100"), "USD"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                    data.Posting(
                        account="Expenses:Test",
                        units=data.Amount(Decimal("-100"), "USD"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                ],
            ),
        ]

        result_entries, errors = commodity_pattern.commodity_pattern(
            entries, {})

        self.assertEqual(entries, result_entries)
        self.assertEqual([], errors)

    def test_matching_commodity(self):
        """Test commodity that matches the pattern."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1,
                    "commodity-pattern": "USD|EUR",
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Bank",
                currencies=None,
                booking=None,
            ),
            data.Transaction(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2
                },
                date=datetime.date(2020, 1, 2),
                flag="*",
                payee="Test",
                narration="Test transaction",
                tags=frozenset(),
                links=frozenset(),
                postings=[
                    data.Posting(
                        account="Assets:Bank",
                        units=data.Amount(Decimal("100"), "USD"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                    data.Posting(
                        account="Expenses:Test",
                        units=data.Amount(Decimal("-100"), "USD"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                ],
            ),
        ]

        result_entries, errors = commodity_pattern.commodity_pattern(
            entries, {})

        self.assertEqual(entries, result_entries)
        self.assertEqual([], errors)

    def test_non_matching_commodity(self):
        """Test commodity that doesn't match the pattern."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1,
                    "commodity-pattern": "USD|EUR",
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Bank",
                currencies=None,
                booking=None,
            ),
            data.Transaction(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2
                },
                date=datetime.date(2020, 1, 2),
                flag="*",
                payee="Test",
                narration="Test transaction",
                tags=frozenset(),
                links=frozenset(),
                postings=[
                    data.Posting(
                        account="Assets:Bank",
                        units=data.Amount(Decimal("100"), "JPY"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                    data.Posting(
                        account="Expenses:Test",
                        units=data.Amount(Decimal("-100"), "JPY"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                ],
            ),
        ]

        result_entries, errors = commodity_pattern.commodity_pattern(
            entries, {})

        self.assertEqual(entries, result_entries)
        self.assertEqual(1, len(errors))
        self.assertIn("JPY", errors[0].message)
        self.assertIn("Assets:Bank", errors[0].message)
        self.assertIn("USD|EUR", errors[0].message)

    def test_multiple_postings_same_account(self):
        """Test transaction with multiple postings to same account, some match, some don't."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1,
                    "commodity-pattern": "USD",
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Bank",
                currencies=None,
                booking=None,
            ),
            data.Transaction(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2
                },
                date=datetime.date(2020, 1, 2),
                flag="*",
                payee="Test",
                narration="Multiple currencies",
                tags=frozenset(),
                links=frozenset(),
                postings=[
                    data.Posting(
                        account="Assets:Bank",
                        units=data.Amount(Decimal("100"), "USD"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                    data.Posting(
                        account="Assets:Bank",
                        units=data.Amount(Decimal("50"), "EUR"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                    data.Posting(
                        account="Equity:Opening",
                        units=data.Amount(Decimal("-150"), "USD"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                ],
            ),
        ]

        result_entries, errors = commodity_pattern.commodity_pattern(
            entries, {})

        self.assertEqual(entries, result_entries)
        self.assertEqual(1, len(errors))
        self.assertIn("EUR", errors[0].message)

    def test_multiple_accounts_different_patterns(self):
        """Test multiple accounts with different patterns."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1,
                    "commodity-pattern": "USD|EUR",
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Bank:Fiat",
                currencies=None,
                booking=None,
            ),
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2,
                    "commodity-pattern": "BTC|ETH",
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Crypto",
                currencies=None,
                booking=None,
            ),
            data.Transaction(
                meta={
                    "filename": "test.beancount",
                    "lineno": 3
                },
                date=datetime.date(2020, 1, 2),
                flag="*",
                payee="Exchange",
                narration="Buy crypto",
                tags=frozenset(),
                links=frozenset(),
                postings=[
                    data.Posting(
                        account="Assets:Bank:Fiat",
                        units=data.Amount(Decimal("-1000"), "USD"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                    data.Posting(
                        account="Assets:Crypto",
                        units=data.Amount(Decimal("1"), "BTC"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                ],
            ),
        ]

        result_entries, errors = commodity_pattern.commodity_pattern(
            entries, {})

        self.assertEqual(entries, result_entries)
        self.assertEqual([], errors)

    def test_account_without_pattern_ignored(self):
        """Test that accounts without commodity-pattern metadata are not validated."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1,
                    "commodity-pattern": "USD",
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Bank",
                currencies=None,
                booking=None,
            ),
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2
                },
                date=datetime.date(2020, 1, 1),
                account="Expenses:Food",
                currencies=None,
                booking=None,
            ),
            data.Transaction(
                meta={
                    "filename": "test.beancount",
                    "lineno": 3
                },
                date=datetime.date(2020, 1, 2),
                flag="*",
                payee="Restaurant",
                narration="Lunch",
                tags=frozenset(),
                links=frozenset(),
                postings=[
                    data.Posting(
                        account="Assets:Bank",
                        units=data.Amount(Decimal("-20"), "USD"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                    data.Posting(
                        account="Expenses:Food",
                        units=data.Amount(Decimal("20"), "JPY"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                ],
            ),
        ]

        result_entries, errors = commodity_pattern.commodity_pattern(
            entries, {})

        self.assertEqual(entries, result_entries)
        # No error for Expenses:Food even though JPY doesn't match "USD"
        # because Expenses:Food doesn't have commodity-pattern
        self.assertEqual([], errors)

    def test_invalid_regex_pattern(self):
        """Test that invalid regex pattern reports error early."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1,
                    "commodity-pattern": "[invalid",
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Bank",
                currencies=None,
                booking=None,
            ),
            data.Transaction(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2
                },
                date=datetime.date(2020, 1, 2),
                flag="*",
                payee="Test",
                narration="Test",
                tags=frozenset(),
                links=frozenset(),
                postings=[
                    data.Posting(
                        account="Assets:Bank",
                        units=data.Amount(Decimal("100"), "USD"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                ],
            ),
        ]

        result_entries, errors = commodity_pattern.commodity_pattern(
            entries, {})

        self.assertEqual(entries, result_entries)
        self.assertEqual(1, len(errors))
        self.assertIn("Invalid regex pattern", errors[0].message)
        self.assertIn("[invalid", errors[0].message)
        self.assertIn("Assets:Bank", errors[0].message)

    def test_auto_balanced_posting_skipped(self):
        """Test that postings with units=None are skipped."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1,
                    "commodity-pattern": "USD",
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Bank",
                currencies=None,
                booking=None,
            ),
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2,
                    "commodity-pattern": "USD",
                },
                date=datetime.date(2020, 1, 1),
                account="Expenses:Test",
                currencies=None,
                booking=None,
            ),
            data.Transaction(
                meta={
                    "filename": "test.beancount",
                    "lineno": 3
                },
                date=datetime.date(2020, 1, 2),
                flag="*",
                payee="Test",
                narration="Auto-balanced",
                tags=frozenset(),
                links=frozenset(),
                postings=[
                    data.Posting(
                        account="Assets:Bank",
                        units=data.Amount(Decimal("-100"), "USD"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                    data.Posting(
                        account="Expenses:Test",
                        units=None,
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                ],
            ),
        ]

        result_entries, errors = commodity_pattern.commodity_pattern(
            entries, {})

        self.assertEqual(entries, result_entries)
        self.assertEqual([], errors)

    def test_complex_regex_pattern_stock(self):
        """Test complex regex pattern for stock symbols."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1,
                    "commodity-pattern": "STOCK-[A-Z]+",
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Stocks",
                currencies=None,
                booking=None,
            ),
            data.Transaction(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2
                },
                date=datetime.date(2020, 1, 2),
                flag="*",
                payee="Broker",
                narration="Buy stock",
                tags=frozenset(),
                links=frozenset(),
                postings=[
                    data.Posting(
                        account="Assets:Stocks",
                        units=data.Amount(Decimal("10"), "STOCK-AAPL"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                    data.Posting(
                        account="Assets:Cash",
                        units=data.Amount(Decimal("-1000"), "USD"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                ],
            ),
        ]

        result_entries, errors = commodity_pattern.commodity_pattern(
            entries, {})

        self.assertEqual(entries, result_entries)
        self.assertEqual([], errors)

    def test_complex_regex_pattern_suffix(self):
        """Test regex pattern matching suffix."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1,
                    "commodity-pattern": ".*-JPY",
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:FX",
                currencies=None,
                booking=None,
            ),
            data.Transaction(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2
                },
                date=datetime.date(2020, 1, 2),
                flag="*",
                payee="FX",
                narration="FX position",
                tags=frozenset(),
                links=frozenset(),
                postings=[
                    data.Posting(
                        account="Assets:FX",
                        units=data.Amount(Decimal("100"), "USD-JPY"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                    data.Posting(
                        account="Assets:Cash",
                        units=data.Amount(Decimal("-100"), "USD"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                ],
            ),
        ]

        result_entries, errors = commodity_pattern.commodity_pattern(
            entries, {})

        self.assertEqual(entries, result_entries)
        self.assertEqual([], errors)

    def test_fullmatch_not_partial(self):
        """Test that pattern must match the entire commodity, not just a part."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1,
                    "commodity-pattern": "USD",
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Bank",
                currencies=None,
                booking=None,
            ),
            data.Transaction(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2
                },
                date=datetime.date(2020, 1, 2),
                flag="*",
                payee="Test",
                narration="Test",
                tags=frozenset(),
                links=frozenset(),
                postings=[
                    data.Posting(
                        account="Assets:Bank",
                        units=data.Amount(Decimal("100"), "USDC"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                ],
            ),
        ]

        result_entries, errors = commodity_pattern.commodity_pattern(
            entries, {})

        self.assertEqual(entries, result_entries)
        # USDC should NOT match pattern "USD" because fullmatch is used
        self.assertEqual(1, len(errors))
        self.assertIn("USDC", errors[0].message)

    def test_multiple_errors_same_transaction(self):
        """Test transaction with multiple failing postings reports multiple errors."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1,
                    "commodity-pattern": "USD",
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Bank",
                currencies=None,
                booking=None,
            ),
            data.Transaction(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2
                },
                date=datetime.date(2020, 1, 2),
                flag="*",
                payee="Test",
                narration="Multiple failures",
                tags=frozenset(),
                links=frozenset(),
                postings=[
                    data.Posting(
                        account="Assets:Bank",
                        units=data.Amount(Decimal("100"), "EUR"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                    data.Posting(
                        account="Assets:Bank",
                        units=data.Amount(Decimal("50"), "JPY"),
                        cost=None,
                        price=None,
                        flag=None,
                        meta=None,
                    ),
                ],
            ),
        ]

        result_entries, errors = commodity_pattern.commodity_pattern(
            entries, {})

        self.assertEqual(entries, result_entries)
        self.assertEqual(2, len(errors))
        error_commodities = {e.message.split("'")[1] for e in errors}
        self.assertEqual({"EUR", "JPY"}, error_commodities)


if __name__ == "__main__":
    unittest.main()
