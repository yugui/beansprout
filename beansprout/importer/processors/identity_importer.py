"""Identity importer for importing transactions from .beancount files.

This module provides the IdentityImporter class that imports transactions
from .beancount files. It follows the API of the beangulp.importer module.
"""

import os
from typing import List, Optional

import beangulp
from beancount import load_file
from beancount.core import data


class IdentityImporter(beangulp.Importer):
    """Importer for .beancount files.
    
    This importer reads transactions from .beancount files and imports them
    as-is. It's useful for importing transactions from existing beancount files.
    
    Attributes:
        account_name: The account name to associate with imported transactions.
    """

    def __init__(self, account_name: str):
        """Initialize the IdentityImporter.
        
        Args:
            account_name: The account name to associate with imported transactions.
        """
        self.account_name = account_name

    def identify(self, file_path: str) -> bool:
        """Identify if this importer can handle the given file.
        
        Args:
            file_path: The path to the file to check.
            
        Returns:
            True if the file is a .beancount file, False otherwise.
        """
        return file_path.endswith('.beancount')

    def account(self, file_path: str) -> str:
        """Return the account associated with the given file.
        
        Args:
            file_path: The path to the file.
            
        Returns:
            The account name provided in the constructor.
        """
        return self.account_name

    def extract(self,
                file_path: str,
                existing_entries=None) -> List[data.Directive]:
        """Extract transactions from the given file.
        
        Args:
            file_path: The path to the file to extract transactions from.
            existing_entries: Optional list of existing entries for training.
            
        Returns:
            A list of extracted directives.
        """
        entries, _, _ = load_file(file_path)
        return entries
