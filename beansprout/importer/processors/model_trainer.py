"""Model trainer processor for training the account predictor model.

This module provides the ModelTrainer processor that detects prediction failures
by comparing extracted transactions with their duplicate existing transactions
and updates the account predictor model.
"""

import os
import click
from typing import Dict, List, Tuple

from beancount.core.data import Directive, Entries

from beansprout.importer.merge import ImporterType
from beansprout.importer.processors.base import Processor


class ModelTrainer(Processor):
    """Concrete implementation of Processor that trains the account predictor model.

    This class implements the process_output method to detect prediction failures
    and update the account predictor model based on the correct accounts found
    in existing duplicate transactions.

    Attributes:
        account_predictor: The account predictor model to train.
        account_predictor_path: The path to save the updated model.
        dry_run: Whether to perform a dry run without updating the model.
    """

    def __init__(self,
                 importers,
                 account_predictor,
                 account_predictor_path,
                 destination=None,
                 reverse=False,
                 failfast=False,
                 quiet=0,
                 dry_run=False):
        """Initialize the ModelTrainer.

        Args:
            importers: List of importers to use for extracting transactions.
            account_predictor: The account predictor model to train.
            account_predictor_path: The path to save the updated model.
            destination: The destination directory for extracted transactions.
            reverse: Whether to sort entries in reverse order.
            failfast: Whether to stop processing at the first error.
            quiet: Level of output suppression (0 for normal output, higher for less output).
            dry_run: Whether to perform a dry run without updating the model.
        """
        super().__init__(importers, destination, reverse, failfast, quiet)
        self.account_predictor = account_predictor
        self.account_predictor_path = account_predictor_path
        self.dry_run = dry_run

    def get_duplicate(self, entry):
        """Get the duplicate entry if it exists.

        Args:
            entry: The entry to check for duplicates.

        Returns:
            The duplicate entry if found, None otherwise.
        """
        if hasattr(
                entry, 'meta'
        ) and entry.meta is not None and '__duplicate__' in entry.meta:
            return entry.meta['__duplicate__']
        return None

    def process_output(self, entries_by_account_month: Dict[Tuple[
        str, str], List[Tuple[Directive, ImporterType]]],
                       entries_by_dest_file: Dict[str, Entries]) -> None:
        """Process the output for the extracted entries and train the model.

        This method detects prediction failures by comparing extracted transactions
        with their duplicate existing transactions. It then updates the prediction
        model using the account in the existing duplicate transactions for
        mismatching cases.

        Args:
            entries_by_account_month: Dictionary mapping (account, year_month) tuples to 
                                     lists of (entry, importer) tuples
            entries_by_dest_file: Dictionary mapping destination file paths to lists of existing entries
        """
        total_entries = 0
        duplicate_entries = 0
        mismatch_entries = 0
        training_count = 0

        # Process all extracted entries
        for (account, year_month), entry_importer_pairs in sorted(
                entries_by_account_month.items()):
            # Get the destination file path using the helper method
            dest_file = self.get_account_file_path(account, year_month)
            existing_entries_in_dest = entries_by_dest_file.get(dest_file, [])

            for entry, importer in entry_importer_pairs:
                total_entries += 1

                duplicate_entry = self.get_duplicate(entry)
                if not duplicate_entry:
                    continue
                duplicate_entries += 1

                # Skip entries without postings
                if not hasattr(entry, 'postings') or not hasattr(
                        duplicate_entry, 'postings'):
                    continue

                (is_mismatch, trained) = self._process_duplicate_pair(
                    account, entry, duplicate_entry, importer)
                if is_mismatch:
                    mismatch_entries += 1
                if trained:
                    training_count += 1

        # Save the updated model if not in dry-run mode and we have training examples
        if not self.dry_run and training_count > 0:
            self.account_predictor.save(self.account_predictor_path)
            self.log(
                f"Updated account predictor model with {training_count} examples and saved to {self.account_predictor_path}"
            )

        # Print summary
        self.log(
            f"Processed {total_entries} entries, found {duplicate_entries} duplicates, "
            +
            f"detected {mismatch_entries} prediction mismatches, trained on {training_count} examples"
        )

    def _process_duplicate_pair(self, account, entry, duplicate_entry,
                                importer) -> Tuple[bool, bool]:
        """Process a posting to detect prediction failures and update the model.

        Args:
            account: The account the transaction belongs to.
            entry: The extracted entry.
            duplicate_entry: The duplicate entry from existing transactions.
            importer: The importer that created the entry.
            
        Returns:
            A tuple (is_mismatch, trained) indicating whether a mismatch was detected
            and whether the model was trained on this example.
        """

        def _get_posting(entry, account):
            if len(entry.postings) != 2:
                return None
            for posting in entry.postings:
                if posting.account != account:
                    return posting
            return None

        posting = _get_posting(entry, account)
        duplicate_posting = _get_posting(duplicate_entry, account)
        if not duplicate_posting:
            return (False, False)
        if posting and posting.account == duplicate_posting.account:
            return (False, False)

        # Get transaction narration, posting narration, and hint
        transaction_narration = ""
        posting_narration = ""
        hint = []

        # Check if the importer is a MoneyForwardImporter and has the extract_prediction_data method
        if hasattr(importer, 'extract_prediction_data'):
            # Use the extract_prediction_data method to get the data
            transaction_narration, posting_narration, hint = importer.extract_prediction_data(
                entry)
        else:
            # Fallback to the old way of extracting data
            transaction_narration = entry.narration if hasattr(
                entry, 'narration') else ""
            posting_narration = posting.meta.get('narration', '') if hasattr(
                posting, 'meta') and posting.meta else ""

        self.log(
            f"Training on mismatch: {transaction_narration} - " +
            f"Predicted: {posting.account if posting else None}, Actual: {duplicate_posting.account}"
        )

        # Update the model with the correct account
        if self.dry_run:
            return (True, False)

        self.account_predictor.update(
            belonging_account=account,
            transaction_narration=transaction_narration,
            posting_narration=posting_narration,
            hint=hint,
            correct_account=duplicate_posting.account)
        return (True, True)
