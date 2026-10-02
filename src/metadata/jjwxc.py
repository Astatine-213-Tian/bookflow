from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


TIME_AREAS = ("近代现代", "古色古香", "架空历史", "幻想未来")
GENRES = (
    "爱情",
    "武侠",
    "奇幻",
    "仙侠",
    "游戏",
    "传奇",
    "科幻",
    "童话",
    "惊悚",
    "悬疑",
    "剧情",
    "轻小说",
    "古典衍生",
    "东方衍生",
    "西方衍生",
    "其他衍生",
)

ARTICLE_TYPE_RE = re.compile(
    r"文章类型：</span>\s*<span[^>]*itemprop=[\"']genre[\"'][^>]*>\s*(.*?)\s*</span>",
    re.S,
)
TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class JjwxcTypeMetadata:
    article_type: str
    time_area: str
    genre: str
    source: str


@dataclass(frozen=True)
class JjwxcChapter:
    number: int
    title: str
    url: str | None


@dataclass(frozen=True)
class JjwxcVolume:
    title: str
    chapters: tuple[JjwxcChapter, ...]


@dataclass(frozen=True)
class JjwxcContents:
    source: str
    volumes: tuple[JjwxcVolume, ...]

    @property
    def chapter_count(self) -> int:
        return sum(len(volume.chapters) for volume in self.volumes)

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "chapter_count": self.chapter_count,
            "volumes": [
                {
                    "title": volume.title,
                    "chapters": [asdict(chapter) for chapter in volume.chapters],
                }
                for volume in self.volumes
            ],
        }


def parse_jjwxc_contents(html: str, *, novel_id: str) -> JjwxcContents:
    """Read volume boundaries from directory rows, never from title wording."""
    if not novel_id.isdigit():
        raise ValueError("Jinjiang contents require a numeric novel ID")
    soup = BeautifulSoup(html, "html.parser")
    # itemprop is a token list: the latest row is `chapter newestChapter`.
    chapter_rows = soup.select('tr[itemprop~="chapter"]')
    if not chapter_rows:
        raise ValueError("Jinjiang page has no readable chapter directory")
    table = chapter_rows[0].find_parent("table")
    if table is None or any(row.find_parent("table") is not table for row in chapter_rows):
        raise ValueError("Jinjiang chapter directory has an ambiguous table structure")
    groups: list[tuple[str, list[JjwxcChapter]]] = []
    previous_number = 0
    for row in table.find_all("tr"):
        if row.find_parent("table") is not table:
            continue
        is_chapter = "chapter" in row.get("itemprop", "").split()
        marker = row.select_one(".volumnfont")
        if marker is not None and marker.find_parent("tr") is row and not is_chapter:
            title = marker.get_text(" ", strip=True)
            if not title:
                raise ValueError("Jinjiang directory contains an empty volume title")
            groups.append((title, []))
            continue
        if not is_chapter:
            continue
        first_cell = row.find("td", recursive=False)
        number_text = first_cell.get_text(strip=True) if first_cell else ""
        if not number_text.isdigit() or int(number_text) <= previous_number:
            raise ValueError("Jinjiang chapter numbers are missing, duplicated, or out of order")
        number = int(number_text)
        headline = row.select_one('[itemprop~="headline"]')
        if headline is None:
            raise ValueError(f"Jinjiang chapter {number} has no headline")
        link = next(
            (node for node in headline.select('a[itemprop~="url"]') if node.get_text(strip=True)),
            None,
        )
        title = (link if link is not None else headline).get_text(" ", strip=True)
        if not title:
            raise ValueError(f"Jinjiang chapter {number} has an empty title")
        url = None
        if link is not None:
            for attribute in ("href", "rel"):
                value = link.get(attribute, "")
                if isinstance(value, list):
                    value = " ".join(value)
                query = parse_qs(urlparse(value).query)
                chapter_id = query.get("chapterid", [""])[0]
                if not chapter_id:
                    continue
                if not chapter_id.isdigit() or query.get("novelid") != [novel_id]:
                    raise ValueError(f"Jinjiang chapter {number} links to an unexpected work")
                url = f"https://www.jjwxc.net/onebook.php?novelid={novel_id}&chapterid={chapter_id}"
                break
        if not groups:
            groups.append(("", []))
        groups[-1][1].append(JjwxcChapter(number, title, url))
        previous_number = number
    return JjwxcContents(
        source=f"https://www.jjwxc.net/onebook.php?novelid={novel_id}",
        volumes=tuple(JjwxcVolume(title, tuple(chapters)) for title, chapters in groups),
    )


