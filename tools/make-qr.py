#!/usr/bin/env python3
"""Writes the QR codes the PS3 app draws, as C headers.

There is no QR library on this machine and the previous generator is gone - it lived in a scratchpad
and went with it, leaving a header nobody could regenerate. So this is written out again, and the
thing that makes it trustworthy is that it has to REPRODUCE the header that is already in the tree,
module for module, before it is allowed to make a new one (tests/test_qr.py does exactly that).

Byte mode, error correction M, the smallest version that fits, and every mask tried with the
penalty rules from the specification - which is what decides a mask, rather than a guess.

    python3 tools/make-qr.py --check          reproduce the existing header and compare
    python3 tools/make-qr.py --write          write the headers the app includes
"""

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
from teecellstream import URL_DONATE, URL_RELEASES   # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent.parent
INCLUDE = HERE / "ps3-src" / "apps" / "cell-stream" / "include"

# ---------------------------------------------------------------- Galois field GF(256), x^8+x^4+x^3+x^2+1
EXP = [0] * 512
LOG = [0] * 256
_x = 1
for _i in range(255):
    EXP[_i] = _x
    LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    EXP[_i] = EXP[_i - 255]


def gf_mul(a: int, b: int) -> int:
    return 0 if a == 0 or b == 0 else EXP[LOG[a] + LOG[b]]


def generator_poly(degree: int) -> list[int]:
    """(x - a^0)(x - a^1)... - highest degree FIRST, which is the order the encoder below divides in.
    The old generator got this backwards once; it is the kind of mistake that still produces a
    plausible-looking code that no phone can read."""
    poly = [1]
    for power in range(degree):
        nxt = [0] * (len(poly) + 1)
        for index, coefficient in enumerate(poly):
            nxt[index] ^= coefficient
            nxt[index + 1] ^= gf_mul(coefficient, EXP[power])
        poly = nxt
    return poly


def error_correction(data: list[int], count: int) -> list[int]:
    poly = generator_poly(count)
    remainder = list(data) + [0] * count
    for index in range(len(data)):
        factor = remainder[index]
        if factor:
            for offset, coefficient in enumerate(poly):
                remainder[index + offset] ^= gf_mul(coefficient, factor)
    return remainder[len(data):]


# ------------------------------------------------------------------------- version tables (EC level M)
# (data codewords, ec codewords per block, blocks in group 1, blocks in group 2)
VERSIONS_M = {
    1: (16, 10, 1, 0), 2: (28, 16, 1, 0), 3: (44, 26, 1, 0), 4: (64, 18, 2, 0),
    5: (86, 24, 2, 0), 6: (108, 16, 4, 0), 7: (124, 18, 4, 0), 8: (154, 22, 2, 2),
    9: (182, 22, 3, 2), 10: (216, 26, 4, 1), 11: (254, 30, 1, 4), 12: (290, 22, 6, 2),
    13: (334, 22, 8, 1), 14: (365, 24, 4, 5), 15: (415, 24, 5, 5),
}
ALIGNMENT = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34],
             7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50], 11: [6, 30, 54],
             12: [6, 32, 58], 13: [6, 34, 62], 14: [6, 26, 46, 66], 15: [6, 26, 48, 70]}
# BCH-encoded format strings for EC level M, masks 0-7 (specification table C.1)
FORMAT_M = [0x5412, 0x5125, 0x5E7C, 0x5B4B, 0x45F9, 0x40CE, 0x4F97, 0x4AA0]
VERSION_BITS = {7: 0x07C94, 8: 0x085BC, 9: 0x09A99, 10: 0x0A4D3, 11: 0x0BBF6, 12: 0x0C762,
                13: 0x0D847, 14: 0x0E60D, 15: 0x0F928}


def choose_version(length: int) -> int:
    for version, (data_words, _ec, _g1, _g2) in sorted(VERSIONS_M.items()):
        header = 4 + (8 if version < 10 else 16)      # mode nibble + character count
        if header + length * 8 <= data_words * 8:
            return version
    raise ValueError("text too long for the versions tabulated here")


def encode_data(text: str, version: int) -> list[int]:
    data_words, _ec, _g1, _g2 = VERSIONS_M[version]
    raw = text.encode("utf-8")
    bits = "0100"                                      # byte mode
    bits += format(len(raw), "016b" if version >= 10 else "08b")
    bits += "".join(format(byte, "08b") for byte in raw)
    bits += "0" * min(4, data_words * 8 - len(bits))   # terminator, as far as there is room
    bits += "0" * (-len(bits) % 8)                     # up to the byte boundary - and no further
    words = [int(bits[i:i + 8], 2) for i in range(0, len(bits), 8)]
    # 236/17 alternating. The count has to be taken BEFORE the loop: len(words) grows with every
    # append, so using it inside made every pad byte 0xEC and the code unreadable - while still
    # looking like a perfectly good QR code.
    first_pad = len(words)
    for pad in range(first_pad, data_words):
        words.append(0xEC if (pad - first_pad) % 2 == 0 else 0x11)
    return words[:data_words]


