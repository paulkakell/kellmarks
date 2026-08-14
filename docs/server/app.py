from __future__ import annotations

import hmac
import importlib
import ipaddress
import json
import logging
import os
import re
import secrets
import shutil
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid
from collections import OrderedDict, deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar, cast

from flask import Flask, Response, g, jsonify, request, send_from_directory
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge, UnsupportedMediaType

APP_VERSION = "02.00.02"
DATA_SCHEMA_VERSION = 2
DEFAULT_PORT = 8787
DEFAULT_MAX_REQUEST_BYTES = 1_048_576
DEFAULT_MAX_DATA_BYTES = 16_777_216
DEFAULT_MAX_ENTRIES = 10_000
DEFAULT_MAX_IMPORT_ENTRIES = 5_000
MAX_TITLE_LENGTH = 120
MAX_URL_LENGTH = 2_048
MAX_DESCRIPTION_LENGTH = 600
MAX_TAGS = 32
MAX_TAG_LENGTH = 80
MAX_ID_LENGTH = 80
MAX_QUERY_LENGTH = 512
MAX_EXTERNAL_QUERY_LENGTH = 256
MAX_PATH_LENGTH = 256
DDG_MAX_RESPONSE_BYTES = 2_097_152
STATIC_ASSETS = frozenset({"app.css", "app.js", "logo.svg", "sample-data.json"})
CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
ENTRY_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,80}$")
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
PROCESS_LOCK = threading.RLock()
T = TypeVar("T")


class ValidationError(ValueError):
    """Raised when untrusted application data fails validation."""


