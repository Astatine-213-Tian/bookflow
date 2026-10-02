"""Summarize frozen model judgments and build a private, score-free reading page."""
from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path
from typing import Any

from experiments.iteration6.probe import METHODS, ROOT, read, verify_bindings, write

LABELS = {"direct": "原有直接译写", "positive": "直接译写＋正例",
          "contrastive": "直接译写＋纠错对照", "edited": "中文局部编辑＋英文核查"}


def aggregate() -> dict[str, Any]:
    manifest = verify_bindings(ROOT / "sampling_manifest.json")
    verify_bindings(ROOT / "bank_manifest.json")
    verify_bindings(ROOT / "output_manifest.json")
    mappings = read(ROOT / "blind_mapping.json")
    totals = {str(j): {m: Counter() for m in METHODS} for j in (1, 2)}
    flags, invalid, scenes, comparisons = [], [], [], []
    for draw in manifest["draws"]:
        if draw["role"] != "dev":
            continue
        sid = draw["sample_id"]
        sample = read(ROOT / f"samples/{sid}.json")
        mapping = mappings[sid]
        outputs = {m: read(ROOT / f"outputs/{sid}/{m}.json")["paragraphs"] for m in METHODS}
        source = "\n".join([*sample["context_before"], *[r["english"] for r in sample["english"]], *sample["context_after"]])
        counts = {}
        for j in (1, 2):
            counts[str(j)] = {m: Counter() for m in METHODS}
            result = read(ROOT / f"evaluation/{sid}/source_{j}.json")
            for assessment in result["assessments"]:
                method = mapping[assessment["candidate_id"]]
                seen = set()
                for kind in ("wording_errors", "meaning_errors"):
                    for issue in assessment[kind]:
                        entry = {"scene": sid, "judge": j, "method": method, "kind": kind, **issue}
                        if not issue["quote"] or issue["quote"] not in "\n".join(outputs[method]):
                            invalid.append({**entry, "validation_failure": "Candidate quotation is not exact"})
                            continue
                        if kind == "meaning_errors" and (not issue["source_quote"] or issue["source_quote"] not in source):
                            invalid.append({**entry, "validation_failure": "English quotation is not exact"})
                            continue
                        identity = (kind, issue["quote"])
                        if identity in seen:
                            continue
                        seen.add(identity)
                        flags.append(entry)
                        counts[str(j)][method][kind] += 1
                        totals[str(j)][method][kind] += 1
                        if kind == "meaning_errors":
                            counts[str(j)][method][f"meaning_{issue['severity']}"] += 1
                            totals[str(j)][method][f"meaning_{issue['severity']}"] += 1
        gold = read(ROOT / f"gold/{sid}.json")
        style_path = ROOT / f"evaluation/{sid}/style.json"
        style = read(style_path) if style_path.exists() else None
        rank = {mapping[label]: position for position, group in enumerate(style["ranking"]) for label in group} if style else {}
        if rank:
            comparisons.append({"scene": sid, "rank": rank,
                "versus_direct": {m: "win" if rank[m] < rank["direct"] else "tie" if rank[m] == rank["direct"] else "loss" for m in METHODS if m != "direct"}})
        scenes.append({"sample_id": sid, "title": sample["title"], "chapter": sample["chapter"],
            "english_words": sample["english_words"], "source_judge_counts": counts,
            "style_rank": rank, "edition_difference_count": len(gold["edition_differences"]),
            "cjk_counts": {m: sum(len(__import__('re').findall(r'[\u4e00-\u9fff]', t)) for t in values) for m, values in outputs.items()}})
    exposure = sum(x["english_words"] for x in scenes)
    style_vs = {m: dict(Counter(x["versus_direct"][m] for x in comparisons)) for m in METHODS if m != "direct"}
    summary = {"status": "Exploratory model judgments; quotation validation does not validate an error claim.",
        "english_word_exposure_per_method": exposure, "scenes": scenes, "source_judge_totals": totals,
        "wording_flags_per_1000_english_words": {j: {m: round(c["wording_errors"] / exposure * 1000, 2) for m, c in rows.items()} for j, rows in totals.items()},
        "style_versus_direct": style_vs, "flags": flags, "invalid_quoted_flags": invalid,
        "bank": {k: read(ROOT / "bank_manifest.json")[k] for k in ("accepted", "rejected", "prompt_example_ids")}}
    write(ROOT / "summary.json", summary)
    return summary


