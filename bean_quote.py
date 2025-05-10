#!/usr/bin/env python3
"""Command for fetching and managing price quotes using custom quoters.

This command extends the default bean-price functionality by supporting
custom price quoters from the beansprout.quoter package and providing additional
features for price quote management.

The bean-quote command reads commodity definitions from beancount files,
fetches price quotes for active commodities, and writes the quotes to
appropriate destination files organized by commodity and date.
"""

import os
import sys
import click
import datetime
import logging
from typing import List, Optional, Dict, Any, Tuple, Set

from beancount.core import data
from beancount.core.data import Entries, Directive, Commodity, Price
from beancount import loader
from beanprice import source

# Import the commodity finder and quote fetcher from new package structure
from beansprout.quoter.commodity_finder import CommodityFinder
from beansprout.quoter.quote_fetcher import QuoteFetcher
from beansprout.quoter.quote_writer import QuoteWriter


@click.command()
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
@click.option('--custom-only',
              '-c',
              is_flag=True,
              help='Use only custom quoters from beansprout.quoter.sources package.')
@click.option('--verbose',
              '-v',
              count=True,
              help='Print verbose information about the process.')
@click.option('--dryrun',
              is_flag=True,
              help='Print extracted price entries without writing them.')
@click.option(
    '--destination',
    '-o',
    type=click.Path(file_okay=False, resolve_path=True),
    default=os.getcwd(),
    help='Base directory for output files (default: current directory).')
def bean_quote(filenames: List[str], date: Optional[datetime.datetime],
               inactive: bool, custom_only: bool, verbose: int, dryrun: bool,
               destination: str) -> None:
    """Fetch price quotes for commodities using custom quoters.
    
    This command fetches price quotes for commodities defined in the given
    beancount files using custom quoters from the beansprout.quoter.sources package
    and optionally built-in quoters from beanprice.
    
    The command outputs price directives to files named:
    $destination/quotes/$symbol/YYYYmm.beancount
    where $symbol is the commodity symbol and YYYYmm is the year and month.
    
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

    if verbose:
        click.echo(f"Loading entries from {len(filenames)} file(s)")

    for filename in filenames:
        if verbose > 1:
            click.echo(f"  Loading {filename}")

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
    if verbose:
        click.echo(f"Found {len(all_commodities)} commodities")

    # Filter active commodities
    if not inactive:
        active_commodities = finder.filter_active_commodities(
            commodities=all_commodities)
        if verbose:
            click.echo(
                f"Filtered to {len(active_commodities)} active commodities")
    else:
        active_commodities = all_commodities
        if verbose:
            click.echo("Including all commodities (--inactive flag)")

    # Find the price date to use
    price_date = date.date() if date else datetime.date.today()
    if verbose:
        click.echo(f"Using price date: {price_date}")

    # Create the quote fetcher
    fetcher = QuoteFetcher(custom_only=custom_only)

    # Fetch quotes for each active commodity
    price_entries = []
    for commodity in active_commodities:
        if verbose > 1:
            click.echo(f"Fetching quote for {commodity.currency}")

        price_entry = fetcher.fetch_quote(commodity=commodity,
                                          quote_date=price_date)

        if price_entry:
            price_entries.append(price_entry)
            if verbose > 1:
                click.echo(
                    f"  Got price: {price_entry.amount} {price_entry.currency}"
                )
        elif verbose > 1:
            click.echo(f"  No price found for {commodity.currency}")

    if verbose:
        click.echo(f"Fetched {len(price_entries)} price entries")

    # Create quote writer for destination file management
    writer = QuoteWriter(destination_base=destination, verbose=verbose)

    # Write price entries to destination files or print them in dry run mode
    if dryrun:
        click.echo("Dry run - printing price entries:")
        for price in price_entries:
            click.echo(writer.format_price_for_display(price))
    else:
        written_files = writer.write_prices(price_entries)

        if verbose:
            total_files = sum(len(files) for files in written_files.values())
            click.echo(
                f"Wrote price entries for {len(written_files)} commodities "
                f"to {total_files} files in {writer.quotes_dir}")

    click.echo("Done.")


def main() -> int:
    """Entry point for the bean-quote command.
    
    Returns:
        Exit code, 0 for success, non-zero for error.
    """
    try:
        bean_quote()
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