def interleave(words: list[int], version: int) -> list[int]:
    data_words, ec_words, group1, group2 = VERSIONS_M[version]
    blocks_total = group1 + group2
    short = data_words // blocks_total
    blocks = []
    at = 0
    for index in range(blocks_total):
        size = short + (1 if index >= group1 else 0)
        blocks.append(words[at:at + size])
        at += size
    checks = [error_correction(block, ec_words) for block in blocks]
    out = []
    for column in range(max(len(b) for b in blocks)):
        for block in blocks:
            if column < len(block):
                out.append(block[column])
    for column in range(ec_words):
        for check in checks:
            out.append(check[column])
    return out


# --------------------------------------------------------------------------------- laying out the grid
def new_matrix(version: int):
    size = version * 4 + 17
    return [[None] * size for _ in range(size)], size


def place_finder(matrix, size, top, left):
    """The 7x7 eye plus its light separator: a dark ring, a light ring inside it, a dark 3x3 core."""
    for row in range(-1, 8):
        for col in range(-1, 8):
            y, x = top + row, left + col
            if not (0 <= y < size and 0 <= x < size):
                continue
            if row in (-1, 7) or col in (-1, 7):
                matrix[y][x] = 0                       # the separator around the eye
                continue
            ring = max(abs(row - 3), abs(col - 3))
            matrix[y][x] = 1 if ring in (0, 1, 3) else 0


def place_alignment(matrix, size, version):
    centres = ALIGNMENT[version]
    for row in centres:
        for col in centres:
            if (row, col) in ((6, 6), (6, size - 7), (size - 7, 6)):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    matrix[row + dy][col + dx] = 1 if max(abs(dy), abs(dx)) != 1 else 0


def reserve(matrix, size, version):
    place_finder(matrix, size, 0, 0)
    place_finder(matrix, size, 0, size - 7)
    place_finder(matrix, size, size - 7, 0)
    place_alignment(matrix, size, version)
    for i in range(8, size - 8):                      # the two timing lines
        bit = 1 if i % 2 == 0 else 0
        matrix[6][i] = bit
        matrix[i][6] = bit
    matrix[size - 8][8] = 1                           # the one module that is always dark
    for i in range(9):                                # format information, reserved for now
        if matrix[8][i] is None:
            matrix[8][i] = "F"
        if matrix[i][8] is None:
            matrix[i][8] = "F"
    for i in range(8):
        if matrix[8][size - 1 - i] is None:
            matrix[8][size - 1 - i] = "F"
        if matrix[size - 1 - i][8] is None:
            matrix[size - 1 - i][8] = "F"
    if version >= 7:
        for i in range(6):
            for j in range(3):
                matrix[size - 11 + j][i] = "V"
                matrix[i][size - 11 + j] = "V"


def place_data(matrix, size, words):
    bits = "".join(format(word, "08b") for word in words)
    index = 0
    upward = True
    col = size - 1
    while col > 0:
        if col == 6:                                   # the vertical timing line is skipped entirely
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for row in rows:
            for offset in (0, 1):
                x = col - offset
                if matrix[row][x] is None:
                    matrix[row][x] = int(bits[index]) if index < len(bits) else 0
                    index += 1
        upward = not upward
        col -= 2


