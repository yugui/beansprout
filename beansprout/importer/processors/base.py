"""Base processor for handling imported transaction data.

This module provides a base class for processors that process imported
transaction data.
"""

from typing import Optional
from beancount.core.data import Directive
from beansprout.importer.merge import Processor as BaseProcessor


class Processor(BaseProcessor):
    """Base class for processors that process imported transaction data."""

    def get_duplicate(self, entry: Directive) -> Optional[Directive]:
        """Get the duplicate entry if it exists.

        Args:
            entry: The entry to check for duplicates.

        Returns:
            The duplicate entry if found, None otherwise.
        """
        if hasattr(
                entry, 'meta'
        ) and entry.meta is not None and '__duplicate__' in entry.meta:
            return entry.meta['__duplicate__']
        return None
