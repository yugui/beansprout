import logging
import os
import importlib
from typing import NamedTuple, Optional, List, Tuple, Any, Dict

from beansprout.importer.merge import ImporterType
import beancount.loader
from beancount.core import data

_logger = logging.getLogger(__name__)


class Config(NamedTuple):
    primary_file: Optional[str] = None
    importers: List[ImporterType] = []


def load_config() -> Config:
    """
    Load the beansprout configuration from a beancount file.
    
    Looks for a file named 'beansprout.beancount' or '.beansprout.beancount' in the current directory.
    Processes custom directives with the type 'beansprout' to configure:
    
    1. Primary file: Specified with 'primary_file' directive
       Example: 2025-05-18 custom "beansprout" "primary_file" "main.beancount"
    
    2. Importers: Specified with 'importer' directive followed by the importer name and parameters
       Example: 2025-05-18 custom "beansprout" "importer" "some_importer" "account" "Assets:Foo:Bar" "filename_pattern" "*.csv"
       
       Parameters are specified as interleaving names and values, where each parameter name is followed by its value.
    
    Returns:
        Config: A configuration object containing the primary file path and a list of importers.
    """
    file_path = os.path.join("beansprout.beancount")
    if not os.path.exists(file_path):
        file_path = os.path.join(".beansprout.beancount")
    if not os.path.exists(file_path):
        return Config(primary_file=None, importers=[])

    entries, _, _ = beancount.loader.load_file(file_path)
    primary_file = None
    importer_specs: List[Tuple[str, Dict[str, Any]]] = []

    for entry in entries:
        if not isinstance(entry, data.Custom):
            continue
        if entry.type != "beansprout":
            continue
        if len(entry.values) < 2:
            continue

        if entry.values[0].value == "primary_file":
            if not isinstance(entry.values[1].value, str):
                raise ValueError("Invalid primary_file name")
            primary_file = entry.values[1].value

        elif entry.values[0].value == "importer":
            if not isinstance(entry.values[1].value, str):
                raise ValueError("Invalid importer name")
            importer_name = entry.values[1].value
            importer_kwargs = {}
            param_values = entry.values[2:]
            if len(param_values) % 2 != 0:
                _logger.warning(
                    f"Odd number of parameters for importer {importer_name}, last parameter will be ignored"
                )
                param_values = param_values[:
                                            -1]  # Remove the last parameter to make it even

            for i in range(0, len(param_values), 2):
                name_value = param_values[i]
                param_value = param_values[i + 1]

                if not isinstance(name_value.value, str):
                    _logger.warning(
                        f"Parameter name for importer {importer_name} is not a string: {name_value.value}"
                    )
                    continue

                name = name_value.value
                value = param_value.value
                importer_kwargs[name] = value

            importer_specs.append((importer_name, importer_kwargs))

    importers = []
    for importer_name, kwargs in importer_specs:
        importer = _build_importer(importer_name, kwargs)
        if importer is None:
            raise ValueError(f"Invalid importer name: {importer_name}")
        importers.append(importer)

    return Config(primary_file=primary_file, importers=importers)


def _build_importer(importer_name: str,
                    kwargs: Dict[str, Any]) -> Optional[ImporterType]:
    """
    Build an importer instance from the given name and parameters.
    
    Attempts to load the importer module from either 'beansprout.importer.{importer_name}'
    or directly from '{importer_name}'. Then instantiates the 'Importer' class from
    the module with the provided keyword arguments.
    
    Args:
        importer_name: The name of the importer module to load
        kwargs: A dictionary of keyword arguments to pass to the importer constructor
        
    Returns:
        An instance of the importer if successful, None otherwise
    """
    try:
        module = importlib.import_module(
            f"beansprout.importer.{importer_name}")
        if hasattr(module, "Importer"):
            importer_class = getattr(module, "Importer")
            try:
                return importer_class(**kwargs)
            except (TypeError, ValueError) as e:
                _logger.warning(
                    f"Failed to instantiate importer {importer_name}: {str(e)}"
                )
                return None
    except ImportError:
        _logger.debug(
            f"No importer found for beansprout.importer.{importer_name}")

    try:
        module = importlib.import_module(importer_name)
        if hasattr(module, "Importer"):
            importer_class = getattr(module, "Importer")
            try:
                return importer_class(**kwargs)
            except (TypeError, ValueError) as e:
                _logger.warning(
                    f"Failed to instantiate importer {importer_name}: {str(e)}"
                )
                return None
    except ImportError:
        _logger.error(f"Failed to load importer {importer_name}")

    return None
