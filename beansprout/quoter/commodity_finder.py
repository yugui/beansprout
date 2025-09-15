#!/usr/bin/env python3
"""Module for finding and filtering active commodities in beancount files.

This module provides functionality to identify commodities in beancount ledger files
and filter them based on their metadata to determine which ones should have
price quotes fetched.
"""

from typing import Dict, List, Optional, Set
import re

from beancount.core import data
from beancount.core.data import Directive, Commodity


class CommodityFinder:
    """Class for finding and filtering commodities in beancount entries.
    
    This class provides methods to extract commodity directives from beancount entries
    and filter them based on metadata fields that determine whether they should be
    considered for price fetching.
    """

    def find_all_commodities(self,
                             entries: List[Directive]) -> List[Commodity]:
        """Find all commodity directives in the given entries.
        
        Args:
            entries: List of beancount directives to search through.
            
        Returns:
            List of commodity directives found in the entries.
        """
        return [
            entry for entry in entries if isinstance(entry, data.Commodity)
        ]

    def filter_active_commodities(
            self, commodities: List[Commodity]) -> List[Commodity]:
        """Filter out inactive commodities that should not have prices fetched.
        
        A commodity is considered active if:
        1. It has "price" metadata specifying source information
        2. It does NOT have "quote: disabled" metadata
        
        Args:
            commodities: List of commodity directives to filter.
            
        Returns:
            List of active commodity directives that should have prices fetched.
        """
        active = []
        for commodity in commodities:
            # Check if the commodity has price metadata
            if 'price' not in commodity.meta:
                continue

            # Check if the commodity has quote: disabled metadata
            if commodity.meta.get('quote') == 'disabled':
                continue

            active.append(commodity)

        return active

    def filter_by_pattern(self, commodities: List[Commodity],
                          pattern: str) -> List[Commodity]:
        """Filter commodities by regex pattern on their currency symbol.
        
        Args:
            commodities: List of commodity directives to filter.
            pattern: Regular expression pattern to match against commodity symbols.
            
        Returns:
            List of commodity directives whose symbols match the pattern.
            
        Raises:
            re.error: If the pattern is invalid.
        """
        try:
            compiled_pattern = re.compile(pattern)
        except re.error as e:
            raise re.error(f"Invalid regex pattern '{pattern}': {e}")

        filtered = []
        for commodity in commodities:
            if compiled_pattern.match(commodity.currency):
                filtered.append(commodity)

        return filtered

    def filter_by_source(self, commodities: List[Commodity],
                         sources: Set[str]) -> List[Commodity]:
        """Filter commodities by source names in their price metadata.
        
        Args:
            commodities: List of commodity directives to filter.
            sources: Set of source names to match against.
            
        Returns:
            List of commodity directives that use at least one of the specified sources.
        """
        filtered = []
        for commodity in commodities:
            commodity_sources = self.parse_source_names(commodity)
            if commodity_sources.intersection(sources):
                filtered.append(commodity)

        return filtered

    def parse_source_names(self, commodity: Commodity) -> Set[str]:
        """Parse source names from commodity price metadata.
        
        Args:
            commodity: Commodity directive to parse.
            
        Returns:
            Set of source names found in the price metadata.
        """
        if 'price' not in commodity.meta:
            return set()

        price_metadata = commodity.meta['price']
        sources = set()

        # Parse format: "USD:yahoo/AAPL,coinbase/BTC JPY:yahoo/MSFT.T"
        # Split by spaces to get different currency sections
        currency_sections = price_metadata.split()

        for section in currency_sections:
            if ':' in section:
                # Extract the part after the colon
                after_colon = section.split(':', 1)[1]
                # Split by comma to get individual source/ticker pairs
                source_ticker_pairs = after_colon.split(',')

                for pair in source_ticker_pairs:
                    if '/' in pair:
                        source_name = pair.split('/')[0]
                        sources.add(source_name)

        return sources
