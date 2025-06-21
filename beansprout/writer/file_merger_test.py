"""Unit tests for the FileMerger class."""

import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from beancount.core import data
from beancount.parser import parser

from beansprout.writer.file_merger import FileMerger
from beansprout.writer.types import BlockType, Block


class FileMergerTest(unittest.TestCase):
    """Test case for the FileMerger class."""

    def setUp(self):
        """Set up the test case."""
        self.tempdir = tempfile.mkdtemp()
        self.mock_importer = Mock()
        self.mock_importer.deduplicate = lambda entries, existing_entries: None

    def tearDown(self):
        """Clean up after the test case."""
        for filename in os.listdir(self.tempdir):
            os.remove(os.path.join(self.tempdir, filename))
        os.rmdir(self.tempdir)

    def _create_test_entry(self, date_str, narration="Test Entry"):
        """Create a test entry with the given date and narration.
        
        Args:
            date_str: The date string in YYYY-MM-DD format.
            narration: The narration for the entry.
            
        Returns:
            A Transaction directive.
        """
        return data.Transaction(
            meta={
                "filename": "",
                "lineno": 1
            },
            date=parser.parse_date(date_str),
            flag="*",
            payee=None,
            narration=narration,
            tags=set(),
            links=set(),
            postings=[
                data.Posting(
                    account="Assets:Checking",
                    units=data.Amount(data.D("100.00"), "USD"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
                data.Posting(
                    account="Expenses:Food",
                    units=data.Amount(data.D("-100.00"), "USD"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )

    def test_merge_entries_basic(self):
        """Test basic merging of entries into an empty file."""
        # Setup
        merger = FileMerger()
        dest_file = os.path.join(self.tempdir, "test.beancount")
        entry = self._create_test_entry("2023-01-01")
        entry_importer_pairs = [(entry, self.mock_importer)]

        # Execute
        merger.merge_entries(dest_file, entry_importer_pairs)

        with open(dest_file, 'r') as f:
            content = f.read()
            self.assertIn("2023-01-01", content)

    def test_merge_entries_with_duplicates(self):
        """Test merging entries with duplicates."""
        # Setup
        merger = FileMerger()
        dest_file = os.path.join(self.tempdir, "test.beancount")

        # Create an entry and mark it as a duplicate
        entry = self._create_test_entry("2023-01-01")
        duplicate_entry = self._create_test_entry("2023-01-01")
        entry.meta['__duplicate__'] = duplicate_entry
        duplicate_entry.meta['filename'] = dest_file

        entry_importer_pairs = [(entry, self.mock_importer)]

        # Execute
        merger.merge_entries(dest_file, entry_importer_pairs)

        # Verify
        self.assertTrue(os.path.exists(dest_file))
        with open(dest_file, 'r') as f:
            content = f.read()
            self.assertNotIn("2023-01-01", content)  # Entry should be skipped

    def test_merge_entries_with_commented_entries(self):
        """Test merging entries that should be commented out."""
        # Setup
        merger = FileMerger()
        dest_file = os.path.join(self.tempdir, "test.beancount")

        # Create an entry and mark it as a duplicate, but with a different filename
        entry = self._create_test_entry("2023-01-01")
        duplicate_entry = self._create_test_entry("2023-01-01")
        entry.meta['__duplicate__'] = duplicate_entry
        duplicate_entry.meta['filename'] = "different_file.beancount"

        entry_importer_pairs = [(entry, self.mock_importer)]

        # Execute
        merger.merge_entries(dest_file, entry_importer_pairs)

        # Verify
        self.assertTrue(os.path.exists(dest_file))
        with open(dest_file, 'r') as f:
            content = f.read()
            self.assertIn("; 2023-01-01",
                          content)  # Entry should be commented out

    def test_merge_entries_chronological_order(self):
        """Test that entries are inserted in chronological order."""
        # Setup
        merger = FileMerger()
        dest_file = os.path.join(self.tempdir, "test.beancount")

        # Create entries with different dates
        entry1 = self._create_test_entry("2023-01-01")
        entry2 = self._create_test_entry("2023-01-15")
        entry3 = self._create_test_entry("2023-01-30")

        # Add them in non-chronological order
        entry_importer_pairs = [(entry3, self.mock_importer),
                                (entry1, self.mock_importer),
                                (entry2, self.mock_importer)]

        # Execute
        merger.merge_entries(dest_file, entry_importer_pairs)

        # Read the file and check the order of entries
        with open(dest_file, 'r') as f:
            content = f.read()
            # Check that the entries appear in chronological order
            pos1 = content.find("2023-01-01")
            pos2 = content.find("2023-01-15")
            pos3 = content.find("2023-01-30")
            self.assertGreater(pos1, 0)
            self.assertGreater(pos2, pos1)
            self.assertGreater(pos3, pos2)

    def test_merge_entries_reverse_order(self):
        """Test that entries are inserted in reverse chronological order when reverse=True."""
        # Setup
        merger = FileMerger(reverse=True)
        dest_file = os.path.join(self.tempdir, "test.beancount")

        # Create entries with different dates
        entry1 = self._create_test_entry("2023-01-01")
        entry2 = self._create_test_entry("2023-01-15")
        entry3 = self._create_test_entry("2023-01-30")

        # Add them in non-chronological order
        entry_importer_pairs = [(entry2, self.mock_importer),
                                (entry1, self.mock_importer),
                                (entry3, self.mock_importer)]

        # Execute
        merger.merge_entries(dest_file, entry_importer_pairs)

        # Read the file and check the order of entries
        with open(dest_file, 'r') as f:
            content = f.read()
            # Check that the entries appear in reverse chronological order
            pos1 = content.find("2023-01-01")
            pos2 = content.find("2023-01-15")
            pos3 = content.find("2023-01-30")
            self.assertGreater(pos3, 0)
            self.assertGreater(pos2, pos3)
            self.assertGreater(pos1, pos2)

    def test_merge_entries_with_existing_content(self):
        """Test merging entries into a file with existing content."""
        # Setup
        merger = FileMerger()
        dest_file = os.path.join(self.tempdir, "test.beancount")

        # Create a file with existing content
        with open(dest_file, 'w') as f:
            f.write('2023-01-01 * "Existing Entry"\n')
            f.write('  Assets:Checking  100.00 USD\n')
            f.write('  Expenses:Food   -100.00 USD\n\n')

        # Create a new entry
        entry = self._create_test_entry("2023-01-15")
        entry_importer_pairs = [(entry, self.mock_importer)]

        # Execute
        merger.merge_entries(dest_file, entry_importer_pairs)

        # Read the file and check that both entries are present
        with open(dest_file, 'r') as f:
            content = f.read()
            self.assertIn("Existing Entry", content)
            self.assertIn("2023-01-15", content)

    def test_merge_entries_dry_run(self):
        """Test dry run mode."""
        # Setup
        merger = FileMerger()
        dest_file = os.path.join(self.tempdir, "test.beancount")
        entry = self._create_test_entry("2023-01-01")
        entry_importer_pairs = [(entry, self.mock_importer)]

        # Execute
        merger.merge_entries(dest_file, entry_importer_pairs, dry_run=True)

        # In dry run mode, the file should not be created
        self.assertFalse(os.path.exists(dest_file))

    def test_merge_entries_with_rededuplication(self):
        """Test re-deduplication against existing entries."""
        # Setup
        merger = FileMerger()
        dest_file = os.path.join(self.tempdir, "test.beancount")

        # Create a file with existing content
        with open(dest_file, 'w') as f:
            f.write('2023-01-01 * "Existing Entry"\n')
            f.write('  Assets:Checking  100.00 USD\n')
            f.write('  Expenses:Food   -100.00 USD\n\n')

        # Create a new entry that will be re-deduplicated
        entry = self._create_test_entry("2023-01-15")
        duplicate_entry = self._create_test_entry("2023-01-15")
        entry.meta['__duplicate__'] = duplicate_entry
        duplicate_entry.meta['filename'] = "different_file.beancount"

        # Mock the deduplicate method to mark the entry as a duplicate with the dest_file
        def mock_deduplicate(entries, existing_entries):
            for entry in entries:
                if '__duplicate__' not in entry.meta:
                    continue
                entry.meta['__duplicate__'].meta['filename'] = dest_file

        mock_importer = Mock()
        mock_importer.deduplicate = mock_deduplicate

        entry_importer_pairs = [(entry, mock_importer)]

        # Execute
        merger.merge_entries(dest_file, entry_importer_pairs)

        # Read the file and check that only the existing entry is present
        with open(dest_file, 'r') as f:
            content = f.read()
            self.assertIn("Existing Entry", content)
            self.assertNotIn("2023-01-15", content)
