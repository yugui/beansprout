"""Text preserving parser for Beancount files.

This module provides a parser that preserves the original text representation
of Beancount files, including comments, free text, and formatting.

The parser uses a state pattern to handle different types of content in Beancount files:

State Transition Map:
```mermaid
stateDiagram-v2
    [*] --> InitialState
    
    InitialState --> EntryState: Found entry
    InitialState --> CommentedEntryState: Found commented entry
    InitialState --> CommentBlockState: Found comment
    InitialState --> NonEntryBlockState: Found other content
    
    CommentBlockState --> EntryState: Found entry
    CommentBlockState --> CommentedEntryState: Found commented entry
    CommentBlockState --> NonEntryBlockState: Found non-comment content
    CommentBlockState --> CommentBlockState: Found more comments
    
    CommentedEntryState --> EntryState: Found entry
    CommentedEntryState --> CommentedEntryState: Found continuation of commented entry
    CommentedEntryState --> CommentBlockState: Found comment
    CommentedEntryState --> NonEntryBlockState: Found other content
    
    NonEntryBlockState --> EntryState: Found entry
    NonEntryBlockState --> CommentedEntryState: Found commented entry
    NonEntryBlockState --> CommentBlockState: Found comment
    NonEntryBlockState --> NonEntryBlockState: Found more non-entry content
    
    EntryState --> EntryState: Found entry
    EntryState --> CommentedEntryState: Found commented entry
    EntryState --> CommentBlockState: Found comment
    EntryState --> NonEntryBlockState: Found blank line or other content
    EntryState --> EntryState: Found continuation of entry
```

The parser processes each line of the file and transitions between states based on the content
of the line. Each state handles its specific parsing logic and determines the next state.
This approach allows for more maintainable and extensible code compared to a monolithic parsing approach.
"""

import os
import io
import logging
import re
from typing import List, Optional, Tuple

import beancount
from beancount import Directive, Directives
from beancount.parser import parser

from beansprout.writer.types import (BlockType, Block, EntryWithLines,
                                     CommentedEntryWithLines, NonEntryBlock)

COMMENTED_ENTRY_PATTERN = re.compile(
    r'^(\s*;\s*)\d{4}-\d{2}-\d{2}\s+\S+\s*\S+')
ENTRY_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}\s+\S+\s*\S+')


class ParserState:
    """Base class for parser states."""

    def __init__(self, parser: 'TextPreservingParser'):
        """Initialize the state.
        
        Args:
            parser: The TextPreservingParser instance
        """
        self.parser = parser

        parser.logger.debug(f"Entering: {self.__class__.__name__}")

    def process_line(self, line: str, lineno: int) -> 'ParserState':
        """Process the current line and return the next state.
        
        Args:
            line: The current line to process
            lineno: The line number of the current line
            
        Returns:
            The next state to transition to
        """
        raise NotImplementedError

    def finalize(self) -> None:
        """Finalize the state
        
        The key purpose of this method is to add the block being built to the
        parse result.
        """
        pass

    def _match_next_entry(self, line: str, lineno: int) -> Optional[Directive]:
        """Check if the next entry matches the current line."""
        if not self.parser.existing_entries:
            return None

        next_entry = self.parser.existing_entries[-1]
        if next_entry.meta['lineno'] != lineno:
            return None

        if not ENTRY_PATTERN.match(line):
            raise ValueError(
                f"Expected entry at line {lineno}, but got: {line}")

        return self.parser.existing_entries.pop()


class InitialState(ParserState):
    """Initial state for the parser."""

    def process_line(self, line: str, lineno: int) -> ParserState:
        """Process the current line and return the next state.
        
        Args:
            line: The current line to process
            lineno: The line number of the current line
            
        Returns:
            The next state to transition to
        """
        found_entry = self._match_next_entry(line, lineno)
        if found_entry:
            return EntryState(
                parser=self.parser,
                entry=found_entry,
                block_start=lineno,
                block_lines=[line],
            )

        if line.lstrip().startswith(';'):
            if COMMENTED_ENTRY_PATTERN.match(line):
                return CommentedEntryState(
                    parser=self.parser,
                    block_start=lineno,
                    block_lines=[line],
                )
            else:
                return CommentBlockState(
                    parser=self.parser,
                    block_start=lineno,
                    block_lines=[line],
                )

        # Transition to EntryState should have been covered by the entry_state check

        return NonEntryBlockState(parser=self.parser,
                                  block_start=lineno,
                                  block_lines=[line])


