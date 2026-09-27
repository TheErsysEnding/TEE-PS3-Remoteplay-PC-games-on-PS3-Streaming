"""MPEG-2 as a test codec: the splitter, the command line, and who is allowed to get it."""

import os
import random
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from teecellstream import encoders, protocol   # noqa: E402
from teecellstream.stream_sender import Mpeg2Splitter   # noqa: E402

FFMPEG = shutil.which("ffmpeg")


def _split(data: bytes, chunk=None, seed=7):
    splitter, units, rng, pos = Mpeg2Splitter(), [], random.Random(seed), 0
    while pos < len(data):
        n = len(data) if chunk is None else rng.randint(1, chunk)
        splitter.push(data[pos:pos + n])
        pos += n
        while (unit := splitter.take_access_unit()) is not None:
            units.append(unit)
    while (unit := splitter.flush()) is not None:
        units.append(unit)
    return units


def _picture(coding_type: int) -> bytes:
    """A picture header with the given picture_coding_type and one slice behind it."""
    return (b"\x00\x00\x01\x00" + bytes([0x00, (coding_type << 3) & 0x38, 0xFF, 0xF8])
            + b"\x00\x00\x01\xb5\x8f\xff\xf3\x41\x80" + b"\x00\x00\x01\x01\x12\x34\x56")


class Mpeg2SplitterTests(unittest.TestCase):

    def test_synthetic_gop(self):
        # I-picture with sequence header, extension and GOP header in front, then two P-pictures
        stream = (b"\x00\x00\x01\xb3\x78\x04\x38\x35\xff\xff\xe0\x18" + b"\x00\x00\x01\xb5\x14\x8a\x00\x01\x00\x00"
                  + b"\x00\x00\x01\xb8\x00\x08\x00\x40" + _picture(1) + _picture(2) + _picture(2))
        units = _split(stream)
        self.assertEqual([True, False, False], [keyframe for _, keyframe in units])
        self.assertTrue(units[0][0].startswith(b"\x00\x00\x01\xb3"), "headers belong to the I-picture's unit")
        self.assertEqual(stream, b"".join(data for data, _ in units))

    def test_extension_behind_a_picture_does_not_split(self):
        units = _split(_picture(1) + _picture(2))
        self.assertEqual(2, len(units))

    def test_sequence_end_belongs_to_no_picture(self):
        units = _split(_picture(1) + _picture(2) + b"\x00\x00\x01\xb7")
        self.assertEqual(2, len(units))

    @unittest.skipUnless(FFMPEG, "ffmpeg wird gebraucht")
    def test_a_real_stream_in_random_pieces(self):
        data = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                               "testsrc2=size=640x360:rate=60", "-frames:v", "90", "-c:v", "mpeg2video", "-bf", "0",
                               "-g", "30", "-flags", "+low_delay", "-f", "mpeg2video", "-"],
                              capture_output=True, check=True).stdout
        for chunk in (None, 997, 7):
            units = _split(data, chunk)
            self.assertEqual(90, len(units), chunk)
            self.assertEqual([0, 30, 60], [i for i, (_, keyframe) in enumerate(units) if keyframe], chunk)
            self.assertEqual(data, b"".join(unit for unit, _ in units), chunk)


