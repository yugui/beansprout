#!/usr/bin/env python3
"""Plugin for completing missing price directives using graph-based shortest path algorithms.

This plugin generates missing price directives for commodities by:
1. Building a graph of price relationships from existing price entries
2. Using Dijkstra's algorithm to find shortest paths from operating currencies
3. Applying temporal weighting to prefer recent quotes over historical ones
4. Generating new price entries for reachable commodities

The plugin only processes dates that already have price entries and fills in missing
prices for all commodities in all operating currencies where possible.

Usage:
    plugin "beansprout.plugins.price_completion"
    plugin "beansprout.plugins.price_completion" "temporal_base=1.0,temporal_scale=0.1"
"""

import datetime
import heapq
import math
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List, NamedTuple, Optional, Set, Tuple

import beancount
from beancount.core import data

__plugins__ = ("price_completion", )


class PriceCalculationResult(NamedTuple):
    """Result of price calculation with metadata from the closest edge."""
    price: Decimal
    closest_metadata: Dict[str, Any]
    has_current_date_edge: bool


class TemporalPriceGraph:
    """Graph data structure for price relationships with temporal weighting."""

    def __init__(self,
                 temporal_base: float = 1.0,
                 temporal_scale: float = 0.1):
        """Initialize the price graph with temporal parameters.
        
        Args:
            temporal_base: Base penalty for using historical quotes (parameter 'a')
            temporal_scale: Logarithmic scaling factor for temporal penalty (parameter 'b')
        """
        self.temporal_base = temporal_base
        self.temporal_scale = temporal_scale

        # Graph structure: commodity -> [(target_commodity, weight, price_value, date, metadata)]
        self.graph = defaultdict(list)

        # Historical price index: (from_commodity, to_commodity) -> [(date, price_value, metadata)]
        self.historical_prices = defaultdict(list)

        # Set of all commodities in the graph
        self.commodities = set()

    def add_price_entry(self, price_entry: data.Price) -> None:
        """Add a price entry to the graph and historical index.
        
        Args:
            price_entry: Beancount Price entry to add
        """
        from_commodity = price_entry.currency
        to_commodity = price_entry.amount.currency
        price_value = price_entry.amount.number
        date = price_entry.date
        metadata = price_entry.meta

        # Add to historical index
        self.historical_prices[(from_commodity, to_commodity)].append(
            (date, price_value, metadata))

        # Add commodities to set
        self.commodities.add(from_commodity)
        self.commodities.add(to_commodity)

    def build_graph_for_date(self, target_date: datetime.date) -> None:
        """Build the graph for a specific date using current and historical prices.
        
        Args:
            target_date: The date for which to build the graph
        """
        # Clear existing graph
        self.graph.clear()

        # Process all commodity pairs
        for (from_commodity,
             to_commodity), price_history in self.historical_prices.items():
            # Skip self-references
            if from_commodity == to_commodity:
                continue

            # Find the best price for this date
            best_price = self._find_best_price_for_date(
                price_history, target_date)
            if best_price is None:
                continue

            price_date, price_value, metadata = best_price

            # Calculate weight based on temporal distance
            if price_date == target_date:
                weight = 1.0
            else:
                days_diff = (target_date - price_date).days
                weight = self.temporal_base + self.temporal_scale * math.log(
                    days_diff)

            # Add bidirectional edges
            self.graph[from_commodity].append(
                (to_commodity, weight, price_value, price_date, metadata))
            if price_value != 0:
                self.graph[to_commodity].append(
                    (from_commodity, weight, 1 / price_value, price_date,
                     metadata))

    def _find_best_price_for_date(
        self, price_history: List[Tuple[datetime.date, Decimal,
                                        Dict[str,
                                             Any]]], target_date: datetime.date
    ) -> Optional[Tuple[datetime.date, Decimal, Dict[str, Any]]]:
        """Find the best price for a given target date.
        
        Args:
            price_history: List of (date, price_value, metadata) tuples sorted by date
            target_date: The target date
            
        Returns:
            (date, price_value, metadata) tuple for the best price, or None if no suitable price found
        """
        # Look for exact match first
        for date, price_value, metadata in price_history:
            if date == target_date:
                return (date, price_value, metadata)

        # Find most recent price before target date
        best_price = None
        for date, price_value, metadata in price_history:
            if date <= target_date:
                best_price = (date, price_value, metadata)
            else:
                break

        return best_price

    def find_shortest_paths(
            self, source_commodity: str) -> Dict[str, Tuple[float, List[str]]]:
        """Find shortest paths from source commodity to all other commodities using Dijkstra.
        
        Args:
            source_commodity: The source commodity to start from
            
        Returns:
            Dictionary mapping target_commodity -> (total_weight, path)
        """
        # Initialize distances and paths
        distances = {commodity: float('inf') for commodity in self.commodities}
        distances[source_commodity] = 0.0
        paths = {source_commodity: [source_commodity]}

        # Priority queue: (distance, commodity)
        pq = [(0.0, source_commodity)]
        visited = set()

        while pq:
            current_dist, current_commodity = heapq.heappop(pq)

            if current_commodity in visited:
                continue
            visited.add(current_commodity)

            # Check all neighbors
            for neighbor, weight, price_value, price_date, metadata in self.graph[
                    current_commodity]:
                if neighbor in visited:
                    continue

                new_dist = current_dist + weight

                if new_dist < distances[neighbor]:
                    distances[neighbor] = new_dist
                    paths[neighbor] = paths[current_commodity] + [neighbor]
                    heapq.heappush(pq, (new_dist, neighbor))

        # Return only reachable commodities (exclude infinite distances)
        result = {}
        for commodity in self.commodities:
            if distances[commodity] != float(
                    'inf') and commodity != source_commodity:
                result[commodity] = (distances[commodity], paths[commodity])

        return result

    def calculate_derived_price(
            self, path: List[str],
            target_date: datetime.date) -> Optional[PriceCalculationResult]:
        """Calculate the derived price along a path and return closest edge metadata.
        
        Args:
            path: List of commodities representing the path
            target_date: The target date for price calculation
            
        Returns:
            PriceCalculationResult with derived price, metadata from closest edge,
            and flag indicating if any edge is from target date, or None if calculation fails
        """
        if len(path) < 2:
            return None

        total_price = Decimal('1.0')
        closest_metadata = {}
        has_current_date_edge = False

        # The "closest" edge is the last edge in the path (directly connected to target)
        target_commodity = path[-1]

        for i in range(len(path) - 1):
            from_commodity = path[i]
            to_commodity = path[i + 1]

            # Find the edge in the graph
            edge_found = False
            for neighbor, weight, price_value, price_date, metadata in self.graph[
                    from_commodity]:
                if neighbor == to_commodity:
                    total_price *= price_value

                    # Check if this edge is from the target date (fresh data)
                    if price_date == target_date:
                        has_current_date_edge = True

                    # If this edge is connected to the target commodity, use its metadata
                    if to_commodity == target_commodity:
                        closest_metadata = metadata.copy() if metadata else {}

                    edge_found = True
                    break

            if not edge_found:
                return None

        return PriceCalculationResult(
            price=total_price,
            closest_metadata=closest_metadata,
            has_current_date_edge=has_current_date_edge)


