"""Unit tests for the account predictor."""

import os
import tempfile
import unittest

from importers import account_predictor


class TestAccountPredictor(unittest.TestCase):
    """Unit tests for the account predictor."""

    def setUp(self):
        """Set up the test case."""
        self.predictor = account_predictor.AccountPredictor(
            default_account="Expenses:Uncategorized",
            min_confidence=0.6,
        )

        # Sample training data
        self.training_data = [
            # Format: (belonging_account, transaction_narration, posting_narration, correct_account)
            ("Assets:Cash:Wallet", "Grocery Store", "Weekly shopping",
             "Expenses:Food:Groceries"),
            ("Assets:Cash:Wallet", "Supermarket", "Food",
             "Expenses:Food:Groceries"),
            ("Assets:Cash:Wallet", "Restaurant", "Dinner with friends",
             "Expenses:Food:Restaurant"),
            ("Assets:Cash:Wallet", "Cafe", "Coffee", "Expenses:Food:Coffee"),
            ("Assets:Cash:Wallet", "Pharmacy", "Medicine",
             "Expenses:Health:Medicine"),
            ("Assets:Cash:Wallet", "Doctor", "Checkup",
             "Expenses:Health:Doctor"),
            ("Assets:Cash:Wallet", "Train", "Commute",
             "Expenses:Transport:Train"),
            ("Assets:Cash:Wallet", "Bus", "City trip",
             "Expenses:Transport:Bus"),
            ("Assets:Cash:Wallet", "Cinema", "Movie night",
             "Expenses:Entertainment:Movies"),
            ("Assets:Cash:Wallet", "Bookstore", "New books",
             "Expenses:Entertainment:Books"),
        ]

    def test_initial_state(self):
        """Test the initial state of the predictor."""
        # With no training data, should return default account with 0 confidence
        account, confidence = self.predictor.predict("Assets:Cash:Wallet",
                                                     "Unknown Store",
                                                     "Something")

        self.assertEqual(account, "Expenses:Uncategorized")
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
                                                     "Weekly shopping")

        self.assertEqual(account, "Expenses:Food:Groceries")
        self.assertGreater(confidence, 0.6)  # Should be high confidence

    def test_prediction_similar_match(self):
        """Test prediction with similar match to training data."""
        # Train with sample data
        self.predictor.train(self.training_data)

        # First, let's make sure the predictor has a strong association with grocery-related terms
        # by adding more examples
        self.predictor.update("Assets:Cash:Wallet", "Grocery", "Food",
                              "Expenses:Food:Groceries")
        self.predictor.update("Assets:Cash:Wallet", "Local Market",
                              "Groceries", "Expenses:Food:Groceries")

        # Predict with similar but not exact match
        account, confidence = self.predictor.predict("Assets:Cash:Wallet",
                                                     "Local Grocery",
                                                     "Food shopping")

        # Should match to Expenses:Food:Groceries due to similar words
        self.assertEqual(account, "Expenses:Food:Groceries")

    def test_prediction_low_confidence(self):
        """Test prediction with low confidence."""
        # Train with sample data
        self.predictor.train(self.training_data)

        # Predict with completely unrelated input
        account, confidence = self.predictor.predict(
            "Assets:Cash:Wallet", "Unknown Place",
            "Something completely different")

        # Should return default account due to low confidence
        self.assertEqual(account, "Expenses:Uncategorized")
        self.assertLess(confidence, 0.6)

    def test_incremental_learning(self):
        """Test incremental learning."""
        # Create a new predictor with higher min_confidence to ensure we get the default account initially
        predictor = account_predictor.AccountPredictor(
            default_account="Expenses:Uncategorized",
            min_confidence=0.9,  # Very high confidence threshold
        )

        # Start with partial training data
        partial_data = self.training_data[:5]
        predictor.train(partial_data)

        # Initial prediction for a new category
        account, confidence1 = predictor.predict("Assets:Cash:Wallet",
                                                 "Cinema", "Movie night")

        # Should be low confidence since we haven't seen movies yet
        self.assertEqual(account, "Expenses:Uncategorized")

        # Update with the correct account multiple times to strengthen the association
        for _ in range(3):  # Add multiple examples to increase confidence
            predictor.update("Assets:Cash:Wallet", "Cinema", "Movie night",
                             "Expenses:Entertainment:Movies")

        # Predict again
        account, confidence2 = predictor.predict("Assets:Cash:Wallet",
                                                 "Cinema", "Movie night")

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
            self.assertEqual(loaded_predictor.default_account,
                             self.predictor.default_account)
            self.assertEqual(loaded_predictor.min_confidence,
                             self.predictor.min_confidence)
            self.assertEqual(loaded_predictor.total_examples,
                             self.predictor.total_examples)
            self.assertEqual(loaded_predictor.known_accounts,
                             self.predictor.known_accounts)

            # Check that predictions have the same account (ignore confidence due to potential floating-point differences)
            original_account, _ = self.predictor.predict(
                "Assets:Cash:Wallet", "Grocery Store", "Weekly shopping")
            loaded_account, _ = loaded_predictor.predict(
                "Assets:Cash:Wallet", "Grocery Store", "Weekly shopping")

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
            ("Assets:Cash:Wallet", "Store A", "Item", "Expenses:Food"),
            ("Assets:Cash:Wallet", "Store B", "Item", "Expenses:Food"),
            ("Assets:Cash:Wallet", "Store C", "Item", "Expenses:Food"),
            ("Assets:Cash:Wallet", "Store D", "Item", "Expenses:Transport"),

            # Most transactions from Assets:Bank:Checking go to Expenses:Bills
            ("Assets:Bank:Checking", "Company A", "Service", "Expenses:Bills"),
            ("Assets:Bank:Checking", "Company B", "Service", "Expenses:Bills"),
            ("Assets:Bank:Checking", "Company C", "Service", "Expenses:Bills"),
            ("Assets:Bank:Checking", "Company D", "Service", "Expenses:Food"),
        ]

        self.predictor.train(pattern_data)

        # Test prediction with ambiguous narration but different belonging accounts
        wallet_account, wallet_conf = self.predictor.predict(
            "Assets:Cash:Wallet", "Payment", "Monthly")

        bank_account, bank_conf = self.predictor.predict(
            "Assets:Bank:Checking", "Payment", "Monthly")

        # Should predict different accounts based on the belonging account pattern
        self.assertEqual(wallet_account, "Expenses:Food")
        self.assertEqual(bank_account, "Expenses:Bills")


if __name__ == '__main__':
    unittest.main()
