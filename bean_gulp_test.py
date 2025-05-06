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
from importers.merge import Processor


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

    @mock.patch("importers.merge.Processor.process")
    def test_merge_command_integration(self, mock_process):
        """Test that the merge command correctly uses the Processor class."""
        # Set up the mock to return success
        mock_process.return_value = 0

        # Create a test CLI context
        with mock.patch("click.pass_obj", lambda f: f):
            # Invoke the merge command
            result = self.runner.invoke(bean_gulp._merge, [
                "--destination", self.dest_dir, "--reverse", "--failfast",
                "--quiet", self.source_file
            ],
                                        obj=self.mock_ctx)

        # Check that the command executed successfully
        self.assertEqual(result.exit_code, 0)

        # Check that the Processor.process method was called with the correct arguments
        mock_process.assert_called_once()
        # The first argument to mock_process should contain the source file name
        source_file_name = os.path.basename(self.source_file)
        self.assertTrue(
            any(source_file_name in str(arg)
                for arg in mock_process.call_args[0][0]))

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
