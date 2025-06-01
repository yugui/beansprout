import logging
import os
import importlib
import sys
import tomllib
from typing import NamedTuple, Optional, List, Dict, Any

from beansprout.importer.merge import ImporterType

_logger = logging.getLogger(__name__)


class Config(NamedTuple):
    primary_file: Optional[str] = None
    importers: List[ImporterType] = []


def load_config() -> Config:
    """
    Load the beansprout configuration from a TOML file.

    Looks for a file named 'beansprout.toml' or '.beansprout.toml' in the current directory.
    Example TOML format:

    primary_file = "main.beancount"

    [[importers]]
    name = "moneyforward"
    account = "Assets:Foo:Bar"
    filename_pattern = "*.csv"

    [[importers]]
    name = "other_importer"
    param1 = "value1"
    param2 = "value2"

    Returns:
        Config: A configuration object containing the primary file path and a list of importers.
    """
    file_path = "beansprout.toml"
    if not os.path.exists(file_path):
        file_path = ".beansprout.toml"
    if not os.path.exists(file_path):
        return Config(primary_file=None, importers=[])

    config_dir = os.path.dirname(os.path.abspath(file_path))
    with open(file_path, "rb") as f:
        config_data = tomllib.load(f)

    primary_file = config_data.get("primary_file")
    if primary_file is not None and not isinstance(primary_file, str):
        raise TypeError("primary_file must be a string or omitted")
    if primary_file is not None and not os.path.isabs(primary_file):
        primary_file = os.path.abspath(os.path.join(config_dir, primary_file))
    importers_data = config_data.get("importers", [])
    importers = []
    for importer_spec in importers_data:
        importer_name = importer_spec.get("name")
        if not isinstance(importer_name, str):
            raise ValueError("Invalid importer name")
        kwargs = {k: v for k, v in importer_spec.items() if k != "name"}
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
