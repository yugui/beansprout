#!/usr/bin/env python3
"""Plugin to infer metadata for directives from other metadata within the same directive.

This plugin allows you to automatically populate metadata fields based on values from
other metadata fields, either by direct copying or by looking up values in a mapping table.

Configuration format (one rule per line):
    <directive_type> <target_metadata> <source_metadata> [file:mapping.yaml]

Where:
- directive_type: Type of directive (open, close, balance, pad, document, commodity, transaction)
- target_metadata: Name of metadata field to populate
- source_metadata: Name of metadata field to copy from, or special values:
  - __commodity__: The commodity name (for Commodity directives)
  - __account__: The short account name (for Open/Close/Balance/Pad/Document directives)
- file:mapping.yaml: Optional YAML file with value mappings (relative to beancount file)

Rules:
- Lines starting with or containing ';' are treated as comments (text after ';' is ignored)
- Leading/trailing whitespace is stripped
- All matching rules are applied in order
- If target metadata already exists, inference is skipped
- Missing keys in mapping tables generate errors

Usage:
    plugin "beansprout.plugins.infer_metadata" "
      ; Infer commodity unit from commodity name
      commodity unit __commodity__
      ; Infer account name from account
      open name __account__
      ; Lookup volatility from account-class via YAML mapping
      open volatility account-class file:volatility.yaml
      ; Copy transaction id from uuid metadata
      transaction id uuid
    "

Example mapping file (volatility.yaml):
    checking: low
    savings: low
    stocks: high
"""

import collections
import os
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

import yaml

from beancount.core import account as account_module
from beancount.core import data

__plugins__ = ("infer_metadata", )

InferMetadataError = collections.namedtuple("InferMetadataError",
                                            "source message entry")


class InferenceRule(NamedTuple):
    """A single inference rule."""
    directive_type: str  # e.g., "open", "commodity", "transaction"
    target_metadata: str
    source_metadata: str
    mapping_file: Optional[str]  # None for direct copy, file path for lookup


def infer_metadata(entries: List[data.Directive],
                   options_map: Dict,
                   config: str = "") -> Tuple[List[data.Directive], List]:
    """Infer metadata for directives based on other metadata within the same directive.

    Args:
        entries: List of Beancount entries
        options_map: Beancount options map
        config: Multiline string with inference rules

    Returns:
        Tuple of (transformed_entries, errors)
    """
    # Parse configuration to get inference rules
    rules = _parse_config(config)

    if not rules:
        # No rules specified, return entries unchanged
        return entries, []

    # Get the directory of the main beancount file for resolving relative paths
    beancount_dir = os.path.dirname(options_map["filename"])

    # Load all mapping tables
    mapping_tables: Dict[str, Dict[str, Any]] = {}
    errors = []

    for rule in rules:
        if rule.mapping_file and rule.mapping_file not in mapping_tables:
            # Resolve relative path
            mapping_path = os.path.join(beancount_dir, rule.mapping_file)
            try:
                with open(mapping_path, 'r') as f:
                    mapping_tables[rule.mapping_file] = yaml.safe_load(f)
            except FileNotFoundError:
                meta = data.new_metadata("<infer_metadata>", 0)
                errors.append(
                    InferMetadataError(
                        meta, f"Mapping file not found: {rule.mapping_file}",
                        None))
            except yaml.YAMLError as e:
                meta = data.new_metadata("<infer_metadata>", 0)
                errors.append(
                    InferMetadataError(
                        meta,
                        f"Error parsing YAML file {rule.mapping_file}: {e}",
                        None))

    # If there were errors loading mapping files, return early
    if errors:
        return entries, errors

    # Group rules by directive type for efficient lookup
    rules_by_type: Dict[str, List[InferenceRule]] = {}
    for rule in rules:
        if rule.directive_type not in rules_by_type:
            rules_by_type[rule.directive_type] = []
        rules_by_type[rule.directive_type].append(rule)

    # Transform entries by applying inference rules
    transformed_entries = []

    for entry in entries:
        # Get directive type name (lowercase)
        directive_type = type(entry).__name__.lower()

        # Check if there are rules for this directive type
        if directive_type in rules_by_type:
            entry, new_errors = _apply_rules(entry,
                                             rules_by_type[directive_type],
                                             mapping_tables)
            errors.extend(new_errors)

        transformed_entries.append(entry)

    return transformed_entries, errors


