"""Release gate checks for rw3_urllib3 streaming response decoders (read-only)."""

from __future__ import annotations

import gzip
import sys
import unittest
import zlib
from io import BytesIO
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import urllib3.response as resp_mod  # noqa: E402
from urllib3.response import HTTPResponse  # noqa: E402


def _raw_deflate(payload: bytes) -> bytes:
    comp = zlib.compressobj(6, zlib.DEFLATED, -zlib.MAX_WBITS)
    return comp.compress(payload) + comp.flush()


class Urllib3ResponseReleaseGateTests(unittest.TestCase):
    def test_gzip_multi_member_bounded_read(self) -> None:
        data = gzip.compress(b"x" * 1024) + gzip.compress(b"y" * 1024)
        for method in ("read", "read1"):
            r = HTTPResponse(BytesIO(data), headers={"content-encoding": "gzip"}, preload_content=False)
            fn = getattr(r, method)
            self.assertEqual(fn(1024), b"x" * 1024)
            self.assertEqual(fn(1024), b"y" * 1024)
            self.assertEqual(fn(), b"")

    def test_raw_deflate_eof_flush_streaming(self) -> None:
        msg = b"abc" * 2000
        raw = _raw_deflate(msg)
        r = HTTPResponse(BytesIO(raw), headers={"content-encoding": "deflate"}, preload_content=False)
        self.assertEqual(b"".join(iter(lambda: r.read(64), b"")), msg)

        # Chained deflate, gzip in 1-byte reads
        gz = zlib.compressobj(6, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
        chained = gz.compress(_raw_deflate(b"abc" * 10)) + gz.flush()
        r2 = HTTPResponse(BytesIO(chained), headers={"content-encoding": "deflate, gzip"}, preload_content=False)
        self.assertEqual(b"".join(iter(lambda: r2.read(1), b"")), b"abc" * 10)

    def test_reject_decode_toggle_before_consuming(self) -> None:
        fp = BytesIO(zlib.compress(b"foo"))
        r = HTTPResponse(fp, headers={"content-encoding": "deflate"}, preload_content=False)
        self.assertEqual(r.read(1), b"f")
        pos = fp.tell()
        with self.assertRaises(RuntimeError):
            r.read(1, decode_content=False)
        self.assertEqual(fp.tell(), pos)
        self.assertEqual(r.read(0, decode_content=False), b"")
        self.assertEqual(r.read(), b"oo")

    def test_optional_brotli_and_zstd_codecs_available(self) -> None:
        """Compliance gate: full codec matrix requires real brotli and zstandard backends installed."""
        self.assertIsNotNone(
            resp_mod.brotli,
            "BLOCKER: optional third-party 'brotli'/'brotlicffi' package is not installed in this environment",
        )
        self.assertTrue(
            bool(getattr(resp_mod, "HAS_ZSTD", False)),
            "BLOCKER: optional 'zstandard' / Python 3.14 compression.zstd backend is not installed in this environment",
        )


if __name__ == "__main__":
    unittest.main()
