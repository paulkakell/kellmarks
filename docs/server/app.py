from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, jsonify, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
DATA_PATH = ASSETS_DIR / "data.json"

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def read_data() -> Dict[str, Any]:
    if not DATA_PATH.exists():
        return {"version": 1, "exportedAt": utc_now_iso(), "entries": []}
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        obj = json.load(f)
    if isinstance(obj, list):
        return {"version": 1, "exportedAt": utc_now_iso(), "entries": obj}
    if not isinstance(obj, dict):
        return {"version": 1, "exportedAt": utc_now_iso(), "entries": []}
    obj.setdefault("version", 1)
    obj.setdefault("exportedAt", utc_now_iso())
    obj.setdefault("entries", [])
    return obj

def write_data(obj: Dict[str, Any]) -> None:
    tmp = str(DATA_PATH) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, DATA_PATH)

def normalize_tags(tags: Any) -> List[str]:
    if tags is None:
        return []
    if isinstance(tags, list):
        return [str(x).strip() for x in tags if str(x).strip()]
    if isinstance(tags, str):
        return [x.strip() for x in tags.split(",") if x.strip()]
    return []

def safe_str(x: Any, max_len: int) -> str:
    s = str(x) if x is not None else ""
    return s[:max_len]

def validate_entry_payload(payload: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    url = safe_str(payload.get("url", ""), 2048).strip()
    if not url:
        return None, "url is required"
    if not re.match(r"^https?://", url):
        return None, "url must start with http:// or https://"

    title = safe_str(payload.get("title", url), 120).strip() or url
    icon_url = safe_str(payload.get("iconUrl", ""), 2048).strip()
    desc = safe_str(payload.get("description", ""), 600).strip()
    tags = normalize_tags(payload.get("tags", []))

    cleaned = {
        "title": title,
        "url": url,
        "iconUrl": icon_url,
        "description": desc,
        "tags": tags,
    }
    return cleaned, None

# Boolean query evaluator
TOKEN_TERM = "TERM"

def tokenize(q: str) -> List[Dict[str, str]]:
    s = (q or "").strip()
    out: List[Dict[str, str]] = []
    i = 0
    while i < len(s):
        c = s[i]
        if c.isspace():
            i += 1
            continue
        if c in ("(", ")"):
            out.append({"type": c})
            i += 1
            continue
        if c == '"':
            j = i + 1
            buf = []
            while j < len(s) and s[j] != '"':
                buf.append(s[j])
                j += 1
            out.append({"type": TOKEN_TERM, "value": "".join(buf).lower()})
            i = j + 1 if j < len(s) else j
            continue
        j = i
        buf = []
        while j < len(s) and (not s[j].isspace()) and s[j] not in ("(", ")"):
            buf.append(s[j])
            j += 1
        w = "".join(buf)
        up = w.upper()
        if up in ("AND", "OR", "NOT"):
            out.append({"type": up})
        else:
            out.append({"type": TOKEN_TERM, "value": w.lower()})
        i = j

    with_and: List[Dict[str, str]] = []
    for k in range(len(out)):
        a = out[k]
        b = out[k + 1] if k + 1 < len(out) else None
        with_and.append(a)
        if not b:
            break
        a_is = (a["type"] == TOKEN_TERM or a["type"] == ")")
        b_is = (b["type"] == TOKEN_TERM or b["type"] in ("(", "NOT"))
        if a_is and b_is:
            with_and.append({"type": "AND"})
    return with_and

def to_rpn(tokens: List[Dict[str, str]]) -> List[Dict[str, str]]:
    prec = {"NOT": 3, "AND": 2, "OR": 1}
    right_assoc = {"NOT": True}
    out: List[Dict[str, str]] = []
    ops: List[Dict[str, str]] = []
    for t in tokens:
        ttype = t["type"]
        if ttype == TOKEN_TERM:
            out.append(t)
            continue
        if ttype == "(":
            ops.append(t)
            continue
        if ttype == ")":
            while ops and ops[-1]["type"] != "(":
                out.append(ops.pop())
            if ops and ops[-1]["type"] == "(":
                ops.pop()
            continue
        if ttype in ("AND", "OR", "NOT"):
            while ops:
                top = ops[-1]["type"]
                if top == "(":
                    break
                p_top = prec.get(top, 0)
                p_t = prec.get(ttype, 0)
                if p_top > p_t or (p_top == p_t and not right_assoc.get(ttype, False)):
                    out.append(ops.pop())
                else:
                    break
            ops.append(t)
    while ops:
        out.append(ops.pop())
    return out

def eval_rpn(rpn: List[Dict[str, str]], text: str) -> bool:
    st: List[bool] = []
    for t in rpn:
        ttype = t["type"]
        if ttype == TOKEN_TERM:
            val = t.get("value", "")
            st.append(val in text if val else True)
            continue
        if ttype == "NOT":
            a = st.pop() if st else False
            st.append(not a)
            continue
        if ttype == "AND":
            b = st.pop() if st else False
            a = st.pop() if st else False
            st.append(bool(a and b))
            continue
        if ttype == "OR":
            b = st.pop() if st else False
            a = st.pop() if st else False
            st.append(bool(a or b))
            continue
    return bool(st[-1]) if st else True

def matches_query(entry: Dict[str, Any], q: str) -> bool:
    q = (q or "").strip()
    if not q:
        return True
    tokens = tokenize(q)
    if not tokens:
        return True
    rpn = to_rpn(tokens)
    fields = [
        str(entry.get("title", "")),
        str(entry.get("url", "")),
        str(entry.get("description", "")),
        " ".join([str(x) for x in entry.get("tags", []) or []]),
    ]
    text = " ".join(fields).lower()
    return eval_rpn(rpn, text)

def tag_prefix_match(entry: Dict[str, Any], prefix: str) -> bool:
    if prefix == "__ALL__":
        return True
    if prefix == "Untagged":
        return not (entry.get("tags") or [])
    for t in entry.get("tags") or []:
        s = str(t)
        if s == prefix or s.startswith(prefix + "/"):
            return True
    return False

def build_tag_tree(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    root: Dict[str, Any] = {"name": "All", "path": "__ALL__", "children": {}, "count": len(entries)}
    untagged: Dict[str, Any] = {"name": "Untagged", "path": "Untagged", "children": {}, "count": 0}
    root["children"]["Untagged"] = untagged

    def ensure_child(parent: Dict[str, Any], part: str, path: str) -> Dict[str, Any]:
        children = parent["children"]
        if part not in children:
            children[part] = {"name": part, "path": path, "children": {}, "count": 0}
        return children[part]

    for e in entries:
        tags = e.get("tags") or []
        if not tags:
            untagged["count"] += 1
            continue
        for raw in tags:
            tag = str(raw).strip()
            if not tag:
                continue
            parts = [p.strip() for p in tag.split("/") if p.strip()]
            acc = ""
            cur = root
            for part in parts:
                acc = f"{acc}/{part}" if acc else part
                child = ensure_child(cur, part, acc)
                child["count"] += 1
                cur = child

    return root

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")

@app.after_request
def add_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    resp.headers["Cache-Control"] = "no-store"
    return resp

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "time": utc_now_iso()})

