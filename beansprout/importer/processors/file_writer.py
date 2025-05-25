"""File writer processor for saving imported transactions to files.

This module provides the FileWriter processor that writes imported
transactions to files in a destination directory, organized by account
and year-month. It preserves text representation when rewriting files,
including comments, free text, and formatting.
"""

import bisect
import click
from dataclasses import dataclass, field
import datetime
import os
from typing import Dict, List, Tuple, Optional

from beancount import Directive, Directives
from beancount.core.data import Transaction
import beangulp

from beansprout.importer.merge import Processor, ImporterType
from beansprout.importer.processors.text_preserving_parser import parse_file
from beansprout.importer.processors.types import (BlockType, Block,
                                                  EntryWithLines,
                                                  CommentedEntryWithLines,
                                                  NonEntryBlock, NewEntryBlock)


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

    def _get_duplicate(self, entry: Directive) -> Optional[Directive]:
        """Get the duplicate entry from an entry's metadata.
        
        Args:
            entry: The entry to check for duplicate metadata.
            
        Returns:
            The entry itself if it's a duplicate, None otherwise.
        """
        if entry.meta and '__duplicate__' in entry.meta:
            return entry.meta['__duplicate__']
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
                         failfast)
        self.dry_run = dry_run
        self.quiet = quiet

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

            merged_blocks = self._process_single_file(dest_file,
                                                      entry_importer_pairs,
                                                      account, year_month)

            if self.dry_run:
                if self.quiet > 0:
                    continue
                for block in merged_blocks:
                    if not isinstance(block, NewEntryBlock):
                        continue
                    click.echo(str(block))
                continue

            os.makedirs(os.path.dirname(dest_file), exist_ok=True)
            with open(dest_file, 'w') as f:
                for block in merged_blocks:
                    f.write(str(block))

    def _process_single_file(self, dest_file: str,
                             entry_importer_pairs: List[Tuple[Directive,
                                                              ImporterType]],
                             account: str, year_month: str) -> None:
        counter_new = 0
        counter_commented = 0
        counter_duplicate = 0

        existing_blocks = parse_file(dest_file)
        commented_entries: Directives = [
            block.entry for block in existing_blocks
            if block.type == BlockType.COMMENTED_ENTRY
        ]

        new_blocks: List[NewEntryBlock] = []
        for (entry, importer) in entry_importer_pairs:
            duplicate = self._get_duplicate(entry)
            if not duplicate:
                counter_new += 1
                new_blocks.append(
                    NewEntryBlock(entry=entry, should_comment=False))
                continue

            if duplicate.meta['filename'] == dest_file:
                counter_duplicate += 1
                continue  # Skip entries that are already in the file

            # Try de-duplicating again to compare with the commented entries
            importer.deduplicate([entry], commented_entries)
            duplicate = self._get_duplicate(entry)
            if duplicate and duplicate.meta['filename'] == dest_file:
                # If the duplicate is already in the file, skip it
                counter_duplicate += 1
                continue

            counter_commented += 1
            new_blocks.append(NewEntryBlock(entry=entry, should_comment=True))

        if self.quiet == 0:
            click.echo(
                f"Processing {len(entry_importer_pairs)} entries for {account} "
                f"({year_month}): {counter_new} new, "
                f"{counter_commented} commented, "
                f"{counter_duplicate} duplicates.")
        # Try to insert entries into blocks without changeing the order of blocks
        # even when the original blocks in the dest_file are not sorted.

        @dataclass
        class DatedBlock:
            block: Block
            date: datetime.date
            reverse: bool

            def __lt__(self, other: 'DatedEntry') -> bool:
                if self.reverse:
                    return self.date > other.date
                return self.date < other.date

        current_date = datetime.date.max if self.reverse else datetime.date.min
        dated_blocks: List[DatedBlock] = []
        merged_blocks: List[Block] = []
        for block in existing_blocks:
            if hasattr(block, 'entry'):
                current_date = block.entry.date
            dated_blocks.append(DatedBlock(block, current_date, self.reverse))
            merged_blocks.append(block)

        for block in new_blocks:
            date = block.entry.date
            # Try to indentify the insertion point by the date of the block
            if self.reverse:
                index = bisect.bisect_left(
                    dated_blocks, DatedBlock(block, date, self.reverse))
            else:
                index = bisect.bisect_right(
                    dated_blocks, DatedBlock(block, date, self.reverse))

            if index == 0:
                block.start_line = -1
            else:
                block.start_line = dated_blocks[index - 1].block.end_line

            merged_blocks.append(block)

        return sorted(merged_blocks, key=lambda b: b.start_line)
