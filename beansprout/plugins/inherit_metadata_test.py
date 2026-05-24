#!/usr/bin/env python3
"""Tests for inherit_metadata plugin."""

import datetime
import unittest

from beancount.core import data

from beansprout.plugins import inherit_metadata


class InheritMetadataTest(unittest.TestCase):
    """Test cases for inherit_metadata plugin."""

    def setUp(self):
        """Set up test data."""
        self.maxDiff = None

        # Create test metadata
        self.meta = {'filename': 'test.beancount', 'lineno': 1}
        self.date = datetime.date(2020, 1, 1)

    def test_inherit_single_metadata_from_parent(self):
        """Test inheriting single metadata from parent."""
        parent_open = data.Open(meta=dict(self.meta, region='US'),
                                date=self.date,
                                account='Assets:Bank',
                                currencies=None,
                                booking=None)

        child_open = data.Open(meta=dict(self.meta),
                               date=self.date,
                               account='Assets:Bank:Checking',
                               currencies=None,
                               booking=None)

        entries = [parent_open, child_open]
        transformed_entries, errors = inherit_metadata.inherit_metadata(
            entries, {}, "region")

        self.assertEqual(len(errors), 0)
        self.assertEqual(len(transformed_entries), 2)

        # Parent should remain unchanged
        self.assertEqual(transformed_entries[0], parent_open)

        # Child should have inherited region
        transformed_child = transformed_entries[1]
        self.assertEqual(transformed_child.meta['region'], 'US')

    def test_inherit_multiple_metadata_from_parent(self):
        """Test inheriting multiple metadata from parent."""
        parent_open = data.Open(meta=dict(self.meta,
                                          region='US',
                                          tax_category='taxable'),
                                date=self.date,
                                account='Assets:Bank',
                                currencies=None,
                                booking=None)

        child_open = data.Open(meta=dict(self.meta),
                               date=self.date,
                               account='Assets:Bank:Checking',
                               currencies=None,
                               booking=None)

        entries = [parent_open, child_open]
        transformed_entries, errors = inherit_metadata.inherit_metadata(
            entries, {}, "region\ntax_category")

        self.assertEqual(len(errors), 0)

        # Child should have inherited both metadata
        transformed_child = transformed_entries[1]
        self.assertEqual(transformed_child.meta['region'], 'US')
        self.assertEqual(transformed_child.meta['tax_category'], 'taxable')

    def test_preserve_existing_metadata(self):
        """Test that existing metadata is not overwritten."""
        parent_open = data.Open(meta=dict(self.meta, region='US'),
                                date=self.date,
                                account='Assets:Bank',
                                currencies=None,
                                booking=None)

        child_open = data.Open(meta=dict(self.meta, region='JP'),
                               date=self.date,
                               account='Assets:Bank:Checking',
                               currencies=None,
                               booking=None)

        entries = [parent_open, child_open]
        transformed_entries, errors = inherit_metadata.inherit_metadata(
            entries, {}, "region")

        self.assertEqual(len(errors), 0)

        # Child should keep its own region value
        transformed_child = transformed_entries[1]
        self.assertEqual(transformed_child.meta['region'], 'JP')

    def test_inherit_from_grandparent(self):
        """Test inheriting metadata from grandparent when parent doesn't have it."""
        grandparent_open = data.Open(meta=dict(self.meta, region='US'),
                                     date=self.date,
                                     account='Assets',
                                     currencies=None,
                                     booking=None)

        parent_open = data.Open(meta=dict(self.meta),
                                date=self.date,
                                account='Assets:Bank',
                                currencies=None,
                                booking=None)

        child_open = data.Open(meta=dict(self.meta),
                               date=self.date,
                               account='Assets:Bank:Checking',
                               currencies=None,
                               booking=None)

        entries = [grandparent_open, parent_open, child_open]
        transformed_entries, errors = inherit_metadata.inherit_metadata(
            entries, {}, "region")

        self.assertEqual(len(errors), 0)

        # Both parent and child should inherit from grandparent
        transformed_parent = transformed_entries[1]
        self.assertEqual(transformed_parent.meta['region'], 'US')

        transformed_child = transformed_entries[2]
        self.assertEqual(transformed_child.meta['region'], 'US')

    def test_partial_inheritance(self):
        """Test partial inheritance where some metadata exists and some doesn't."""
        parent_open = data.Open(meta=dict(self.meta,
                                          region='US',
                                          tax_category='taxable'),
                                date=self.date,
                                account='Assets:Bank',
                                currencies=None,
                                booking=None)

        child_open = data.Open(meta=dict(self.meta, region='JP'),
                               date=self.date,
                               account='Assets:Bank:Checking',
                               currencies=None,
                               booking=None)

        entries = [parent_open, child_open]
        transformed_entries, errors = inherit_metadata.inherit_metadata(
            entries, {}, "region\ntax_category")

        self.assertEqual(len(errors), 0)

        # Child should keep its own region but inherit tax_category
        transformed_child = transformed_entries[1]
        self.assertEqual(transformed_child.meta['region'], 'JP')
        self.assertEqual(transformed_child.meta['tax_category'], 'taxable')

    def test_no_parent_with_metadata(self):
        """Test when account has no parent with metadata."""
        child_open = data.Open(meta=dict(self.meta),
                               date=self.date,
                               account='Assets:Bank:Checking',
                               currencies=None,
                               booking=None)

        entries = [child_open]
        transformed_entries, errors = inherit_metadata.inherit_metadata(
            entries, {}, "region")

        self.assertEqual(len(errors), 0)

        # Child should remain unchanged
        self.assertEqual(transformed_entries[0], child_open)

    def test_empty_config(self):
        """Test with empty configuration (no metadata names)."""
        parent_open = data.Open(meta=dict(self.meta, region='US'),
                                date=self.date,
                                account='Assets:Bank',
                                currencies=None,
                                booking=None)

        child_open = data.Open(meta=dict(self.meta),
                               date=self.date,
                               account='Assets:Bank:Checking',
                               currencies=None,
                               booking=None)

        entries = [parent_open, child_open]
        transformed_entries, errors = inherit_metadata.inherit_metadata(
            entries, {}, "")

        self.assertEqual(len(errors), 0)

        # Both should remain unchanged
        self.assertEqual(transformed_entries[0], parent_open)
        self.assertEqual(transformed_entries[1], child_open)

    def test_config_with_whitespace(self):
        """Test configuration parsing with extra whitespace."""
        parent_open = data.Open(meta=dict(self.meta,
                                          region='US',
                                          tax_category='taxable'),
                                date=self.date,
                                account='Assets:Bank',
                                currencies=None,
                                booking=None)

        child_open = data.Open(meta=dict(self.meta),
                               date=self.date,
                               account='Assets:Bank:Checking',
                               currencies=None,
                               booking=None)

        entries = [parent_open, child_open]
        transformed_entries, errors = inherit_metadata.inherit_metadata(
            entries, {}, "  region  \n  tax_category  ")

        self.assertEqual(len(errors), 0)

        # Child should have inherited both metadata despite whitespace
        transformed_child = transformed_entries[1]
        self.assertEqual(transformed_child.meta['region'], 'US')
        self.assertEqual(transformed_child.meta['tax_category'], 'taxable')

    def test_non_open_directives_unchanged(self):
        """Test that non-Open directives remain unchanged."""
        open_directive = data.Open(meta=dict(self.meta, region='US'),
                                   date=self.date,
                                   account='Assets:Bank',
                                   currencies=None,
                                   booking=None)

        transaction = data.Transaction(meta=self.meta,
                                       date=self.date,
                                       flag='*',
                                       payee='Store',
                                       narration='Purchase',
                                       tags=frozenset(),
                                       links=frozenset(),
                                       postings=[])

        note_directive = data.Note(meta=self.meta,
                                   date=self.date,
                                   account='Assets:Bank',
                                   comment='Test note',
                                   tags=None,
                                   links=None)

        entries = [open_directive, transaction, note_directive]
        transformed_entries, errors = inherit_metadata.inherit_metadata(
            entries, {}, "region")

        self.assertEqual(len(errors), 0)
        self.assertEqual(len(transformed_entries), 3)

        # Transaction and Note should remain unchanged
        self.assertEqual(transformed_entries[1], transaction)
        self.assertEqual(transformed_entries[2], note_directive)

    def test_closest_parent_wins(self):
        """Test that closest parent's metadata takes precedence."""
        root_open = data.Open(meta=dict(self.meta, region='US'),
                              date=self.date,
                              account='Assets',
                              currencies=None,
                              booking=None)

        parent_open = data.Open(meta=dict(self.meta, region='JP'),
                                date=self.date,
                                account='Assets:Bank',
                                currencies=None,
                                booking=None)

        child_open = data.Open(meta=dict(self.meta),
                               date=self.date,
                               account='Assets:Bank:Checking',
                               currencies=None,
                               booking=None)

        entries = [root_open, parent_open, child_open]
        transformed_entries, errors = inherit_metadata.inherit_metadata(
            entries, {}, "region")

        self.assertEqual(len(errors), 0)

        # Child should inherit from closest parent (JP, not US)
        transformed_child = transformed_entries[2]
        self.assertEqual(transformed_child.meta['region'], 'JP')

    def test_complex_hierarchy(self):
        """Test complex account hierarchy with multiple levels."""
        root_open = data.Open(meta=dict(self.meta,
                                        region='US',
                                        tax_category='taxable'),
                              date=self.date,
                              account='Assets',
                              currencies=None,
                              booking=None)

        level1_open = data.Open(meta=dict(self.meta, region='JP'),
                                date=self.date,
                                account='Assets:Bank',
                                currencies=None,
                                booking=None)

        level2_open = data.Open(meta=dict(self.meta),
                                date=self.date,
                                account='Assets:Bank:Savings',
                                currencies=None,
                                booking=None)

        level3_open = data.Open(meta=dict(self.meta),
                                date=self.date,
                                account='Assets:Bank:Savings:Emergency',
                                currencies=None,
                                booking=None)

        entries = [root_open, level1_open, level2_open, level3_open]
        transformed_entries, errors = inherit_metadata.inherit_metadata(
            entries, {}, "region\ntax_category")

        self.assertEqual(len(errors), 0)

        # Level 1 should inherit tax_category from root, keep its own region
        transformed_level1 = transformed_entries[1]
        self.assertEqual(transformed_level1.meta['region'], 'JP')
        self.assertEqual(transformed_level1.meta['tax_category'], 'taxable')

        # Level 2 should inherit region from level1, tax_category from root
        transformed_level2 = transformed_entries[2]
        self.assertEqual(transformed_level2.meta['region'], 'JP')
        self.assertEqual(transformed_level2.meta['tax_category'], 'taxable')

        # Level 3 should inherit both from parents
        transformed_level3 = transformed_entries[3]
        self.assertEqual(transformed_level3.meta['region'], 'JP')
        self.assertEqual(transformed_level3.meta['tax_category'], 'taxable')

    def test_metadata_not_in_config_not_inherited(self):
        """Test that metadata not specified in config is not inherited."""
        parent_open = data.Open(meta=dict(self.meta,
                                          region='US',
                                          tax_category='taxable',
                                          currency_type='fiat'),
                                date=self.date,
                                account='Assets:Bank',
                                currencies=None,
                                booking=None)

        child_open = data.Open(meta=dict(self.meta),
                               date=self.date,
                               account='Assets:Bank:Checking',
                               currencies=None,
                               booking=None)

        entries = [parent_open, child_open]
        transformed_entries, errors = inherit_metadata.inherit_metadata(
            entries, {}, "region\ntax_category")

        self.assertEqual(len(errors), 0)

        # Child should have inherited region and tax_category, but not currency_type
        transformed_child = transformed_entries[1]
        self.assertEqual(transformed_child.meta['region'], 'US')
        self.assertEqual(transformed_child.meta['tax_category'], 'taxable')
        self.assertNotIn('currency_type', transformed_child.meta)


if __name__ == '__main__':
    unittest.main()
