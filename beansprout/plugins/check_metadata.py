#!/usr/bin/env python3
"""Plugin to check presence of required metadata on specified directive types.

This plugin validates that directives have required metadata entries. For
account-based directives (open, close, balance, document, note), the check is
only applied to leaf accounts. For commodity directives, the check is always
applied.

Supported directive types:
  - open, close, balance, document, note: Check only if account is a leaf
  - commodity: Always check

Usage:
    # Check all leaf accounts
    plugin "beansprout.plugins.check_metadata" "open
        region
        tax_category"

    # Check only leaf accounts under Assets:Bank
    plugin "beansprout.plugins.check_metadata" "open Assets:Bank
        region"

This will check that Open directives on specified leaf accounts have the
required metadata.

Example:
    Input:
        2020-01-01 open Assets:Bank
          region: "US"

        2020-01-02 open Assets:Bank:Checking
          region: "US"

        2020-01-03 open Assets:Bank:Savings

        2020-01-04 open Assets:Crypto:Wallet

    With config "open\nregion":
        - Assets:Bank is not a leaf (has children) - NOT CHECKED
        - Assets:Bank:Checking is a leaf with region - OK
        - Assets:Bank:Savings is a leaf without region - ERROR
        - Assets:Crypto:Wallet is a leaf without region - ERROR

    With config "open Assets:Bank\nregion":
        - Assets:Bank is not a leaf - NOT CHECKED
        - Assets:Bank:Checking is a leaf with region - OK
        - Assets:Bank:Savings is a leaf without region - ERROR
        - Assets:Crypto:Wallet is outside filter - NOT CHECKED
"""

import collections
from typing import Dict, List, Set, Tuple

from beancount.core import data
from beancount.core import realization

__plugins__ = ("check_metadata", )

CheckMetadataError = collections.namedtuple("CheckMetadataError",
                                            "source message entry")

# Mapping of lowercase directive names to their types
DIRECTIVE_TYPES = {
    "open": data.Open,
    "close": data.Close,
    "balance": data.Balance,
    "note": data.Note,
    "document": data.Document,
    "commodity": data.Commodity,
}

# Directive types that should only be checked on leaf accounts
LEAF_ONLY_DIRECTIVES = {"open", "close", "balance", "note", "document"}


def check_metadata(
        entries: List[data.Directive],
        options_map: Dict,
        config: str = "") -> Tuple[List[data.Directive], List[data.Directive]]:
    """Check presence of required metadata on specified directive types.

    Args:
        entries: List of Beancount entries
        options_map: Beancount options map
        config: Multiline string with directive name and optional account on first line,
                followed by metadata names (one per line)
                First line format: "<directive> [account]"

    Returns:
        Tuple of (entries, errors)
    """
    # Parse configuration
    directive_name, account_filter, metadata_names = _parse_config(config)

    if not directive_name or not metadata_names:
        # No directive or metadata names specified, return unchanged
        return entries, []

    # Validate directive type
    directive_type = DIRECTIVE_TYPES.get(directive_name)
    if directive_type is None:
        # Unknown directive type
        default_meta = data.new_metadata("<check_metadata>", 0)
        error = CheckMetadataError(
            default_meta, f"Unknown directive type: {directive_name}. "
            f"Valid types: {', '.join(sorted(DIRECTIVE_TYPES.keys()))}", None)
        return entries, [error]

    # Build set of leaf accounts if needed
    leaf_accounts = None
    if directive_name in LEAF_ONLY_DIRECTIVES:
        leaf_accounts = _build_leaf_accounts(entries, account_filter)

    # Check all directives of the specified type
    errors = []
    for entry in entries:
        if isinstance(entry, directive_type):
            # Determine if we should check this entry
            should_check = _should_check_entry(entry, directive_name,
                                               leaf_accounts)

            if should_check:
                missing = _check_entry_metadata(entry, metadata_names)
                if missing:
                    error = _create_error(entry, directive_name, missing)
                    errors.append(error)

    return entries, errors


