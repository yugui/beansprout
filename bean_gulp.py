#!/usr/bin/python3

import os
import click
import datetime
import glob
import beangulp
import sys
from typing import Dict, List, Tuple
from beancount import loader
from beancount.parser import printer
from beancount.core.data import Directive, Entries
from importers.moneyforward import Importer as MoneyForwardImporter
from importers.account_predictor import AccountPredictor
from importers.merge import Processor, ImporterType

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


class FileWriter(Processor):
    """Concrete implementation of Processor that writes entries to files.
    
    This class implements the process_output method to write entries to files
    in the destination directory, organized by account and year-month.
    
    Attributes:
        dry_run: Whether to perform a dry run without writing files.
    """

    def __init__(self,
                 importers,
                 destination=None,
                 reverse=False,
                 failfast=False,
                 quiet=0,
                 dry_run=False):
        """Initialize the FileWriter.
        
        Args:
            importers: List of importers to use for extracting transactions.
            destination: The destination directory for extracted transactions.
            reverse: Whether to sort entries in reverse order.
            failfast: Whether to stop processing at the first error.
            quiet: Level of output suppression (0 for normal output, higher for less output).
            dry_run: Whether to perform a dry run without writing files.
        """
        super().__init__(importers, destination, reverse, failfast, quiet)
        self.dry_run = dry_run

    def is_duplicate(self, entry):
        """Check if an entry is marked as a duplicate.
        
        Args:
            entry: The entry to check.
            
        Returns:
            True if the entry is marked as a duplicate, False otherwise.
        """
        return (hasattr(entry, 'meta') and entry.meta is not None
                and '__duplicate__' in entry.meta)

    def process_output(self, entries_by_account_month: Dict[Tuple[
        str, str], List[Tuple[Directive, ImporterType]]],
                       entries_by_dest_file: Dict[str, Entries]) -> None:
        """Process the output for the extracted and deduplicated entries.
        
        This method writes entries to files in the destination directory,
        organized by account and year-month. It handles duplicate entries
        according to the following rules:
        1. Skip entries that are duplicates with entries in the destination file.
        2. Comment out entries that are duplicates with entries from other files.
        
        Args:
            entries_by_account_month: Dictionary mapping (account, year_month) tuples to 
                                     lists of (entry, importer) tuples
            entries_by_dest_file: Dictionary mapping destination file paths to lists of existing entries
        """
        for (account, year_month), entry_importer_pairs in sorted(
                entries_by_account_month.items()):
            # Create the destination path
            account_path = account.replace(':', os.sep)
            dest_dir = os.path.join(self.destination, account_path)
            dest_file = os.path.join(dest_dir, f"{year_month}.beancount")

            # Check if the destination file already exists and has entries
            existing_entries_in_dest = entries_by_dest_file.get(dest_file, [])

            # Process entries - filter out duplicates with existing_entries_in_dest
            # and mark other duplicates for commenting
            processed_entries = []
            regular_count = 0
            commented_count = 0
            skipped_count = 0

            for entry, importer in entry_importer_pairs:
                if self.is_duplicate(entry):
                    # Get the duplicate entry that this entry duplicates
                    duplicate_entry = entry.meta['__duplicate__']

                    # Check if the duplicate entry is in existing_entries_in_dest
                    is_duplicate_with_dest = duplicate_entry in existing_entries_in_dest

                    if is_duplicate_with_dest:
                        # Skip this entry as it's a duplicate with an entry in the destination file
                        skipped_count += 1
                        continue
                    else:
                        # Mark the duplicate entry for commenting out
                        processed_entries.append(
                            (duplicate_entry, True))  # (entry, should_comment)
                        commented_count += 1
                else:
                    # Regular entry
                    processed_entries.append(
                        (entry, False))  # (entry, should_comment)
                    regular_count += 1

            # Combine with existing entries from the destination file
            for entry in existing_entries_in_dest:
                processed_entries.append(
                    (entry, False))  # (entry, should_comment)

            # Sort all entries by date
            processed_entries.sort(key=lambda x: x[0].date,
                                   reverse=self.reverse)

            # Print information
            self.log(
                f"Writing entries ({regular_count} new, {commented_count} duplicates commented, {skipped_count} duplicates skipped) for {account} {year_month} to {dest_file}"
            )

            if self.dry_run:
                # In dry-run mode, print new transactions to stdout if not quiet
                if self.quiet <= 0 and regular_count > 0:
                    click.echo(
                        f"\nNew transactions that would be written to {dest_file}:"
                    )
                    for entry, should_comment in processed_entries:
                        if not should_comment and entry not in existing_entries_in_dest:
                            string = printer.format_entry(entry)
                            click.echo(string)
            else:
                # Create directory if it doesn't exist
                os.makedirs(dest_dir, exist_ok=True)

                # Write entries to file
                with open(dest_file, 'w') as output:
                    output.write(beangulp.extract.HEADER + '\n')
                    output.write(
                        f"; Transactions for {account} {year_month}\n\n")

                    for entry, should_comment in processed_entries:
                        string = printer.format_entry(entry)
                        if should_comment:
                            # Comment out each line of the entry
                            string = '; ' + string.replace('\n', '\n; ')
                        output.write(string)
                        output.write('\n')


