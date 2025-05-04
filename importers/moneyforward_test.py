"""Unit tests for the MoneyForward ME importer."""

import datetime
import io
import os
import tempfile
import unittest
from unittest import mock

from beancount.core import data
from beancount.parser import cmptest

from importers import moneyforward
from importers.account_predictor import AccountPredictor


class TestMoneyForwardImporter(cmptest.TestCase):
    """Unit tests for the MoneyForward ME importer."""

    def setUp(self):
        """Set up the test case."""
        # Create a sample CSV file with MoneyForward ME data
        self.temp_dir = tempfile.TemporaryDirectory()
        self.csv_filename = os.path.join(self.temp_dir.name,
                                         "wallet-202501.csv")

        # Sample data in Shift_JIS encoding
        csv_content = (
            '"計算対象","日付","内容","金額（円）","保有金融機関","大項目","中項目","メモ","振替","ID"\n'
            '"1","2025/01/15","東京スーパー","-2500","財布","食費","食料品","週末の買い物","0","abcdef123456"\n'
            '"1","2025/01/20","渋谷カフェ","-800","財布","食費","昼ご飯","同僚とランチ","0","abcdef789012"\n'
            '"1","2025/01/25","クリニック","-1200","財布","健康・医療","医療費","定期検診","0","ghijkl123456"\n'
            '"0","2025/01/30","給料","250000","財布","収入","給与","1月分","1","mnopqr123456"\n'
        ).encode('shift_jis')

        with open(self.csv_filename, 'wb') as f:
            f.write(csv_content)

        # Create an account predictor
        self.account_predictor = AccountPredictor(min_confidence=0.6, )

        # Create an importer instance
        self.importer = moneyforward.Importer(
            wallet_account="Assets:Cash:Wallet",
            expected_institution="財布",
            account_predictor=self.account_predictor,
            expense_accounts={
                "食費": "Expenses:Food",
                "食費:昼ご飯": "Expenses:Food:Lunch",
                "食費:食料品": "Expenses:Food:Groceries",
                "健康・医療": "Expenses:Health",
                "健康・医療:医療費": "Expenses:Health:Medical",
            },
            income_accounts={
                "収入": "Income:Other",
                "収入:給与": "Income:Salary",
            },
            currency="JPY",
        )

    def tearDown(self):
        """Clean up after the test case."""
        self.temp_dir.cleanup()

    def test_identify(self):
        """Test the identify method."""
        self.assertTrue(self.importer.identify(self.csv_filename))

        # Test with a non-matching filename
        with tempfile.NamedTemporaryFile(suffix='.txt') as f:
            self.assertFalse(self.importer.identify(f.name))

    def test_extract(self):
        """Test the extract method."""
        # The extract method requires an existing entries list
        existing_entries = []
        entries = self.importer.extract(self.csv_filename, existing_entries)

        self.assertEqual(4, len(entries))

        # Check each entry individually
        # First entry (expense)
        entry1 = entries[0]
        self.assertEqual(datetime.date(2025, 1, 15), entry1.date)
        self.assertEqual('*', entry1.flag)
        self.assertEqual('東京スーパー', entry1.payee)
        self.assertEqual('週末の買い物', entry1.narration)
        self.assertEqual('食費', entry1.meta['category'])
        self.assertEqual('食料品', entry1.meta['subcategory'])
        self.assertEqual('週末の買い物', entry1.meta['memo'])
        self.assertEqual('abcdef123456', entry1.meta['id'])
        self.assertEqual(2, len(entry1.postings))
        self.assertEqual('Assets:Cash:Wallet', entry1.postings[0].account)
        self.assertEqual(-2500, entry1.postings[0].units.number)
        self.assertEqual('JPY', entry1.postings[0].units.currency)
        self.assertEqual('Expenses:Food:Groceries', entry1.postings[1].account)
        self.assertEqual(2500, entry1.postings[1].units.number)
        self.assertEqual('JPY', entry1.postings[1].units.currency)

        # Second entry (expense)
        entry2 = entries[1]
        self.assertEqual(datetime.date(2025, 1, 20), entry2.date)
        self.assertEqual('*', entry2.flag)
        self.assertEqual('渋谷カフェ', entry2.payee)
        self.assertEqual('同僚とランチ', entry2.narration)
        self.assertEqual('食費', entry2.meta['category'])
        self.assertEqual('昼ご飯', entry2.meta['subcategory'])
        self.assertEqual('同僚とランチ', entry2.meta['memo'])
        self.assertEqual('abcdef789012', entry2.meta['id'])
        self.assertEqual(2, len(entry2.postings))
        self.assertEqual('Assets:Cash:Wallet', entry2.postings[0].account)
        self.assertEqual(-800, entry2.postings[0].units.number)
        self.assertEqual('JPY', entry2.postings[0].units.currency)
        self.assertEqual('Expenses:Food:Lunch', entry2.postings[1].account)
        self.assertEqual(800, entry2.postings[1].units.number)
        self.assertEqual('JPY', entry2.postings[1].units.currency)

        # Third entry (expense)
        entry3 = entries[2]
        self.assertEqual(datetime.date(2025, 1, 25), entry3.date)
        self.assertEqual('*', entry3.flag)
        self.assertEqual('クリニック', entry3.payee)
        self.assertEqual('定期検診', entry3.narration)
        self.assertEqual('健康・医療', entry3.meta['category'])
        self.assertEqual('医療費', entry3.meta['subcategory'])
        self.assertEqual('定期検診', entry3.meta['memo'])
        self.assertEqual('ghijkl123456', entry3.meta['id'])
        self.assertEqual(2, len(entry3.postings))
        self.assertEqual('Assets:Cash:Wallet', entry3.postings[0].account)
        self.assertEqual(-1200, entry3.postings[0].units.number)
        self.assertEqual('JPY', entry3.postings[0].units.currency)
        self.assertEqual('Expenses:Health:Medical', entry3.postings[1].account)
        self.assertEqual(1200, entry3.postings[1].units.number)
        self.assertEqual('JPY', entry3.postings[1].units.currency)

        # Fourth entry (income/transfer)
        entry4 = entries[3]
        self.assertEqual(datetime.date(2025, 1, 30), entry4.date)
        self.assertEqual('!', entry4.flag)
        self.assertEqual('給料', entry4.payee)
        self.assertEqual('1月分', entry4.narration)
        self.assertEqual('収入', entry4.meta['category'])
        self.assertEqual('給与', entry4.meta['subcategory'])
        self.assertEqual('1月分', entry4.meta['memo'])
        self.assertEqual('mnopqr123456', entry4.meta['id'])
        # Only one posting for transfer transactions
        self.assertEqual(1, len(entry4.postings))
        self.assertEqual('Assets:Cash:Wallet', entry4.postings[0].account)
        self.assertEqual(250000, entry4.postings[0].units.number)
        self.assertEqual('JPY', entry4.postings[0].units.currency)

    def test_file_date(self):
        """Test the file_date method."""
        date = self.importer.file_date(self.csv_filename)

        self.assertEqual(datetime.date(2025, 1, 1), date)


if __name__ == '__main__':
    unittest.main()