def _parse_config(config: str) -> Tuple[str, str, Set[str]]:
    """Parse configuration to extract directive name, account filter, and metadata names.

    Args:
        config: Multiline string with directive name and optional account on first line,
                followed by metadata names (one per line)
                First line format: "<directive> [account]"

    Returns:
        Tuple of (directive_name, account_filter, set_of_metadata_names)
        account_filter will be empty string if not specified
    """
    if not config:
        return "", "", set()

    lines = [
        line.strip() for line in config.strip().split('\n') if line.strip()
    ]

    if not lines:
        return "", "", set()

    # Parse first line: directive name and optional account
    first_line_parts = lines[0].split(None,
                                      1)  # Split on whitespace, max 2 parts
    directive_name = first_line_parts[0].lower()
    account_filter = first_line_parts[1] if len(first_line_parts) > 1 else ""

    metadata_names = set(lines[1:]) if len(lines) > 1 else set()

    return directive_name, account_filter, metadata_names


def _build_leaf_accounts(entries: List[data.Directive],
                         account_filter: str = "") -> Set[str]:
    """Build a set of leaf account names (accounts with no children).

    Args:
        entries: List of Beancount entries
        account_filter: Optional account prefix to filter by. If specified, only
                       include leaf accounts under this account hierarchy.

    Returns:
        Set of leaf account names
    """
    real_root = realization.realize(entries, compute_balance=False)

    leaf_accounts = set()
    for real_account in realization.iter_children(real_root):
        # An account is a leaf if it has no children
        if len(real_account) == 0:
            account = real_account.account

            # Apply account filter if specified
            if account_filter:
                # Check if account is under the filter hierarchy
                # Account must either be the filter itself or a child of it
                if account == account_filter or account.startswith(
                        account_filter + ":"):
                    leaf_accounts.add(account)
            else:
                leaf_accounts.add(account)

    return leaf_accounts


def _should_check_entry(entry: data.Directive, directive_name: str,
                        leaf_accounts: Set[str]) -> bool:
    """Determine if an entry should be checked based on directive type and leaf status.

    Args:
        entry: Directive to check
        directive_name: Name of the directive type (lowercase)
        leaf_accounts: Set of leaf account names (None if not applicable)

    Returns:
        True if the entry should be checked, False otherwise
    """
    # Commodity directives are always checked
    if directive_name == "commodity":
        return True

    # For account-based directives, only check if account is a leaf
    if directive_name in LEAF_ONLY_DIRECTIVES:
        # Extract account from the directive
        account = _get_account_from_directive(entry)
        if account is None:
            return False

        # Check if account is a leaf
        return account in leaf_accounts

    return False


def _get_account_from_directive(entry: data.Directive) -> str:
    """Extract account name from an account-based directive.

    Args:
        entry: Directive to extract account from

    Returns:
        Account name, or None if directive has no account
    """
    if isinstance(
            entry,
        (data.Open, data.Close, data.Balance, data.Note, data.Document)):
        return entry.account
    return None


def _check_entry_metadata(entry: data.Directive,
                          metadata_names: Set[str]) -> Set[str]:
    """Check which required metadata are missing from an entry.

    Args:
        entry: Directive to check
        metadata_names: Set of required metadata names

    Returns:
        Set of missing metadata names
    """
    missing = set()
    for name in metadata_names:
        if name not in entry.meta:
            missing.add(name)
    return missing


def _create_error(entry: data.Directive, directive_name: str,
                  missing: Set[str]) -> CheckMetadataError:
    """Create an error entry for missing metadata.

    Args:
        entry: Directive with missing metadata
        directive_name: Name of the directive type
        missing: Set of missing metadata names

    Returns:
        CheckMetadataError namedtuple
    """
    missing_list = sorted(missing)
    missing_str = ", ".join(missing_list)

    # Build appropriate message based on directive type
    if directive_name == "commodity":
        if isinstance(entry, data.Commodity):
            message = f"Commodity '{entry.currency}' is missing required metadata: {missing_str}"
        else:
            message = f"Commodity is missing required metadata: {missing_str}"
    else:
        account = _get_account_from_directive(entry)
        message = f"{directive_name.capitalize()} directive for account '{account}' is missing required metadata: {missing_str}"

    return CheckMetadataError(entry.meta, message, entry)