def reading_page() -> None:
    mappings = read(ROOT / "blind_mapping.json")
    scenes = []
    for sid, mapping in mappings.items():
        sample, gold = read(ROOT / f"samples/{sid}.json"), read(ROOT / f"gold/{sid}.json")
        scenes.append({"id": sid, "title": sample["title"], "chapter": sample["chapter"],
            "english": [x["english"] for x in sample["english"]], "gold": gold["paragraphs"],
            "boundary_notes": gold["boundary_notes"], "differences": gold["edition_differences"],
            "candidates": [{"id": label, "method": LABELS[method], "paragraphs": read(ROOT / f"outputs/{sid}/{method}.json")["paragraphs"]} for label, method in mapping.items()]})
    data = json.dumps(scenes, ensure_ascii=False).replace("<", "\\u003c")
    template = """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>措辞修正实验 · 六组匿名对照</title><style>
:root{font:16px/1.9 system-ui,sans-serif;color:#253329;background:#f4f2ed}body{margin:0}header{background:#e8eee5;padding:22px 4vw}h1{font-size:24px;margin:0}header p{max-width:1000px;margin:7px 0}.controls{display:flex;gap:12px;flex-wrap:wrap;margin-top:14px}select,button{font:inherit;padding:5px 10px;border:1px solid #a9b5a4;border-radius:5px;background:#fff;color:inherit}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin:24px 4vw}article{padding:20px;background:#fff;border:1px solid #d5ddd0;border-radius:8px;min-width:0}article h2{font:600 17px system-ui;color:#566d4f;margin:0 0 20px}article p{font:18px/1.9 'Songti SC','Noto Serif CJK SC',serif;white-space:pre-wrap;margin:0 0 1em}details,footer{margin:20px 4vw}#english{max-width:1050px}#notes p{font-size:14px}a{color:#3f673e}@media(max-width:950px){.grid{grid-template-columns:1fr}}@media(prefers-color-scheme:dark){:root{color:#e0e8dd;background:#192019}header{background:#263123}article,select,button{background:#222a20;border-color:#45553e}article h2,a{color:#b3cdaa}}
</style><header><h1>措辞修正实验 · 六组匿名对照</h1>
<p>从正文随机抽取的新样本。先比较两个匿名版本的自然程度、动作推进和句群节奏，再按需查看作者原文。更短不自动等于更好；英文版本增加或删去的意思已另作记录。</p>
<p>本页不显示机器评分。方法名称默认隐藏；原文和版本差异放在下方，可选择展开。<a href="example_bank.html">查看训练用纠错例库</a></p>
<div class="controls"><label>片段 <select id="scene"></select></label><label>左侧 <select id="left"></select></label><label>右侧 <select id="right"></select></label><button id="reveal">揭示方法名称</button><button id="goldToggle">显示作者原文</button></div></header>
<main class="grid" id="grid"><article><h2 id="leftTitle"></h2><div id="leftText"></div></article><article><h2 id="rightTitle"></h2><div id="rightText"></div></article><article id="goldPanel"><h2>作者中文原文</h2><div id="gold"></div></article></main>
<details><summary>查看英文来源</summary><div id="english"></div></details><details><summary>查看对齐边界与中英版本差异（机器标注，需辨别）</summary><div id="notes"></div></details>
<footer>研究样稿，尚未替换 EPUB。作者中文未交给生成、中文编辑或英文核查步骤。样本来自两部历史题材作品，不能据此推断其他题材效果。例库页面含提示用样本，可在盲读后查看。</footer>
<script id="data" type="application/json">__DATA__</script><script>
const rows=JSON.parse(document.getElementById('data').textContent),el=id=>document.getElementById(id);let reveal=false,showGold=false;
function paras(id,values){el(id).replaceChildren(...values.flatMap(v=>v.split(/\\n+/).filter(x=>x.trim())).map(v=>{const p=document.createElement('p');p.textContent=v;return p}))}
for(const s of rows){const o=document.createElement('option');o.value=s.id;o.textContent=s.id+' · '+s.title+' · 英文第'+s.chapter+'章';el('scene').append(o)}
function draw(){const s=rows.find(x=>x.id===el('scene').value);for(const side of ['left','right']){const c=s.candidates.find(x=>x.id===el(side).value);el(side+'Title').textContent=c.id+(reveal?' · '+c.method:'');paras(side+'Text',c.paragraphs)}paras('gold',s.gold);paras('english',s.english);paras('notes',[...s.boundary_notes,...s.differences.map(d=>d.difference+'\\nEN: '+d.english_quote+'\\nCN: '+d.chinese_quote)]);el('goldPanel').hidden=!showGold;el('grid').style.gridTemplateColumns=window.innerWidth<950?'1fr':showGold?'repeat(3,minmax(0,1fr))':'repeat(2,minmax(0,1fr))';el('reveal').textContent=reveal?'隐藏方法名称':'揭示方法名称';el('goldToggle').textContent=showGold?'隐藏作者原文':'显示作者原文'}
function select(){const s=rows.find(x=>x.id===el('scene').value);for(const side of ['left','right']){el(side).replaceChildren(...s.candidates.map(c=>{const o=document.createElement('option');o.value=c.id;o.textContent=c.id;return o}))}el('right').selectedIndex=1;reveal=false;draw()}
el('scene').onchange=select;el('left').onchange=draw;el('right').onchange=draw;el('reveal').onclick=()=>{reveal=!reveal;draw()};el('goldToggle').onclick=()=>{showGold=!showGold;draw()};window.onresize=draw;select();
</script></html>"""
    (ROOT / "comparison.html").write_text(template.replace("__DATA__", data))


