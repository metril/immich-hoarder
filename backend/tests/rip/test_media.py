import hashlib
import random
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.rip.media import (
    NotAnImage,
    analyze,
    chunks16,
    hamming,
    to_signed64,
    to_unsigned64,
)


def _synthetic(size: int) -> Image.Image:
    rng = random.Random(7)
    img = Image.new("RGB", (800, 800), "white")
    d = ImageDraw.Draw(img)
    for _ in range(25):
        x, y = rng.randrange(700), rng.randrange(700)
        d.rectangle(
            (x, y, x + rng.randrange(20, 300), y + rng.randrange(20, 300)),
            fill=tuple(rng.randrange(256) for _ in range(3)),
        )
    return img.resize((size, size)) if size != 800 else img


def test_analyze_jpeg_dims_sha1(tmp_path: Path) -> None:
    p = tmp_path / "a.jpg"
    Image.new("RGB", (64, 32), "red").save(p, "JPEG")
    info = analyze(p)
    assert (info.format, info.width, info.height, info.animated) == ("JPEG", 64, 32, False)
    assert info.size == p.stat().st_size
    assert info.sha1 == hashlib.sha1(p.read_bytes()).digest()
    assert -(2**63) <= info.phash < 2**63


def test_animated_gif_detected(tmp_path: Path) -> None:
    p = tmp_path / "a.gif"
    frames = [Image.new("RGB", (16, 16), c) for c in ("red", "blue")]
    frames[0].save(p, "GIF", save_all=True, append_images=frames[1:])
    info = analyze(p)
    assert info.format == "GIF"
    assert info.animated is True


def test_html_as_jpg_not_an_image(tmp_path: Path) -> None:
    p = tmp_path / "x.jpg"
    p.write_text("<html><body>nope</body></html>")
    with pytest.raises(NotAnImage):
        analyze(p)


def test_truncated_jpeg_not_an_image(tmp_path: Path) -> None:
    p = tmp_path / "t.jpg"
    _synthetic(800).save(p, "JPEG")
    p.write_bytes(p.read_bytes()[:-2000][:3000])
    with pytest.raises(NotAnImage):
        analyze(p)


def test_resized_recompressed_near_duplicate_distance_le_3(tmp_path: Path) -> None:
    a, b = tmp_path / "a.jpg", tmp_path / "b.jpg"
    _synthetic(800).save(a, "JPEG", quality=95)
    _synthetic(400).save(b, "JPEG", quality=60)
    assert hamming(analyze(a).phash, analyze(b).phash) <= 3


def test_signed_roundtrip_and_chunks() -> None:
    for u in (0, 2**63, 2**64 - 1):
        assert to_unsigned64(to_signed64(u)) == u
    assert to_signed64(2**63) == -(2**63)
    assert to_signed64(2**64 - 1) == -1
    assert chunks16(0) == (0, 0, 0, 0)
    assert chunks16(2**64 - 1) == (65535,) * 4
    assert chunks16(2**63) == (0x8000, 0, 0, 0)
    assert chunks16(to_signed64(2**63)) == (0x8000, 0, 0, 0)


def test_hamming() -> None:
    assert hamming(0, 0) == 0
    assert hamming(0, 2**64 - 1) == 64
    assert hamming(-1, 2**64 - 1) == 0
    assert hamming(to_signed64(2**63), 0) == 1
