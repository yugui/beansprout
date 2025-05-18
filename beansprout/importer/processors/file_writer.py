"""File writer processor for saving imported transactions to files.

This module provides the FileWriter processor that writes imported
transactions to files in a destination directory, organized by account
and year-month.
"""

import os
import click
from typing import Dict, List, Tuple

from beancount.core.data import Directive, Entries
from beancount.parser import printer
import beangulp

from beansprout.importer.merge import ImporterType
from beansprout.importer.processors.base import Processor


class FileWriter(Processor):
    """Concrete implementation of Processor that writes entries to files.

    This class implements the process_output method to write entries to files
    in the destination directory, organized by account and year-month.

    Attributes:
        dry_run: Whether to perform a dry run without writing files.
    """

    def get_duplicate(self, entry):
        """Get the duplicate entry from an entry's metadata.
        
        Args:
            entry: The entry to check for duplicate metadata.
            
        Returns:
            The entry itself if it's a duplicate, None otherwise.
        """
        if hasattr(entry,
                   'meta') and entry.meta and '__duplicate__' in entry.meta:
            return entry
        return None

    def __init__(self,
                 importers,
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
        super().__init__(importers, destination, existing_file, reverse,
                         failfast, quiet)
        self.dry_run = dry_run

    def process_output(self, entries_by_account_month: Dict[Tuple[
        str, str], List[Tuple[Directive, ImporterType]]],
                       entries_by_dest_file: Dict[str, Entries]) -> None:
        """Process the output for the extracted and deduplicated entries.

        This method writes entries to files in the destination directory,
        organized by account and year-month following the Beansprout directory
        structure (transactions/[Account Type]/[Account Path]/${YYYYmm}.beancount).
        It handles duplicate entries according to the following rules:
        1. Skip entries that are duplicates with entries in the destination file.
        2. Comment out entries that are duplicates with entries from other files.

        Args:
            entries_by_account_month: Dictionary mapping (account, year_month) tuples to 
                                     lists of (entry, importer) tuples
            entries_by_dest_file: Dictionary mapping destination file paths to lists of existing entries
        """
        for (account, year_month), entry_importer_pairs in sorted(
                entries_by_account_month.items()):
            # Create the destination path using the helper method
            dest_file = self.get_account_file_path(account, year_month)
            dest_dir = os.path.dirname(dest_file)

            # Check if the destination file already exists and has entries
            existing_entries_in_dest = entries_by_dest_file.get(dest_file, [])

            # Process entries - filter out duplicates with existing_entries_in_dest
            # and mark other duplicates for commenting
            processed_entries = []
            regular_count = 0
            commented_count = 0
            skipped_count = 0

            for entry, importer in entry_importer_pairs:
                duplicate_entry = self.get_duplicate(entry)
                if duplicate_entry:
                    # Check if the duplicate entry is in existing_entries_in_dest
                    is_duplicate_with_dest = duplicate_entry in existing_entries_in_dest

                    if is_duplicate_with_dest:
                        # Skip this entry as it's a duplicate with an entry in the destination file
                        skipped_count += 1
                        continue
                    else:
                        # Mark the duplicate entry for commenting out
                        processed_entries.append(
                            (duplicate_entry, True))  # (entry, should_comment)
                        commented_count += 1
                else:
                    # Regular entry
                    processed_entries.append(
                        (entry, False))  # (entry, should_comment)
                    regular_count += 1

            # Combine with existing entries from the destination file
            for entry in existing_entries_in_dest:
                processed_entries.append(
                    (entry, False))  # (entry, should_comment)

            # Sort all entries by date
            processed_entries.sort(key=lambda x: x[0].date,
                                   reverse=self.reverse)

            # Print information
            self.log(
                f"Writing entries ({regular_count} new, {commented_count} duplicates commented, {skipped_count} duplicates skipped) for {account} {year_month} to {dest_file}"
            )

            if self.dry_run:
                # In dry-run mode, print new transactions to stdout if not quiet
                if self.quiet <= 0 and regular_count > 0:
                    click.echo(
                        f"\nNew transactions that would be written to {dest_file}:"
                    )
                    for entry, should_comment in processed_entries:
                        if not should_comment and entry not in existing_entries_in_dest:
                            string = printer.format_entry(entry)
                            click.echo(string)
            else:
                # Create directory if it doesn't exist
                os.makedirs(dest_dir, exist_ok=True)

                # Write entries to file
                with open(dest_file, 'w') as output:
                    output.write(beangulp.extract.HEADER + '\n')
                    output.write(
                        f"; Transactions for {account} {year_month}\n\n")

                    for entry, should_comment in processed_entries:
                        string = printer.format_entry(entry)
                        if should_comment:
                            # Comment out each line of the entry
                            string = '; ' + string.replace('\n', '\n; ')
                        output.write(string)
                        output.write('\n')