def parse_config(config_str: str) -> Dict[str, float]:
    """Parse plugin configuration string.
    
    Args:
        config_str: Configuration string in format "temporal_base=1.0,temporal_scale=0.1"
        
    Returns:
        Dictionary of configuration parameters
    """
    config = {"temporal_base": 1.0, "temporal_scale": 0.1}

    if not config_str:
        return config

    for param in config_str.split(','):
        if '=' in param:
            key, value = param.split('=', 1)
            key = key.strip()
            if key in config:
                try:
                    config[key] = float(value.strip())
                except ValueError:
                    pass  # Keep default value

    return config


def price_completion(
        entries: List[data.Directive],
        options_map: Dict,
        config: str = "") -> Tuple[List[data.Directive], List[data.Directive]]:
    """Complete missing price directives using graph-based shortest path algorithms.
    
    Args:
        entries: List of Beancount entries
        options_map: Beancount options map
        config: Plugin configuration string
        
    Returns:
        Tuple of (entries, errors)
    """
    # Parse configuration
    config_params = parse_config(config)

    # Extract operating currencies
    operating_currencies = set(options_map.get('operating_currency', []))

    # Create temporal price graph
    graph = TemporalPriceGraph(temporal_base=config_params['temporal_base'],
                               temporal_scale=config_params['temporal_scale'])

    # Collect all price entries and dates
    price_entries = []
    price_dates = set()

    for entry in entries:
        if isinstance(entry, data.Price):
            price_entries.append(entry)
            price_dates.add(entry.date)
            graph.add_price_entry(entry)

    # Sort historical prices by date for efficient lookup
    for price_history in graph.historical_prices.values():
        price_history.sort(key=lambda x: x[0])

    # Generate missing prices for each date
    new_price_entries = []
    errors = []

    for target_date in sorted(price_dates):
        # Build graph for this specific date
        graph.build_graph_for_date(target_date)

        # Find missing prices from each operating currency
        for operating_currency in operating_currencies:
            if operating_currency not in graph.commodities:
                continue

            # Find shortest paths from this operating currency
            paths = graph.find_shortest_paths(operating_currency)

            # Generate missing price entries
            for target_commodity, (total_weight, path) in paths.items():
                # Check if we already have this price
                existing_price = False
                for entry in price_entries:
                    if (entry.date == target_date
                            and entry.currency == target_commodity
                            and entry.amount.currency == operating_currency):
                        existing_price = True
                        break

                if existing_price:
                    continue

                # Calculate derived price (this gives us operating_currency -> target_commodity rate)
                price_result = graph.calculate_derived_price(path, target_date)
                if price_result is None:
                    continue

                # Skip price completion if all edges in the path are historical (no current-date edges)
                if not price_result.has_current_date_edge:
                    continue

                # Invert to get target_commodity price in operating_currency
                # price_result.price is "1 operating_currency = X target_commodity"
                # We want "1 target_commodity = Y operating_currency", so Y = 1/X
                target_commodity_price = Decimal("1") / price_result.price

                # Prepare metadata with filename and lineno from closest edge
                metadata = price_result.closest_metadata.copy()

                # Create new price entry
                new_price_entry = data.Price(meta=metadata,
                                             date=target_date,
                                             currency=target_commodity,
                                             amount=beancount.Amount(
                                                 target_commodity_price,
                                                 operating_currency))
                new_price_entries.append(new_price_entry)

    return entries + new_price_entries, errors
