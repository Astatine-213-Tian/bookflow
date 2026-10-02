'use strict';
const el = id => document.getElementById(id), cacheKey = 'style-paired48-iteration9-v1';
let data = {cases: [], ready_new: 0}, saved = {}, pending = {}, currentKey = '', noteTimer, saving = Promise.resolve();
try { pending = JSON.parse(localStorage.getItem(cacheKey) || '{}').pending || {}; } catch {}
function status(text, error = false) { el('saveStatus').textContent = text; el('saveStatus').classList.toggle('error', error); }
function persist() { try { localStorage.setItem(cacheKey, JSON.stringify({pending})); } catch { status('浏览器暂存不可用；请确认本地保存成功', true); } }
function current() { return data.cases.find(c => c.key === currentKey); }
function subset() { return data.cases.filter(c => (el('scope').value === 'all' || c.reading_stage === el('scope').value) && (el('book').value === 'all' || c.title === el('book').value)); }
function voteFor(c) { const v = pending[c.key] || saved[c.key]; return v && v.display_manifest_sha256 === c.display_manifest_sha256 ? v : null; }
function isRated(c) { const v = voteFor(c); return !!v && !['unrated', 'skip'].includes(v.choice); }
function description(v) { if (!v || v.choice === 'unrated') return '尚未选择'; if (v.choice === 'preferred') return '偏好 ' + v.candidate_ids[0]; return {tie: '两个差不多', none: '都不理想', skip: '已暂时跳过'}[v.choice]; }
function drawProse(node, candidate) { const chars = Array.from(candidate.text); let start = 0; for (const [a, b] of candidate.highlights) { node.append(document.createTextNode(chars.slice(start, a).join(''))); const mark = document.createElement('mark'); mark.textContent = chars.slice(a, b).join(''); node.append(mark); start = b; } node.append(document.createTextNode(chars.slice(start).join(''))); }
function renderDirectory() {
  const rows = subset();
  el('directory').replaceChildren(...rows.map(c => { const b = document.createElement('button'); b.textContent = c.number; b.title = c.title + ' · 第' + c.volume + '卷 · 来源第' + c.chapter + '章'; b.classList.toggle('current', c.key === currentKey); b.classList.toggle('rated', isRated(c)); b.onclick = () => navigate(c.key); return b; }));
  el('progress').textContent = data.ready_new + '/48 组就绪 · 已反馈 ' + data.cases.filter(isRated).length + '/48 · 当前范围 ' + rows.filter(isRated).length + '/' + rows.length;
  const first = data.cases.filter(c => c.reading_stage === 'first12');
  el('checkpoint').hidden = first.length !== 12 || !first.every(isRated);
}
function renderChoices() {
  const c = current(); if (!c) return;
  const vote = voteFor(c);
  for (const card of document.querySelectorAll('.candidate')) { const selected = !!vote && vote.candidate_ids.includes(card.dataset.candidate); card.classList.toggle('selected', selected); const button = card.querySelector('button'); button.setAttribute('aria-pressed', String(selected)); button.textContent = selected ? '已选 ' + card.dataset.candidate : '更像作者：' + card.dataset.candidate; }
  const stale = pending[c.key] && pending[c.key].display_manifest_sha256 !== c.display_manifest_sha256;
  status(stale ? '旧版本反馈已暂存，请按当前文本重新选择' : pending[c.key] ? '正在保存…' : vote ? '已保存 · ' + description(vote) : description(vote), !!stale);
  renderDirectory();
}
function render() {
  const c = current();
  for (const id of ['allTie', 'none', 'skip', 'clear', 'note']) el(id).disabled = !c;
  el('author').replaceChildren(); el('candidates').replaceChildren();
  if (!c) { el('notice').textContent = '这个范围的片段尚未就绪。'; el('sampleTitle').textContent = ''; el('note').value = ''; el('prev').disabled = true; el('next').disabled = true; status('尚未选择'); renderDirectory(); return; }
  const rows = subset(), index = rows.findIndex(x => x.key === c.key);
  el('sample').value = c.key; el('prev').disabled = index <= 0; el('next').disabled = index >= rows.length - 1;
  el('sampleTitle').textContent = '第 ' + c.number + ' / 48 组 · 《' + c.title + '》 · 第 ' + c.volume + ' 卷';
  el('notice').textContent = c.identical_candidates ? '本组两版文字完全相同，可选“两个差不多”。' : data.ready_new < 48 ? '片段陆续就绪，当前内容不会自动切换。' : '';
  el('author').replaceChildren(...c.author.map(text => { const p = document.createElement('p'); p.textContent = text; return p; }));
  el('candidates').replaceChildren(...c.candidates.map(candidate => { const card = document.createElement('article'); card.className = 'candidate'; card.dataset.candidate = candidate.id; const head = document.createElement('div'); head.className = 'candidate-head'; const h = document.createElement('h3'); h.textContent = '候选 ' + candidate.id; const button = document.createElement('button'); button.type = 'button'; button.onclick = () => choose(candidate.id); head.append(h, button); const prose = document.createElement('div'); prose.className = 'prose'; drawProse(prose, candidate); card.append(head, prose); return card; }));
  el('note').value = voteFor(c)?.note || ''; renderChoices();
}
function populate() { const rows = subset(); el('sample').replaceChildren(...rows.map(c => { const o = document.createElement('option'); o.value = c.key; o.textContent = c.number + ' / 48 · ' + c.title + ' · 第' + c.chapter + '章'; return o; })); if (!rows.some(c => c.key === currentKey)) currentKey = rows[0]?.key || ''; render(); }
function capture(choice, ids, note) { const c = current(); return {sample_key: c.key, display_manifest_sha256: c.display_manifest_sha256, choice, candidate_ids: ids, note, view: {highlights_enabled: el('highlight').checked, reading_scope: el('scope').value}}; }
function queueVote(payload) {
  pending[payload.sample_key] = payload; persist(); renderChoices();
  saving = saving.then(async () => { if (pending[payload.sample_key] !== payload) return; try { const response = await fetch('/api/vote', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)}); const result = await response.json(); if (!response.ok) throw Error(result.error || '保存失败'); saved[payload.sample_key] = result.vote; if (pending[payload.sample_key] === payload) delete pending[payload.sample_key]; persist(); if (currentKey === payload.sample_key) renderChoices(); else renderDirectory(); } catch (error) { if (currentKey === payload.sample_key) status('已暂存浏览器，尚未写入文件：' + error.message, true); } });
}
function flushNote() { if (!noteTimer) return; clearTimeout(noteTimer); noteTimer = null; const c = current(); if (c) { const v = voteFor(c); queueVote(capture(v?.choice || 'unrated', v?.candidate_ids || [], el('note').value)); } }
function navigate(key) { flushNote(); currentKey = key; location.hash = encodeURIComponent(key); render(); window.scrollTo({top: 0, behavior: 'instant'}); }
function choose(id) { flushNote(); queueVote(capture('preferred', [id], el('note').value)); }
function special(choice) { flushNote(); queueVote(capture(choice, choice === 'tie' ? current().candidates.map(c => c.id) : [], el('note').value)); }
async function refresh(initial = false) {
  try { const response = await fetch('/api/data'); if (!response.ok) throw Error('读取失败'); const incoming = await response.json(); const old = current(), replacement = incoming.cases.find(c => c.key === currentKey); const changed = !!old && !!replacement && old.display_manifest_sha256 !== replacement.display_manifest_sha256; if (changed) flushNote(); data = incoming;
    if (initial) { saved = (await (await fetch('/api/votes')).json()).votes; const requested = data.cases.find(c => c.key === decodeURIComponent(location.hash.slice(1))); currentKey = requested?.key || ''; if (requested) el('scope').value = requested.reading_stage; populate(); for (const payload of Object.values(pending)) queueVote(payload); }
    else { const c = current(); if (!c || changed) populate(); else { const rows = subset(); const oldValue = el('sample').value; el('sample').replaceChildren(...rows.map(row => { const o = document.createElement('option'); o.value = row.key; o.textContent = row.number + ' / 48 · ' + row.title + ' · 第' + row.chapter + '章'; return o; })); el('sample').value = oldValue; el('next').disabled = rows.findIndex(row => row.key === c.key) >= rows.length - 1; renderDirectory(); } }
  } catch { el('notice').textContent = '本地服务暂不可用；已载入内容仍可阅读，反馈会暂存浏览器。'; }
}
for (const id of ['scope', 'book']) el(id).onchange = () => { flushNote(); currentKey = ''; populate(); };
el('sample').onchange = () => navigate(el('sample').value);
el('prev').onclick = () => { const rows = subset(), i = rows.findIndex(c => c.key === currentKey); if (i > 0) navigate(rows[i - 1].key); };
el('next').onclick = () => { const rows = subset(), i = rows.findIndex(c => c.key === currentKey); if (i + 1 < rows.length) navigate(rows[i + 1].key); };
el('highlight').onchange = () => document.body.classList.toggle('no-highlights', !el('highlight').checked);
el('allTie').onclick = () => special('tie'); el('none').onclick = () => special('none'); el('skip').onclick = () => special('skip'); el('clear').onclick = () => special('unrated');
el('note').oninput = () => { clearTimeout(noteTimer); noteTimer = setTimeout(flushNote, 600); };
el('export').onclick = async () => { flushNote(); await saving; let state; try { state = await (await fetch('/api/export')).json(); } catch { state = {schema_version: 1, votes: saved}; } state.pending_browser_feedback = Object.values(pending); const url = URL.createObjectURL(new Blob([JSON.stringify(state, null, 2)], {type: 'application/json'})); const a = document.createElement('a'); a.href = url; a.download = 'translation-paired48-feedback.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); };
window.addEventListener('beforeunload', () => { flushNote(); persist(); });
refresh(true); setInterval(() => refresh(false), 20000);
