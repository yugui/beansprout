#!/usr/bin/python3

import os
import tempfile
import unittest
from unittest import mock
import datetime
import decimal
import click
from click.testing import CliRunner

import bean_gulp
from beancount.core import data
from beancount.parser import printer
from beancount import loader


class TestMergeCommand(unittest.TestCase):
    """Test the merge command functionality."""

    def setUp(self):
        """Set up the test environment."""
        # Create a temporary directory for test files
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = self.temp_dir.name

        # Create a source directory for test files
        self.source_dir = os.path.join(self.test_dir, "source")
        os.makedirs(self.source_dir, exist_ok=True)

        # Create a destination directory for output files
        self.dest_dir = os.path.join(self.test_dir, "dest")
        os.makedirs(self.dest_dir, exist_ok=True)

        # Create a mock account directory
        self.account_dir = os.path.join(self.dest_dir, "Assets", "Cash",
                                        "Wallet")
        os.makedirs(self.account_dir, exist_ok=True)

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

        # Create a test source file
        self.source_file = os.path.join(self.source_dir, "test_source.csv")
        with open(self.source_file, "w") as f:
            f.write("Test source file content")

        # Create a mock importer
        self.mock_importer = mock.MagicMock()
        self.mock_importer.name = "MockImporter"
        self.mock_importer.account.return_value = "Assets:Cash:Wallet"
        self.mock_importer.extract.return_value = [self.test_transaction]
        self.mock_importer.deduplicate.side_effect = lambda entries, existing: None  # No-op

        # Create a mock context
        self.mock_ctx = mock.MagicMock()
        self.mock_ctx.importers = [self.mock_importer]
        self.mock_ctx.hooks = []

        # Create a CLI runner
        self.runner = CliRunner()

    def tearDown(self):
        """Clean up after the test."""
        self.temp_dir.cleanup()

    @mock.patch("beangulp.identify.identify")
    @mock.patch("beangulp.extract.extract_from_file")
    @mock.patch("beancount.loader.load_file")
    def test_merge_new_file(self, mock_load_file, mock_extract, mock_identify):
        """Test merging transactions into a new file."""
        # Set up mocks
        mock_identify.return_value = self.mock_importer
        mock_extract.return_value = [self.test_transaction]
        mock_load_file.return_value = ([], None, None)

        # Create a test CLI context
        with mock.patch("click.pass_obj", lambda f: f):
            # Invoke the merge command
            result = self.runner.invoke(
                bean_gulp._merge,
                ["--destination", self.dest_dir, self.source_file],
                obj=self.mock_ctx)

        # Check that the command executed successfully
        self.assertEqual(result.exit_code, 0)

        # Check that the destination file was created
        dest_file = os.path.join(self.account_dir, "202504.beancount")
        self.assertTrue(os.path.exists(dest_file))

        # Check the content of the destination file
        with open(dest_file, "r") as f:
            content = f.read()

        # Verify that the transaction is in the file
        self.assertIn("Test Transaction", content)
        self.assertIn("Assets:Cash:Wallet", content)
        self.assertIn("Expenses:Food", content)
        self.assertIn("-1000 JPY", content)
        self.assertIn("1000 JPY", content)

    @mock.patch("beangulp.identify.identify")
    @mock.patch("beangulp.extract.extract_from_file")
    @mock.patch("beancount.loader.load_file")
    def test_merge_existing_file(self, mock_load_file, mock_extract,
                                 mock_identify):
        """Test merging transactions into an existing file."""
        # Create an existing transaction
        existing_date = datetime.date(2025, 4, 10)
        existing_transaction = data.Transaction(
            meta=data.new_metadata("existing.beancount", 1),
            date=existing_date,
            flag="*",
            payee="Existing Payee",
            narration="Existing Transaction",
            tags=set(),
            links=set(),
            postings=[
                data.Posting(
                    account="Assets:Cash:Wallet",
                    units=data.Amount(number=decimal.Decimal("-500"),
                                      currency="JPY"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
                data.Posting(
                    account="Expenses:Transport",
                    units=data.Amount(number=decimal.Decimal("500"),
                                      currency="JPY"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )

        # Create an existing file
        existing_file = os.path.join(self.account_dir, "202504.beancount")
        with open(existing_file, "w") as f:
            f.write(";; -*- mode: beancount -*-\n")
            f.write("; Transactions for Assets:Cash:Wallet 202504\n\n")
            f.write(printer.format_entry(existing_transaction))
            f.write("\n")

        # Set up mocks
        mock_identify.return_value = self.mock_importer
        mock_extract.return_value = [self.test_transaction]
        mock_load_file.return_value = ([existing_transaction], None, None)

        # Create a test CLI context
        with mock.patch("click.pass_obj", lambda f: f):
            # Invoke the merge command
            result = self.runner.invoke(
                bean_gulp._merge,
                ["--destination", self.dest_dir, self.source_file],
                obj=self.mock_ctx)

        # Check that the command executed successfully
        self.assertEqual(result.exit_code, 0)

        # Check the content of the destination file
        with open(existing_file, "r") as f:
            content = f.read()

        # Verify that both transactions are in the file
        self.assertIn("Test Transaction", content)
        self.assertIn("Existing Transaction", content)
        self.assertIn("Expenses:Food", content)
        self.assertIn("Expenses:Transport", content)

    @mock.patch("beangulp.identify.identify")
    @mock.patch("beangulp.extract.extract_from_file")
    @mock.patch("beancount.loader.load_file")
    def test_merge_with_duplicates(self, mock_load_file, mock_extract,
                                   mock_identify):
        """Test merging transactions with duplicates."""
        # Create an existing transaction
        existing_date = datetime.date(2025, 4, 10)
        existing_transaction = data.Transaction(
            meta=data.new_metadata("existing.beancount", 1),
            date=existing_date,
            flag="*",
            payee="Existing Payee",
            narration="Existing Transaction",
            tags=set(),
            links=set(),
            postings=[
                data.Posting(
                    account="Assets:Cash:Wallet",
                    units=data.Amount(number=decimal.Decimal("-500"),
                                      currency="JPY"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
                data.Posting(
                    account="Expenses:Transport",
                    units=data.Amount(number=decimal.Decimal("500"),
                                      currency="JPY"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )

        # Create a duplicate transaction that will be extracted
        duplicate_transaction = data.Transaction(
            meta=data.new_metadata("duplicate_source.csv", 1),
            date=existing_date,
            flag="*",
            payee="Existing Payee",
            narration="Existing Transaction",
            tags=set(),
            links=set(),
            postings=[
                data.Posting(
                    account="Assets:Cash:Wallet",
                    units=data.Amount(number=decimal.Decimal("-500"),
                                      currency="JPY"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
                data.Posting(
                    account="Expenses:Transport",
                    units=data.Amount(number=decimal.Decimal("500"),
                                      currency="JPY"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )

        # Create a new transaction that is not a duplicate
        new_transaction = self.test_transaction

        # Create an existing file
        existing_file = os.path.join(self.account_dir, "202504.beancount")
        with open(existing_file, "w") as f:
            f.write(";; -*- mode: beancount -*-\n")
            f.write("; Transactions for Assets:Cash:Wallet 202504\n\n")
            f.write(printer.format_entry(existing_transaction))
            f.write("\n")

        # Set up mocks
        mock_identify.return_value = self.mock_importer
        mock_extract.return_value = [duplicate_transaction, new_transaction]
        mock_load_file.return_value = ([existing_transaction], None, None)

        # Mock the deduplicate method to mark the duplicate transaction
        def mock_deduplicate(entries, existing):
            for entry in entries:
                if (entry.date == existing_date
                        and entry.payee == "Existing Payee"
                        and entry.narration == "Existing Transaction"):
                    if not hasattr(entry, 'meta') or entry.meta is None:
                        entry.meta = {}
                    entry.meta['__duplicate__'] = True

        self.mock_importer.deduplicate.side_effect = mock_deduplicate

        # Create a test CLI context
        with mock.patch("click.pass_obj", lambda f: f):
            # Invoke the merge command
            result = self.runner.invoke(
                bean_gulp._merge,
                ["--destination", self.dest_dir, self.source_file],
                obj=self.mock_ctx)

        # Check that the command executed successfully
        self.assertEqual(result.exit_code, 0)

        # Check the content of the destination file
        with open(existing_file, "r") as f:
            content = f.read()

        # Verify that only the existing transaction and the new transaction are in the file
        # The duplicate transaction should be filtered out
        self.assertIn("Test Transaction", content)
        self.assertIn("Existing Transaction", content)

        # Count occurrences of "Existing Transaction" - should only appear once
        self.assertEqual(content.count("Existing Transaction"), 1)

        # Verify that both expense accounts are in the file
        self.assertIn("Expenses:Food", content)
        self.assertIn("Expenses:Transport", content)

    @mock.patch("beangulp.identify.identify")
    @mock.patch("beangulp.extract.extract_from_file")
    @mock.patch("beancount.loader.load_file")
    def test_merge_dry_run(self, mock_load_file, mock_extract, mock_identify):
        """Test dry run mode."""
        # Set up mocks
        mock_identify.return_value = self.mock_importer
        mock_extract.return_value = [self.test_transaction]
        mock_load_file.return_value = ([], None, None)

        # Create a test CLI context
        with mock.patch("click.pass_obj", lambda f: f):
            # Invoke the merge command with dry-run
            result = self.runner.invoke(bean_gulp._merge, [
                "--destination", self.dest_dir, "--dry-run", self.source_file
            ],
                                        obj=self.mock_ctx)

        # Check that the command executed successfully
        self.assertEqual(result.exit_code, 0)

        # Check that the destination file was not created
        dest_file = os.path.join(self.account_dir, "202504.beancount")
        self.assertFalse(os.path.exists(dest_file))

        # Check that the output contains the transaction details
        self.assertIn("Test Transaction", result.output)
        self.assertIn("Assets:Cash:Wallet", result.output)
        self.assertIn("Expenses:Food", result.output)


if __name__ == "__main__":
    unittest.main()
