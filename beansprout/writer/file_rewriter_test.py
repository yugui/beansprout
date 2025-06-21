#!/usr/bin/env python3
"""Unit tests for the file_rewriter module."""

import os
import tempfile
import unittest
from unittest import mock

from beansprout.writer.file_rewriter import FileRewriter
from beansprout.writer.types import Block, NonEntryBlock, BlockType


class TestFileRewriter(unittest.TestCase):
    """Test the FileRewriter class."""

    def setUp(self):
        """Set up the test environment."""
        # Create a temporary directory for test files
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = self.temp_dir.name

        # Create a test file
        self.test_file = os.path.join(self.test_dir, "test_file.txt")
        with open(self.test_file, "w") as f:
            f.write("Line 1\nLine 2\nLine 3\n")

    def tearDown(self):
        """Clean up after the test."""
        self.temp_dir.cleanup()

    def test_basic_rewrite(self):
        """Test basic file rewriting functionality."""
        # Create a FileRewriter instance
        rewriter = FileRewriter(quiet=0)

        # Define a simple transformation function
        def transform_blocks(blocks):
            # Add a new block at the end
            blocks.append(
                NonEntryBlock(start_line=len(blocks),
                              original_lines=["Line 4\n"],
                              type=BlockType.FREE_TEXT))
            return blocks

        # Rewrite the file
        rewriter.rewrite_file(dest_file=self.test_file,
                              transform_blocks=transform_blocks,
                              dry_run=False)

        # Check that the file was rewritten correctly
        with open(self.test_file, "r") as f:
            content = f.read()

        self.assertEqual(content, "Line 1\nLine 2\nLine 3\nLine 4\n")

    def test_transform_blocks(self):
        """Test that the transform_blocks callback is called with the correct arguments."""
        # Create a FileRewriter instance
        rewriter = FileRewriter(quiet=0)

        # Create a mock transform_blocks function
        mock_transform = mock.Mock()
        mock_transform.return_value = []  # Return an empty list of blocks

        # Rewrite the file
        rewriter.rewrite_file(
            dest_file=self.test_file,
            transform_blocks=mock_transform,
            dry_run=True  # Use dry_run to avoid actually writing the file
        )

        # Check that the transform_blocks function was called
        mock_transform.assert_called_once()

        # Check that the transform_blocks function was called with a list of blocks
        args, _ = mock_transform.call_args
        self.assertIsInstance(args[0], list)
        self.assertTrue(all(isinstance(block, Block) for block in args[0]))

    def test_dry_run_mode(self):
        """Test that dry run mode works correctly."""
        # Create a FileRewriter instance
        rewriter = FileRewriter(quiet=0)

        # Define a simple transformation function
        def transform_blocks(blocks):
            # Add a new block at the end
            blocks.append(
                NonEntryBlock(start_line=len(blocks),
                              original_lines=["Line 4\n"],
                              type=BlockType.FREE_TEXT))
            return blocks

        # Save the original content
        with open(self.test_file, "r") as f:
            original_content = f.read()

        # Rewrite the file in dry run mode
        rewriter.rewrite_file(dest_file=self.test_file,
                              transform_blocks=transform_blocks,
                              dry_run=True)

        # Check that the file was not modified
        with open(self.test_file, "r") as f:
            content = f.read()

        self.assertEqual(content, original_content)

    def test_quiet_mode(self):
        """Test that quiet mode suppresses output in dry run mode."""
        # Create a FileRewriter instance with quiet=1
        rewriter = FileRewriter(quiet=1)

        # Define a simple transformation function
        def transform_blocks(blocks):
            # Add a new block at the end
            blocks.append(
                NonEntryBlock(start_line=len(blocks),
                              original_lines=["Line 4\n"],
                              type=BlockType.FREE_TEXT))
            return blocks

        # Rewrite the file in dry run mode with quiet=1
        rewriter.rewrite_file(dest_file=self.test_file,
                              transform_blocks=transform_blocks,
                              dry_run=True)

    def test_create_directory(self):
        """Test that directories are created if they don't exist."""
        # Create a FileRewriter instance
        rewriter = FileRewriter(quiet=0)

        # Define a simple transformation function
        def transform_blocks(blocks):
            return blocks

        # Create a file path in a non-existent directory
        new_dir = os.path.join(self.test_dir, "new_dir")
        new_file = os.path.join(new_dir, "new_file.txt")

        # Rewrite the file
        rewriter.rewrite_file(dest_file=new_file,
                              transform_blocks=transform_blocks,
                              dry_run=False)

        # Check that the directory was created
        self.assertTrue(os.path.exists(new_dir))
        # Check that the file was created
        self.assertTrue(os.path.exists(new_file))

    def test_empty_file(self):
        """Test rewriting an empty file."""
        # Create an empty file
        empty_file = os.path.join(self.test_dir, "empty_file.txt")
        with open(empty_file, "w") as f:
            pass

        # Create a FileRewriter instance
        rewriter = FileRewriter(quiet=0)

        # Define a simple transformation function
        def transform_blocks(blocks):
            # Add a new block
            blocks.append(
                NonEntryBlock(start_line=0,
                              original_lines=["New content\n"],
                              type=BlockType.FREE_TEXT))
            return blocks

        # Rewrite the file
        rewriter.rewrite_file(dest_file=empty_file,
                              transform_blocks=transform_blocks,
                              dry_run=False)

        # Check that the file was rewritten correctly
        with open(empty_file, "r") as f:
            content = f.read()

        self.assertEqual(content, "New content\n")

    def test_nonexistent_file(self):
        """Test rewriting a non-existent file."""
        # Create a FileRewriter instance
        rewriter = FileRewriter(quiet=0)

        # Define a simple transformation function
        def transform_blocks(blocks):
            # Add a new block
            blocks.append(
                NonEntryBlock(start_line=0,
                              original_lines=["New content\n"],
                              type=BlockType.FREE_TEXT))
            return blocks

        # Create a file path for a non-existent file
        nonexistent_file = os.path.join(self.test_dir, "nonexistent_file.txt")

        # Rewrite the file
        rewriter.rewrite_file(dest_file=nonexistent_file,
                              transform_blocks=transform_blocks,
                              dry_run=False)

        # Check that the file was created
        self.assertTrue(os.path.exists(nonexistent_file))

        # Check that the file was written correctly
        with open(nonexistent_file, "r") as f:
            content = f.read()

        self.assertEqual(content, "New content\n")


if __name__ == "__main__":
    unittest.main()
