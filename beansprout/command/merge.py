"""Merge command for Beansprout.

This module provides the Merge class that combines the functionality of the
abstract Processor class and the concrete FileWriter class to provide a complete
implementation of the merge process, from extraction to file writing with text
preservation.
"""

import os
import logging
import sys
from typing import Dict, List, Set, Tuple, Optional, TypeVar, Generic

import click
import beancount
import beangulp
from beancount import Directive, Directives

from beansprout.importer.types import ImporterType
from beansprout.writer.file_merger import FileMerger


class Merge(Generic[ImporterType]):
    """Processor for merging extracted transactions with existing files.
    
    This class combines the functionality of the abstract Processor class and the
    concrete FileWriter class to provide a complete implementation of the merge
    process, from extraction to file writing with text preservation.
    
    Attributes:
        importers: List of importers to use for extracting transactions.
        hooks: List of hooks to apply to extracted entries.
        destination: The destination directory for extracted transactions.
        existing_file: Path to a Beancount file with existing entries for training.
        reverse: Whether to sort entries in reverse order.
        failfast: Whether to stop processing at the first error.
        quiet: Level of output suppression.
        dry_run: Whether to perform a dry run without writing files.
        file_merger: FileMerger instance for merging entries into files.
    """

    def __init__(self,
                 importers: List[ImporterType],
                 hooks: List,
                 destination: str = None,
                 existing_file: str = None,
                 reverse: bool = False,
                 failfast: bool = False,
                 quiet: int = 0,
                 dry_run: bool = False):
        """Initialize the Merge class.
        
        Args:
            importers: List of importers to use for extracting transactions.
            hooks: List of hooks to apply to extracted entries.
            destination: The destination directory for extracted transactions.
            existing_file: Path to a Beancount file with existing entries for training.
                           Defaults to "ledger.beancount" in the current directory if it exists.
            reverse: Whether to sort entries in reverse order.
            failfast: Whether to stop processing at the first error.
            quiet: Level of output suppression (0 for normal output, higher for less output).
            dry_run: Whether to perform a dry run without writing files.
        """
        self.importers = importers
        self.hooks = hooks
        self.destination = destination
        self.reverse = reverse
        self.failfast = failfast
        self.quiet = quiet
        self.dry_run = dry_run
        self.logger = logging.getLogger(__name__)
        self.log = beangulp.utils.logger(verbosity=(self.logger.level + 20) //
                                         10)
        self.errors = beangulp.exceptions.ExceptionsTrap(self.log)
        self.file_merger = FileMerger(quiet=quiet, reverse=reverse)

        # Load existing entries for training if a file is provided or default exists
        self.existing_entries = []
        if existing_file and os.path.exists(existing_file):
            try:
                self.existing_entries, _, _ = beancount.load_file(
                    existing_file)
                self.logger.debug(
                    f"Loaded {len(self.existing_entries)} existing entries from {existing_file} for training"
                )
            except Exception as e:
                self.logger.warning(f"Could not load {existing_file}: {e}")

    def process(self, src: List[str]) -> int:
        """Process source files and merge extracted transactions with existing files.
        
        This method implements the complete merge process:
        1. Walk the source files and extract transactions
        2. Sort the extracted entries
        3. Deduplicate extracted entries against existing entries
        4. Apply hooks to the extracted entries
        5. Group entries by account and year-month
        6. Process output by writing entries to files
        
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

        # Phase 3: Deduplicate extracted entries against existing entries
        self._mark_duplicate_entries(extracted)

        # Phase 4: Apply hooks to the extracted entries
        for func in self.hooks:
            extracted = func(extracted, self.existing_entries)

        # Phase 5: Group entries by account and year-month, preserving importer information
        entries_by_account_month = self._group_entries_by_account_month(
            extracted)

        # Phase 6: Process output by writing entries to files
        self._write_files(entries_by_account_month)

        return 0 if not self.errors else 1

    def _extract_transactions(
        self, src: List[str]
    ) -> Tuple[List[Tuple[str, Directives, str, ImporterType]], Set[str]]:
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

    def _mark_duplicate_entries(self,
                                extracted: List[Tuple[str, Directives, str,
                                                      ImporterType]]):
        """Deduplicate extracted entries against existing entries.
        
        Args:
            extracted: List of tuples (filename, entries, account, importer)
        """
        existing_entries = self.existing_entries.copy()
        for filename, entries, account, importer in extracted:
            # Mark duplicate entries
            importer.deduplicate(entries, existing_entries)
            existing_entries.extend(entries)

    def _group_entries_by_account_month(
        self, extracted: List[Tuple[str, Directives, str, ImporterType]]
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

    def _write_files(
        self, entries_by_account_month: Dict[Tuple[str, str],
                                             List[Tuple[Directive,
                                                        ImporterType]]]
    ) -> None:
        """Write the extracted and deduplicated entries to files.
        
        Args:
            entries_by_account_month: Dictionary mapping (account, year_month) tuples to 
                                     lists of (entry, importer) tuples
        """
        for (account, year_month
             ), entry_importer_pairs in entries_by_account_month.items():
            dest_file = self._get_account_file_path(account, year_month)
            if self.quiet == 0:
                if self.dry_run:
                    click.echo(f"Dry run: would write to {dest_file}")
                else:
                    click.echo(f"Writing to {dest_file}")

            # Use the FileMerger to merge entries
            self.file_merger.merge_entries(
                dest_file=dest_file,
                entry_importer_pairs=entry_importer_pairs,
                dry_run=self.dry_run)

    def _get_account_file_path(self, account: str, year_month: str) -> str:
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
