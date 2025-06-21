#!/usr/bin/env python3
"""Unit tests for the text_preserving_parser module."""

import os
import tempfile
import unittest
import logging
from unittest import mock
import datetime
import decimal

import beancount
from beancount.core import data
from beancount.parser import printer

from beansprout.writer.types import (BlockType, EntryWithLines,
                                     CommentedEntryWithLines, NonEntryBlock)
from beansprout.writer.text_preserving_parser import TextPreservingParser


class TestTextPreservingParser(unittest.TestCase):
    """Test the TextPreservingParser class."""

    def setUp(self):
        """Set up the test environment."""
        self.test_dir = os.path.join(os.path.dirname(__file__),
                                     "testdata/parser")
        self.temp_dir = tempfile.TemporaryDirectory()

        # Create a test transaction
        self.test_date = datetime.date(2025, 4, 15)
        self.test_transaction = data.Transaction(
            meta=data.new_metadata("test_source.csv", 1),
            date=self.test_date,
            flag="*",
            payee="Test Payee",
            narration="Test Transaction",
            tags=set(),
            links=set(),
            postings=[
                data.Posting(
                    account="Assets:Cash:Wallet",
                    units=data.Amount(number=decimal.Decimal("-1000"),
                                      currency="JPY"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
                data.Posting(
                    account="Expenses:Food",
                    units=data.Amount(number=decimal.Decimal("1000"),
                                      currency="JPY"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )

        logging.basicConfig(level=logging.DEBUG)

    def tearDown(self):
        """Clean up the test environment."""
        self.temp_dir.cleanup()

    def test_empty_file(self):
        """Test parsing an empty file."""
        test_file = os.path.join(self.test_dir, "empty.beancount")
        parser = TextPreservingParser(test_file)
        blocks = parser.parse()
        self.assertEqual(len(blocks), 0)

    def test_blank_lines_only(self):
        """Test parsing a file with only blank lines."""
        test_file = os.path.join(self.test_dir, "blank_lines.beancount")
        with open(test_file, 'r') as f:
            content = f.read()

        parser = TextPreservingParser(test_file)
        blocks = parser.parse()

        # Check that the file content has only blank line blocks
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].type, BlockType.FREE_TEXT)
        self.assertEqual(''.join(blocks[0].original_lines), content)
        self.assertEqual(blocks[0].start_line, 1)
        self.assertEqual(blocks[0].end_line, len(content.splitlines()))

    def test_single_comment(self):
        """Test parsing a file with only a comment line."""
        test_file = os.path.join(self.test_dir, "single_comment.beancount")
        with open(test_file, 'r') as f:
            content = f.read()

        parser = TextPreservingParser(test_file)
        blocks = parser.parse()

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].type, BlockType.COMMENT)
        self.assertEqual(''.join(blocks[0].original_lines), content)
        self.assertEqual(blocks[0].start_line, 1)
        self.assertEqual(blocks[0].end_line, 2)

    def test_comments_with_blank_lines(self):
        """Test parsing a file with comments and blank lines."""
        test_file = os.path.join(self.test_dir, "comments.beancount")
        with open(test_file, 'r') as f:
            content = f.read()

        parser = TextPreservingParser(test_file)
        blocks = parser.parse()

        self.assertEqual(len(blocks), 3)

        self.assertEqual(blocks[0].type, BlockType.COMMENT)
        self.assertEqual(blocks[0].start_line, 1)
        self.assertEqual(blocks[0].end_line, 2)

        self.assertEqual(blocks[1].type, BlockType.FREE_TEXT)
        self.assertEqual(blocks[1].start_line, 3)
        self.assertEqual(blocks[1].end_line, 3)

        self.assertEqual(blocks[2].type, BlockType.COMMENT)
        self.assertEqual(blocks[2].start_line, 4)
        self.assertEqual(blocks[2].end_line, 4)

        parsed_original_lines = sum([block.original_lines for block in blocks],
                                    start=[])
        self.assertEqual(''.join(parsed_original_lines), content)

    def test_entries_only(self):
        """Test parsing a file with only entries."""
        test_file = os.path.join(self.test_dir, "entries_only.beancount")
        with open(test_file, "r") as f:
            content = f.read()
        content_entries, _, _ = beancount.load_file(test_file)

        # Parse the file
        parser = TextPreservingParser(test_file)
        blocks = parser.parse()

        self.assertEqual(len(blocks), 4)

        self.assertEqual(blocks[0].type, BlockType.ENTRY)
        self.assertEqual(blocks[0].start_line, 1)
        self.assertEqual(blocks[0].end_line, 3)
        self.assertEqual(blocks[0].entry, content_entries[0])

        self.assertEqual(blocks[1].type, BlockType.ENTRY)
        self.assertEqual(blocks[1].start_line, 4)
        self.assertEqual(blocks[1].end_line, 7)
        self.assertEqual(blocks[1].entry, content_entries[1])

        self.assertEqual(blocks[2].type, BlockType.ENTRY)
        self.assertEqual(blocks[2].start_line, 8)
        self.assertEqual(blocks[2].end_line, 10)
        self.assertEqual(blocks[2].entry, content_entries[2])

        self.assertEqual(blocks[3].type, BlockType.ENTRY)
        self.assertEqual(blocks[3].start_line, 11)
        self.assertEqual(blocks[3].end_line, 15)
        self.assertEqual(blocks[3].entry, content_entries[3])

        parsed_original_lines = sum([block.original_lines for block in blocks],
                                    start=[])
        self.assertEqual(''.join(parsed_original_lines), content)

    def test_commented_entries_only(self):
        """Test parsing a file with only commented entries."""
        test_file = os.path.join(self.test_dir,
                                 "commented_entries_only.beancount")
        with open(test_file, "r") as f:
            content = f.read()

        # Parse the file
        parser = TextPreservingParser(test_file)
        blocks = parser.parse()

        self.assertEqual(len(blocks), 4)

        self.assertEqual(blocks[0].type, BlockType.COMMENTED_ENTRY)
        self.assertEqual(blocks[0].start_line, 1)
        self.assertEqual(blocks[0].end_line, 3)

        self.assertEqual(blocks[1].type, BlockType.COMMENTED_ENTRY)
        self.assertEqual(blocks[1].start_line, 4)
        self.assertEqual(blocks[1].end_line, 7)

        self.assertEqual(blocks[2].type, BlockType.COMMENTED_ENTRY)
        self.assertEqual(blocks[2].start_line, 8)
        self.assertEqual(blocks[2].end_line, 10)

        self.assertEqual(blocks[3].type, BlockType.COMMENTED_ENTRY)
        self.assertEqual(blocks[3].start_line, 11)
        self.assertEqual(blocks[3].end_line, 15)

        parsed_original_lines = sum([block.original_lines for block in blocks],
                                    start=[])
        self.assertEqual(''.join(parsed_original_lines), content)

    def test_free_text_only(self):
        """Test parsing a file with only free text."""
        test_file = os.path.join(self.test_dir, "free_text.beancount")
        with open(test_file, 'r') as f:
            content = f.read()

        parser = TextPreservingParser(test_file)
        blocks = parser.parse()

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].type, BlockType.FREE_TEXT)
        self.assertEqual(blocks[0].start_line, 1)
        self.assertEqual(blocks[0].end_line, 13)
        self.assertEqual(''.join(blocks[0].original_lines), content)

    def test_comment_attached_to_entry(self):
        """Test parsing a file with a comment attached to an entry."""
        test_file = os.path.join(self.test_dir,
                                 "comment_attached_entries.beancount")
        with open(test_file, 'r') as f:
            content = f.read()
        content_entries, _, _ = beancount.load_file(test_file)

        parser = TextPreservingParser(test_file)
        blocks = parser.parse()

        self.assertEqual(len(blocks), 2)

        self.assertEqual(blocks[0].type, BlockType.ENTRY)
        self.assertEqual(blocks[0].start_line, 1)
        self.assertEqual(blocks[0].end_line, 4)
        self.assertEqual(blocks[0].entry, content_entries[0])

        self.assertEqual(blocks[1].type, BlockType.ENTRY)
        self.assertEqual(blocks[1].start_line, 5)
        self.assertEqual(blocks[1].end_line, 13)
        self.assertEqual(blocks[1].entry, content_entries[1])

        parsed_original_lines = sum([block.original_lines for block in blocks],
                                    start=[])
        self.assertEqual(''.join(parsed_original_lines), content)

    def _print_blocks(self, blocks):
        for block in blocks:
            print(block.type)
            print(block)

    def test_comment_attached_commented_block(self):
        """Test parsing a file with a comment block followed by a commented entry."""
        test_file = os.path.join(
            self.test_dir, "comment_attached_commented_entries.beancount")
        with open(test_file, "r") as f:
            content = f.read()

        parser = TextPreservingParser(test_file)
        blocks = parser.parse()
        self._print_blocks(blocks)

        self.assertEqual(len(blocks), 2)

        self.assertEqual(blocks[0].type, BlockType.COMMENTED_ENTRY)
        self.assertEqual(blocks[0].start_line, 1)
        self.assertEqual(blocks[0].end_line, 4)

        self.assertEqual(blocks[1].type, BlockType.COMMENTED_ENTRY)
        self.assertEqual(blocks[1].start_line, 5)
        self.assertEqual(blocks[1].end_line, 13)

        parsed_original_lines = sum([block.original_lines for block in blocks],
                                    start=[])
        self.assertEqual(''.join(parsed_original_lines), content)

    def test_entry_to_commented_entry(self):
        """Test parsing a file with an entry followed by a commented entry (EntryState → CommentedEntryState)."""
        test_file = os.path.join(self.test_dir,
                                 "entry_to_commented_entry.beancount")
        with open(test_file, "r") as f:
            content = f.read()
        content_entries, _, _ = beancount.load_file(test_file)

        parser = TextPreservingParser(test_file)
        blocks = parser.parse()

        self.assertEqual(len(blocks), 2)

        self.assertEqual(blocks[0].type, BlockType.ENTRY)
        self.assertEqual(blocks[0].start_line, 1)
        self.assertEqual(blocks[0].end_line, 3)
        self.assertEqual(blocks[0].entry, content_entries[0])

        self.assertEqual(blocks[1].type, BlockType.COMMENTED_ENTRY)
        self.assertEqual(blocks[1].start_line, 4)
        self.assertEqual(blocks[1].end_line, 6)

        parsed_original_lines = sum([block.original_lines for block in blocks],
                                    start=[])
        self.assertEqual(''.join(parsed_original_lines), content)

    def test_entry_to_comment(self):
        """Test parsing a file with an entry followed by a comment block (EntryState → CommentBlockState)."""
        test_file = os.path.join(self.test_dir, "entry_to_comment.beancount")
        with open(test_file, "r") as f:
            content = f.read()
        content_entries, _, _ = beancount.load_file(test_file)

        parser = TextPreservingParser(test_file)
        blocks = parser.parse()

        self.assertEqual(len(blocks), 2)

        self.assertEqual(blocks[0].type, BlockType.ENTRY)
        self.assertEqual(blocks[0].start_line, 1)
        self.assertEqual(blocks[0].end_line, 3)
        self.assertEqual(blocks[0].entry, content_entries[0])

        self.assertEqual(blocks[1].type, BlockType.COMMENT)
        self.assertEqual(blocks[1].start_line, 4)
        self.assertEqual(blocks[1].end_line, 6)

        parsed_original_lines = sum([block.original_lines for block in blocks],
                                    start=[])
        self.assertEqual(''.join(parsed_original_lines), content)

    def test_entry_to_free_text(self):
        """Test parsing a file with an entry followed by free text (EntryState → NonEntryBlockState)."""
        test_file = os.path.join(self.test_dir, "entry_to_free_text.beancount")
        with open(test_file, "r") as f:
            content = f.read()
        content_entries, _, _ = beancount.load_file(test_file)

        parser = TextPreservingParser(test_file)
        blocks = parser.parse()

        self.assertEqual(len(blocks), 2)

        self.assertEqual(blocks[0].type, BlockType.ENTRY)
        self.assertEqual(blocks[0].start_line, 1)
        self.assertEqual(blocks[0].end_line, 3)
        self.assertEqual(blocks[0].entry, content_entries[0])

        self.assertEqual(blocks[1].type, BlockType.FREE_TEXT)
        self.assertEqual(blocks[1].start_line, 4)
        self.assertEqual(blocks[1].end_line, 7)

        parsed_original_lines = sum([block.original_lines for block in blocks],
                                    start=[])
        self.assertEqual(''.join(parsed_original_lines), content)

    def test_commented_entry_to_entry(self):
        """Test parsing a file with a commented entry followed by an entry (CommentedEntryState → EntryState)."""
        test_file = os.path.join(self.test_dir,
                                 "commented_entry_to_entry.beancount")
        with open(test_file, "r") as f:
            content = f.read()
        content_entries, _, _ = beancount.load_file(test_file)

        parser = TextPreservingParser(test_file)
        blocks = parser.parse()

        self.assertEqual(len(blocks), 2)

        self.assertEqual(blocks[0].type, BlockType.COMMENTED_ENTRY)
        self.assertEqual(blocks[0].start_line, 1)
        self.assertEqual(blocks[0].end_line, 3)

        self.assertEqual(blocks[1].type, BlockType.ENTRY)
        self.assertEqual(blocks[1].start_line, 4)
        self.assertEqual(blocks[1].end_line, 6)
        self.assertEqual(blocks[1].entry, content_entries[0])

        parsed_original_lines = sum([block.original_lines for block in blocks],
                                    start=[])
        self.assertEqual(''.join(parsed_original_lines), content)

    def test_commented_entry_to_free_text(self):
        """Test parsing a file with a commented entry followed by free text (CommentedEntryState → NonEntryBlockState)."""
        test_file = os.path.join(self.test_dir,
                                 "commented_entry_to_free_text.beancount")
        with open(test_file, "r") as f:
            content = f.read()

        parser = TextPreservingParser(test_file)
        blocks = parser.parse()

        self.assertEqual(len(blocks), 2)

        self.assertEqual(blocks[0].type, BlockType.COMMENTED_ENTRY)
        self.assertEqual(blocks[0].start_line, 1)
        self.assertEqual(blocks[0].end_line, 3)

        self.assertEqual(blocks[1].type, BlockType.FREE_TEXT)
        self.assertEqual(blocks[1].start_line, 4)
        self.assertEqual(blocks[1].end_line, 6)

        parsed_original_lines = sum([block.original_lines for block in blocks],
                                    start=[])
        self.assertEqual(''.join(parsed_original_lines), content)

    def test_free_text_to_entry(self):
        """Test parsing a file with free text followed by an entry (NonEntryBlockState → EntryState)."""
        test_file = os.path.join(self.test_dir, "free_text_to_entry.beancount")
        with open(test_file, "r") as f:
            content = f.read()
        content_entries, _, _ = beancount.load_file(test_file)

        parser = TextPreservingParser(test_file)
        blocks = parser.parse()

        self.assertEqual(len(blocks), 2)

        self.assertEqual(blocks[0].type, BlockType.FREE_TEXT)
        self.assertEqual(blocks[0].start_line, 1)
        self.assertEqual(blocks[0].end_line, 3)

        self.assertEqual(blocks[1].type, BlockType.ENTRY)
        self.assertEqual(blocks[1].start_line, 4)
        self.assertEqual(blocks[1].end_line, 6)
        self.assertEqual(blocks[1].entry, content_entries[0])

        parsed_original_lines = sum([block.original_lines for block in blocks],
                                    start=[])
        self.assertEqual(''.join(parsed_original_lines), content)

    def test_free_text_to_commented_entry(self):
        """Test parsing a file with free text followed by a commented entry (NonEntryBlockState → CommentedEntryState)."""
        test_file = os.path.join(self.test_dir,
                                 "free_text_to_commented_entry.beancount")
        with open(test_file, "r") as f:
            content = f.read()

        parser = TextPreservingParser(test_file)
        blocks = parser.parse()

        self.assertEqual(len(blocks), 2)

        self.assertEqual(blocks[0].type, BlockType.FREE_TEXT)
        self.assertEqual(blocks[0].start_line, 1)
        self.assertEqual(blocks[0].end_line, 3)

        self.assertEqual(blocks[1].type, BlockType.COMMENTED_ENTRY)
        self.assertEqual(blocks[1].start_line, 4)
        self.assertEqual(blocks[1].end_line, 6)

        parsed_original_lines = sum([block.original_lines for block in blocks],
                                    start=[])
        self.assertEqual(''.join(parsed_original_lines), content)


if __name__ == "__main__":
    unittest.main()
