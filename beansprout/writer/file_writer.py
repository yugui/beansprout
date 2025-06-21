"""File writer for saving imported transactions to files.

This module provides the FileWriter that writes imported
transactions to files in a destination directory, organized by account
and year-month. It preserves text representation when rewriting files,
including comments, free text, and formatting.
"""

import click
import os
from typing import Dict, List, Tuple

from beancount import Directive, Directives
import beangulp

from beansprout.importer.merge import Processor, ImporterType
from beansprout.writer.file_merger import FileMerger


class FileWriter(Processor):
    """Concrete implementation of Processor that writes entries to files.

    This class implements the process_output method to write entries to files
    in the destination directory, organized by account and year-month. It
    preserves text representation when rewriting files, including comments,
    free text, and formatting.

    Attributes:
        dry_run: Whether to perform a dry run without writing files.
        quiet: Level of output suppression (0 for normal output, higher for less output).
    """

    def __init__(self,
                 importers,
                 hooks: List,
                 destination=None,
                 existing_file=None,
                 reverse=False,
                 failfast=False,
                 quiet=0,
                 dry_run=False):
        """Initialize the FileWriter.

        Args:
            importers: List of importers to use for extracting transactions.
            destination: The destination directory for extracted transactions.
            existing_file: Path to a Beancount file with existing entries for training.
                           Defaults to "ledger.beancount" in the current directory if it exists.
            reverse: Whether to sort entries in reverse order.
            failfast: Whether to stop processing at the first error.
            quiet: Level of output suppression (0 for normal output, higher for less output).
            dry_run: Whether to perform a dry run without writing files.
        """
        super().__init__(importers, hooks, destination, existing_file, reverse,
                         failfast)
        self.dry_run = dry_run
        self.quiet = quiet
        self.file_merger = FileMerger(quiet=quiet, reverse=reverse)

    def process_output(
        self, entries_by_account_month: Dict[Tuple[str, str],
                                             List[Tuple[Directive,
                                                        ImporterType]]]
    ) -> None:
        for (account, year_month
             ), entry_importer_pairs in entries_by_account_month.items():
            dest_file = self.get_account_file_path(account, year_month)
            if self.quiet == 0:
                if self.dry_run:
                    click.echo(f"Dry run: would write to {dest_file}")
                else:
                    click.echo(f"Writing to {dest_file}")

            # Use the FileMerger to merge entries
            counter_new, counter_commented, counter_duplicate = self.file_merger.merge_entries(
                dest_file=dest_file,
                entry_importer_pairs=entry_importer_pairs,
                dry_run=self.dry_run)

            # Report progress
            if self.quiet == 0:
                click.echo(
                    f"Processing {len(entry_importer_pairs)} entries for {account} "
                    f"({year_month}): {counter_new} new, "
                    f"{counter_commented} commented, "
                    f"{counter_duplicate} duplicates.")
