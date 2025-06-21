"""File merger for merging entries into destination files.

This module provides the FileMerger class that handles the merging of entries
into destination files. It uses the FileRewriter class to handle the actual
file rewriting mechanics and provides a clean API for merging entries.
"""

import bisect
import click
from dataclasses import dataclass
import datetime
from typing import Callable, List, Optional, Tuple, NamedTuple

from beancount import Directive, Directives, format_entry
from beancount.core.data import Transaction

from beansprout.importer.types import ImporterType
from beansprout.writer.file_rewriter import FileRewriter
from beansprout.writer.types import (BlockType, Block, EntryWithLines,
                                     CommentedEntryWithLines, NonEntryBlock,
                                     NewEntryBlock)

EntryImporterPair = Tuple[Directive, ImporterType]


class FileMerger:
    """Class responsible for merging entries into a destination file.
    
    This class handles the core merge logic for determining which entries to add,
    which to comment out, and which to skip, as well as managing the insertion
    of entries at the appropriate positions.
    
    Attributes:
        quiet: Level of output suppression (0 for normal output, higher for less output).
        reverse: Whether to sort entries in reverse order.
    """

    def __init__(self, quiet: int = 0, reverse: bool = False):
        """Initialize the FileMerger.
        
        Args:
            quiet: Level of output suppression (0 for normal output, higher for less output).
            reverse: Whether to sort entries in reverse order.
        """
        self.quiet = quiet
        self.reverse = reverse
        self.file_rewriter = FileRewriter(quiet=quiet)

    def merge_entries(self,
                      dest_file: str,
                      entry_importer_pairs: List[EntryImporterPair],
                      dry_run: bool = False):
        """Merge entries into a destination file.
        
        Args:
            dest_file: The destination file to merge entries into.
            entry_importer_pairs: List of (entry, importer) pairs to merge.
            dry_run: Whether to perform a dry run without writing files.
            
        Returns:
            A tuple of (new_count, commented_count, duplicate_count) indicating
            the number of entries added as new, commented, or skipped as duplicates.
        """
        # Create a transformation function for this file
        transform_blocks = self._create_transform_function(
            entry_importer_pairs=entry_importer_pairs, dest_file=dest_file)

        # Use the FileRewriter to rewrite the file
        self.file_rewriter.rewrite_file(dest_file=dest_file,
                                        transform_blocks=transform_blocks,
                                        dry_run=dry_run)

        # In dry run mode with quiet=0, print the transaction details directly
        if dry_run and self.quiet == 0:
            for (entry, _) in entry_importer_pairs:
                duplicate = self._get_duplicate(entry)
                if duplicate and duplicate.meta['filename'] == dest_file:
                    continue  # Skip entries that are already in the file
                click.echo(format_entry(entry))

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

    def _create_transform_function(
            self, entry_importer_pairs: List[EntryImporterPair],
            dest_file: str) -> Callable[[List[Block]], List[Block]]:
        """Create a transformation function for the given entries.
        
        Args:
            entry_importer_pairs: List of (entry, importer) pairs to process.
            dest_file: The destination file to merge entries into.
            
        Returns:
            - A function that takes a list of blocks and returns a transformed list.
        """

        def transform_blocks(existing_blocks: List[Block]) -> List[Block]:
            counter_new = 0
            counter_commented = 0
            counter_duplicate = 0

            existing_entries: Directives = [
                block.entry for block in existing_blocks
                if block.type in [BlockType.COMMENTED_ENTRY, BlockType.ENTRY]
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

                # Temporarily reset the duplicate metadata before the re-deduplication
                orig_duplicate = duplicate
                del entry.meta['__duplicate__']
                # Try de-duplicating again to compare with the existing entries
                importer.deduplicate([entry], existing_entries)
                duplicate = self._get_duplicate(entry)
                if duplicate and duplicate.meta['filename'] == dest_file:
                    # If the duplicate is already in the file, skip it
                    counter_duplicate += 1
                    continue
                # Restore the original duplicate metadata as it may be needed later
                entry.meta['__duplicate__'] = orig_duplicate

                counter_commented += 1
                new_blocks.append(
                    NewEntryBlock(entry=entry, should_comment=True))

            # Try to insert entries into blocks without changing the order of blocks
            # even when the original blocks in the dest_file are not sorted.
            @dataclass
            class DatedBlock:
                block: Block
                date: datetime.date
                reverse: bool

                def __lt__(self, other: 'DatedBlock') -> bool:
                    if self.reverse:
                        return self.date > other.date
                    return self.date < other.date

            current_date = datetime.date.max if self.reverse else datetime.date.min
            dated_blocks: List[DatedBlock] = []
            merged_blocks: List[Block] = []
            for block in existing_blocks:
                if hasattr(block, 'entry'):
                    current_date = block.entry.date
                dated_blocks.append(
                    DatedBlock(block, current_date, self.reverse))
                merged_blocks.append(block)

            for block in new_blocks:
                date = block.entry.date
                # Try to identify the insertion point by the date of the block
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

            if self.quiet == 0:
                click.echo(f"Added {counter_new} new entries, "
                           f"{counter_commented} commented out, "
                           f"{counter_duplicate} duplicates skipped.")

            return sorted(merged_blocks, key=lambda b: b.start_line)

        return transform_blocks
