#!/usr/bin/env python3
"""Module for finding and filtering active commodities in beancount files.

This module provides functionality to identify commodities in beancount ledger files
and filter them based on their metadata to determine which ones should have
price quotes fetched.
"""

from typing import Dict, List, Optional

from beancount.core import data
from beancount.core.data import Directive, Commodity


class CommodityFinder:
    """Class for finding and filtering commodities in beancount entries.
    
    This class provides methods to extract commodity directives from beancount entries
    and filter them based on metadata fields that determine whether they should be
    considered for price fetching.
    """

    def find_all_commodities(self, entries: List[Directive]) -> List[Commodity]:
        """Find all commodity directives in the given entries.
        
        Args:
            entries: List of beancount directives to search through.
            
        Returns:
            List of commodity directives found in the entries.
        """
        return [entry for entry in entries 
                if isinstance(entry, data.Commodity)]
    
    def filter_active_commodities(self, commodities: List[Commodity]) -> List[Commodity]:
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
    
    def get_price_sources(self, commodity: Commodity) -> Dict[str, str]:
        """Extract price sources from commodity metadata.
        
        The price metadata format is: "CURRENCY1:SOURCE1/TICKER1 CURRENCY2:SOURCE2/TICKER2 ..."
        For example: "USD:yahoo/AAPL CAD:yahoo/AAPL.TO"
        
        Args:
            commodity: Commodity directive to extract price sources from.
            
        Returns:
            Dictionary mapping quote currencies to source/ticker strings.
            For example: {"USD": "yahoo/AAPL", "CAD": "yahoo/AAPL.TO"}
        """
        if 'price' not in commodity.meta:
            return {}
            
        price_meta = commodity.meta['price']
        sources = {}
        
        # Split by spaces to get each currency:source/ticker pair
        for pair in price_meta.split():
            if ':' not in pair:
                continue
                
            currency, source_ticker = pair.split(':', 1)
            sources[currency] = source_ticker
            
        return sources