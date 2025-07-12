from enum import Enum, auto
from dataclasses import dataclass
from typing import List, Optional, TypeAlias, Union

import beancount
from beancount import Directive


class BlockType(Enum):
    """Enum for different types of non-entry blocks in a file."""
    COMMENT = auto()
    FREE_TEXT = auto()
    ENTRY = auto()
    COMMENTED_ENTRY = auto()


@dataclass
class EntryWithLines:
    """Represents a regular Beancount entry with its original text representation.
    
    Attributes:
        entry: The parsed Beancount directive
        start_line: The line number where the entry starts
        original_lines: The original text representation of the entry
        attached_comment_lines: Any comment lines attached to this entry
    """
    entry: Directive
    start_line: int
    original_lines: List[str]

    @property
    def type(self) -> BlockType:
        return BlockType.ENTRY

    @property
    def end_line(self) -> int:
        """Return the line number where the entry ends."""
        return self.start_line + len(self.original_lines) - 1

    def __str__(self) -> str:
        return "".join(self.original_lines)


@dataclass
class CommentedEntryWithLines:
    """Represents a commented-out entry with its original text representation.
    
    Attributes:
        commented_entry: The parsed Beancount directive (after removing comment markers)
        start_line: The line number where the commented entry starts
        original_lines: The original text representation of the commented entry
    """
    entry: Directive
    start_line: int
    original_lines: List[str]

    @property
    def type(self) -> BlockType:
        return BlockType.COMMENTED_ENTRY

    @property
    def end_line(self) -> int:
        """Return the line number where the commented entry ends."""
        return self.start_line + len(self.original_lines) - 1

    def __str__(self) -> str:
        return "".join(self.original_lines)


@dataclass
class NonEntryBlock:
    """Represents non-entry content like comments or free text.
    
    Attributes:
        start_line: The line number where the block starts
        original_lines: The original text representation of the block
        type: The type of the block (comment, free text, blank lines)
    """
    start_line: int
    original_lines: List[str]
    type: BlockType

    @property
    def end_line(self) -> int:
        """Return the line number where the block ends."""
        return self.start_line + len(self.original_lines) - 1

    def __str__(self) -> str:
        return "".join(self.original_lines)


@dataclass
class NewEntryBlock:
    """Represents a new entry to be inserted into a file.
    
    Attributes:
        entry: The entry to be inserted
        start_line: The line number where the entry should be inserted
        should_comment: Whether the entry should be commented out
    """
    entry: Directive
    start_line: Optional[int] = None
    should_comment: bool = False

    @property
    def type(self) -> BlockType:
        return BlockType.ENTRY if not self.should_comment else BlockType.COMMENTED_ENTRY

    @property
    def end_line(self) -> int:
        """Return the line number where the new entry ends.
        
        Note that new entries do not take any space in the original file and thus
        the end line is the same as the start line.
        """
        return self.line_number

    def __str__(self) -> str:
        """Return the string representation of the new entry."""
        entry_string = beancount.format_entry(self.entry)
        if self.should_comment:
            # Comment out each line of the entry
            entry_string = '; ' + entry_string.rstrip('\n').replace(
                '\n', '\n; ') + '\n'

        # Only add newline if the entry_string doesn't already end with one
        if not entry_string.endswith('\n'):
            entry_string += '\n'

        return entry_string


Block: TypeAlias = Union[EntryWithLines, CommentedEntryWithLines,
                         NonEntryBlock, NewEntryBlock]
