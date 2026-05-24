#!/usr/bin/env python3
"""A plugin that issues errors when transactions or pad directives are posted to non-leaf accounts.

This is a variant of beancount.plugins.leafonly that only restricts transactions
and pad directives on non-leaf accounts, while allowing other directives like
balance assertions.

If you install this plugin, it will issue errors for all non-leaf accounts that have:
- Transaction postings
- Pad directives

Other directives (Balance, Note, Document, etc.) are allowed on non-leaf accounts.
"""

import collections
from typing import Dict, List, Tuple

from beancount.core import data
from beancount.core import getters
from beancount.core import realization

__plugins__ = ("validate_leaf_only", )

LeafOnlyError = collections.namedtuple("LeafOnlyError", "source message entry")


def validate_leaf_only(
        entries: List[data.Directive],
        unused_options_map: Dict) -> Tuple[List[data.Directive], List]:
    """Check for non-leaf accounts that have transactions or pad directives.

    Args:
        entries: A list of directives.
        unused_options_map: An options map.

    Returns:
        A tuple of (entries, errors) where errors is a list of new errors if any were found.
    """
    real_root = realization.realize(entries, compute_balance=False)

    default_meta = data.new_metadata("<leafonly>", 0)
    open_close_map = None  # Lazily computed.
    errors = []

    for real_account in realization.iter_children(real_root):
        if len(real_account) > 0:
            # Filter to only transactions and pad directives
            offending_items = [
                item for item in real_account.txn_postings
                if isinstance(item, (data.TxnPosting, data.Pad))
            ]

            if offending_items:
                # Lazily compute open/close map only if we need it
                if open_close_map is None:
                    open_close_map = getters.get_account_open_close(entries)

                # Get the Open directive for this account if it exists
                try:
                    open_entry = open_close_map[real_account.account][0]
                except KeyError:
                    open_entry = None

                errors.append(
                    LeafOnlyError(
                        open_entry.meta if open_entry else default_meta,
                        "Non-leaf account '{}' has transactions or pad directives on it"
                        .format(real_account.account), open_entry))

    return entries, errors
