# Kellmarks API 02.01.01

Default base URL: `http://127.0.0.1:8787`

## Authentication

Direct loopback access is allowed without authentication only when no token is configured, the Host is loopback, and the request contains no proxy-forwarding headers. Public Host, public-origin, cross-origin, proxied, configured-token, and non-loopback access requires:

```http
Authorization: Bearer <KELLMARKS_AUTH_TOKEN>
```

A missing or invalid token returns `401`. Remote access without a configured token returns `403`. Repeated invalid attempts return `429`.

Never send the token in the URL. The API does not use cookies, so bearer-token requests do not require a CSRF token.

## Common headers

Every response includes `X-Request-ID`. Clients may supply a request ID containing 1 to 64 letters, digits, periods, underscores, colons, or hyphens. Invalid values are replaced.

Write requests require:

```http
Content-Type: application/json
```

The default request-body limit is 1 MiB.

## Entry model

```json
{
  "id": "e-2d6e85a248364080b760cdfef0bbb2ac",
  "title": "Example",
  "url": "https://example.com/",
  "iconUrl": "https://example.com/icon.png",
  "description": "Reference site",
  "tags": ["work/reference"],
  "createdAt": "2026-08-13T12:00:00Z",
  "updatedAt": "2026-08-13T12:00:00Z"
}
```

Rules:

- `url` is required, uses HTTP or HTTPS, has a host, contains no credentials, and is at most 2048 characters.
- `iconUrl` is empty or follows the same URL rules.
- `title` is at most 120 characters.
- `description` is at most 600 characters.
- `tags` contains at most 32 values, each at most 80 characters.
- imported `id` values use letters, digits, periods, underscores, colons, and hyphens, with at most 80 characters.
- create operations generate IDs server-side.

## Health

`GET /api/health`

```json
{
  "ok": true,
  "version": "02.01.01",
  "dataSchemaVersion": 2,
  "time": "2026-08-13T12:00:00Z"
}
```

## Entries

`GET /api/entries` returns an array of entries.

`POST /api/entries` creates an entry and returns `201`.

```json
{
  "title": "Example",
  "url": "https://example.com/",
  "iconUrl": "",
  "description": "Reference site",
  "tags": ["work/reference"]
}
```

`GET /api/entries/{id}` returns one entry or `404`.

`PUT /api/entries/{id}` updates supplied fields and retains omitted fields.

`DELETE /api/entries/{id}` returns:

```json
{
  "deleted": true,
  "entry": {}
}
```

## Import and export

`GET /api/export` returns:

```json
{
  "version": 2,
  "exportedAt": "2026-08-13T12:00:00Z",
  "entries": []
}
```

`POST /api/import` validates the complete replacement before writing it:

```json
{
  "entries": []
}
```

Response:

```json
{
  "imported": 0,
  "backupCreated": true
}
```

The default import limit is 5000 entries. Duplicate IDs or any unsafe entry reject the complete import. A successful replacement creates a `.bak` file when prior data exists.

## Tags

`GET /api/tags/tree` returns the hierarchical tag tree.

## Search

`GET /api/search?q=BOOLEAN_QUERY&path=TAG_PREFIX`

Examples:

```text
/api/search?q=vpn%20AND%20aws&path=work/security
/api/search?q=%22zero%20trust%22%20OR%20iam&path=__ALL__
```

The internal query limit is 512 characters; the tag path limit is 256.

## External search

`GET /api/external/ddg?q=QUERY`

The proxy calls a fixed HTTPS DuckDuckGo endpoint, bounds the upstream response to 2 MiB, validates the final hostname, filters output URLs, and returns at most 20 items. The query limit is 256 characters.

```json
{
  "q": "QUERY",
  "results": [
    {
      "url": "https://example.com/",
      "title": "Title",
      "snippet": "Text"
    }
  ]
}
```

## Errors

Most errors use:

```json
{
  "error": "message",
  "requestId": "4f280fcc305d77df"
}
```

Relevant status codes:

- `400`: validation or malformed JSON
- `401`: bearer authentication required or invalid
- `403`: remote access, CORS, or policy denial
- `404`: route or entry not found
- `413`: request body too large
- `415`: JSON content type required
- `429`: write, authentication, or external-search rate limit
- `500`: persistent store failure
- `502`: external search unavailable

## Reviewed import additions in 02.01.00

`POST /api/import/preview` is authenticated and subject to the write-rate limit even though it does not write. Supply JSON with `format` (`json`, the default, or `html`), `mode` (`merge`, the preview default, or `replace`), `titleSource` (`existing` or `incoming`) and `descriptionSource` (`existing` or `incoming`). Both source choices default to `existing` and apply across the import. JSON uses `entries`; HTML uses an `html` string. HTML is never rendered or fetched.

