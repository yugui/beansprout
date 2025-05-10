#!/usr/bin/env python3
"""Unit tests for the merge module."""

import os
import tempfile
import unittest
from unittest import mock
import datetime
import decimal

from beancount.core import data
from beancount.parser import printer
from beancount import loader

from beansprout.importer.merge import Processor


class TestProcessor(unittest.TestCase):
    """Test the Processor class."""

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

        # Create the transactions directory structure
        self.transactions_dir = os.path.join(self.dest_dir, "transactions")
        os.makedirs(self.transactions_dir, exist_ok=True)

        # Create a mock account directory following Beansprout structure
        self.account_dir = os.path.join(self.transactions_dir, "Assets",
                                        "Cash", "Wallet")
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

    def tearDown(self):
        """Clean up after the test."""
        self.temp_dir.cleanup()

    # Create a concrete implementation of Processor for testing
    class ConcreteProcessor(Processor):
        """Concrete implementation of Processor for testing."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.output_called = False
            self.output_args = None

        def process_output(self, entries_by_account_month,
                           entries_by_dest_file):
            """Record that process_output was called and with what arguments."""
            self.output_called = True
            self.output_args = (entries_by_account_month, entries_by_dest_file)

    def test_get_account_file_path(self):
        """Test the get_account_file_path method."""
        processor = self.ConcreteProcessor(importers=[self.mock_importer],
                                           destination=self.dest_dir)

        # Test simple account
        expected_path = os.path.join(self.dest_dir, "transactions", "Assets",
                                     "Cash", "Wallet", "202504.beancount")
        actual_path = processor.get_account_file_path("Assets:Cash:Wallet",
                                                      "202504")
        self.assertEqual(actual_path, expected_path)

        # Test more complex account
        expected_path = os.path.join(self.dest_dir, "transactions",
                                     "Liabilities", "CreditCard", "Chase",
                                     "202505.beancount")
        actual_path = processor.get_account_file_path(
            "Liabilities:CreditCard:Chase", "202505")
        self.assertEqual(actual_path, expected_path)

        # Test account with many components
        expected_path = os.path.join(self.dest_dir, "transactions", "Assets",
                                     "Investments", "Brokerage", "Stocks",
                                     "Tech", "202506.beancount")
        actual_path = processor.get_account_file_path(
            "Assets:Investments:Brokerage:Stocks:Tech", "202506")
        self.assertEqual(actual_path, expected_path)

    @mock.patch("beangulp.identify.identify")
    @mock.patch("beangulp.extract.extract_from_file")
    @mock.patch("beancount.loader.load_file")
    def test_process_new_file(self, mock_load_file, mock_extract,
                              mock_identify):
        """Test processing transactions into a new file."""
        # Set up mocks
        mock_identify.return_value = self.mock_importer
        mock_extract.return_value = [self.test_transaction]
        mock_load_file.return_value = ([], None, None)

        # Create a processor
        processor = self.ConcreteProcessor(importers=[self.mock_importer],
                                           destination=self.dest_dir,
                                           reverse=False,
                                           failfast=False,
                                           quiet=0)

        # Process the source file
        status = processor.process([self.source_file])

        # Check that the process completed successfully
        self.assertEqual(status, 0)

        # Check that process_output was called
        self.assertTrue(processor.output_called)

        # Check that entries_by_account_month contains our test transaction
        entries_by_account_month, entries_by_dest_file = processor.output_args
        self.assertIn(("Assets:Cash:Wallet", "202504"),
                      entries_by_account_month)
        self.assertEqual(
            len(entries_by_account_month[("Assets:Cash:Wallet", "202504")]), 1)
        entry, importer = entries_by_account_month[("Assets:Cash:Wallet",
                                                    "202504")][0]
        self.assertEqual(entry, self.test_transaction)
        self.assertEqual(importer, self.mock_importer)

        # Check that entries_by_dest_file is empty (since no existing files)
        self.assertEqual(len(entries_by_dest_file), 0)

    @mock.patch("beangulp.identify.identify")
    @mock.patch("beangulp.extract.extract_from_file")
    @mock.patch("beancount.loader.load_file")
    def test_process_existing_file(self, mock_load_file, mock_extract,
                                   mock_identify):
        """Test processing transactions into an existing file."""
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

        # Create an existing file with the proper Beansprout structure
        existing_file = os.path.join(self.transactions_dir, "Assets", "Cash",
                                     "Wallet", "202504.beancount")
        os.makedirs(os.path.dirname(existing_file), exist_ok=True)

        with open(existing_file, "w") as f:
            f.write(";; -*- mode: beancount -*-\n")
            f.write("; Transactions for Assets:Cash:Wallet 202504\n\n")
            f.write(printer.format_entry(existing_transaction))
            f.write("\n")

        # Set up mocks
        mock_identify.return_value = self.mock_importer
        mock_extract.return_value = [self.test_transaction]
        mock_load_file.return_value = ([existing_transaction], None, None)

        # Create a processor
        processor = self.ConcreteProcessor(importers=[self.mock_importer],
                                           destination=self.dest_dir,
                                           reverse=False,
                                           failfast=False,
                                           quiet=0)

        # Process the source file
        status = processor.process([self.source_file])

        # Check that the process completed successfully
        self.assertEqual(status, 0)

        # Check that process_output was called
        self.assertTrue(processor.output_called)

        # Check that entries_by_account_month contains our test transaction
        entries_by_account_month, entries_by_dest_file = processor.output_args
        self.assertIn(("Assets:Cash:Wallet", "202504"),
                      entries_by_account_month)
        self.assertEqual(
            len(entries_by_account_month[("Assets:Cash:Wallet", "202504")]), 1)
        entry, importer = entries_by_account_month[("Assets:Cash:Wallet",
                                                    "202504")][0]
        self.assertEqual(entry, self.test_transaction)
        self.assertEqual(importer, self.mock_importer)

        # Check that entries_by_dest_file contains the existing file with the existing transaction
        self.assertIn(existing_file, entries_by_dest_file)
        self.assertEqual(len(entries_by_dest_file[existing_file]), 1)
        self.assertEqual(entries_by_dest_file[existing_file][0],
                         existing_transaction)

    @mock.patch("beangulp.identify.identify")
    @mock.patch("beangulp.extract.extract_from_file")
    @mock.patch("beancount.loader.load_file")
    def test_process_with_duplicates(self, mock_load_file, mock_extract,
                                     mock_identify):
        """Test processing transactions with duplicates."""
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

        # Create an existing file with the proper Beansprout structure
        existing_file = os.path.join(self.transactions_dir, "Assets", "Cash",
                                     "Wallet", "202504.beancount")
        os.makedirs(os.path.dirname(existing_file), exist_ok=True)

        with open(existing_file, "w") as f:
            f.write(";; -*- mode: beancount -*-\n")
            f.write("; Transactions for Assets:Cash:Wallet 202504\n\n")
            f.write(printer.format_entry(existing_transaction))
            f.write("\n")

        # Set up mocks
        mock_identify.return_value = self.mock_importer
        mock_extract.return_value = [
            duplicate_transaction, self.test_transaction
        ]
        mock_load_file.return_value = ([existing_transaction], None, None)

        # Mock the deduplicate method to mark the duplicate transaction
        def mock_deduplicate(entries, existing):
            for entry in entries:
                if (entry.date == existing_date
                        and entry.payee == "Existing Payee"
                        and entry.narration == "Existing Transaction"):
                    if not hasattr(entry, 'meta') or entry.meta is None:
                        entry.meta = {}
                    # Store the duplicate entry in the metadata
                    entry.meta['__duplicate__'] = existing_transaction

        self.mock_importer.deduplicate.side_effect = mock_deduplicate

        # Create a processor
        processor = self.ConcreteProcessor(importers=[self.mock_importer],
                                           destination=self.dest_dir,
                                           reverse=False,
                                           failfast=False,
                                           quiet=0)

        # Process the source file
        status = processor.process([self.source_file])

        # Check that the process completed successfully
        self.assertEqual(status, 0)

        # Check that process_output was called
        self.assertTrue(processor.output_called)

        # Check that entries_by_account_month contains both transactions
        # (including the duplicate, which should be marked but not filtered out)
        entries_by_account_month, entries_by_dest_file = processor.output_args
        self.assertIn(("Assets:Cash:Wallet", "202504"),
                      entries_by_account_month)
        self.assertEqual(
            len(entries_by_account_month[("Assets:Cash:Wallet", "202504")]), 2)

        # Check that one of the entries is marked as a duplicate
        entry_importer_pairs = entries_by_account_month[("Assets:Cash:Wallet",
                                                         "202504")]
        duplicate_entries = [
            entry for entry, _ in entry_importer_pairs
            if hasattr(entry, 'meta') and entry.meta
            and '__duplicate__' in entry.meta
        ]
        self.assertEqual(len(duplicate_entries), 1)

        # Check that entries_by_dest_file contains the existing file with the existing transaction
        self.assertIn(existing_file, entries_by_dest_file)
        self.assertEqual(len(entries_by_dest_file[existing_file]), 1)
        self.assertEqual(entries_by_dest_file[existing_file][0],
                         existing_transaction)


if __name__ == "__main__":
    unittest.main()
