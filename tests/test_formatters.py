"""
Unit tests for formatting utilities.
"""
import unittest
from src.utils.formatters import (
    format_bytes,
    format_seconds,
    parse_time_str,
    format_time_hms,
    parse_fps,
)


class TestFormatters(unittest.TestCase):
    def test_format_bytes(self):
        self.assertEqual(format_bytes(500), "500 B")
        self.assertEqual(format_bytes(1024), "1.0 KB")
        self.assertEqual(format_bytes(1024 * 1024), "1.0 MB")
        self.assertEqual(format_bytes(1024 * 1024 * 1024), "1.00 GB")
        self.assertEqual(format_bytes(None), "N/A")
        self.assertEqual(format_bytes(-10), "N/A")
        self.assertEqual(format_bytes(None, fallback="Tự động tính"), "Tự động tính")
        self.assertEqual(format_bytes(0, fallback="Tự động tính"), "Tự động tính")
        self.assertEqual(format_bytes(0), "0 B")

    def test_format_seconds(self):
        self.assertEqual(format_seconds(0), "00:00")
        self.assertEqual(format_seconds(45), "00:45")
        self.assertEqual(format_seconds(65), "01:05")
        self.assertEqual(format_seconds(3665), "01:01:05")
        self.assertEqual(format_seconds(None), "N/A")
        self.assertEqual(format_seconds(None, fallback="--:--"), "--:--")

    def test_parse_time_str(self):
        self.assertEqual(parse_time_str("01:02:03"), 3723.0)
        self.assertEqual(parse_time_str("05:30"), 330.0)
        self.assertEqual(parse_time_str("12.5"), 12.5)
        self.assertEqual(parse_time_str(""), 0.0)
        self.assertEqual(parse_time_str("invalid"), 0.0)

    def test_format_time_hms(self):
        self.assertEqual(format_time_hms(3723.0), "01:02:03")
        self.assertEqual(format_time_hms(3723.4, include_subseconds=True), "01:02:03.4")
        self.assertEqual(format_time_hms(0.0), "00:00:00")

    def test_parse_fps(self):
        self.assertEqual(parse_fps("30"), 30.0)
        self.assertEqual(parse_fps("30000/1001"), 29.97)
        self.assertEqual(parse_fps("60/1"), 60.0)
        self.assertEqual(parse_fps("0/0"), 30.0)
        self.assertEqual(parse_fps(""), 30.0)


if __name__ == "__main__":
    unittest.main()

