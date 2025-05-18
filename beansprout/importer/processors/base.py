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
        """Get the duplicate entry from an entry's metadata.
        
        Args:
            entry: The entry to check for duplicate metadata.
            
        Returns:
            The entry itself if it's a duplicate, None otherwise.
        """
        if hasattr(
                entry, 'meta'
        ) and entry.meta is not None and '__duplicate__' in entry.meta:
            return entry.meta['__duplicate__']
        return None
