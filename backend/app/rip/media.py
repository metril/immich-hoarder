"""Media analysis and perceptual-hash helpers."""

import hashlib
import warnings
from dataclasses import dataclass
from pathlib import Path

import imagehash
from PIL import Image

Image.MAX_IMAGE_PIXELS = 178_956_970

ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "GIF", "WEBP", "BMP", "TIFF", "AVIF", "HEIF"})
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


def _sha1(path: Path) -> bytes:
    h = hashlib.sha1(usedforsecurity=False)
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.digest()


def analyze(path: Path) -> MediaInfo:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as probe:
                fmt = probe.format
                probe.verify()
            if fmt not in ALLOWED_FORMATS:
                raise NotAnImage(f"unsupported format: {fmt}")
            with Image.open(path) as img:
                animated = bool(
                    getattr(img, "is_animated", False) or getattr(img, "n_frames", 1) > 1
                )
                img.seek(0)
                img.load()
                width, height = img.size
                frame = img if img.mode in ("L", "RGB") else img.convert("RGB")
                phash = to_signed64(int(str(imagehash.phash(frame)), 16))
    except NotAnImage:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as e:
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