class Mpeg2CommandLineTests(unittest.TestCase):
    INPUT = ["-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", "1280x720", "-r", "60", "-i", "pipe:0"]

    def _args(self, **kw):
        return encoders.build_ffmpeg_args("ffmpeg", encoders.MPEG2, self.INPUT, 1280, 720, 60, 20000, "keyframe",
                                          False, **kw)

    def test_shape(self):
        args = self._args()
        self.assertIn("mpeg2video", args)
        self.assertEqual(["-f", "mpeg2video", "-flush_packets", "1", "pipe:1"], args[-5:])
        self.assertEqual("30", args[args.index("-g") + 1], "keyframes twice a second, as for H.264 keyframe mode")
        self.assertIn("+low_delay", args)

    def test_no_h264_options_leak_in(self):
        args = self._args(entropy_coder="cabac", nvenc_deblocking_off=True, nvenc_whole_pixels=True,
                          rate_control="quality")
        for option in ("-coder", "-dblk_idc", "-mv_precision", "-crf", "-x264-params"):
            self.assertNotIn(option, args)

    def test_stock_mpeg2_never_intra_refresh(self):
        self.assertFalse(encoders.intra_refresh_enabled(encoders.MPEG2, "intra"))

    def test_not_a_rung(self):
        self.assertNotIn(encoders.MPEG2, encoders.LADDER)

    @unittest.skipUnless(FFMPEG, "ffmpeg wird gebraucht")
    def test_ffmpeg_takes_the_command_line(self):
        args = encoders.build_ffmpeg_args(FFMPEG, encoders.MPEG2,
                                          ["-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=60", "-frames:v", "20"],
                                          1280, 720, 60, 20000, "keyframe", False)
        result = subprocess.run(args, capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr.decode()[-400:])
        self.assertEqual(20, len(_split(result.stdout)))


PATCHED_FFMPEG = os.path.join(os.path.dirname(__file__), "..", "ffmpeg-nvenc", "install", "bin", "ffmpeg")
HAVE_PATCHED = os.access(PATCHED_FFMPEG, os.X_OK)


class Mpeg2IntraRefreshTests(unittest.TestCase):
    """Our ffmpeg patch: one I-picture, then a sweep of intra rows instead of keyframes."""
    INPUT = ["-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", "1280x720", "-r", "60", "-i", "pipe:0"]

    def _args(self, encoder, loss_recovery="intra"):
        return encoders.build_ffmpeg_args("ffmpeg", encoder, self.INPUT, 1280, 720, 60, 20000, loss_recovery, False)

    def test_refresh_encoder_announces_intra_refresh(self):
        self.assertTrue(encoders.intra_refresh_enabled(encoders.MPEG2_REFRESH, "intra"))
        self.assertFalse(encoders.intra_refresh_enabled(encoders.MPEG2_REFRESH, "keyframe"))

    def test_sweep_replaces_keyframes(self):
        args = self._args(encoders.MPEG2_REFRESH)
        self.assertEqual("60", args[args.index("-intra_refresh") + 1], "one sweep per REFRESH_SWEEP_SECONDS")
        self.assertEqual(str(protocol.ANCHOR_KEYFRAME_SECONDS * 60), args[args.index("-g") + 1])
        self.assertIn("-sc_threshold", args)

    def test_keyframe_mode_and_stock_encoder_leave_it_out(self):
        for args in (self._args(encoders.MPEG2_REFRESH, "keyframe"), self._args(encoders.MPEG2, "intra")):
            self.assertNotIn("-intra_refresh", args)
            self.assertEqual("30", args[args.index("-g") + 1])

    def test_stock_ffmpeg_gets_the_keyframe_encoder(self):
        if FFMPEG and b"-intra_refresh" not in subprocess.run([FFMPEG, "-hide_banner", "-h", "encoder=mpeg2video"],
                                                               capture_output=True).stdout:
            self.assertIs(encoders.MPEG2, encoders.mpeg2_encoder(FFMPEG))
        self.assertIs(encoders.MPEG2, encoders.mpeg2_encoder(""))

    @unittest.skipUnless(HAVE_PATCHED, "gepatchtes ffmpeg wird gebraucht")
    def test_patched_ffmpeg_sends_one_keyframe_and_heals(self):
        self.assertIs(encoders.MPEG2_REFRESH, encoders.mpeg2_encoder(PATCHED_FFMPEG))
        args = encoders.build_ffmpeg_args(PATCHED_FFMPEG, encoders.MPEG2_REFRESH,
                                          ["-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=60", "-frames:v", "150"],
                                          1280, 720, 60, 20000, "intra", False)
        data = subprocess.run(args, capture_output=True, check=True).stdout
        units = _split(data)
        self.assertEqual(150, len(units))
        self.assertEqual([0], [i for i, (_, keyframe) in enumerate(units) if keyframe])
        # drop picture 40, decode both, and the damage must be gone one sweep (60 pictures) later
        broken = b"".join(unit for i, (unit, _) in enumerate(units) if i != 40)

        def decode(stream):
            return subprocess.run([PATCHED_FFMPEG, "-v", "quiet", "-f", "mpegvideo", "-i", "-", "-f", "rawvideo",
                                   "-pix_fmt", "yuv420p", "-"], input=stream, capture_output=True, check=True).stdout
        size = 1280 * 720 * 3 // 2
        clean, damaged = decode(data), decode(broken)
        picture = lambda raw, i: raw[i * size:(i + 1) * size]
        self.assertNotEqual(picture(clean, 45), picture(damaged, 44), "the drop must have done damage")
        for i in range(41 + 2 * 60, 149):
            self.assertEqual(picture(clean, i + 1), picture(damaged, i), "picture %d still damaged" % i)


