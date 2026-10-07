from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import requests

from src.epub.metadata import enrich_epub_metadata
from src.metadata.catalog import MetadataLookup, PackageMetadata
from src.metadata.enrich import enrich_source
from src.metadata.jjwxc import parse_jjwxc_contents

CONTENTS = """
<html><body>
<table><tr><td><b class="volumnfont">Outside the directory</b></td></tr></table>
<table id="oneboolt">
  <tr><td colspan="6"><b class="volumnfont">引子 任意开头</b></td></tr>
  <tr itemprop="chapter"><td>1</td><td><span itemprop="headline">
    <a itemprop="url" href="http://www.jjwxc.net/onebook.php?novelid=123&amp;chapterid=1">开始</a>
  </span></td><td>提要提到尾声，不是卷标题</td></tr>
  <tr><td colspan="6"><b class="volumnfont">没有卷字的名字</b></td></tr>
  <tr itemprop="chapter"><td>2</td><td><span itemprop="headline">
    <a itemprop="url" rel="http://my.jjwxc.net/onebook_vip.php?novelid=123&amp;chapterid=2">途中</a>
    <a rel="http://my.jjwxc.net/backend/buynovel.php?novelid=123&amp;chapterid=2">[VIP]</a>
  </span></td></tr>
  <tr><td colspan="6"><b class="volumnfont">尾声 任意结尾</b></td></tr>
  <tr itemprop="chapter newestChapter"><td>3</td><td><span itemprop="headline">
    <a itemprop="url" rel="http://my.jjwxc.net/onebook_vip.php?novelid=123&amp;chapterid=3">结束</a>
    <a>[VIP]</a>
  </span></td></tr>
</table>
</body></html>
"""

AUTHOR = """
<table class="author novel">
<tr><td><a onclick="jump_book2(123,456)">《样本》</a></td></tr>
<tr><td>类型:原创-纯爱-架空历史-传奇-主受</td></tr>
<tr><td>发表时间：2020-01-02 11:00:00</td></tr>
</table>
"""
DESCRIPTION = '<html><div id="novelintro">样本简介</div></html>'


class Session:
    def __init__(self, contents: str | Exception = CONTENTS):
        self.headers = {}
        self.urls = []
        self.contents = contents

    def get(self, url, *, timeout):
        self.urls.append(url)
        values = {
            "https://m.jjwxc.net/wapauthor/456": AUTHOR,
            "https://m.jjwxc.net/book2/123": DESCRIPTION,
            "https://www.jjwxc.net/onebook.php?novelid=123": self.contents,
        }
        value = values[url]
        if isinstance(value, Exception):
            raise value
        response = requests.Response()
        response.status_code = 200
        response._content = value.encode("gb18030")
        return response


def package() -> PackageMetadata:
    return PackageMetadata("样本", "作者", "zh-CN", "", "", "", (), None, None)


def lookup(session: Session) -> MetadataLookup:
    return MetadataLookup(author_ids={"作者": "456"}, session=session, kadokado=False)


