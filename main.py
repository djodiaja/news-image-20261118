#!/usr/bin/env python3
"""make.fun bounty news-image-20261118 — "Sum up 18 November's world news in one image".

Writes the pre-rendered editorial page (assets/entry.png, built by render.py) to
$MAKEFUN_OUTPUT_DIR/entry.png (default /output/entry.png).

Standard library only, no network, no clock, no randomness: every run writes the exact
bytes of the committed PNG, so two runs are byte-identical.
"""
import hashlib
import os
import struct
import sys
import zlib
from pathlib import Path

EXPECTED_SHA256 = "fc1bd71bb9ced809691cde1c2c4483b0518f240df7284273adcb5b63f8566e2e"
MAX_BYTES = 1024 * 1024
MAX_SIDE = 1024
PNG_SIG = b"\x89PNG\r\n\x1a\n"


def check_png(data):
    """Verify the PNG is whole: signature, every chunk CRC, IHDR size, IEND last."""
    if not data.startswith(PNG_SIG):
        raise ValueError("not a PNG")
    pos, width, height, seen_end = len(PNG_SIG), None, None, False
    while pos < len(data):
        length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        (crc,) = struct.unpack(">I", data[pos + 8 + length:pos + 12 + length])
        if zlib.crc32(ctype + body) & 0xFFFFFFFF != crc:
            raise ValueError(f"bad CRC in {ctype!r} chunk")
        if ctype == b"IHDR":
            width, height = struct.unpack(">II", body[:8])
        pos += 12 + length
        if ctype == b"IEND":
            seen_end = True
            break
    if not seen_end or pos != len(data):
        raise ValueError("PNG does not end cleanly at IEND")
    if not width or not height or width > MAX_SIDE or height > MAX_SIDE:
        raise ValueError(f"bad size {width}x{height}")
    return width, height


def main():
    src = Path(__file__).resolve().parent / "assets" / "entry.png"
    data = src.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED_SHA256:
        sys.exit(f"assets/entry.png sha256 {digest} != expected {EXPECTED_SHA256}")
    if len(data) > MAX_BYTES:
        sys.exit(f"image is {len(data)} bytes, over 1 MiB")
    width, height = check_png(data)

    out_dir = Path(os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output")
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / ".entry.png.part"
    tmp.write_bytes(data)
    os.replace(tmp, out_dir / "entry.png")
    print(f"wrote {out_dir / 'entry.png'} ({width}x{height}, {len(data)} bytes, sha256 {digest})")


if __name__ == "__main__":
    main()
