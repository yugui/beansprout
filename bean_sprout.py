#!/usr/bin/python3
"""Command-line tool for managing Beancount ledgers with Beansprout.

This module provides the bean-sprout command with subcommands for importing,
merging, training on transaction data, and fetching price quotes for commodities,
all using the Beansprout directory structure conventions.
"""

import os
import click
import datetime
import glob
import beangulp
import sys
import logging
from typing import Dict, List, Optional, Tuple

from beancount import loader
from beancount.parser import printer
from beancount.core.data import Directive, Entries, Commodity, Price
from beancount.core import data
from beanprice import source

from beansprout.importer.importers.moneyforward import Importer as MoneyForwardImporter
from beansprout.importer.account_predictor import AccountPredictor
from beansprout.importer.merge import Processor, ImporterType
from beansprout.importer.processors.file_writer import FileWriter
from beansprout.importer.processors.model_trainer import ModelTrainer

# Import the quote-related modules
from beansprout.quoter.commodity_finder import CommodityFinder
from beansprout.quoter.quote_fetcher import QuoteFetcher
from beansprout.quoter.quote_writer import QuoteWriter
from beansprout.quoter.sources import cache_manager

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
@click.option('--ledger-directory',
              '-d',
              metavar='DIR',
              type=click.Path(exists=True, file_okay=False, resolve_path=True),
              help='The ledger directory containing existing transactions.')
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
    'Path to the account predictor model file. Defaults to the environment variable BEANSPROUT_ACCOUNT_PREDICTOR_PATH or ~/.cache/beansprout/account-prediction.pickle.'
)
@click.pass_obj
def _train(ctx, src, ledger_directory, reverse, failfast, quiet, dry_run,
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
            "BEANSPROUT_ACCOUNT_PREDICTOR_PATH",
            os.path.expanduser("~/.cache/beansprout/account-prediction.pickle"))

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
                             ledger_directory=ledger_directory,
                             reverse=reverse,
                             failfast=failfast,
                             quiet=quiet,
                             dry_run=dry_run)

    # Process the source files
    status = processor.process(src)

    # Exit with the appropriate status code
    if status != 0:
        sys.exit(status)


@click.command('quote')
@click.argument('filenames',
                nargs=-1,
                type=click.Path(exists=True, resolve_path=True),
                required=True)
@click.option('--date',
              '-d',
              type=click.DateTime(formats=["%Y-%m-%d"]),
              help='Fetch prices for this specific date.')
@click.option('--inactive',
              '-i',
              is_flag=True,
              help='Include inactive commodities.')
@click.option(
    '--custom-only',
    '-c',
    is_flag=True,
    help='Use only custom quoters from beansprout.quoter.sources package.')
@click.option('--verbose',
              '-v',
              count=True,
              help='Print verbose information about the process.')
@click.option('--dry-run',
              '-n',
              is_flag=True,
              help='Print extracted price entries without writing them.')
@click.option(
    '--destination',
    '-o',
    type=click.Path(file_okay=False, resolve_path=True),
    default=os.getcwd(),
    help='Base directory for output files (default: current directory).')
@click.option('--no-cache',
              is_flag=True,
              help='Disable caching of price quotes.')
@click.option(
    '--cache-file',
    type=click.Path(dir_okay=False, resolve_path=True),
    help=
    'Path to the cache file (default: ~/.cache/beansprout/quote-cache.dbm).')
