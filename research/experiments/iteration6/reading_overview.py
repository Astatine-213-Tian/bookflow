"""Render every frozen comparison together so no passage is hidden in a selector."""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path

from bs4 import BeautifulSoup

from experiments.iteration6.runtime import ROOT, read, write


def paragraphs(values: list[str]) -> str:
    return "".join(f"<p>{html.escape(text)}</p>" for value in values
                   for text in value.splitlines() if text.strip())


def render(rows: list[dict]) -> str:
    count = len(rows)
    links, sections = [], []
    for number, row in enumerate(rows, 1):
        sid = html.escape(row["id"], quote=True)
        title = html.escape(row["title"])
        links.append(f'<a href="#{sid}">第 {number} 组 · {title}</a>')
        candidates = "".join(
            f'<article data-candidate="{html.escape(candidate["id"], quote=True)}">'
            f'<h3>第 {number} 组 · {html.escape(candidate["id"])}</h3>'
            f'{paragraphs(candidate["paragraphs"])}</article>'
            for candidate in row["candidates"]
        )
        methods = "".join(f'<tr><th scope="row">{html.escape(c["id"])}</th>'
                          f'<td>{html.escape(c["method"])}</td></tr>' for c in row["candidates"])
        notes = row["boundary_notes"] + [x["difference"] for x in row["differences"]]
        sections.append(f'''<section id="{sid}" class="scene" aria-labelledby="{sid}-title">
<h2 id="{sid}-title">第 {number} / {count} 组 · 《{title}》</h2>
<p class="meta">{sid} · 英文第 {row['chapter']} 章 · 4 个候选均已展开</p>
<div class="candidates">{candidates}</div>
<details class="reference"><summary>第 {number} 组：查看作者中文原文</summary>{paragraphs(row['gold'])}</details>
<details><summary>第 {number} 组：查看英文来源与版本差异</summary>{paragraphs(row['english'])}<h3>对齐说明</h3>{paragraphs(notes)}</details>
<details class="methods"><summary>第 {number} 组：揭示方法名称</summary><table><tbody>{methods}</tbody></table></details>
<a class="back" href="#top">回到六组目录 ↑</a></section>''')
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>六组对照 · 全部展开</title><style>
:root{color-scheme:light dark;font:16px/1.85 system-ui,sans-serif;background:#f4f2ed;color:#253329}
*{box-sizing:border-box}body{margin:0}header{padding:26px 4vw 18px;background:#e8eee5}h1{font-size:27px;margin:0 0 8px}header p{margin:5px 0;max-width:1050px}
nav{position:sticky;top:0;z-index:2;display:flex;flex-wrap:wrap;gap:8px;padding:12px 4vw;background:#e8eee5;border-bottom:1px solid #bcc9b6}
a{color:#315e34}nav a{padding:4px 12px;text-decoration:none;border:1px solid #a9b7a0;border-radius:6px;background:#fff;font-size:14px}a:hover{background:#dce7d5}
main{padding:0 4vw}.scene{padding:30px 0 38px;border-bottom:2px solid #bcc9b6;scroll-margin-top:130px}h2{font-size:23px;margin:0}.meta{color:#64765c;margin:4px 0 18px}
.candidates{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}article{background:#fff;padding:24px;border:1px solid #d0d8ca;border-radius:8px;min-width:0}article h3{margin:0 0 18px;color:#536d48;font:600 17px system-ui}article p,.reference p{font:18px/1.95 'Songti SC','Noto Serif CJK SC',serif;white-space:pre-wrap;margin:0 0 1em}
details{margin:14px 0;padding:12px 16px;border:1px solid #c8d3c0;border-radius:6px}summary{cursor:pointer;font-weight:600}details p{white-space:pre-wrap}table{border-collapse:collapse;margin-top:12px}th,td{text-align:left;padding:6px 18px 6px 0}.back{display:inline-block;margin-top:12px}footer{padding:22px 4vw;color:#65765c}
@media(max-width:750px){.candidates{grid-template-columns:1fr}article{padding:18px}nav{gap:6px;padding:8px 3vw}nav a{padding:3px 8px;font-size:13px}.scene{scroll-margin-top:160px}h1{font-size:23px}}
@media(prefers-color-scheme:dark){:root{background:#192019;color:#e0e8dd}header,nav{background:#263123}article,nav a{background:#222a20;border-color:#45553e}article h3,a{color:#bed8b4}a:hover{background:#34452e}.meta,footer{color:#b2c4aa}details,.scene,nav{border-color:#45553e}}
</style></head><body><header id="top"><h1>六组对照，全部展开</h1>
<p>共 <strong>6 组 × 4 个候选</strong>。向下滚动就能看到全部片段，也可以直接点击目录跳转。</p>
<p>A / B / C / D 只在各自组内有效，不代表固定方法。反馈时请写“第几组 + 候选字母”。</p>
</header><nav aria-label="六组对照目录">''' + "".join(links) + '''</nav><main>''' + "".join(sections) + '''</main>
<footer>使用同一批六组译文，仅调整展示方式。作者原文及方法名称可逐组展开；本页不显示机器评分。</footer></body></html>'''


def main() -> None:
    source = ROOT / "comparison.html"
    soup = BeautifulSoup(source.read_text(), "html.parser")
    rows = json.loads(soup.find("script", id="data").string)
    assert len(rows) == 6 and all(len(row["candidates"]) == 4 for row in rows)
    target = ROOT / "comparison.all.html"
    target.write_text(render(rows), encoding="utf-8")
    check = BeautifulSoup(target.read_text(), "html.parser")
    assert len(check.select("section.scene")) == 6 and len(check.select("article")) == 24
    for row in rows:
        section = check.find("section", id=row["id"])
        for candidate in row["candidates"]:
            article = section.find("article", attrs={"data-candidate": candidate["id"]})
            expected = [line for value in candidate["paragraphs"] for line in value.splitlines() if line.strip()]
            assert [node.get_text() for node in article.find_all("p")] == expected
    write(ROOT / "reading_overview_manifest.json", {
        "purpose": "Display-only response to user seeing a single comparison; no resampling or regeneration.",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "scene_count": 6, "candidate_count": 24, "paragraph_readback": "exact",
    })
    print(target)


if __name__ == "__main__":
    main()