def bank_page() -> None:
    bank = read(ROOT / "bank.json")
    chosen = {x["example_id"] for x in bank["prompt_examples"]}
    entries = []
    esc = html.escape
    for x in bank["accepted"]:
        fields = [("直接译稿", x["before"]), ("最小修正", x["after"]), ("措辞问题", x["reason"]),
                  ("英文依据（上下文，未必与修正片段等长）", x["english_support"]),
                  ("作者用语证据", x["author_anchor"]), ("独立复核", x["review_reason"])]
        entries.append(f'<article><h2>{esc(x["example_id"])} · {esc(x["title"])}'+(' · 已用于提示' if x['example_id'] in chosen else '')+'</h2>'+''.join(f'<h3>{esc(k)}</h3><p>{esc(v)}</p>' for k,v in fields)+'</article>')
    rejects = ''.join(f'<li>{esc(x["example_id"])}: {esc(x.get("review_reason", "; ".join(x.get("rejection_reasons", []))))}</li>' for x in bank['rejected'])
    text = '<!doctype html><meta charset="utf-8"><title>训练措辞例库</title><style>body{font:17px/1.8 system-ui;max-width:1000px;margin:30px auto;padding:0 20px;background:#f4f2ed;color:#263629}article{background:white;border:1px solid #ccd5c8;padding:22px;margin:22px 0}h1{font-size:26px}h2{font-size:20px}h3{font-size:15px;color:#657b5c;margin-bottom:4px}p{margin-top:0;white-space:pre-wrap}</style><h1>训练措辞例库</h1><p>从固定随机样本产生的直接译稿中提取。英文是内容依据；作者原文只作为表达证据。仅纳入独立复核最终认可的明确措辞问题，保留拒绝记录。局部修正不是整段回译。</p>' + ''.join(entries) + '<details><summary>未纳入的候选</summary><ul>' + rejects + '</ul></details>'
    (ROOT / "example_bank.html").write_text(text)


def main() -> None:
    summary = aggregate()
    reading_page()
    bank_page()
    print(json.dumps({k: summary[k] for k in ("english_word_exposure_per_method", "source_judge_totals", "style_versus_direct", "bank")}, ensure_ascii=False, indent=2))
    print(ROOT / "comparison.html")


if __name__ == "__main__":
    main()