```json
{
  "format": "json",
  "mode": "merge",
  "titleSource": "existing",
  "descriptionSource": "incoming",
  "entries": [
    {"url": "https://example.com/reference", "title": "Reference", "tags": ["research"]}
  ]
}
```

A valid preview returns `valid: true`, a `baseRevision`, normalized `incomingEntries`, `mode`, `totalCount`, `newCount`, `duplicateCount`, `updatedCount`, `unchangedCount`, `replacedCount`, `details`, `invalidCount: 0` and `errors: []`. `updatedCount` counts distinct pre-existing bookmarks changed; duplicate and unchanged counts refer to incoming matches. Replacement reports incoming count as `newCount` and the old collection size as `replacedCount`; it does not perform merge analysis.

Individual invalid entries return HTTP 200 with `valid: false`, a complete `invalidCount`, up to 50 `{index, error}` details (zero-based indices) and empty `incomingEntries`. Invalid format/options, ambiguous identity, final-library limits or malformed source return `400`. No invalid candidate is applied. The response is private, not cacheable, and can contain bookmark URLs.

Apply by POSTing to `/api/import` with explicit `mode`, the same field-source choices, `format: "json"`, the returned `incomingEntries` as `entries`, and `baseRevision`. Use normalized JSON after an HTML preview so IDs and timestamps stay those that were reviewed.



The following runnable local example previews and applies without exposing an authentication token in the URL:

```python
import json
import os
from urllib.request import Request, urlopen

base = "http://127.0.0.1:8787"
headers = {"Content-Type": "application/json"}
if os.environ.get("KELLMARKS_AUTH_TOKEN"):
    headers["Authorization"] = "Bearer " + os.environ["KELLMARKS_AUTH_TOKEN"]

def post(path, body):
    request = Request(base + path, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urlopen(request, timeout=10) as response:
        return json.load(response)

options = {"mode": "merge", "titleSource": "existing", "descriptionSource": "existing"}
review = post("/api/import/preview", {**options, "entries": [{"url": "https://example.com", "title": "Example"}]})
if not review["valid"]:
    raise SystemExit(review["errors"])
print({key: review[key] for key in ("newCount", "updatedCount", "totalCount")})
if input("Apply this reviewed import? Type yes: ") == "yes":
    result = post("/api/import", {**options, "entries": review["incomingEntries"], "baseRevision": review["baseRevision"]})
    print(result)
```

Apply revalidates the entire candidate under the store lock. A mismatching revision returns `409`; preview again instead of ignoring the conflict. A missing/malformed revision returns `400`. Success includes the legacy `imported`/`backupCreated` fields plus `mode`, `added`, `updated` and `totalCount`. The original no-mode `/api/import` contract still replaces the collection and does not require a revision. New dashboard code never uses this unguarded compatibility path.

`GET /api/health` adds `externalRequestsAllowed`. `KELLMARKS_EXTERNAL_REQUESTS=0` makes `/api/external/ddg` return `403` before any upstream request. Authentication and other security gates still run first. The default `1` preserves direct API behavior; ordinary dashboard search no longer invokes DDG automatically.


## Version status — `GET /api/version` (02.01.01)

Uses the same authentication as other API routes. Returns HTTP 200 with status data even when GitHub is unavailable or external requests are disabled; authentication failures remain 401/403. No parameters are accepted to change the upstream URL or bypass caching.

```json
{
  "currentVersion": "02.01.01",
  "latestVersion": "02.01.01",
  "status": "current",
  "releaseUrl": "https://github.com/paulkakell/kellmarks/releases/tag/02.01.01",
  "checkedAt": "2026-09-27T19:00:00Z"
}
```

`status` is one of `current`, `update_available`, `ahead`, `unavailable`, `no_release` or `disabled`. `latestVersion` is null when no valid release was retrieved; `checkedAt` is null when checking is disabled, otherwise the timestamp of the last upstream attempt. Version components are compared numerically. Prereleases and nonnumeric tags are not treated as stable releases. Successful results are cached for 3,600 seconds and unsuccessful attempts for 300 seconds, per process.

The server fetches one fixed HTTPS GitHub endpoint, rejects redirects, limits upstream time to four seconds per network operation and response size to 262,144 bytes, and forwards no incoming authorization, cookies, query or bookmark data. `KELLMARKS_EXTERNAL_REQUESTS=0` returns `disabled` without network access. `/api/health` remains a local-only health and installed-version response.

## Creation-only tags (02.01.01)

`POST /api/entries` now fills normalized empty tags (missing, null, empty list, empty string or whitespace-only values) with up to five local site suggestions. Existing same-host tags have precedence over bundled site rules and the `sites/<hostname>` fallback. Nonempty explicit tags retain their existing validation and values. `PUT /api/entries/<id>` never runs this logic: an empty tag list clears tags, and omitted tags preserve the stored value. Import, export, store loading and migration do not generate tags. An omitted icon remains an empty stored `iconUrl`; favicon fallback is a consent-controlled frontend display behavior.
