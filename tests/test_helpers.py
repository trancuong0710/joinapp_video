"""
Unit tests for helper utilities.
"""
import unittest
from src.utils.file_helpers import sanitize_filename


class TestFileHelpers(unittest.TestCase):
    def test_sanitize_filename(self):
        dirty = 'Video: "Best Moments" <2026> / 4K? *Part 1* | OK.mp4'
        clean = sanitize_filename(dirty)
        self.assertEqual(clean, "Video Best Moments 2026 4K Part 1 OK.mp4")

    def test_sanitize_filename_max_len(self):
        long_name = "a" * 200
        clean = sanitize_filename(long_name, max_len=50)
        self.assertEqual(len(clean), 50)


if __name__ == "__main__":
    unittest.main()
