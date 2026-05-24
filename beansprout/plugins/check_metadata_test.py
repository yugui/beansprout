#!/usr/bin/env python3
"""Tests for check_metadata plugin."""

import datetime
import unittest
from decimal import Decimal

from beancount.core import data
from beansprout.plugins import check_metadata


class CheckMetadataTest(unittest.TestCase):
    """Test cases for check_metadata plugin."""

    def test_empty_config(self):
        """Test with empty configuration."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Bank:Checking",
                currencies=["USD"],
                booking=None,
            ),
        ]

        result_entries, errors = check_metadata.check_metadata(entries, {}, "")

        self.assertEqual(entries, result_entries)
        self.assertEqual([], errors)

    def test_unknown_directive_type(self):
        """Test with unknown directive type."""
        entries = []
        result_entries, errors = check_metadata.check_metadata(
            entries, {}, "transaction\nmetadata1")

        self.assertEqual(entries, result_entries)
        self.assertEqual(1, len(errors))
        self.assertIn("Unknown directive type", errors[0].message)
        self.assertIn("transaction", errors[0].message)

    def test_open_leaf_account_with_metadata(self):
        """Test Open directive on leaf account with all required metadata."""
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
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2,
                    "region": "US",
                    "tax_category": "taxable"
                },
                date=datetime.date(2020, 1, 2),
                account="Assets:Bank:Checking",
                currencies=["USD"],
                booking=None,
            ),
        ]

        config = "open\nregion\ntax_category"
        result_entries, errors = check_metadata.check_metadata(
            entries, {}, config)

        self.assertEqual(entries, result_entries)
        self.assertEqual([], errors)

    def test_open_leaf_account_missing_metadata(self):
        """Test Open directive on leaf account missing required metadata."""
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
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2
                },
                date=datetime.date(2020, 1, 2),
                account="Assets:Bank:Checking",
                currencies=["USD"],
                booking=None,
            ),
        ]

        config = "open\nregion\ntax_category"
        result_entries, errors = check_metadata.check_metadata(
            entries, {}, config)

        self.assertEqual(entries, result_entries)
        self.assertEqual(1, len(errors))
        self.assertIn("Assets:Bank:Checking", errors[0].message)
        self.assertIn("region", errors[0].message)
        self.assertIn("tax_category", errors[0].message)

    def test_open_non_leaf_account_not_checked(self):
        """Test Open directive on non-leaf account is not checked."""
        entries = [
            # Assets:Bank is non-leaf (has children)
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
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2,
                    "region": "US"
                },
                date=datetime.date(2020, 1, 2),
                account="Assets:Bank:Checking",
                currencies=["USD"],
                booking=None,
            ),
        ]

        config = "open\nregion"
        result_entries, errors = check_metadata.check_metadata(
            entries, {}, config)

        self.assertEqual(entries, result_entries)
        # Assets:Bank has no region metadata but is non-leaf, so no error
        # Assets:Bank:Checking has region metadata, so no error
        self.assertEqual([], errors)

    def test_close_leaf_account_missing_metadata(self):
        """Test Close directive on leaf account missing required metadata."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Bank:Old",
                currencies=["USD"],
                booking=None,
            ),
            data.Close(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2
                },
                date=datetime.date(2020, 12, 31),
                account="Assets:Bank:Old",
            ),
        ]

        config = "close\nreason"
        result_entries, errors = check_metadata.check_metadata(
            entries, {}, config)

        self.assertEqual(entries, result_entries)
        self.assertEqual(1, len(errors))
        self.assertIn("Assets:Bank:Old", errors[0].message)
        self.assertIn("reason", errors[0].message)

    def test_balance_leaf_account_with_metadata(self):
        """Test Balance directive on leaf account with required metadata."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Cash",
                currencies=["USD"],
                booking=None,
            ),
            data.Balance(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2,
                    "verified": "yes"
                },
                date=datetime.date(2020, 1, 15),
                account="Assets:Cash",
                amount=data.Amount(Decimal("100"), "USD"),
                tolerance=None,
                diff_amount=None,
            ),
        ]

        config = "balance\nverified"
        result_entries, errors = check_metadata.check_metadata(
            entries, {}, config)

        self.assertEqual(entries, result_entries)
        self.assertEqual([], errors)

    def test_document_leaf_account_missing_metadata(self):
        """Test Document directive on leaf account missing required metadata."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Documents",
                currencies=["USD"],
                booking=None,
            ),
            data.Document(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Documents",
                filename="/path/to/doc.pdf",
                tags=frozenset(),
                links=frozenset(),
            ),
        ]

        config = "document\ncategory"
        result_entries, errors = check_metadata.check_metadata(
            entries, {}, config)

        self.assertEqual(entries, result_entries)
        self.assertEqual(1, len(errors))
        self.assertIn("Assets:Documents", errors[0].message)
        self.assertIn("category", errors[0].message)

    def test_note_leaf_account_with_metadata(self):
        """Test Note directive on leaf account with required metadata."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Account",
                currencies=["USD"],
                booking=None,
            ),
            data.Note(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2,
                    "importance": "high"
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Account",
                comment="Important note",
                tags=frozenset(),
                links=frozenset(),
            ),
        ]

        config = "note\nimportance"
        result_entries, errors = check_metadata.check_metadata(
            entries, {}, config)

        self.assertEqual(entries, result_entries)
        self.assertEqual([], errors)

    def test_commodity_always_checked_with_metadata(self):
        """Test Commodity directive with required metadata (always checked)."""
        entries = [
            data.Commodity(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1,
                    "export": "yahoo/USD"
                },
                date=datetime.date(2020, 1, 1),
                currency="USD",
            ),
        ]

        config = "commodity\nexport"
        result_entries, errors = check_metadata.check_metadata(
            entries, {}, config)

        self.assertEqual(entries, result_entries)
        self.assertEqual([], errors)

    def test_commodity_always_checked_missing_metadata(self):
        """Test Commodity directive missing required metadata (always checked)."""
        entries = [
            data.Commodity(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1
                },
                date=datetime.date(2020, 1, 1),
                currency="JPY",
            ),
        ]

        config = "commodity\nexport"
        result_entries, errors = check_metadata.check_metadata(
            entries, {}, config)

        self.assertEqual(entries, result_entries)
        self.assertEqual(1, len(errors))
        self.assertIn("JPY", errors[0].message)
        self.assertIn("export", errors[0].message)

    def test_mixed_leaf_and_non_leaf_accounts(self):
        """Test multiple Open directives with mix of leaf and non-leaf accounts."""
        entries = [
            # Non-leaf parent - no region metadata
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
            # Leaf with metadata - OK
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2,
                    "region": "US"
                },
                date=datetime.date(2020, 1, 2),
                account="Assets:Bank:Checking",
                currencies=["USD"],
                booking=None,
            ),
            # Leaf without metadata - ERROR
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 3
                },
                date=datetime.date(2020, 1, 3),
                account="Assets:Bank:Savings",
                currencies=["USD"],
                booking=None,
            ),
        ]

        config = "open\nregion"
        result_entries, errors = check_metadata.check_metadata(
            entries, {}, config)

        self.assertEqual(entries, result_entries)
        # Only Assets:Bank:Savings should have an error
        self.assertEqual(1, len(errors))
        self.assertIn("Assets:Bank:Savings", errors[0].message)
        self.assertIn("region", errors[0].message)

    def test_multiple_missing_metadata(self):
        """Test directive missing multiple required metadata."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Account",
                currencies=["USD"],
                booking=None,
            ),
        ]

        config = "open\nregion\ntax_category\ntype"
        result_entries, errors = check_metadata.check_metadata(
            entries, {}, config)

        self.assertEqual(entries, result_entries)
        self.assertEqual(1, len(errors))
        # All three metadata should be listed in sorted order
        self.assertIn("region", errors[0].message)
        self.assertIn("tax_category", errors[0].message)
        self.assertIn("type", errors[0].message)

    def test_case_insensitive_directive_name(self):
        """Test that directive names are case-insensitive."""
        entries = [
            data.Commodity(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1
                },
                date=datetime.date(2020, 1, 1),
                currency="EUR",
            ),
        ]

        # Test with uppercase directive name
        config = "COMMODITY\nexport"
        result_entries, errors = check_metadata.check_metadata(
            entries, {}, config)

        self.assertEqual(entries, result_entries)
        self.assertEqual(1, len(errors))

    def test_only_specified_directive_type_checked(self):
        """Test that only the specified directive type is checked."""
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
            data.Commodity(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2
                },
                date=datetime.date(2020, 1, 1),
                currency="USD",
            ),
        ]

        # Check only commodity, not open
        config = "commodity\nexport"
        result_entries, errors = check_metadata.check_metadata(
            entries, {}, config)

        self.assertEqual(entries, result_entries)
        # Only commodity should be checked
        self.assertEqual(1, len(errors))
        self.assertIn("USD", errors[0].message)

    def test_deeply_nested_leaf_accounts(self):
        """Test deeply nested account hierarchy."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1
                },
                date=datetime.date(2020, 1, 1),
                account="Assets",
                currencies=[],
                booking=None,
            ),
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Bank",
                currencies=[],
                booking=None,
            ),
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 3
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Bank:Chase",
                currencies=[],
                booking=None,
            ),
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 4,
                    "region": "US"
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Bank:Chase:Checking",
                currencies=["USD"],
                booking=None,
            ),
        ]

        config = "open\nregion"
        result_entries, errors = check_metadata.check_metadata(
            entries, {}, config)

        self.assertEqual(entries, result_entries)
        # Only the deepest account is a leaf, and it has the metadata
        self.assertEqual([], errors)

    def test_account_filter_only_checks_matching_accounts(self):
        """Test that account filter only checks accounts under the specified hierarchy."""
        entries = [
            # Assets:Bank hierarchy
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Bank",
                currencies=[],
                booking=None,
            ),
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2,
                    "region": "US"
                },
                date=datetime.date(2020, 1, 2),
                account="Assets:Bank:Checking",
                currencies=["USD"],
                booking=None,
            ),
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 3
                },
                date=datetime.date(2020, 1, 3),
                account="Assets:Bank:Savings",
                currencies=["USD"],
                booking=None,
            ),
            # Assets:Crypto hierarchy - should not be checked
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 4
                },
                date=datetime.date(2020, 1, 4),
                account="Assets:Crypto:Wallet",
                currencies=["BTC"],
                booking=None,
            ),
        ]

        config = "open Assets:Bank\nregion"
        result_entries, errors = check_metadata.check_metadata(
            entries, {}, config)

        self.assertEqual(entries, result_entries)
        # Only Assets:Bank:Savings should have an error
        # Assets:Crypto:Wallet is outside the filter
        self.assertEqual(1, len(errors))
        self.assertIn("Assets:Bank:Savings", errors[0].message)

    def test_account_filter_with_exact_match(self):
        """Test that account filter works when the account exactly matches the filter."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1,
                    "region": "US"
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Cash",
                currencies=["USD"],
                booking=None,
            ),
        ]

        config = "open Assets:Cash\nregion"
        result_entries, errors = check_metadata.check_metadata(
            entries, {}, config)

        self.assertEqual(entries, result_entries)
        self.assertEqual([], errors)

    def test_account_filter_excludes_partial_matches(self):
        """Test that account filter doesn't match partial account names."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:BankAccount",
                currencies=[],
                booking=None,
            ),
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2
                },
                date=datetime.date(2020, 1, 2),
                account="Assets:BankAccount:Checking",
                currencies=["USD"],
                booking=None,
            ),
        ]

        # Filter is "Assets:Bank", should not match "Assets:BankAccount"
        config = "open Assets:Bank\nregion"
        result_entries, errors = check_metadata.check_metadata(
            entries, {}, config)

        self.assertEqual(entries, result_entries)
        # No errors because no accounts match the filter
        self.assertEqual([], errors)

    def test_account_filter_with_multiple_hierarchies(self):
        """Test account filter with complex account hierarchies."""
        entries = [
            # Assets:US:Bank hierarchy
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:US",
                currencies=[],
                booking=None,
            ),
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2
                },
                date=datetime.date(2020, 1, 2),
                account="Assets:US:Bank",
                currencies=[],
                booking=None,
            ),
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 3,
                    "region": "US"
                },
                date=datetime.date(2020, 1, 3),
                account="Assets:US:Bank:Checking",
                currencies=["USD"],
                booking=None,
            ),
            # Assets:JP:Bank hierarchy
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 4
                },
                date=datetime.date(2020, 1, 4),
                account="Assets:JP",
                currencies=[],
                booking=None,
            ),
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 5
                },
                date=datetime.date(2020, 1, 5),
                account="Assets:JP:Bank",
                currencies=[],
                booking=None,
            ),
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 6,
                    "region": "JP"
                },
                date=datetime.date(2020, 1, 6),
                account="Assets:JP:Bank:Checking",
                currencies=["JPY"],
                booking=None,
            ),
        ]

        # Filter only Assets:US:Bank
        config = "open Assets:US:Bank\nregion"
        result_entries, errors = check_metadata.check_metadata(
            entries, {}, config)

        self.assertEqual(entries, result_entries)
        # Only Assets:US:Bank:Checking should be checked (and it has region)
        # Assets:JP:Bank:Checking should not be checked
        self.assertEqual([], errors)

    def test_account_filter_backward_compatibility(self):
        """Test that omitting account filter checks all leaf accounts (backward compatible)."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Bank",
                currencies=[],
                booking=None,
            ),
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2,
                    "region": "US"
                },
                date=datetime.date(2020, 1, 2),
                account="Assets:Bank:Checking",
                currencies=["USD"],
                booking=None,
            ),
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 3
                },
                date=datetime.date(2020, 1, 3),
                account="Assets:Crypto:Wallet",
                currencies=["BTC"],
                booking=None,
            ),
        ]

        # No account filter - should check all leaf accounts
        config = "open\nregion"
        result_entries, errors = check_metadata.check_metadata(
            entries, {}, config)

        self.assertEqual(entries, result_entries)
        # Both leaf accounts should be checked
        self.assertEqual(1, len(errors))
        self.assertIn("Assets:Crypto:Wallet", errors[0].message)

    def test_account_filter_with_close_directive(self):
        """Test that account filter works with close directive."""
        entries = [
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 1
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Bank:Old",
                currencies=["USD"],
                booking=None,
            ),
            data.Close(
                meta={
                    "filename": "test.beancount",
                    "lineno": 2,
                    "reason": "closed"
                },
                date=datetime.date(2020, 12, 31),
                account="Assets:Bank:Old",
            ),
            data.Open(
                meta={
                    "filename": "test.beancount",
                    "lineno": 3
                },
                date=datetime.date(2020, 1, 1),
                account="Assets:Crypto:Old",
                currencies=["BTC"],
                booking=None,
            ),
            data.Close(
                meta={
                    "filename": "test.beancount",
                    "lineno": 4
                },
                date=datetime.date(2020, 12, 31),
                account="Assets:Crypto:Old",
            ),
        ]

        config = "close Assets:Bank\nreason"
        result_entries, errors = check_metadata.check_metadata(
            entries, {}, config)

        self.assertEqual(entries, result_entries)
        # Only Assets:Bank:Old should be checked (has reason)
        # Assets:Crypto:Old is outside filter
        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