class StoreError(RuntimeError):
    """Raised when the persistent data store cannot be read or written safely."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be a boolean value")


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < minimum or value > maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def _env_csv(name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _require_text(value: Any, field: str, max_length: int, *, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string")
    text = value.strip()
    if required and not text:
        raise ValidationError(f"{field} is required")
    if len(text) > max_length:
        raise ValidationError(f"{field} must not exceed {max_length} characters")
    if CONTROL_CHAR_RE.search(text) or CONTROL_CHAR_RE.search(urllib.parse.unquote(text)):
        raise ValidationError(f"{field} contains control characters")
    return text


def normalize_http_url(
    value: Any,
    field: str = "url",
    *,
    required: bool = True,
) -> str:
    text = _require_text(value, field, MAX_URL_LENGTH, required=required)
    if not text:
        return ""
    if "\\" in text or any(character.isspace() for character in text):
        raise ValidationError(f"{field} contains unsupported whitespace or backslashes")
    if re.search(r"%(?![0-9A-Fa-f]{2})", text):
        raise ValidationError(f"{field} contains malformed percent encoding")

    try:
        parsed = urllib.parse.urlsplit(text)
        port = parsed.port
    except ValueError as exc:
        raise ValidationError(f"{field} is not a valid URL") from exc

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValidationError(f"{field} must use http or https")
    raw_hostname = parsed.hostname
    if not raw_hostname:
        raise ValidationError(f"{field} must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValidationError(f"{field} must not include credentials")
    if port is not None and not 1 <= port <= 65535:
        raise ValidationError(f"{field} has an invalid port")

    try:
        parsed_ip = ipaddress.ip_address(raw_hostname)
        hostname = parsed_ip.compressed
        if parsed_ip.version == 6:
            hostname = f"[{hostname}]"
    except ValueError:
        try:
            hostname = raw_hostname.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValidationError(f"{field} has an invalid host") from exc
    netloc = hostname
    if port is not None:
        netloc = f"{hostname}:{port}"

    normalized = urllib.parse.urlunsplit(
        (scheme, netloc, parsed.path or "", parsed.query or "", parsed.fragment or "")
    )
    if len(normalized) > MAX_URL_LENGTH:
        raise ValidationError(f"{field} must not exceed {MAX_URL_LENGTH} characters")
    return normalized


def normalize_tags(value: Any) -> list[str]:
    if value is None:
        raw_tags: list[Any] = []
    elif isinstance(value, str):
        raw_tags = value.split(",")
    elif isinstance(value, list):
        raw_tags = value
    else:
        raise ValidationError("tags must be a list of strings or a comma-separated string")

    if len(raw_tags) > MAX_TAGS:
        raise ValidationError(f"tags must contain no more than {MAX_TAGS} values")

    tags: list[str] = []
    seen: set[str] = set()
    for raw in raw_tags:
        tag = _require_text(raw, "tag", MAX_TAG_LENGTH)
        if not tag:
            continue
        tag = re.sub(r"\s+", " ", tag)
        if tag.startswith("/") or tag.endswith("/") or "//" in tag:
            raise ValidationError("tag paths must not start, end, or repeat a slash")
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag)

    return tags


def normalize_timestamp(value: Any, fallback: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        return fallback
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return fallback
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_entry_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValidationError("request body must be a JSON object")

    url = normalize_http_url(payload.get("url"), "url", required=True)
    title = _require_text(payload.get("title", url), "title", MAX_TITLE_LENGTH) or url
    icon_url = normalize_http_url(payload.get("iconUrl", ""), "iconUrl", required=False)
    description = _require_text(
        payload.get("description", ""), "description", MAX_DESCRIPTION_LENGTH
    )
    tags = normalize_tags(payload.get("tags", []))

    return {
        "title": title,
        "url": url,
        "iconUrl": icon_url,
        "description": description,
        "tags": tags,
    }


def normalize_entry_id(value: Any, *, generate: bool = False) -> str:
    if value is None or value == "":
        if generate:
            return f"e-{uuid.uuid4().hex}"
        raise ValidationError("id is required")
    text = _require_text(value, "id", MAX_ID_LENGTH, required=True)
    if not ENTRY_ID_RE.fullmatch(text):
        raise ValidationError("id contains unsupported characters")
    return text


def normalize_import_entries(
    value: Any,
    max_entries: int,
    *,
    generate_missing_ids: bool = True,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValidationError("entries must be a list")
    if len(value) > max_entries:
        raise ValidationError(f"entries must contain no more than {max_entries} items")

    now = utc_now_iso()
    normalized: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValidationError(f"entries[{index}] must be an object")
        try:
            cleaned = normalize_entry_payload(item)
            entry_id = normalize_entry_id(
                item.get("id"), generate=generate_missing_ids
            )
        except ValidationError as exc:
            raise ValidationError(f"entries[{index}]: {exc}") from exc
        if entry_id in ids:
            raise ValidationError(f"entries[{index}]: duplicate id {entry_id}")
        ids.add(entry_id)
        normalized.append(
            {
                "id": entry_id,
                "createdAt": normalize_timestamp(item.get("createdAt"), now),
                "updatedAt": normalize_timestamp(item.get("updatedAt"), now),
                **cleaned,
            }
        )
    return normalized


def normalize_store_object(value: Any, max_entries: int) -> dict[str, Any]:
    now = utc_now_iso()
    if isinstance(value, list):
        entries = normalize_import_entries(
            value, max_entries, generate_missing_ids=False
        )
        exported_at = now
    elif isinstance(value, dict):
        if "entries" not in value:
            raise StoreError("data store object must contain entries")
        entries = normalize_import_entries(
            value["entries"], max_entries, generate_missing_ids=False
        )
        exported_at = normalize_timestamp(value.get("exportedAt"), now)
    else:
        raise StoreError("data store root must be an object or list")
    return {
        "version": DATA_SCHEMA_VERSION,
        "exportedAt": exported_at,
        "entries": entries,
    }


def ensure_private_directory(path: Path) -> None:
    created = not path.exists()
    path.mkdir(parents=True, exist_ok=True)
    if not created:
        return
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def atomic_private_copy(source: Path, destination: Path) -> None:
    ensure_private_directory(destination.parent)
    temporary_path: Path | None = None
    try:
        with source.open("rb") as source_handle:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{destination.name}.",
                suffix=".tmp",
                dir=destination.parent,
                delete=False,
            ) as destination_handle:
                temporary_path = Path(destination_handle.name)
                shutil.copyfileobj(source_handle, destination_handle)
                destination_handle.flush()
                os.fsync(destination_handle.fileno())
        if temporary_path is None:
            raise StoreError("private backup temporary file was not created")
        try:
            os.chmod(temporary_path, 0o600)
        except OSError:
            pass
        os.replace(temporary_path, destination)
        fsync_directory(destination.parent)
    except OSError as exc:
        raise StoreError(f"could not create private backup {destination.name}") from exc
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


@contextmanager
def advisory_file_lock(path: Path) -> Iterator[None]:
    ensure_private_directory(path.parent)
    with PROCESS_LOCK:
        with path.open("a+b") as handle:
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                msvcrt = cast(Any, importlib.import_module("msvcrt"))
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class JsonStore:
    def __init__(
        self,
        data_path: Path,
        seed_path: Path,
        legacy_path: Path,
        *,
        max_entries: int,
        max_data_bytes: int,
    ) -> None:
        self.data_path = data_path
        self.seed_path = seed_path
        self.legacy_path = legacy_path
        self.lock_path = data_path.with_suffix(data_path.suffix + ".lock")
        self.max_entries = max_entries
        self.max_data_bytes = max_data_bytes

    def initialize(self) -> None:
        with advisory_file_lock(self.lock_path):
            ensure_private_directory(self.data_path.parent)
            if self.data_path.exists():
                self._read_unlocked()
                return

            source: Path | None = None
            if self.legacy_path.exists():
                source = self.legacy_path
            elif self.seed_path.exists():
                source = self.seed_path

            if source is None:
                store = {
                    "version": DATA_SCHEMA_VERSION,
                    "exportedAt": utc_now_iso(),
                    "entries": [],
                }
            else:
                store = self._read_external_store(source)
                if source == self.legacy_path:
                    backup = self.data_path.parent / "data.pre-v02.00.00.json"
                    if not backup.exists():
                        atomic_private_copy(source, backup)

            self._write_unlocked(store)

    def _read_external_store(self, path: Path) -> dict[str, Any]:
        if path.stat().st_size > self.max_data_bytes:
            raise StoreError(f"data source exceeds {self.max_data_bytes} bytes")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StoreError(f"could not read data source {path}") from exc
        try:
            return normalize_store_object(raw, self.max_entries)
        except ValidationError as exc:
            raise StoreError(f"data source validation failed: {exc}") from exc

    def _read_unlocked(self) -> dict[str, Any]:
        if not self.data_path.exists():
            return {
                "version": DATA_SCHEMA_VERSION,
                "exportedAt": utc_now_iso(),
                "entries": [],
            }
        if self.data_path.stat().st_size > self.max_data_bytes:
            raise StoreError(f"data store exceeds {self.max_data_bytes} bytes")
        try:
            raw = json.loads(self.data_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StoreError("data store is unreadable or corrupt") from exc
        try:
            return normalize_store_object(raw, self.max_entries)
        except ValidationError as exc:
            raise StoreError(f"data store validation failed: {exc}") from exc

    def _write_unlocked(self, store: dict[str, Any]) -> None:
        store = {
            "version": DATA_SCHEMA_VERSION,
            "exportedAt": store.get("exportedAt") or utc_now_iso(),
            "entries": store.get("entries", []),
        }
        encoded = (json.dumps(store, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        if len(encoded) > self.max_data_bytes:
            raise StoreError(f"data store would exceed {self.max_data_bytes} bytes")

        ensure_private_directory(self.data_path.parent)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{self.data_path.name}.",
                suffix=".tmp",
                dir=self.data_path.parent,
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            if temporary_path is None:
                raise StoreError("data store temporary file was not created")
            try:
                os.chmod(temporary_path, 0o600)
            except OSError:
                pass
            os.replace(temporary_path, self.data_path)
            fsync_directory(self.data_path.parent)
        except OSError as exc:
            raise StoreError("atomic data store write failed") from exc
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)

    def read(self) -> dict[str, Any]:
        with advisory_file_lock(self.lock_path):
            return self._read_unlocked()

    def mutate(self, mutation: Callable[[dict[str, Any]], T]) -> T:
        with advisory_file_lock(self.lock_path):
            store = self._read_unlocked()
            result = mutation(store)
            store["version"] = DATA_SCHEMA_VERSION
            store["exportedAt"] = utc_now_iso()
            self._write_unlocked(store)
            return result

    def replace(self, entries: list[dict[str, Any]]) -> Path | None:
        if len(entries) > self.max_entries:
            raise ValidationError(f"entries must contain no more than {self.max_entries} items")
        with advisory_file_lock(self.lock_path):
            backup: Path | None = None
            if self.data_path.exists():
                backup = self.data_path.with_suffix(self.data_path.suffix + ".bak")
                atomic_private_copy(self.data_path, backup)
            self._write_unlocked(
                {
                    "version": DATA_SCHEMA_VERSION,
                    "exportedAt": utc_now_iso(),
                    "entries": entries,
                }
            )
            return backup


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: OrderedDict[str, deque[float]] = OrderedDict()
        self._max_keys = 10_000
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            events = self._events.setdefault(key, deque())
            self._events.move_to_end(key)
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(now)
            while len(self._events) > self._max_keys:
                self._events.popitem(last=False)
            return True


def tokenize(query: str) -> list[dict[str, str]]:
    text = query.strip()
    output: list[dict[str, str]] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char in {"(", ")"}:
            output.append({"type": char})
            index += 1
            continue
        if char == '"':
            end = index + 1
            buffer: list[str] = []
            while end < len(text) and text[end] != '"':
                buffer.append(text[end])
                end += 1
            output.append({"type": "TERM", "value": "".join(buffer).lower()})
            index = end + 1 if end < len(text) else end
            continue
        end = index
        buffer = []
        while end < len(text) and not text[end].isspace() and text[end] not in {"(", ")"}:
            buffer.append(text[end])
            end += 1
        word = "".join(buffer)
        upper = word.upper()
        if upper in {"AND", "OR", "NOT"}:
            output.append({"type": upper})
        else:
            output.append({"type": "TERM", "value": word.lower()})
        index = end

    with_implicit_and: list[dict[str, str]] = []
    for position, token in enumerate(output):
        next_token = output[position + 1] if position + 1 < len(output) else None
        with_implicit_and.append(token)
        if next_token is None:
            continue
        token_is_value = token["type"] in {"TERM", ")"}
        next_is_value = next_token["type"] in {"TERM", "(", "NOT"}
        if token_is_value and next_is_value:
            with_implicit_and.append({"type": "AND"})
    return with_implicit_and


def to_rpn(tokens: list[dict[str, str]]) -> list[dict[str, str]]:
    precedence = {"NOT": 3, "AND": 2, "OR": 1}
    output: list[dict[str, str]] = []
    operators: list[dict[str, str]] = []
    for token in tokens:
        token_type = token["type"]
        if token_type == "TERM":
            output.append(token)
        elif token_type == "(":
            operators.append(token)
        elif token_type == ")":
            while operators and operators[-1]["type"] != "(":
                output.append(operators.pop())
            if operators and operators[-1]["type"] == "(":
                operators.pop()
        elif token_type in precedence:
            while operators and operators[-1]["type"] != "(":
                top = operators[-1]["type"]
                if precedence.get(top, 0) > precedence[token_type] or (
                    precedence.get(top, 0) == precedence[token_type] and token_type != "NOT"
                ):
                    output.append(operators.pop())
                else:
                    break
            operators.append(token)
    while operators:
        operator = operators.pop()
        if operator["type"] not in {"(", ")"}:
            output.append(operator)
    return output


def eval_rpn(rpn: list[dict[str, str]], text: str) -> bool:
    stack: list[bool] = []
    for token in rpn:
        token_type = token["type"]
        if token_type == "TERM":
            value = token.get("value", "")
            stack.append(value in text if value else True)
        elif token_type == "NOT":
            stack.append(not (stack.pop() if stack else False))
        elif token_type in {"AND", "OR"}:
            right = stack.pop() if stack else False
            left = stack.pop() if stack else False
            stack.append(left and right if token_type == "AND" else left or right)
    return stack[-1] if stack else True


def matches_query(entry: dict[str, Any], query: str) -> bool:
    if not query.strip():
        return True
    searchable = " ".join(
        [
            str(entry.get("title", "")),
            str(entry.get("url", "")),
            str(entry.get("description", "")),
            " ".join(str(tag) for tag in entry.get("tags", [])),
        ]
    ).lower()
    return eval_rpn(to_rpn(tokenize(query)), searchable)


def tag_prefix_match(entry: dict[str, Any], prefix: str) -> bool:
    if prefix == "__ALL__":
        return True
    if prefix == "Untagged":
        return not entry.get("tags")
    return any(
        str(tag) == prefix or str(tag).startswith(f"{prefix}/")
        for tag in entry.get("tags", [])
    )


def build_tag_tree(entries: list[dict[str, Any]]) -> dict[str, Any]:
    root: dict[str, Any] = {
        "name": "All",
        "path": "__ALL__",
        "children": {},
        "count": len(entries),
    }
    root["children"]["Untagged"] = {
        "name": "Untagged",
        "path": "Untagged",
        "children": {},
        "count": 0,
    }

    for entry in entries:
        tags = entry.get("tags", [])
        if not tags:
            root["children"]["Untagged"]["count"] += 1
            continue
        for raw_tag in tags:
            parts = [part.strip() for part in str(raw_tag).split("/") if part.strip()]
            current = root
            accumulated = ""
            for part in parts:
                accumulated = f"{accumulated}/{part}" if accumulated else part
                children = current["children"]
                child = children.setdefault(
                    part,
                    {
                        "name": part,
                        "path": accumulated,
                        "children": {},
                        "count": 0,
                    },
                )
                child["count"] += 1
                current = child
    return root


def _is_loopback(address: str | None) -> bool:
    if not address:
        return False
    if address.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


def _normalize_origin_value(origin: str) -> str | None:
    if not origin or "\\" in origin or any(character.isspace() for character in origin):
        return None
    try:
        parsed = urllib.parse.urlsplit(origin)
        port = parsed.port
    except ValueError:
        return None
    scheme = parsed.scheme.lower()
    raw_hostname = parsed.hostname
    if (
        scheme not in {"http", "https"}
        or not raw_hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return None
    try:
        parsed_ip = ipaddress.ip_address(raw_hostname)
        hostname = parsed_ip.compressed
        if parsed_ip.version == 6:
            hostname = f"[{hostname}]"
    except ValueError:
        try:
            hostname = raw_hostname.encode("idna").decode("ascii").lower().rstrip(".")
        except UnicodeError:
            return None
    if not hostname:
        return None
    default_port = 80 if scheme == "http" else 443
    netloc = hostname if port in {None, default_port} else f"{hostname}:{port}"
    return f"{scheme}://{netloc}"


def _validated_origins(origins: tuple[str, ...]) -> frozenset[str]:
    validated: set[str] = set()
    for origin in origins:
        if origin == "*":
            raise RuntimeError("KELLMARKS_ALLOWED_ORIGINS must not contain a wildcard")
        normalized = _normalize_origin_value(origin)
        if normalized is None:
            raise RuntimeError(f"invalid allowed origin: {origin}")
        validated.add(normalized)
    return frozenset(validated)


def _validated_public_origin(origin: str) -> str:
    if not origin:
        return ""
    normalized = _normalize_origin_value(origin)
    if normalized is None:
        raise RuntimeError("KELLMARKS_PUBLIC_ORIGIN must be an exact HTTP(S) origin")
    return normalized


def _validated_trusted_hosts(hosts: tuple[str, ...]) -> list[str]:
    validated: list[str] = []
    for raw_host in hosts:
        host = raw_host.strip()
        if not host:
            continue
        if (
            "*" in host
            or host.startswith(".")
            or "://" in host
            or "/" in host
            or "@" in host
            or CONTROL_CHAR_RE.search(host)
            or any(character.isspace() for character in host)
        ):
            raise RuntimeError(f"invalid trusted host: {raw_host}")
        if host.startswith("[") and host.endswith("]"):
            try:
                address = ipaddress.ip_address(host[1:-1])
            except ValueError as exc:
                raise RuntimeError(f"invalid trusted host: {raw_host}") from exc
            if address.version != 6:
                raise RuntimeError(f"invalid trusted host: {raw_host}")
            normalized = f"[{address.compressed}]"
        else:
            if ":" in host:
                raise RuntimeError(
                    f"trusted hosts must not include ports: {raw_host}"
                )
            try:
                normalized = ipaddress.ip_address(host).compressed
            except ValueError:
                try:
                    normalized = host.encode("idna").decode("ascii").lower().rstrip(".")
                except UnicodeError as exc:
                    raise RuntimeError(f"invalid trusted host: {raw_host}") from exc
                labels = normalized.split(".")
                if any(
                    not label
                    or len(label) > 63
                    or not re.fullmatch(
                        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label
                    )
                    for label in labels
                ):
                    raise RuntimeError(
                        f"invalid trusted host: {raw_host}"
                    ) from None
        validated.append(normalized)
    if not validated:
        raise RuntimeError("KELLMARKS_TRUSTED_HOSTS must contain at least one host")
    return validated


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    base_dir = Path(__file__).resolve().parent.parent
    server_dir = Path(__file__).resolve().parent
    default_data_path = server_dir / "instance" / "data.json"

    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(
        APP_VERSION=APP_VERSION,
        DATA_SCHEMA_VERSION=DATA_SCHEMA_VERSION,
        DATA_PATH=Path(os.getenv("KELLMARKS_DATA_FILE", str(default_data_path))),
        SEED_PATH=base_dir / "assets" / "sample-data.json",
        LEGACY_DATA_PATH=Path(
            os.getenv(
                "KELLMARKS_LEGACY_DATA_FILE",
                str(base_dir / "assets" / "data.json"),
            )
        ),
        MAX_CONTENT_LENGTH=_env_int(
            "KELLMARKS_MAX_REQUEST_BYTES",
            DEFAULT_MAX_REQUEST_BYTES,
            16_384,
            16_777_216,
        ),
        MAX_DATA_BYTES=_env_int(
            "KELLMARKS_MAX_DATA_BYTES",
            DEFAULT_MAX_DATA_BYTES,
            1_048_576,
            268_435_456,
        ),
        MAX_ENTRIES=_env_int(
            "KELLMARKS_MAX_ENTRIES", DEFAULT_MAX_ENTRIES, 1, 100_000
        ),
        MAX_IMPORT_ENTRIES=_env_int(
            "KELLMARKS_MAX_IMPORT_ENTRIES",
            DEFAULT_MAX_IMPORT_ENTRIES,
            1,
            100_000,
        ),
        AUTH_TOKEN=os.getenv("KELLMARKS_AUTH_TOKEN", ""),
        REQUIRE_AUTH=_env_bool("KELLMARKS_REQUIRE_AUTH", False),
        ENABLE_HSTS=_env_bool("KELLMARKS_ENABLE_HSTS", False),
        ALLOWED_ORIGINS=_validated_origins(_env_csv("KELLMARKS_ALLOWED_ORIGINS")),
        PUBLIC_ORIGIN=_validated_public_origin(
            os.getenv("KELLMARKS_PUBLIC_ORIGIN", "").strip()
        ),
        TRUSTED_HOSTS=_validated_trusted_hosts(
            _env_csv(
                "KELLMARKS_TRUSTED_HOSTS",
                ("localhost", "127.0.0.1", "[::1]"),
            )
        ),
        WRITE_RATE_LIMIT=_env_int("KELLMARKS_WRITE_RATE_LIMIT", 120, 1, 10_000),
        DDG_RATE_LIMIT=_env_int("KELLMARKS_DDG_RATE_LIMIT", 30, 1, 10_000),
        AUTH_RATE_LIMIT=_env_int("KELLMARKS_AUTH_RATE_LIMIT", 20, 1, 10_000),
    )
    if test_config:
        app.config.update(test_config)

    app.config["ALLOWED_ORIGINS"] = _validated_origins(
        tuple(app.config.get("ALLOWED_ORIGINS", ()))
    )
    app.config["TRUSTED_HOSTS"] = _validated_trusted_hosts(
        tuple(app.config.get("TRUSTED_HOSTS", ()))
    )
    app.config["PUBLIC_ORIGIN"] = _validated_public_origin(
        str(app.config.get("PUBLIC_ORIGIN", ""))
    )
    token = str(app.config.get("AUTH_TOKEN", ""))
    if token and len(token) < 32:
        raise RuntimeError("KELLMARKS_AUTH_TOKEN must be at least 32 characters")
    if token and (
        token != token.strip()
        or CONTROL_CHAR_RE.search(token)
        or any(character.isspace() for character in token)
    ):
        raise RuntimeError("KELLMARKS_AUTH_TOKEN must not contain whitespace")
    if app.config.get("REQUIRE_AUTH") and not token:
        raise RuntimeError("KELLMARKS_REQUIRE_AUTH requires KELLMARKS_AUTH_TOKEN")
    if (
        app.config.get("PUBLIC_ORIGIN") or app.config.get("ALLOWED_ORIGINS")
    ) and not token:
        raise RuntimeError(
            "public or cross-origin access requires KELLMARKS_AUTH_TOKEN"
        )
    store = JsonStore(
        Path(app.config["DATA_PATH"]),
        Path(app.config["SEED_PATH"]),
        Path(app.config["LEGACY_DATA_PATH"]),
        max_entries=int(app.config["MAX_ENTRIES"]),
        max_data_bytes=int(app.config["MAX_DATA_BYTES"]),
    )
    store.initialize()
    app.extensions["kellmarks_store"] = store

    limiter = SlidingWindowLimiter()
    app.extensions["kellmarks_limiter"] = limiter

    app.logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    app.logger.addHandler(handler)
    app.logger.setLevel(os.getenv("KELLMARKS_LOG_LEVEL", "INFO").upper())
    app.logger.propagate = False

    def log_event(level: int, event: str, **fields: Any) -> None:
        record = {
            "timestamp": utc_now_iso(),
            "level": logging.getLevelName(level),
            "event": event,
            **fields,
        }
        app.logger.log(level, json.dumps(record, separators=(",", ":"), default=str))

    def request_client_key(suffix: str) -> str:
        return f"{request.remote_addr or 'unknown'}:{suffix}"

    def origin_is_allowed(origin: str) -> bool:
        normalized = _normalize_origin_value(origin)
        request_origin = _normalize_origin_value(request.host_url)
        if normalized is None:
            return False
        accepted_origins = set(app.config["ALLOWED_ORIGINS"])
        if request_origin is not None:
            accepted_origins.add(request_origin)
        public_origin = str(app.config.get("PUBLIC_ORIGIN", ""))
        if public_origin:
            accepted_origins.add(public_origin)
        return normalized in accepted_origins

    def request_host_is_loopback() -> bool:
        try:
            hostname = urllib.parse.urlsplit(f"//{request.host}").hostname
        except ValueError:
            return False
        return _is_loopback(hostname)

    def json_error(message: str, status: int) -> tuple[Response, int]:
        return jsonify({"error": message, "requestId": g.get("request_id")}), status

    def parse_json_object() -> dict[str, Any]:
        if not request.is_json:
            raise UnsupportedMediaType("Content-Type must be application/json")
        payload = request.get_json(silent=False)
        if not isinstance(payload, dict):
            raise ValidationError("request body must be a JSON object")
        return payload

    def enforce_write_rate_limit() -> Response | None:
        if limiter.allow(
            request_client_key("write"), int(app.config["WRITE_RATE_LIMIT"]), 60
        ):
            return None
        return json_error("write rate limit exceeded", 429)[0]

    @app.before_request
    def security_gate() -> Response | tuple[Response, int] | None:
        supplied_request_id = request.headers.get("X-Request-ID", "")
        g.request_id = (
            supplied_request_id
            if REQUEST_ID_RE.fullmatch(supplied_request_id)
            else secrets.token_hex(8)
        )
        g.request_started = time.monotonic()

        if not request.path.startswith("/api/"):
            return None

        origin = request.headers.get("Origin")
        if origin and not origin_is_allowed(origin):
            log_event(
                logging.WARNING,
                "cors_rejected",
                requestId=g.request_id,
                remoteAddress=request.remote_addr,
            )
            return json_error("origin is not allowed", 403)

        if request.method == "OPTIONS":
            return Response(status=204)

        configured_token = str(app.config.get("AUTH_TOKEN", ""))
        forwarded_request = any(
            request.headers.get(name)
            for name in ("Forwarded", "X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto")
        )
        auth_required = bool(configured_token) or bool(app.config.get("REQUIRE_AUTH"))
        auth_required = (
            auth_required
            or forwarded_request
            or not _is_loopback(request.remote_addr)
            or not request_host_is_loopback()
        )
        if not auth_required:
            return None

        if not configured_token:
            log_event(
                logging.WARNING,
                "remote_access_denied",
                requestId=g.request_id,
                remoteAddress=request.remote_addr,
            )
            return json_error("remote access requires KELLMARKS_AUTH_TOKEN", 403)

        header = request.headers.get("Authorization", "")
        scheme, separator, credentials = header.partition(" ")
        supplied_token = credentials if separator and scheme.lower() == "bearer" else ""
        if supplied_token and hmac.compare_digest(supplied_token, configured_token):
            return None

        if not limiter.allow(
            request_client_key("auth"), int(app.config["AUTH_RATE_LIMIT"]), 60
        ):
            return json_error("authentication rate limit exceeded", 429)

        log_event(
            logging.WARNING,
            "authentication_failed",
            requestId=g.request_id,
            remoteAddress=request.remote_addr,
        )
        response, status = json_error("authentication required", 401)
        response.headers["WWW-Authenticate"] = 'Bearer realm="Kellmarks"'
        return response, status

    @app.after_request
    def secure_response(response: Response) -> Response:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' https: data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'none'; "
            "frame-ancestors 'none'; "
            "form-action 'self'"
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Request-ID"] = g.get("request_id", secrets.token_hex(8))
        if app.config.get("ENABLE_HSTS"):
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        origin = request.headers.get("Origin")
        if origin and origin_is_allowed(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type, X-Request-ID"
            )
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, DELETE, OPTIONS"
            )
            response.headers.add("Vary", "Origin")

        if request.path.startswith("/api/"):
            duration_ms = round(
                (time.monotonic() - g.get("request_started", time.monotonic())) * 1000,
                2,
            )
            log_event(
                logging.INFO,
                "api_request",
                requestId=g.get("request_id"),
                method=request.method,
                path=request.path,
                status=response.status_code,
                durationMs=duration_ms,
                remoteAddress=request.remote_addr,
            )
        return response

    @app.errorhandler(ValidationError)
    def handle_validation_error(error: ValidationError) -> tuple[Response, int]:
        return json_error(str(error), 400)

    @app.errorhandler(RequestEntityTooLarge)
    def handle_request_too_large(_: RequestEntityTooLarge) -> tuple[Response, int]:
        return json_error("request body is too large", 413)

    @app.errorhandler(UnsupportedMediaType)
    def handle_unsupported_media(error: UnsupportedMediaType) -> tuple[Response, int]:
        return json_error(error.description, 415)

    @app.errorhandler(BadRequest)
    def handle_bad_request(_: BadRequest) -> tuple[Response, int]:
        return json_error("malformed JSON request", 400)

    @app.errorhandler(StoreError)
    def handle_store_error(error: StoreError) -> tuple[Response, int]:
        log_event(
            logging.ERROR,
            "store_error",
            requestId=g.get("request_id"),
            errorType=type(error).__name__,
        )
        return json_error("persistent store operation failed", 500)

    @app.get("/")
    def root_index() -> Response:
        return send_from_directory(base_dir, "index.html")

    @app.get("/assets/<path:filename>")
    def static_asset(filename: str) -> Response | tuple[Response, int]:
        if filename not in STATIC_ASSETS:
            return Response("Not found", status=404, mimetype="text/plain"), 404
        return send_from_directory(base_dir / "assets", filename)

    @app.get("/favicon.ico")
    def favicon() -> Response:
        return send_from_directory(base_dir, "favicon.ico")

    @app.get("/api/health")
    def health() -> Response:
        return jsonify(
            {
                "ok": True,
                "version": APP_VERSION,
                "dataSchemaVersion": DATA_SCHEMA_VERSION,
                "time": utc_now_iso(),
            }
        )

    @app.get("/api/entries")
    def list_entries() -> Response:
        return jsonify(store.read()["entries"])

    @app.post("/api/entries")
    def create_entry() -> tuple[Response, int] | Response:
        limited = enforce_write_rate_limit()
        if limited is not None:
            return limited, 429
        cleaned = normalize_entry_payload(parse_json_object())
        now = utc_now_iso()

        def mutation(data: dict[str, Any]) -> dict[str, Any]:
            entries = data["entries"]
            if len(entries) >= int(app.config["MAX_ENTRIES"]):
                raise ValidationError("entry limit reached")
            entry = {
                "id": normalize_entry_id(None, generate=True),
                "createdAt": now,
                "updatedAt": now,
                **cleaned,
            }
            entries.insert(0, entry)
            return entry

        entry = store.mutate(mutation)
        return jsonify(entry), 201

    @app.get("/api/entries/<entry_id>")
    def get_entry(entry_id: str) -> tuple[Response, int] | Response:
        normalized_id = normalize_entry_id(entry_id)
        entry = next(
            (
                item
                for item in store.read()["entries"]
                if str(item.get("id")) == normalized_id
            ),
            None,
        )
        if entry is None:
            return json_error("not found", 404)
        return jsonify(entry)

    @app.put("/api/entries/<entry_id>")
    def update_entry(entry_id: str) -> tuple[Response, int] | Response:
        limited = enforce_write_rate_limit()
        if limited is not None:
            return limited, 429
        normalized_id = normalize_entry_id(entry_id)
        payload = parse_json_object()

        def mutation(data: dict[str, Any]) -> dict[str, Any]:
            for index, current in enumerate(data["entries"]):
                if current["id"] != normalized_id:
                    continue
                merged = {**current, **payload}
                cleaned = normalize_entry_payload(merged)
                updated = {**current, **cleaned, "updatedAt": utc_now_iso()}
                data["entries"][index] = updated
                return updated
            raise LookupError

        try:
            entry = store.mutate(mutation)
        except LookupError:
            return json_error("not found", 404)
        return jsonify(entry)

    @app.delete("/api/entries/<entry_id>")
    def delete_entry(entry_id: str) -> tuple[Response, int] | Response:
        limited = enforce_write_rate_limit()
        if limited is not None:
            return limited, 429
        normalized_id = normalize_entry_id(entry_id)

        def mutation(data: dict[str, Any]) -> dict[str, Any]:
            entries = cast(list[dict[str, Any]], data["entries"])
            for index, current in enumerate(entries):
                if current["id"] == normalized_id:
                    return entries.pop(index)
            raise LookupError

        try:
            deleted = store.mutate(mutation)
        except LookupError:
            return json_error("not found", 404)
        return jsonify({"deleted": True, "entry": deleted})

    @app.get("/api/export")
    def export_all() -> Response:
        return jsonify(store.read())

    @app.post("/api/import")
    def import_all() -> tuple[Response, int] | Response:
        limited = enforce_write_rate_limit()
        if limited is not None:
            return limited, 429
        payload = parse_json_object()
        entries = normalize_import_entries(
            payload.get("entries"), int(app.config["MAX_IMPORT_ENTRIES"])
        )
        backup = store.replace(entries)
        return jsonify(
            {
                "imported": len(entries),
                "backupCreated": backup is not None,
            }
        )

    @app.get("/api/tags/tree")
    def tags_tree() -> Response:
        return jsonify(build_tag_tree(store.read()["entries"]))

    @app.get("/api/search")
    def search() -> Response:
        query = _require_text(request.args.get("q", ""), "q", MAX_QUERY_LENGTH)
        path = _require_text(
            request.args.get("path", "__ALL__"), "path", MAX_PATH_LENGTH, required=True
        )
        entries = [
            entry
            for entry in store.read()["entries"]
            if tag_prefix_match(entry, path) and matches_query(entry, query)
        ]
        return jsonify(
            {
                "q": query,
                "path": path,
                "count": len(entries),
                "entries": entries,
            }
        )

    @app.get("/api/external/ddg")
    def ddg_proxy() -> tuple[Response, int] | Response:
        query = _require_text(
            request.args.get("q", ""),
            "q",
            MAX_EXTERNAL_QUERY_LENGTH,
            required=True,
        )
        if not limiter.allow(
            request_client_key("ddg"), int(app.config["DDG_RATE_LIMIT"]), 60
        ):
            return json_error("external search rate limit exceeded", 429)

        api_url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode(
            {
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
            }
        )
        outbound = urllib.request.Request(
            api_url,
            headers={"User-Agent": f"Kellmarks/{APP_VERSION}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(outbound, timeout=8) as upstream:  # nosec B310
                final_url = urllib.parse.urlsplit(upstream.geturl())
                final_host = (final_url.hostname or "").lower()
                if final_url.scheme != "https" or not (
                    final_host == "duckduckgo.com"
                    or final_host.endswith(".duckduckgo.com")
                ):
                    raise StoreError("DuckDuckGo redirected to an untrusted host")
                raw = upstream.read(DDG_MAX_RESPONSE_BYTES + 1)
            if len(raw) > DDG_MAX_RESPONSE_BYTES:
                raise StoreError("DuckDuckGo response exceeded the size limit")
            data = json.loads(raw.decode("utf-8", errors="strict"))
            if not isinstance(data, dict):
                raise StoreError("DuckDuckGo returned an invalid JSON document")
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            RecursionError,
            StoreError,
        ) as exc:
            log_event(
                logging.WARNING,
                "external_search_failed",
                requestId=g.get("request_id"),
                errorType=type(exc).__name__,
            )
            return json_error("external search is unavailable", 502)

        candidates: list[dict[str, str]] = []
        raw_results = data.get("Results")
        if isinstance(raw_results, list):
            candidates.extend(
                result for result in raw_results[:1_000] if isinstance(result, dict)
            )

        def walk_topics(topics: Any) -> Iterator[dict[str, str]]:
            pending = list(reversed(topics)) if isinstance(topics, list) else []
            visited = 0
            while pending and visited < 1_000:
                topic = pending.pop()
                visited += 1
                if not isinstance(topic, dict):
                    continue
                nested = topic.get("Topics")
                if isinstance(nested, list):
                    pending.extend(reversed(nested))
                else:
                    yield topic

        candidates.extend(walk_topics(data.get("RelatedTopics")))
        results: list[dict[str, str]] = []
        seen: set[str] = set()
        for candidate in candidates:
            try:
                url = normalize_http_url(candidate.get("FirstURL"), required=True)
            except ValidationError:
                continue
            try:
                text = _require_text(candidate.get("Text", ""), "result text", 1_000)
            except ValidationError:
                continue
            if not text or url in seen:
                continue
            seen.add(url)
            results.append(
                {
                    "url": url,
                    "title": text.split(" - ", 1)[0][:MAX_TITLE_LENGTH],
                    "snippet": text[:280],
                }
            )
            if len(results) >= 20:
                break
        return jsonify({"q": query, "results": results})

    return app


app = create_app()


if __name__ == "__main__":
    bind_host = os.getenv("KELLMARKS_BIND_HOST", "127.0.0.1").strip()
    port = _env_int("KELLMARKS_PORT", DEFAULT_PORT, 1, 65535)
    if not _is_loopback(bind_host):
        raise RuntimeError(
            "The built-in server is loopback-only. Use an HTTPS reverse proxy "
            "or production WSGI server for network access."
        )
    app.run(host=bind_host, port=port, debug=False, use_reloader=False)
