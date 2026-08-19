from __future__ import annotations

import unittest

from bot.timecode import TimecodeError, format_timecode, parse_timecode


class ParseTimecodeTests(unittest.TestCase):
    def test_minute_only(self):
        self.assertEqual(parse_timecode("1"), 60_000)

    def test_minute_second(self):
        self.assertEqual(parse_timecode("1:23"), 83_000)

    def test_minute_second_ms(self):
        self.assertEqual(parse_timecode("1:23:500"), 83_500)

    def test_zero(self):
        self.assertEqual(parse_timecode("0"), 0)

    def test_strips_whitespace(self):
        self.assertEqual(parse_timecode("  1:02  "), 62_000)

    def test_large_minutes_allowed(self):
        # No hour field by design; large minute counts (>59) are fine.
        self.assertEqual(parse_timecode("125:30"), 125 * 60_000 + 30_000)

    def test_empty_raises(self):
        with self.assertRaises(TimecodeError):
            parse_timecode("")

    def test_too_many_parts_raises(self):
        with self.assertRaises(TimecodeError):
            parse_timecode("1:2:3:4")

    def test_non_digit_raises(self):
        with self.assertRaises(TimecodeError):
            parse_timecode("a:b")

    def test_second_out_of_range_raises(self):
        with self.assertRaises(TimecodeError):
            parse_timecode("1:60")

    def test_ms_out_of_range_raises(self):
        with self.assertRaises(TimecodeError):
            parse_timecode("1:23:1000")

    def test_negative_raises(self):
        with self.assertRaises(TimecodeError):
            parse_timecode("-1:00")


class FormatTimecodeTests(unittest.TestCase):
    def test_no_ms(self):
        self.assertEqual(format_timecode(83_000), "01:23")

    def test_with_ms(self):
        self.assertEqual(format_timecode(83_500), "01:23.500")

    def test_negative_clamped_to_zero(self):
        self.assertEqual(format_timecode(-100), "00:00")

    def test_roundtrip(self):
        ms = parse_timecode("12:34:567")
        self.assertEqual(format_timecode(ms), "12:34.567")


if __name__ == "__main__":
    unittest.main()
