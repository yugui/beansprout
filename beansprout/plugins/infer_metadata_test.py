#!/usr/bin/env python3
"""Tests for infer_metadata plugin."""

import datetime
import os
import tempfile
import unittest
from decimal import Decimal

from beancount.core import data
from beancount.core.amount import Amount

from beansprout.plugins import infer_metadata


class InferMetadataTest(unittest.TestCase):
    """Test cases for infer_metadata plugin."""

    def setUp(self):
        """Set up test data."""
        self.maxDiff = None
        self.meta = {'filename': 'test.beancount', 'lineno': 1}
        self.date = datetime.date(2020, 1, 1)

        # Create temporary directory for test files
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.test_dir)

    def _create_options_map(self):
        """Create a test options map."""
        return {'filename': os.path.join(self.test_dir, 'test.beancount')}

    def test_direct_copy_metadata(self):
        """Test direct copying of metadata values."""
        commodity = data.Commodity(meta=dict(self.meta, source_field='USD'),
                                   date=self.date,
                                   currency='USD')

        entries = [commodity]
        config = "commodity target_field source_field"
        options_map = self._create_options_map()

        transformed_entries, errors = infer_metadata.infer_metadata(
            entries, options_map, config)

        self.assertEqual(len(errors), 0)
        self.assertEqual(len(transformed_entries), 1)
        self.assertEqual(transformed_entries[0].meta['target_field'], 'USD')

    def test_special_commodity_source(self):
        """Test __commodity__ special source for Commodity directives."""
        commodity = data.Commodity(meta=dict(self.meta),
                                   date=self.date,
                                   currency='USD')

        entries = [commodity]
        config = "commodity unit __commodity__"
        options_map = self._create_options_map()

        transformed_entries, errors = infer_metadata.infer_metadata(
            entries, options_map, config)

        self.assertEqual(len(errors), 0)
        self.assertEqual(transformed_entries[0].meta['unit'], 'USD')

    def test_special_account_source_open(self):
        """Test __account__ special source for Open directives."""
        open_entry = data.Open(meta=dict(self.meta),
                               date=self.date,
                               account='Assets:Bank:Checking',
                               currencies=None,
                               booking=None)

        entries = [open_entry]
        config = "open name __account__"
        options_map = self._create_options_map()

        transformed_entries, errors = infer_metadata.infer_metadata(
            entries, options_map, config)

        self.assertEqual(len(errors), 0)
        self.assertEqual(transformed_entries[0].meta['name'], 'Checking')

    def test_special_account_source_balance(self):
        """Test __account__ special source for Balance directives."""
        balance = data.Balance(meta=dict(self.meta),
                               date=self.date,
                               account='Assets:Bank:Savings',
                               amount=Amount(Decimal('1000.00'), 'USD'),
                               tolerance=None,
                               diff_amount=None)

        entries = [balance]
        config = "balance account_name __account__"
        options_map = self._create_options_map()

        transformed_entries, errors = infer_metadata.infer_metadata(
            entries, options_map, config)

        self.assertEqual(len(errors), 0)
        self.assertEqual(transformed_entries[0].meta['account_name'],
                         'Savings')

    def test_mapping_lookup(self):
        """Test metadata inference with mapping file lookup."""
        # Create mapping file
        mapping_path = os.path.join(self.test_dir, 'volatility.yaml')
        with open(mapping_path, 'w') as f:
            f.write('checking: low\n')
            f.write('savings: low\n')
            f.write('stocks: high\n')

        open_entry = data.Open(meta=dict(self.meta, account_class='stocks'),
                               date=self.date,
                               account='Assets:Investments:Stocks',
                               currencies=None,
                               booking=None)

        entries = [open_entry]
        config = "open volatility account_class file:volatility.yaml"
        options_map = self._create_options_map()

        transformed_entries, errors = infer_metadata.infer_metadata(
            entries, options_map, config)

        self.assertEqual(len(errors), 0)
        self.assertEqual(transformed_entries[0].meta['volatility'], 'high')

    def test_mapping_lookup_error(self):
        """Test error when key not found in mapping table."""
        # Create mapping file
        mapping_path = os.path.join(self.test_dir, 'volatility.yaml')
        with open(mapping_path, 'w') as f:
            f.write('checking: low\n')
            f.write('savings: low\n')

        open_entry = data.Open(meta=dict(self.meta, account_class='unknown'),
                               date=self.date,
                               account='Assets:Unknown',
                               currencies=None,
                               booking=None)

        entries = [open_entry]
        config = "open volatility account_class file:volatility.yaml"
        options_map = self._create_options_map()

        transformed_entries, errors = infer_metadata.infer_metadata(
            entries, options_map, config)

        self.assertEqual(len(errors), 1)
        self.assertIn('unknown', errors[0].message)
        self.assertIn('volatility.yaml', errors[0].message)

    def test_multiple_rules_same_directive(self):
        """Test applying multiple rules to the same directive type."""
        open_entry = data.Open(meta=dict(self.meta, account_class='stocks'),
                               date=self.date,
                               account='Assets:Investments:Stocks',
                               currencies=None,
                               booking=None)

        entries = [open_entry]
        config = """
            open name __account__
            open class_copy account_class
        """
        options_map = self._create_options_map()

        transformed_entries, errors = infer_metadata.infer_metadata(
            entries, options_map, config)

        self.assertEqual(len(errors), 0)
        self.assertEqual(transformed_entries[0].meta['name'], 'Stocks')
        self.assertEqual(transformed_entries[0].meta['class_copy'], 'stocks')

    def test_skip_existing_metadata(self):
        """Test that existing metadata is not overwritten."""
        commodity = data.Commodity(meta=dict(self.meta, unit='EUR'),
                                   date=self.date,
                                   currency='USD')

        entries = [commodity]
        config = "commodity unit __commodity__"
        options_map = self._create_options_map()

        transformed_entries, errors = infer_metadata.infer_metadata(
            entries, options_map, config)

        self.assertEqual(len(errors), 0)
        # Should preserve existing value
        self.assertEqual(transformed_entries[0].meta['unit'], 'EUR')

    def test_config_with_comments(self):
        """Test configuration parsing with comments."""
        commodity = data.Commodity(meta=dict(self.meta),
                                   date=self.date,
                                   currency='USD')

        entries = [commodity]
        config = """
            ; This is a comment
            commodity unit __commodity__  ; inline comment
            ; Another comment
        """
        options_map = self._create_options_map()

        transformed_entries, errors = infer_metadata.infer_metadata(
            entries, options_map, config)

        self.assertEqual(len(errors), 0)
        self.assertEqual(transformed_entries[0].meta['unit'], 'USD')

    def test_config_with_whitespace(self):
        """Test configuration parsing with extra whitespace."""
        commodity = data.Commodity(meta=dict(self.meta),
                                   date=self.date,
                                   currency='USD')

        entries = [commodity]
        config = "  commodity   unit   __commodity__  "
        options_map = self._create_options_map()

        transformed_entries, errors = infer_metadata.infer_metadata(
            entries, options_map, config)

        self.assertEqual(len(errors), 0)
        self.assertEqual(transformed_entries[0].meta['unit'], 'USD')

    def test_empty_config(self):
        """Test with empty configuration."""
        commodity = data.Commodity(meta=dict(self.meta),
                                   date=self.date,
                                   currency='USD')

        entries = [commodity]
        config = ""
        options_map = self._create_options_map()

        transformed_entries, errors = infer_metadata.infer_metadata(
            entries, options_map, config)

        self.assertEqual(len(errors), 0)
        # Entry should remain unchanged
        self.assertEqual(transformed_entries[0], commodity)

    def test_source_metadata_missing(self):
        """Test when source metadata doesn't exist."""
        commodity = data.Commodity(meta=dict(self.meta),
                                   date=self.date,
                                   currency='USD')

        entries = [commodity]
        config = "commodity target nonexistent_source"
        options_map = self._create_options_map()

        transformed_entries, errors = infer_metadata.infer_metadata(
            entries, options_map, config)

        self.assertEqual(len(errors), 0)
        # Should not add target metadata
        self.assertNotIn('target', transformed_entries[0].meta)

    def test_transaction_directive(self):
        """Test inference on Transaction directives."""
        transaction = data.Transaction(meta=dict(self.meta, uuid='abc123'),
                                       date=self.date,
                                       flag='*',
                                       payee='Store',
                                       narration='Purchase',
                                       tags=frozenset(),
                                       links=frozenset(),
                                       postings=[])

        entries = [transaction]
        config = "transaction id uuid"
        options_map = self._create_options_map()

        transformed_entries, errors = infer_metadata.infer_metadata(
            entries, options_map, config)

        self.assertEqual(len(errors), 0)
        self.assertEqual(transformed_entries[0].meta['id'], 'abc123')

    def test_close_directive(self):
        """Test inference on Close directives."""
        close_entry = data.Close(meta=dict(self.meta),
                                 date=self.date,
                                 account='Assets:Bank:Checking')

        entries = [close_entry]
        config = "close name __account__"
        options_map = self._create_options_map()

        transformed_entries, errors = infer_metadata.infer_metadata(
            entries, options_map, config)

        self.assertEqual(len(errors), 0)
        self.assertEqual(transformed_entries[0].meta['name'], 'Checking')

    def test_pad_directive(self):
        """Test inference on Pad directives."""
        pad_entry = data.Pad(meta=dict(self.meta),
                             date=self.date,
                             account='Assets:Bank:Checking',
                             source_account='Equity:Opening')

        entries = [pad_entry]
        config = "pad name __account__"
        options_map = self._create_options_map()

        transformed_entries, errors = infer_metadata.infer_metadata(
            entries, options_map, config)

        self.assertEqual(len(errors), 0)
        self.assertEqual(transformed_entries[0].meta['name'], 'Checking')

    def test_document_directive(self):
        """Test inference on Document directives."""
        document = data.Document(meta=dict(self.meta),
                                 date=self.date,
                                 account='Assets:Bank:Checking',
                                 filename='/path/to/doc.pdf',
                                 tags=None,
                                 links=None)

        entries = [document]
        config = "document name __account__"
        options_map = self._create_options_map()

        transformed_entries, errors = infer_metadata.infer_metadata(
            entries, options_map, config)

        self.assertEqual(len(errors), 0)
        self.assertEqual(transformed_entries[0].meta['name'], 'Checking')

    def test_file_not_found_error(self):
        """Test error when mapping file is not found."""
        open_entry = data.Open(meta=dict(self.meta, account_class='stocks'),
                               date=self.date,
                               account='Assets:Investments',
                               currencies=None,
                               booking=None)

        entries = [open_entry]
        config = "open volatility account_class file:nonexistent.yaml"
        options_map = self._create_options_map()

        transformed_entries, errors = infer_metadata.infer_metadata(
            entries, options_map, config)

        self.assertEqual(len(errors), 1)
        self.assertIn('not found', errors[0].message)
        self.assertIn('nonexistent.yaml', errors[0].message)

    def test_invalid_yaml_error(self):
        """Test error when YAML file is invalid."""
        # Create invalid YAML file
        mapping_path = os.path.join(self.test_dir, 'invalid.yaml')
        with open(mapping_path, 'w') as f:
            f.write('invalid: yaml: content:\n')
            f.write('  bad indentation\n')

        open_entry = data.Open(meta=dict(self.meta, account_class='stocks'),
                               date=self.date,
                               account='Assets:Investments',
                               currencies=None,
                               booking=None)

        entries = [open_entry]
        config = "open volatility account_class file:invalid.yaml"
        options_map = self._create_options_map()

        transformed_entries, errors = infer_metadata.infer_metadata(
            entries, options_map, config)

        self.assertEqual(len(errors), 1)
        self.assertIn('Error parsing YAML', errors[0].message)

    def test_complex_workflow(self):
        """Test complex workflow with multiple directive types and rules."""
        # Create mapping file
        mapping_path = os.path.join(self.test_dir, 'asset_type.yaml')
        with open(mapping_path, 'w') as f:
            f.write('Checking: cash\n')
            f.write('Savings: cash\n')
            f.write('Investments: securities\n')

        commodity = data.Commodity(meta=dict(self.meta),
                                   date=self.date,
                                   currency='USD')

        open_entry = data.Open(meta=dict(self.meta),
                               date=self.date,
                               account='Assets:Bank:Checking',
                               currencies=None,
                               booking=None)

        transaction = data.Transaction(meta=dict(self.meta, ref='tx001'),
                                       date=self.date,
                                       flag='*',
                                       payee='Store',
                                       narration='Purchase',
                                       tags=frozenset(),
                                       links=frozenset(),
                                       postings=[])

        entries = [commodity, open_entry, transaction]
        config = """
            ; Commodity rules
            commodity unit __commodity__
            ; Open rules
            open short_name __account__
            open type short_name file:asset_type.yaml
            ; Transaction rules
            transaction id ref
        """
        options_map = self._create_options_map()

        transformed_entries, errors = infer_metadata.infer_metadata(
            entries, options_map, config)

        self.assertEqual(len(errors), 0)

        # Check commodity
        self.assertEqual(transformed_entries[0].meta['unit'], 'USD')

        # Check open
        self.assertEqual(transformed_entries[1].meta['short_name'], 'Checking')
        self.assertEqual(transformed_entries[1].meta['type'], 'cash')

        # Check transaction
        self.assertEqual(transformed_entries[2].meta['id'], 'tx001')


if __name__ == '__main__':
    unittest.main()
