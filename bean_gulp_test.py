#!/usr/bin/python3

import os
import unittest
import tempfile
import pickle
from unittest import mock
from datetime import date

from beancount.core import data
from beancount.core.amount import Amount
from beancount.core.number import Decimal

from importers.account_predictor import AccountPredictor
from bean_gulp import ModelTrainer


class TestModelTrainer(unittest.TestCase):
    """Test the ModelTrainer class."""

    def setUp(self):
        """Set up the test environment."""
        # Create a temporary directory for the model file
        self.temp_dir = tempfile.TemporaryDirectory()
        self.model_path = os.path.join(self.temp_dir.name,
                                       "account-prediction.pickle")

        # Create a test account predictor
        self.account_predictor = AccountPredictor(min_confidence=0.6)

        # Create a mock importer
        self.mock_importer = mock.MagicMock()

        # Create a ModelTrainer instance
        self.trainer = ModelTrainer(importers=[self.mock_importer],
                                    account_predictor=self.account_predictor,
                                    account_predictor_path=self.model_path,
                                    destination="/tmp",
                                    quiet=1)

    def tearDown(self):
        """Clean up after the test."""
        self.temp_dir.cleanup()

    def test_is_duplicate(self):
        """Test the is_duplicate method."""
        # Create a test entry with __duplicate__ metadata
        entry = data.Transaction(meta={"__duplicate__": "duplicate_entry"},
                                 date=date(2023, 1, 1),
                                 flag="*",
                                 payee=None,
                                 narration="Test transaction",
                                 tags=set(),
                                 links=set(),
                                 postings=[])

        # Test that the entry is recognized as a duplicate
        self.assertTrue(self.trainer.is_duplicate(entry))

        # Create a test entry without __duplicate__ metadata
        entry = data.Transaction(meta={},
                                 date=date(2023, 1, 1),
                                 flag="*",
                                 payee=None,
                                 narration="Test transaction",
                                 tags=set(),
                                 links=set(),
                                 postings=[])

        # Test that the entry is not recognized as a duplicate
        self.assertFalse(self.trainer.is_duplicate(entry))

    def test_process_posting(self):
        """Test the _process_posting method."""
        # Create a test account
        account = "Assets:Cash:Wallet"

        # Create a test entry with a posting
        entry = data.Transaction(
            meta={},
            date=date(2023, 1, 1),
            flag="*",
            payee=None,
            narration="Test transaction",
            tags=set(),
            links=set(),
            postings=[
                data.Posting(account=account,
                             units=Amount(Decimal("100"), "JPY"),
                             cost=None,
                             price=None,
                             flag=None,
                             meta={}),
                data.Posting(account="Expenses:Food",
                             units=Amount(Decimal("-100"), "JPY"),
                             cost=None,
                             price=None,
                             flag=None,
                             meta={"narration": "Test posting"})
            ])

        # Create a duplicate entry with a different account
        duplicate_entry = data.Transaction(
            meta={},
            date=date(2023, 1, 1),
            flag="*",
            payee=None,
            narration="Test transaction",
            tags=set(),
            links=set(),
            postings=[
                data.Posting(account=account,
                             units=Amount(Decimal("100"), "JPY"),
                             cost=None,
                             price=None,
                             flag=None,
                             meta={}),
                data.Posting(account="Expenses:Groceries",
                             units=Amount(Decimal("-100"), "JPY"),
                             cost=None,
                             price=None,
                             flag=None,
                             meta={})
            ])

        # Process the posting
        self.trainer._process_posting(account=account,
                                      entry=entry,
                                      posting=entry.postings[1],
                                      duplicate_entry=duplicate_entry)

        # Check that the account predictor was updated
        self.assertEqual(self.trainer.training_count, 1)

        # Save the model and check that it exists
        self.trainer.account_predictor.save(self.model_path)
        self.assertTrue(os.path.exists(self.model_path))

        # Load the model and check that it has the training data
        loaded_predictor = AccountPredictor.load(self.model_path)
        self.assertEqual(loaded_predictor.total_examples, 1)

        # Test prediction
        predicted_account, confidence = loaded_predictor.predict(
            belonging_account=account,
            transaction_narration="Test transaction",
            posting_narration="Test posting")

        # The prediction should be the account from the duplicate entry
        self.assertEqual(predicted_account, "Expenses:Groceries")
        self.assertGreater(confidence, 0.6)

    def test_process_output(self):
        """Test the process_output method."""
        # Create a test account
        account = "Assets:Cash:Wallet"
        year_month = "202301"

        # Create a test entry with a posting
        entry = data.Transaction(
            meta={"__duplicate__": None},  # Will be set below
            date=date(2023, 1, 1),
            flag="*",
            payee=None,
            narration="Test transaction",
            tags=set(),
            links=set(),
            postings=[
                data.Posting(account=account,
                             units=Amount(Decimal("100"), "JPY"),
                             cost=None,
                             price=None,
                             flag=None,
                             meta={}),
                data.Posting(account="Expenses:Food",
                             units=Amount(Decimal("-100"), "JPY"),
                             cost=None,
                             price=None,
                             flag=None,
                             meta={"narration": "Test posting"})
            ])

        # Create a duplicate entry with a different account
        duplicate_entry = data.Transaction(
            meta={},
            date=date(2023, 1, 1),
            flag="*",
            payee=None,
            narration="Test transaction",
            tags=set(),
            links=set(),
            postings=[
                data.Posting(account=account,
                             units=Amount(Decimal("100"), "JPY"),
                             cost=None,
                             price=None,
                             flag=None,
                             meta={}),
                data.Posting(account="Expenses:Groceries",
                             units=Amount(Decimal("-100"), "JPY"),
                             cost=None,
                             price=None,
                             flag=None,
                             meta={})
            ])

        # Set the duplicate entry reference
        entry.meta["__duplicate__"] = duplicate_entry

        # Create the entries_by_account_month dictionary
        entries_by_account_month = {
            (account, year_month): [(entry, self.mock_importer)]
        }

        # Create the entries_by_dest_file dictionary
        entries_by_dest_file = {}

        # Process the output
        self.trainer.process_output(entries_by_account_month,
                                    entries_by_dest_file)

        # Check that the account predictor was updated
        self.assertEqual(self.trainer.training_count, 1)

        # Save the model and check that it exists
        self.trainer.account_predictor.save(self.model_path)
        self.assertTrue(os.path.exists(self.model_path))

        # Load the model and check that it has the training data
        loaded_predictor = AccountPredictor.load(self.model_path)
        self.assertEqual(loaded_predictor.total_examples, 1)

        # Test prediction
        predicted_account, confidence = loaded_predictor.predict(
            belonging_account=account,
            transaction_narration="Test transaction",
            posting_narration="Test posting")

        # The prediction should be the account from the duplicate entry
        self.assertEqual(predicted_account, "Expenses:Groceries")
        self.assertGreater(confidence, 0.6)


if __name__ == "__main__":
    unittest.main()
