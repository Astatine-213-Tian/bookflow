"""Build a private, self-contained reading page without showing model scores."""
from __future__ import annotations

import json

from experiments.iteration5.pilot import ROOT, SCENES, evaluation_packet, verify_lock


def main() -> None:
    manifest = verify_lock()
    scenes = []
    for sid, *_ in SCENES:
        packet, names = evaluation_packet(sid, manifest)
        scenes.append({**packet, "method_key": names})
    data = json.dumps(scenes, ensure_ascii=False).replace("<", "\\u003c")
    template = """<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>作者文风 · 四组盲读对照</title>
<style>
:root{color-scheme:light dark;font:16px/1.9 system-ui,sans-serif}body{margin:0;background:#f4f2ed;color:#232923}
header{padding:24px 4vw 18px;background:#e8ede5;border-bottom:1px solid #c7d0c5}h1{font-size:24px;margin:0 0 8px}
header p{max-width:900px;margin:4px 0;color:#465345}button,select{font:inherit;padding:5px 12px;border:1px solid #9aa795;border-radius:5px;background:#fff;color:#232923}
.controls{display:flex;gap:16px;flex-wrap:wrap;align-items:center;margin-top:14px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;padding:24px 4vw}
article{background:#fff;border:1px solid #d6dbd1;border-radius:8px;padding:20px;min-width:0}article h2{font:600 17px system-ui;margin:0 0 20px;color:#536650}
article p{font-family:"Songti SC","Noto Serif CJK SC",serif;white-space:pre-wrap;margin:0 0 1em;font-size:18px;line-height:1.9}details{margin:0 4vw 40px}#english p{max-width:1000px}
.meta{font:14px system-ui;color:#747e6f;margin:10px 0}footer{margin:15px 4vw 40px;font-size:14px;color:#596853}
@media(max-width:900px){.grid{grid-template-columns:1fr}article{padding:16px}header{padding:18px 4vw}}
@media(prefers-color-scheme:dark){body{background:#171c17;color:#e7eadf}header{background:#222c22;border-color:#40503d}header p{color:#bccbb6}article{background:#202720;border-color:#40503d}article h2{color:#b9d1ab}button,select{background:#202720;color:#e7eadf}.meta,footer{color:#b2bea9}}
</style>
<header><h1>作者文风 · 四组盲读对照</h1>
<p>原文在左，任选两个匿名版本比较。关注句群节奏、对白、叙述口吻和措辞；更华丽或更短，不一定更像作者。英文与中文版本的局部差异不等于候选译错。</p>
<p>四组均来自同一篇《乱世为王》新番外。这里不显示机器评分，方法名称默认隐藏。所有文本只从本地文件读取。</p>
<div class="controls"><label>场景 <select id="scene"></select></label><label>中间 <select id="left"></select></label><label>右边 <select id="right"></select></label><button id="reveal">揭示方法名称</button></div></header>
<main class="grid"><article><h2>作者中文原文</h2><div class="meta" id="goldMeta"></div><div id="gold"></div></article><article><h2 id="leftTitle"></h2><div class="meta" id="leftMeta"></div><div id="leftText"></div></article><article><h2 id="rightTitle"></h2><div class="meta" id="rightMeta"></div><div id="rightText"></div></article></main>
<details><summary>查看对应英文来源</summary><div id="english"></div></details>
<footer>这是研究样稿，不是新版 EPUB。作者原文未交给候选生成步骤；不同版本可以重新分段，逐行位置不表示语义对齐。</footer>
<script id="dataset" type="application/json">__DATA__</script>
<script>
const data=JSON.parse(document.getElementById('dataset').textContent);
const labels={neutral:'中性翻译',method4:'现有 Method4',direct_scene:'直接整场景译写',ledger_scene:'内容清单重建'};
const el=id=>document.getElementById(id);let revealed=false;
for(const s of data){const o=document.createElement('option');o.value=s.sample_id;o.textContent=s.sample_id;el('scene').append(o)}
function visibleParagraphs(values){return values.flatMap(text=>text.split(/\\n+/).filter(p=>p.trim()))}
function paragraphs(id,values){el(id).replaceChildren(...visibleParagraphs(values).map(text=>{const p=document.createElement('p');p.textContent=text;return p}))}
function draw(){const s=data.find(s=>s.sample_id===el('scene').value);paragraphs('gold',s.author_reference_zh);el('goldMeta').textContent=visibleParagraphs(s.author_reference_zh).length+' 段';
for(const side of ['left','right']){const c=s.candidates.find(c=>c.candidate_id===el(side).value);paragraphs(side+'Text',c.paragraphs);el(side+'Title').textContent=c.candidate_id+(revealed?' · '+labels[s.method_key[c.candidate_id]]:'');el(side+'Meta').textContent=visibleParagraphs(c.paragraphs).length+' 段'}paragraphs('english',s.english_source.map(r=>r.english));el('reveal').textContent=revealed?'隐藏方法名称':'揭示方法名称'}
function selectScene(){const s=data.find(s=>s.sample_id===el('scene').value);for(const side of ['left','right']){el(side).replaceChildren(...s.candidates.map(c=>{const o=document.createElement('option');o.value=c.candidate_id;o.textContent=c.candidate_id;return o}))}el('right').selectedIndex=1;revealed=false;draw()}
el('scene').onchange=selectScene;el('left').onchange=draw;el('right').onchange=draw;el('reveal').onclick=()=>{revealed=!revealed;draw()};selectScene();
</script></html>"""
    output = ROOT / "comparison.html"
    output.write_text(template.replace("__DATA__", data), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