class CapabilityTests(unittest.TestCase):

    def test_plain_play_asks_for_nothing(self):
        self.assertEqual(set(), protocol.play_capabilities("PLAY"))

    def test_the_new_app_asks_for_mpeg2(self):
        self.assertIn(protocol.PLAY_CAPABILITY_MPEG2, protocol.play_capabilities("PLAY mpeg2"))

    def test_other_packets_carry_no_capabilities(self):
        self.assertEqual(set(), protocol.play_capabilities("PLAYER mpeg2"))
        self.assertEqual(set(), protocol.play_capabilities("STOP mpeg2"))
        self.assertEqual(set(), protocol.play_capabilities(""))


if __name__ == "__main__":
    unittest.main()


class Mpeg2PaddingTests(unittest.TestCase):
    """1080 rows become 1088, so the console never has to guess where the colour planes begin."""

    def _vf(self, width, height, needs_scale=False):
        args = encoders.build_ffmpeg_args("ffmpeg", encoders.MPEG2, ["-i", "pipe:0"], width, height, 60, 20000,
                                          "keyframe", needs_scale)
        return args[args.index("-vf") + 1] if "-vf" in args else None

    def test_1080_is_padded_to_1088(self):
        self.assertEqual("pad=1920:1088:0:0:black", self._vf(1920, 1080))

    def test_sizes_that_divide_by_16_stay_as_they_are(self):
        for width, height in ((1280, 720), (1536, 864), (1792, 1008), (960, 544)):
            self.assertIsNone(self._vf(width, height), (width, height))

    def test_scaling_comes_before_the_padding(self):
        vf = self._vf(1920, 1080, needs_scale=True)
        self.assertTrue(vf.startswith("scale=1920:1080"), vf)
        self.assertTrue(vf.endswith("pad=1920:1088:0:0:black"), vf)

    @unittest.skipUnless(FFMPEG, "ffmpeg wird gebraucht")
    def test_the_stream_really_is_1088(self):
        args = encoders.build_ffmpeg_args(FFMPEG, encoders.MPEG2,
                                          ["-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=60", "-frames:v", "5"],
                                          1920, 1080, 60, 20000, "keyframe", False)
        data = subprocess.run(args, capture_output=True, check=True).stdout
        header = data[data.find(b"\x00\x00\x01\xb3") + 4:]
        self.assertEqual((1920, 1088), ((header[0] << 4) | (header[1] >> 4), ((header[1] & 0x0F) << 8) | header[2]))


class PaceParseTests(unittest.TestCase):
    def test_a_real_report(self):
        period, error = protocol.parse_pace("PACE 16683350 -1234")
        self.assertAlmostEqual(1001 / 60000, period, places=6)
        self.assertAlmostEqual(-0.001234, error)

    def test_nonsense_is_refused(self):
        for text in ("PACE", "PACE 16683350", "PACE x 1", "PACE 100 0", "PACE 16683350 20000", "PACEX 16683350 0"):
            self.assertIsNone(protocol.parse_pace(text), text)