@click.command('merge')
@click.argument('src',
                nargs=-1,
                type=click.Path(exists=True, resolve_path=True))
@click.option('--destination',
              '-o',
              metavar='DIR',
              type=click.Path(exists=True, file_okay=False, resolve_path=True),
              help='The destination directory for extracted transactions.')
@click.option('--reverse',
              '-r',
              is_flag=True,
              help='Sort entries in reverse order.')
@click.option('--failfast',
              '-x',
              is_flag=True,
              help='Stop processing at the first error.')
@click.option('--quiet', '-q', count=True, help='Suppress all output.')
@click.option(
    '--dry-run',
    '-n',
    is_flag=True,
    help=
    'Just print where the files would be written, without actually writing them.'
)
@click.pass_obj
def _merge(ctx, src, destination, reverse, failfast, quiet, dry_run):
    """Extract transactions from documents and merge them with existing monthly files.
    
    Walk the SRC list of files or directories and extract the ledger
    entries from each file identified by one of the configured
    importers. The entries are grouped by year and month and merged with
    existing entries in files named after the calendar year and month in the 
    archival subdirectory specified by the importer within the destination directory.
    
    Existing transactions are read from all beancount files under the destination
    directory whose base name matches the year-month of the extracted transactions.
    """
    # Create a FileWriter instance
    processor = FileWriter(importers=ctx.importers,
                           destination=destination,
                           reverse=reverse,
                           failfast=failfast,
                           quiet=quiet,
                           dry_run=dry_run)

    # Process the source files
    status = processor.process(src)

    # Exit with the appropriate status code
    if status != 0:
        sys.exit(status)


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
        self.training_count = 0

    def is_duplicate(self, entry):
        """Check if an entry is marked as a duplicate.
        
        Args:
            entry: The entry to check.
            
        Returns:
            True if the entry is marked as a duplicate, False otherwise.
        """
        return (hasattr(entry, 'meta') and entry.meta is not None
                and '__duplicate__' in entry.meta)

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

        # Process all extracted entries
        for (account, year_month), entry_importer_pairs in sorted(
                entries_by_account_month.items()):
            for entry, importer in entry_importer_pairs:
                total_entries += 1

                # Skip non-duplicate entries
                if not self.is_duplicate(entry):
                    continue

                duplicate_entries += 1
                duplicate_entry = entry.meta['__duplicate__']

                # Skip entries without postings
                if not hasattr(entry, 'postings') or not hasattr(
                        duplicate_entry, 'postings'):
                    continue

                # For each posting in the extracted entry
                for posting in entry.postings:
                    # Skip the posting if it's for the wallet account (belonging account)
                    if posting.account == account:
                        continue

                    # Find the corresponding posting in the duplicate entry
                    self._process_posting(account, entry, posting,
                                          duplicate_entry)

        # Save the updated model if not in dry-run mode and we have training examples
        if not self.dry_run and self.training_count > 0:
            self.account_predictor.save(self.account_predictor_path)
            self.log(
                f"Updated account predictor model with {self.training_count} examples and saved to {self.account_predictor_path}"
            )

        # Print summary
        self.log(
            f"Processed {total_entries} entries, found {duplicate_entries} duplicates, "
            +
            f"detected {mismatch_entries} prediction mismatches, trained on {self.training_count} examples"
        )

    def _process_posting(self, account, entry, posting, duplicate_entry):
        """Process a posting to detect prediction failures and update the model.
        
        Args:
            account: The account the transaction belongs to.
            entry: The extracted entry.
            posting: The posting to process.
            duplicate_entry: The duplicate entry from existing transactions.
        """
        # Find the corresponding posting in the duplicate entry
        for dup_posting in duplicate_entry.postings:
            # Skip if not matching by amount and currency
            if (dup_posting.units.number != posting.units.number
                    or dup_posting.units.currency != posting.units.currency
                    or dup_posting.account == account):
                continue

            # Skip if the predicted account matches the actual account
            if posting.account == dup_posting.account:
                return

            # Get transaction narration and posting narration
            transaction_narration = entry.narration if hasattr(
                entry, 'narration') else ""
            posting_narration = posting.meta.get('narration', '') if hasattr(
                posting, 'meta') and posting.meta else ""

            # Update the model with the correct account
            if not self.dry_run:
                self.account_predictor.update(
                    belonging_account=account,
                    transaction_narration=transaction_narration,
                    posting_narration=posting_narration,
                    correct_account=dup_posting.account)
                self.training_count += 1

            self.log(
                f"Training on mismatch: {transaction_narration} - " +
                f"Predicted: {posting.account}, Actual: {dup_posting.account}")
            return


