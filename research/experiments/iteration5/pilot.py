from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.translation.prompt_builder import build_translation_prompt
from src.translation.style_transfer import (
    StyleTransferRunner, _codex_binary, _minimal_child_environment,
    _parse_events, _sandbox_profile,
)

RESEARCH = Path(__file__).resolve().parents[2]
REPO = RESEARCH.parent
ROOT = RESEARCH / "generated/style_reassessment_20260925"
SEED = 20260925
METHODS = ["neutral", "method4", "direct_scene", "ledger_scene"]
SCENES = [
    ("s1", 1, 28, 1, 20, "opening and comic failed quests"),
    ("s2", 132, 166, 97, 125, "request for help and prince dialogue"),
    ("s3", 309, 340, 226, 248, "workplace rhythm and romantic uncertainty"),
    ("s4", 373, 409, 271, 296, "career change, comic correction and partnership"),
]
TERMS = {"You Miao": "游淼", "Li Zhifeng": "李治锋", "Nie Dan": "聂丹", "Zhao Chao": "赵超",
         "Glann": "格兰", "Chanfeng Pass": "长枫关", "Oaktree Inn": "橡树旅店",
         "spellsword": "魔法剑士", "Medusa": "美杜莎"}

DIRECT = """将给出的完整英文场景写成自然的简体中文小说。英文是内容依据；
authentic_examples 是同一作者其他作品的真实英文译文与作者中文，观察英文译者的
断句、补明、对白标签怎样与作者中文不同，从中文例子学习叙述距离、语气、句群与
对白节奏。不要把例子的情节、比喻、人物或特有措辞移植进来，不要追求更华丽。
从英文直接完成整场景，不先造逐段中性中文。按汉语场景推进重新组织句子和段落，
可以合并/拆分英文段落，调节对白标签的位置，不能改变事件先后、人物关系或语义。
必须保留英文的每项事实、否定、程度、悬念、玩笑、说话人和数量，不新增意象、
动作、感情解释、心理活动或因果。没有中文版测试答案，不能检索或补写记忆原文。
只返回 JSON，paragraphs 是完整场景的中文段落字符串数组，notes 只写真正不确定处。"""

LEDGER = """只做英文小说场景的内容与话语结构分析，不翻译成连贯中文小说。
将完整场景分解为按原顺序排列的 beats，用简短中文记录原子事实（非文学句子）。
每个 beat 记录所覆盖的英文下标 source_ids、content_zh（全部事件、属性、人物指代、
数量、否定、程度、因果）、speech_zh（如有对白，记录说话人、全部命题、语气、
停顿、自我纠正、未完成话语）、discourse_zh（谁的视角、叙述距离、心理/外部观察、
铺垫与笑点或情绪转折的先后）。保留英文所有内容，不添加解释。没有则用空字符串。
不要逐句照译，不复制英文语序，不润色成成品。glossary 固定名字。
完整覆盖所有输入下标。只返回 schema JSON。"""

LEDGER_QA = """独立对照英文检查内容清单。逐项核对主体、客体、言语内容、数量、
程度、否定、时间顺序、因果、隐喻、笑点、自我纠正和悬而未决的意思。
只修复清单的遗漏/误解/无依据添加，维持中文原子信息形式，不写文学成品。
不得以风格为由删去事实。输出完整 corrected beats，notes 写修复记录。
输入没有任何作者中文答案；英文是唯一事实依据。只返回 schema JSON。"""

RENDER = """依据给出的中文内容清单，将整个场景实现为自然的简体中文小说。
你没有英文原句，也没有该段作者中文答案。authentic_examples 来自同一作者其他作品，
只学习中文叙述距离、语气、句群、对白节奏与详略，不移植情节、意象或特有词句。
不要照着清单次序机械拼句，不要写成梗概；把事实恢复为完整现场叙事和对白，
按场景节奏自由断句分段，保持事件/对白先后。每项事实、属性、数量、否定、程度、
笑点、自我纠正、说话人、悬置都必须保留。不能新增心理解释、动作、比喻或因果。
克制华丽措辞与过度解释；作者感来自句群和口吻，不来自塞进惯用词。
paragraphs 是完整场景中文段落字符串数组，notes 只写不确定处。只返回 JSON。"""

