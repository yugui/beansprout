"""File rewriter for preserving text representation when rewriting files.

This module provides the FileRewriter class that handles the rewriting of files
with text preservation, including preserving comments, free text, and formatting.
It uses the TextPreservingParser to parse existing files and delegates the
transformation of blocks to a callback.
"""

import os
from typing import Callable, List

from beansprout.writer.text_preserving_parser import parse_file
from beansprout.writer.types import Block


class FileRewriter:
    """Class responsible for rewriting files with text preservation.
    
    This class handles the rewriting of files with text preservation, including
    preserving comments, free text, and formatting. It uses the TextPreservingParser
    to parse existing files and delegates the transformation of blocks to a callback.
    """

    def __init__(self, quiet: int = 0) -> None:
        """Initialize the FileRewriter.
        
        Args:
            quiet: Level of output suppression (0 for normal output, higher for less output).
        """
        self.quiet = quiet

    def rewrite_file(self,
                     dest_file: str,
                     transform_blocks: Callable[[List[Block]], List[Block]],
                     dry_run: bool = False) -> None:
        """Rewrite a file with transformed blocks, preserving text representation.
        
        Args:
            dest_file: The destination file to write to.
            transform_blocks: A callback function that takes a list of existing blocks
                             and returns a transformed list of blocks.
            dry_run: Whether to perform a dry run without writing files.
        """
        # Parse the existing file to get blocks
        existing_blocks = self._parse_file(dest_file)

        # Apply the transformation to get the new blocks
        transformed_blocks = transform_blocks(existing_blocks)

        # Write the file with preservation
        if not dry_run:
            self._write_file_with_preservation(dest_file, transformed_blocks)

    def _parse_file(self, file_path: str) -> List[Block]:
        """Parse a file and return its blocks.
        
        Args:
            file_path: The path to the file to parse.
            
        Returns:
            A list of Block objects representing the parsed file content.
        """
        return parse_file(file_path)

    def _write_file_with_preservation(self, file_path: str,
                                      blocks: List[Block]) -> None:
        """Write a file with text preservation.
        
        Args:
            file_path: The path to the file to write to.
            blocks: List of Block objects to write to the file.
        """
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w') as f:
            for block in blocks:
                f.write(str(block))