def novel_id_from_url(value: str) -> str:
    parsed = urlparse(value)
    query = parse_qs(parsed.query)
    novel_id = query.get("novelid", [""])[0]
    if novel_id:
        return novel_id
    if value.isdigit():
        return value
    return ""


def parse_article_type(value: str, *, source: str = "jjwxc") -> JjwxcTypeMetadata | None:
    cleaned = TAG_RE.sub("", value or "")
    cleaned = re.sub(r"\s+", "", cleaned)
    if not cleaned:
        return None
    parts = [part for part in cleaned.split("-") if part]
    time_area = next((part for part in parts if part in TIME_AREAS), "")
    genre = next((part for part in parts if part in GENRES), "")
    if not time_area and len(parts) >= 3 and parts[2] in TIME_AREAS:
        time_area = parts[2]
    if not genre and len(parts) >= 4 and parts[3] in GENRES:
        genre = parts[3]
    if not genre:
        genre = infer_genre(cleaned)
    if not time_area:
        time_area = infer_time_area(cleaned)
    return JjwxcTypeMetadata(cleaned, time_area, genre, source)


def parse_jjwxc_book_page(html: str) -> JjwxcTypeMetadata | None:
    match = ARTICLE_TYPE_RE.search(html)
    if not match:
        return None
    return parse_article_type(match.group(1), source="jjwxc")


def fetch_jjwxc_type(value: str, *, timeout: int = 20) -> JjwxcTypeMetadata | None:
    novel_id = novel_id_from_url(value)
    if not novel_id:
        return None
    req = Request(
        f"https://www.jjwxc.net/onebook.php?novelid={novel_id}",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    data = urlopen(req, timeout=timeout).read()
    html = data.decode("gb18030", "replace")
    return parse_jjwxc_book_page(html)


def infer_time_area(text: str) -> str:
    if re.search(r"星际|未来|末世|虫族|机甲|AI|机器人|宇宙|银河", text, re.I):
        return "幻想未来"
    if re.search(r"架空|皇|帝|王爷|朝堂|宫廷|将军|侯|国师|锦衣卫|战国|天宝|江山", text):
        return "架空历史"
    if re.search(r"古代|江湖|武林|修仙|仙尊|神魔|妖|剑|侠|山海", text):
        return "古色古香"
    return "近代现代"


def infer_genre(text: str) -> str:
    if re.search(r"无限|副本|逃生|恐怖|鬼|死亡|梦魇|惊悚", text):
        return "惊悚"
    if re.search(r"悬疑|刑侦|破案|案件|犯罪|律师|审判|侦探", text):
        return "悬疑"
    if re.search(r"电竞|网游|游戏|直播|玩家|系统", text):
        return "游戏"
    if re.search(r"星际|未来|末世|虫族|机甲|机器人|AI|科幻", text, re.I):
        return "科幻"
    if re.search(r"修仙|仙侠|仙尊|灵根|飞升", text):
        return "仙侠"
    if re.search(r"武侠|江湖|武林|剑客|侠", text):
        return "武侠"
    if re.search(r"奇幻|魔|妖|异能|灵魂|神怪", text):
        return "奇幻"
    if "童话" in text:
        return "童话"
    if "传奇" in text:
        return "传奇"
    if "轻小说" in text:
        return "轻小说"
    if "衍生" in text:
        return "其他衍生"
    if "剧情" in text:
        return "剧情"
    return "爱情"


def classify_from_text(title: str, author: str = "", intro: str = "", sample: str = "") -> JjwxcTypeMetadata:
    text = "\n".join(part for part in [title, author, intro, sample[:4000]] if part)
    time_area = infer_time_area(text)
    genre = infer_genre(text)
    return JjwxcTypeMetadata("", time_area, genre, "heuristic")
