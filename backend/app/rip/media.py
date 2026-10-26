"""Media analysis and perceptual-hash helpers."""

import hashlib
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = 178_956_970
# _check_pixels rejects oversized images explicitly; the warning (1x-2x the limit) is noise.
warnings.filterwarnings("ignore", category=Image.DecompressionBombWarning)

ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "GIF", "WEBP", "BMP", "TIFF", "AVIF"})
_ANIMATABLE = frozenset({"GIF", "WEBP", "PNG", "AVIF"})
_CHUNK = 1024 * 1024
_MASK64 = (1 << 64) - 1


class NotAnImage(Exception):
    """The file is not a readable image of an allowed format."""


@dataclass(frozen=True)
class MediaInfo:
    format: str
    width: int
    height: int
    animated: bool
    size: int
    sha1: bytes
    phash: int  # signed int64


def to_signed64(u: int) -> int:
    u &= _MASK64
    return u - (1 << 64) if u >= 1 << 63 else u


def to_unsigned64(s: int) -> int:
    return s & _MASK64


def chunks16(u: int) -> tuple[int, int, int, int]:
    u &= _MASK64
    return (u >> 48, (u >> 32) & 0xFFFF, (u >> 16) & 0xFFFF, u & 0xFFFF)


def hamming(a: int, b: int) -> int:
    return ((a ^ b) & _MASK64).bit_count()


def _dct_matrix(n: int) -> np.ndarray:
    k = np.arange(n)[:, None]
    x = np.arange(n)[None, :]
    c = np.cos(np.pi * (2 * x + 1) * k / (2 * n)) * np.sqrt(2.0 / n)
    c[0] /= np.sqrt(2.0)
    return np.asarray(c)


_DCT = _dct_matrix(32)


def _phash(frame: Image.Image) -> int:
    small = np.asarray(frame.convert("L").resize((32, 32), Image.Resampling.LANCZOS), dtype=float)
    block = (_DCT @ small @ _DCT.T)[:8, :8]
    bits = (block > np.median(block)).ravel()
    u = 0
    for b in bits:
        u = (u << 1) | int(b)
    return to_signed64(u)


def _sha1(path: Path) -> bytes:
    h = hashlib.sha1(usedforsecurity=False)
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.digest()


def _check_pixels(img: Image.Image) -> None:
    limit = Image.MAX_IMAGE_PIXELS
    if limit is not None and img.width * img.height > limit:
        raise NotAnImage("too large")


def analyze(path: Path) -> MediaInfo:
    try:
        with Image.open(path) as probe:
            fmt = "JPEG" if probe.format == "MPO" else probe.format
            if fmt not in ALLOWED_FORMATS:
                raise NotAnImage(f"unsupported format: {fmt}")
            _check_pixels(probe)
            probe.verify()
        with Image.open(path) as img:
            _check_pixels(img)
            animated = fmt in _ANIMATABLE and bool(
                getattr(img, "is_animated", False) or getattr(img, "n_frames", 1) > 1
            )
            width, height = img.size
            img.seek(0)
            if fmt == "JPEG":
                img.draft("RGB", (256, 256))
            img.load()
            upright = ImageOps.exif_transpose(img)
            # draft() shrinks the image; only the swap (honouring EXIF and XMP) is trusted
            if upright.size != img.size and img.width != img.height:
                width, height = height, width
            phash = _phash(upright)
    except NotAnImage:
        raise
    except Image.DecompressionBombError as e:
        raise NotAnImage("too large") from e
    except Exception as e:
        raise NotAnImage(f"unreadable image: {type(e).__name__}") from e
    assert fmt is not None
    return MediaInfo(
        format=fmt,
        width=width,
        height=height,
        animated=animated,
        size=path.stat().st_size,
        sha1=_sha1(path),
        phash=phash,
    )
