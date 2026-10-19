"""Build the side-by-side cover review page for one restoration round."""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from urllib.parse import quote

from PIL import Image


def _describe(path: Path) -> dict:
    data = path.read_bytes()
    with Image.open(path) as image:
        width, height = image.size
    return {
        "src": quote(path.name),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "size": f"{width}×{height}",
    }


def build_review(manifest_path: Path, output: Path) -> Path:
    """Write ``output`` beside the manifest; image paths are relative to it.

    The manifest lists only covers changed this round:
    ``{"round": str, "items": [{"id", "title", "original", "proposed", "notes"?}]}``.
    """
    manifest = json.loads(manifest_path.read_text())
    root = manifest_path.parent
    if output.parent.resolve() != root.resolve():
        raise ValueError("Write the review page beside its manifest and images")
    items = []
    for item in manifest["items"]:
        original, proposed = root / item["original"], root / item["proposed"]
        if original.parent.resolve() != root.resolve() or proposed.parent.resolve() != root.resolve():
            raise ValueError("Review images must sit beside the manifest")
        items.append(
            {
                "id": item["id"],
                "title": item["title"],
                "notes": item.get("notes", ""),
                "original": _describe(original),
                "proposed": _describe(proposed),
            }
        )
    if not items:
        raise ValueError("A review round needs at least one changed cover")
    payload = {"round": manifest["round"], "items": items}
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    data = json.dumps({**payload, "manifest_sha256": digest}, ensure_ascii=False)
    output.write_text(PAGE.replace("__DATA__", data.replace("</", "<\\/")).replace(
        "__TITLE__", html.escape(f"Cover review · {manifest['round']}")
    ))
    return output


PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#f5f4ef;--card:#fffefa;--ink:#24261f;--muted:#6a6d60;--line:#dcdccf;--accent:#4f6a43;--warn:#9a5b2e}
@media (prefers-color-scheme:dark){:root{--bg:#191a17;--card:#23241f;--ink:#ecebe3;--muted:#a4a597;--line:#3a3b33;--accent:#9cc28a;--warn:#e0a46f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"PingFang SC","Segoe UI",sans-serif}
header,main{max-width:1200px;margin:auto;padding:24px 16px}h1{margin:0 0 6px;font-size:28px}.muted{color:var(--muted)}
.bar{position:sticky;top:0;z-index:2;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;justify-content:center}
button{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:7px 12px;cursor:pointer}
button.primary{background:var(--accent);color:var(--bg);border-color:var(--accent)}
article{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin:0 0 22px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media (max-width:640px){.pair{grid-template-columns:1fr}}
figure{margin:0}figure img{width:100%;max-height:70vh;object-fit:contain;background:#8882;border-radius:8px;cursor:zoom-in}
figcaption{font-size:13px;color:var(--muted);margin-top:6px}
.choices{display:flex;gap:14px;flex-wrap:wrap;margin-top:14px}.choices label{display:flex;gap:6px;align-items:center}
textarea{width:100%;min-height:64px;margin-top:10px;font:inherit;padding:8px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--ink)}
.need{color:var(--warn);font-size:13px}
dialog{width:min(96vw,1600px);height:92vh;border:1px solid var(--line);border-radius:12px;padding:0;background:var(--card);color:var(--ink)}
dialog .tools{display:flex;gap:8px;padding:10px;border-bottom:1px solid var(--line);align-items:center;flex-wrap:wrap}
dialog .views{display:grid;grid-template-columns:1fr 1fr;height:calc(100% - 56px)}
dialog .view{overflow:auto;border-right:1px solid var(--line)}dialog .view img{display:block;max-width:none}
</style></head><body>
<header><h1>Cover review</h1><p class="muted" id="intro"></p></header>
<div class="bar"><span id="count"></span><button class="primary" id="download">Download decisions</button></div>
<main id="list"></main>
<dialog id="zoom"><div class="tools"><strong id="ztitle"></strong>
<button data-z="fit">Fit</button><button data-z="1">100%</button><button data-z="2">200%</button><button data-z="4">400%</button>
<span class="muted">Both sides scroll together.</span><button id="zclose" style="margin-left:auto">Close</button></div>
<div class="views"><div class="view" id="vo"><img id="zo" alt=""></div><div class="view" id="vp"><img id="zp" alt=""></div></div></dialog>
<script>
const DATA = __DATA__;
const key = "bookflow-cover-review:" + DATA.manifest_sha256;
let decisions = {};
try { decisions = JSON.parse(localStorage.getItem(key) || "{}"); } catch (e) {}
const save = () => { try { localStorage.setItem(key, JSON.stringify(decisions)); } catch (e) {} render(); };
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
document.getElementById("intro").textContent = `Round ${DATA.round}: ${DATA.items.length} changed cover(s). Original on the left, proposal on the right. Click an image to zoom.`;
const list = document.getElementById("list");
DATA.items.forEach(item => {
  const a = document.createElement("article");
  const fig = (side, label) => `<figure><img src="${item[side].src}" alt="${esc(item.title)} ${label}" data-id="${esc(item.id)}"><figcaption>${label} · ${item[side].size} · ${(item[side].bytes/1000).toFixed(0)} KB</figcaption></figure>`;
  a.innerHTML = `<h2>${esc(item.title)}</h2>${item.notes ? `<p class="muted">${esc(item.notes)}</p>` : ""}
    <div class="pair">${fig("original","Original")}${fig("proposed","Proposed")}</div>
    <div class="choices">${["accept","keep_original","regenerate"].map(v => `<label><input type="radio" name="d-${esc(item.id)}" value="${v}"> ${{accept:"Accept",keep_original:"Keep original",regenerate:"Regenerate with comment"}[v]}</label>`).join("")}</div>
    <textarea placeholder="Comment (required to regenerate)"></textarea><div class="need"></div>`;
  a.querySelectorAll("input").forEach(r => r.addEventListener("change", () => { decisions[item.id] = {...decisions[item.id], decision: r.value}; save(); }));
  const t = a.querySelector("textarea");
  t.value = (decisions[item.id] || {}).comment || "";
  t.addEventListener("input", () => { decisions[item.id] = {...decisions[item.id], comment: t.value}; save(); });
  a.querySelectorAll("img").forEach(img => img.addEventListener("click", () => openZoom(item)));
  a.dataset.id = item.id;
  list.appendChild(a);
});
function render() {
  let done = 0;
  list.querySelectorAll("article").forEach(a => {
    const d = decisions[a.dataset.id] || {};
    a.querySelectorAll("input").forEach(r => r.checked = r.value === d.decision);
    const missing = d.decision === "regenerate" && !(d.comment || "").trim();
    a.querySelector(".need").textContent = missing ? "Add a comment describing what to change." : "";
    if (d.decision && !missing) done++;
  });
  document.getElementById("count").textContent = `${done} of ${DATA.items.length} decided`;
}
render();
document.getElementById("download").addEventListener("click", () => {
  const out = {round: DATA.round, manifest_sha256: DATA.manifest_sha256, items: {}};
  DATA.items.forEach(i => { const d = decisions[i.id] || {}; out.items[i.id] = {decision: d.decision || null, comment: (d.comment || "").trim(), proposed_sha256: i.proposed.sha256, original_sha256: i.original.sha256}; });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 2)], {type: "application/json"}));
  link.download = `cover-decisions-${DATA.round}.json`; link.click();
});
const zoom = document.getElementById("zoom"), vo = document.getElementById("vo"), vp = document.getElementById("vp");
let scale = "fit";
function openZoom(item) {
  document.getElementById("ztitle").textContent = item.title;
  document.getElementById("zo").src = item.original.src; document.getElementById("zp").src = item.proposed.src;
  zoom.showModal(); applyZoom();
}
// Both sides use the wider image's pixels, so the same region lines up.
function applyZoom() {
  const imgs = [document.getElementById("zo"), document.getElementById("zp")];
  const fit = () => {
    if (!imgs.every(img => img.complete && img.naturalWidth)) return;
    const width = Math.max(...imgs.map(img => img.naturalWidth));
    imgs.forEach((img, i) => {
      const view = [vo, vp][i];
      if (scale === "fit") { img.style.width = ""; img.style.maxWidth = "100%"; img.style.maxHeight = (view.clientHeight - 4) + "px"; }
      else { img.style.maxWidth = "none"; img.style.maxHeight = "none"; img.style.width = (width * scale) + "px"; }
    });
  };
  imgs.forEach(img => img.onload = fit);
  fit();
}
zoom.querySelectorAll("[data-z]").forEach(b => b.addEventListener("click", () => { scale = b.dataset.z === "fit" ? "fit" : Number(b.dataset.z); applyZoom(); }));
let syncing = false;
[[vo,vp],[vp,vo]].forEach(([from, to]) => from.addEventListener("scroll", () => {
  if (syncing) return; syncing = true;
  to.scrollLeft = from.scrollLeft * (to.scrollWidth / Math.max(1, from.scrollWidth));
  to.scrollTop = from.scrollTop * (to.scrollHeight / Math.max(1, from.scrollHeight));
  requestAnimationFrame(() => syncing = false);
}));
document.getElementById("zclose").addEventListener("click", () => zoom.close());
</script></body></html>
"""
