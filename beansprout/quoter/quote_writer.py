#!/usr/bin/env python3
"""Price quote writer for bean-quote command.

This module provides the QuoteWriter class which handles writing price quotes
to properly structured output files following the pattern:
$destination/quotes/$symbol/YYYYmm.beancount
"""

import os
import logging
from typing import Dict, List, Optional, Tuple, Set
import datetime

from beancount.core.data import Price
from beancount.parser import printer
from beancount import loader

from beansprout.writer.file_rewriter import FileRewriter
from beansprout.writer.types import Block, BlockType, EntryWithLines, CommentedEntryWithLines, NewEntryBlock


class QuoteWriter:
    """A class to manage writing price quotes to destination files.
    
    This class handles the organization of price quotes into files based on
    commodity and month, creating necessary directory structures, and
    formatting the output.
    """

    def __init__(self, destination_base: str):
        """Initialize a QuoteWriter with a base destination directory.
        
        Args:
            destination_base: The base directory for output files.
        """
        self.destination_base = destination_base
        self.logger = logging.getLogger(__name__)

        # Create the quotes directory under the destination
        self.quotes_dir = os.path.join(destination_base, 'quotes')
        os.makedirs(self.quotes_dir, exist_ok=True)

        self.logger.debug(
            f"Initialized quote writer with base path: {self.quotes_dir}")

    def write_prices(self,
                     prices: List[Price],
                     clobber: bool = False) -> Dict[str, List[str]]:
        """Write price entries to appropriate destination files.
        
        Args:
            prices: List of Price directives to write.
            clobber: If True, overwrite existing prices. If False, skip existing prices.
            
        Returns:
            A dictionary mapping commodity symbols to lists of created file paths.
        """
        if not prices:
            self.logger.info("No prices to write")
            return {}

        # Filter out existing prices unless clobber is True
        filtered_prices = self.filter_new_prices(prices, clobber)

        if not filtered_prices:
            self.logger.info(
                "No new prices to write (all prices already exist)")
            return {}

        if len(filtered_prices) < len(prices):
            self.logger.info(
                f"Filtered {len(prices) - len(filtered_prices)} existing prices, writing {len(filtered_prices)} new prices"
            )

        # Group and deduplicate price entries by commodity, month, and date
        price_map = self._group_prices_by_symbol_and_month(filtered_prices)

        # Track written files
        written_files: Dict[str, List[str]] = {}

        # Write each group to a separate file
        for symbol, months in price_map.items():
            # Create the directory for this symbol
            symbol_dir = os.path.join(self.quotes_dir, symbol)
            os.makedirs(symbol_dir, exist_ok=True)

            written_files[symbol] = []

            for month_key, dated_prices in months.items():
                # Convert the dict of dated prices to a list and sort by date
                prices_list = list(dated_prices.values())
                prices_list.sort(key=lambda p: p.date)

                # Create the file path
                file_path = os.path.join(symbol_dir, f"{month_key}.beancount")
                written_files[symbol].append(file_path)

                # Check if file exists to determine write mode
                if os.path.exists(file_path):
                    self._write_to_existing_file(file_path, prices_list)
                else:
                    self._write_to_new_file(file_path, prices_list, symbol,
                                            month_key)

            total_prices = sum(len(prices) for prices in months.values())
            self.logger.info(
                f"Wrote {total_prices} prices for {symbol} to {len(months)} files"
            )

        return written_files

    def get_destination_path(self, symbol: str, month_key: str) -> str:
        """Get the destination file path for a given commodity and month.
        
        Args:
            symbol: The commodity symbol.
            month_key: The month key in YYYYMM format.
            
        Returns:
            The full file path for the given commodity and month.
        """
        symbol_dir = os.path.join(self.quotes_dir, symbol)
        return os.path.join(symbol_dir, f"{month_key}.beancount")

    def get_existing_quote_dates(self, symbol: str,
                                 month_key: str) -> Set[datetime.date]:
        """Get the set of dates for which quotes already exist in a file.
        
        Args:
            symbol: The commodity symbol.
            month_key: The month key in YYYYMM format.
            
        Returns:
            Set of dates for which quotes already exist.
        """
        file_path = self.get_destination_path(symbol, month_key)

        if not os.path.exists(file_path):
            return set()

        try:
            entries, errors, _ = loader.load_file(file_path)
            if errors:
                self.logger.warning(f"Errors loading {file_path}: {errors}")
                return set()

            # Extract dates from Price entries
            quote_dates = set()
            for entry in entries:
                if entry.__class__.__name__ == 'Price' and entry.currency == symbol:
                    quote_dates.add(entry.date)

            return quote_dates
        except Exception as e:
            self.logger.warning(
                f"Error reading existing quotes from {file_path}: {e}")
            return set()

    def filter_new_prices(self,
                          prices: List[Price],
                          clobber: bool = False) -> List[Price]:
        """Filter prices to only include those that don't already exist.
        
        Args:
            prices: List of Price directives to filter.
            clobber: If True, don't filter out existing prices.
            
        Returns:
            List of Price directives that don't already exist (unless clobber=True).
        """
        if clobber:
            return prices

        # Group prices by symbol and month to check efficiently
        filtered_prices = []

        for price in prices:
            symbol = price.currency
            month_key = price.date.strftime("%Y%m")

            # Get existing dates for this symbol/month combination
            existing_dates = self.get_existing_quote_dates(symbol, month_key)

            # Only include if the date doesn't already exist
            if price.date not in existing_dates:
                filtered_prices.append(price)
            else:
                self.logger.info(
                    f"Skipping existing quote for {symbol} on {price.date}")

        return filtered_prices

    def _group_prices_by_symbol_and_month(
            self,
            prices: List[Price]) -> Dict[str, Dict[str, Dict[str, Price]]]:
        """Group and deduplicate price entries by commodity, month, and date.
        
        Args:
            prices: List of Price directives to group.
            
        Returns:
            A nested dictionary: {symbol: {month_key: {date_key: price}}}
        """
        price_map: Dict[str, Dict[str, Dict[str, Price]]] = {}
        for price in prices:
            symbol = price.currency
            month_key = price.date.strftime("%Y%m")
            date_key = price.date.strftime("%Y-%m-%d")

            if symbol not in price_map:
                price_map[symbol] = {}

            if month_key not in price_map[symbol]:
                price_map[symbol][month_key] = {}

            # Only use the latest price entry for each date (if we have multiple for the same date)
            price_map[symbol][month_key][date_key] = price

        return price_map

    def _merge_prices_by_date(self, existing_prices: List[Price],
                              new_prices: List[Price]) -> List[Price]:
        """Merge two lists of prices, with new prices taking precedence for same dates.
        
        Args:
            existing_prices: List of existing Price directives.
            new_prices: List of new Price directives to merge.
            
        Returns:
            A merged and sorted list of Price directives.
        """
        # Create a map of date to price for deduplication
        price_map: Dict[str, Price] = {}

        # Add existing prices first
        for price in existing_prices:
            date_key = price.date.strftime("%Y-%m-%d")
            price_map[date_key] = price

        # Add new prices, overwriting existing ones for same dates
        for price in new_prices:
            date_key = price.date.strftime("%Y-%m-%d")
            price_map[date_key] = price

        # Convert back to list and sort by date
        merged_prices = list(price_map.values())
        merged_prices.sort(key=lambda p: p.date)

        return merged_prices

    def _write_to_new_file(self, file_path: str, prices_list: List[Price],
                           symbol: str, month_key: str) -> None:
        """Write prices to a new file (original implementation).
        
        Args:
            file_path: The path to the file to write.
            prices_list: List of Price directives to write.
            symbol: The commodity symbol.
            month_key: The month key in YYYYMM format.
        """
        self.logger.debug(
            f"Writing {len(prices_list)} prices to new file {file_path}")

        with open(file_path, 'w') as f:
            # Add file header
            f.write(
                f";; Price quotes for {symbol} - {month_key[0:4]}-{month_key[4:6]}\n"
            )
            f.write(f";; Generated by bean-sprout quote command\n\n")

            for price in prices_list:
                # Format price and normalize spaces
                formatted_price = printer.format_entry(price).rstrip()
                f.write(formatted_price)
                f.write('\n')

    def _write_to_existing_file(self, file_path: str,
                                new_prices: List[Price]) -> None:
        """Write prices to an existing file, preserving existing content.
        
        Args:
            file_path: The path to the existing file to update.
            new_prices: List of new Price directives to add/merge.
        """
        self.logger.debug(
            f"Updating existing file {file_path} with {len(new_prices)} prices"
        )

        file_rewriter = FileRewriter()
        transform_callback = self._create_price_merge_transform(new_prices)
        file_rewriter.rewrite_file(file_path, transform_callback)

    def _create_price_merge_transform(self, new_prices: List[Price]):
        """Create a transformation callback for merging prices.
        
        Args:
            new_prices: List of new Price directives to merge.
            
        Returns:
            A callback function that transforms blocks by merging prices.
        """

        def transform_blocks(existing_blocks: List[Block]) -> List[Block]:
            # Keep track of which new prices we still need to insert
            prices_to_insert = list(new_prices)
            result_blocks = []

            # Get all existing price dates for reference
            existing_price_dates = []
            for block in existing_blocks:
                if (block.type == BlockType.ENTRY and hasattr(block, 'entry')
                        and block.entry.__class__.__name__ == 'Price'):
                    existing_price_dates.append(block.entry.date)

            # Process each existing block in order
            for i, block in enumerate(existing_blocks):
                result_blocks.append(block)

                # If this is a price entry, check if we need to insert new prices after it
                if (block.type == BlockType.ENTRY and hasattr(block, 'entry')
                        and block.entry.__class__.__name__ == 'Price'):

                    current_date = block.entry.date

                    # Find the next price date in the file for boundary checking
                    next_price_date = None
                    for j in range(i + 1, len(existing_blocks)):
                        next_block = existing_blocks[j]
                        if (next_block.type == BlockType.ENTRY
                                and hasattr(next_block, 'entry')
                                and next_block.entry.__class__.__name__
                                == 'Price'):
                            next_price_date = next_block.entry.date
                            break

                    # Determine which new prices should be inserted after this position
                    prices_to_insert_here = []
                    remaining_prices = []

                    for new_price in prices_to_insert:
                        should_insert_here = self._should_insert_after_position(
                            new_price.date, current_date, next_price_date,
                            existing_price_dates)

                        if should_insert_here:
                            prices_to_insert_here.append(new_price)
                        else:
                            remaining_prices.append(new_price)

                    # Insert new prices with blank line separation
                    for new_price in prices_to_insert_here:
                        # Add blank line before new price entry
                        from beansprout.writer.types import NonEntryBlock
                        blank_line = NonEntryBlock(start_line=0,
                                                   original_lines=['\n'],
                                                   type=BlockType.FREE_TEXT)
                        result_blocks.append(blank_line)

                        # Add the new price entry
                        new_price_block = NewEntryBlock(entry=new_price)
                        result_blocks.append(new_price_block)

                    prices_to_insert = remaining_prices

            # If there are still prices to insert (they go after all existing entries)
            for new_price in prices_to_insert:
                # Add blank line before new price entry
                from beansprout.writer.types import NonEntryBlock
                blank_line = NonEntryBlock(start_line=0,
                                           original_lines=['\n'],
                                           type=BlockType.FREE_TEXT)
                result_blocks.append(blank_line)

                # Add the new price entry
                new_price_block = NewEntryBlock(entry=new_price)
                result_blocks.append(new_price_block)

            return result_blocks

        return transform_blocks

    def _should_insert_after_position(self, new_price_date, current_date,
                                      next_price_date, existing_price_dates):
        """Determine if a new price should be inserted after the current position.
        
        Args:
            new_price_date: Date of the new price to insert
            current_date: Date of the current price entry 
            next_price_date: Date of the next price entry (None if no next entry)
            existing_price_dates: List of all existing price dates in the file
            
        Returns:
            True if the new price should be inserted after the current position
        """
        # Don't insert if the new price date is before the current date
        if new_price_date < current_date:
            return False

        # If the new price already exists at this exact date, don't insert duplicate
        if new_price_date in existing_price_dates:
            return False

        # If there's no next price entry, this is the last position, so insert here
        # if new price date is >= current date
        if next_price_date is None:
            return new_price_date >= current_date

        # Insert here if the new price fits chronologically between current and next
        # (new price date <= next price date)
        return new_price_date <= next_price_date
