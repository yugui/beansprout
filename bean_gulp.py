#!/usr/bin/python3

import os
import click
import datetime
import glob
import beangulp
import sys
from beancount import loader
from beancount.parser import printer
from importers.moneyforward import Importer as MoneyForwardImporter
from importers.account_predictor import AccountPredictor
from importers.merge import Processor

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
    
    def process_output(self, entries_by_account_month, entries_by_dest_file):
        """Process the output for the extracted and deduplicated entries.
        
        This method writes entries to files in the destination directory,
        organized by account and year-month. It handles duplicate entries
        according to the following rules:
        1. Skip entries that are duplicates with entries in the destination file.
        2. Comment out entries that are duplicates with entries from other files.
        
        Args:
            entries_by_account_month: Dictionary mapping (account, year_month) tuples to lists of entries
            entries_by_dest_file: Dictionary mapping destination file paths to lists of existing entries
        """
        for (account, year_month), entries in sorted(entries_by_account_month.items()):
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
            
            for entry in entries:
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
                        processed_entries.append((duplicate_entry, True))  # (entry, should_comment)
                        commented_count += 1
                else:
                    # Regular entry
                    processed_entries.append((entry, False))  # (entry, should_comment)
                    regular_count += 1
            
            # Combine with existing entries from the destination file
            for entry in existing_entries_in_dest:
                processed_entries.append((entry, False))  # (entry, should_comment)
            
            # Sort all entries by date
            processed_entries.sort(key=lambda x: x[0].date, reverse=self.reverse)
            
            # Print information
            self.log(f"Writing entries ({regular_count} new, {commented_count} duplicates commented, {skipped_count} duplicates skipped) for {account} {year_month} to {dest_file}")
            
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
                    output.write(f"; Transactions for {account} {year_month}\n\n")
                    
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
    processor = FileWriter(
        importers=ctx.importers,
        destination=destination,
        reverse=reverse,
        failfast=failfast,
        quiet=quiet,
        dry_run=dry_run
    )
    
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