MASKS = (lambda r, c: (r + c) % 2 == 0,
         lambda r, c: r % 2 == 0,
         lambda r, c: c % 3 == 0,
         lambda r, c: (r + c) % 3 == 0,
         lambda r, c: (r // 2 + c // 3) % 2 == 0,
         lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
         lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
         lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0)


def apply_mask(matrix, size, reserved, mask):
    out = [row[:] for row in matrix]
    for row in range(size):
        for col in range(size):
            if not reserved[row][col] and MASKS[mask](row, col):
                out[row][col] ^= 1
    return out


def place_format(matrix, size, mask):
    bits = format(FORMAT_M[mask], "015b")
    for i in range(6):
        matrix[8][i] = int(bits[i])
        matrix[size - 1 - i][8] = int(bits[i])
    matrix[8][7] = int(bits[6])
    matrix[size - 7][8] = int(bits[6])
    matrix[8][8] = int(bits[7])
    matrix[7][8] = int(bits[8])
    for i in range(9, 15):
        matrix[14 - i][8] = int(bits[i])
    # The second copy's horizontal half carries EIGHT modules, from size-8 to size-1 - it starts two
    # earlier than the vertical half ends. Beginning at 9 left (8, size-8) and (8, size-7) holding
    # whatever the data and the mask had put there: one module wrong out of 1369, and a code that a
    # reader can still correct - which is exactly the kind of error that ships.
    for i in range(7, 15):
        matrix[8][size - 15 + i] = int(bits[i])


def place_version(matrix, size, version):
    if version < 7:
        return
    bits = format(VERSION_BITS[version], "018b")
    for i in range(18):
        bit = int(bits[17 - i])
        matrix[i // 3][size - 11 + i % 3] = bit
        matrix[size - 11 + i % 3][i // 3] = bit


def penalty(matrix, size) -> int:
    score = 0
    for line in list(matrix) + [list(col) for col in zip(*matrix)]:
        run, previous = 1, line[0]
        for value in line[1:]:
            if value == previous:
                run += 1
            else:
                if run >= 5:
                    score += 3 + run - 5
                run, previous = 1, value
        if run >= 5:
            score += 3 + run - 5
        text = "".join(str(v) for v in line)
        score += 40 * (text.count("1011101000000") + text.count("0000010111010"))
    for row in range(size - 1):
        for col in range(size - 1):
            block = (matrix[row][col], matrix[row][col + 1], matrix[row + 1][col], matrix[row + 1][col + 1])
            if len(set(block)) == 1:
                score += 3
    dark = sum(sum(row) for row in matrix)
    percent = dark * 100 // (size * size)
    score += 10 * min(abs(percent - 50) // 5, abs(percent + (5 - percent % 5 if percent % 5 else 0) - 50) // 5)
    return score


def build(text: str):
    """The finished module grid for `text`, plus the version and mask that were chosen."""
    version = choose_version(len(text.encode("utf-8")))
    words = interleave(encode_data(text, version), version)
    matrix, size = new_matrix(version)
    reserve(matrix, size, version)
    reserved = [[cell is not None for cell in row] for row in matrix]
    for row in range(size):
        for col in range(size):
            if matrix[row][col] in ("F", "V"):
                matrix[row][col] = 0
    place_data(matrix, size, words)
    best, best_score, best_mask = None, None, 0
    for mask in range(8):
        candidate = apply_mask(matrix, size, reserved, mask)
        place_format(candidate, size, mask)
        place_version(candidate, size, version)
        score = penalty(candidate, size)
        if best_score is None or score < best_score:
            best, best_score, best_mask = candidate, score, mask
    return best, size, version, best_mask


# ------------------------------------------------------------------------------- the C header
def as_header(name: str, url: str, matrix, size: int, version: int, mask: int, note: str) -> str:
    rows = ",\n".join("   " + ",".join(str(cell) for cell in row) for row in matrix)
    return ('#pragma once\n\n'
            '// %s\n'
            '// Generated by tools/make-qr.py - do not edit by hand. 1 = dark module, 0 = light.\n'
            '// Draw it with a light quiet-zone border around it, or no phone will see it.\n'
            '//\n'
            '// url:     %s\n'
            '// version: %d (%dx%d), error correction M, mask %d (chosen by the penalty rules)\n'
            '//\n'
            '// The generator that made this is checked against the code that was already in the tree:\n'
            '// tests/test_qr.py has it rebuild the old release-page code module for module before it is\n'
            '// trusted with a new one. That is the only verification available without a camera.\n\n'
            '#define %s_SIZE %d\n\n'
            'static const unsigned char %s_MODULES[%s_SIZE * %s_SIZE] = {\n%s\n};\n'
            % (note, url, version, size, size, mask, name, size, name, name, name, rows))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="rebuild the existing header and compare")
    parser.add_argument("--write", action="store_true", help="write the headers the app includes")
    parser.add_argument("--url", help="print one code for any URL instead")
    options = parser.parse_args()

    if options.url:
        matrix, size, version, mask = build(options.url)
        print("version %d, %dx%d, mask %d" % (version, size, size, mask))
        for row in matrix:
            print("".join("##" if cell else "  " for cell in row))
        return 0

    if options.check:
        old_url = "https://github.com/TheErsysEnding/TEE-Cell-Stream-Server-Linux/releases/latest"
        matrix, size, _version, _mask = build(old_url)
        text = (INCLUDE / "qr-code.h").read_text()
        numbers = [int(n) for n in text.split("{", 1)[1].split("}", 1)[0].replace("\n", "").split(",") if n.strip()]
        mine = [cell for row in matrix for cell in row]
        if mine == numbers:
            print("the generator reproduces the existing code exactly (%dx%d)" % (size, size))
            return 0
        wrong = sum(1 for a, b in zip(mine, numbers) if a != b)
        print("MISMATCH: %d of %d modules differ (sizes %d vs %d)"
              % (wrong, len(numbers), len(mine), len(numbers)))
        return 1

    if options.write:
        for name, url, path, note in (
                ("QR", URL_RELEASES, INCLUDE / "qr-code.h",
                 "QR code for this project's release page - the app shows it while it waits for a server."),
                ("QR_DONATE", URL_DONATE, INCLUDE / "qr-donate.h",
                 "QR code for the donation page. One euro pays for a month of the server this project "
                 "lives on."),
        ):
            matrix, size, version, mask = build(url)
            path.write_text(as_header(name, url, matrix, size, version, mask, note))
            print("wrote %s  (version %d, %dx%d, mask %d)" % (path.name, version, size, size, mask))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
