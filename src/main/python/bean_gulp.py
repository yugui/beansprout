#!/usr/bin/python3

import beangulp
from src.main.python.importers.moneyforward import Importer as MoneyForwardImporter


def main():
    # Define importers
    importers = [
        # MoneyForward ME importer
        # Configure with your wallet account and optional category mappings
        MoneyForwardImporter(
            wallet_account="Assets:Cash:Wallet",
            expense_accounts={
                "食費": "Expenses:Food",
                "食費:昼ご飯": "Expenses:Food:Lunch",
                "食費:食料品": "Expenses:Food:Groceries",
                "交通費": "Expenses:Transport",
                "健康・医療": "Expenses:Health",
                "健康・医療:医療費": "Expenses:Health:Medical",
                "趣味・娯楽": "Expenses:Entertainment",
                "交際費": "Expenses:Social",
            },
            income_accounts={
                "収入": "Income:Other",
                "収入:債権回収": "Income:Reimbursement",
            },
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
