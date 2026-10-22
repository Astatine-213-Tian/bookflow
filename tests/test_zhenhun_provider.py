from __future__ import annotations

import unittest

from src.crawler.providers.zhenhun import parser


BOOK_HTML = """
<html>
  <head><title>天涯客（priest）</title></head>
  <body>
    <h1 class="focusbox-title">天涯客</h1>
    <div class="focusbox-text"><div class="text">一入江湖岁月催</div></div>
    <div class="excerpts">
      <article class="excerpt"><a href="https://www.zhenhunxiaoshuo.com/510.html">天涯客（priest） 简介</a></article>
      <article class="excerpt"><a href="https://www.zhenhunxiaoshuo.com/516.html">第1章 天窗</a></article>
      <article class="excerpt"><a href="https://www.zhenhunxiaoshuo.com/678.html">番外二 前世今生</a></article>
    </div>
  </body>
</html>
"""

CHAPTER_HTML = """
<html><body>
  <article class="article-content">
    <p>番外二 前世今生</p>
    <p>（阿湘和小曹的番外，奉上。）</p>
    <p>有的人死了，回想过自己的一生。</p>
    <p>-----</p>
    <p>黄泉路有多长――多长能忘得了，就有多长。</p>
  </article>
</body></html>
"""


class ZhenhunProviderTests(unittest.TestCase):
    def test_book_page_reads_full_width_author_and_skips_intro_post(self) -> None:
        meta, refs = parser.parse_book_page(BOOK_HTML, "tianyake")

        self.assertEqual(meta.author, "priest")
        self.assertEqual(meta.intro_paragraphs, ["一入江湖岁月催"])
        self.assertEqual([ref.title for ref in refs], ["第1章 天窗", "番外二 前世今生"])
        self.assertEqual([ref.order for ref in refs], [0, 1])

    def test_category_title_names_author(self) -> None:
        html = BOOK_HTML.replace(
            "天涯客（priest）</title>", "天涯客_priest小说作品【全文+番外】 - 镇魂小说网</title>"
        )

        meta, _ = parser.parse_book_page(html, "tianyake")

        self.assertEqual(meta.author, "priest")

    def test_unnumbered_post_is_one_chapter_titled_by_directory_entry(self) -> None:
        ref = parser.ChapterRef("番外二 前世今生", "https://example.test/678.html", "678", 1)

        sections = parser.parse_chapter_page(CHAPTER_HTML, ref)
        chapters = parser._sections_to_chapters([sections])

        self.assertEqual([chapter.title for chapter in chapters], ["番外二 前世今生"])
        self.assertEqual(
            chapters[0].paragraphs,
            [
                "（阿湘和小曹的番外，奉上。）",
                "有的人死了，回想过自己的一生。",
                "黄泉路有多长――多长能忘得了，就有多长。",
            ],
        )

    def test_numbered_sections_keep_section_titles(self) -> None:
        html = """
        <article class="article-content">
          <p>1</p><p>第一段。</p><p>2</p><p>第二段。</p>
        </article>
        """
        ref = parser.ChapterRef("合集", "https://example.test/1.html", "1", 0)

        chapters = parser._sections_to_chapters([parser.parse_chapter_page(html, ref)])

        self.assertEqual([chapter.title for chapter in chapters], ["第1节", "第2节"])

    def test_empty_post_is_reported_instead_of_imported(self) -> None:
        ref = parser.ChapterRef("第1章", "https://example.test/1.html", "1", 0)

        self.assertEqual(
            parser.parse_chapter_page('<article class="article-content"></article>', ref),
            [],
        )


if __name__ == "__main__":
    unittest.main()
