#!/usr/bin/env python3
"""Plugin to interpolate missing metadata in open directives from parent accounts.

This plugin fills in missing metadata for Open directives by:
1. Taking a list of metadata names to track (from plugin config)
2. For each Open directive, checking if specified metadata exists
3. If missing, traversing up the account hierarchy to find and copy the metadata
4. Stopping at the first parent that has the metadata, or at root if none found

Usage:
    plugin "beansprout.plugins.inherit_metadata" "region
        tax_category"

Example:
    Input:
        2020-01-01 open Assets:Bank:Savings
          region: "US"
          tax_category: "taxable"

        2020-01-02 open Assets:Bank:Savings:Emergency

    Output:
        2020-01-01 open Assets:Bank:Savings
          region: "US"
          tax_category: "taxable"

        2020-01-02 open Assets:Bank:Savings:Emergency
          region: "US"
          tax_category: "taxable"
"""

from typing import Dict, List, Set, Tuple

from beancount.core import data
from beancount.core.account import parent

__plugins__ = ("inherit_metadata", )


def inherit_metadata(
        entries: List[data.Directive],
        options_map: Dict,
        config: str = "") -> Tuple[List[data.Directive], List[data.Directive]]:
    """Interpolate missing metadata in Open directives from parent accounts.

    Args:
        entries: List of Beancount entries
        options_map: Beancount options map
        config: Multiline string with metadata names (one per line)

    Returns:
        Tuple of (transformed_entries, errors)
    """
    # Parse configuration to get list of metadata names
    metadata_names = _parse_metadata_names(config)

    if not metadata_names:
        # No metadata names specified, return entries unchanged
        return entries, []

    # First pass: build account metadata mapping from existing Open directives
    account_metadata = _extract_account_metadata(entries, metadata_names)

    # Second pass: transform Open directives by inheriting missing metadata
    transformed_entries = []
    errors = []

    for entry in entries:
        if isinstance(entry, data.Open):
            transformed_entry = _transform_open(entry, account_metadata,
                                                metadata_names)
            transformed_entries.append(transformed_entry)
        else:
            transformed_entries.append(entry)

    return transformed_entries, errors


def _parse_metadata_names(config: str) -> Set[str]:
    """Parse metadata names from multiline configuration string.

    Args:
        config: Multiline string with metadata names (one per line)

    Returns:
        Set of metadata names
    """
    if not config:
        return set()

    metadata_names = set()
    for line in config.strip().split('\n'):
        name = line.strip()
        if name:
            metadata_names.add(name)

    return metadata_names


def _extract_account_metadata(
        entries: List[data.Directive],
        metadata_names: Set[str]) -> Dict[str, Dict[str, any]]:
    """Extract account-to-metadata mapping from Open directives.

    Args:
        entries: List of Beancount entries
        metadata_names: Set of metadata names to track

    Returns:
        Dictionary mapping account names to metadata dictionaries
    """
    account_metadata = {}

    for entry in entries:
        if isinstance(entry, data.Open):
            # Extract only the specified metadata
            metadata = {}
            for name in metadata_names:
                if name in entry.meta:
                    metadata[name] = entry.meta[name]

            if metadata:
                account_metadata[entry.account] = metadata

    return account_metadata


def _transform_open(entry: data.Open, account_metadata: Dict[str, Dict[str,
                                                                       any]],
                    metadata_names: Set[str]) -> data.Open:
    """Transform an Open directive by inheriting missing metadata from parents.

    Args:
        entry: Open directive to transform
        account_metadata: Dictionary mapping account names to metadata
        metadata_names: Set of metadata names to inherit

    Returns:
        Transformed Open directive
    """
    # Track which metadata needs to be added
    metadata_to_add = {}

    for name in metadata_names:
        # Skip if metadata already exists
        if name in entry.meta:
            continue

        # Look up parent hierarchy for this metadata
        value = _find_metadata_in_parents(entry.account, name,
                                          account_metadata)
        if value is not None:
            metadata_to_add[name] = value

    # If no metadata to add, return unchanged
    if not metadata_to_add:
        return entry

    # Create new meta dictionary with inherited metadata
    new_meta = entry.meta.copy()
    new_meta.update(metadata_to_add)

    return entry._replace(meta=new_meta)


def _find_metadata_in_parents(
        account: str, metadata_name: str,
        account_metadata: Dict[str, Dict[str, any]]) -> any:
    """Find metadata value by traversing up the account hierarchy.

    Args:
        account: Account name to start from
        metadata_name: Metadata name to search for
        account_metadata: Dictionary mapping account names to metadata

    Returns:
        Metadata value if found in parent hierarchy, None otherwise
    """
    current_account = account

    while True:
        parent_account = parent(current_account)

        # Stop if we've reached the root (parent returns empty string)
        if not parent_account:
            break

        # Check if parent has this metadata
        if parent_account in account_metadata:
            parent_meta = account_metadata[parent_account]
            if metadata_name in parent_meta:
                return parent_meta[metadata_name]

        # Move up to parent
        current_account = parent_account

    return None
