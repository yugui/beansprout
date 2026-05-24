#!/usr/bin/env python3
"""Tests for trading_validation plugin."""

import datetime
import unittest
from decimal import Decimal

from beancount.core import data
from beancount.core.amount import Amount
from beancount.ops.validation import ValidationError

from beansprout.plugins import trading_validation


class TradingValidationTest(unittest.TestCase):
    """Test cases for trading_validation plugin."""

    def setUp(self):
        """Set up test data."""
        self.maxDiff = None

        # Create test metadata
        self.meta = {'filename': 'test.beancount', 'lineno': 1}
        self.date = datetime.date(2023, 1, 15)

        # Default options map with required Beancount options
        self.options_map = {
            'infer_tolerance_from_cost': True,
            'inferred_tolerance_multiplier': 0.5,
            'inferred_tolerance_default': {},
        }

    def test_extract_commodity_mapping(self):
        """Test extraction of commodity trading-account metadata."""
        entries = [
            data.Commodity(meta=dict(self.meta,
                                     **{'trading-account': 'disabled'}),
                           date=self.date,
                           currency='DISABLED_STOCK'),
            data.Commodity(meta=self.meta,
                           date=self.date,
                           currency='NORMAL_STOCK'),
        ]

        mapping = trading_validation._extract_commodity_mapping(entries)

        expected_mapping = {
            'DISABLED_STOCK': 'disabled',
        }

        self.assertEqual(mapping, expected_mapping)

    def test_has_trading_accounts(self):
        """Test detection of trading accounts in transactions."""
        # Transaction with trading accounts
        postings_with_trading = [
            data.Posting('Assets:Cash', Amount(Decimal('-100'), 'USD'), None,
                         None, None, None),
            data.Posting('Equity:Trading:TEST', Amount(Decimal('100'), 'USD'),
                         None, None, None, None),
        ]

        txn_with_trading = data.Transaction(meta=self.meta,
                                            date=self.date,
                                            flag='*',
                                            payee=None,
                                            narration='With trading',
                                            tags=frozenset(),
                                            links=frozenset(),
                                            postings=postings_with_trading)

        self.assertTrue(
            trading_validation._has_trading_accounts(txn_with_trading,
                                                     'Equity:Trading'))

        # Transaction without trading accounts
        postings_without_trading = [
            data.Posting('Assets:Cash', Amount(Decimal('-100'), 'USD'), None,
                         None, None, None),
            data.Posting('Expenses:Food', Amount(Decimal('100'), 'USD'), None,
                         None, None, None),
        ]

        txn_without_trading = data.Transaction(
            meta=self.meta,
            date=self.date,
            flag='*',
            payee=None,
            narration='Without trading',
            tags=frozenset(),
            links=frozenset(),
            postings=postings_without_trading)

        self.assertFalse(
            trading_validation._has_trading_accounts(txn_without_trading,
                                                     'Equity:Trading'))

    def test_is_trading_account(self):
        """Test trading account detection."""
        self.assertTrue(
            trading_validation._is_trading_account('Equity:Trading:STOCK-USD',
                                                   'Equity:Trading'))
        self.assertTrue(
            trading_validation._is_trading_account('Equity:Trading',
                                                   'Equity:Trading'))
        self.assertFalse(
            trading_validation._is_trading_account('Assets:Cash',
                                                   'Equity:Trading'))
        self.assertFalse(
            trading_validation._is_trading_account('Equity:OpeningBalances',
                                                   'Equity:Trading'))

    def test_extract_effective_commodities_normal(self):
        """Test commodity extraction for normal commodities."""
        postings = [
            data.Posting('Assets:Cash', Amount(Decimal('-100'), 'USD'), None,
                         None, None, None),
            data.Posting('Assets:Securities', Amount(Decimal('1'), 'STOCK'),
                         None, None, None, None),
        ]

        txn = data.Transaction(meta=self.meta,
                               date=self.date,
                               flag='*',
                               payee=None,
                               narration='Test',
                               tags=frozenset(),
                               links=frozenset(),
                               postings=postings)

        commodities = trading_validation._extract_effective_commodities(
            txn, {})

        self.assertEqual(commodities, {'USD', 'STOCK'})

    def test_extract_effective_commodities_disabled(self):
        """Test commodity extraction for disabled trading-account commodities."""
        postings = [
            data.Posting('Assets:Securities',
                         Amount(Decimal('1'), 'DISABLED_STOCK'), None,
                         Amount(Decimal('100'), 'USD'), None, None),
            data.Posting('Assets:Cash', Amount(Decimal('-100'), 'USD'), None,
                         None, None, None),
        ]

        txn = data.Transaction(meta=self.meta,
                               date=self.date,
                               flag='*',
                               payee=None,
                               narration='Test',
                               tags=frozenset(),
                               links=frozenset(),
                               postings=postings)

        commodity_mapping = {'DISABLED_STOCK': 'disabled'}
        commodities = trading_validation._extract_effective_commodities(
            txn, commodity_mapping)

        # DISABLED_STOCK should be grouped by its price currency (USD)
        self.assertEqual(commodities, {'USD'})

    def test_extract_effective_commodities_disabled_no_price(self):
        """Test commodity extraction for disabled commodities without price."""
        postings = [
            data.Posting(
                'Assets:Securities',
                Amount(Decimal('1'), 'DISABLED_STOCK'),
                None,
                None,
                None,
                None  # No price
            ),
            data.Posting('Assets:Cash', Amount(Decimal('-100'), 'USD'), None,
                         None, None, None),
        ]

        txn = data.Transaction(meta=self.meta,
                               date=self.date,
                               flag='*',
                               payee=None,
                               narration='Test',
                               tags=frozenset(),
                               links=frozenset(),
                               postings=postings)

        commodity_mapping = {'DISABLED_STOCK': 'disabled'}
        commodities = trading_validation._extract_effective_commodities(
            txn, commodity_mapping)

        # DISABLED_STOCK without price should be skipped, only USD remains
        self.assertEqual(commodities, {'USD'})

    def test_get_postings_for_commodity_normal(self):
        """Test posting extraction for normal commodities."""
        postings = [
            data.Posting('Assets:Cash', Amount(Decimal('-100'), 'USD'), None,
                         None, None, None),
            data.Posting('Assets:Securities', Amount(Decimal('1'), 'STOCK'),
                         None, None, None, None),
            data.Posting('Assets:More', Amount(Decimal('-50'), 'USD'), None,
                         None, None, None),
        ]

        txn = data.Transaction(meta=self.meta,
                               date=self.date,
                               flag='*',
                               payee=None,
                               narration='Test',
                               tags=frozenset(),
                               links=frozenset(),
                               postings=postings)

        usd_postings = trading_validation._get_postings_for_commodity(
            txn, 'USD', {})
        stock_postings = trading_validation._get_postings_for_commodity(
            txn, 'STOCK', {})

        self.assertEqual(len(usd_postings), 2)  # First and third postings
        self.assertEqual(len(stock_postings), 1)  # Second posting
        self.assertEqual(usd_postings[0].account, 'Assets:Cash')
        self.assertEqual(usd_postings[1].account, 'Assets:More')
        self.assertEqual(stock_postings[0].account, 'Assets:Securities')

    def test_get_postings_for_commodity_disabled(self):
        """Test posting extraction for disabled trading-account commodities."""
        postings = [
            data.Posting('Assets:Securities',
                         Amount(Decimal('1'), 'DISABLED_STOCK'), None,
                         Amount(Decimal('100'), 'USD'), None, None),
            data.Posting('Assets:Cash', Amount(Decimal('-100'), 'USD'), None,
                         None, None, None),
        ]

        txn = data.Transaction(meta=self.meta,
                               date=self.date,
                               flag='*',
                               payee=None,
                               narration='Test',
                               tags=frozenset(),
                               links=frozenset(),
                               postings=postings)

        commodity_mapping = {'DISABLED_STOCK': 'disabled'}

        # For disabled commodity, group by price currency (USD)
        usd_postings = trading_validation._get_postings_for_commodity(
            txn, 'USD', commodity_mapping)

        # Should include both postings: one with USD units, one with USD price
        self.assertEqual(len(usd_postings), 2)

    def test_validate_balanced_trading_transaction(self):
        """Test validation of a properly balanced trading transaction."""
        postings = [
            # Security purchase
            data.Posting('Assets:Securities', Amount(Decimal('1'), 'STOCK'),
                         None, Amount(Decimal('100'), 'USD'), None, None),
            data.Posting('Assets:Cash', Amount(Decimal('-100'), 'USD'), None,
                         None, None, None),

            # Trading accounts to balance the conversion
            data.Posting('Equity:Trading:STOCK-USD',
                         Amount(Decimal('-1'), 'STOCK'), None,
                         Amount(Decimal('100'), 'USD'), None, None),
            data.Posting('Equity:Trading:STOCK-USD',
                         Amount(Decimal('100'), 'USD'), None, None, None,
                         None),
        ]

        txn = data.Transaction(meta=self.meta,
                               date=self.date,
                               flag='*',
                               payee=None,
                               narration='Stock purchase',
                               tags=frozenset(),
                               links=frozenset(),
                               postings=postings)

        entries = [txn]
        transformed_entries, errors = trading_validation.trading_validation(
            entries, self.options_map)

        # Should have no validation errors
        self.assertEqual(len(errors), 0)
        self.assertEqual(transformed_entries, entries)

    def test_validate_unbalanced_trading_accounts(self):
        """Test validation detects unbalanced trading accounts."""
        postings = [
            data.Posting('Assets:Cash', Amount(Decimal('-100'), 'USD'), None,
                         None, None, None),
            data.Posting('Assets:Securities', Amount(Decimal('1'), 'STOCK'),
                         None, None, None, None),

            # Unbalanced trading accounts (missing offsetting entry)
            data.Posting('Equity:Trading:STOCK-USD',
                         Amount(Decimal('-1'), 'STOCK'), None, None, None,
                         None),
            # Missing: Equity:Trading:STOCK-USD 100 USD
        ]

        txn = data.Transaction(meta=self.meta,
                               date=self.date,
                               flag='*',
                               payee=None,
                               narration='Unbalanced trading',
                               tags=frozenset(),
                               links=frozenset(),
                               postings=postings)

        entries = [txn]
        transformed_entries, errors = trading_validation.trading_validation(
            entries, self.options_map)

        # Should detect trading accounts don't balance
        self.assertGreater(len(errors), 0)
        self.assertTrue(
            any("Transaction does not balance" in str(error.message)
                for error in errors))

    def test_validate_unbalanced_non_trading_accounts(self):
        """Test validation detects unbalanced non-trading accounts."""
        postings = [
            # Unbalanced non-trading accounts
            data.Posting('Assets:Cash', Amount(Decimal('-50'), 'USD'), None,
                         None, None, None),  # Should be -100
            data.Posting('Assets:Securities', Amount(Decimal('1'), 'STOCK'),
                         None, None, None, None),

            # Balanced trading accounts
            data.Posting('Equity:Trading:STOCK-USD',
                         Amount(Decimal('-1'), 'STOCK'), None, None, None,
                         None),
            data.Posting('Equity:Trading:STOCK-USD',
                         Amount(Decimal('100'), 'USD'), None, None, None,
                         None),
        ]

        txn = data.Transaction(meta=self.meta,
                               date=self.date,
                               flag='*',
                               payee=None,
                               narration='Unbalanced non-trading',
                               tags=frozenset(),
                               links=frozenset(),
                               postings=postings)

        entries = [txn]
        transformed_entries, errors = trading_validation.trading_validation(
            entries, self.options_map)

        # Should detect non-trading accounts don't balance
        self.assertGreater(len(errors), 0)
        self.assertTrue(
            any("Transaction does not balance" in str(error.message)
                for error in errors))

    def test_validate_transaction_without_trading_accounts(self):
        """Test that transactions without trading accounts are not validated."""
        postings = [
            data.Posting('Assets:Cash', Amount(Decimal('-100'), 'USD'), None,
                         None, None, None),
            data.Posting('Expenses:Food', Amount(Decimal('100'), 'USD'), None,
                         None, None, None),
        ]

        txn = data.Transaction(meta=self.meta,
                               date=self.date,
                               flag='*',
                               payee=None,
                               narration='Regular transaction',
                               tags=frozenset(),
                               links=frozenset(),
                               postings=postings)

        entries = [txn]
        transformed_entries, errors = trading_validation.trading_validation(
            entries, self.options_map)

        # Should have no validation errors (transaction is ignored)
        self.assertEqual(len(errors), 0)
        self.assertEqual(transformed_entries, entries)

    def test_custom_trading_prefix(self):
        """Test using custom trading account prefix."""
        postings = [
            data.Posting('Assets:Cash', Amount(Decimal('-100'), 'USD'), None,
                         None, None, None),
            data.Posting('Assets:Trading:CUSTOM',
                         Amount(Decimal('100'),
                                'USD'), None, None, None, None),
        ]

        txn = data.Transaction(meta=self.meta,
                               date=self.date,
                               flag='*',
                               payee=None,
                               narration='Custom prefix',
                               tags=frozenset(),
                               links=frozenset(),
                               postings=postings)

        entries = [txn]
        # Use custom trading prefix - this should detect validation errors
        # because we have both trading and non-trading accounts that are unbalanced separately
        transformed_entries, errors = trading_validation.trading_validation(
            entries, self.options_map, "Assets:Trading")

        # Should detect errors with custom prefix (both trading-only and non-trading-only are unbalanced)
        self.assertGreater(len(errors), 0)

        # Should not validate with default prefix (so transaction is ignored)
        transformed_entries2, errors2 = trading_validation.trading_validation(
            entries, self.options_map, "Equity:Trading")
        self.assertEqual(len(errors2), 0)  # Ignored, so no errors

    def test_disabled_commodity_validation(self):
        """Test validation with disabled trading-account commodity."""
        # Create commodity with disabled trading-account
        commodity = data.Commodity(meta=dict(self.meta,
                                             **{'trading-account':
                                                'disabled'}),
                                   date=self.date,
                                   currency='DISABLED_STOCK')

        postings = [
            # This should be grouped by USD (price currency)
            data.Posting('Assets:Securities',
                         Amount(Decimal('1'), 'DISABLED_STOCK'), None,
                         Amount(Decimal('100'), 'USD'), None, None),
            data.Posting('Assets:Cash', Amount(Decimal('-100'), 'USD'), None,
                         None, None, None),
        ]

        txn = data.Transaction(meta=self.meta,
                               date=self.date,
                               flag='*',
                               payee=None,
                               narration='Disabled commodity',
                               tags=frozenset(),
                               links=frozenset(),
                               postings=postings)

        entries = [commodity, txn]
        transformed_entries, errors = trading_validation.trading_validation(
            entries, self.options_map)

        # Should balance properly when grouped by USD
        self.assertEqual(len(errors), 0)

    def test_error_types(self):
        """Test that errors are of correct type."""
        postings = [
            data.Posting('Assets:Cash', Amount(Decimal('-50'), 'USD'), None,
                         None, None, None),  # Unbalanced
            data.Posting('Equity:Trading:TEST', Amount(Decimal('100'), 'USD'),
                         None, None, None, None),
        ]

        txn = data.Transaction(meta=self.meta,
                               date=self.date,
                               flag='*',
                               payee=None,
                               narration='Error test',
                               tags=frozenset(),
                               links=frozenset(),
                               postings=postings)

        entries = [txn]
        transformed_entries, errors = trading_validation.trading_validation(
            entries, self.options_map)

        # Should have errors of ValidationError type
        self.assertGreater(len(errors), 0)
        for error in errors:
            self.assertIsInstance(error, ValidationError)
            self.assertIn('filename', error.source)
            self.assertIn('lineno', error.source)
            self.assertIsInstance(error.message, str)


if __name__ == '__main__':
    unittest.main()
