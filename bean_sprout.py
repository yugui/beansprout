#!/usr/bin/python3
"""Command-line tool for managing Beancount ledgers with Beansprout.

This module provides the bean-sprout command with subcommands for importing,
merging, and fetching price quotes for commodities, all using the Beansprout
directory structure conventions.
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

from beansprout.config import load_config, Config
from beansprout.importer.types import ImporterType
from beansprout.command.merge import Merge
from beansprout.quoter.commodity_finder import CommodityFinder
from beansprout.quoter.quote_fetcher import QuoteFetcher
from beansprout.quoter.quote_writer import QuoteWriter
from beansprout.quoter.sources import cache_manager


def complete_existing_file(config: Config,
                           existing_file: Optional[str],
                           destination: Optional[str] = None) -> str:
    """Complete the existing file path with a default if not provided.
    
    Args:
        config: The configuration object containing primary file information.
        existing_file: The existing file path, if provided.
        destination: The destination directory, used to construct the default path.
        
    Returns:
        The completed file path, either the provided path or a default.
    """
    if existing_file:
        return existing_file
    if config.primary_file:
        return config.primary_file
    return os.path.join(complete_destination(destination), "ledger.beancount")


def complete_destination(destination: Optional[str]) -> str:
    """Complete the destination directory path with a default if not provided.
    
    Args:
        destination: The destination directory path, if provided.
        
    Returns:
        The completed directory path, either the provided path or a default.
    """
    if destination:
        return destination
    return os.getcwd()


@click.command('merge')
@click.argument('src',
                nargs=-1,
                type=click.Path(exists=True, resolve_path=True))
@click.option('--destination',
              '-o',
              metavar='DIR',
              default=os.getcwd(),
              type=click.Path(exists=True, file_okay=False, resolve_path=True),
              help='The destination directory for extracted transactions.')
@click.option(
    '--existing-file',
    '-e',
    metavar='FILE',
    type=click.Path(exists=True, dir_okay=False, resolve_path=True),
    help=
    'Path to a Beancount file with existing entries for training. Defaults to "ledger.beancount" in the current directory if it exists.'
)
@click.option('--reverse',
              '-r',
              is_flag=True,
              help='Sort entries in reverse order.')
@click.option('--failfast',
              '-x',
              is_flag=True,
              help='Stop processing at the first error.')
@click.option('--quiet', '-q', count=True, help='Suppress all output.')
@click.option('--verbose', '-v', count=True, help='Print verbose information.')
@click.option(
    '--dry-run',
    '-n',
    is_flag=True,
    help=
    'Just print where the files would be written, without actually writing them.'
)
@click.pass_obj
def _merge(ctx, src, destination, existing_file, reverse, failfast, verbose,
           quiet, dry_run):
    """Extract transactions from documents and merge them with existing monthly files.

    Walk the SRC list of files or directories and extract the ledger
    entries from each file identified by one of the configured
    importers. The entries are grouped by year and month and merged with
    existing entries in files named after the calendar year and month in the 
    archival subdirectory specified by the importer within the destination directory.

    Existing transactions are read from all beancount files under the destination
    directory whose base name matches the year-month of the extracted transactions.
    
    If --existing-file is specified, entries from this file will be used for training
    the smart_importer account predictor. This defaults to "ledger.beancount" in the
    current directory if it exists.
    """

    # Set up logging
    logging_level = logging.WARNING
    if verbose == 1:
        logging_level = logging.INFO
    elif verbose >= 2:
        logging_level = logging.DEBUG
    elif quiet > 0:
        logging_level = logging.ERROR
    logging.basicConfig(level=logging_level,
                        format='%(levelname)s: %(message)s')

    destination = complete_destination(destination)
    processor = Merge(importers=ctx.importers,
                      hooks=ctx.hooks,
                      destination=destination,
                      existing_file=complete_existing_file(
                          ctx.config, existing_file, destination),
                      reverse=reverse,
                      failfast=failfast,
                      quiet=quiet,
                      dry_run=dry_run)

    status = processor.process(src)
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


@click.command('archive')
@click.argument('src',
                nargs=-1,
                type=click.Path(exists=True, resolve_path=True))
@click.option('--destination',
              '-o',
              metavar='DIR',
              type=click.Path(file_okay=False, resolve_path=True),
              default=os.getcwd(),
              help='The destination documents tree root directory.')
@click.option('--overwrite',
              '-f',
              is_flag=True,
              help='Overwrite destination files with the same name.')
@click.option('--dry-run',
              '-n',
              is_flag=True,
              help='Just print where the files would be moved.')
@click.option('--failfast',
              '-x',
              is_flag=True,
              help='Stop processing at the first error.')
@click.option('--quiet', '-q', count=True, help='Suppress all output.')
@click.pass_obj
def _archive(ctx, src, destination, overwrite, dry_run, failfast, quiet):
    """Archive documents.

    Walk the SRC list of files or directories and move each file identified by
    one of the configured importers in a directory hierarchy mirroring the
    structure of the accounts associated to the documents and with a file name
    composed by the document date and document name returned by the importer.

    Documents are moved to their filing location only when no errors are
    encountered processing all the input files. Documents in the destination
    directory are not overwritten, unless the --force option is used.
    
    The default destination path follows Beansprout's conventional directory
    structure: {destination_dir}/transactions/{account_hierarchy}/{filename}
    """
    transaction_dir = os.path.join(complete_destination(destination),
                                   "transactions")

    from beangulp import _archive as beangulp_archive
    callback = beangulp_archive.callback
    return callback(src=src,
                    destination=transaction_dir,
                    dry_run=dry_run,
                    overwrite=overwrite,
                    failfast=failfast,
                    quiet=quiet)


@click.command('extract')
@click.argument('src',
                nargs=-1,
                type=click.Path(exists=True, resolve_path=True))
@click.option('--output',
              '-o',
              type=click.File('w'),
              default='-',
              help='Output file.')
@click.option('--existing',
              '-e',
              type=click.Path(exists=True),
              help='Existing Beancount ledger for de-duplication.')
@click.option('--reverse',
              '-r',
              is_flag=True,
              help='Sort entries in reverse order.')
@click.option('--failfast',
              '-x',
              is_flag=True,
              help='Stop processing at the first error.')
@click.option('--verbose',
              '-v',
              count=True,
              help='Print verbose information about the process.')
@click.option('--quiet', '-q', count=True, help='Suppress all output.')
@click.pass_obj
def _extract(ctx, src, output, existing, reverse, failfast, verbose, quiet):
    existing = complete_existing_file(ctx.config, existing)

    # Set up logging
    logging_level = logging.WARNING
    if verbose == 1:
        quiet = 0
        logging_level = logging.INFO
    elif verbose >= 2:
        quiet = 0
        logging_level = logging.DEBUG
    elif quiet > 0:
        logging_level = logging.ERROR
    logging.basicConfig(level=logging_level,
                        format='%(levelname)s: %(message)s')

    from beangulp import _extract as beangulp_extract
    return beangulp_extract(ctx, src, output, existing, reverse, failfast,
                            quiet)


class BeanSprout(beangulp.Ingest):
    """BeanSprout command-line tool for managing Beancount ledgers."""

    def __init__(self,
                 config: Config,
                 importers: List[ImporterType],
                 hooks=None):
        """Initialize the BeanSprout class.

        Args:
            config: Configuration object
            importers: List of importers to use.
            hooks: Optional list of hooks to run after extraction.
        """
        # Initialize the parent class
        super().__init__(importers, hooks)
        self.config = config

        # Remove the original archive command
        self.cli.commands.pop("archive", None)

        # Add our custom archive command
        self.cli.add_command(_archive)

        # Add the merge command
        self.cli.add_command(_merge)

        # Add the quote command
        self.cli.add_command(_quote)


def main():
    config = load_config()

    importers = config.importers

    # Define hooks for post-processing
    hooks = []

    # Apply smart_importer if enabled (default to True)
    use_smart_importer = os.environ.get("BEANSPROUT_USE_SMART_IMPORTER",
                                        "1") == "1"
    if use_smart_importer:
        from smart_importer import PredictPostings

        # Configure weights if provided
        weights_str = os.environ.get("BEANSPROUT_SMART_IMPORTER_WEIGHTS", "")
        weights = None
        if weights_str:
            try:
                weights = eval(weights_str)  # Convert string to dict
                if not isinstance(weights, dict):
                    weights = None
            except:
                pass

        if weights:
            hooks.append(PredictPostings(weights=weights).hook)
        else:
            hooks.append(PredictPostings().hook)

    # Create and run the ingest command using our extended version
    ingest = BeanSprout(importers=importers, hooks=hooks, config=config)
    ingest()


if __name__ == "__main__":
    main()
