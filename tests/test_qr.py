"""The QR codes the PS3 app draws.

A wrong QR code is the worst kind of wrong: it still looks like a QR code, it still has its three
eyes and its quiet zone, and it is simply unreadable - or worse, readable and pointing somewhere
else. Nothing in a build catches that, and neither does looking at it.

So the generator is held to two things it cannot fake. First it has to REPRODUCE the code that was
already in the tree, module for module, from the URL that header documents - that pins the layout,
the masking, the error correction and the padding all at once. Second, every code it makes is read
back with an independent path through the same data and has to yield the URL that went in.

Both mistakes this found were of the silent kind: pad bytes that were all 0xEC because the loop read
a length that was growing underneath it, and a format-information copy two modules short.

Run: cd <project> && PYTHONPATH=src python3 -m unittest tests.test_qr -v
"""

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location("make_qr", ROOT / "tools" / "make-qr.py")
qr = importlib.util.module_from_spec(_spec)
_argv, sys.argv = sys.argv, ["make-qr.py"]
_spec.loader.exec_module(qr)
sys.argv = _argv

from teecellstream import URL_DONATE, URL_RELEASES   # noqa: E402

# what the header in the tree was made from, and the only external truth available here
OLD_RELEASE_URL = "https://github.com/TheErsysEnding/TEE-Cell-Stream-Server-Linux/releases/latest"

# total codewords per version - the sum every row of the table has to add up to
TOTAL_CODEWORDS = {1: 26, 2: 44, 3: 70, 4: 100, 5: 134, 6: 172, 7: 196, 8: 242, 9: 292,
                   10: 346, 11: 404, 12: 466, 13: 532, 14: 581, 15: 655}


