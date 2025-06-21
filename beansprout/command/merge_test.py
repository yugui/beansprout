"""Tests for the Merge class."""

import os
import tempfile
import unittest
import datetime
import decimal
from typing import List, Optional, Dict, Any

from beancount import Directive
from beancount.core import data
from beancount.parser import printer

from beansprout.command.merge import Merge
from beansprout.importer.types import ImporterType


class FakeImporter:
    """A fake importer for testing purposes."""

    def __init__(self,
                 account: str,
                 file_name: str,
                 extract_entries: List[Directive] = None,
                 name: str = "FakeImporter"):
        """Initialize the fake importer.
        
        Args:
            account: The account to use for this importer.
            file_name: The file name this importer can identify.
            extract_entries: The entries to return when extract is called.
            name: The name of the importer.
        """
        self.account_value = account
        self.file_name = file_name
        self.extract_entries = extract_entries or []
        self.deduplicate_called = False
        self.deduplicate_entries = []
        self.deduplicate_existing = []
        self.name = name

    def account(self, filename: str) -> str:
        """Return the account for this importer."""
        return self.account_value

    def identify(self, file_path: str) -> bool:
        """Identify if this importer can handle the given file."""
        # For testing purposes, only identify files that match the file name
        return os.path.basename(file_path) == self.file_name

    def extract(self,
                file_path: str,
                existing_entries: List[Directive] = None) -> List[Directive]:
        """Extract entries from the given file."""
        return self.extract_entries

    def sort(self, entries: List[Directive]) -> None:
        """Sort the entries by date."""
        # This is a no-op for testing purposes
        pass

    def deduplicate(self, entries: List[Directive],
                    existing_entries: List[Directive]) -> None:
        """Mark duplicate entries."""
        self.deduplicate_called = True
        self.deduplicate_entries = entries
        self.deduplicate_existing = existing_entries

        # Mark entries with __duplicate__ metadata if they match existing entries
        for entry in entries:
            for existing in existing_entries:
                if (isinstance(entry, data.Transaction)
                        and isinstance(existing, data.Transaction)
                        and entry.date == existing.date
                        and entry.payee == existing.payee
                        and entry.narration == existing.narration):
                    if not hasattr(entry, 'meta') or entry.meta is None:
                        entry.meta = {}
                    entry.meta['__duplicate__'] = existing


class ErrorImporter(FakeImporter):
    """An importer that raises an error during extraction."""

    def __init__(self,
                 account: str,
                 file_name: str,
                 extract_entries: List[Directive] = None):
        """Initialize the error importer."""
        super().__init__(account,
                         file_name,
                         extract_entries,
                         name="ErrorImporter")

    def extract(self,
                file_path: str,
                existing_entries: List[Directive] = None) -> List[Directive]:
        """Raise an error when extracting entries."""
        # This will be caught by the errors trap in _extract_transactions
        raise ValueError("Test error")


class FakeHook:
    """A fake hook for testing purposes."""

    def __init__(self, transform_func=None):
        """Initialize the fake hook.
        
        Args:
            transform_func: A function that transforms the extracted entries.
        """
        self.called = False
        self.extracted = None
        self.existing_entries = None
        self.transform_func = transform_func

    def __call__(self, extracted, existing_entries):
        """Apply the hook to the extracted entries."""
        # Always mark as called when the hook is invoked
        self.called = True
        self.extracted = extracted
        self.existing_entries = existing_entries

        if self.transform_func:
            return self.transform_func(extracted, existing_entries)
        return extracted


