#!/usr/bin/env python3
"""Unit tests for the file_writer module."""

import datetime
import decimal
import os
import tempfile
import unittest
from unittest import mock
import shutil

import beancount
from beancount import Directives
from beancount.core import data
import beangulp

from beansprout.writer.file_writer import FileWriter
from beansprout.writer.identity_importer import IdentityImporter


class FakeImporter(beangulp.Importer):
    """Fake importer for testing purposes."""

    def identify(self, filepath: str) -> bool:
        raise NotImplementedError("This method should not be called.")

    def account(self, filepath: str) -> str:
        raise NotImplementedError("This method should not be called.")

    def extract(self, filepath: str, existings: Directives) -> Directives:
        raise NotImplementedError("This method should not be called.")


class TestFileWriter(unittest.TestCase):
    """Test the FileWriter class."""

    def setUp(self):
        """Set up the test environment."""
        # Create a temporary directory for test files
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = self.temp_dir.name

        self.test_input_dir = os.path.join(os.path.dirname(__file__),
                                           "testdata")

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

        # Create an existing transaction
        self.existing_date = datetime.date(2025, 4, 10)
        self.existing_transaction = data.Transaction(
            meta=data.new_metadata("existing.beancount", 1),
            date=self.existing_date,
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

        # Create a test source file
        self.source_file = os.path.join(self.source_dir, "test_source.csv")
        with open(self.source_file, "w") as f:
            f.write("Test source file content")

        self.fake_importer = FakeImporter()

    def tearDown(self):
        """Clean up after the test."""
        self.temp_dir.cleanup()

    def _create_test_transaction(self, date, payee, narration, amount):
        """Helper method to create a test transaction."""
        return data.Transaction(
            meta=data.new_metadata("test_source.csv", 1),
            date=date,
            flag="*",
            payee=payee,
            narration=narration,
            tags=set(),
            links=set(),
            postings=[
                data.Posting(
                    account="Assets:Cash:Wallet",
                    units=data.Amount(number=amount, currency="JPY"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
                data.Posting(
                    account="Expenses:Food",
                    units=data.Amount(number=-amount, currency="JPY"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )

    def test_basic_writing(self):
        """Test that new entries are written to a new file correctly."""
        processor = FileWriter(
            importers=[self.fake_importer],
            hooks=[],
            destination=self.dest_dir,
            existing_file="",  # Use empty string instead of None
            reverse=False,
            failfast=False,
            quiet=0,
            dry_run=False)

        # Create entries_by_account_month and entries_by_dest_file
        entries_by_account_month = {
            ("Assets:Cash:Wallet", "202504"):
            [(self.test_transaction, self.fake_importer)]
        }

        # Process the output
        processor.process_output(entries_by_account_month)

        # Check that the file was created
        dest_file = os.path.join(self.account_dir, "202504.beancount")
        self.assertTrue(os.path.exists(dest_file))

        written_entries, _, _ = beancount.load_file(dest_file)
        self.assertEqual(len(written_entries), 1)

    def test_duplicate_handling(self):
        """Test that duplicates are handled correctly."""
        dest_file = os.path.join(self.account_dir, "202504.beancount")
        with open(dest_file, "w") as f:
            f.write(";; -*- mode: beancount -*-\n")
            f.write("; Transactions for Assets:Cash:Wallet 202504\n\n")
            f.write(beancount.format_entry(self.existing_transaction))
            f.write("\n")
        self.existing_transaction.meta['filename'] = dest_file

        other_existing = self._create_test_transaction(
            date=datetime.date(2025, 4, 20),
            payee="Other Duplicate",
            narration="Other Transaction",
            amount=decimal.Decimal("-700"))
        other_existing.meta['filename'] = "other_existing.beancount"

        # Create a processor
        processor = FileWriter(importers=[self.fake_importer],
                               hooks=[],
                               destination=self.dest_dir,
                               existing_file=dest_file,
                               reverse=False,
                               failfast=False,
                               quiet=0,
                               dry_run=False)

        # Create a duplicate transaction
        duplicate_transaction = self._create_test_transaction(
            date=self.existing_transaction.date,
            payee=self.existing_transaction.payee,
            narration=self.existing_transaction.narration,
            amount=decimal.Decimal("-500"))
        duplicate_transaction.meta['__duplicate__'] = self.existing_transaction

        # Create a new transaction that would be a duplicate with other_existing
        other_duplicate = self._create_test_transaction(
            date=other_existing.date,
            payee=other_existing.payee,
            narration=other_existing.narration,
            amount=decimal.Decimal("-700"))
        other_duplicate.meta['__duplicate__'] = other_existing

        # Create entries_by_account_month and entries_by_dest_file
        entries_by_account_month = {
            ("Assets:Cash:Wallet", "202504"):
            [(duplicate_transaction, self.fake_importer),
             (other_duplicate, self.fake_importer)]
        }

        # Process the output
        processor.process_output(entries_by_account_month)

        # Read the file content
        with open(dest_file, "r") as f:
            content = f.read()

        # Check that the duplicate with the destination file was skipped
        self.assertEqual(content.count("Existing Payee"), 1)

        # Check that the duplicate with another file was commented out
        self.assertIn(
            "; 2025-04-20 * \"Other Duplicate\" \"Other Transaction\"",
            content)

        # Check that the regular entry was written normally
        self.assertIn(
            "2025-04-10 * \"Existing Payee\" \"Existing Transaction\"",
            content)

    @mock.patch("click.echo")
    def test_dry_run_mode(self, mock_echo):
        """Test that dry run mode works correctly."""
        processor = FileWriter(
            importers=[self.fake_importer],
            hooks=[],
            destination=self.dest_dir,
            existing_file="",  # Use empty string instead of None
            reverse=False,
            failfast=False,
            quiet=0,
            dry_run=True)

        # Create entries_by_account_month and entries_by_dest_file
        entries_by_account_month = {
            ("Assets:Cash:Wallet", "202504"):
            [(self.test_transaction, self.fake_importer)]
        }

        # Process the output
        processor.process_output(entries_by_account_month)

        # Check that the file was not created
        dest_file = os.path.join(self.account_dir, "202504.beancount")
        self.assertFalse(os.path.exists(dest_file))

        # Check that click.echo was called with the expected output
        mock_echo.assert_any_call(f"Dry run: would write to {dest_file}")
        # Check that the transaction details were printed
        self.assertTrue(
            any("Test Payee" in call[0][0]
                for call in mock_echo.call_args_list))

    def test_basic_text_preservation(self):
        """Test that comments and free text lines are preserved when rewriting a file."""
        # Create from a test data
        existing_file = os.path.join(os.path.dirname(__file__),
                                     'testdata/parser/mixed.beancount')
        dest_file = os.path.join(self.account_dir, "202504.beancount")
        shutil.copy(existing_file, dest_file)

        # Create a processor
        processor = FileWriter(importers=[self.fake_importer],
                               hooks=[],
                               destination=self.dest_dir,
                               existing_file=dest_file)

        # Create entries_by_account_month and entries_by_dest_file
        entries_by_account_month = {
            ("Assets:Cash:Wallet", "202504"):
            [(self.test_transaction, self.fake_importer)]
        }

        # Process the output
        processor.process_output(entries_by_account_month)

        # Read the file content
        with open(dest_file, "r") as f:
            written_content = f.read()

        golden_path = os.path.join(
            os.path.dirname(__file__),
            'testdata/writer/mixed_basic.golden.beancount')
        with open(golden_path, "r") as f:
            golden_content = f.read()

        self.maxDiff = None
        self.assertEqual(
            written_content, golden_content,
            "The written content does not match the golden file.")

    def test_reversed_text_preservation(self):
        # Create from a test data
        existing_file = os.path.join(
            os.path.dirname(__file__),
            'testdata/parser/mixed_reversed.beancount')
        dest_file = os.path.join(self.account_dir, "202504.beancount")
        shutil.copy(existing_file, dest_file)

        # Create a processor
        processor = FileWriter(importers=[self.fake_importer],
                               hooks=[],
                               destination=self.dest_dir,
                               existing_file=dest_file,
                               reverse=True)

        # Create entries_by_account_month and entries_by_dest_file
        entries_by_account_month = {
            ("Assets:Cash:Wallet", "202504"):
            [(self.test_transaction, self.fake_importer)]
        }

        # Process the output
        processor.process_output(entries_by_account_month)

        # Read the file content
        with open(dest_file, "r") as f:
            written_content = f.read()

        golden_path = os.path.join(
            os.path.dirname(__file__),
            'testdata/writer/mixed_reversed.golden.beancount')
        with open(golden_path, "r") as f:
            golden_content = f.read()

        self.maxDiff = None
        self.assertEqual(
            written_content, golden_content,
            "The written content does not match the golden file.")

    def test_text_preservation_with_wrong_order(self):
        # Create from a test data
        existing_file = os.path.join(os.path.dirname(__file__),
                                     'testdata/parser/mixed.beancount')
        dest_file = os.path.join(self.account_dir, "202504.beancount")
        shutil.copy(existing_file, dest_file)

        # Create a processor
        processor = FileWriter(importers=[self.fake_importer],
                               hooks=[],
                               destination=self.dest_dir,
                               existing_file=dest_file,
                               reverse=True)

        # Create entries_by_account_month and entries_by_dest_file
        entries_by_account_month = {
            ("Assets:Cash:Wallet", "202504"):
            [(self.test_transaction, self.fake_importer)]
        }

        # Process the output
        processor.process_output(entries_by_account_month)

        # Read the file content
        with open(dest_file, "r") as f:
            written_content = f.read()

        golden_path = os.path.join(
            os.path.dirname(__file__),
            'testdata/writer/mixed_wrong_order.golden.beancount')
        with open(golden_path, "r") as f:
            golden_content = f.read()

        self.maxDiff = None
        self.assertEqual(
            written_content, golden_content,
            "The written content does not match the golden file.")

    def test_text_preservation_last(self):
        # Create from a test data
        existing_file = os.path.join(os.path.dirname(__file__),
                                     'testdata/parser/mixed.beancount')
        dest_file = os.path.join(self.account_dir, "202504.beancount")
        shutil.copy(existing_file, dest_file)

        # Create a processor
        processor = FileWriter(importers=[self.fake_importer],
                               hooks=[],
                               destination=self.dest_dir,
                               existing_file=dest_file)

        last_transaction = self._create_test_transaction(
            date=datetime.date(2025, 4, 30),
            payee="Last Transaction",
            narration="This is the last transaction",
            amount=decimal.Decimal("-500"))

        # Create entries_by_account_month and entries_by_dest_file
        entries_by_account_month = {
            ("Assets:Cash:Wallet", "202504"):
            [(last_transaction, self.fake_importer)]
        }

        # Process the output
        processor.process_output(entries_by_account_month)

        # Read the file content
        with open(dest_file, "r") as f:
            written_content = f.read()

        golden_path = os.path.join(
            os.path.dirname(__file__),
            'testdata/writer/mixed_last.golden.beancount')
        with open(golden_path, "r") as f:
            golden_content = f.read()

        self.maxDiff = None
        self.assertEqual(
            written_content, golden_content,
            "The written content does not match the golden file.")

    def test_text_preservation_commented(self):
        # Create from a test data
        existing_file = os.path.join(os.path.dirname(__file__),
                                     'testdata/parser/mixed.beancount')
        dest_file = os.path.join(self.account_dir, "202504.beancount")
        shutil.copy(existing_file, dest_file)

        importer = FakeImporter()

        # Create a processor
        processor = FileWriter(importers=[self.fake_importer],
                               hooks=[],
                               destination=self.dest_dir,
                               existing_file=dest_file)

        duplicate_transaction = self._create_test_transaction(
            date=datetime.date(2025, 4, 20),
            payee="Payee C",
            narration="Transaction",
            amount=decimal.Decimal("-500"))
        duplicate_transaction.postings.pop()
        duplicate_transaction.meta['__duplicate__'] = self.existing_transaction

        # Create entries_by_account_month and entries_by_dest_file
        entries_by_account_month = {
            ("Assets:Cash:Wallet", "202504"):
            [(duplicate_transaction, importer)]
        }

        # Process the output
        processor.process_output(entries_by_account_month)

        with open(dest_file, "r") as f:
            written_content = f.read()

        golden_path = os.path.join(
            os.path.dirname(__file__),
            'testdata/writer/mixed_commented.golden.beancount')
        with open(golden_path, "r") as f:
            golden_content = f.read()

        self.maxDiff = None
        self.assertEqual(
            written_content, golden_content,
            "The written content does not match the golden file.")

    def test_full_scenario(self):
        # Create from a test data
        existing_file = os.path.join(self.test_input_dir,
                                     'parser/mixed.beancount')
        dest_file = os.path.join(self.account_dir, "202504.beancount")
        shutil.copy(existing_file, dest_file)

        root_file = os.path.join(self.dest_dir, "root.beancount")
        root_template_file = os.path.join(
            self.test_input_dir, 'writer/full_scenario.root.beancount')
        shutil.copy(root_template_file, root_file)

        importer = IdentityImporter(account_name="Assets:Cash:Wallet")

        # Create a processor
        processor = FileWriter(importers=[importer],
                               hooks=[],
                               destination=self.dest_dir,
                               existing_file=root_file)

        input_file = os.path.join(self.test_input_dir,
                                  "writer/full_scenario.source.beancount")

        # Process the output
        processor.process([input_file])

        with open(dest_file, "r") as f:
            written_content = f.read()

        golden_path = os.path.join(self.test_input_dir,
                                   'writer/full_scenario.golden.beancount')
        with open(golden_path, "r") as f:
            golden_content = f.read()

        self.maxDiff = None
        self.assertEqual(
            written_content, golden_content,
            "The written content does not match the golden file.")


if __name__ == "__main__":
    unittest.main()
