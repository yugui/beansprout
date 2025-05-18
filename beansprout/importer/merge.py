#!/usr/bin/env python3
"""Abstract processor for merging extracted transactions with existing files.

This module provides an abstract base class for processing extracted transactions
and merging them with existing files. It implements the core logic of the merge
process while allowing customization of the final output phase.
"""

import os
import abc
import logging
import sys
from typing import Dict, List, Set, Tuple, Optional, TypeVar, Generic

import beangulp
from beancount import loader
from beancount.core import data
from beancount.core.data import Directive, Entries

# Type for importers
ImporterType = TypeVar('ImporterType', bound=beangulp.Importer)


class Processor(abc.ABC, Generic[ImporterType]):
    """Abstract base class for processing and merging extracted transactions.
    
    This class implements the core logic of the merge process (phases 1-5) from
    the beangulp merge command, while leaving the final output phase abstract
    for customization by subclasses.
    
    Attributes:
        importers: List of importers to use for extracting transactions.
        destination: The destination directory for extracted transactions.
        reverse: Whether to sort entries in reverse order.
        failfast: Whether to stop processing at the first error.
        quiet: Level of output suppression.
        log: Logger function for output.
    """

    def __init__(self,
                 importers: List[ImporterType],
                 destination: str,
                 existing_file: str,
                 reverse: bool = False,
                 failfast: bool = False):
        """Initialize the Processor.
        
        Args:
            importers: List of importers to use for extracting transactions.
            destination: The destination directory for extracted transactions.
            existing_file: Path to a Beancount file with existing entries for training.
                           Defaults to "ledger.beancount" in the current directory if it exists.
            reverse: Whether to sort entries in reverse order.
            failfast: Whether to stop processing at the first error.
            quiet: Level of output suppression (0 for normal output, higher for less output).
        """
        self.importers = importers
        self.destination = destination
        self.reverse = reverse
        self.failfast = failfast
        self.logger = logging.getLogger(__name__)
        self.log = beangulp.utils.logger(verbosity=(self.logger.level + 20) //
                                         10)
        self.errors = beangulp.exceptions.ExceptionsTrap(self.log)

        # Load existing entries for training if a file is provided or default exists
        self.existing_entries = []
        if os.path.exists(existing_file):
            try:
                self.existing_entries, _, _ = loader.load_file(existing_file)
                self.logger.debug(
                    f"Loaded {len(self.existing_entries)} existing entries from {existing_file} for training"
                )
            except Exception as e:
                self.logger.warning(f"Could not load {existing_file}: {e}")

    def get_account_file_path(self, account: str, year_month: str) -> str:
        """Construct the file path for an account and year-month based on Beansprout directory structure.
        
        Args:
            account: The account name, e.g., "Assets:Cash:Wallet".
            year_month: The year and month in YYYYMM format.
            
        Returns:
            The file path relative to the destination directory, e.g.,
            "transactions/Assets/Cash/Wallet/202505.beancount".
        """
        # Split the account by colon to get the components
        account_components = account.split(":")
        # Create the path under the "transactions" directory
        path_components = ["transactions"] + account_components
        # Create the directory path
        dir_path = os.path.join(self.destination, *path_components)
        # Return the full file path
        return os.path.join(dir_path, f"{year_month}.beancount")

    def process(self, src: List[str]) -> int:
        """Process source files and merge extracted transactions with existing files.
        
        This method implements the core logic of the merge process:
        1. Walk the source files and extract transactions
        2. Sort the extracted entries
        3. Read existing transactions for each year-month
        4. Deduplicate extracted entries against existing entries
        5. Group entries by account and year-month, preserving importer information
        6. Process output (abstract method to be implemented by subclasses)
        
        Args:
            src: List of source files or directories to process.
            
        Returns:
            An integer status code (0 for success, non-zero for failure).
        """
        # Phase 1: Walk the source files and extract transactions
        extracted, year_months = self._extract_transactions(src)

        # If there are any errors, stop here
        if self.errors:
            self.log('# Errors detected: transactions will not be written.')
            return 1

        # Phase 2: Sort the extracted entries
        beangulp.extract.sort_extracted_entries(extracted)

        # Phase 3: Read existing transactions for each year-month
        existing_entries_by_year_month, entries_by_dest_file = self._read_existing_transactions(
            year_months)

        # Phase 4: Deduplicate extracted entries against existing entries
        self._deduplicate_entries(extracted, existing_entries_by_year_month)

        # Phase 5: Group entries by account and year-month, preserving importer information
        entries_by_account_month = self._group_entries_by_account_month(
            extracted)

        # Phase 6: Process output (abstract method to be implemented by subclasses)
        self.process_output(entries_by_account_month, entries_by_dest_file)

        return 0 if not self.errors else 1

    def _extract_transactions(
        self, src: List[str]
    ) -> Tuple[List[Tuple[str, Entries, str, ImporterType]], Set[str]]:
        """Walk the source files and extract transactions.
        
        Args:
            src: List of source files or directories to process.
            
        Returns:
            A tuple containing:
            - A list of tuples (filename, entries, account, importer)
            - A set of distinct year-months
        """
        extracted = []  # List of (filename, entries, account, importer) tuples
        year_months = set()  # Set of distinct year-months

        for filename in beangulp.utils.walk(src):
            with self.errors:
                self.log(f'* {filename:}', nl=False)
                if os.path.getsize(
                        filename) > beangulp.identify.FILE_TOO_LARGE_THRESHOLD:
                    self.log(' ... SKIP')
                    continue

                importer = beangulp.identify.identify(self.importers, filename)
                if not importer:
                    self.log('')  # Newline.
                    continue

                # Signal processing of this document.
                self.log(' ...', nl=False)

                # Get the account for this file
                account = importer.account(filename)

                # Extract entries from the file, passing existing entries for training
                entries = beangulp.extract.extract_from_file(
                    importer, filename, self.existing_entries)

                if not entries:
                    self.log(' (no entries)')
                    continue

                # Collect year-months from entries
                for entry in entries:
                    year_months.add(entry.date.strftime("%Y%m"))

                # Store the extracted entries
                extracted.append((filename, entries, account, importer))
                self.log(' OK', fg='green')

            if self.failfast and self.errors:
                break

        return extracted, year_months

    def _read_existing_transactions(
        self, year_months: Set[str]
    ) -> Tuple[Dict[str, Entries], Dict[str, Entries]]:
        """Read existing transactions for each year-month.
        
        Args:
            year_months: Set of distinct year-months to read transactions for.
            
        Returns:
            A tuple containing:
            - A dictionary mapping year-months to lists of existing entries
            - A dictionary mapping destination file paths to lists of existing entries
        """
        existing_entries_by_year_month: Dict[str, Entries] = {}
        # Also track entries by destination file path for merging later
        entries_by_dest_file: Dict[str, Entries] = {}

        for year_month in sorted(year_months):
            # Find all beancount files with matching year-month in the destination directory
            existing_entries: Entries = []

            # Look for transactions directory at the root level
            transactions_dir = os.path.join(self.destination, "transactions")
            if os.path.exists(transactions_dir):
                for root, dirs, files in os.walk(transactions_dir):
                    for file in files:
                        existing_file = os.path.join(root, file)
                        try:
                            entries, _, _ = loader.load_file(existing_file)

                            # Store entries by file path for merging later
                            entries_by_dest_file[existing_file] = entries

                            # Add to the collection of all existing entries for deduplication
                            existing_entries.extend(entries)
                            self.logger.debug(
                                f"Loaded {len(entries)} existing entries from {existing_file}"
                            )
                        except Exception as e:
                            self.logger.warning(
                                f'Could not load {existing_file}: {e}')

            existing_entries_by_year_month[year_month] = existing_entries

        return existing_entries_by_year_month, entries_by_dest_file

    def _deduplicate_entries(
            self, extracted: List[Tuple[str, Entries, str, ImporterType]],
            existing_entries_by_year_month: Dict[str, Entries]) -> None:
        """Deduplicate extracted entries against existing entries.
        
        Args:
            extracted: List of tuples (filename, entries, account, importer)
            existing_entries_by_year_month: Dictionary mapping year-months to lists of existing entries
        """
        for filename, entries, account, importer in extracted:
            # Group entries by year-month
            entries_by_year_month: Dict[str, Entries] = {}
            for entry in entries:
                year_month = entry.date.strftime("%Y%m")
                if year_month not in entries_by_year_month:
                    entries_by_year_month[year_month] = []
                entries_by_year_month[year_month].append(entry)

            # Deduplicate entries for each year-month
            for year_month, month_entries in entries_by_year_month.items():
                existing = existing_entries_by_year_month.get(year_month, [])
                # Mark duplicate entries
                importer.deduplicate(month_entries, existing)

                # Note: We keep entries that are marked as duplicates
                # They are marked by setting the '__duplicate__' metadata
                # but we don't remove them here

    def _group_entries_by_account_month(
        self, extracted: List[Tuple[str, Entries, str, ImporterType]]
    ) -> Dict[Tuple[str, str], List[Tuple[Directive, ImporterType]]]:
        """Group entries by account and year-month, preserving importer information.
        
        Args:
            extracted: List of tuples (filename, entries, account, importer)
            
        Returns:
            A dictionary mapping (account, year_month) tuples to lists of (entry, importer) tuples
        """
        entries_by_account_month: Dict[Tuple[str, str],
                                       List[Tuple[Directive,
                                                  ImporterType]]] = {}

        for filename, entries, account, importer in extracted:
            for entry in entries:
                # Note: We keep entries that are marked as duplicates
                year_month = entry.date.strftime("%Y%m")
                key = (account, year_month)
                if key not in entries_by_account_month:
                    entries_by_account_month[key] = []
                entries_by_account_month[key].append((entry, importer))

        return entries_by_account_month

    @abc.abstractmethod
    def process_output(self, entries_by_account_month: Dict[Tuple[
        str, str], List[Tuple[Directive, ImporterType]]],
                       entries_by_dest_file: Dict[str, Entries]) -> None:
        """Process the output for the extracted and deduplicated entries.
        
        This abstract method must be implemented by subclasses to define how
        to process the final output. It corresponds to phase 6 of the merge process.
        
        Args:
            entries_by_account_month: Dictionary mapping (account, year_month) tuples to 
                                     lists of (entry, importer) tuples
            entries_by_dest_file: Dictionary mapping destination file paths to lists of existing entries
        """
        pass
