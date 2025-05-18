#!/usr/bin/env python3
"""Unit tests for the config module."""

import os
import tempfile
import unittest
import sys
from typing import List, Optional

from beancount.core import data
from beancount.parser import parser

from beansprout.config import load_config, Config


class TestImporter:
    """Test importer class for testing the config module."""

    def __init__(self, account: str = "Assets:Test", **kwargs):
        self.account = account
        self.kwargs = kwargs

    def identify(self, file_path):
        """Identify if this importer can handle the given file."""
        return False

    def extract(self, file_path, existing_entries=None):
        """Extract entries from the given file."""
        return []

    def file_account(self, file_path):
        """Return the account associated with this importer."""
        return self.account


class TestLoadConfig(unittest.TestCase):
    """Test the load_config function."""

    def setUp(self):
        """Set up the test environment."""
        # Create a temporary directory for test files
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.temp_dir.name)

        # Create a test importer module
        self.module_dir = os.path.join(self.temp_dir.name, "test_importers")
        os.makedirs(self.module_dir, exist_ok=True)

        # Create __init__.py in the module directory
        with open(os.path.join(self.module_dir, "__init__.py"), "w") as f:
            f.write("# Test importers package\n")

        # Create a test importer module
        with open(os.path.join(self.module_dir, "test_importer.py"), "w") as f:
            f.write("""
class Importer:
    def __init__(self, account="Assets:Test", **kwargs):
        self.account = account
        self.kwargs = kwargs
    
    def identify(self, file_path):
        return False
    
    def extract(self, file_path, existing_entries=None):
        return []
    
    def file_account(self, file_path):
        return self.account
""")

        # Add the module directory to sys.path
        sys.path.insert(0, self.temp_dir.name)

    def tearDown(self):
        """Clean up after the test."""
        # Remove the module directory from sys.path
        sys.path.remove(self.temp_dir.name)

        # Change back to the original directory
        os.chdir(self.old_cwd)

        # Clean up the temporary directory
        self.temp_dir.cleanup()

    def _create_config_file(self,
                            content: str,
                            filename: str = "beansprout.beancount"):
        """Create a config file with the given content."""
        with open(filename, "w") as f:
            f.write(content)

    def test_no_config_file(self):
        """Test loading config when no config file exists."""
        # Don't create any config files
        config = load_config()

        # Check that the config has default values
        self.assertIsNone(config.primary_file)
        self.assertEqual(len(config.importers), 0)

    def test_empty_config_file(self):
        """Test loading an empty config file."""
        # Create an empty config file
        self._create_config_file("")

        # Load the config
        config = load_config()

        # Check that the config has default values
        self.assertIsNone(config.primary_file)
        self.assertEqual(len(config.importers), 0)

    def test_config_with_primary_file(self):
        """Test loading a config with a primary_file directive."""
        # Create a config file with a primary_file directive
        self._create_config_file("""
2025-01-01 custom "beansprout" "primary_file" "main.beancount"
""")

        # Load the config
        config = load_config()

        # Check that the primary_file is set correctly
        self.assertEqual(config.primary_file, "main.beancount")
        self.assertEqual(len(config.importers), 0)

    def test_config_with_importer(self):
        """Test loading a config with an importer directive."""
        # Create a config file with an importer directive using the new interleaving format
        self._create_config_file("""
2025-01-01 custom "beansprout" "importer" "test_importers.test_importer" "account" "Assets:Test:Account"
""")

        # Load the config
        config = load_config()

        # Check that the importer is loaded correctly
        self.assertIsNone(config.primary_file)
        self.assertEqual(len(config.importers), 1)

        # Check that the importer has the correct account
        importer = config.importers[0]
        self.assertEqual(importer.account, "Assets:Test:Account")

    def test_config_with_multiple_importers(self):
        """Test loading a config with multiple importer directives."""
        # Create a config file with multiple importer directives using the new interleaving format
        self._create_config_file("""
2025-01-01 custom "beansprout" "importer" "test_importers.test_importer" "account" "Assets:Test:Account1"
2025-01-01 custom "beansprout" "importer" "test_importers.test_importer" "account" "Assets:Test:Account2"
""")

        # Load the config
        config = load_config()

        # Check that the importers are loaded correctly
        self.assertIsNone(config.primary_file)
        self.assertEqual(len(config.importers), 2)

        # Check that the importers have the correct accounts
        self.assertEqual(config.importers[0].account, "Assets:Test:Account1")
        self.assertEqual(config.importers[1].account, "Assets:Test:Account2")

    def test_config_with_primary_file_and_importers(self):
        """Test loading a config with both primary_file and importer directives."""
        # Create a config file with both primary_file and importer directives using the new interleaving format
        self._create_config_file("""
2025-01-01 custom "beansprout" "primary_file" "main.beancount"
2025-01-01 custom "beansprout" "importer" "test_importers.test_importer" "account" "Assets:Test:Account"
""")

        # Load the config
        config = load_config()

        # Check that both primary_file and importers are set correctly
        self.assertEqual(config.primary_file, "main.beancount")
        self.assertEqual(len(config.importers), 1)
        self.assertEqual(config.importers[0].account, "Assets:Test:Account")

    def test_config_with_invalid_primary_file(self):
        """Test loading a config with an invalid primary_file directive."""
        # Create a config file with an invalid primary_file directive
        self._create_config_file("""
2025-01-01 custom "beansprout" "primary_file" 123
""")

        # Load the config should raise a ValueError
        with self.assertRaises(ValueError):
            load_config()

    def test_config_with_invalid_importer_name(self):
        """Test loading a config with an invalid importer name."""
        # Create a config file with an invalid importer name
        self._create_config_file("""
2025-01-01 custom "beansprout" "importer" 123
""")

        # Load the config should raise a ValueError
        with self.assertRaises(ValueError):
            load_config()

    def test_config_with_nonexistent_importer(self):
        """Test loading a config with a nonexistent importer."""
        # Create a config file with a nonexistent importer
        self._create_config_file("""
2025-01-01 custom "beansprout" "importer" "nonexistent_importer"
""")

        # Load the config should raise a ValueError
        with self.assertRaises(ValueError):
            load_config()

    def test_alternate_config_file_name(self):
        """Test loading a config with the alternate file name."""
        # Create a config file with the alternate name
        self._create_config_file("""
2025-01-01 custom "beansprout" "primary_file" "alternate.beancount"
""",
                                 filename=".beansprout.beancount")

        # Load the config
        config = load_config()

        # Check that the primary_file is set correctly
        self.assertEqual(config.primary_file, "alternate.beancount")


if __name__ == "__main__":
    unittest.main()
