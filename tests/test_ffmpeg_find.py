"""Which ffmpeg the server runs: the one the package ships, and the fallback when it cannot run here."""

import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
_TMP = tempfile.mkdtemp(prefix="tee-cst-ffmpegfind-")
os.environ.setdefault("TEE_CST_SETTINGS_PATH", os.path.join(_TMP, "settings.json"))
os.environ.setdefault("TEE_CST_LOG_PATH", os.path.join(_TMP, "server.log"))

from teecellstream import ffmpeg_find   # noqa: E402


def _script(path: str, exit_code: int) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write("#!/bin/sh\nexit %d\n" % exit_code)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)


@unittest.skipIf(ffmpeg_find.WINDOWS, "the Linux half")
class BundledLinuxTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="tee-cst-pkg-")
        self._saved = ffmpeg_find._executable_dir
        ffmpeg_find._executable_dir = lambda: self.root
        ffmpeg_find.forget()

    def tearDown(self):
        ffmpeg_find._executable_dir = self._saved
        ffmpeg_find.forget()

    def test_the_bundled_one_wins_when_it_runs(self):
        bundled = os.path.join(self.root, "ffmpeg", "ffmpeg")
        _script(bundled, 0)
        self.assertEqual(bundled, ffmpeg_find.find())

    def test_one_that_does_not_run_falls_back_to_path(self):
        _script(os.path.join(self.root, "ffmpeg", "ffmpeg"), 1)   # what a too-new glibc looks like from here
        self.assertNotEqual(os.path.join(self.root, "ffmpeg", "ffmpeg"), ffmpeg_find.find())

    def test_no_bundle_means_path(self):
        import shutil
        self.assertEqual(shutil.which("ffmpeg") or "ffmpeg", ffmpeg_find.find())

    def test_the_setting_still_overrides_everything(self):
        _script(os.path.join(self.root, "ffmpeg", "ffmpeg"), 0)
        chosen = os.path.join(self.root, "mine")
        _script(chosen, 0)
        self.assertEqual(chosen, ffmpeg_find.find(chosen))


if __name__ == "__main__":
    unittest.main()
