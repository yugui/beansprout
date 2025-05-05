#!/usr/bin/python3

import os
import click
import datetime
import glob
import beangulp
from beancount import loader
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
    import sys
    from beancount.parser import printer

    # If the output directory is not specified, use the current working directory
    if destination is None:
        destination = os.getcwd()

    verbosity = -quiet
    log = beangulp.utils.logger(verbosity, err=True)
    errors = beangulp.exceptions.ExceptionsTrap(log)

    # Phase 1: Walk the source files and extract transactions
    extracted = []  # List of (filename, entries, account, importer) tuples
    year_months = set()  # Set of distinct year-months

    for filename in beangulp.utils.walk(src):
        with errors:
            log(f'* {filename:}', nl=False)
            if os.path.getsize(
                    filename) > beangulp.identify.FILE_TOO_LARGE_THRESHOLD:
                log(' ... SKIP')
                continue

            importer = beangulp.identify.identify(ctx.importers, filename)
            if not importer:
                log('')  # Newline.
                continue

            # Signal processing of this document.
            log(' ...', nl=False)

            # Get the account for this file
            account = importer.account(filename)

            # Extract entries from the file (without deduplication yet)
            entries = beangulp.extract.extract_from_file(
                importer, filename, [])

            if not entries:
                log(' (no entries)')
                continue

            # Collect year-months from entries
            for entry in entries:
                year_months.add(entry.date.strftime("%Y%m"))

            # Store the extracted entries
            extracted.append((filename, entries, account, importer))
            log(' OK', fg='green')

        if failfast and errors:
            break

    # If there are any errors, stop here
    if errors:
        log('# Errors detected: transactions will not be written.')
        sys.exit(1)

    # Phase 2: Sort the extracted entries
    beangulp.extract.sort_extracted_entries(extracted)

    # Phase 3: Read existing transactions for each year-month
    existing_entries_by_year_month = {}
    # Also track entries by destination file path for merging later
    entries_by_dest_file = {}

    for year_month in sorted(year_months):
        # Find all beancount files with matching year-month in the destination directory
        existing_entries = []

        for root, _, files in os.walk(destination):
            for file in files:
                if file.endswith(".beancount") and file.startswith(year_month):
                    existing_file = os.path.join(root, file)
                    try:
                        entries, _, _ = loader.load_file(existing_file)

                        # Store entries by file path for merging later
                        # We'll use these entries if the file path matches our destination file
                        entries_by_dest_file[existing_file] = entries

                        # Add to the collection of all existing entries for deduplication
                        existing_entries.extend(entries)
                        log(f"Loaded {len(entries)} existing entries from {existing_file}"
                            )
                    except Exception as e:
                        log(f'Warning: Could not load {existing_file}: {e}')

        existing_entries_by_year_month[year_month] = existing_entries

    # Phase 4: Deduplicate extracted entries against existing entries
    for filename, entries, account, importer in extracted:
        # Group entries by year-month
        entries_by_year_month = {}
        for entry in entries:
            year_month = entry.date.strftime("%Y%m")
            if year_month not in entries_by_year_month:
                entries_by_year_month[year_month] = []
            entries_by_year_month[year_month].append(entry)

        # Deduplicate entries for each year-month
        for year_month, month_entries in entries_by_year_month.items():
            existing = existing_entries_by_year_month.get(year_month, [])
            # Mark duplicate entries
            importer.deduplicate(month_entries, existing)

            # Remove entries that have been marked as duplicates
            # Entries are marked as duplicates by setting the '__duplicate__' metadata
            month_entries[:] = [
                entry for entry in month_entries
                if not (hasattr(entry, 'meta') and entry.meta is not None
                        and '__duplicate__' in entry.meta)
            ]

    # Phase 5 & 6: Group entries by account and year-month, then write to files
    # First, group all extracted entries by account and year-month
    entries_by_account_month = {}

    for filename, entries, account, importer in extracted:
        for entry in entries:
            # Skip entries that have been marked as duplicates
            if hasattr(
                    entry, 'meta'
            ) and entry.meta is not None and '__duplicate__' in entry.meta:
                continue

            year_month = entry.date.strftime("%Y%m")
            key = (account, year_month)
            if key not in entries_by_account_month:
                entries_by_account_month[key] = []
            entries_by_account_month[key].append(entry)

    # Now process each account and year-month combination
    for (account,
         year_month), new_entries in sorted(entries_by_account_month.items()):
        # Create the destination path
        account_path = account.replace(':', os.sep)
        dest_dir = os.path.join(destination, account_path)
        dest_file = os.path.join(dest_dir, f"{year_month}.beancount")

        # Check if the destination file already exists and has entries
        existing_entries_in_dest = entries_by_dest_file.get(dest_file, [])

        # Combine new entries with existing entries from the destination file
        combined_entries = existing_entries_in_dest + new_entries

        # Sort all entries
        combined_entries.sort(key=lambda e: e.date, reverse=reverse)

        # Print information
        log(f"Writing {len(combined_entries)} entries ({len(new_entries)} new) for {account} {year_month} to {dest_file}"
            )

        if dry_run:
            # In dry-run mode, print new transactions to stdout if not quiet
            if quiet <= 0 and new_entries:
                click.echo(
                    f"\nNew transactions that would be written to {dest_file}:"
                )
                for entry in new_entries:
                    string = printer.format_entry(entry)
                    click.echo(string)
        else:
            # Create directory if it doesn't exist
            os.makedirs(dest_dir, exist_ok=True)

            # Write entries to file
            with open(dest_file, 'w') as output:
                output.write(beangulp.extract.HEADER + '\n')
                output.write(f"; Transactions for {account} {year_month}\n\n")

                for entry in combined_entries:
                    string = printer.format_entry(entry)
                    output.write(string)
                    output.write('\n')


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