def _quote(filenames: List[str], date: Optional[datetime.datetime],
           inactive: bool, custom_only: bool, verbose: int, dry_run: bool,
           destination: str, no_cache: bool,
           cache_file: Optional[str]) -> None:
    """Fetch price quotes for commodities using custom quoters.
    
    This command fetches price quotes for commodities defined in the given
    beancount files using custom quoters from the beansprout.quoter.sources package
    and optionally built-in quoters from beanprice.
    
    The command outputs price directives to files named:
    $destination/quotes/$symbol/YYYYmm.beancount
    where $symbol is the commodity symbol and YYYYmm is the year and month.
    
    Price quotes are cached by default to reduce network calls and improve performance.
    The cache is stored at ~/.cache/beansprout/quote-cache.dbm, and entries expire
    after 24 hours. You can disable caching with --no-cache or specify a custom
    cache file location with --cache-file.
    
    FILENAMES are one or more beancount files containing commodity definitions.
    """
    # Set up logging
    logging_level = logging.WARNING
    if verbose == 1:
        logging_level = logging.INFO
    elif verbose >= 2:
        logging_level = logging.DEBUG
    logging.basicConfig(level=logging_level,
                        format='%(levelname)s: %(message)s')

    # Set up the commodity finder
    finder = CommodityFinder()

    # Load all entries from all input files
    all_entries: List[Directive] = []
    all_errors: List[str] = []

    logging.info(f"Loading entries from {len(filenames)} file(s)")

    for filename in filenames:
        logging.debug(f"  Loading file: {filename}")

        entries, errors, options_map = loader.load_file(filename=filename)
        all_entries.extend(entries)
        all_errors.extend(errors)

    # Report any errors
    if all_errors:
        for error in all_errors:
            print(error, file=sys.stderr)
        if len(all_errors) > 10:
            print(f"Found {len(all_errors)} errors in total", file=sys.stderr)

    # Find all commodities
    all_commodities = finder.find_all_commodities(entries=all_entries)
    logging.info(f"Found {len(all_commodities)} commodities")

    # Filter active commodities
    if not inactive:
        active_commodities = finder.filter_active_commodities(
            commodities=all_commodities)
        logging.info(
            f"Filtered to {len(active_commodities)} active commodities")
    else:
        active_commodities = all_commodities
        logging.info("Including all commodities (--inactive flag set)")

    # Find the price date to use
    price_date = date.date() if date else datetime.date.today()
    logging.info(f"Using price date: {price_date}")

    # Set up cache manager based on options
    def open_cache():
        if no_cache:
            logging.info("Cache disabled (--no-cache)")
            return cache_manager.NullCacheManager()
        else:
            cache = cache_manager.DBMCacheManager(cache_file_path=cache_file)
            logging.info(f"Using cache file: {cache.cache_file_path}")
            return cache

    with open_cache() as cache:
        fetcher = QuoteFetcher(custom_only=custom_only, cache_mgr=cache)

        # Fetch quotes for each active commodity
        price_entries = []
        for commodity in active_commodities:
            logging.debug(f"Fetching quote for {commodity.currency}")

            price_entry = fetcher.fetch_quote(commodity=commodity,
                                              quote_date=price_date)

            if price_entry:
                price_entries.append(price_entry)
                logging.debug(
                    f"  Got price: {price_entry.amount} {price_entry.currency}"
                )
            else:
                logging.warning(f"  No price found for {commodity.currency}")

    logging.info(f"Fetched {len(price_entries)} price entries")

    # Create quote writer for destination file management
    writer = QuoteWriter(destination_base=destination)

    # Write price entries to destination files or print them in dry run mode
    if dry_run:
        click.echo("Dry run - printing price entries:")
        for price in price_entries:
            click.echo(printer.format_entry(price).rstrip())
    else:
        written_files = writer.write_prices(price_entries)

        if verbose:
            total_files = sum(len(files) for files in written_files.values())
            click.echo(
                f"Wrote price entries for {len(written_files)} commodities "
                f"to {total_files} files in {writer.quotes_dir}")

    click.echo("Done.")


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

        # Add the quote command
        self.cli.add_command(_quote)


def main():
    # Load account mappings from TSV files
    expense_accounts = load_account_mappings(EXPENSE_ACCOUNTS_FILE)
    income_accounts = load_account_mappings(INCOME_ACCOUNTS_FILE)

    # Load account predictor from pickle file
    # Check if the path is provided in an environment variable
    account_predictor_path = os.environ.get(
        "BEANSPROUT_ACCOUNT_PREDICTOR_PATH",
        os.path.expanduser("~/.cache/beansprout/account-prediction.pickle"))
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
