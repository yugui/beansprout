#!/usr/bin/env python3
"""Plugin to process fiscal_income_expense custom directives.

This plugin processes 'fiscal_income_expense' custom directives that check
the net change (sum of postings) of an income or expense account within a
fiscal year period.

The directive takes two or three arguments:
1. An account name (includes sub-accounts in the calculation)
2. (Optional) A begin date for the fiscal year. Defaults to January 1st of
   the year of the directive's date if omitted.
3. An expected amount - either:
   - Native Beancount Amount type (e.g., 50000 JPY)
   - String with optional tolerance using ~ syntax (e.g., "50000 ~ 1 JPY")

The directive's own date serves as the end date of the fiscal period.

Tolerance handling:
- When using native Amount, tolerance is inferred from decimal precision
  following Beancount conventions (tolerance = 10^exponent * 0.5).
  For example, 50000 JPY has tolerance 0.5, while 50000.00 JPY has 0.005.
- When using string with ~ syntax, explicit tolerance is used.
  For example, "50000 ~ 1 JPY" allows differences up to 1 JPY.

Usage:
    plugin "beansprout.plugins.fiscal_income_expense"

Example directives:
    ; With explicit begin date
    2024-03-31 custom "fiscal_income_expense" Expenses:Food 2023-04-01 50000 JPY

    ; With implicit begin date (defaults to 2024-01-01)
    2024-12-31 custom "fiscal_income_expense" Expenses:Food 50000 JPY

    ; With explicit tolerance (allows +/- 1 JPY difference)
    2024-12-31 custom "fiscal_income_expense" Expenses:Food "50000 ~ 1 JPY"
"""

import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from beancount.core import account, amount as amount_module, data, realization
from beancount.ops.validation import ValidationError
from beancount.parser import parser

__plugins__ = ("fiscal_income_expense", )

# Default tolerance multiplier following Beancount conventions.
# See https://beancount.github.io/docs/rounding_precision_in_beancount.html
DEFAULT_TOLERANCE_MULTIPLIER = Decimal('0.5')


def _infer_tolerance(amount: amount_module.Amount) -> Decimal:
    """Infer tolerance from the decimal precision of an amount.

    Uses the same algorithm as Beancount's tolerance inference:
    tolerance = 10^exponent * DEFAULT_TOLERANCE_MULTIPLIER

    Args:
        amount: The amount to infer tolerance from.

    Returns:
        The inferred tolerance as a Decimal.
    """
    exponent = amount.number.as_tuple().exponent
    if isinstance(exponent, int) and exponent < 0:
        return Decimal(10)**exponent * DEFAULT_TOLERANCE_MULTIPLIER
    # For whole numbers (exponent >= 0), use the multiplier directly
    return DEFAULT_TOLERANCE_MULTIPLIER


def _parse_amount_with_tolerance(
    expression: str, meta: Dict
) -> Tuple[Optional[amount_module.Amount], Optional[Decimal], List]:
    """Parse an amount expression with optional tolerance using Beancount's parser.

    Supports the "amount ~ tolerance currency" syntax (e.g., "50000 ~ 1 JPY").

    Args:
        expression: The amount expression string to parse.
        meta: Metadata for error reporting.

    Returns:
        Tuple of (amount, tolerance, errors). If successful, errors is empty.
        Tolerance is None if not specified in the expression.
    """
    # Construct a synthetic Balance directive and parse it
    synthetic_beancount = (f"2000-01-01 open Assets:Dummy\n"
                           f"2000-01-01 balance Assets:Dummy {expression}\n")

    entries, parse_errors, _ = parser.parse_string(synthetic_beancount)

    if parse_errors:
        error_messages = [str(e.message) for e in parse_errors]
        error = ValidationError(
            meta, f"Failed to parse amount expression '{expression}': "
            f"{'; '.join(error_messages)}", None)
        return None, None, [error]

    # Find the Balance entry
    for entry in entries:
        if isinstance(entry, data.Balance):
            return entry.amount, entry.tolerance, []

    # Should not reach here if parsing succeeded
    error = ValidationError(
        meta, f"Failed to evaluate amount expression '{expression}'", None)
    return None, None, [error]


def fiscal_income_expense(
        entries: List[data.Directive],
        options_map: Dict,
        config: str = "") -> Tuple[List[data.Directive], List]:
    """Process fiscal_income_expense custom directives.

    Args:
        entries: List of Beancount entries
        options_map: Beancount options map
        config: Plugin configuration (unused)

    Returns:
        Tuple of (entries, errors)
    """
    new_entries = []
    errors = []
    custom_directives = []

    # Separate custom directives from other entries
    for entry in entries:
        if isinstance(entry,
                      data.Custom) and entry.type == "fiscal_income_expense":
            custom_directives.append(entry)
        else:
            new_entries.append(entry)

    # Process custom directives
    for custom_entry in custom_directives:
        validation_errors = _process_fiscal_income_expense(
            custom_entry, new_entries)
        errors.extend(validation_errors)

    return new_entries, errors