class JinjiangContentsTests(unittest.TestCase):
    def test_groups_by_html_structure_and_preserves_arbitrary_names(self):
        result = parse_jjwxc_contents(CONTENTS, novel_id="123")
        self.assertEqual(
            [v.title for v in result.volumes],
            [
                "引子 任意开头",
                "没有卷字的名字",
                "尾声 任意结尾",
            ],
        )
        self.assertEqual(
            [[c.number for c in v.chapters] for v in result.volumes], [[1], [2], [3]]
        )
        self.assertEqual(result.chapter_count, 3)
        self.assertEqual(result.volumes[-1].chapters[0].title, "结束")
        self.assertEqual(
            result.volumes[1].chapters[0].url,
            "https://www.jjwxc.net/onebook.php?novelid=123&chapterid=2",
        )

    def test_does_not_infer_volumes_from_chapter_words_or_colspan(self):
        html = CONTENTS.replace(
            '<b class="volumnfont">引子 任意开头</b>', "普通合并单元格"
        )
        html = html.replace("开始</a>", "第一卷 尾声</a>")
        result = parse_jjwxc_contents(html, novel_id="123")
        self.assertEqual(result.volumes[0].title, "")
        self.assertEqual(result.volumes[0].chapters[0].title, "第一卷 尾声")

    def test_preserves_empty_and_repeated_volume_rows(self):
        html = CONTENTS.replace("没有卷字的名字", "尾声 任意结尾")
        html = html.replace(
            "</table>\n</body>",
            '<tr><td><b class="volumnfont">空分组</b></td></tr></table>\n</body>',
        )
        result = parse_jjwxc_contents(html, novel_id="123")
        self.assertEqual(
            [v.title for v in result.volumes],
            [
                "引子 任意开头",
                "尾声 任意结尾",
                "尾声 任意结尾",
                "空分组",
            ],
        )
        self.assertEqual(result.volumes[-1].chapters, ())

    def test_locked_chapter_without_link_is_retained(self):
        html = CONTENTS.replace(
            '<a itemprop="url" rel="http://my.jjwxc.net/onebook_vip.php?novelid=123&amp;chapterid=3">结束</a>\n    <a>[VIP]</a>',
            "[锁]",
        )
        chapter = parse_jjwxc_contents(html, novel_id="123").volumes[-1].chapters[0]
        self.assertEqual(chapter.number, 3)
        self.assertEqual(chapter.title, "[锁]")
        self.assertIsNone(chapter.url)

    def test_rejects_missing_or_inconsistent_directory(self):
        for html in [
            "<html>验证页面</html>",
            CONTENTS.replace("<td>3</td>", "<td>2</td>"),
            CONTENTS.replace(
                "novelid=123&amp;chapterid=3", "novelid=999&amp;chapterid=3"
            ),
        ]:
            with self.subTest(html=html[:50]), self.assertRaises(ValueError):
                parse_jjwxc_contents(html, novel_id="123")

    def test_same_metadata_lookup_fetches_book_details_and_complete_contents(self):
        session = Session()
        result = lookup(session).find(package())
        self.assertEqual(result.date, "2020-01-02")
        self.assertEqual(result.source, "https://www.jjwxc.net/onebook.php?novelid=123")
        self.assertEqual(result.table_of_contents.chapter_count, 3)
        self.assertIsNone(result.table_of_contents_error)
        self.assertIn("https://m.jjwxc.net/book2/123", session.urls)
        self.assertIn(result.source, session.urls)

    def test_author_homepage_uses_the_exact_author_lookup(self):
        self.assertEqual(
            lookup(Session()).find_author_homepage("作者"),
            "https://www.jjwxc.net/oneauthor.php?authorid=456",
        )
        with patch.object(MetadataLookup, "_find_jjwxc_author_id", return_value=None):
            self.assertIsNone(MetadataLookup().find_author_homepage("无匹配作者"))

    def test_directory_failure_is_reported_without_erasing_verified_metadata(self):
        for response in ["<html>验证页面</html>", requests.Timeout("fixture timeout")]:
            with self.subTest(response=str(response)):
                result = lookup(Session(response)).find(package())
                self.assertEqual(result.date, "2020-01-02")
                self.assertIsNone(result.table_of_contents)
                self.assertTrue(result.table_of_contents_error)

    def test_prepared_source_receives_contents_from_the_same_lookup(self):
        book = {
            "metadata": {
                "title": "样本",
                "creator": "作者",
                "language": "zh-CN",
                "date": "",
                "source": "",
                "description": "",
                "subjects": [],
                "series": "",
                "series_position": "",
            }
        }
        report = enrich_source(book, lookup=lookup(Session()))
        self.assertEqual(
            report["table_of_contents"]["volumes"][-1]["title"], "尾声 任意结尾"
        )
        self.assertEqual(book["metadata"]["date"], "2020-01-02")

    def test_epub_metadata_command_report_includes_contents_without_rewriting_body(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fixture.epub"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(
                    "mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED
                )
                archive.writestr(
                    "EPUB/content.opf",
                    """<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
                <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>样本</dc:title><dc:creator>作者</dc:creator></metadata>
                <manifest/><spine/></package>""",
                )
                archive.writestr("EPUB/chapter.xhtml", "<html>unchanged body</html>")
            report = enrich_epub_metadata(
                path, backup_dir=None, lookup=lookup(Session())
            )
            self.assertEqual(report.status, "enriched")
            encoded = json.loads(json.dumps(report.to_dict(), ensure_ascii=False))
            self.assertEqual(
                encoded["table_of_contents"]["volumes"][-1]["chapters"][0]["number"], 3
            )
            self.assertIn("chapters=3", report.format_text())
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(
                    archive.read("EPUB/chapter.xhtml"), b"<html>unchanged body</html>"
                )


if __name__ == "__main__":
    unittest.main()
