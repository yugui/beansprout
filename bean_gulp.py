#!/usr/bin/python3

import os
import beangulp
from importers.moneyforward import Importer as MoneyForwardImporter
from importers.account_predictor import AccountPredictor

# Define static file paths for account mappings
# Use absolute paths to ensure files are found regardless of working directory
EXPENSE_ACCOUNTS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "expense_accounts.tsv")
INCOME_ACCOUNTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "data", "income_accounts.tsv")


def load_account_mappings(file_path):
    """Load account mappings from a TSV file.
    
    Args:
        file_path: Path to the TSV file containing account mappings.
        
    Returns:
        A dictionary mapping categories to accounts.
    """
    mappings = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split('\t')
                if len(parts) == 2:
                    category, account = parts
                    mappings[category] = account
    except FileNotFoundError:
        print(f"Warning: Account mapping file not found: {file_path}")
    return mappings


def main():
    # Load account mappings from TSV files
    expense_accounts = load_account_mappings(EXPENSE_ACCOUNTS_FILE)
    income_accounts = load_account_mappings(INCOME_ACCOUNTS_FILE)

    # Load account predictor from pickle file
    # Check if the path is provided in an environment variable
    account_predictor_path = os.environ.get(
        "BEANGULP_ACCOUNT_PREDICTOR_PATH",
        os.path.expanduser("~/.cache/beangulp/account-prediction.pickle"))
    try:
        account_predictor = AccountPredictor.load(account_predictor_path)
        print(f"Loaded account predictor from {account_predictor_path}")
    except FileNotFoundError:
        print(
            f"Account predictor file not found at {account_predictor_path}, creating a new one"
        )
        account_predictor = AccountPredictor(min_confidence=0.6)

    # Define importers
    importers = [
        # MoneyForward ME importer
        # Configure with your wallet account and mappings loaded from TSV files
        MoneyForwardImporter(
            wallet_account="Assets:Cash:Wallet",
            account_predictor=account_predictor,
            expense_accounts=expense_accounts,
            income_accounts=income_accounts,
            currency="JPY",
        ),
    ]

    # Define hooks for post-processing
    hooks = []

    # Create and run the ingest command
    ingest = beangulp.Ingest(importers, hooks)
    ingest()


if __name__ == "__main__":
    main()
