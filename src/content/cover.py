"""Cover normalization: keep or slightly crop a 2:3 cover; flag the rest for restoration.

The cover procedure in ``.agents/skills/book-management/references/cover-normalization.md``
owns restoration. This module only makes the decisions that need no judgment and
delivers every cover at no more than ``MAX_BYTES``.
"""

from __future__ import annotations

import io
from dataclasses import asdict, dataclass, field, replace

from PIL import Image, ImageCms, ImageOps, ImageStat

ORIENTATION = 0x0112

RATIO = 2 / 3
# Within 1% of 2:3 a cover is already the right shape.
KEEP_TOLERANCE = 0.01
# Up to 5% off, a centered crop removes at most a sliver of either edge.
CROP_TOLERANCE = 0.05
# Narrower covers are too soft for the library; restore them instead.
MIN_WIDTH = 800
MAX_BYTES = 1_000_000
# A near-white band this deep on an edge, ending at a straight content edge (a
# row or column spanning at least this much of the cover), is an external scan
# margin. Designed whitespace instead gives way to sparse artwork or lettering.
MARGIN_WHITE = 245
MARGIN_DEPTH = 0.02
MARGIN_EDGE_FILL = 0.6


@dataclass(frozen=True)
class CoverAssessment:
    width: int
    height: int
    ratio_error: float
    verdict: str  # keep | crop | restore
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _white_margins(image: Image.Image) -> list[str]:
    content = image.convert("L").point(lambda v: 255 if v < MARGIN_WHITE else 0)
    width, height = content.size
    box = content.getbbox()
    if box is None:
        return []
    left, top, right, bottom = box
    fill = lambda region: ImageStat.Stat(content.crop(region)).mean[0] / 255
    sides = [
        ("top", top, height, (0, top, width, top + 1)),
        ("bottom", height - bottom, height, (0, bottom - 1, width, bottom)),
        ("left", left, width, (left, 0, left + 1, height)),
        ("right", width - right, width, (right - 1, 0, right, height)),
    ]
    return [
        side
        for side, gap, size, edge in sides
        if gap >= size * MARGIN_DEPTH and fill(edge) >= MARGIN_EDGE_FILL
    ]


@dataclass(frozen=True)
class _Decoded:
    image: Image.Image  # RGB, as displayed
    icc: bytes | None  # an RGB profile worth keeping
    transparent: bool
    unchanged: bool  # already an upright RGB/gray PNG or JPEG


def _decode(data: bytes) -> _Decoded:
    """Decode a cover as readers display it: EXIF-rotated and in RGB."""
    with Image.open(io.BytesIO(data)) as source:
        source.load()
        image = ImageOps.exif_transpose(source)
        rotated = source.getexif().get(ORIENTATION, 1) != 1
        plain = source.format in {"PNG", "JPEG"} and source.mode in {"RGB", "L"}
    icc = image.info.get("icc_profile")
    transparent = False
    if image.mode in {"RGBA", "LA", "PA"} or "transparency" in image.info:
        image = image.convert("RGBA")
        transparent = image.getchannel("A").getextrema()[0] < 255
    if image.mode in {"I;16", "I;16B", "I;16L", "I"}:
        # Scale 16-bit samples down instead of clipping them to white.
        image = image.convert("I").point(lambda v: v * (1 / 256)).convert("L")
        icc = None
    if image.mode != "RGB" and icc:
        # A CMYK or gray profile cannot describe the RGB result; convert through it.
        try:
            image = ImageCms.profileToProfile(
                image,
                ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                ImageCms.createProfile("sRGB"),
                outputMode="RGB",
            )
        except (ImageCms.PyCMSError, OSError):
            image = image.convert("RGB")
        icc = None
    image = image.convert("RGB")
    return _Decoded(image, icc, transparent, plain and not rotated and not transparent)


def assess_cover(data: bytes) -> CoverAssessment:
    decoded = _decode(data)
    width, height = decoded.image.size
    error = (width / height) / RATIO - 1
    reasons = []
    if decoded.transparent:
        reasons.append("transparent pixels")
    if margins := _white_margins(decoded.image):
        reasons.append("white margin on " + ", ".join(margins))
    if width < MIN_WIDTH:
        reasons.append(f"width {width}px is below {MIN_WIDTH}px")
    if abs(error) > CROP_TOLERANCE:
        reasons.append(f"ratio is {abs(error):.1%} from 2:3")
    if reasons:
        verdict = "restore"
    elif abs(error) <= KEEP_TOLERANCE:
        verdict = "keep"
    else:
        verdict = "crop"
    return CoverAssessment(width, height, round(error, 4), verdict, reasons)


def crop_to_ratio(image: Image.Image) -> Image.Image:
    """Center-crop the longer axis to exactly 2:3, never stretching."""
    width, height = image.size
    if width / height > RATIO:
        target = round(height * RATIO)
        left = (width - target) // 2
        return image.crop((left, 0, left + target, height))
    target = round(width / RATIO)
    top = (height - target) // 2
    return image.crop((0, top, width, top + target))


class CoverTooLarge(ValueError):
    pass


def encode_cover(image: Image.Image, icc: bytes | None = None) -> tuple[bytes, str]:
    """Lossless PNG when it fits, else the highest full-chroma JPEG quality that fits."""
    profile = {"icc_profile": icc} if icc else {}
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True, compress_level=9, **profile)
    if buffer.tell() <= MAX_BYTES:
        return buffer.getvalue(), "image/png"
    for quality in range(100, 79, -1):
        buffer = io.BytesIO()
        image.save(
            buffer,
            format="JPEG",
            quality=quality,
            subsampling=0,
            optimize=True,
            progressive=True,
            **profile,
        )
        if buffer.tell() <= MAX_BYTES:
            return buffer.getvalue(), "image/jpeg"
    raise CoverTooLarge(f"cover does not fit {MAX_BYTES} bytes at JPEG quality 80")


def normalize_cover(data: bytes) -> tuple[bytes, str, CoverAssessment]:
    """Return the delivered cover for a keep/crop verdict; restoration is left to review."""
    assessment = assess_cover(data)
    if assessment.verdict == "restore":
        return data, "", assessment
    decoded = _decode(data)
    image = decoded.image
    if assessment.verdict == "crop":
        image = crop_to_ratio(image)
    try:
        encoded, mime = encode_cover(image, decoded.icc)
    except CoverTooLarge as error:
        return data, "", replace(assessment, verdict="restore", reasons=[str(error)])
    return encoded, mime, assessment


def fit_restored_cover(data: bytes) -> tuple[bytes, str]:
    """Check an approved replacement is 2:3 and deliver it within the byte limit."""
    decoded = _decode(data)
    width, height = decoded.image.size
    if abs((width / height) / RATIO - 1) > KEEP_TOLERANCE:
        raise ValueError(f"Replacement cover is {width}x{height}, not 2:3")
    if decoded.transparent:
        raise ValueError("Replacement cover has transparent pixels; flatten it")
    if decoded.unchanged and len(data) <= MAX_BYTES:
        return data, "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"
    return encode_cover(decoded.image, decoded.icc)
