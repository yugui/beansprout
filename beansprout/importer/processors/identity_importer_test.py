#!/usr/bin/env python3
"""Unit tests for the identity_importer module."""

import os
import tempfile
import unittest

import beangulp
from beancount.core import data
from beancount.parser import printer

from beansprout.importer.processors.identity_importer import IdentityImporter


class TestIdentityImporter(unittest.TestCase):
    """Test the IdentityImporter class."""

    def setUp(self):
        """Set up the test environment."""
        # Create a temporary directory for test files
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = self.temp_dir.name

        # Create a test beancount file
        self.test_file = os.path.join(self.test_dir, "test.beancount")
        with open(self.test_file, "w") as f:
            f.write(";; -*- mode: beancount -*-\n\n")
            f.write("2025-04-15 * \"Test Payee\" \"Test Transaction\"\n")
            f.write("  Assets:Cash:Wallet  -1000 JPY\n")
            f.write("  Expenses:Food        1000 JPY\n\n")

        # Create a non-beancount file
        self.non_beancount_file = os.path.join(self.test_dir, "test.txt")
        with open(self.non_beancount_file, "w") as f:
            f.write("This is not a beancount file.\n")

        # Create an importer
        self.account_name = "Assets:Cash:Wallet"
        self.importer = IdentityImporter(self.account_name)

    def tearDown(self):
        """Clean up after the test."""
        self.temp_dir.cleanup()

    def test_identify(self):
        """Test the identify method."""
        # Should identify beancount files
        self.assertTrue(self.importer.identify(self.test_file))
        # Should not identify non-beancount files
        self.assertFalse(self.importer.identify(self.non_beancount_file))

    def test_account(self):
        """Test the account method."""
        # Should return the account name provided in the constructor
        self.assertEqual(self.importer.account(self.test_file),
                         self.account_name)

    def test_extract(self):
        """Test the extract method."""
        # Extract entries from the test file
        entries = self.importer.extract(self.test_file)

        # Should extract one entry
        self.assertEqual(len(entries), 1)

        # The entry should be a transaction
        entry = entries[0]
        self.assertIsInstance(entry, data.Transaction)

        # Check the transaction details
        self.assertEqual(entry.payee, "Test Payee")
        self.assertEqual(entry.narration, "Test Transaction")
        self.assertEqual(len(entry.postings), 2)

        # Check the postings
        self.assertEqual(entry.postings[0].account, "Assets:Cash:Wallet")
        self.assertEqual(entry.postings[0].units.number, -1000)
        self.assertEqual(entry.postings[0].units.currency, "JPY")

        self.assertEqual(entry.postings[1].account, "Expenses:Food")
        self.assertEqual(entry.postings[1].units.number, 1000)
        self.assertEqual(entry.postings[1].units.currency, "JPY")


if __name__ == "__main__":
    unittest.main()
