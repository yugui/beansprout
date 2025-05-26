#!/usr/bin/env python3
"""Unit tests for the Tokenizer class."""

import unittest
from beansprout.importer.tokenizer import Tokenizer


class TokenizerTest(unittest.TestCase):
    """Test cases for the Tokenizer class."""

    def setUp(self):
        """Set up a Tokenizer instance for tests."""
        self.tokenizer = Tokenizer()

    def test_empty_text(self):
        """Test tokenization of empty text."""
        self.assertEqual(self.tokenizer.tokenize(""), [])
        self.assertEqual(self.tokenizer.tokenize(None), [])

    def test_latin_only(self):
        """Test tokenization of text with only Latin characters."""
        # Simple words
        self.assertEqual(self.tokenizer.tokenize("hello world"),
                         ["hello", "world"])

        # With numbers
        self.assertEqual(self.tokenizer.tokenize("test123 456test"),
                         ["test123", "456test"])

        # With punctuation
        self.assertEqual(self.tokenizer.tokenize("hello, world! How are you?"),
                         ["hello", "world", "how", "are", "you"])

    def test_japanese_only(self):
        """Test tokenization of text with only Japanese characters."""
        # Hiragana
        hiragana = "こんにちは"
        expected_hiragana = ["こん", "んに", "にち", "ちは"]
        self.assertEqual(self.tokenizer.tokenize(hiragana), expected_hiragana)

        # Katakana
        katakana = "テスト"
        expected_katakana = ["テス", "スト"]
        self.assertEqual(self.tokenizer.tokenize(katakana), expected_katakana)

        # Kanji
        kanji = "東京"
        expected_kanji = ["東京"]
        self.assertEqual(self.tokenizer.tokenize(kanji), expected_kanji)

        # Mixed Japanese scripts
        mixed_jp = "東京テストこんにちは"
        expected_mixed_jp = [
            "東京", "京テ", "テス", "スト", "トこ", "こん", "んに", "にち", "ちは"
        ]
        self.assertEqual(self.tokenizer.tokenize(mixed_jp), expected_mixed_jp)

    def test_mixed_scripts(self):
        """Test tokenization of text with mixed Latin and Japanese characters."""
        # Latin followed by Japanese
        text1 = "hello東京"
        expected1 = ["hello", "東京"]
        self.assertEqual(self.tokenizer.tokenize(text1), expected1)

        # Japanese followed by Latin
        text2 = "東京hello"
        expected2 = ["東京", "hello"]
        self.assertEqual(self.tokenizer.tokenize(text2), expected2)

        # Alternating scripts
        text3 = "hello東京world"
        expected3 = ["hello", "東京", "world"]
        self.assertEqual(self.tokenizer.tokenize(text3), expected3)

        # Complex mixed text
        text4 = "2023年5月4日 Tokyo Trip 旅行"
        expected4 = ["2023", "年", "5", "月", "4", "日", "tokyo", "trip", "旅行"]
        self.assertEqual(self.tokenizer.tokenize(text4), expected4)

    def test_edge_cases(self):
        """Test tokenization of edge cases."""
        # Single Japanese character
        self.assertEqual(self.tokenizer.tokenize("東"), ["東"])

        # Single Latin character (should be filtered out as it's not a word)
        self.assertEqual(self.tokenizer.tokenize("a"), ["a"])

        # Numbers only
        self.assertEqual(self.tokenizer.tokenize("12345"), ["12345"])

        # Punctuation only (should result in empty list as they're not words)
        self.assertEqual(self.tokenizer.tokenize("!@#$%"), [])

        # Mixed case (should be lowercased)
        self.assertEqual(self.tokenizer.tokenize("HeLLo"), ["hello"])

    def test_special_cases(self):
        """Test tokenization of special cases."""
        # Japanese with numbers
        text1 = "価格1000円"
        expected1 = ["価格", "1000", "円"]
        self.assertEqual(self.tokenizer.tokenize(text1), expected1)

        # Japanese with punctuation
        text2 = "こんにちは！世界。"
        expected2 = ["こん", "んに", "にち", "ちは", "世界"]
        self.assertEqual(self.tokenizer.tokenize(text2), expected2)

        # Latin with Japanese punctuation
        text3 = "hello　world"  # Contains Japanese full-width space
        expected3 = ["hello", "world"]
        self.assertEqual(self.tokenizer.tokenize(text3), expected3)


if __name__ == "__main__":
    unittest.main()
