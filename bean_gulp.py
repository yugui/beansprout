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
from beansprout.importer.importers.moneyforward import Importer as MoneyForwardImporter
from beansprout.importer.account_predictor import AccountPredictor
from beansprout.importer.merge import Processor, ImporterType
from beansprout.importer.processors.file_writer import FileWriter
from beansprout.importer.processors.model_trainer import ModelTrainer

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
