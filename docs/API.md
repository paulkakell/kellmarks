# Kellmarks API 02.00.02

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
  "version": "02.00.02",
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
