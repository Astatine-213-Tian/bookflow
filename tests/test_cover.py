from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from src.content.cover import MAX_BYTES, assess_cover, fit_restored_cover, normalize_cover
from src.translation.gates import ReviewRequired
from src.workflows.cover import deliver_cover
from src.workflows.cover_review import build_review


def cover(width: int, height: int, *, noise: bool = False, white: bool = False) -> bytes:
    if noise:
        # Upscaled noise defeats PNG like a detailed painting does.
        small = (width // 4, height // 4)
        image = Image.frombytes("RGB", small, os.urandom(small[0] * small[1] * 3))
        image = image.resize((width, height), Image.Resampling.BICUBIC)
    else:
        image = Image.new("RGB", (width, height), "white" if white else (110, 40, 40))
    ImageDraw.Draw(image).text((width // 3, height // 3), "书名", fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def size(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as image:
        return image.size


class CoverNormalizationTests(unittest.TestCase):
    def test_a_2_3_cover_is_kept_at_its_size_within_the_byte_limit(self):
        data, mime, found = normalize_cover(cover(1000, 1500, noise=True))
        self.assertEqual(found.verdict, "keep")
        self.assertEqual(size(data), (1000, 1500))
        self.assertEqual(mime, "image/jpeg")
        self.assertLessEqual(len(data), MAX_BYTES)

    def test_a_slightly_off_cover_is_center_cropped_without_stretching(self):
        for width, height, expected in [(1000, 1460, (973, 1460)), (1000, 1560, (1000, 1500))]:
            with self.subTest(size=(width, height)):
                data, _, found = normalize_cover(cover(width, height))
                self.assertEqual(found.verdict, "crop")
                self.assertEqual(size(data), expected)

    def test_soft_misshapen_or_margined_covers_need_restoration(self):
        page = Image.new("RGB", (1100, 1700), "white")
        page.paste(Image.new("RGB", (1000, 1500), (110, 40, 40)), (50, 100))
        scan = io.BytesIO()
        page.save(scan, format="PNG")
        for data, reason in [
            (cover(600, 900), "width"),
            (cover(1000, 1250), "ratio"),
            (scan.getvalue(), "white margin"),
        ]:
            with self.subTest(reason=reason):
                found = assess_cover(data)
                self.assertEqual(found.verdict, "restore")
                self.assertTrue(any(reason in r for r in found.reasons))

    def test_designed_whitespace_is_not_a_margin(self):
        self.assertEqual(assess_cover(cover(1000, 1500, white=True)).verdict, "keep")

    def test_covers_are_judged_and_delivered_as_displayed(self):
        stored = Image.new("RGB", (1500, 1000), (110, 40, 40))
        exif = stored.getexif()
        exif[0x0112] = 6  # stored sideways; readers rotate it upright
        buffer = io.BytesIO()
        stored.save(buffer, format="JPEG", exif=exif.tobytes())
        data, _, found = normalize_cover(buffer.getvalue())
        self.assertEqual((found.verdict, size(data)), ("keep", (1000, 1500)))
        cmyk = io.BytesIO()
        Image.new("CMYK", (1000, 1500), (0, 80, 80, 40)).save(cmyk, format="JPEG")
        data, _, _ = normalize_cover(cmyk.getvalue())
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual(image.mode, "RGB")
        deep = io.BytesIO()
        Image.new("I;16", (1000, 1500), 20000).save(deep, format="PNG")
        data, _, _ = normalize_cover(deep.getvalue())
        with Image.open(io.BytesIO(data)) as image:
            self.assertLess(image.convert("L").getextrema()[1], 255)

    def test_a_cover_too_large_to_fit_pauses_for_restoration(self):
        from unittest.mock import patch

        with patch("src.content.cover.MAX_BYTES", 1000):
            _, _, found = normalize_cover(cover(1000, 1500, noise=True))
        self.assertEqual(found.verdict, "restore")
        self.assertIn("does not fit", found.reasons[0])

    def test_a_restored_cover_must_be_2_3(self):
        with self.assertRaisesRegex(ValueError, "not 2:3"):
            fit_restored_cover(cover(1000, 1400))
        data, _ = fit_restored_cover(cover(1024, 1536, noise=True))
        self.assertLessEqual(len(data), MAX_BYTES)


class CoverStageTests(unittest.TestCase):
    def test_restoration_pauses_with_a_task_and_resumes_with_the_approved_cover(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            source = run / "source.json"
            with self.assertRaises(ReviewRequired) as paused:
                deliver_cover(cover(600, 900), "image/png", run, source=source)
            task = json.loads(paused.exception.path.read_text())
            self.assertEqual(paused.exception.kind, "cover")
            self.assertTrue(Path(task["original"]).exists())
            self.assertEqual(task["source"], str(source))
            approved = run / "approved.png"
            approved.write_bytes(cover(1024, 1536))
            data, _, report = deliver_cover(
                cover(600, 900), "image/png", run, source=source, replacement=approved
            )
            self.assertEqual(report["verdict"], "replaced")
            self.assertEqual(size(data), (1024, 1536))
            original = cover(600, 900)
            self.assertEqual(
                deliver_cover(original, "image/png", run, source=source, keep_original=True)[0],
                original,
            )

    def test_a_text_only_ingest_does_not_pause_for_its_unused_cover(self):
        from src.workflows.ingest import OutputOptions, uses_cover

        self.assertFalse(uses_cover(OutputOptions(output_formats=("txt",))))
        self.assertTrue(uses_cover(OutputOptions(output_formats=("txt", "notion"))))
        notion = OutputOptions(output_formats=("notion",))
        self.assertFalse(uses_cover(notion, cover_url="https://example.org/c.png"))
        both = OutputOptions(output_formats=("epub", "notion"), output=Path("b.epub"))
        self.assertTrue(uses_cover(both, cover_url="https://example.org/c.png"))

    def test_review_page_lists_the_round_and_rejects_outside_images(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "old.png").write_bytes(cover(600, 900))
            (root / "new.png").write_bytes(cover(1024, 1536))
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"round": "r1", "items": [
                {"id": "book", "title": "书名", "original": "old.png", "proposed": "new.png"}
            ]}))
            page = build_review(manifest, root / "review.html").read_text()
            for part in ["Keep original", "Regenerate with comment", "Download decisions", "manifest_sha256", "new.png"]:
                self.assertIn(part, page)
            manifest.write_text(json.dumps({"round": "r1", "items": [
                {"id": "book", "title": "书名", "original": "../old.png", "proposed": "new.png"}
            ]}))
            with self.assertRaisesRegex(ValueError, "beside the manifest"):
                build_review(manifest, root / "review.html")


if __name__ == "__main__":
    unittest.main()
