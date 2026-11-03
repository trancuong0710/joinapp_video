"""
Unit tests for subtitle parsing and SRT generation.
"""
import unittest
from src.core.youtube.subtitles import parse_vtt_or_srt_to_cues, cues_to_srt


class TestSubtitles(unittest.TestCase):
    def test_parse_vtt(self):
        vtt_sample = """WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:03.500
Hello and welcome to this video.

00:00:04.200 --> 00:00:07.800
<c>Today we are going to learn</c> Python.
"""
        cues = parse_vtt_or_srt_to_cues(vtt_sample)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0]['start'], '00:00:01,000')
        self.assertEqual(cues[0]['end'], '00:00:03,500')
        self.assertEqual(cues[0]['text'], 'Hello and welcome to this video.')
        self.assertEqual(cues[1]['text'], 'Today we are going to learn Python.')

    def test_cues_to_srt(self):
        cues = [
            {'start': '00:00:01,000', 'end': '00:00:03,500', 'text': 'Xin chào các bạn.'},
            {'start': '00:00:04,000', 'end': '00:00:06,000', 'text': 'Chúc các bạn một ngày tốt lành.'}
        ]
        srt = cues_to_srt(cues)
        self.assertIn("1\n00:00:01,000 --> 00:00:03,500\nXin chào các bạn.", srt)
        self.assertIn("2\n00:00:04,000 --> 00:00:06,000\nChúc các bạn một ngày tốt lành.", srt)


if __name__ == "__main__":
    unittest.main()

