#!/usr/bin/env python3
"""Plugin to validate trading account balance rules.

This plugin validates that transactions with trading accounts follow specific balance rules:
1. Trading accounts alone must balance to zero
2. Non-trading accounts alone must balance to zero  
3. For each commodity, postings with that commodity must balance to zero

Trading accounts are identified by a configurable account prefix (default: "Equity:Trading").

Special handling for commodities with 'trading-account: "disabled"' metadata:
- These commodities are grouped by their price currency instead of units currency
- Balance validation includes both units and price for these commodities
- If no price is available, validation is skipped for that posting

Usage:
    plugin "beansprout.plugins.trading_validation"
    plugin "beansprout.plugins.trading_validation" "Assets:Trading"
"""

from typing import Dict, List, Set, Tuple

from beancount.core import data
from beancount.ops.validation import validate_check_transaction_balances

__plugins__ = ("trading_validation", )


def trading_validation(
    entries: List[data.Directive],
    options_map: Dict,
    config: str = "Equity:Trading"
) -> Tuple[List[data.Directive], List[data.Directive]]:
    """Validate trading account balance rules.
    
    Args:
        entries: List of Beancount entries
        options_map: Beancount options map
        config: Trading account prefix (default: "Equity:Trading")
        
    Returns:
        Tuple of (entries, errors)
    """
    trading_prefix = config.strip() if config else "Equity:Trading"

    # Extract commodity metadata for disabled trading accounts
    commodity_mapping = _extract_commodity_mapping(entries)

    # Validate each transaction that contains trading accounts
    errors = []
    for entry in entries:
        if isinstance(entry, data.Transaction):
            if _has_trading_accounts(entry, trading_prefix):
                validation_errors = _validate_trading_transaction(
                    entry, commodity_mapping, trading_prefix, options_map)
                errors.extend(validation_errors)

    return entries, errors


def _extract_commodity_mapping(
        entries: List[data.Directive]) -> Dict[str, str]:
    """Extract commodity trading-account metadata.
    
    Args:
        entries: List of Beancount entries
        
    Returns:
        Dictionary mapping currency codes to trading-account metadata values
    """
    commodity_mapping = {}

    for entry in entries:
        if isinstance(entry, data.Commodity):
            trading_account_meta = entry.meta.get('trading-account')
            if trading_account_meta:
                commodity_mapping[entry.currency] = trading_account_meta

    return commodity_mapping


def _has_trading_accounts(transaction: data.Transaction,
                          trading_prefix: str) -> bool:
    """Check if transaction contains any trading accounts.
    
    Args:
        transaction: Transaction to check
        trading_prefix: Trading account prefix to look for
        
    Returns:
        True if transaction has trading accounts, False otherwise
    """
    return any(
        _is_trading_account(posting.account, trading_prefix)
        for posting in transaction.postings)


def _is_trading_account(account: str, trading_prefix: str) -> bool:
    """Check if an account is a trading account.
    
    Args:
        account: Account name to check
        trading_prefix: Trading account prefix
        
    Returns:
        True if account starts with trading prefix, False otherwise
    """
    return account.startswith(trading_prefix)


def _validate_trading_transaction(transaction: data.Transaction,
                                  commodity_mapping: Dict[str, str],
                                  trading_prefix: str,
                                  options_map: Dict) -> List[data.Directive]:
    """Validate a single trading transaction with all three rules.
    
    Args:
        transaction: Transaction to validate
        commodity_mapping: Commodity metadata mapping
        trading_prefix: Trading account prefix
        options_map: Beancount options map
        
    Returns:
        List of validation errors
    """
    errors = []

    # Rule 1: Trading accounts only must balance
    trading_postings = [
        posting for posting in transaction.postings
        if _is_trading_account(posting.account, trading_prefix)
    ]
    if trading_postings:
        temp_txn = transaction._replace(postings=trading_postings)
        trading_errors = validate_check_transaction_balances([temp_txn],
                                                             options_map)
        errors.extend(trading_errors)

    # Rule 2: Non-trading accounts only must balance
    non_trading_postings = [
        posting for posting in transaction.postings
        if not _is_trading_account(posting.account, trading_prefix)
    ]
    if non_trading_postings:
        temp_txn = transaction._replace(postings=non_trading_postings)
        non_trading_errors = validate_check_transaction_balances([temp_txn],
                                                                 options_map)
        errors.extend(non_trading_errors)

    # Rule 3: Per-commodity balance (with disabled commodity handling)
    effective_commodities = _extract_effective_commodities(
        transaction, commodity_mapping)
    for commodity in effective_commodities:
        commodity_postings = _get_postings_for_commodity(
            transaction, commodity, commodity_mapping)
        if commodity_postings:
            temp_txn = transaction._replace(postings=commodity_postings)
            commodity_errors = validate_check_transaction_balances([temp_txn],
                                                                   options_map)
            errors.extend(commodity_errors)

    return errors


def _extract_effective_commodities(
        transaction: data.Transaction,
        commodity_mapping: Dict[str, str]) -> Set[str]:
    """Extract effective commodities for balance checking.
    
    For normal commodities, uses units.currency.
    For commodities with trading-account: "disabled", uses price.currency if available.
    
    Args:
        transaction: Transaction to extract commodities from
        commodity_mapping: Commodity metadata mapping
        
    Returns:
        Set of effective commodity names
    """
    commodities = set()

    for posting in transaction.postings:
        if posting.units:
            commodity = posting.units.currency

            # Check if commodity has trading-account: "disabled"
            if commodity_mapping.get(commodity) == "disabled":
                # Use price currency instead (if available)
                if posting.price:
                    commodities.add(posting.price.currency)
                # Skip if no price available (validation will be skipped)
            else:
                commodities.add(commodity)

    return commodities


def _get_postings_for_commodity(
        transaction: data.Transaction, commodity: str,
        commodity_mapping: Dict[str, str]) -> List[data.Posting]:
    """Get all postings that should be included in balance check for given commodity.
    
    Args:
        transaction: Transaction to extract postings from
        commodity: Commodity to filter by
        commodity_mapping: Commodity metadata mapping
        
    Returns:
        List of postings that should be balanced together for this commodity
    """
    commodity_postings = []

    for posting in transaction.postings:
        if not posting.units:
            continue

        units_commodity = posting.units.currency

        # Check if this posting's commodity has trading-account: "disabled"
        if commodity_mapping.get(units_commodity) == "disabled":
            # For disabled commodities, group by price currency
            if posting.price and posting.price.currency == commodity:
                commodity_postings.append(posting)
            continue

        # For normal commodities, group by units currency
        if units_commodity == commodity:
            posting = posting._replace(price=None, cost=None)
            commodity_postings.append(posting)

    return commodity_postings
