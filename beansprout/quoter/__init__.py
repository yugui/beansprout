"""Custom price quoters for beancount.

This package contains custom price source implementations for beancount price
fetching. Each module in this package can implement a Source class that is
compatible with the beanprice.source.Source interface.
"""

import importlib
import logging
from typing import Dict, Optional, Type, Set

from beanprice.source import Source

# Configure logging
_logger = logging.getLogger(__name__)

# Dictionary of source name -> source class
SOURCES: Dict[str, Type[Source]] = {}

# Set to track modules we've already tried to import
_TRIED_MODULES: Set[str] = set()


def get_source(source_name: str,
               custom_only: bool = False) -> Optional[Source]:
    """Get a price source instance by name.
    
    This function tries to load and instantiate a price source in the following order:
    1. Check if it's already loaded in SOURCES
    2. Try to load from beansprout.quoter.sources package with "beansprout.quoter.sources." prefix
    3. Try to load from quoters package with "quoters." prefix (legacy support)
    4. Try to load from beanprice.sources with "beanprice.sources." prefix (if custom_only is False)
    5. Try to interpret the name as a full module path (if custom_only is False)
    
    Args:
        source_name: The name of the source to load
        custom_only: If True, only try to load from the beansprout.quoter.sources package
        
    Returns:
        An instance of the Source class if found, None otherwise
    """
    # First check if it's a source we've already loaded
    if source_name in SOURCES:
        return SOURCES[source_name]()

    # 1. Try to load from beansprout.quoter.sources package
    sources_module_name = f"beansprout.quoter.sources.{source_name}"
    if sources_module_name not in _TRIED_MODULES:
        _TRIED_MODULES.add(sources_module_name)
        try:
            module = importlib.import_module(sources_module_name)
            if hasattr(module, 'Source'):
                source_class = getattr(module, 'Source')
                SOURCES[source_name] = source_class
                return source_class()
        except ImportError:
            _logger.debug(f"No source found in {sources_module_name}")

    # 2. Try to load from legacy quoters package with "quoters." prefix (for backward compatibility)
    legacy_module_name = f"quoters.{source_name}"
    if legacy_module_name not in _TRIED_MODULES:
        _TRIED_MODULES.add(legacy_module_name)
        try:
            module = importlib.import_module(legacy_module_name)
            if hasattr(module, 'Source'):
                source_class = getattr(module, 'Source')
                SOURCES[source_name] = source_class
                _logger.warning(
                    f"Using legacy source from {legacy_module_name}. "
                    f"Consider migrating to {sources_module_name}.")
                return source_class()
        except ImportError:
            _logger.debug(f"No source found in {legacy_module_name}")

    # If custom_only is True, we stop here
    if custom_only:
        _logger.warning(f"No custom price source found for '{source_name}'")
        return None

    # 3. Try to load from beanprice.sources with "beanprice.sources." prefix
    beanprice_module_name = f"beanprice.sources.{source_name}"
    if beanprice_module_name not in _TRIED_MODULES:
        _TRIED_MODULES.add(beanprice_module_name)
        try:
            module = importlib.import_module(beanprice_module_name)
            if hasattr(module, 'Source'):
                source_class = getattr(module, 'Source')
                SOURCES[source_name] = source_class
                return source_class()
        except ImportError:
            _logger.debug(f"No source found in {beanprice_module_name}")

    # 4. Try to interpret the name as a full module path
    if source_name not in _TRIED_MODULES:
        _TRIED_MODULES.add(source_name)
        try:
            module = importlib.import_module(source_name)
            if hasattr(module, 'Source'):
                source_class = getattr(module, 'Source')
                SOURCES[source_name] = source_class
                return source_class()
        except ImportError:
            _logger.debug(f"Could not import module: {source_name}")

    # No source found
    _logger.warning(f"No price source found for '{source_name}'")
    return None


__all__ = ['SOURCES', 'get_source']
