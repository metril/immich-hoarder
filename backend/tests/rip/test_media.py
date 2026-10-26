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


def test_phash_deterministic(tmp_path: Path) -> None:
    p = tmp_path / "a.png"
    _synthetic(300).save(p, "PNG")
    assert analyze(p).phash == analyze(p).phash


def test_phash_differs_for_different_images(tmp_path: Path) -> None:
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    _synthetic(300).save(a, "PNG")
    rng = random.Random(99)
    noise = Image.new("L", (300, 300))
    noise.putdata([rng.randrange(256) for _ in range(300 * 300)])
    noise.resize((300, 300)).save(b, "PNG")
    assert hamming(analyze(a).phash, analyze(b).phash) > 10


def test_mpo_accepted_as_jpeg_not_animated(tmp_path: Path) -> None:
    p = tmp_path / "m.jpg"
    a, b = _synthetic(200), _synthetic(200).rotate(5)
    a.save(p, "MPO", save_all=True, append_images=[b])
    with Image.open(p) as probe:
        assert probe.format == "MPO"
    info = analyze(p)
    assert info.format == "JPEG"
    assert info.animated is False


def test_animated_webp_detected(tmp_path: Path) -> None:
    p = tmp_path / "a.webp"
    frames = [Image.new("RGB", (16, 16), c) for c in ("red", "blue")]
    frames[0].save(p, "WEBP", save_all=True, append_images=frames[1:])
    info = analyze(p)
    assert (info.format, info.animated) == ("WEBP", True)


def test_animated_apng_detected(tmp_path: Path) -> None:
    p = tmp_path / "a.png"
    frames = [Image.new("RGB", (16, 16), c) for c in ("red", "blue")]
    frames[0].save(p, "PNG", save_all=True, append_images=frames[1:])
    info = analyze(p)
    assert (info.format, info.animated) == ("PNG", True)


def test_multipage_tiff_not_animated(tmp_path: Path) -> None:
    p = tmp_path / "a.tif"
    frames = [Image.new("RGB", (16, 16), c) for c in ("red", "blue")]
    frames[0].save(p, "TIFF", save_all=True, append_images=frames[1:])
    assert analyze(p).animated is False


def test_decompression_bomb_not_an_image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "b.png"
    Image.new("RGB", (100, 100)).save(p, "PNG")
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 50)
    with pytest.raises(NotAnImage, match="too large"):
        analyze(p)


def test_unsupported_format_not_an_image(tmp_path: Path) -> None:
    p = tmp_path / "i.ico"
    Image.new("RGB", (16, 16), "red").save(p, "ICO")
    with pytest.raises(NotAnImage):
        analyze(p)


def test_truncated_png_not_an_image(tmp_path: Path) -> None:
    p = tmp_path / "t.png"
    _synthetic(400).save(p, "PNG")
    p.write_bytes(p.read_bytes()[:-3000])
    with pytest.raises(NotAnImage):
        analyze(p)


def test_exif_orientation_applied(tmp_path: Path) -> None:
    stored = _synthetic(800).crop((0, 0, 500, 800))
    exif = Image.Exif()
    exif[0x0112] = 6  # display = rotate 90 clockwise
    a, b = tmp_path / "a.jpg", tmp_path / "b.jpg"
    stored.save(a, "JPEG", quality=95, exif=exif)
    stored.transpose(Image.Transpose.ROTATE_270).save(b, "JPEG", quality=95)
    ia, ib = analyze(a), analyze(b)
    assert (ia.width, ia.height) == (800, 500)
    assert hamming(ia.phash, ib.phash) <= 3


def test_xmp_only_orientation_swaps_dimensions(tmp_path: Path) -> None:
    xmp = (
        b'<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?><x:xmpmeta xmlns:x="adobe:ns:meta/">'
        b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        b'<rdf:Description rdf:about="" xmlns:tiff="http://ns.adobe.com/tiff/1.0/" '
        b'tiff:Orientation="6"/></rdf:RDF></x:xmpmeta><?xpacket end="w"?>'
    )
    p = tmp_path / "x.jpg"
    Image.new("RGB", (500, 300), "red").save(p, "JPEG", xmp=xmp)
    info = analyze(p)
    assert (info.width, info.height) == (300, 500)


def test_large_jpeg_dims_not_draft_scaled(tmp_path: Path) -> None:
    p = tmp_path / "big.jpg"
    Image.new("RGB", (2000, 1000), "blue").save(p, "JPEG")
    info = analyze(p)
    assert (info.width, info.height) == (2000, 1000)


def test_bomb_warning_filtered_at_module_level() -> None:
    import subprocess
    import sys

    code = (
        "import warnings, app.rip.media\n"
        "from PIL import Image\n"
        "print(any(f[0] == 'ignore' and f[2] is Image.DecompressionBombWarning"
        " for f in warnings.filters))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "True"
