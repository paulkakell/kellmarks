"""Offline site-tag suggestions. Called only when creating a new bookmark."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SITE_RULES: dict[str, list[str]] = json.loads(
    (Path(__file__).resolve().parents[1] / "assets" / "site-tags.json").read_text("utf-8")
)
MAX_SUGGESTIONS = 5


def site_host(url: str) -> str:
    """Use exact hosts (apart from www) rather than guessing public suffixes."""
    host = (urlsplit(url).hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
    return host.removeprefix("www.")


def suggest_tags(url: str, entries: list[dict[str, Any]]) -> list[str]:
    host = site_host(url)
    if not host:
        return []
    counts: Counter[str] = Counter()
    labels: dict[str, str] = {}
    for entry in entries:
        if site_host(entry["url"]) == host:
            for tag in entry.get("tags", []):
                if tag:
                    key = tag.lower()
                    counts[key] += 1
                    labels.setdefault(key, tag)
    if counts:
        keys = sorted(counts, key=lambda tag: (-counts[tag], tag))[:MAX_SUGGESTIONS]
        return [labels[key] for key in keys]
    # Longest matching domain wins; a dot boundary prevents github.com.evil matches.
    for domain in sorted(SITE_RULES, key=lambda value: (-len(value), value)):
        if host == domain or host.endswith("." + domain):
            return SITE_RULES[domain][:MAX_SUGGESTIONS]
    # An unfamiliar site still gets a useful, deterministic group, without network access.
    return ["sites/" + host[:74]]