def _process_fiscal_income_expense(custom_entry: data.Custom,
                                   entries: List[data.Directive]) -> List:
    """Process a single fiscal_income_expense custom directive.

    Validates that the net change of the account (including sub-accounts)
    within the fiscal period matches the expected amount.

    Args:
        custom_entry: The custom directive to process
        entries: All other entries (for balance computation)

    Returns:
        List of errors (empty if validation passes)
    """
    errors = []

    # Validate directive structure
    if len(custom_entry.values) not in (2, 3):
        return [
            ValidationError(
                custom_entry.meta,
                f"fiscal_income_expense directive requires 2 or 3 parameters "
                f"(account, [begin_date,] amount), got {len(custom_entry.values)}",
                custom_entry)
        ]

    # Extract parameters
    account_param = custom_entry.values[0]

    # Validate account parameter
    if not account_param or account_param.dtype != account.TYPE:
        return [
            ValidationError(
                custom_entry.meta, f"First parameter must be an account name, "
                f"got {type(account_param.value).__name__ if account_param else 'None'}",
                custom_entry)
        ]
    account_name = account_param.value

    end_date = custom_entry.date

    # Handle optional begin_date parameter
    if len(custom_entry.values) == 3:
        begin_date_param = custom_entry.values[1]
        amount_param = custom_entry.values[2]

        # Validate begin_date parameter
        if not begin_date_param or begin_date_param.dtype != datetime.date:
            return [
                ValidationError(
                    custom_entry.meta, f"Second parameter must be a date, "
                    f"got {type(begin_date_param.value).__name__ if begin_date_param else 'None'}",
                    custom_entry)
            ]
        begin_date = begin_date_param.value
    else:
        # Default to January 1st of the year of end_date
        amount_param = custom_entry.values[1]
        begin_date = datetime.date(end_date.year, 1, 1)

    # Validate date range
    if begin_date > end_date:
        return [
            ValidationError(
                custom_entry.meta,
                f"Begin date ({begin_date}) must be before or equal to "
                f"end date ({end_date})", custom_entry)
        ]

    # Validate and parse amount parameter (supports Amount or string with ~ syntax)
    if not amount_param:
        return [
            ValidationError(
                custom_entry.meta,
                "Amount parameter is required but was not provided",
                custom_entry)
        ]

    if amount_param.dtype == str:
        # Parse string expression (supports "50000 ~ 1 JPY" syntax)
        expected_amount, tolerance, parse_errors = _parse_amount_with_tolerance(
            amount_param.value, custom_entry.meta)
        if parse_errors:
            return parse_errors
        # If no explicit tolerance, infer from amount precision
        if tolerance is None:
            tolerance = _infer_tolerance(expected_amount)
    elif amount_param.dtype == amount_module.Amount:
        # Use Amount directly and infer tolerance from precision
        expected_amount = amount_param.value
        tolerance = _infer_tolerance(expected_amount)
    else:
        return [
            ValidationError(
                custom_entry.meta,
                f"Amount parameter must be an amount or string, "
                f"got {type(amount_param.value).__name__}", custom_entry)
        ]

    filtered_entries = [
        e for e in entries
        if hasattr(e, 'date') and begin_date <= e.date <= end_date
    ]

    # Realize filtered entries and compute balance
    actual_balance = _compute_account_balance(filtered_entries, account_name)

    # Check balance for the expected currency with tolerance
    actual_amount = actual_balance.get(expected_amount.currency, Decimal('0'))
    diff = actual_amount - expected_amount.number

    if abs(diff) > tolerance:
        errors.append(
            ValidationError(
                custom_entry.meta,
                f"Fiscal balance check failed for {account_name} "
                f"({begin_date} to {end_date}): "
                f"expected {expected_amount} (tolerance: {tolerance}), "
                f"got {actual_amount} {expected_amount.currency} "
                f"(difference: {diff} {expected_amount.currency})",
                custom_entry))

    return errors


def _compute_account_balance(entries: List[data.Directive],
                             account_name: str) -> Dict[str, Decimal]:
    """Compute the balance of an account including sub-accounts.

    Args:
        entries: List of entries to realize
        account_name: Account name to compute balance for

    Returns:
        Dictionary mapping currency -> balance amount.
        Returns empty dict if account has no transactions in the entries.
    """
    # Realize the entries
    real_root = realization.realize(entries)

    # Find the account in the realization tree
    account_real = realization.get(real_root, account_name)
    if account_real is None:
        # Account has no transactions in the filtered period
        return {}

    # Compute balance including sub-accounts
    balance = realization.compute_balance(account_real)

    # Convert to simple dict format
    result = {}
    for position in balance:
        if position.units:
            currency = position.units.currency
            amount = position.units.number
            result[currency] = result.get(currency, Decimal('0')) + amount

    return result
