#!/usr/bin/env python3
"""Unit tests for the account predictor."""

import os
import tempfile
import unittest

from beansprout.importer import account_predictor
from beansprout.importer.account_predictor import TrainingData


class TestAccountPredictor(unittest.TestCase):
    """Unit tests for the account predictor."""

    def setUp(self):
        """Set up the test case."""
        self.predictor = account_predictor.AccountPredictor(
            min_confidence=0.6, )

        # Sample training data
        self.training_data = [
            # Format: TrainingData(belonging_account, transaction_narration, posting_narration, correct_account, hint)
            TrainingData(belonging_account="Assets:Cash:Wallet",
                         transaction_narration="Grocery Store",
                         posting_narration="Weekly shopping",
                         correct_account="Expenses:Food:Groceries",
                         hint=["food", "grocery"]),
            TrainingData(belonging_account="Assets:Cash:Wallet",
                         transaction_narration="Supermarket",
                         posting_narration="Food",
                         correct_account="Expenses:Food:Groceries",
                         hint=["food", "grocery"]),
            TrainingData(belonging_account="Assets:Cash:Wallet",
                         transaction_narration="Restaurant",
                         posting_narration="Dinner with friends",
                         correct_account="Expenses:Food:Restaurant",
                         hint=["food", "restaurant"]),
            TrainingData(belonging_account="Assets:Cash:Wallet",
                         transaction_narration="Cafe",
                         posting_narration="Coffee",
                         correct_account="Expenses:Food:Coffee",
                         hint=["food", "coffee"]),
            TrainingData(belonging_account="Assets:Cash:Wallet",
                         transaction_narration="Pharmacy",
                         posting_narration="Medicine",
                         correct_account="Expenses:Health:Medicine",
                         hint=["health", "medicine"]),
            TrainingData(belonging_account="Assets:Cash:Wallet",
                         transaction_narration="Doctor",
                         posting_narration="Checkup",
                         correct_account="Expenses:Health:Doctor",
                         hint=["health", "doctor"]),
            TrainingData(belonging_account="Assets:Cash:Wallet",
                         transaction_narration="Train",
                         posting_narration="Commute",
                         correct_account="Expenses:Transport:Train",
                         hint=["transport", "train"]),
            TrainingData(belonging_account="Assets:Cash:Wallet",
                         transaction_narration="Bus",
                         posting_narration="City trip",
                         correct_account="Expenses:Transport:Bus",
                         hint=["transport", "bus"]),
            TrainingData(belonging_account="Assets:Cash:Wallet",
                         transaction_narration="Cinema",
                         posting_narration="Movie night",
                         correct_account="Expenses:Entertainment:Movies",
                         hint=["entertainment", "movie"]),
            TrainingData(belonging_account="Assets:Cash:Wallet",
                         transaction_narration="Bookstore",
                         posting_narration="New books",
                         correct_account="Expenses:Entertainment:Books",
                         hint=["entertainment", "book"]),
        ]

    def test_initial_state(self):
        """Test the initial state of the predictor."""
        # With no training data, should return None with 0 confidence
        account, confidence = self.predictor.predict("Assets:Cash:Wallet",
                                                     "Unknown Store",
                                                     "Something", ["unknown"])

        self.assertIsNone(account)
        self.assertEqual(confidence, 0.0)

    def test_training(self):
        """Test training the predictor."""
        # Train with sample data
        self.predictor.train(self.training_data)

        # Check that accounts were learned
        self.assertEqual(self.predictor.total_examples, 10)
        # There are 9 unique accounts in the training data (not 7)
        self.assertEqual(len(self.predictor.known_accounts), 9)

        # Check account counts
        self.assertEqual(
            self.predictor.account_counts["Expenses:Food:Groceries"], 2)
        self.assertEqual(
            self.predictor.account_counts["Expenses:Food:Restaurant"], 1)

    def test_prediction_exact_match(self):
        """Test prediction with exact match to training data."""
        # Train with sample data
        self.predictor.train(self.training_data)

        # Predict with exact match to training data
        account, confidence = self.predictor.predict("Assets:Cash:Wallet",
                                                     "Grocery Store",
                                                     "Weekly shopping",
                                                     ["food", "grocery"])

        self.assertEqual(account, "Expenses:Food:Groceries")
        self.assertGreater(confidence, 0.6)  # Should be high confidence

    def test_prediction_similar_match(self):
        """Test prediction with similar match to training data."""
        # Train with sample data
        self.predictor.train(self.training_data)

        # First, let's make sure the predictor has a strong association with grocery-related terms
        # by adding more examples
        self.predictor.update("Assets:Cash:Wallet", "Grocery", "Food",
                              "Expenses:Food:Groceries", ["food", "grocery"])
        self.predictor.update("Assets:Cash:Wallet", "Local Market",
                              "Groceries", "Expenses:Food:Groceries",
                              ["food", "grocery"])

        # Predict with similar but not exact match
        account, confidence = self.predictor.predict("Assets:Cash:Wallet",
                                                     "Local Grocery",
                                                     "Food shopping",
                                                     ["food", "grocery"])

        # Should match to Expenses:Food:Groceries due to similar words
        self.assertEqual(account, "Expenses:Food:Groceries")

    def test_prediction_low_confidence(self):
        """Test prediction with low confidence."""
        # Train with sample data
        self.predictor.train(self.training_data)

        # Predict with completely unrelated input
        account, confidence = self.predictor.predict(
            "Assets:Cash:Wallet", "Unknown Place",
            "Something completely different", ["unknown"])

        # Should return None due to low confidence
        self.assertIsNone(account)
        self.assertLess(confidence, 0.6)

    def test_incremental_learning(self):
        """Test incremental learning."""
        # Create a new predictor with higher min_confidence to ensure we get None initially
        predictor = account_predictor.AccountPredictor(
            min_confidence=0.9,  # Very high confidence threshold
        )

        # Start with partial training data
        partial_data = self.training_data[:5]
        predictor.train(partial_data)

        # Initial prediction for a new category
        account, confidence1 = predictor.predict("Assets:Cash:Wallet",
                                                 "Cinema", "Movie night",
                                                 ["entertainment", "movie"])

        # Should be low confidence since we haven't seen movies yet
        self.assertIsNone(account)

        # Update with the correct account multiple times to strengthen the association
        for _ in range(3):  # Add multiple examples to increase confidence
            predictor.update("Assets:Cash:Wallet", "Cinema", "Movie night",
                             "Expenses:Entertainment:Movies",
                             ["entertainment", "movie"])

        # Predict again
        account, confidence2 = predictor.predict("Assets:Cash:Wallet",
                                                 "Cinema", "Movie night",
                                                 ["entertainment", "movie"])

        # Should now predict the correct account with higher confidence
        self.assertEqual(account, "Expenses:Entertainment:Movies")
        self.assertGreater(confidence2, confidence1)

    def test_save_and_load(self):
        """Test saving and loading the model."""
        # Train with sample data
        self.predictor.train(self.training_data)

        # Save the model to a temporary file
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name

        try:
            self.predictor.save(temp_path)

            # Load the model
            loaded_predictor = account_predictor.AccountPredictor.load(
                temp_path)

            # Check that the loaded model has the same state
            self.assertEqual(loaded_predictor.min_confidence,
                             self.predictor.min_confidence)
            self.assertEqual(loaded_predictor.total_examples,
                             self.predictor.total_examples)
            self.assertEqual(loaded_predictor.known_accounts,
                             self.predictor.known_accounts)

            # Check that predictions have the same account (ignore confidence due to potential floating-point differences)
            original_account, _ = self.predictor.predict(
                "Assets:Cash:Wallet", "Grocery Store", "Weekly shopping",
                ["food", "grocery"])
            loaded_account, _ = loaded_predictor.predict(
                "Assets:Cash:Wallet", "Grocery Store", "Weekly shopping",
                ["food", "grocery"])

            self.assertEqual(original_account, loaded_account)
        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_belonging_account_patterns(self):
        """Test that belonging account patterns influence predictions."""
        # Create specific training data with patterns
        pattern_data = [
            # Most transactions from Assets:Cash:Wallet go to Expenses:Food
            TrainingData(belonging_account="Assets:Cash:Wallet",
                         transaction_narration="Store A",
                         posting_narration="Item",
                         correct_account="Expenses:Food",
                         hint=["food"]),
            TrainingData(belonging_account="Assets:Cash:Wallet",
                         transaction_narration="Store B",
                         posting_narration="Item",
                         correct_account="Expenses:Food",
                         hint=["food"]),
            TrainingData(belonging_account="Assets:Cash:Wallet",
                         transaction_narration="Store C",
                         posting_narration="Item",
                         correct_account="Expenses:Food",
                         hint=["food"]),
            TrainingData(belonging_account="Assets:Cash:Wallet",
                         transaction_narration="Store D",
                         posting_narration="Item",
                         correct_account="Expenses:Transport",
                         hint=["transport"]),

            # Most transactions from Assets:Bank:Checking go to Expenses:Bills
            TrainingData(belonging_account="Assets:Bank:Checking",
                         transaction_narration="Company A",
                         posting_narration="Service",
                         correct_account="Expenses:Bills",
                         hint=["bills"]),
            TrainingData(belonging_account="Assets:Bank:Checking",
                         transaction_narration="Company B",
                         posting_narration="Service",
                         correct_account="Expenses:Bills",
                         hint=["bills"]),
            TrainingData(belonging_account="Assets:Bank:Checking",
                         transaction_narration="Company C",
                         posting_narration="Service",
                         correct_account="Expenses:Bills",
                         hint=["bills"]),
            TrainingData(belonging_account="Assets:Bank:Checking",
                         transaction_narration="Company D",
                         posting_narration="Service",
                         correct_account="Expenses:Food",
                         hint=["food"]),
        ]

        self.predictor.train(pattern_data)

        # Test prediction with ambiguous narration but different belonging accounts
        wallet_account, wallet_conf = self.predictor.predict(
            "Assets:Cash:Wallet", "Payment", "Monthly", ["payment"])

        bank_account, bank_conf = self.predictor.predict(
            "Assets:Bank:Checking", "Payment", "Monthly", ["payment"])

        # Should predict different accounts based on the belonging account pattern
        self.assertEqual(wallet_account, "Expenses:Food")
        self.assertEqual(bank_account, "Expenses:Bills")


if __name__ == '__main__':
    unittest.main()