JUDGE = """你是独立的双语文学评审。参考中文是此英文场景对应的作者原文，
但英文译者可能已重分段、补明或改动局部内容。匿名候选来自未知方法。
分别评价风格与英文内容保真，不推测方法身份，不把字面重合/同样人物名当作风格。
不要因为候选更流畅、更短、更华丽就认定更像作者，也不因中文段数不同直接扣分。
风格依据此场景的作者中文具体行为：句群长短与停顿、叙事距离和心理表达的直接/间接、
对白短促与插语、口语感及幽默的轻重。rhythm,dialogue,narration,diction 各1-5，
1=明显不像，3=部分相近，5=高度相近；naturalness 单独1-5。
英文内容单独核对，列 major_errors（主体/事件/否定/数量/强度等实质错误），
minor_errors（小细节/色彩），给 en_fidelity 1-5。不要求恢复英文中已经缺失的中文，
不惩罚候选忠实英文却与作者中文不同之处。不要把中文删节当作候选冗余。
每个候选 evidence 简短引用可见句法/口吻证据；严禁用总体印象代替。
输出所有 candidate_id 的评价。style_ranking 由最像到最不像，用并列分组。
这是探索性机器评审，分数不是风格还原百分比。只返回 schema JSON。"""


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def object_schema(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


STRING = {"type": "string"}
STRINGS = {"type": "array", "items": STRING}
TEXT_SCHEMA = object_schema({"paragraphs": STRINGS, "notes": STRINGS})
BEAT = object_schema({"source_ids": {"type": "array", "items": {"type": "integer"}},
                      "content_zh": STRING, "speech_zh": STRING, "discourse_zh": STRING})
LEDGER_SCHEMA = object_schema({"beats": {"type": "array", "items": BEAT}, "notes": STRINGS})
SCORE = {"type": "integer", "minimum": 1, "maximum": 5}
RATING = object_schema({"candidate_id": STRING, "rhythm": SCORE, "dialogue": SCORE,
                       "narration": SCORE, "diction": SCORE, "naturalness": SCORE,
                       "en_fidelity": SCORE, "major_errors": STRINGS,
                       "minor_errors": STRINGS, "evidence": STRING})
RATING_SCHEMA = object_schema({"ratings": {"type": "array", "items": RATING},
                               "style_ranking": {"type": "array", "items": STRINGS},
                               "limitations": STRINGS})
NEUTRAL_SCHEMA = object_schema({"chapter_title": STRING,
    "translations": {"type": "array", "items": object_schema({"index": {"type": "integer"}, "zh": STRING})},
    "glossary_candidates": {"type": "array", "items": object_schema({"source": STRING, "zh": STRING,
         "reason": STRING, "confidence": {"type": "string", "enum": ["high", "medium", "low"]}})}})


def prepare() -> None:
    if (ROOT / "manifest.json").exists():
        verify_lock()
        print("Existing frozen manifest verified")
        return
    en = read(ROOT / "sources/lsww_en.json")["paragraphs"]
    zh = read(ROOT / "sources/lsww_zh.json")["paragraphs"]
    examples = read(ROOT / "real_parallel_examples.json")
    for sid, a, b, c, d, label in SCENES:
        write(ROOT / f"samples/{sid}.json", {"sample_id": sid,
            "english": [{"index": i, "english": en[i]} for i in range(a, b)], "glossary": TERMS})
        write(ROOT / f"gold/{sid}.json", {"paragraphs": zh[c:d], "source_indices": [c, d], "label": label,
              "alignment": "Manually reviewed contiguous scene alignment; boundaries may be many-to-many. English-local changes retained, not treated as style failures."})
    prompts = {"direct_scene": DIRECT, "ledger": LEDGER, "ledger_qa": LEDGER_QA, "renderer": RENDER, "judge": JUDGE}
    for name, value in prompts.items():
        path = ROOT / f"prompts/{name}.txt"; path.parent.mkdir(parents=True, exist_ok=True);path.write_text(value)
    (ROOT / "prompts/neutral_source.py").write_bytes((REPO / "src/translation/prompt_builder.py").read_bytes())
    config = read(REPO / "book_specs/eternal_gate/config.json")
    model = config["codex"]["model_order"][0]
    judge_models = config["codex"]["model_order"][:2]
    bindings = [p for folder in ("sources", "samples", "gold", "prompts") for p in (ROOT/folder).glob('*') if p.is_file()]
    bindings += [ROOT / "real_parallel_examples.json", Path(__file__),
                 REPO / "src/translation/style_transfer.py", REPO / "src/translation/style_transfer_assets.py",
                 REPO / "book_specs/eternal_gate/config.json", RESEARCH / "generated/style_research/corpus/splits.json"]
    style = config["style_transfer"]
    for k in ("asset_path", "prompt_path", "schema_path"):
        bindings.append(REPO / style[k])
    manifest = {"schema_version": 1, "seed": SEED, "created_at": datetime.now(UTC).isoformat(),
       "status": "exploratory_pre_generation_lock", "methods": METHODS, "scenes": SCENES,
       "generator_model": model, "judge_models": judge_models, "reasoning_effort": "high",
       "model_seed_supported": False, "method4_block_size": 12,
       "bindings": {str(p.relative_to(REPO)): sha(p) for p in bindings},
       "evaluation": {"style": ["rhythm", "dialogue", "narration", "diction"],
          "content": "independent English fidelity plus errors, never fold into style score",
          "blinding": "opaque per-scene labels, randomized order; second judge receives reversed candidate order",
          "selection": "no score-guided retries or prompt edits; no production promotion on four scenes",
          "replication_unit": "one story, four dependent purposive non-explicit scenes",
          "limitations": ["Bundled interventions are confounded", "LLM ratings are not human ratings", "Same model family judge dependence", "New extra entirely withheld from generation except names-only shared glossary", "English and Chinese edition differences", "No erotic/censored region evaluated"]}}
    write(ROOT / "manifest.json", manifest)
    print(json.dumps({"manifest": str(ROOT / "manifest.json"), "bindings": len(bindings), "model": model}, ensure_ascii=False))


def verify_lock() -> dict[str, Any]:
    m = read(ROOT / "manifest.json")
    for path, digest in m["bindings"].items():
        if sha(REPO / path) != digest:
            raise RuntimeError(f"Frozen input changed: {path}")
    return m


def invoke(name: str, prompt: str, payload: Any, schema: dict[str, Any], model: str) -> Any:
    out = ROOT / f"calls/{name}.json"
    packet = {"prompt": prompt, "payload": payload, "schema": schema, "model": model}
    digest = hashlib.sha256(json.dumps(packet, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if out.exists():
        record = read(out)
        if record["input_sha256"] != digest: raise RuntimeError(f"Resume mismatch: {name}")
        return record["result"]
    write(ROOT / f"requests/{name}.json", packet)
    failures = []
    for attempt in range(1, 3):
        with tempfile.TemporaryDirectory(prefix="style-pilot-") as tmp:
            temp = Path(tmp); schema_path = temp / "schema.json"; response = temp / "response.json"
            write(schema_path, schema)
            profile = temp / "isolation.sb"; profile.write_text(_sandbox_profile())
            cmd = ["/usr/bin/sandbox-exec", "-f", str(profile), str(_codex_binary("codex")), "exec",
                   "--ephemeral", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check",
                   "--dangerously-bypass-approvals-and-sandbox"]
            for feature in ("shell_tool", "unified_exec", "browser_use", "browser_use_external", "browser_use_full_cdp_access", "in_app_browser", "computer_use", "apps", "multi_agent"):
                cmd += ["--disable", feature]
            cmd += ["--cd", str(temp), "--model", model, "--config", 'model_reasoning_effort="high"',
                    "--output-schema", str(schema_path), "--output-last-message", str(response), "--json", "-"]
            try:
                process = subprocess.run(cmd, input=prompt + "\n\nDo not use tools or inspect files. Only use supplied data.\n" + json.dumps(payload, ensure_ascii=False),
                    text=True, capture_output=True, timeout=900, cwd=temp, env=_minimal_child_environment(temp))
                if process.returncode or not response.exists():
                    raise RuntimeError(f"exit {process.returncode}: {process.stderr[-500:]} {process.stdout[-500:]}")
                result = read(response)
                thread, usage, errors = _parse_events(process.stdout)
                write(out, {"input_sha256": digest, "model": model, "attempt": attempt, "response_id": thread,
                       "usage": usage, "prior_failures": failures, "completed_at": datetime.now(UTC).isoformat(), "result": result})
                print(f"complete {name}", flush=True)
                return result
            except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
                failures.append(str(exc))
                write(ROOT / f"failures/{name}.json", failures)
    raise RuntimeError(f"{name} failed: {failures}")


def generate_scene(sid: str, m: dict[str, Any]) -> None:
    s = read(ROOT / f"samples/{sid}.json"); examples = read(ROOT / "real_parallel_examples.json")
    base = {"sample_id": sid, "english": s["english"], "glossary": TERMS}
    neutral_payload = {"pass": "semantic_draft", "book_title": "", "author": "", "source_context": "English published translation is semantic authority.",
        "chapter_id": sid, "chapter_title": "", "glossary": [{"source": k, "zh": v} for k,v in TERMS.items()], "sentence_translations": [],
        "items": [{**row, "current_zh": "", "context_before": [x["english"] for x in s["english"][max(0,i-5):i]],
                   "context_after": [x["english"] for x in s["english"][i+1:i+6]], "glossary_matches": []} for i,row in enumerate(s["english"])]}
    neutral = {"translations": []}
    for offset in range(0, len(neutral_payload["items"]), 30):
        chunk = {**neutral_payload, "items": neutral_payload["items"][offset:offset+30]}
        part = invoke(f"{sid}/neutral_{offset}", build_translation_prompt(chunk), {}, NEUTRAL_SCHEMA, m["generator_model"])
        neutral["translations"] += part["translations"]
    assert [x["index"] for x in neutral["translations"]] == [x["index"] for x in s["english"]]
    assert all(x["zh"].strip() for x in neutral["translations"])
    write(ROOT / f"outputs/{sid}/neutral.json", {"paragraphs": [x["zh"] for x in neutral["translations"]]})
    direct = invoke(f"{sid}/direct", DIRECT, {**base, "authentic_examples": examples}, TEXT_SCHEMA, m["generator_model"])
    write(ROOT / f"outputs/{sid}/direct_scene.json", direct)
    ledger = invoke(f"{sid}/ledger", LEDGER, base, LEDGER_SCHEMA, m["generator_model"])
    checked = invoke(f"{sid}/ledger_qa", LEDGER_QA, {**base, "ledger": ledger}, LEDGER_SCHEMA, m["judge_models"][1])
    covered = sorted(set(i for b in checked["beats"] for i in b["source_ids"]))
    assert covered == [x["index"] for x in s["english"]], (sid, covered)
    rendered = invoke(f"{sid}/render", RENDER, {"sample_id": sid, "glossary": TERMS,
        "content_ledger": checked, "authentic_examples": examples}, TEXT_SCHEMA, m["generator_model"])
    write(ROOT / f"outputs/{sid}/ledger_scene.json", rendered)
    dest = ROOT / f"outputs/{sid}/method4.json"
    if dest.exists(): return
    style = read(REPO / "book_specs/eternal_gate/config.json")["style_transfer"]
    runroot = ROOT / f"method4/{sid}"; runroot.mkdir(parents=True, exist_ok=True)
    runner = StyleTransferRunner(style_run_dir=runroot, asset_path=REPO/style["asset_path"],
        asset_file_sha256=sha(REPO/style["asset_path"]), prompt_path=REPO/style["prompt_path"], schema_path=REPO/style["schema_path"],
        models=[m["generator_model"]], reasoning_effort="high", timeout_seconds=900, max_attempts=2, codex_bin="codex", overwrite=False)
    rows = [{**e, "neutral_zh": n["zh"]} for e,n in zip(s["english"], neutral["translations"])]
    combined, artifacts = [], []
    for offset in range(0, len(rows), 12):
        block_path = runroot / f"block_{offset}.json"
        if block_path.exists(): block = read(block_path)
        else:
            seg = runner.invoke_segment(chunk_id=f"{sid}_{offset}", chapter_id=sid, rows=rows[offset:offset+12], segment_name="root", depth=0)
            block = {"paragraphs": seg.paragraphs, "artifacts": seg.artifacts, "usage": seg.usage}; write(block_path, block)
            print(f"complete {sid}/method4_{offset}", flush=True)
        combined += block["paragraphs"]; artifacts += block["artifacts"]
    write(dest, {"paragraphs": combined, "artifacts": artifacts})


def generate() -> None:
    m = verify_lock()
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(generate_scene, s[0], m) for s in SCENES]
        for job in as_completed(jobs): job.result()


def evaluation_packet(sid: str, m: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    rng = random.Random(SEED + int(sid[1:]))
    methods = METHODS.copy(); rng.shuffle(methods)
    names = {f"V{i+1}": method for i,method in enumerate(methods)}
    s = read(ROOT / f"samples/{sid}.json")
    candidates = [{"candidate_id": key, "paragraphs": read(ROOT/f"outputs/{sid}/{method}.json")["paragraphs"]} for key,method in names.items()]
    packet = {"sample_id": sid, "english_source": s["english"],
              "author_reference_zh": read(ROOT / f"gold/{sid}.json")["paragraphs"], "candidates": candidates}
    return packet,names


def evaluate() -> None:
    m = verify_lock(); jobs = []
    for sid,*_ in SCENES:
        packet, names = evaluation_packet(sid,m)
        write(ROOT / f"evaluation/keys/{sid}.json", names)
        for j,model in enumerate(m["judge_models"]):
            p = {**packet, "candidates": packet["candidates"] if j == 0 else list(reversed(packet["candidates"]))}
            write(ROOT/f"evaluation/packets/{sid}_{j}.json",p)
            jobs.append((f"judgments/{sid}_{j}",JUDGE,p,RATING_SCHEMA,model))
    write(ROOT / "evaluation/frozen_outputs.json", {str(p.relative_to(ROOT)):sha(p) for p in (ROOT/"outputs").rglob('*.json')})
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(invoke,*job) for job in jobs]
        for future in as_completed(futures): future.result()


def report() -> None:
    m = verify_lock(); rows = []
    for sid,*_ in SCENES:
        names = read(ROOT / f"evaluation/keys/{sid}.json")
        for j,model in enumerate(m["judge_models"]):
            result = read(ROOT/f"calls/judgments/{sid}_{j}.json")["result"]
            assert sorted(x["candidate_id"] for x in result["ratings"]) == sorted(names)
            for rating in result["ratings"]:
                rows.append({"scene":sid,"judge":model,"method":names[rating["candidate_id"]],
                    "style_mean":sum(rating[k] for k in m["evaluation"]["style"])/4,**rating})
    summary = {}
    for method in METHODS:
        rr=[r for r in rows if r["method"]==method]
        summary[method]={"style_mean":sum(r['style_mean'] for r in rr)/len(rr),
            "naturalness_mean":sum(r['naturalness'] for r in rr)/len(rr),
            "fidelity_mean":sum(r['en_fidelity'] for r in rr)/len(rr),
            "ratings_with_major_error":sum(bool(r['major_errors']) for r in rr),
            "rating_count":len(rr), "paragraph_count":sum(len(read(ROOT/f'outputs/{sid}/{method}.json')['paragraphs']) for sid,*_ in SCENES)}
    write(ROOT/'evaluation/summary.json',{'methods':summary,'ratings':rows,'limitations':m['evaluation']['limitations']})
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    lines=['# Blind reading packet','', 'Method names are deliberately hidden. Read author reference and candidates before revealing keys.','']
    for sid,*_ in SCENES:
        p,_=evaluation_packet(sid,m)
        lines += [f'## {sid}', '', '### Author reference', '', '\n\n'.join(p['author_reference_zh']),'']
        for c in p['candidates']:
            lines += [f"### {c['candidate_id']}",'','\n\n'.join(c['paragraphs']),'']
    (ROOT/'blind_reading.md').write_text('\n'.join(lines))


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','generate','evaluate','report'])
    globals()[parser.parse_args().stage]()
