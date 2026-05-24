#!/usr/bin/env python3
"""Tests for leafonly plugin."""

import datetime
import unittest
from decimal import Decimal

from beancount.core import data
from beancount.core.amount import Amount

from beansprout.plugins import leafonly


class LeafOnlyTest(unittest.TestCase):
    """Test cases for leafonly plugin."""

    def setUp(self):
        """Set up test data."""
        self.maxDiff = None
        self.meta = {'filename': 'test.beancount', 'lineno': 1}
        self.date = datetime.date(2020, 1, 1)

    def test_leaf_account_with_transaction(self):
        """Test that leaf accounts with transactions are allowed."""
        parent_open = data.Open(meta=dict(self.meta),
                                date=self.date,
                                account='Expenses:Food',
                                currencies=None,
                                booking=None)

        leaf_open = data.Open(meta=dict(self.meta),
                              date=self.date,
                              account='Expenses:Food:Restaurant',
                              currencies=None,
                              booking=None)

        other_open = data.Open(meta=dict(self.meta),
                               date=self.date,
                               account='Assets:Cash',
                               currencies=None,
                               booking=None)

        transaction = data.Transaction(
            meta=self.meta,
            date=self.date,
            flag='*',
            payee='Restaurant',
            narration='Lunch',
            tags=frozenset(),
            links=frozenset(),
            postings=[
                data.Posting(account='Expenses:Food:Restaurant',
                             units=Amount(Decimal('10.00'), 'USD'),
                             cost=None,
                             price=None,
                             flag=None,
                             meta=None),
                data.Posting(account='Assets:Cash',
                             units=Amount(Decimal('-10.00'), 'USD'),
                             cost=None,
                             price=None,
                             flag=None,
                             meta=None),
            ])

        entries = [parent_open, leaf_open, other_open, transaction]
        _, errors = leafonly.validate_leaf_only(entries, {})

        self.assertEqual(len(errors), 0)

    def test_non_leaf_account_with_transaction(self):
        """Test that non-leaf accounts with transactions generate errors."""
        parent_open = data.Open(meta=dict(self.meta),
                                date=self.date,
                                account='Expenses:Food',
                                currencies=None,
                                booking=None)

        leaf_open = data.Open(meta=dict(self.meta),
                              date=self.date,
                              account='Expenses:Food:Restaurant',
                              currencies=None,
                              booking=None)

        other_open = data.Open(meta=dict(self.meta),
                               date=self.date,
                               account='Assets:Cash',
                               currencies=None,
                               booking=None)

        # Transaction posting to non-leaf account
        transaction = data.Transaction(
            meta=self.meta,
            date=self.date,
            flag='*',
            payee='Store',
            narration='Purchase',
            tags=frozenset(),
            links=frozenset(),
            postings=[
                data.Posting(account='Expenses:Food',
                             units=Amount(Decimal('15.00'), 'USD'),
                             cost=None,
                             price=None,
                             flag=None,
                             meta=None),
                data.Posting(account='Assets:Cash',
                             units=Amount(Decimal('-15.00'), 'USD'),
                             cost=None,
                             price=None,
                             flag=None,
                             meta=None),
            ])

        entries = [parent_open, leaf_open, other_open, transaction]
        _, errors = leafonly.validate_leaf_only(entries, {})

        self.assertEqual(len(errors), 1)
        self.assertIn('Expenses:Food', errors[0].message)

    def test_non_leaf_account_with_balance(self):
        """Test that non-leaf accounts with balance assertions are allowed."""
        parent_open = data.Open(meta=dict(self.meta),
                                date=self.date,
                                account='Assets:Bank',
                                currencies=None,
                                booking=None)

        leaf_open = data.Open(meta=dict(self.meta),
                              date=self.date,
                              account='Assets:Bank:Checking',
                              currencies=None,
                              booking=None)

        balance = data.Balance(meta=self.meta,
                               date=self.date,
                               account='Assets:Bank',
                               amount=Amount(Decimal('1000.00'), 'USD'),
                               tolerance=None,
                               diff_amount=None)

        entries = [parent_open, leaf_open, balance]
        _, errors = leafonly.validate_leaf_only(entries, {})

        self.assertEqual(len(errors), 0)

    def test_non_leaf_account_with_pad(self):
        """Test that non-leaf accounts with pad directives generate errors."""
        parent_open = data.Open(meta=dict(self.meta),
                                date=self.date,
                                account='Assets:Bank',
                                currencies=None,
                                booking=None)

        leaf_open = data.Open(meta=dict(self.meta),
                              date=self.date,
                              account='Assets:Bank:Checking',
                              currencies=None,
                              booking=None)

        equity_open = data.Open(meta=dict(self.meta),
                                date=self.date,
                                account='Equity:Opening',
                                currencies=None,
                                booking=None)

        pad = data.Pad(meta=self.meta,
                       date=self.date,
                       account='Assets:Bank',
                       source_account='Equity:Opening')

        entries = [parent_open, leaf_open, equity_open, pad]
        _, errors = leafonly.validate_leaf_only(entries, {})

        self.assertEqual(len(errors), 1)
        self.assertIn('Assets:Bank', errors[0].message)

    def test_leaf_account_with_pad(self):
        """Test that leaf accounts with pad directives are allowed."""
        leaf_open = data.Open(meta=dict(self.meta),
                              date=self.date,
                              account='Assets:Bank:Checking',
                              currencies=None,
                              booking=None)

        equity_open = data.Open(meta=dict(self.meta),
                                date=self.date,
                                account='Equity:Opening',
                                currencies=None,
                                booking=None)

        pad = data.Pad(meta=self.meta,
                       date=self.date,
                       account='Assets:Bank:Checking',
                       source_account='Equity:Opening')

        entries = [leaf_open, equity_open, pad]
        _, errors = leafonly.validate_leaf_only(entries, {})

        self.assertEqual(len(errors), 0)

    def test_non_leaf_account_with_note(self):
        """Test that non-leaf accounts with note directives are allowed."""
        parent_open = data.Open(meta=dict(self.meta),
                                date=self.date,
                                account='Assets:Bank',
                                currencies=None,
                                booking=None)

        leaf_open = data.Open(meta=dict(self.meta),
                              date=self.date,
                              account='Assets:Bank:Checking',
                              currencies=None,
                              booking=None)

        note = data.Note(meta=self.meta,
                         date=self.date,
                         account='Assets:Bank',
                         comment='This is a note',
                         tags=None,
                         links=None)

        entries = [parent_open, leaf_open, note]
        _, errors = leafonly.validate_leaf_only(entries, {})

        self.assertEqual(len(errors), 0)

    def test_account_without_open_directive(self):
        """Test that accounts without open directives are handled gracefully."""
        # No open directive for Expenses:Food
        leaf_open = data.Open(meta=dict(self.meta),
                              date=self.date,
                              account='Expenses:Food:Restaurant',
                              currencies=None,
                              booking=None)

        other_open = data.Open(meta=dict(self.meta),
                               date=self.date,
                               account='Assets:Cash',
                               currencies=None,
                               booking=None)

        # Transaction posting to non-leaf account without Open directive
        transaction = data.Transaction(
            meta=self.meta,
            date=self.date,
            flag='*',
            payee='Store',
            narration='Purchase',
            tags=frozenset(),
            links=frozenset(),
            postings=[
                data.Posting(account='Expenses:Food',
                             units=Amount(Decimal('20.00'), 'USD'),
                             cost=None,
                             price=None,
                             flag=None,
                             meta=None),
                data.Posting(account='Assets:Cash',
                             units=Amount(Decimal('-20.00'), 'USD'),
                             cost=None,
                             price=None,
                             flag=None,
                             meta=None),
            ])

        entries = [leaf_open, other_open, transaction]
        _, errors = leafonly.validate_leaf_only(entries, {})

        # Should still report error even without Open directive
        self.assertEqual(len(errors), 1)
        self.assertIn('Expenses:Food', errors[0].message)

    def test_multiple_non_leaf_violations(self):
        """Test multiple non-leaf accounts with violations."""
        # Two parent accounts
        food_open = data.Open(meta=dict(self.meta),
                              date=self.date,
                              account='Expenses:Food',
                              currencies=None,
                              booking=None)

        food_leaf_open = data.Open(meta=dict(self.meta),
                                   date=self.date,
                                   account='Expenses:Food:Restaurant',
                                   currencies=None,
                                   booking=None)

        bank_open = data.Open(meta=dict(self.meta),
                              date=self.date,
                              account='Assets:Bank',
                              currencies=None,
                              booking=None)

        bank_leaf_open = data.Open(meta=dict(self.meta),
                                   date=self.date,
                                   account='Assets:Bank:Checking',
                                   currencies=None,
                                   booking=None)

        cash_open = data.Open(meta=dict(self.meta),
                              date=self.date,
                              account='Assets:Cash',
                              currencies=None,
                              booking=None)

        equity_open = data.Open(meta=dict(self.meta),
                                date=self.date,
                                account='Equity:Opening',
                                currencies=None,
                                booking=None)

        # Transaction on Expenses:Food (non-leaf)
        transaction = data.Transaction(
            meta=self.meta,
            date=self.date,
            flag='*',
            payee='Store',
            narration='Purchase',
            tags=frozenset(),
            links=frozenset(),
            postings=[
                data.Posting(account='Expenses:Food',
                             units=Amount(Decimal('25.00'), 'USD'),
                             cost=None,
                             price=None,
                             flag=None,
                             meta=None),
                data.Posting(account='Assets:Cash',
                             units=Amount(Decimal('-25.00'), 'USD'),
                             cost=None,
                             price=None,
                             flag=None,
                             meta=None),
            ])

        # Pad on Assets:Bank (non-leaf)
        pad = data.Pad(meta=self.meta,
                       date=self.date,
                       account='Assets:Bank',
                       source_account='Equity:Opening')

        entries = [
            food_open, food_leaf_open, bank_open, bank_leaf_open, cash_open,
            equity_open, transaction, pad
        ]
        _, errors = leafonly.validate_leaf_only(entries, {})

        self.assertEqual(len(errors), 2)
        error_messages = [error.message for error in errors]
        self.assertTrue(any('Expenses:Food' in msg for msg in error_messages))
        self.assertTrue(any('Assets:Bank' in msg for msg in error_messages))

    def test_complex_hierarchy(self):
        """Test complex account hierarchy with multiple levels."""
        # Root level
        assets_open = data.Open(meta=dict(self.meta),
                                date=self.date,
                                account='Assets',
                                currencies=None,
                                booking=None)

        # Level 1
        bank_open = data.Open(meta=dict(self.meta),
                              date=self.date,
                              account='Assets:Bank',
                              currencies=None,
                              booking=None)

        # Level 2
        checking_open = data.Open(meta=dict(self.meta),
                                  date=self.date,
                                  account='Assets:Bank:Checking',
                                  currencies=None,
                                  booking=None)

        # Level 3 (leaf)
        sub_checking_open = data.Open(
            meta=dict(self.meta),
            date=self.date,
            account='Assets:Bank:Checking:SubAccount',
            currencies=None,
            booking=None)

        cash_open = data.Open(meta=dict(self.meta),
                              date=self.date,
                              account='Assets:Cash',
                              currencies=None,
                              booking=None)

        # Transaction on level 2 (non-leaf)
        transaction = data.Transaction(
            meta=self.meta,
            date=self.date,
            flag='*',
            payee='Bank',
            narration='Fee',
            tags=frozenset(),
            links=frozenset(),
            postings=[
                data.Posting(account='Assets:Bank:Checking',
                             units=Amount(Decimal('-5.00'), 'USD'),
                             cost=None,
                             price=None,
                             flag=None,
                             meta=None),
                data.Posting(account='Assets:Cash',
                             units=Amount(Decimal('5.00'), 'USD'),
                             cost=None,
                             price=None,
                             flag=None,
                             meta=None),
            ])

        entries = [
            assets_open, bank_open, checking_open, sub_checking_open,
            cash_open, transaction
        ]
        _, errors = leafonly.validate_leaf_only(entries, {})

        # Assets:Bank:Checking is non-leaf (has SubAccount child)
        self.assertEqual(len(errors), 1)
        self.assertIn('Assets:Bank:Checking', errors[0].message)


if __name__ == '__main__':
    unittest.main()