class TestMerge(unittest.TestCase):
    """Tests for the Merge class."""

    def setUp(self):
        """Set up the test environment."""
        # Create a temporary directory for test files
        self.temp_dir = tempfile.TemporaryDirectory()
        self.destination = self.temp_dir.name

        # Create a source directory for test files
        self.source_dir = os.path.join(self.temp_dir.name, "source")
        os.makedirs(self.source_dir, exist_ok=True)

        # Create a test source file
        self.source_file_name = "test_source.csv"
        self.source_file = os.path.join(self.source_dir, self.source_file_name)
        with open(self.source_file, "w") as f:
            f.write("Test source file content")

        # Create a test transaction
        self.test_date = datetime.date(2025, 6, 22)
        self.test_transaction = data.Transaction(
            meta=data.new_metadata(self.source_file, 1),
            date=self.test_date,
            flag="*",
            payee="Test Payee",
            narration="Test Transaction",
            tags=set(),
            links=set(),
            postings=[
                data.Posting(
                    account="Assets:Test:Account",
                    units=data.Amount(number=decimal.Decimal("1000"),
                                      currency="USD"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
                data.Posting(
                    account="Expenses:Test",
                    units=data.Amount(number=decimal.Decimal("-1000"),
                                      currency="USD"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )

        # Create a fake importer
        self.fake_importer = FakeImporter(
            account="Assets:Test:Account",
            file_name=self.source_file_name,
            extract_entries=[self.test_transaction])

        # Create a fake hook
        self.fake_hook = FakeHook()

    def tearDown(self):
        """Clean up the test environment."""
        self.temp_dir.cleanup()

    def test_init(self):
        """Test initialization of the Merge class."""
        # Test with minimal required parameters
        merge = Merge(
            importers=[self.fake_importer],
            hooks=[self.fake_hook],
            destination=self.destination,
        )

        self.assertEqual(merge.importers, [self.fake_importer])
        self.assertEqual(merge.hooks, [self.fake_hook])
        self.assertEqual(merge.destination, self.destination)
        self.assertEqual(merge.reverse, False)  # Default value
        self.assertEqual(merge.failfast, False)  # Default value
        self.assertEqual(merge.quiet, 0)  # Default value
        self.assertEqual(merge.dry_run, False)  # Default value
        self.assertEqual(merge.existing_entries, [])  # Default value

        # Test with all parameters
        merge = Merge(
            importers=[self.fake_importer],
            hooks=[self.fake_hook],
            destination=self.destination,
            existing_file="nonexistent.beancount",  # Nonexistent file
            reverse=True,
            failfast=True,
            quiet=1,
            dry_run=True,
        )

        self.assertEqual(merge.importers, [self.fake_importer])
        self.assertEqual(merge.hooks, [self.fake_hook])
        self.assertEqual(merge.destination, self.destination)
        self.assertEqual(merge.reverse, True)
        self.assertEqual(merge.failfast, True)
        self.assertEqual(merge.quiet, 1)
        self.assertEqual(merge.dry_run, True)
        self.assertEqual(merge.existing_entries,
                         [])  # Still empty because file doesn't exist

    def test_get_account_file_path(self):
        """Test the _get_account_file_path method."""
        merge = Merge(
            importers=[self.fake_importer],
            hooks=[self.fake_hook],
            destination=self.destination,
        )

        # Test with a simple account
        account = "Assets:Test"
        year_month = "202506"
        expected_path = os.path.join(
            self.destination,
            "transactions",
            "Assets",
            "Test",
            "202506.beancount",
        )
        actual_path = merge._get_account_file_path(account, year_month)
        self.assertEqual(actual_path, expected_path)

        # Test with a nested account
        account = "Assets:Test:Nested:Account"
        year_month = "202506"
        expected_path = os.path.join(
            self.destination,
            "transactions",
            "Assets",
            "Test",
            "Nested",
            "Account",
            "202506.beancount",
        )
        actual_path = merge._get_account_file_path(account, year_month)
        self.assertEqual(actual_path, expected_path)

    def test_process_with_no_files(self):
        """Test processing with no files."""
        merge = Merge(
            importers=[self.fake_importer],
            hooks=[],  # No hooks to avoid the hook being called
            destination=self.destination,
        )

        # Process with an empty list of files
        status = merge.process([])

        # Check that the process completed successfully
        self.assertEqual(status, 0)

    def test_process_with_single_file(self):
        """Test processing a single file."""
        merge = Merge(
            importers=[self.fake_importer],
            hooks=[self.fake_hook],
            destination=self.destination,
        )

        # Process the source file
        status = merge.process([self.source_file])

        # Check that the process completed successfully
        self.assertEqual(status, 0)

        # Check that the hook was called
        self.assertTrue(self.fake_hook.called)

        # Check that the deduplicate method was called
        self.assertTrue(self.fake_importer.deduplicate_called)

        # Check that the destination file was created
        dest_file = os.path.join(
            self.destination,
            "transactions",
            "Assets",
            "Test",
            "Account",
            "202506.beancount",
        )
        self.assertTrue(os.path.exists(dest_file))

        # Check the content of the destination file
        with open(dest_file, "r") as f:
            content = f.read()
            self.assertIn("Test Payee", content)
            self.assertIn("Test Transaction", content)
            self.assertIn("Assets:Test:Account", content)
            self.assertIn("Expenses:Test", content)

    def test_process_with_duplicate_entries(self):
        """Test processing with duplicate entries."""
        # Create an existing transaction that matches the test transaction
        existing_transaction = data.Transaction(
            meta=data.new_metadata("existing.beancount", 1),
            date=self.test_date,
            flag="*",
            payee="Test Payee",
            narration="Test Transaction",
            tags=set(),
            links=set(),
            postings=[
                data.Posting(
                    account="Assets:Test:Account",
                    units=data.Amount(number=decimal.Decimal("1000"),
                                      currency="USD"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
                data.Posting(
                    account="Expenses:Test",
                    units=data.Amount(number=decimal.Decimal("-1000"),
                                      currency="USD"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )

        # Create an existing file with the proper structure
        existing_file = os.path.join(self.temp_dir.name, "existing.beancount")
        with open(existing_file, "w") as f:
            f.write(";; -*- mode: beancount -*-\n")
            f.write("; Existing transactions\n\n")
            f.write(printer.format_entry(existing_transaction))
            f.write("\n")

        # Create a merge instance with the existing file
        merge = Merge(
            importers=[self.fake_importer],
            hooks=[self.fake_hook],
            destination=self.destination,
            existing_file=existing_file,
        )

        # Process the source file
        status = merge.process([self.source_file])

        # Check that the process completed successfully
        self.assertEqual(status, 0)

        # Check that the hook was called
        self.assertTrue(self.fake_hook.called)

        # Check that the deduplicate method was called
        self.assertTrue(self.fake_importer.deduplicate_called)

        # Check that the destination file was created
        dest_file = os.path.join(
            self.destination,
            "transactions",
            "Assets",
            "Test",
            "Account",
            "202506.beancount",
        )
        self.assertTrue(os.path.exists(dest_file))

        # Check the content of the destination file
        with open(dest_file, "r") as f:
            content = f.read()
            # The transaction should be commented out because it's a duplicate
            # The format might vary, so we just check that it's commented out
            self.assertIn("; 2025-06-22", content)

    def test_process_with_hook_transformation(self):
        """Test processing with a hook that transforms entries."""

        # Create a hook that adds a tag to all transactions
        def add_tag(extracted, existing_entries):
            for _, entries, _, _ in extracted:
                for entry in entries:
                    if isinstance(entry, data.Transaction):
                        entry.tags.add("test-tag")
            return extracted

        transform_hook = FakeHook(add_tag)

        # Create a merge instance with the transform hook
        merge = Merge(
            importers=[self.fake_importer],
            hooks=[transform_hook],
            destination=self.destination,
        )

        # Process the source file
        status = merge.process([self.source_file])

        # Check that the process completed successfully
        self.assertEqual(status, 0)

        # Check that the hook was called
        self.assertTrue(transform_hook.called)

        # Check that the destination file was created
        dest_file = os.path.join(
            self.destination,
            "transactions",
            "Assets",
            "Test",
            "Account",
            "202506.beancount",
        )
        self.assertTrue(os.path.exists(dest_file))

        # Check the content of the destination file
        with open(dest_file, "r") as f:
            content = f.read()
            self.assertIn("#test-tag", content)

    def test_process_with_dry_run(self):
        """Test processing with dry_run=True."""
        merge = Merge(
            importers=[self.fake_importer],
            hooks=[self.fake_hook],
            destination=self.destination,
            dry_run=True,
        )

        # Process the source file
        status = merge.process([self.source_file])

        # Check that the process completed successfully
        self.assertEqual(status, 0)

        # Check that the hook was called
        self.assertTrue(self.fake_hook.called)

        # Check that the deduplicate method was called
        self.assertTrue(self.fake_importer.deduplicate_called)

        # Check that the destination file was NOT created
        dest_file = os.path.join(
            self.destination,
            "transactions",
            "Assets",
            "Test",
            "Account",
            "202506.beancount",
        )
        self.assertFalse(os.path.exists(dest_file))

    def test_process_with_multiple_importers(self):
        """Test processing with multiple importers."""
        # Create a second importer with a different account
        second_transaction = data.Transaction(
            meta=data.new_metadata(self.source_file, 2),
            date=self.test_date,
            flag="*",
            payee="Second Payee",
            narration="Second Transaction",
            tags=set(),
            links=set(),
            postings=[
                data.Posting(
                    account="Assets:Second:Account",
                    units=data.Amount(number=decimal.Decimal("500"),
                                      currency="USD"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
                data.Posting(
                    account="Expenses:Second",
                    units=data.Amount(number=decimal.Decimal("-500"),
                                      currency="USD"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )

        second_file_name = "second_source.csv"
        second_importer = FakeImporter(account="Assets:Second:Account",
                                       file_name=second_file_name,
                                       extract_entries=[second_transaction])

        # Create a second source file
        second_source_file = os.path.join(self.source_dir, second_file_name)
        with open(second_source_file, "w") as f:
            f.write("Second source file content")

        # Create a merge instance with both importers
        merge = Merge(
            importers=[self.fake_importer, second_importer],
            hooks=[self.fake_hook],
            destination=self.destination,
        )

        # Process both source files
        status = merge.process([self.source_file, second_source_file])

        # Check that the process completed successfully
        self.assertEqual(status, 0)

        # Check that the hook was called
        self.assertTrue(self.fake_hook.called)

        # Check that both destination files were created
        first_dest_file = os.path.join(
            self.destination,
            "transactions",
            "Assets",
            "Test",
            "Account",
            "202506.beancount",
        )
        second_dest_file = os.path.join(
            self.destination,
            "transactions",
            "Assets",
            "Second",
            "Account",
            "202506.beancount",
        )
        self.assertTrue(os.path.exists(first_dest_file))
        self.assertTrue(os.path.exists(second_dest_file))

        # Check the content of the first destination file
        with open(first_dest_file, "r") as f:
            content = f.read()
            self.assertIn("Test Payee", content)
            self.assertIn("Test Transaction", content)

        # Check the content of the second destination file
        with open(second_dest_file, "r") as f:
            content = f.read()
            self.assertIn("Second Payee", content)
            self.assertIn("Second Transaction", content)

    def test_process_with_error(self):
        """Test processing with an error."""
        # Create an error importer
        error_file_name = "error_source.csv"
        error_importer = ErrorImporter(account="Assets:Error:Account",
                                       file_name=error_file_name)

        # Create a source file for the error importer
        error_source_file = os.path.join(self.source_dir, error_file_name)
        with open(error_source_file, "w") as f:
            f.write("Error source file content")

        # Create a merge instance with the error importer
        merge = Merge(
            importers=[error_importer],
            hooks=[self.fake_hook],
            destination=self.destination,
        )

        # Process the source file
        status = merge.process([error_source_file])

        # Check that the process failed
        self.assertEqual(status, 1)

        # Check that the hook was not called
        self.assertFalse(self.fake_hook.called)

        # Check that no destination file was created
        dest_file = os.path.join(
            self.destination,
            "transactions",
            "Assets",
            "Error",
            "Account",
            "202506.beancount",
        )
        self.assertFalse(os.path.exists(dest_file))

    def test_process_with_failfast(self):
        """Test processing with failfast=True."""
        # Create an error importer
        error_file_name = "error_source.csv"
        error_importer = ErrorImporter(account="Assets:Error:Account",
                                       file_name=error_file_name)

        # Create a source file for the error importer
        error_source_file = os.path.join(self.source_dir, error_file_name)
        with open(error_source_file, "w") as f:
            f.write("Error source file content")

        # Create a merge instance with both importers and failfast=True
        merge = Merge(
            importers=[error_importer, self.fake_importer],
            hooks=[self.fake_hook],
            destination=self.destination,
            failfast=True,
        )

        # Process both source files
        status = merge.process([error_source_file, self.source_file])

        # Check that the process failed
        self.assertEqual(status, 1)

        # Check that the hook was not called
        self.assertFalse(self.fake_hook.called)

        # Check that no destination files were created
        first_dest_file = os.path.join(
            self.destination,
            "transactions",
            "Assets",
            "Error",
            "Account",
            "202506.beancount",
        )
        second_dest_file = os.path.join(
            self.destination,
            "transactions",
            "Assets",
            "Test",
            "Account",
            "202506.beancount",
        )
        self.assertFalse(os.path.exists(first_dest_file))
        self.assertFalse(os.path.exists(second_dest_file))


if __name__ == "__main__":
    unittest.main()