@click.command('train')
@click.argument('src',
                nargs=-1,
                type=click.Path(exists=True, resolve_path=True))
@click.option(
    '--destination',
    '-o',
    metavar='DIR',
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    help='The destination directory containing existing transactions.')
@click.option('--reverse',
              '-r',
              is_flag=True,
              help='Sort entries in reverse order.')
@click.option('--failfast',
              '-x',
              is_flag=True,
              help='Stop processing at the first error.')
@click.option('--quiet', '-q', count=True, help='Suppress all output.')
@click.option(
    '--dry-run',
    '-n',
    is_flag=True,
    help='Just analyze prediction failures without updating the model.')
@click.option(
    '--model-path',
    '-m',
    metavar='FILE',
    type=click.Path(resolve_path=True),
    help=
    'Path to the account predictor model file. Defaults to the environment variable BEANGULP_ACCOUNT_PREDICTOR_PATH or ~/.cache/beangulp/account-prediction.pickle.'
)
@click.pass_obj
def _train(ctx, src, destination, reverse, failfast, quiet, dry_run,
           model_path):
    """Train the account predictor model based on prediction failures.
    
    Walk the SRC list of files or directories and extract the ledger
    entries from each file identified by one of the configured
    importers. Compare the extracted transactions with existing duplicate
    transactions to detect prediction failures. Update the account predictor
    model using the correct accounts from the existing transactions.
    
    This command is useful for improving the accuracy of account predictions
    by learning from existing manually corrected transactions.
    """
    # Determine the model path
    if not model_path:
        model_path = os.environ.get(
            "BEANGULP_ACCOUNT_PREDICTOR_PATH",
            os.path.expanduser("~/.cache/beangulp/account-prediction.pickle"))

    # Load the account predictor model
    try:
        account_predictor = AccountPredictor.load(model_path)
        if not quiet:
            click.echo(f"Loaded account predictor from {model_path}")
    except FileNotFoundError:
        if not quiet:
            click.echo(
                f"Account predictor file not found at {model_path}, creating a new one"
            )
        account_predictor = AccountPredictor(min_confidence=0.6)

    # Create a ModelTrainer instance
    processor = ModelTrainer(importers=ctx.importers,
                             account_predictor=account_predictor,
                             account_predictor_path=model_path,
                             destination=destination,
                             reverse=reverse,
                             failfast=failfast,
                             quiet=quiet,
                             dry_run=dry_run)

    # Process the source files
    status = processor.process(src)

    # Exit with the appropriate status code
    if status != 0:
        sys.exit(status)


class ExtendedIngest(beangulp.Ingest):
    """Extended version of beangulp.Ingest with additional subcommands."""

    def __init__(self, importers, hooks=None):
        """Initialize the ExtendedIngest class.
        
        Args:
            importers: List of importers to use.
            hooks: Optional list of hooks to run after extraction.
        """
        # Initialize the parent class
        super().__init__(importers, hooks)

        # Add the merge command
        self.cli.add_command(_merge)

        # Add the train command
        self.cli.add_command(_train)


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

    # Define a function to create a MoneyForward importer
    def create_mf_importer(wallet_account: str,
                           expected_institution: str) -> MoneyForwardImporter:
        """Create a MoneyForward ME importer with the specified parameters.
        
        Args:
            wallet_account: The Beancount account for the wallet.
            expected_institution: The expected financial institution name in MoneyForward ME.
            
        Returns:
            A configured MoneyForwardImporter instance.
        """
        return MoneyForwardImporter(
            wallet_account=wallet_account,
            expected_institution=expected_institution,
            account_predictor=account_predictor,
            expense_accounts=expense_accounts,
            income_accounts=income_accounts,
            currency="JPY",
        )

    # Define importers
    importers = [
        # MoneyForward ME importer
        # Configure with your wallet account and mappings loaded from TSV files
        create_mf_importer(
            wallet_account="Assets:Cash:Wallet",
            expected_institution="財布",
        ),
    ]

    # Define hooks for post-processing
    hooks = []

    # Create and run the ingest command using our extended version
    ingest = ExtendedIngest(importers, hooks)
    ingest()


if __name__ == "__main__":
    main()