@app.route("/api/entries", methods=["GET", "POST", "OPTIONS"])
def entries():
    if app.config.get("TESTING") and request.method == "OPTIONS":
        return ("", 204)
    if request.method == "OPTIONS":
        return ("", 204)

    store = read_data()
    items = store.get("entries", [])

    if request.method == "GET":
        return jsonify(items)

    payload = request.get_json(silent=True) or {}
    cleaned, err = validate_entry_payload(payload)
    if err:
        return jsonify({"error": err}), 400

    new_id = safe_str(payload.get("id", ""), 80).strip() or f"e-{int(time.time()*1000)}"
    now = utc_now_iso()
    entry = {"id": new_id, "createdAt": now, "updatedAt": now, **cleaned}
    items.insert(0, entry)
    store["exportedAt"] = now
    store["entries"] = items
    write_data(store)
    return jsonify(entry), 201

@app.route("/api/entries/<entry_id>", methods=["GET", "PUT", "DELETE", "OPTIONS"])
def entry_by_id(entry_id: str):
    if request.method == "OPTIONS":
        return ("", 204)

    store = read_data()
    items: List[Dict[str, Any]] = store.get("entries", [])

    idx = next((i for i, e in enumerate(items) if str(e.get("id")) == entry_id), None)
    if idx is None:
        return jsonify({"error": "not found"}), 404

    if request.method == "GET":
        return jsonify(items[idx])

    if request.method == "DELETE":
        deleted = items.pop(idx)
        store["exportedAt"] = utc_now_iso()
        store["entries"] = items
        write_data(store)
        return jsonify({"deleted": True, "entry": deleted})

    payload = request.get_json(silent=True) or {}
    merged = {**items[idx], **payload}
    cleaned, err = validate_entry_payload(merged)
    if err:
        return jsonify({"error": err}), 400

    now = utc_now_iso()
    items[idx] = {**items[idx], **cleaned, "updatedAt": now}
    store["exportedAt"] = now
    store["entries"] = items
    write_data(store)
    return jsonify(items[idx])