def _parse_config(config: str) -> List[InferenceRule]:
    """Parse configuration string into inference rules.

    Args:
        config: Multiline string with inference rules

    Returns:
        List of InferenceRule objects
    """
    if not config:
        return []

    rules = []
    for line in config.strip().split('\n'):
        # Strip leading/trailing whitespace
        line = line.strip()

        # Skip empty lines
        if not line:
            continue

        # Remove comments (everything after semicolon)
        if ';' in line:
            line = line[:line.index(';')].strip()

        # Skip if line became empty after removing comments
        if not line:
            continue

        # Parse rule: <type> <target> <source> [file:mapping]
        parts = line.split()
        if len(parts) < 3:
            # Invalid rule, skip
            continue

        directive_type = parts[0]
        target_metadata = parts[1]
        source_metadata = parts[2]
        mapping_file = None

        if len(parts) >= 4 and parts[3].startswith("file:"):
            mapping_file = parts[3][5:]  # Remove "file:" prefix

        rules.append(
            InferenceRule(directive_type, target_metadata, source_metadata,
                          mapping_file))

    return rules


def _apply_rules(
        entry: data.Directive, rules: List[InferenceRule],
        mapping_tables: Dict[str, Dict[str,
                                       Any]]) -> Tuple[data.Directive, List]:
    """Apply inference rules to a single directive.

    Args:
        entry: The directive to transform
        rules: List of rules to apply
        mapping_tables: Dictionary of loaded mapping tables

    Returns:
        Tuple of (transformed_entry, errors)
    """
    errors = []
    new_meta = entry.meta.copy()

    for rule in rules:
        if rule.target_metadata in new_meta:
            continue

        # Get source value (using accumulated new_meta to see changes from previous rules)
        source_value = _get_source_value(entry, rule.source_metadata, new_meta)

        if source_value is None:
            # Source metadata doesn't exist, skip
            continue

        # Apply mapping if specified
        if rule.mapping_file:
            mapping = mapping_tables.get(rule.mapping_file)
            if mapping is None:
                # Mapping table not loaded (error already reported)
                continue

            if source_value not in mapping:
                # Lookup failed - report error
                errors.append(
                    InferMetadataError(
                        entry.meta,
                        f"Key '{source_value}' not found in mapping file {rule.mapping_file}",
                        entry))
                continue

            target_value = mapping[source_value]
        else:
            # Direct copy
            target_value = source_value

        # Set target metadata
        new_meta[rule.target_metadata] = target_value

    # If metadata was modified, create new entry
    if new_meta != entry.meta:
        return entry._replace(meta=new_meta), errors
    else:
        return entry, errors


def _get_source_value(entry: data.Directive, source_metadata: str,
                      metadata: Dict[str, Any]) -> Optional[Any]:
    """Get the source value for inference.

    Args:
        entry: The directive
        source_metadata: The source metadata name or special value
        metadata: The metadata dictionary to lookup from (may include changes from previous rules)

    Returns:
        The source value, or None if not available
    """
    # Handle special source metadata
    if source_metadata == "__commodity__":
        if isinstance(entry, data.Commodity):
            return entry.currency
        return None

    if source_metadata == "__account__":
        if isinstance(
                entry,
            (data.Open, data.Close, data.Balance, data.Pad, data.Document)):
            return account_module.leaf(entry.account)
        return None

    # Regular metadata lookup
    return metadata.get(source_metadata)
