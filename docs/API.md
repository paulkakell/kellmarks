# Kellmarks API

Base URL
- Default: http://127.0.0.1:8787

Auth
- None by default. If you expose this to the public internet, add auth and HTTPS before use.

Data model: Entry
```json
{
  "id": "string",
  "title": "string",
  "url": "https://example.com",
  "iconUrl": "https://example.com/icon.png",
  "description": "string",
  "tags": ["work/security", "aws/iam"],
  "createdAt": "ISO-8601 UTC",
  "updatedAt": "ISO-8601 UTC"
}
```

Endpoints

Health
- GET /api/health
Response
```json
{ "ok": true, "time": "2025-01-01T00:00:00Z" }
```

Entries
- GET /api/entries
Response: array of Entry

- POST /api/entries
Request body
```json
{ "title": "X", "url": "https://x", "iconUrl": "", "description": "", "tags": ["a/b", "c"] }
```
Response: created Entry (201)

- GET /api/entries/{id}
Response: Entry

- PUT /api/entries/{id}
Request body: same fields as POST, partial allowed
Response: updated Entry

- DELETE /api/entries/{id}
Response
```json
{ "deleted": true, "entry": { ... } }
```

Import and export
- GET /api/export
Response
```json
{ "version": 1, "exportedAt": "ISO-8601", "entries": [ ... ] }
```

- POST /api/import
Request body
```json
{ "entries": [ ...Entry... ] }
```
Response
```json
{ "imported": 123 }
```

Tags
- GET /api/tags/tree
Response
```json
{
  "name": "All",
  "path": "__ALL__",
  "count": 10,
  "children": {
    "Untagged": { "name": "Untagged", "path": "Untagged", "count": 2, "children": {} },
    "work": { "name": "work", "path": "work", "count": 6, "children": { "security": { ... } } }
  }
}
```

Search
- GET /api/search?q=BOOLEAN_QUERY&path=TAG_PREFIX
Examples
- /api/search?q=vpn%20AND%20aws&path=work/security
- /api/search?q="zero%20trust"%20OR%20iam&path=__ALL__

Response
```json
{ "q": "...", "path": "...", "count": 3, "entries": [ ... ] }
```

External search proxy
- GET /api/external/ddg?q=QUERY
Response
```json
{
  "q": "QUERY",
  "results": [
    { "url": "https://...", "title": "Title", "snippet": "Text..." }
  ]
}
```

Error format
- Most errors return
```json
{ "error": "message" }
```
with an HTTP 4xx status code.
