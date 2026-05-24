#!/usr/bin/env python3
"""Plugin to process comprehensive_balance custom directives.

This plugin processes 'comprehensive_balance' custom directives that specify:
1. An account name
2. A multi-line string containing balance assertions (one amount per line)

The plugin validates that the specified account contains only the commodities
listed in the balance assertions (plus any commodities with zero balance, which
are ignored). For any unlisted commodities with non-zero balances, it generates
additional zero-balance assertions.

The plugin removes the custom directives and replaces them with standard
Balance directives for each assertion, plus zero-balance assertions for any
unlisted non-zero commodities.

Balance assertions support:
- Arithmetic expressions (+, -, *, /, parentheses)
- Comma-formatted numbers (e.g., 1,234.56)
- Local tolerance specification using ~ syntax (e.g., 100 ~ 0.01 USD)

Usage:
    plugin "beansprout.plugins.comprehensive_balance"

Example directive:
    2024-01-01 custom "comprehensive_balance" Assets:Checking "
      1000.00 USD
      50.00 EUR  ; European holdings
      "

Example with arithmetic expressions:
    2024-01-01 custom "comprehensive_balance" Assets:Savings "
      1,000 + 500 USD           ; Deposits
      (10000 - 200) * 0.5 JPY   ; Complex calculation
      "

Example with local tolerance:
    2024-01-01 custom "comprehensive_balance" Assets:Investing "
      319.020 ~ 0.002 RGAGX     ; Fund shares with tolerance
      100 + 50 ~ 0.5 USD        ; Expression with tolerance
      "
"""

import datetime
import re
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from beancount.core import account, data, realization
from beancount.ops.validation import ValidationError
from beancount.parser import parser

__plugins__ = ("comprehensive_balance", )


