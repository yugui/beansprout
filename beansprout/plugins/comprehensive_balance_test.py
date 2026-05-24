#!/usr/bin/env python3
"""Tests for comprehensive_balance plugin."""

import datetime
import unittest
from decimal import Decimal

from beancount.core import account, data
from beancount.ops.validation import ValidationError
from beancount.parser.grammar import ValueType
from beansprout.plugins import comprehensive_balance


class TestComprehensiveBalance(unittest.TestCase):
    """Test cases for comprehensive_balance plugin."""

    def setUp(self):
        """Set up test fixtures."""
        self.meta = {'filename': 'test.beancount', 'lineno': 1}
        self.date = datetime.date(2024, 1, 1)
        self.options_map = {'operating_currency': ['USD']}

        # Create basic account structure for testing
        self.base_entries = [
            data.Open(meta=self.meta,
                      date=datetime.date(2023, 1, 1),
                      account='Assets:Checking',
                      currencies=['USD', 'EUR'],
                      booking=None),
            data.Open(meta=self.meta,
                      date=datetime.date(2023, 1, 1),
                      account='Expenses:Coffee',
                      currencies=['USD'],
                      booking=None),
        ]

    def test_simple_valid_balance(self):
        """Test a simple valid comprehensive_balance directive."""
        entries = self.base_entries + [
            # Add some transactions to create balances
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 12, 31),
                flag='*',
                payee=None,
                narration='Initial balance',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('1000'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-1000'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Comprehensive balance directive
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType('1000.00 USD', str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        # Should have no errors
        self.assertEqual(len(errors), 0)

        # Should have replaced custom directive with Balance directive
        balance_directives = [
            e for e in new_entries if isinstance(e, data.Balance)
        ]
        self.assertEqual(len(balance_directives), 1)

        balance = balance_directives[0]
        self.assertEqual(balance.account, 'Assets:Checking')
        self.assertEqual(balance.amount.number, Decimal('1000.00'))
        self.assertEqual(balance.amount.currency, 'USD')
        self.assertEqual(balance.date, self.date)

        # Should not contain the custom directive
        custom_directives = [
            e for e in new_entries if isinstance(e, data.Custom)
        ]
        self.assertEqual(len(custom_directives), 0)

    def test_multiple_currencies(self):
        """Test comprehensive_balance with multiple currencies."""
        entries = self.base_entries + [
            # Add multi-currency transaction
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 12, 31),
                flag='*',
                payee=None,
                narration='Multi-currency balance',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('1000'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('500'), 'EUR'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-1000'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-500'), 'EUR'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Comprehensive balance directive with both currencies
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType(
                                """
                    1000.00 USD
                    500.00 EUR  ; European holdings
                """, str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        # Should have no errors
        self.assertEqual(len(errors), 0)

        # Should have two Balance directives
        balance_directives = [
            e for e in new_entries if isinstance(e, data.Balance)
        ]
        self.assertEqual(len(balance_directives), 2)

        # Check USD balance
        usd_balance = next(b for b in balance_directives
                           if b.amount.currency == 'USD')
        self.assertEqual(usd_balance.amount.number, Decimal('1000.00'))

        # Check EUR balance
        eur_balance = next(b for b in balance_directives
                           if b.amount.currency == 'EUR')
        self.assertEqual(eur_balance.amount.number, Decimal('500.00'))

    def test_unlisted_commodity_zero_balance(self):
        """Test zero-balance assertion generated for unlisted commodity with non-zero balance."""
        entries = self.base_entries + [
            # Add transaction with unlisted commodity
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 12, 31),
                flag='*',
                payee=None,
                narration='Unlisted commodity',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('1000'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(
                        account='Assets:Checking',
                        units=data.Amount(Decimal('100'), 'JPY'),  # Unlisted
                        cost=None,
                        price=None,
                        flag=None,
                        meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-1000'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-100'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Comprehensive balance directive missing JPY
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType('1000.00 USD', str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        # Should have no errors (zero-balance assertion generated instead)
        self.assertEqual(len(errors), 0)

        # Should have two Balance directives: one for USD and one zero-balance for JPY
        balance_directives = [
            e for e in new_entries if isinstance(e, data.Balance)
        ]
        self.assertEqual(len(balance_directives), 2)

        # Check USD balance (declared)
        usd_balance = next(b for b in balance_directives
                           if b.amount.currency == 'USD')
        self.assertEqual(usd_balance.amount.number, Decimal('1000.00'))

        # Check JPY zero-balance assertion (generated for unlisted commodity)
        jpy_balance = next(b for b in balance_directives
                           if b.amount.currency == 'JPY')
        self.assertEqual(jpy_balance.amount.number, Decimal('0'))
        self.assertEqual(jpy_balance.account, 'Assets:Checking')

    def test_zero_balance_ignored(self):
        """Test that commodities with zero balance are ignored."""
        entries = self.base_entries + [
            # Add transaction that results in zero balance for some commodity
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 12, 31),
                flag='*',
                payee=None,
                narration='Zero balance test',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('1000'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('100'), 'EUR'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(
                        account='Assets:Checking',
                        units=data.Amount(Decimal('-100'),
                                          'EUR'),  # Net zero EUR
                        cost=None,
                        price=None,
                        flag=None,
                        meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-1000'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Comprehensive balance directive only declares USD (EUR has zero balance)
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType('1000.00 USD', str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        # Should have no errors (zero EUR balance should be ignored)
        self.assertEqual(len(errors), 0)

    def test_invalid_directive_parameters(self):
        """Test error handling for invalid directive parameters."""
        # Test wrong number of parameters
        invalid_entry = data.Custom(
            meta=self.meta,
            date=self.date,
            type='comprehensive_balance',
            values=[ValueType('Assets:Checking',
                              account.TYPE)]  # Missing second parameter
        )

        entries = self.base_entries + [invalid_entry]
        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        self.assertEqual(len(errors), 1)
        self.assertIn('exactly 2 parameters', str(errors[0]))

    def test_invalid_balance_format(self):
        """Test error handling for invalid balance assertion format."""
        entries = self.base_entries + [
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType('invalid format', str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        self.assertEqual(len(errors), 1)
        self.assertIn('Invalid balance assertion format', str(errors[0]))

    def test_nonexistent_account(self):
        """Test error handling for nonexistent account."""
        entries = self.base_entries + [
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:NonExistent', account.TYPE),
                            ValueType('1000.00 USD', str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        self.assertEqual(len(errors), 1)
        self.assertIn('not found', str(errors[0]))

    def test_duplicate_commodity(self):
        """Test error handling for duplicate commodity in assertions."""
        entries = self.base_entries + [
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType(
                                """
                    1000.00 USD
                    500.00 USD  ; Duplicate USD
                """, str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        self.assertEqual(len(errors), 1)
        self.assertIn('Duplicate commodity', str(errors[0]))

    def test_empty_lines_and_comments(self):
        """Test that empty lines and comments are properly ignored."""
        entries = self.base_entries + [
            # Add transaction
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 12, 31),
                flag='*',
                payee=None,
                narration='Test balance',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('1000'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-1000'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Comprehensive balance with empty lines and comments
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType(
                                """
                    ; This is a comment
                    
                    1000.00 USD  ; Balance assertion
                    
                    ; Another comment
                """, str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        # Should have no errors
        self.assertEqual(len(errors), 0)

        # Should have one balance directive
        balance_directives = [
            e for e in new_entries if isinstance(e, data.Balance)
        ]
        self.assertEqual(len(balance_directives), 1)
        self.assertEqual(balance_directives[0].amount.number,
                         Decimal('1000.00'))

    def test_negative_amounts(self):
        """Test handling of negative amounts in assertions."""
        entries = self.base_entries + [
            # Add transaction with negative balance
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 12, 31),
                flag='*',
                payee=None,
                narration='Negative balance',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('-500'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('500'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Comprehensive balance with negative amount
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType('-500.00 USD', str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        # Should have no errors
        self.assertEqual(len(errors), 0)

        # Should have one balance directive with negative amount
        balance_directives = [
            e for e in new_entries if isinstance(e, data.Balance)
        ]
        self.assertEqual(len(balance_directives), 1)
        self.assertEqual(balance_directives[0].amount.number,
                         Decimal('-500.00'))

    def test_multiple_unlisted_commodities(self):
        """Test zero-balance assertions for multiple unlisted commodities."""
        entries = self.base_entries + [
            # Add transaction with multiple unlisted commodities
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 12, 31),
                flag='*',
                payee=None,
                narration='Multiple unlisted commodities',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('1000'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('100'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('50'), 'GBP'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-1000'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-100'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-50'), 'GBP'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Comprehensive balance directive only declares USD
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType('1000.00 USD', str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        # Should have no errors
        self.assertEqual(len(errors), 0)

        # Should have three Balance directives: USD (declared), JPY and GBP (zero-balance)
        balance_directives = [
            e for e in new_entries if isinstance(e, data.Balance)
        ]
        self.assertEqual(len(balance_directives), 3)

        # Check USD balance (declared)
        usd_balance = next(b for b in balance_directives
                           if b.amount.currency == 'USD')
        self.assertEqual(usd_balance.amount.number, Decimal('1000.00'))

        # Check JPY zero-balance assertion
        jpy_balance = next(b for b in balance_directives
                           if b.amount.currency == 'JPY')
        self.assertEqual(jpy_balance.amount.number, Decimal('0'))

        # Check GBP zero-balance assertion
        gbp_balance = next(b for b in balance_directives
                           if b.amount.currency == 'GBP')
        self.assertEqual(gbp_balance.amount.number, Decimal('0'))

    def test_arithmetic_addition(self):
        """Test arithmetic addition expression in balance assertion."""
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 12, 31),
                flag='*',
                payee=None,
                narration='Test balance',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('150'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-150'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType('100 + 50 USD', str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)
        balance_directives = [
            e for e in new_entries if isinstance(e, data.Balance)
        ]
        self.assertEqual(len(balance_directives), 1)
        self.assertEqual(balance_directives[0].amount.number, Decimal('150'))

    def test_arithmetic_subtraction(self):
        """Test arithmetic subtraction expression in balance assertion."""
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 12, 31),
                flag='*',
                payee=None,
                narration='Test balance',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('50'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-50'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType('100 - 50 USD', str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)
        balance_directives = [
            e for e in new_entries if isinstance(e, data.Balance)
        ]
        self.assertEqual(len(balance_directives), 1)
        self.assertEqual(balance_directives[0].amount.number, Decimal('50'))

    def test_arithmetic_multiplication(self):
        """Test arithmetic multiplication expression in balance assertion."""
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 12, 31),
                flag='*',
                payee=None,
                narration='Test balance',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('200'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-200'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType('10 * 20 USD', str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)
        balance_directives = [
            e for e in new_entries if isinstance(e, data.Balance)
        ]
        self.assertEqual(len(balance_directives), 1)
        self.assertEqual(balance_directives[0].amount.number, Decimal('200'))

    def test_arithmetic_division(self):
        """Test arithmetic division expression in balance assertion."""
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 12, 31),
                flag='*',
                payee=None,
                narration='Test balance',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('25'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-25'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType('100 / 4 USD', str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)
        balance_directives = [
            e for e in new_entries if isinstance(e, data.Balance)
        ]
        self.assertEqual(len(balance_directives), 1)
        self.assertEqual(balance_directives[0].amount.number, Decimal('25'))

    def test_arithmetic_complex_expression(self):
        """Test complex arithmetic expression with parentheses."""
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 12, 31),
                flag='*',
                payee=None,
                narration='Test balance',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('400'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-400'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # (1000 - 200) * 2 / 4 = 800 / 4 = 200... wait let me recalculate
            # (1000 - 200) = 800, 800 * 2 = 1600, 1600 / 4 = 400
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType('(1000 - 200) * 2 / 4 USD', str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)
        balance_directives = [
            e for e in new_entries if isinstance(e, data.Balance)
        ]
        self.assertEqual(len(balance_directives), 1)
        self.assertEqual(balance_directives[0].amount.number, Decimal('400'))

    def test_arithmetic_operator_precedence(self):
        """Test that operator precedence is handled correctly."""
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 12, 31),
                flag='*',
                payee=None,
                narration='Test balance',
                tags=set(),
                links=set(),
                postings=[
                    # 2 + 3 * 4 = 2 + 12 = 14 (multiplication before addition)
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('14'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-14'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType('2 + 3 * 4 USD', str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)
        balance_directives = [
            e for e in new_entries if isinstance(e, data.Balance)
        ]
        self.assertEqual(len(balance_directives), 1)
        self.assertEqual(balance_directives[0].amount.number, Decimal('14'))

    def test_arithmetic_unary_negative(self):
        """Test unary negative operator in expression."""
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 12, 31),
                flag='*',
                payee=None,
                narration='Test balance',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('-100'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('100'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType('-100 USD', str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)
        balance_directives = [
            e for e in new_entries if isinstance(e, data.Balance)
        ]
        self.assertEqual(len(balance_directives), 1)
        self.assertEqual(balance_directives[0].amount.number, Decimal('-100'))

    def test_arithmetic_expression_result_negative(self):
        """Test expression that evaluates to negative result."""
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 12, 31),
                flag='*',
                payee=None,
                narration='Test balance',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('-100'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('100'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType('100 - 200 USD', str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)
        balance_directives = [
            e for e in new_entries if isinstance(e, data.Balance)
        ]
        self.assertEqual(len(balance_directives), 1)
        self.assertEqual(balance_directives[0].amount.number, Decimal('-100'))

    def test_arithmetic_comma_formatted_numbers(self):
        """Test comma-formatted numbers in expressions."""
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 12, 31),
                flag='*',
                payee=None,
                narration='Test balance',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('1234.56'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-1234.56'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType('1,234.56 USD', str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)
        balance_directives = [
            e for e in new_entries if isinstance(e, data.Balance)
        ]
        self.assertEqual(len(balance_directives), 1)
        self.assertEqual(balance_directives[0].amount.number,
                         Decimal('1234.56'))

    def test_arithmetic_comma_in_expression(self):
        """Test comma-formatted numbers combined with arithmetic."""
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 12, 31),
                flag='*',
                payee=None,
                narration='Test balance',
                tags=set(),
                links=set(),
                postings=[
                    # 1,000 + 234 = 1234
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('1234'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-1234'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType('1,000 + 234 USD', str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)
        balance_directives = [
            e for e in new_entries if isinstance(e, data.Balance)
        ]
        self.assertEqual(len(balance_directives), 1)
        self.assertEqual(balance_directives[0].amount.number, Decimal('1234'))

    def test_arithmetic_multiple_currencies_with_expressions(self):
        """Test expressions with multiple currencies in one directive."""
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 12, 31),
                flag='*',
                payee=None,
                narration='Test balance',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('150'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('300'), 'EUR'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-150'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-300'), 'EUR'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType(
                                """
                    100 + 50 USD
                    200 + 100 EUR
                """, str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)
        balance_directives = [
            e for e in new_entries if isinstance(e, data.Balance)
        ]
        self.assertEqual(len(balance_directives), 2)

        usd_balance = next(b for b in balance_directives
                           if b.amount.currency == 'USD')
        self.assertEqual(usd_balance.amount.number, Decimal('150'))

        eur_balance = next(b for b in balance_directives
                           if b.amount.currency == 'EUR')
        self.assertEqual(eur_balance.amount.number, Decimal('300'))

    def test_arithmetic_invalid_expression(self):
        """Test error handling for invalid arithmetic expression."""
        entries = self.base_entries + [
            data.Custom(
                meta=self.meta,
                date=self.date,
                type='comprehensive_balance',
                values=[
                    ValueType('Assets:Checking', account.TYPE),
                    ValueType('100 + USD', str)  # Invalid: missing operand
                ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        self.assertEqual(len(errors), 1)
        self.assertIn('Failed to parse expression', str(errors[0]))

    def test_tolerance_simple(self):
        """Test simple local tolerance specification."""
        entries = self.base_entries + [
            data.Transaction(meta=self.meta,
                             date=datetime.date(2023, 12, 31),
                             flag='*',
                             payee=None,
                             narration='Test balance',
                             tags=set(),
                             links=set(),
                             postings=[
                                 data.Posting(account='Assets:Checking',
                                              units=data.Amount(
                                                  Decimal('1000.005'), 'USD'),
                                              cost=None,
                                              price=None,
                                              flag=None,
                                              meta={}),
                                 data.Posting(account='Expenses:Coffee',
                                              units=data.Amount(
                                                  Decimal('-1000.005'), 'USD'),
                                              cost=None,
                                              price=None,
                                              flag=None,
                                              meta={}),
                             ]),
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType('1000.00 ~ 0.01 USD', str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)
        balance_directives = [
            e for e in new_entries if isinstance(e, data.Balance)
        ]
        self.assertEqual(len(balance_directives), 1)
        self.assertEqual(balance_directives[0].amount.number,
                         Decimal('1000.00'))
        self.assertEqual(balance_directives[0].tolerance, Decimal('0.01'))

    def test_tolerance_with_expression(self):
        """Test tolerance combined with arithmetic expression."""
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 12, 31),
                flag='*',
                payee=None,
                narration='Test balance',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('150.3'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-150.3'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType('100 + 50 ~ 0.5 USD', str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)
        balance_directives = [
            e for e in new_entries if isinstance(e, data.Balance)
        ]
        self.assertEqual(len(balance_directives), 1)
        self.assertEqual(balance_directives[0].amount.number, Decimal('150'))
        self.assertEqual(balance_directives[0].tolerance, Decimal('0.5'))

    def test_tolerance_none_when_not_specified(self):
        """Test that tolerance is None when not specified (backward compat)."""
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 12, 31),
                flag='*',
                payee=None,
                narration='Test balance',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('1000'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-1000'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType('1000.00 USD', str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)
        balance_directives = [
            e for e in new_entries if isinstance(e, data.Balance)
        ]
        self.assertEqual(len(balance_directives), 1)
        self.assertIsNone(balance_directives[0].tolerance)

    def test_tolerance_multiple_currencies(self):
        """Test tolerance with multiple currencies, some with and without."""
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 12, 31),
                flag='*',
                payee=None,
                narration='Test balance',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('1000'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Checking',
                                 units=data.Amount(Decimal('500'), 'EUR'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-1000'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Expenses:Coffee',
                                 units=data.Amount(Decimal('-500'), 'EUR'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            data.Custom(meta=self.meta,
                        date=self.date,
                        type='comprehensive_balance',
                        values=[
                            ValueType('Assets:Checking', account.TYPE),
                            ValueType(
                                """
                    1000.00 ~ 0.01 USD  ; With tolerance
                    500.00 EUR          ; Without tolerance
                """, str)
                        ])
        ]

        new_entries, errors = comprehensive_balance.comprehensive_balance(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)
        balance_directives = [
            e for e in new_entries if isinstance(e, data.Balance)
        ]
        self.assertEqual(len(balance_directives), 2)

        usd_balance = next(b for b in balance_directives
                           if b.amount.currency == 'USD')
        self.assertEqual(usd_balance.amount.number, Decimal('1000.00'))
        self.assertEqual(usd_balance.tolerance, Decimal('0.01'))

        eur_balance = next(b for b in balance_directives
                           if b.amount.currency == 'EUR')
        self.assertEqual(eur_balance.amount.number, Decimal('500.00'))
        self.assertIsNone(eur_balance.tolerance)


if __name__ == '__main__':
    unittest.main()
