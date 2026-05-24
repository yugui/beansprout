#!/usr/bin/env python3
"""Tests for fiscal_income_expense plugin."""

import datetime
import unittest
from decimal import Decimal

from beancount.core import account, amount as amount_module, data
from beancount.parser.grammar import ValueType

from beansprout.plugins import fiscal_income_expense


class TestFiscalIncomeExpense(unittest.TestCase):
    """Test cases for fiscal_income_expense plugin."""

    def setUp(self):
        """Set up test fixtures."""
        self.meta = {'filename': 'test.beancount', 'lineno': 1}
        self.options_map = {'operating_currency': ['JPY']}

        # Create basic account structure for testing
        self.base_entries = [
            data.Open(meta=self.meta,
                      date=datetime.date(2023, 1, 1),
                      account='Expenses:Food',
                      currencies=['JPY'],
                      booking=None),
            data.Open(meta=self.meta,
                      date=datetime.date(2023, 1, 1),
                      account='Expenses:Food:Groceries',
                      currencies=['JPY'],
                      booking=None),
            data.Open(meta=self.meta,
                      date=datetime.date(2023, 1, 1),
                      account='Expenses:Food:Restaurant',
                      currencies=['JPY'],
                      booking=None),
            data.Open(meta=self.meta,
                      date=datetime.date(2023, 1, 1),
                      account='Assets:Bank',
                      currencies=['JPY'],
                      booking=None),
            data.Open(meta=self.meta,
                      date=datetime.date(2023, 1, 1),
                      account='Income:Salary',
                      currencies=['JPY'],
                      booking=None),
        ]

    def test_matching_balance(self):
        """Test a matching fiscal balance check."""
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 5, 15),
                flag='*',
                payee='Supermarket',
                narration='Groceries',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Expenses:Food:Groceries',
                                 units=data.Amount(Decimal('3000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('-3000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 6, 20),
                flag='*',
                payee='Restaurant',
                narration='Dinner',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Expenses:Food:Restaurant',
                                 units=data.Amount(Decimal('2000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('-2000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Fiscal balance directive: check total Expenses:Food (includes sub-accounts)
            data.Custom(meta=self.meta,
                        date=datetime.date(2024, 3, 31),
                        type='fiscal_income_expense',
                        values=[
                            ValueType('Expenses:Food', account.TYPE),
                            ValueType(datetime.date(2023, 4, 1),
                                      datetime.date),
                            ValueType(data.Amount(Decimal('5000'), 'JPY'),
                                      amount_module.Amount),
                        ]),
        ]

        new_entries, errors = fiscal_income_expense.fiscal_income_expense(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)
        # Custom directive should be removed
        custom_directives = [
            e for e in new_entries if isinstance(e, data.Custom)
        ]
        self.assertEqual(len(custom_directives), 0)

    def test_matching_balance_with_implicit_begin_date(self):
        """Test a matching fiscal balance check without explicit begin_date.

        When begin_date is omitted, it defaults to January 1st of the year
        of the directive's date.
        """
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 5, 15),
                flag='*',
                payee='Supermarket',
                narration='Groceries',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Expenses:Food:Groceries',
                                 units=data.Amount(Decimal('3000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('-3000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 6, 20),
                flag='*',
                payee='Restaurant',
                narration='Dinner',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Expenses:Food:Restaurant',
                                 units=data.Amount(Decimal('2000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('-2000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Fiscal balance directive with implicit begin_date (defaults to 2023-01-01)
            # Directive date is 2023-12-31, so begin_date defaults to 2023-01-01
            data.Custom(meta=self.meta,
                        date=datetime.date(2023, 12, 31),
                        type='fiscal_income_expense',
                        values=[
                            ValueType('Expenses:Food', account.TYPE),
                            ValueType(data.Amount(Decimal('5000'), 'JPY'),
                                      amount_module.Amount),
                        ]),
        ]

        new_entries, errors = fiscal_income_expense.fiscal_income_expense(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)
        # Custom directive should be removed
        custom_directives = [
            e for e in new_entries if isinstance(e, data.Custom)
        ]
        self.assertEqual(len(custom_directives), 0)

    def test_implicit_begin_date_excludes_prior_year(self):
        """Test that implicit begin_date correctly excludes prior year transactions."""
        entries = self.base_entries + [
            # Transaction in 2022 - should be excluded when checking 2023
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2022, 12, 15),
                flag='*',
                payee='Supermarket',
                narration='Groceries from 2022',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Expenses:Food:Groceries',
                                 units=data.Amount(Decimal('1000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('-1000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Transaction in 2023 - should be included
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 5, 15),
                flag='*',
                payee='Supermarket',
                narration='Groceries',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Expenses:Food:Groceries',
                                 units=data.Amount(Decimal('3000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('-3000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Check only 2023 (3000 JPY, not 4000 JPY)
            data.Custom(meta=self.meta,
                        date=datetime.date(2023, 12, 31),
                        type='fiscal_income_expense',
                        values=[
                            ValueType('Expenses:Food', account.TYPE),
                            ValueType(data.Amount(Decimal('3000'), 'JPY'),
                                      amount_module.Amount),
                        ]),
        ]

        new_entries, errors = fiscal_income_expense.fiscal_income_expense(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)

    def test_mismatching_balance(self):
        """Test a mismatching fiscal balance check generates error."""
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 5, 15),
                flag='*',
                payee='Supermarket',
                narration='Groceries',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Expenses:Food:Groceries',
                                 units=data.Amount(Decimal('3000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('-3000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Expect 5000 but actual is 3000
            data.Custom(meta=self.meta,
                        date=datetime.date(2024, 3, 31),
                        type='fiscal_income_expense',
                        values=[
                            ValueType('Expenses:Food', account.TYPE),
                            ValueType(datetime.date(2023, 4, 1),
                                      datetime.date),
                            ValueType(data.Amount(Decimal('5000'), 'JPY'),
                                      amount_module.Amount),
                        ]),
        ]

        new_entries, errors = fiscal_income_expense.fiscal_income_expense(
            entries, self.options_map)

        self.assertEqual(len(errors), 1)
        self.assertIn('Fiscal balance check failed', str(errors[0]))
        self.assertIn('expected 5000 JPY', str(errors[0]))
        self.assertIn('got 3000', str(errors[0]))
        self.assertIn('difference: -2000', str(errors[0]))

    def test_sub_account_aggregation(self):
        """Test that sub-accounts are properly aggregated."""
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 5, 15),
                flag='*',
                payee=None,
                narration='Groceries',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Expenses:Food:Groceries',
                                 units=data.Amount(Decimal('1000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('-1000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 6, 20),
                flag='*',
                payee=None,
                narration='Restaurant',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Expenses:Food:Restaurant',
                                 units=data.Amount(Decimal('2000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('-2000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Check parent account aggregates sub-accounts: 1000 + 2000 = 3000
            data.Custom(meta=self.meta,
                        date=datetime.date(2024, 3, 31),
                        type='fiscal_income_expense',
                        values=[
                            ValueType('Expenses:Food', account.TYPE),
                            ValueType(datetime.date(2023, 4, 1),
                                      datetime.date),
                            ValueType(data.Amount(Decimal('3000'), 'JPY'),
                                      amount_module.Amount),
                        ]),
        ]

        new_entries, errors = fiscal_income_expense.fiscal_income_expense(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)

    def test_date_filtering(self):
        """Test that only transactions within the fiscal period are counted."""
        entries = self.base_entries + [
            # Transaction before fiscal year
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 3, 15),
                flag='*',
                payee=None,
                narration='Before fiscal year',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Expenses:Food',
                                 units=data.Amount(Decimal('1000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('-1000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Transaction within fiscal year
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 5, 15),
                flag='*',
                payee=None,
                narration='Within fiscal year',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Expenses:Food',
                                 units=data.Amount(Decimal('2000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('-2000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Transaction after fiscal year
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2024, 4, 15),
                flag='*',
                payee=None,
                narration='After fiscal year',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Expenses:Food',
                                 units=data.Amount(Decimal('3000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('-3000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Only the 2000 JPY transaction within fiscal year should count
            data.Custom(meta=self.meta,
                        date=datetime.date(2024, 3, 31),
                        type='fiscal_income_expense',
                        values=[
                            ValueType('Expenses:Food', account.TYPE),
                            ValueType(datetime.date(2023, 4, 1),
                                      datetime.date),
                            ValueType(data.Amount(Decimal('2000'), 'JPY'),
                                      amount_module.Amount),
                        ]),
        ]

        new_entries, errors = fiscal_income_expense.fiscal_income_expense(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)

    def test_income_account(self):
        """Test with income account (typically negative amounts)."""
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 5, 25),
                flag='*',
                payee='Employer',
                narration='Salary',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('300000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Income:Salary',
                                 units=data.Amount(Decimal('-300000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Income accounts have negative balances in Beancount
            data.Custom(meta=self.meta,
                        date=datetime.date(2024, 3, 31),
                        type='fiscal_income_expense',
                        values=[
                            ValueType('Income:Salary', account.TYPE),
                            ValueType(datetime.date(2023, 4, 1),
                                      datetime.date),
                            ValueType(data.Amount(Decimal('-300000'), 'JPY'),
                                      amount_module.Amount),
                        ]),
        ]

        new_entries, errors = fiscal_income_expense.fiscal_income_expense(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)

    def test_multiple_currencies(self):
        """Test handling of multiple currencies."""
        entries = self.base_entries + [
            data.Open(meta=self.meta,
                      date=datetime.date(2023, 1, 1),
                      account='Expenses:Travel',
                      currencies=['JPY', 'USD'],
                      booking=None),
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 5, 15),
                flag='*',
                payee=None,
                narration='Travel in JPY',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Expenses:Travel',
                                 units=data.Amount(Decimal('10000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('-10000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 6, 20),
                flag='*',
                payee=None,
                narration='Travel in USD',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Expenses:Travel',
                                 units=data.Amount(Decimal('100'), 'USD'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('-15000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Check only JPY balance
            data.Custom(meta=self.meta,
                        date=datetime.date(2024, 3, 31),
                        type='fiscal_income_expense',
                        values=[
                            ValueType('Expenses:Travel', account.TYPE),
                            ValueType(datetime.date(2023, 4, 1),
                                      datetime.date),
                            ValueType(data.Amount(Decimal('10000'), 'JPY'),
                                      amount_module.Amount),
                        ]),
        ]

        new_entries, errors = fiscal_income_expense.fiscal_income_expense(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)

    def test_empty_period(self):
        """Test with no transactions in the fiscal period."""
        entries = self.base_entries + [
            # Transaction outside the fiscal year
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2022, 5, 15),
                flag='*',
                payee=None,
                narration='Old transaction',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Expenses:Food',
                                 units=data.Amount(Decimal('1000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('-1000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Expect zero for the fiscal year
            data.Custom(meta=self.meta,
                        date=datetime.date(2024, 3, 31),
                        type='fiscal_income_expense',
                        values=[
                            ValueType('Expenses:Food', account.TYPE),
                            ValueType(datetime.date(2023, 4, 1),
                                      datetime.date),
                            ValueType(data.Amount(Decimal('0'), 'JPY'),
                                      amount_module.Amount),
                        ]),
        ]

        new_entries, errors = fiscal_income_expense.fiscal_income_expense(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)

    def test_wrong_parameter_count_too_few(self):
        """Test error for too few parameters (1 parameter)."""
        entries = self.base_entries + [
            data.Custom(meta=self.meta,
                        date=datetime.date(2024, 3, 31),
                        type='fiscal_income_expense',
                        values=[
                            ValueType('Expenses:Food', account.TYPE),
                        ]),
        ]

        new_entries, errors = fiscal_income_expense.fiscal_income_expense(
            entries, self.options_map)

        self.assertEqual(len(errors), 1)
        self.assertIn('2 or 3 parameters', str(errors[0]))

    def test_wrong_parameter_count_too_many(self):
        """Test error for too many parameters (4 parameters)."""
        entries = self.base_entries + [
            data.Custom(meta=self.meta,
                        date=datetime.date(2024, 3, 31),
                        type='fiscal_income_expense',
                        values=[
                            ValueType('Expenses:Food', account.TYPE),
                            ValueType(datetime.date(2023, 4, 1),
                                      datetime.date),
                            ValueType(data.Amount(Decimal('5000'), 'JPY'),
                                      amount_module.Amount),
                            ValueType('extra', str),
                        ]),
        ]

        new_entries, errors = fiscal_income_expense.fiscal_income_expense(
            entries, self.options_map)

        self.assertEqual(len(errors), 1)
        self.assertIn('2 or 3 parameters', str(errors[0]))

    def test_invalid_begin_date_after_end_date(self):
        """Test error when begin date is after end date."""
        entries = self.base_entries + [
            data.Custom(
                meta=self.meta,
                date=datetime.date(2023, 3, 31),  # End date before begin date
                type='fiscal_income_expense',
                values=[
                    ValueType('Expenses:Food', account.TYPE),
                    ValueType(datetime.date(2023, 4, 1),
                              datetime.date),  # Begin after end
                    ValueType(data.Amount(Decimal('5000'), 'JPY'),
                              amount_module.Amount),
                ]),
        ]

        new_entries, errors = fiscal_income_expense.fiscal_income_expense(
            entries, self.options_map)

        self.assertEqual(len(errors), 1)
        self.assertIn('Begin date', str(errors[0]))
        self.assertIn('must be before or equal to', str(errors[0]))

    def test_boundary_dates_inclusive(self):
        """Test that begin and end dates are both inclusive."""
        entries = self.base_entries + [
            # Transaction on begin date
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 4, 1),
                flag='*',
                payee=None,
                narration='On begin date',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Expenses:Food',
                                 units=data.Amount(Decimal('1000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('-1000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Transaction on end date
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2024, 3, 31),
                flag='*',
                payee=None,
                narration='On end date',
                tags=set(),
                links=set(),
                postings=[
                    data.Posting(account='Expenses:Food',
                                 units=data.Amount(Decimal('2000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('-2000'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Both transactions should be included: 1000 + 2000 = 3000
            data.Custom(meta=self.meta,
                        date=datetime.date(2024, 3, 31),
                        type='fiscal_income_expense',
                        values=[
                            ValueType('Expenses:Food', account.TYPE),
                            ValueType(datetime.date(2023, 4, 1),
                                      datetime.date),
                            ValueType(data.Amount(Decimal('3000'), 'JPY'),
                                      amount_module.Amount),
                        ]),
        ]

        new_entries, errors = fiscal_income_expense.fiscal_income_expense(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)

    def test_inferred_tolerance_passes(self):
        """Test that inferred tolerance allows small differences.

        For whole number amounts like 50000 JPY (exponent 0), the inferred
        tolerance is 0.5. A difference of 0.4 should pass.
        """
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 5, 15),
                flag='*',
                payee='Supermarket',
                narration='Groceries',
                tags=set(),
                links=set(),
                postings=[
                    # Actual amount: 49999.6 JPY
                    data.Posting(account='Expenses:Food:Groceries',
                                 units=data.Amount(Decimal('49999.6'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('-49999.6'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Expected 50000 JPY, actual 49999.6 JPY, diff = 0.4 < tolerance 0.5
            data.Custom(meta=self.meta,
                        date=datetime.date(2023, 12, 31),
                        type='fiscal_income_expense',
                        values=[
                            ValueType('Expenses:Food', account.TYPE),
                            ValueType(data.Amount(Decimal('50000'), 'JPY'),
                                      amount_module.Amount),
                        ]),
        ]

        new_entries, errors = fiscal_income_expense.fiscal_income_expense(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)

    def test_inferred_tolerance_fails(self):
        """Test that inferred tolerance rejects larger differences.

        For whole number amounts like 50000 JPY (exponent 0), the inferred
        tolerance is 0.5. A difference of 1 should fail.
        """
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 5, 15),
                flag='*',
                payee='Supermarket',
                narration='Groceries',
                tags=set(),
                links=set(),
                postings=[
                    # Actual amount: 49999 JPY
                    data.Posting(account='Expenses:Food:Groceries',
                                 units=data.Amount(Decimal('49999'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('-49999'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Expected 50000 JPY, actual 49999 JPY, diff = 1 > tolerance 0.5
            data.Custom(meta=self.meta,
                        date=datetime.date(2023, 12, 31),
                        type='fiscal_income_expense',
                        values=[
                            ValueType('Expenses:Food', account.TYPE),
                            ValueType(data.Amount(Decimal('50000'), 'JPY'),
                                      amount_module.Amount),
                        ]),
        ]

        new_entries, errors = fiscal_income_expense.fiscal_income_expense(
            entries, self.options_map)

        self.assertEqual(len(errors), 1)
        self.assertIn('Fiscal balance check failed', str(errors[0]))
        self.assertIn('tolerance: 0.5', str(errors[0]))

    def test_explicit_tolerance_string_passes(self):
        """Test that explicit tolerance string allows specified differences.

        With "50000 ~ 1 JPY", a difference of 0.5 should pass.
        """
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 5, 15),
                flag='*',
                payee='Supermarket',
                narration='Groceries',
                tags=set(),
                links=set(),
                postings=[
                    # Actual amount: 49999.5 JPY
                    data.Posting(account='Expenses:Food:Groceries',
                                 units=data.Amount(Decimal('49999.5'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('-49999.5'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Expected 50000 JPY with tolerance 1, actual 49999.5, diff = 0.5 <= 1
            data.Custom(meta=self.meta,
                        date=datetime.date(2023, 12, 31),
                        type='fiscal_income_expense',
                        values=[
                            ValueType('Expenses:Food', account.TYPE),
                            ValueType('50000 ~ 1 JPY', str),
                        ]),
        ]

        new_entries, errors = fiscal_income_expense.fiscal_income_expense(
            entries, self.options_map)

        self.assertEqual(len(errors), 0)

    def test_explicit_tolerance_string_fails(self):
        """Test that explicit tolerance string rejects larger differences.

        With "50000 ~ 1 JPY", a difference of 2 should fail.
        """
        entries = self.base_entries + [
            data.Transaction(
                meta=self.meta,
                date=datetime.date(2023, 5, 15),
                flag='*',
                payee='Supermarket',
                narration='Groceries',
                tags=set(),
                links=set(),
                postings=[
                    # Actual amount: 49998 JPY
                    data.Posting(account='Expenses:Food:Groceries',
                                 units=data.Amount(Decimal('49998'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                    data.Posting(account='Assets:Bank',
                                 units=data.Amount(Decimal('-49998'), 'JPY'),
                                 cost=None,
                                 price=None,
                                 flag=None,
                                 meta={}),
                ]),
            # Expected 50000 JPY with tolerance 1, actual 49998, diff = 2 > 1
            data.Custom(meta=self.meta,
                        date=datetime.date(2023, 12, 31),
                        type='fiscal_income_expense',
                        values=[
                            ValueType('Expenses:Food', account.TYPE),
                            ValueType('50000 ~ 1 JPY', str),
                        ]),
        ]

        new_entries, errors = fiscal_income_expense.fiscal_income_expense(
            entries, self.options_map)

        self.assertEqual(len(errors), 1)
        self.assertIn('Fiscal balance check failed', str(errors[0]))
        self.assertIn('tolerance: 1', str(errors[0]))


if __name__ == '__main__':
    unittest.main()
