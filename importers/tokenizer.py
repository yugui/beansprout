"""Tokenizer for text processing in Beancount importers.

This module provides a Tokenizer class that handles text tokenization with special
handling for Japanese characters.
"""

import re
from typing import List, Optional


class Tokenizer:
    """A tokenizer that handles mixed scripts with special handling for Japanese text.
    
    This tokenizer implements the following rules:
    1. Split tokens at the boundaries between Japanese and non-Japanese characters
    2. Split consecutive Japanese characters into character-wise bigrams
    3. Split non-Japanese text at non-alphanumeric characters
    """

    # Define Japanese character ranges
    # Hiragana: \u3040-\u309F
    # Katakana: \u30A0-\u30FF
    # CJK Unified Ideographs (Kanji): \u4E00-\u9FFF
    # Half-width Katakana: \uFF65-\uFF9F
    _JAPANESE_CHAR_PATTERN = r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uFF65-\uFF9F]'
    _NON_JAPANESE_CHAR_PATTERN = r'[^\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uFF65-\uFF9F]'
    JAPANESE_BOUNDARY_PATTERN = r'(?<={ja})(?={non_ja})|(?<={non_ja})(?={ja})'.format(
        ja=_JAPANESE_CHAR_PATTERN, non_ja=_NON_JAPANESE_CHAR_PATTERN)

    def tokenize(self, text: Optional[str]) -> List[str]:
        """Convert text to a list of tokens.
        
        Args:
            text: The text to tokenize.
            
        Returns:
            A list of tokens.
        """
        if not text:
            return []

        text = text.lower()
        chunks = re.split(self.JAPANESE_BOUNDARY_PATTERN, text)

        tokens = []
        for chunk in chunks:
            if re.search(self._JAPANESE_CHAR_PATTERN, chunk):
                # Split Japanese text into character-wise bigrams
                tokens.extend(self._split_japanese(chunk))
            else:
                # Split non-Japanese text at non-alphanumeric characters
                tokens.extend(self._split_non_japanese(chunk))

        return tokens

    def _split_japanese(self, text: str) -> List[str]:
        """Split Japanese text into character-wise bigrams."""
        if len(text) < 2:
            return [text]
        # Split the text into characters
        chars = list(text)
        # Create bigrams
        bigrams = [chars[i:i + 2] for i in range(len(chars) - 1)]
        # Join bigrams into strings
        return [''.join(bigram) for bigram in bigrams]

    def _split_non_japanese(self, text: str) -> List[str]:
        """Split non-Japanese text at non-alphanumeric characters."""
        seq = re.split(r'[^a-zA-Z0-9]+', text)
        return [s for s in seq if s]
