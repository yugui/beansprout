#!/usr/bin/env python3
"""Plugin to validate posting commodities against regex patterns.

This plugin validates that posting commodities in transactions match regex
patterns specified in the Open directive metadata for each account.

Accounts with `commodity-pattern` metadata will have all their postings
validated against the pattern. Accounts without this metadata are ignored.

Usage:
    plugin "beansprout.plugins.commodity_pattern"

Example:
    2020-01-01 open Assets:Stocks:US
      commodity-pattern: "STOCK-[A-Z]+"

    2020-01-01 open Assets:Crypto
      commodity-pattern: "BTC|ETH|USDC|USDT"

    ; This transaction is valid (STOCK-AAPL matches "STOCK-[A-Z]+")
    2020-01-02 * "Buy stock"
      Assets:Stocks:US  10 STOCK-AAPL
      Assets:Cash      -1000 USD

    ; This transaction would produce an error (DOGE doesn't match "BTC|ETH|USDC|USDT")
    2020-01-03 * "Buy crypto"
      Assets:Crypto  1 DOGE
      Assets:Cash   -100 USD
"""

import collections
import re
from typing import Dict, List, Pattern, Tuple

from beancount.core import data

__plugins__ = ("commodity_pattern", )

CommodityPatternError = collections.namedtuple("CommodityPatternError",
                                               "source message entry")

METADATA_KEY = "commodity-pattern"


def commodity_pattern(
    entries: List[data.Directive],
    options_map: Dict,
    config: str = ""
) -> Tuple[List[data.Directive], List[CommodityPatternError]]:
    """Validate posting commodities against account patterns.

    Args:
        entries: List of Beancount entries
        options_map: Beancount options map
        config: Plugin configuration (unused)

    Returns:
        Tuple of (entries, errors)
    """
    account_patterns, pattern_errors = _build_account_patterns(entries)
    if pattern_errors:
        return entries, pattern_errors

    validation_errors = _validate_transactions(entries, account_patterns)
    return entries, validation_errors


def _build_account_patterns(
    entries: List[data.Directive]
) -> Tuple[Dict[str, Tuple[Pattern, str]], List[CommodityPatternError]]:
    """Extract and compile regex patterns from Open directives.

    Args:
        entries: List of Beancount entries

    Returns:
        Tuple of:
        - Dictionary mapping account names to (compiled_pattern, pattern_string)
        - List of errors for invalid regex patterns
    """
    account_patterns = {}
    errors = []

    for entry in entries:
        if isinstance(entry, data.Open):
            pattern_str = entry.meta.get(METADATA_KEY)
            if pattern_str is not None:
                try:
                    compiled = re.compile(pattern_str)
                    account_patterns[entry.account] = (compiled, pattern_str)
                except re.error as e:
                    error = CommodityPatternError(
                        entry.meta,
                        f"Invalid regex pattern '{pattern_str}' for account "
                        f"'{entry.account}': {e}", entry)
                    errors.append(error)

    return account_patterns, errors


def _validate_transactions(
    entries: List[data.Directive], account_patterns: Dict[str, Tuple[Pattern,
                                                                     str]]
) -> List[CommodityPatternError]:
    """Validate all posting commodities in transactions.

    Args:
        entries: List of Beancount entries
        account_patterns: Mapping of accounts to their compiled patterns

    Returns:
        List of validation errors
    """
    errors = []

    for entry in entries:
        if isinstance(entry, data.Transaction):
            for posting in entry.postings:
                # Skip postings without units (auto-balanced)
                if posting.units is None:
                    continue

                pattern_info = account_patterns.get(posting.account)
                if pattern_info is None:
                    continue

                compiled_pattern, pattern_str = pattern_info
                commodity = posting.units.currency

                if not compiled_pattern.fullmatch(commodity):
                    error = CommodityPatternError(
                        entry.meta,
                        f"Commodity '{commodity}' in account '{posting.account}' "
                        f"does not match pattern '{pattern_str}'", entry)
                    errors.append(error)

    return errors
