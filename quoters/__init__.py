"""Custom price quoters for beancount.

This package contains custom price source implementations for beancount price
fetching. Each module in this package can implement a Source class that is
compatible with the beanprice.source.Source interface.
"""

import os
import importlib
import pkgutil
from typing import Dict, Type

from beanprice.source import Source

# Dictionary of source name -> source class
SOURCES: Dict[str, Type[Source]] = {}


def _discover_and_register_sources() -> None:
    """Discover and register all source modules in this package."""
    package_dir = os.path.dirname(__file__)
    
    for _, name, is_pkg in pkgutil.iter_modules([package_dir]):
        # Skip __init__.py and non-modules
        if name.startswith('_') or is_pkg:
            continue
            
        # Import the module
        try:
            module = importlib.import_module(f"quoters.{name}")
            
            # If the module has a Source class, register it
            if hasattr(module, 'Source'):
                source_class = getattr(module, 'Source')
                # Register the source under its module name
                SOURCES[name] = source_class
        except Exception as e:
            print(f"Failed to load quoter module {name}: {e}")


# Discover and register sources on import
_discover_and_register_sources()


__all__ = ['SOURCES']