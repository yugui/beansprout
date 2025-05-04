"""Importer for MoneyForward ME CSV files.

This module provides a custom importer for MoneyForward ME CSV files that works with beangulp.
MoneyForward ME is a personal finance management service in Japan that exports
single-entry transactions in CSV format.

The importer successfully:
1. Identifies MoneyForward ME CSV files based on filename pattern and content
2. Handles Shift_JIS encoded CSV files
3. Extracts transactions from the CSV files
4. Converts single-entry transactions to double-entry Beancount transactions
5. Maps MoneyForward ME categories to appropriate Beancount accounts
6. Preserves metadata like category, subcategory, memo, and ID

Usage:
    ```python
    from importers.moneyforward import Importer as MoneyForwardImporter
    
    # Create an importer instance
    importer = MoneyForwardImporter(
        wallet_account="Assets:Cash:Wallet",
        expense_accounts={
            "食費": "Expenses:Food",
            "食費:昼ご飯": "Expenses:Food:Lunch",
            # Add more mappings as needed
        },
        income_accounts={
            "収入": "Income:Other",
            # Add more mappings as needed
        },
        currency="JPY",
    )
    
    # Use with beangulp
    importers = [importer]
    ingest = beangulp.Ingest(importers)
    ingest()
    ```

The importer can be used with the `bean-gulp` command:
    ```bash
    bazel run //src/main/python:bean-gulp -- identify /path/to/wallet-YYYYMM.csv
    bazel run //src/main/python:bean-gulp -- extract /path/to/wallet-YYYYMM.csv
    ```
"""

import datetime
import re
from os import path
from typing import Any, Dict, List, Optional, Pattern, Union

from beancount.core import data
from beangulp import mimetypes
from beangulp.importers import csvbase