def read_back(matrix, size, version):
    """Read a finished code the other way round: find its mask from the format bits, unmask, walk the
    data modules and decode the byte-mode payload. Deliberately not shared with the writer."""
    blank, _ = qr.new_matrix(version)
    qr.reserve(blank, size, version)
    reserved = [[cell is not None for cell in row] for row in blank]

    bits = "".join(str(matrix[8][i]) for i in range(6))
    bits += str(matrix[8][7]) + str(matrix[8][8]) + str(matrix[7][8])
    bits += "".join(str(matrix[14 - i][8]) for i in range(9, 15))
    mask = qr.FORMAT_M.index(int(bits, 2))

    plain = [[matrix[r][c] ^ (1 if not reserved[r][c] and qr.MASKS[mask](r, c) else 0)
              for c in range(size)] for r in range(size)]

    stream, upward, col = [], True, size - 1
    while col > 0:
        if col == 6:
            col -= 1
        for row in (range(size - 1, -1, -1) if upward else range(size)):
            for offset in (0, 1):
                if not reserved[row][col - offset]:
                    stream.append(plain[row][col - offset])
        upward = not upward
        col -= 2

    words = [int("".join(str(b) for b in stream[i:i + 8]), 2)
             for i in range(0, len(stream) // 8 * 8, 8)]
    data_words, _ec, group1, group2 = qr.VERSIONS_M[version]
    blocks = group1 + group2
    per_block = data_words // blocks
    columns = [[] for _ in range(blocks)]
    for index in range(per_block * blocks):
        columns[index % blocks].append(words[index])
    ordered = [word for block in columns for word in block]

    text = "".join(format(word, "08b") for word in ordered)
    count = int(text[4:12], 2) if version < 10 else int(text[4:20], 2)
    start = 12 if version < 10 else 20
    payload = bytes(int(text[start + i * 8:start + 8 + i * 8], 2) for i in range(count))
    return text[:4], payload.decode("utf-8"), mask


class GeneratorTests(unittest.TestCase):

    def test_it_reproduces_the_code_that_was_already_in_the_tree(self):
        """The one check with an outside witness: the header predates this generator entirely."""
        header = (ROOT / "ps3-src" / "apps" / "cell-stream" / "include" / "qr-code.h").read_text()
        self.assertIn(qr.URL_RELEASES.split("/releases")[0], header + OLD_RELEASE_URL)
        matrix, size, version, mask = qr.build(OLD_RELEASE_URL)
        # the current header is the NEW url, so the old one is rebuilt and compared against the
        # modules the tree carried before this generator existed - kept here as the reference
        self.assertEqual(37, size)
        self.assertEqual(5, version)
        self.assertEqual(6, mask)
        mine = [cell for row in matrix for cell in row]
        self.assertEqual(REFERENCE_MODULES, mine, "the generator no longer reproduces the known code")

    def test_every_code_it_makes_reads_back_as_what_went_in(self):
        for url in (URL_RELEASES, URL_DONATE, OLD_RELEASE_URL, "https://example.com/x"):
            with self.subTest(url=url):
                matrix, size, version, mask = qr.build(url)
                mode, text, found_mask = read_back(matrix, size, version)
                self.assertEqual("0100", mode, "byte mode")
                self.assertEqual(url, text)
                self.assertEqual(mask, found_mask)

    def test_the_version_table_adds_up(self):
        """Data codewords plus error-correction codewords must be the version's total. One row had
        four blocks where the standard has two, and every code it made was unreadable."""
        for version, (data, ec, group1, group2) in sorted(qr.VERSIONS_M.items()):
            with self.subTest(version=version):
                self.assertEqual(TOTAL_CODEWORDS[version], data + ec * (group1 + group2))

    def test_padding_alternates(self):
        """0xEC, 0x11, 0xEC, 0x11 - not 0xEC all the way down, which is what a length read inside the
        loop that was extending it produced."""
        words = qr.encode_data("https://example.com", 5)
        tail = words[len("https://example.com") + 2:]
        self.assertGreater(len(tail), 4)
        self.assertEqual([0xEC, 0x11, 0xEC, 0x11], tail[:4])

    def test_both_format_copies_are_written_whole(self):
        """The second copy carries eight modules horizontally and seven vertically. Two missing left
        a code that readers could still correct - so it worked, until it did not."""
        matrix, size, version, mask = qr.build(URL_DONATE)
        bits = format(qr.FORMAT_M[mask], "015b")
        for i in range(7, 15):
            self.assertEqual(int(bits[i]), matrix[8][size - 15 + i], "horizontal copy, bit %d" % i)
        for i in range(6):
            self.assertEqual(int(bits[i]), matrix[size - 1 - i][8], "vertical copy, bit %d" % i)
        self.assertEqual(1, matrix[size - 8][8], "the module that is always dark")

    def test_the_headers_in_the_tree_match_what_the_generator_makes_now(self):
        """A header edited by hand, or left behind after a link changed, is caught here."""
        include = ROOT / "ps3-src" / "apps" / "cell-stream" / "include"
        for name, url, path in (("QR", URL_RELEASES, include / "qr-code.h"),
                                ("QR_DONATE", URL_DONATE, include / "qr-donate.h")):
            with self.subTest(header=path.name):
                self.assertTrue(path.is_file(), "%s is missing" % path.name)
                text = path.read_text()
                self.assertIn(url, text, "the header does not name the url it was made from")
                numbers = [int(n) for n in text.split("{", 1)[1].split("}", 1)[0]
                           .replace("\n", "").split(",") if n.strip()]
                matrix, size, _version, _mask = qr.build(url)
                self.assertEqual([cell for row in matrix for cell in row], numbers)
                self.assertIn("#define %s_SIZE %d" % (name, size), text)


# The reference code, copied out of the tree before it was regenerated. It is the only thing in this
# file that did not come from the generator being tested, which is the whole point of it.
REFERENCE_MODULES = [
    1, 1, 1, 1, 1, 1, 1, 0, 1, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1,
    1, 0, 0, 0, 0, 0, 1, 0, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1,
    1, 0, 1, 1, 1, 0, 1, 0, 1, 1, 1, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 1, 0, 0, 0, 1, 1, 1, 0, 0, 1, 0, 1, 1, 1, 0, 1,
    1, 0, 1, 1, 1, 0, 1, 0, 0, 1, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 1, 0, 1, 1, 0, 1, 0, 1, 1, 1, 0, 1,
    1, 0, 1, 1, 1, 0, 1, 0, 1, 0, 0, 1, 1, 0, 1, 1, 0, 1, 0, 1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 0, 1, 0, 1, 1, 1, 0, 1,
    1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1, 1, 1, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 1,
    1, 1, 1, 1, 1, 1, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 1, 1, 1, 1, 1, 1,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0,
    1, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0, 1, 0, 1, 1, 0, 0, 1, 0, 1, 1, 1,
    0, 1, 1, 0, 1, 0, 0, 0, 1, 1, 1, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 1, 0,
    1, 0, 0, 0, 1, 0, 1, 1, 1, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 0, 1, 1, 0, 1, 1, 1, 0, 1, 1, 0, 1, 1, 0, 1, 0, 0, 1,
    0, 0, 1, 0, 1, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 1, 1, 1, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1,
    0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 1, 0, 1, 1, 1, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 1, 0, 0, 0, 0, 1,
    1, 1, 0, 1, 0, 1, 0, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 0, 1, 0, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 0, 0, 1, 1, 0, 1, 0,
    0, 0, 0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 1, 1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1,
    0, 0, 0, 1, 1, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 0,
    1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 1, 0, 0, 1, 1, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 1, 1, 1,
    1, 1, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0, 0, 1, 1, 1, 1, 0, 1, 0, 0, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 0, 0,
    0, 0, 0, 0, 0, 1, 1, 0, 1, 1, 0, 1, 1, 1, 0, 0, 1, 1, 0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 1, 0, 0, 1, 1, 0, 0, 1,
    0, 1, 1, 1, 1, 1, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 1, 0, 0, 1, 0, 0, 1,
    0, 0, 0, 1, 1, 0, 1, 0, 1, 1, 1, 0, 1, 0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 0, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0,
    1, 0, 0, 1, 1, 1, 0, 1, 0, 1, 0, 1, 1, 0, 0, 1, 0, 1, 1, 1, 0, 0, 1, 0, 0, 0, 1, 1, 0, 1, 0, 0, 1, 0, 1, 1, 1,
    1, 1, 0, 0, 0, 1, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 0, 1, 0, 0, 1,
    0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 1, 1, 1, 1, 0, 1,
    1, 1, 0, 0, 1, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 1, 0, 1, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0,
    1, 1, 1, 1, 0, 1, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 0, 0, 1, 1, 1, 0, 1, 1, 1, 0, 0, 0,
    1, 1, 0, 0, 0, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1, 1, 0, 0, 0, 1, 1, 1,
    1, 0, 0, 1, 1, 0, 0, 0, 0, 1, 1, 1, 0, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 1, 1, 0, 1, 1, 0, 0,
    1, 0, 0, 0, 0, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 1, 1, 1, 0, 1, 0, 0, 1, 1, 1, 1, 0, 0, 0, 1, 0, 1, 1, 0,
    1, 1, 1, 1, 1, 1, 1, 0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 1, 0, 1, 0, 1, 0, 0, 1, 1,
    1, 0, 0, 0, 0, 0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 1, 1, 1, 1, 1, 0, 0, 0, 1, 0, 0, 0, 1,
    1, 0, 1, 1, 1, 0, 1, 0, 1, 1, 1, 1, 1, 0, 1, 1, 1, 0, 1, 1, 0, 0, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0,
    1, 0, 1, 1, 1, 0, 1, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 1, 0, 1, 1, 1, 0, 0, 1, 0, 1, 1, 1, 0, 0, 0, 1, 0, 1,
    1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 1, 1, 1, 0, 0, 1, 0, 0, 0, 1,
    1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 0, 1, 0, 1, 0, 1, 1, 1, 0, 1, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 1, 0, 1, 0, 0, 1,
]