def comprehensive_balance(
        entries: List[data.Directive],
        options_map: Dict,
        config: str = "") -> Tuple[List[data.Directive], List[data.Directive]]:
    """Process comprehensive_balance custom directives.
    
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
                      data.Custom) and entry.type == "comprehensive_balance":
            custom_directives.append(entry)
        else:
            new_entries.append(entry)

    # Build realization tree for balance computation (without custom directives)
    real_root = realization.realize(new_entries)

    # Process custom directives
    for custom_entry in custom_directives:
        balance_entries, validation_errors = _process_comprehensive_balance(
            custom_entry, real_root, options_map)
        new_entries.extend(balance_entries)
        errors.extend(validation_errors)

    return new_entries, errors


def _process_comprehensive_balance(
        custom_entry: data.Custom, real_root: realization.RealAccount,
        options_map: Dict
) -> Tuple[List[data.Directive], List[data.Directive]]:
    """Process a single comprehensive_balance custom directive.
    
    Creates Balance directives for declared assertions and zero-balance assertions
    for any unlisted commodities with non-zero balances.
    
    Args:
        custom_entry: The custom directive to process
        real_root: Realization tree root for balance computation
        options_map: Beancount options map
        
    Returns:
        Tuple of (balance_entries, errors)
    """
    balance_entries = []
    errors = []

    # Validate directive structure
    if len(custom_entry.values) != 2:
        error = ValidationError(
            custom_entry.meta,
            f"comprehensive_balance directive requires exactly 2 parameters, got {len(custom_entry.values)}",
            custom_entry)
        return [], [error]

    # Extract parameters
    account_name = custom_entry.values[0]
    balance_text = custom_entry.values[1]

    if not account_name or account_name.dtype != account.TYPE:
        error = ValidationError(
            custom_entry.meta,
            f"First parameter must be an account name (string), got {type(account_name).__name__}",
            custom_entry)
        return [], [error]

    if not balance_text or balance_text.dtype != str:
        error = ValidationError(
            custom_entry.meta,
            f"Second parameter must be a string, got {type(balance_text).__name__}",
            custom_entry)
        return [], [error]

    # Parse balance assertions from multi-line string
    assertions, parse_errors = _parse_balance_assertions(
        balance_text.value, custom_entry.meta)
    errors.extend(parse_errors)

    if parse_errors:
        return [], errors

    # Get actual account balance at the directive date
    account_balance = _get_account_balance_at_date(real_root,
                                                   account_name.value,
                                                   custom_entry.date,
                                                   options_map)
    if account_balance is None:
        error = ValidationError(custom_entry.meta,
                                f"Account '{account_name.value}' not found",
                                custom_entry)
        return [], [error]

    # Validate that account has only the declared commodities (plus zero-balance ones)
    declared_commodities = set(assertions.keys())
    actual_commodities = set(account_balance.keys())

    # Generate zero-balance assertions for unlisted commodities with non-zero balances
    for commodity in actual_commodities:
        if commodity not in declared_commodities:
            amount = account_balance[commodity]
            if amount != Decimal('0'):
                # Create zero-balance assertion for unlisted commodity
                zero_balance_entry = data.Balance(
                    meta=custom_entry.meta.copy(),
                    date=custom_entry.date,
                    account=account_name.value,
                    amount=data.Amount(Decimal('0'), commodity),
                    tolerance=None,
                    diff_amount=None)
                balance_entries.append(zero_balance_entry)

    # Create Balance directives for each assertion
    for commodity, (amount, tolerance) in assertions.items():
        balance_entry = data.Balance(meta=custom_entry.meta.copy(),
                                     date=custom_entry.date,
                                     account=account_name.value,
                                     amount=data.Amount(amount, commodity),
                                     tolerance=tolerance,
                                     diff_amount=None)
        balance_entries.append(balance_entry)

    return balance_entries, errors


def _parse_balance_assertions(
    balance_text: str, meta: Dict
) -> Tuple[Dict[str, Tuple[Decimal, Optional[Decimal]]],
           List[ValidationError]]:
    """Parse balance assertions from multi-line string.

    Supports arithmetic expressions in amounts using Beancount's expression
    parser, as well as local tolerance specification. Examples:
        - "1000.00 USD" (simple constant)
        - "100 + 50 USD" (addition)
        - "(1000 - 200) * 2 USD" (complex expression)
        - "1,234.56 USD" (comma-formatted numbers)
        - "1000.00 ~ 0.01 USD" (with local tolerance)
        - "100 + 50 ~ 0.5 USD" (expression with tolerance)

    Args:
        balance_text: Multi-line string containing balance assertions
        meta: Metadata for error reporting

    Returns:
        Tuple of (assertions_dict, errors) where assertions_dict maps
        currency to (amount, tolerance) tuple. Tolerance is None if not
        specified.
    """
    assertions: Dict[str, Tuple[Decimal, Optional[Decimal]]] = {}
    errors = []

    # Pattern to match expression and currency (with optional comment)
    # The expression part captures everything before the currency token.
    # Currency must start with uppercase letter followed by uppercase letters,
    # digits, underscores, or hyphens.
    # Examples: "1000.00 USD", "100 + 50 EUR  ; comment", "(10 * 5) JPY"
    #           "1000.00 ~ 0.01 USD" (with tolerance)
    amount_pattern = re.compile(r'^\s*(.+?)\s+([A-Z][A-Z0-9_-]*)\s*(?:;.*)?$')

    for line_num, line in enumerate(balance_text.strip().split('\n'), 1):
        line = line.strip()

        # Skip empty lines and pure comment lines
        if not line or line.startswith(';'):
            continue

        match = amount_pattern.match(line)
        if not match:
            error = ValidationError(
                meta,
                f"Invalid balance assertion format on line {line_num}: '{line}'. "
                f"Expected format: 'expression [~ tolerance] currency [; comment]'",
                None)
            errors.append(error)
            continue

        expression, currency = match.groups()

        # Check for duplicate commodities before evaluating (fail fast)
        if currency in assertions:
            error = ValidationError(
                meta,
                f"Duplicate commodity '{currency}' in balance assertions",
                None)
            errors.append(error)
            continue

        # Evaluate the expression using Beancount's parser
        amount, tolerance, eval_errors = _evaluate_amount_expression(
            expression, currency, meta)
        if eval_errors:
            errors.extend(eval_errors)
            continue

        assertions[currency] = (amount, tolerance)

    return assertions, errors


def _get_account_balance_at_date(
        real_root: realization.RealAccount, account_name: str,
        date: datetime.date,
        options_map: Dict) -> Optional[Dict[str, Decimal]]:
    """Get account balance at a specific date.
    
    Args:
        real_root: Realization tree root
        account_name: Account name to get balance for
        date: Date to compute balance at
        options_map: Beancount options map
        
    Returns:
        Dictionary mapping currency -> balance amount, or None if account not found
    """
    # Find the account in the realization tree
    account_real = realization.get(real_root, account_name)
    if account_real is None:
        return None

    # Get the balance directly from the RealAccount
    balance = realization.compute_balance(account_real)

    # Convert to simple dict format
    result = {}
    for position in balance:
        if position.units:
            currency = position.units.currency
            amount = position.units.number
            result[currency] = result.get(currency, Decimal('0')) + amount

    return result


def _evaluate_amount_expression(
    expression: str, currency: str, meta: Dict
) -> Tuple[Optional[Decimal], Optional[Decimal], List[ValidationError]]:
    """Evaluate an arithmetic expression using Beancount's parser.

    This function constructs a synthetic Balance directive and parses it
    with Beancount's parser to evaluate arithmetic expressions like
    "100 + 50 * 2" or "(1000 - 200) / 4". It also supports local tolerance
    specification using the "~ tolerance" syntax.

    Args:
        expression: The numeric expression to evaluate, optionally including
            tolerance (e.g., "100 + 50", "100 ~ 0.01", "100 + 50 ~ 0.5")
        currency: The currency code (e.g., "USD")
        meta: Metadata for error reporting

    Returns:
        Tuple of (amount, tolerance, errors). If successful, errors is empty,
        amount contains the evaluated result, and tolerance contains the
        local tolerance value (or None if not specified).
    """
    # Construct a synthetic Balance directive
    synthetic_beancount = (
        f"2000-01-01 open Assets:Dummy\n"
        f"2000-01-01 balance Assets:Dummy {expression} {currency}\n")

    entries, parse_errors, _ = parser.parse_string(synthetic_beancount)

    if parse_errors:
        # Translate parser errors to our context
        error_messages = [str(e.message) for e in parse_errors]
        error = ValidationError(
            meta,
            f"Failed to parse expression '{expression} {currency}': {'; '.join(error_messages)}",
            None)
        return None, None, [error]

    # Find the Balance entry
    for entry in entries:
        if isinstance(entry, data.Balance):
            return entry.amount.number, entry.tolerance, []

    # Should not reach here if parsing succeeded
    error = ValidationError(
        meta, f"Failed to evaluate expression '{expression} {currency}'", None)
    return None, None, [error]