class Importer(csvbase.Importer):
    """Importer for MoneyForward ME CSV files.

    This importer processes CSV files exported from MoneyForward ME, which is a
    personal finance management service in Japan. The CSV files contain
    single-entry transactions.
    """

    # File configuration
    encoding = 'shift_jis'
    skiplines = 1  # Skip the header row
    names = False  # No column names in the file

    # Column mappings to MoneyForward ME CSV columns
    # Example row: ["1","2025/04/30","クリニック","-410","財布","健康・医療","医療費","","0","abc-def_ghi"]
    flag = csvbase.Column(0)  # Column 1: Transaction flag (0 or 1)
    date = csvbase.Date(1,
                        '%Y/%m/%d')  # Column 2: Date (日付) in YYYY/MM/DD format
    payee = csvbase.Column(2)  # Column 3: Description/Payee (内容)
    narration = csvbase.Column(
        7, default='')  # Column 8: Use memo (メモ) as narration
    amount = csvbase.Amount(
        3, {',': ''})  # Column 4: Amount (金額) (negative for expenses)
    wallet = csvbase.Column(4)  # Column 5: Account/Wallet (財布 = wallet)
    category = csvbase.Column(
        5)  # Column 6: Category (大項目) e.g., 食費 (food), 健康・医療 (health)
    subcategory = csvbase.Column(
        6)  # Column 7: Subcategory (中項目) e.g., 昼ご飯 (lunch), 医療費 (medical)
    memo = csvbase.Column(7)  # Column 8: Notes/Memo (メモ)
    status = csvbase.Column(8)  # Column 9: Transfer flag (振替) (0 or 1)
    id = csvbase.Column(9)  # Column 10: Unique transaction ID

    def __init__(
        self,
        wallet_account: str,
        expense_accounts: Optional[Dict[str, str]] = None,
        income_accounts: Optional[Dict[str, str]] = None,
        default_expense_account: str = "Expenses:Uncategorized",
        default_income_account: str = "Income:Uncategorized",
        currency: str = "JPY",
        file_pattern: str = r".*\.csv",
    ) -> None:
        """Initialize the importer.

        Args:
            wallet_account: The Beancount account for the wallet.
            expense_accounts: A dictionary mapping MoneyForward ME categories to
                Beancount expense accounts.
            income_accounts: A dictionary mapping MoneyForward ME categories to
                Beancount income accounts.
            default_expense_account: The default Beancount expense account.
            default_income_account: The default Beancount income account.
            currency: The currency of the transactions.
            file_pattern: A regular expression pattern to identify MoneyForward ME
                CSV files.
        """
        super().__init__(wallet_account, currency)
        self.expense_accounts = expense_accounts or {}
        self.income_accounts = income_accounts or {}
        self.default_expense_account = default_expense_account
        self.default_income_account = default_income_account
        self.file_pattern = file_pattern

    def identify(self, filepath: str) -> bool:
        """Identify if the file is a MoneyForward ME CSV file.

        Args:
            filepath: The file to identify.

        Returns:
            True if the file is a MoneyForward ME CSV file, False otherwise.
        """
        # Check if the filename matches the pattern
        if not re.match(self.file_pattern, path.basename(filepath)):
            return False

        # Check if it's a CSV file
        mimetype, encoding = mimetypes.guess_type(filepath)
        if mimetype != 'text/csv':
            return False

        # Try to read the first few lines to confirm it's a MoneyForward ME CSV file
        try:
            with open(filepath, 'r', encoding=self.encoding) as f:
                header = f.readline()
                if 'ID' not in header:
                    return False
                return True
        except (UnicodeDecodeError, IOError):
            return False

    def filename(self, filepath: str) -> str:
        """Return a descriptive filename for the file.

        Args:
            filepath: The file path.

        Returns:
            A descriptive filename.
        """
        return 'moneyforward.' + path.basename(filepath)

    def file_date(self, filepath: str) -> Optional[datetime.date]:
        """Return the date associated with the file.

        Args:
            filepath: The file path.

        Returns:
            The date associated with the file, or None if it cannot be determined.
        """
        # Try to extract the date from the filename (e.g., wallet-202504.csv)
        match = re.match(r'wallet-(\d{4})(\d{2})\.csv',
                         path.basename(filepath))
        if match:
            year, month = match.groups()
            return datetime.date(int(year), int(month), 1)
        return None

    def metadata(self, filepath: str, lineno: int, row: Any) -> Dict[str, Any]:
        """Build transaction metadata dictionary.

        Args:
            filepath: Path to the file being imported.
            lineno: Line number of the data being processed.
            row: The data row being processed.

        Returns:
            A metadata dictionary.
        """
        meta = data.new_metadata(filepath, lineno)
        meta['category'] = row.category
        meta['subcategory'] = row.subcategory
        if row.memo:
            meta['memo'] = row.memo
        meta['id'] = row.id
        return meta

    def finalize(self, txn: data.Transaction,
                 row: Any) -> Optional[data.Transaction]:
        """Post process the transaction.

        Args:
            txn: The just build Transaction object.
            row: The data row being processed.

        Returns:
            A potentially extended or modified Transaction object or None.
        """
        # Skip empty transactions
        if not txn.postings:
            return None

        # Get the first posting (created by the base class)
        posting = txn.postings[0]
        amount_value = posting.units.number

        # Check if this is a transfer transaction
        if row.status == "1":
            # This is a transfer transaction
            destination_account = self._guess_transfer_destination_account(
                row.category, row.subcategory, row.memo, row.narration)

            if destination_account is not None:
                # Create a new posting for the destination account
                units = data.Amount(-amount_value, posting.units.currency)
                new_posting = data.Posting(destination_account, units, None,
                                           None, None, None)

                # Update the transaction with both postings
                txn = txn._replace(postings=[posting, new_posting])
            else:
                # Leave the transaction unbalanced if we can't determine the destination account
                pass
        else:
            # Regular income/expense transaction
            if amount_value < 0:
                # Expense transaction
                account = self._get_expense_account(row.category,
                                                    row.subcategory)
                # Make the amount positive for the expense posting
                units = data.Amount(-amount_value, posting.units.currency)
            else:
                # Income transaction
                account = self._get_income_account(row.category,
                                                   row.subcategory)
                # Keep the amount positive for the income posting
                units = data.Amount(amount_value, posting.units.currency)

            # Create a new posting for the expense/income account
            new_posting = data.Posting(account, units, None, None, None, None)

            # Update the transaction with both postings
            txn = txn._replace(postings=[posting, new_posting])

        # Set the flag based on the MoneyForward ME flag
        flag = '*' if row.flag == '1' else '!'
        txn = txn._replace(flag=flag)

        return txn

    def _get_expense_account(self, category: str, subcategory: str) -> str:
        """Get the expense account for the given category and subcategory.

        Args:
            category: The MoneyForward ME category.
            subcategory: The MoneyForward ME subcategory.

        Returns:
            The Beancount expense account.
        """
        # Try to find a match in the expense_accounts dictionary
        key = f"{category}:{subcategory}" if subcategory else category
        if key in self.expense_accounts:
            return self.expense_accounts[key]
        if category in self.expense_accounts:
            return self.expense_accounts[category]

        # Return the default expense account
        return self.default_expense_account

    def _get_income_account(self, category: str, subcategory: str) -> str:
        """Get the income account for the given category and subcategory.

        Args:
            category: The MoneyForward ME category.
            subcategory: The MoneyForward ME subcategory.

        Returns:
            The Beancount income account.
        """
        # Try to find a match in the income_accounts dictionary
        key = f"{category}:{subcategory}" if subcategory else category
        if key in self.income_accounts:
            return self.income_accounts[key]
        if category in self.income_accounts:
            return self.income_accounts[category]

        # Return the default income account
        return self.default_income_account

    def _guess_transfer_destination_account(self, category: str,
                                            subcategory: str, memo: str,
                                            notes: str) -> Optional[str]:
        """Guess the destination account for a transfer transaction.
        
        This method attempts to determine the destination account for a transfer
        transaction based on the category, subcategory, memo, and notes.
        
        Args:
            category: The MoneyForward ME category.
            subcategory: The MoneyForward ME subcategory.
            memo: The memo field from the transaction.
            notes: Additional notes from the transaction.
            
        Returns:
            The destination account name if it can be determined, None otherwise.
        """
        # Initial implementation returns None
        # This can be extended in the future to guess the destination account
        # based on patterns in the category, subcategory, memo, and notes
        return None
