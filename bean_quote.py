#!/usr/bin/env python3
"""Command for fetching and managing price quotes using custom quoters.

This command extends the default bean-price functionality by supporting
custom price quoters from the quoters/ directory and providing additional
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

# Import the commodity finder and quote fetcher
from quoters.commodity_finder import CommodityFinder
from quoters.quote_fetcher import QuoteFetcher


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
              help='Use only custom quoters from quoters/ directory.')
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
    beancount files using custom quoters from the quoters/ directory and
    optionally built-in quoters from beanprice.
    
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

    # Write price entries to destination files or print them in dry run mode
    if dryrun:
        click.echo("Dry run - printing price entries:")
        for price in price_entries:
            click.echo(f"{price.date} price {price.currency} {price.amount}")
    else:
        # Create the quotes directory structure
        quotes_dir = os.path.join(destination, 'quotes')
        os.makedirs(quotes_dir, exist_ok=True)

        # Group price entries by commodity and month
        price_map: Dict[str, Dict[str, List[Price]]] = {}
        for price in price_entries:
            symbol = price.currency
            month_key = price.date.strftime("%Y%m")

            if symbol not in price_map:
                price_map[symbol] = {}

            if month_key not in price_map[symbol]:
                price_map[symbol][month_key] = []

            price_map[symbol][month_key].append(price)

        # Write each group to a separate file
        for symbol, months in price_map.items():
            # Create the directory for this symbol
            symbol_dir = os.path.join(quotes_dir, symbol)
            os.makedirs(symbol_dir, exist_ok=True)

            for month_key, prices in months.items():
                # Sort prices by date
                prices.sort(key=lambda p: p.date)

                # Create the file path
                file_path = os.path.join(symbol_dir, f"{month_key}.beancount")

                if verbose > 1:
                    click.echo(f"Writing {len(prices)} prices to {file_path}")

                # Write the prices to the file
                with open(file_path, 'w') as f:
                    for price in prices:
                        f.write(
                            f"{price.date} price {price.currency} {price.amount}\n"
                        )

        if verbose:
            click.echo(f"Wrote price entries to {quotes_dir}")

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
