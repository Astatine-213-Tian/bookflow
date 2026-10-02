"""Loopback-only reading interface and durable, version-bound human feedback."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
from datetime import UTC, datetime
from difflib import SequenceMatcher
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from experiments.iteration6.results import LABELS
from experiments.iteration8.study import PREVIOUS, ROOT, read, sha, write

ASSETS = Path(__file__).parent / "reader_assets"
FEEDBACK = ROOT / "human_feedback"
LOCK = threading.Lock()
CACHE: dict[str, tuple[tuple, dict]] = {}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def diff_ranges(texts: list[str]) -> list[list[list[int]]]:
    """Symmetric local differences; punctuation and large reorderings aren't painted."""
    indexes = [[i for i,c in enumerate(text) if c.isalnum()] for text in texts]
    normalized = ["".join(text[i] for i in index) for text,index in zip(texts,indexes)]
    scores = [[0]*len(text) for text in texts]
    for a in range(len(texts)):
        for b in range(a+1, len(texts)):
            ops = SequenceMatcher(None, normalized[a], normalized[b], autojunk=False).get_opcodes()
            for at,(tag,i,j,k,l) in enumerate(ops):
                if tag == "equal" or max(j-i,l-k) > 32:
                    continue
                before = ops[at-1][2]-ops[at-1][1] if at and ops[at-1][0] == "equal" else 0
                after = ops[at+1][2]-ops[at+1][1] if at+1<len(ops) and ops[at+1][0] == "equal" else 0
                if not ((before>=3 and after>=3) or (at==0 and after>=6) or (at==len(ops)-1 and before>=6)):
                    continue
                for n,start,end in ((a,i,j),(b,k,l)):
                    if start<end:
                        for pos in range(indexes[n][start], indexes[n][end-1]+1):
                            scores[n][pos] += 1
    result = []
    for text,score in zip(texts,scores):
        threshold = 2 if sum(x>0 for x in score)>len(text)*0.45 else 1
        ranges, start = [], None
        for i,value in enumerate(score+[0]):
            if value>=threshold and start is None:
                start=i
            elif value<threshold and start is not None:
                ranges.append([start,i]);start=None
        result.append(ranges)
    return result


def get_case(root: Path, sid: str, batch: str, number: int, mapping: dict) -> dict | None:
    files = [root/f"samples/{sid}.json", root/f"gold/{sid}.json"]
    files += [root/f"outputs/{sid}/{method}.json" for method in mapping.values()]
    if not all(p.exists() for p in files):
        return None
    crops_path = root / "audit/display_crops.json"
    manifest_path=root/"manifest.json"
    mapping_path=root/"blind_mapping.json"
    watched = files + [manifest_path] + ([mapping_path] if mapping_path.exists() else []) + ([crops_path] if crops_path.exists() else [])
    stamp = tuple((p.stat().st_mtime_ns,p.stat().st_size) for p in watched)
    key=f"{batch}/{sid}"
    with LOCK:
        if key in CACHE and CACHE[key][0] == stamp:
            return CACHE[key][1]
    sample,gold=read(files[0]),read(files[1])
    if not gold["usable"]:
        return None
    author = gold["paragraphs"]
    crop = next((r for r in read(crops_path)["records"] if r["sample_id"] == sid), None) if crops_path.exists() else None
    if crop:
        if crop["gold_file_sha256"] != sha(files[1]):
            raise ValueError(f"Stale source display crop: {sid}")
        spans = crop["paragraph_spans"]
        if [span["paragraph_index"] for span in spans] != list(range(len(author))):
            raise ValueError(f"Source display crop omitted or reordered paragraphs: {sid}")
        expected = []
        for span, paragraph in zip(spans, author):
            start, end = span["start"], span["end"]
            if not 0 <= start <= end <= len(paragraph):
                raise ValueError(f"Source display crop outside paragraph: {sid}")
            expected.append(paragraph[start:end])
        if expected != crop["paragraphs"]:
            raise ValueError(f"Nonliteral source display crop: {sid}")
        author = expected
    candidates=[]
    for label,method in mapping.items():
        path=root/f"outputs/{sid}/{method}.json"
        paragraphs=read(path)["paragraphs"]
        candidates.append({"id":label[-1], "label":label, "method":LABELS[method],
            "paragraphs":paragraphs, "text":"\n".join(paragraphs), "output_sha256":sha(path),
            "text_sha256":digest(paragraphs)})
    for candidate,ranges in zip(candidates,diff_ranges([c["text"] for c in candidates])):
        candidate["highlights"]=ranges
    case={"key":key,"sample_id":sid,"batch":batch,"number":number,"title":sample["title"],
        "chapter":sample["chapter"],"volume":sample["volume"],"author":author,"source_crop_sha256":digest(crop) if crop else None,
        "english":[x["english"] for x in sample["english"]],
        "batch_manifest_sha256":sha(manifest_path),"candidates":candidates}
    case["display_manifest_sha256"]=digest(case)
    with LOCK:
        CACHE[key]=(stamp,case)
    return case


def dataset() -> dict:
    cases = []
    for number, (sid, mapping) in enumerate(read(ROOT / "blind_mapping.json").items(), 1):
        case = get_case(ROOT, sid, "balanced48", number, mapping)
        if case:
            cases.append(case)
    return {"schema_version": 1, "reader_version": "balanced48_v1", "planned_new": 48,
            "ready_new": len(cases), "legacy_count": 0, "cases": cases}


def votes() -> dict:
    path=FEEDBACK/"votes.json"
    return read(path) if path.exists() else {"schema_version":1,"votes":{}}