@app.route("/api/export", methods=["GET"])
def export_all():
    return jsonify(read_data())

@app.route("/api/import", methods=["POST", "OPTIONS"])
def import_all():
    if request.method == "OPTIONS":
        return ("", 204)

    payload = request.get_json(silent=True) or {}
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return jsonify({"error": "entries must be a list"}), 400

    cleaned: List[Dict[str, Any]] = []
    for x in entries:
        if not isinstance(x, dict):
            continue
        url = safe_str(x.get("url", ""), 2048).strip()
        if not url:
            continue
        entry_id = safe_str(x.get("id", ""), 80).strip() or f"e-{int(time.time()*1000)}"
        cleaned.append({
            "id": entry_id,
            "createdAt": safe_str(x.get("createdAt", utc_now_iso()), 64),
            "updatedAt": safe_str(x.get("updatedAt", utc_now_iso()), 64),
            "title": safe_str(x.get("title", url), 120).strip() or url,
            "url": url,
            "iconUrl": safe_str(x.get("iconUrl", ""), 2048).strip(),
            "description": safe_str(x.get("description", ""), 600).strip(),
            "tags": normalize_tags(x.get("tags", [])),
        })

    store = {"version": 1, "exportedAt": utc_now_iso(), "entries": cleaned}
    write_data(store)
    return jsonify({"imported": len(cleaned)})

@app.route("/api/tags/tree", methods=["GET"])
def tags_tree():
    store = read_data()
    return jsonify(build_tag_tree(store.get("entries", [])))

@app.route("/api/search", methods=["GET"])
def search():
    q = request.args.get("q", "")
    path = request.args.get("path", "__ALL__")
    store = read_data()
    items = store.get("entries", [])
    out = []
    for e in items:
        if not tag_prefix_match(e, path):
            continue
        if matches_query(e, q):
            out.append(e)
    return jsonify({"q": q, "path": path, "count": len(out), "entries": out})

@app.route("/api/external/ddg", methods=["GET"])
def ddg_proxy():
    import urllib.parse
    import urllib.request

    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"q": q, "results": []})

    api = "https://api.duckduckgo.com/?" + urllib.parse.urlencode({
        "q": q,
        "format": "json",
        "no_html": "1",
        "skip_disambig": "1",
    })

    try:
        with urllib.request.urlopen(api, timeout=8) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
    except Exception:
        return jsonify({"q": q, "results": []})

    results: List[Dict[str, str]] = []

    for r in data.get("Results") or []:
        url = r.get("FirstURL")
        text = r.get("Text")
        if url and text:
            results.append({"url": url, "title": text.split(" - ")[0][:140], "snippet": text[:280]})

    def walk_topics(topics):
        for t in topics or []:
            if isinstance(t, dict) and "Topics" in t and isinstance(t["Topics"], list):
                yield from walk_topics(t["Topics"])
            elif isinstance(t, dict):
                url = t.get("FirstURL")
                text = t.get("Text")
                if url and text:
                    yield {"url": url, "title": text.split(" - ")[0][:140], "snippet": text[:280]}

    for it in walk_topics(data.get("RelatedTopics") or []):
        results.append(it)

    seen = set()
    uniq = []
    for r in results:
        if r["url"] in seen:
            continue
        seen.add(r["url"])
        uniq.append(r)
        if len(uniq) >= 20:
            break

    return jsonify({"q": q, "results": uniq})

@app.route("/", methods=["GET"])
def root_index():
    return send_from_directory(str(BASE_DIR), "index.html")

@app.route("/<path:filename>", methods=["GET"])
def static_files(filename: str):
    return send_from_directory(str(BASE_DIR), filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8787, debug=False)
