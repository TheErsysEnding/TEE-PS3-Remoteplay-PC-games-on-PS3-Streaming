"""Rules both windows share (ui_text.py): the NVENC switches are offered only where they can do something."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from teecellstream.ui_text import (DEBLOCK_HINTS, DEBLOCK_UNAVAILABLE_HINT, NVENC_MISSING_HINT,   # noqa: E402
                                   nvenc_switch_hint)


class _Encoder:
    def __init__(self, kind):
        self.kind = kind


class _Server:
    def __init__(self, kinds, able):
        self.available_encoders = [_Encoder(kind) for kind in kinds]
        self.nvenc_can_skip_deblocking = able


class NvencSwitchTests(unittest.TestCase):
    def test_an_amd_pc_with_the_bundled_ffmpeg_gets_no_switch(self):
        # the bundled ffmpeg knows -dblk_idc everywhere; without an NVIDIA card it changes nothing
        self.assertEqual((False, NVENC_MISSING_HINT),
                         nvenc_switch_hint(_Server(["amf", "x264"], True), "nvenc_can_skip_deblocking",
                                           DEBLOCK_HINTS, 1, DEBLOCK_UNAVAILABLE_HINT))

    def test_nvidia_with_a_stock_ffmpeg_says_what_is_missing(self):
        self.assertEqual((False, DEBLOCK_UNAVAILABLE_HINT),
                         nvenc_switch_hint(_Server(["nvenc", "x264"], False), "nvenc_can_skip_deblocking",
                                           DEBLOCK_HINTS, 1, DEBLOCK_UNAVAILABLE_HINT))

    def test_nvidia_with_the_bundled_ffmpeg_explains_the_choice(self):
        self.assertEqual((True, DEBLOCK_HINTS[1]),
                         nvenc_switch_hint(_Server(["nvenc", "x264"], True), "nvenc_can_skip_deblocking",
                                           DEBLOCK_HINTS, 1, DEBLOCK_UNAVAILABLE_HINT))


if __name__ == "__main__":
    unittest.main()