def validate_vote(payload: dict, case: dict) -> dict:
    if payload.get("display_manifest_sha256") != case["display_manifest_sha256"]:
        raise ValueError("页面数据版本已改变，请刷新后重试")
    choice=payload.get("choice")
    if choice not in ("preferred","tie","none","skip","unrated"):
        raise ValueError("无效的反馈类型")
    ids=payload.get("candidate_ids")
    if not isinstance(ids,list) or any(not isinstance(x,str) for x in ids):
        raise ValueError("无效的候选编号")
    valid_ids={x["id"] for x in case["candidates"]}
    if len(set(ids))!=len(ids) or not set(ids)<=valid_ids:
        raise ValueError("候选编号不属于本组")
    if (choice=="preferred" and len(ids)!=1) or (choice=="tie" and len(ids)<2) or (choice in ("none","skip","unrated") and ids):
        raise ValueError("偏好类型与候选编号不一致")
    note=payload.get("note","")
    if not isinstance(note,str) or len(note)>4000:
        raise ValueError("备注最多 4000 字")
    view=payload.get("view",{})
    if not isinstance(view,dict):
        raise ValueError("无效的阅读状态")
    return {"schema_version":1,"reader_version":"balanced48_v1","sample_key":case["key"],
        "batch_id":case["batch"],"sample_id":case["sample_id"],"batch_manifest_sha256":case["batch_manifest_sha256"],
        "display_manifest_sha256":case["display_manifest_sha256"],"choice":choice,"candidate_ids":ids,
        "outputs":{c["id"]:{"output_sha256":c["output_sha256"],"text_sha256":c["text_sha256"]} for c in case["candidates"]},
        "note":note,"author_visible":True,"highlights_enabled":bool(view.get("highlights_enabled",True)),
        "english_visible":bool(view.get("english_visible",False)),"method_revealed":bool(view.get("method_revealed",False)),
        "candidate_order":[c["id"] for c in case["candidates"]],"updated_at":datetime.now(UTC).isoformat(),
        "interpretation":"Human source-aware preference; methods anonymous unless revealed. Not a fully blind rating."}


def save_vote(payload: dict) -> dict:
    case=next((c for c in dataset()["cases"] if c["key"]==payload.get("sample_key")),None)
    if case is None:
        raise ValueError("本组尚未就绪或不存在")
    row=validate_vote(payload,case)
    with LOCK:
        state=votes()
        previous=state["votes"].get(case["key"])
        row["first_recorded_at"]=previous["first_recorded_at"] if previous else row["updated_at"]
        state["votes"][case["key"]]=row
        state["updated_at"]=row["updated_at"]
        directory=FEEDBACK;directory.mkdir(parents=True,exist_ok=True)
        temp=directory/"votes.json.tmp"
        write(temp,state);os.replace(temp,directory/"votes.json")
        with (directory/"events.jsonl").open("a") as handle:
            handle.write(json.dumps(row,ensure_ascii=False)+"\n")
    return row


class Handler(BaseHTTPRequestHandler):
    def send(self, code: int, value: bytes, mime: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type",mime)
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Length",str(len(value)))
        self.end_headers();self.wfile.write(value)

    def json_response(self, code: int, value: Any) -> None:
        self.send(code,json.dumps(value,ensure_ascii=False).encode(),"application/json; charset=utf-8")

    def do_GET(self) -> None:
        path=urlsplit(self.path).path
        if path=="/api/data":
            self.json_response(200,dataset())
        elif path in ("/api/votes","/api/export"):
            with LOCK:
                value=votes()
            if path == "/api/export":
                previous = PREVIOUS / "human_feedback/votes.json"
                value = {**value, "archived_previous_feedback": read(previous) if previous.exists() else {"votes": {}},
                         "archive_note": "Previous batch feedback is preserved separately and excluded from the current 48-sample analysis."}
            self.json_response(200,value)
        elif path in ("/","/reader.js","/reader.css"):
            name="reader.html" if path=="/" else path[1:]
            mime={"reader.html":"text/html; charset=utf-8","reader.js":"text/javascript; charset=utf-8","reader.css":"text/css; charset=utf-8"}[name]
            self.send(200,(ASSETS/name).read_bytes(),mime)
        elif path=="/favicon.ico":
            self.send(204,b"","image/x-icon")
        else:
            self.json_response(404,{"error":"not found"})

    def do_POST(self) -> None:
        origin=f"http://127.0.0.1:{self.server.server_port}"
        if self.headers.get("Origin")!=origin or self.headers.get("Host")!=f"127.0.0.1:{self.server.server_port}":
            self.json_response(403,{"error":"仅接受本地阅读页的反馈"});return
        if urlsplit(self.path).path!="/api/vote" or self.headers.get_content_type()!="application/json":
            self.json_response(400,{"error":"无效请求"});return
        try:
            size=int(self.headers.get("Content-Length","0"))
            if not 0<size<=24000:
                raise ValueError("反馈内容过大或为空")
            payload=json.loads(self.rfile.read(size))
            if not isinstance(payload,dict):
                raise ValueError("无效数据")
            row=save_vote(payload)
            self.json_response(200,{"saved":True,"vote":row})
        except (ValueError,KeyError) as exc:
            self.json_response(400,{"error":str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    global FEEDBACK
    parser=argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=0)
    parser.add_argument("--feedback-dir",type=Path,default=FEEDBACK,
                        help="Separate directory for test feedback; default is the human feedback directory.")
    args=parser.parse_args()
    FEEDBACK=args.feedback_dir
    server=ThreadingHTTPServer(("127.0.0.1",args.port),Handler)
    url=f"http://127.0.0.1:{server.server_port}"
    write(ROOT/"reader_server.json",{"url":url,"pid":os.getpid(),"started_at":datetime.now(UTC).isoformat(),"host":"127.0.0.1"})
    print(url,flush=True)
    server.serve_forever()


if __name__=="__main__":
    main()
