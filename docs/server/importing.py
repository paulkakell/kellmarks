"""Pure, non-networked helpers for reviewed bookmark imports."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit, urlunsplit


class ImportProblem(ValueError):
    """An import cannot be applied without losing or misidentifying data."""


class ImportConflict(ImportProblem):
    """The live library changed after an import was previewed."""


def library_revision(entries: list[dict[str, Any]]) -> str:
    encoded = json.dumps(entries, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def duplicate_key(url: str) -> str:
    """Compare validated URLs without discarding query, fragment, or path data."""
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if ":" in host:
        host = f"[{host}]"
    port = parsed.port
    if port is not None and (parsed.scheme, port) not in {("http", 80), ("https", 443)}:
        host = f"{host}:{port}"
    return urlunsplit((parsed.scheme.lower(), host, parsed.path or "/", parsed.query, parsed.fragment))


class BookmarkHTMLParser(HTMLParser):
    """Read Netscape bookmark exports as text; never render or fetch their HTML."""

    def __init__(self, max_entries: int) -> None:
        super().__init__(convert_charrefs=True)
        self.max_entries = max_entries
        self.entries: list[dict[str, Any]] = []
        self.folders: list[str] = []
        self.lists: list[bool] = []
        self.pending_folder: str | None = None
        self.kind = ""
        self.parts: list[str] = []
        self.href = ""
        self.ignored = ""

    def finish(self) -> None:
        text = " ".join("".join(self.parts).split())
        if self.kind == "folder":
            self.pending_folder = text.replace("%", "%25").replace("/", "%2F")
        elif self.kind == "link":
            if len(self.entries) >= self.max_entries:
                raise ImportProblem(f"HTML import exceeds {self.max_entries} bookmarks")
            self.entries.append({
                "url": self.href,
                "title": text or self.href,
                "description": "",
                "tags": ["/".join(self.folders)] if self.folders else [],
            })
        elif self.kind == "description" and self.entries:
            self.entries[-1]["description"] = text
        self.kind = ""
        self.parts = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.ignored:
            return
        if tag in {"script", "style"}:
            self.ignored = tag
            return
        if tag in {"h3", "a", "dd", "dt", "dl"}:
            self.finish()
        if tag == "h3":
            self.kind = "folder"
        elif tag == "a":
            self.kind = "link"
            self.href = dict(attrs).get("href") or ""
        elif tag == "dd":
            self.kind = "description"
        elif tag == "dl":
            if len(self.lists) >= 32:
                raise ImportProblem("HTML folder nesting exceeds 32 levels")
            pushed = bool(self.pending_folder)
            self.lists.append(pushed)
            if pushed:
                self.folders.append(str(self.pending_folder))
            self.pending_folder = None

    def handle_endtag(self, tag: str) -> None:
        if self.ignored:
            if tag == self.ignored:
                self.ignored = ""
            return
        if (tag == "h3" and self.kind == "folder") or (tag == "a" and self.kind == "link"):
            self.finish()
        elif tag == "dl":
            self.finish()
            if self.lists and self.lists.pop():
                self.folders.pop()

    def handle_data(self, data: str) -> None:
        if self.kind and not self.ignored:
            self.parts.append(data)


def parse_bookmark_html(value: Any, max_entries: int) -> list[dict[str, Any]]:
    if not isinstance(value, str) or not value.strip():
        raise ImportProblem("html must be a nonempty string")
    parser = BookmarkHTMLParser(max_entries)
    parser.feed(value)
    parser.close()
    parser.finish()
    if not parser.entries:
        raise ImportProblem("HTML contains no bookmarks")
    return parser.entries


def import_options(payload: dict[str, Any]) -> tuple[str, str, str]:
    mode = payload.get("mode", "merge")
    title_source = payload.get("titleSource", "existing")
    description_source = payload.get("descriptionSource", "existing")
    if mode not in ("merge", "replace"):
        raise ImportProblem("mode must be merge or replace")
    if title_source not in ("existing", "incoming"):
        raise ImportProblem("titleSource must be existing or incoming")
    if description_source not in ("existing", "incoming"):
        raise ImportProblem("descriptionSource must be existing or incoming")
    return str(mode), str(title_source), str(description_source)


def build_import_plan(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    *,
    mode: str,
    title_source: str,
    description_source: str,
    now: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build a candidate, leaving both inputs untouched. Caller validates limits."""
    if mode == "replace":
        return deepcopy(incoming), {
            "newCount": len(incoming), "duplicateCount": 0, "updatedCount": 0,
            "unchangedCount": 0, "replacedCount": len(existing), "details": [],
        }

    result = deepcopy(existing)
    by_url: dict[str, list[dict[str, Any]]] = {}
    ids = {str(entry["id"]) for entry in existing}
    id_urls = {str(entry["id"]): duplicate_key(str(entry["url"])) for entry in existing}
    original_ids = set(ids)
    for entry in result:
        by_url.setdefault(duplicate_key(str(entry["url"])), []).append(entry)
    added = 0
    duplicate_count = 0
    unchanged = 0
    updated_ids: set[str] = set()
    details: list[dict[str, Any]] = []
    for entry in incoming:
        key = duplicate_key(str(entry["url"]))
        if str(entry["id"]) in id_urls and id_urls[str(entry["id"])] != key:
            raise ImportProblem(
                "An incoming ID belongs to a different URL; remove that ID before importing"
            )
        targets = by_url.get(key, [])
        if len(targets) > 1:
            raise ImportProblem(
                "An incoming URL matches multiple existing bookmarks; "
                "resolve those library duplicates before merging"
            )
        if not targets:
            created = deepcopy(entry)
            ids.add(created["id"])
            id_urls[str(created["id"])] = key
            result.append(created)
            by_url[key] = [created]
            added += 1
            details.append({"action": "new", "url": entry["url"], "id": created["id"]})
            continue
        duplicate_count += 1
        target = targets[0]
        before = deepcopy(target)
        seen = {tag.casefold() for tag in target["tags"]}
        for tag in entry["tags"]:
            if tag.casefold() not in seen:
                target["tags"].append(tag)
                seen.add(tag.casefold())
        for field, source in (("title", title_source), ("description", description_source)):
            if source == "incoming" and entry.get(field):
                target[field] = entry[field]
        if target != before:
            target["updatedAt"] = now
            if target["id"] in original_ids:
                updated_ids.add(target["id"])
            action = "merge"
        else:
            unchanged += 1
            action = "unchanged"
        details.append({"action": action, "url": entry["url"], "id": target["id"]})
    return result, {
        "newCount": added, "duplicateCount": duplicate_count,
        "updatedCount": len(updated_ids), "unchangedCount": unchanged,
        "replacedCount": 0, "details": details,
    }