class CommentBlockState(ParserState):
    """State for parsing comment blocks."""

    def __init__(self, parser: 'TextPreservingParser', block_start: int,
                 block_lines: List[str]):
        """Initialize the state.
        
        Args:
            parser: The TextPreservingParser instance
            block_start: The line number where the block starts
            block_lines: The lines collected so far for this block
        """
        super().__init__(parser)
        self.block_start = block_start
        self.block_lines = block_lines

    def process_line(self, line: str, lineno: int) -> ParserState:
        """Process the current line and return the next state.
        
        Args:
            line: The current line to process
            lineno: The line number of the current line
            
        Returns:
            The next state to transition to
        """
        found_entry = self._match_next_entry(line, lineno)
        if found_entry:
            # We do not need to finalize the current block here
            # because it is a comment attached to the next entry
            self.block_lines.append(line)
            return EntryState(
                parser=self.parser,
                entry=found_entry,
                block_start=self.block_start,
                block_lines=self.block_lines,
            )

        if line.lstrip().startswith(';'):
            self.block_lines.append(line)

            # Check if it's a commented entry
            if COMMENTED_ENTRY_PATTERN.match(line):
                # We do not need to finalize the current block here
                # because it is a comment attached to the next commented entry
                return CommentedEntryState(
                    parser=self.parser,
                    block_start=self.block_start,
                    block_lines=self.block_lines,
                )
            else:
                # Continue collecting comment lines
                return self

        # End of comment block, add it to parser
        self.finalize()

        # Transition to EntryState should have been covered by the entry_state check

        return NonEntryBlockState(parser=self.parser,
                                  block_start=lineno,
                                  block_lines=[line])

    def finalize(self) -> None:
        self.parser.parsed_blocks.append(
            NonEntryBlock(
                start_line=self.block_start,
                original_lines=self.block_lines,
                type=BlockType.COMMENT,
            ))


class CommentedEntryState(ParserState):
    """State for parsing commented-out entries."""

    def __init__(self, parser: 'TextPreservingParser', block_start: int,
                 block_lines: List[str]):
        """Initialize the state.
        
        Args:
            parser: The TextPreservingParser instance
            block_start: The line number where the entry starts
            block_lines: The lines collected so far for this entry
        """
        super().__init__(parser)
        self.block_start = block_start
        self.block_lines = block_lines

        m = COMMENTED_ENTRY_PATTERN.match(block_lines[-1])
        if not m:
            raise ValueError("Invalid commented entry format")
        self.prefix = m.group(1)

    def process_line(self, line: str, lineno: int) -> ParserState:
        """Process the current line and return the next state.
        
        Args:
            line: The current line to process
            lineno: The line number of the current line
            
        Returns:
            The next state to transition to
        """
        found_entry = self._match_next_entry(line, lineno)
        if found_entry:
            self.finalize()
            return EntryState(
                parser=self.parser,
                entry=found_entry,
                block_start=lineno,
                block_lines=[line],
            )

        if COMMENTED_ENTRY_PATTERN.match(line):
            # This is the next commented entry
            self.finalize()
            return CommentedEntryState(
                parser=self.parser,
                block_start=lineno,
                block_lines=[line],
            )

        if line.startswith(self.prefix) and line[len(self.prefix)].isspace():
            # This is a metadata, a posting, or an inline comment in the commented entry
            self.block_lines.append(line)
            return self
        if line[0].isspace() and line.lstrip().startswith(';'):
            # This is an inline comment in the commented entry
            self.block_lines.append(line)
            return self

        self.finalize()

        if line.lstrip().startswith(';'):
            return CommentBlockState(
                self.parser,
                lineno,
                [line],
            )

        return NonEntryBlockState(
            parser=self.parser,
            block_start=lineno,
            block_lines=[line],
        )

    def finalize(self) -> None:
        uncommented_lines = [
            line[len(self.prefix):] for line in self.block_lines
        ]
        as_bytes = ''.join(uncommented_lines).encode('utf-8')
        file = io.BytesIO(as_bytes)
        entries, errors, _ = parser.parse_file(
            file,
            report_filename=self.parser.file_path,
            report_firstline=self.block_start)

        if errors:
            self.parser.logger.info(
                f"Errors while parsing commented entry at line {self.block_start}"
            )
            for error in errors:
                logging.warning(error.message)

        if not entries:
            self.parser.logger.warning(
                f"Failed to parse commented entry for unknown reasons: {self.block_start}"
            )
            self.parser.parsed_blocks.append(
                NonEntryBlock(
                    start_line=self.block_start,
                    original_lines=self.block_lines,
                    type=BlockType.COMMENT,
                ))

        for entry in entries:
            self.parser.parsed_blocks.append(
                CommentedEntryWithLines(
                    entry=entry,
                    start_line=self.block_start,
                    original_lines=self.block_lines,
                ))


