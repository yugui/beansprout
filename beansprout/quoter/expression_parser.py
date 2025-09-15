#!/usr/bin/env python3
"""Expression parser for price source specifications.

This module provides functionality to parse price source specifications in the format:
"CURRENCY1:SOURCE1/TICKER1,SOURCE2/TICKER2 CURRENCY2:SOURCE3/TICKER3"

For example: "USD:yahoo/AAPL CAD:yahoo/AAPL.TO"

Multiple sources per currency are supported with comma separation:
"USD:source1/TICKER1,source2/TICKER2"

Inversion notation is supported by prefixing the ticker with ^ symbol:
"USD:yahoo/^CADUSD=X" (inverts the CADUSD rate to get USD/CAD)
"""

import logging
from typing import Dict, List, NamedTuple

# A named tuple to represent the price source specification
#
# Fields:
# - quote_currency: The currency in which the price is quoted (e.g., USD)
# - source: The name of the price source module/provider (e.g., yahoo, coinbase)
# - ticker: The ticker symbol for the commodity in the source
# - invert: Boolean flag to invert the price (1/price), useful for currency pairs
SourceSpec = NamedTuple('SourceSpec', [
    ('quote_currency', str),
    ('source', str),
    ('ticker', str),
    ('invert', bool),
])

# Configure logging
_logger = logging.getLogger(__name__)


def parse_price_expression(
        price_expression: str) -> Dict[str, List[SourceSpec]]:
    """Parse a price expression into source specifications.
    
    The price expression format is: "CURRENCY1:SOURCE1/TICKER1 CURRENCY2:SOURCE2/TICKER2 ..."
    For example: "USD:yahoo/AAPL CAD:yahoo/AAPL.TO"
    
    Multiple sources for the same currency can be specified with comma separations:
    "USD:source1/TICKER1,source2/TICKER2"
    
    Inversion notation is supported by prefixing the ticker with ^ symbol:
    "USD:yahoo/^CADUSD=X" (inverts the CADUSD rate to get USD/CAD)
    
    Args:
        price_expression: The price expression string to parse
        
    Returns:
        Dictionary mapping currency -> List[SourceSpec] for each price source.
        The invert flag indicates whether the price should be inverted (1/price).
        
    Raises:
        ValueError: If the expression format is invalid
    """
    if not price_expression or not price_expression.strip():
        raise ValueError("Empty price expression")

    sources = {}

    # Split by spaces to get each currency:source/ticker pair
    for pair in price_expression.split():
        if ':' not in pair:
            raise ValueError(
                f"Invalid format in '{pair}': expected 'CURRENCY:SOURCE/TICKER'"
            )

        currency, source_spec = pair.split(':', 1)
        if not currency:
            raise ValueError(f"Empty currency in '{pair}'")

        if currency not in sources:
            sources[currency] = []

        # Handle multiple sources for the same currency (comma-separated)
        for source_ticker in source_spec.split(','):
            if '/' not in source_ticker:
                raise ValueError(
                    f"Invalid source/ticker format in '{source_ticker}': expected 'SOURCE/TICKER'"
                )

            source, ticker = source_ticker.split('/', 1)

            if not source:
                raise ValueError(f"Empty source in '{source_ticker}'")
            if not ticker:
                raise ValueError(f"Empty ticker in '{source_ticker}'")

            # Check if ticker has the inversion notation (^)
            invert = ticker.startswith('^')
            if invert:
                # Remove the ^ symbol from the ticker
                ticker = ticker[1:]
                if not ticker:
                    raise ValueError(
                        f"Empty ticker after inversion symbol in '{source_ticker}'"
                    )

            sources[currency].append(
                SourceSpec(quote_currency=currency,
                           source=source,
                           ticker=ticker,
                           invert=invert))

    if not sources:
        raise ValueError("No valid price sources found in expression")

    return sources


def get_example_expressions() -> List[str]:
    """Get a list of example price expressions for error messages.
    
    Returns:
        List of example expression strings
    """
    return [
        "USD:yahoo/AAPL", "USD:yahoo/AAPL CAD:yahoo/AAPL.TO",
        "USD:source1/TICKER1,source2/TICKER2", "USD:yahoo/^CADUSD=X",
        "USD:yahoo/MSFT CAD:yahoo/MSFT.TO EUR:yahoo/MSFT.DE"
    ]