class NonEntryBlockState(ParserState):
    """State for parsing non-entry content like free text and blank lines."""

    def __init__(self, parser: 'TextPreservingParser', block_start: int,
                 block_lines: List[str]):
        """Initialize the state.
        
        Args:
            parser: The TextPreservingParser instance
            block_start: The line number where the block starts
            block_lines: The lines collected so far for this block
        """
        super().__init__(parser)
        self.block_start = block_start
        self.block_lines = block_lines

    def process_line(self, line: str, lineno: int) -> ParserState:
        """Process the current line and return the next state.
        
        Args:
            line: The current line to process
            lineno: The line number of the current line
            
        Returns:
            The next state to transition to
        """
        found_entry = self._match_next_entry(line, lineno)
        if found_entry:
            self.finalize()
            return EntryState(
                parser=self.parser,
                entry=found_entry,
                block_start=lineno,
                block_lines=[line],
            )

        if line.lstrip().startswith(';'):
            self.finalize()
            if COMMENTED_ENTRY_PATTERN.match(line):
                return CommentedEntryState(
                    parser=self.parser,
                    block_start=lineno,
                    block_lines=[line],
                )
            return CommentBlockState(
                parser=self.parser,
                block_start=lineno,
                block_lines=[line],
            )

        self.block_lines.append(line)
        return self

    def finalize(self) -> None:
        """Finalize the state and add any remaining blocks to the file content."""
        self.parser.parsed_blocks.append(
            NonEntryBlock(
                start_line=self.block_start,
                original_lines=self.block_lines,
                type=BlockType.FREE_TEXT,
            ))


class EntryState(ParserState):
    """State for parsing regular Beancount entries."""

    def __init__(self, parser: 'TextPreservingParser', block_start: int,
                 block_lines: List[str], entry: Directive):
        """Initialize the state.
        
        Args:
            parser: The TextPreservingParser instance
            block_start: The line number where the entry starts
            block_lines: The lines collected so far for this entry
            entry: The Beancount directive being parsed
        """
        super().__init__(parser)
        self.block_start = block_start
        self.block_lines = block_lines
        self.entry = entry

    def process_line(self, line: str, lineno: int) -> ParserState:
        """Process the current line and return the next state.
        
        Args:
            line: The current line to process
            lineno: The line number of the current line
            
        Returns:
            The next state to transition to
        """
        found_entry = self._match_next_entry(line, lineno)
        if found_entry:
            self.finalize()
            return EntryState(
                parser=self.parser,
                entry=found_entry,
                block_start=lineno,
                block_lines=[line],
            )

        if line.strip() == '':
            self.finalize()
            return NonEntryBlockState(parser=self.parser,
                                      block_start=lineno,
                                      block_lines=[line])
        if COMMENTED_ENTRY_PATTERN.match(line):
            self.finalize()
            return CommentedEntryState(
                parser=self.parser,
                block_start=lineno,
                block_lines=[line],
            )

        if line[0].isspace():
            # This is a metadata, a posting, or an inline comment in the entry
            self.block_lines.append(line)
            return self

        self.finalize()

        if line.lstrip().startswith(';'):
            return CommentBlockState(
                parser=self.parser,
                block_start=lineno,
                block_lines=[line],
            )

        return NonEntryBlockState(
            parser=self.parser,
            block_start=lineno,
            block_lines=[line],
        )

    def finalize(self) -> None:
        """Finalize the state and add the entry to the file content."""
        self.parser.parsed_blocks.append(
            EntryWithLines(
                entry=self.entry,
                start_line=self.block_start,
                original_lines=self.block_lines,
            ))


class TextPreservingParser:
    """Parser that preserves the original text representation of Beancount files."""

    logger = logging.getLogger(__name__)

    def __init__(self, file_path: str):
        """Initialize the parser.
        
        Args:
            file_path: The path to the file to parse
        """
        self.file_path = file_path
        existing_entries, _, _ = beancount.load_file(file_path)
        self.existing_entries = sorted(existing_entries,
                                       key=lambda entry: entry.meta['lineno'],
                                       reverse=True)
        self.parsed_blocks: List[Block] = []

    def parse(self) -> List[Block]:
        """Parse the file and return its content.
        
        Returns:
            A list of Block objects representing the parsed file content

        Raises:
            FileNotFoundError: If the file does not exist
        """
        with open(self.file_path, 'r') as f:
            lines = f.readlines()

        # Process lines
        current_state = InitialState(self)

        for line_idx in range(len(lines)):
            line = lines[line_idx]
            lineno = line_idx + 1

            # Process the current line with the current state
            current_state = current_state.process_line(line, lineno)

        current_state.finalize()

        return self.parsed_blocks


def parse_file(file_path: str) -> List[Block]:
    """Parse a Beancount file and return its content.
    
    Args:
        file_path: The path to the file to parse
        existing_entries: Existing entries to use for parsing   
    """
    if not os.path.exists(file_path):
        return []

    parser = TextPreservingParser(file_path)
    return parser.parse()
