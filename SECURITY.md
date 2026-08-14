# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 02.00.01 | Yes |
| 02.00.00 | Yes |
| 01.xx.xx and earlier | No |

Older versions permit unauthenticated network access, broad cross-origin requests, and public runtime storage. Upgrade before using Kellmarks on a network.

## Reporting a vulnerability

Do not open a public issue containing exploit details, authentication tokens, private bookmark data, or filesystem paths. Use GitHub's private security advisory feature for `paulkakell/kellmarks` when available. Include:

- affected version and commit
- deployment topology
- minimal reproduction steps
- expected and observed behavior
- impact assessment
- suggested remediation, when known

Remove secrets and personal bookmark content from logs and screenshots.

## Deployment requirements

Kellmarks is secure by default for loopback development. The built-in server refuses non-loopback binding. Network deployment requires additional controls:

1. Use release 02.00.00 or newer.
2. Set a randomly generated `KELLMARKS_AUTH_TOKEN` containing at least 32 characters.
3. Keep the built-in server on loopback. Put a maintained HTTPS reverse proxy or production WSGI deployment at the network boundary.
4. Set `KELLMARKS_REQUIRE_AUTH=1`, `KELLMARKS_PUBLIC_ORIGIN` to the exact public HTTPS origin, and `KELLMARKS_ENABLE_HSTS=1` behind a reverse proxy.
5. Set `KELLMARKS_TRUSTED_HOSTS` to exact public hostnames and preserve the original `Host` header.
6. Leave `KELLMARKS_ALLOWED_ORIGINS` empty for one public frontend. Add only exact HTTPS origins for separate frontends. Public-origin or cross-origin configuration is refused unless a bearer token is set.
7. Keep `KELLMARKS_DATA_FILE`, its `.bak`, `.lock`, and migration backup outside every public web root.
8. Run as a dedicated unprivileged account with restrictive filesystem permissions.
9. Protect application and proxy logs because bookmark URLs can contain sensitive path or query information. Kellmarks does not log query-string values, but upstream proxies may.
10. Back up and test restoration of the private data file.

## Token handling

The token is accepted only in the `Authorization: Bearer` header. The browser stores it in session storage. Never commit it, expose it in frontend source, place it in a URL, or send it to a third-party logging service.

Rotate a token by stopping the service, setting a new value, and restarting. Existing browser sessions will receive `401` and request the replacement token.

## Security controls in 02.00.00

- fail-closed remote authorization
- constant-time bearer-token comparison
- exact-origin CORS
- Trusted Host enforcement
- strict HTTP(S)-only URL validation
- request, import, entry, tag, query, and data-file limits
- write, authentication, and external-search rate limits
- private runtime storage
- atomic locked persistence and import backups
- restrictive CSP and browser security headers
- structured logs without authorization values or query strings
- pinned runtime dependencies
- CI linting, typing, SAST, dependency audit, secret scan, tests, and CodeQL

## Known scope limits

The built-in limiter is process-local. Deploy a shared edge limiter when running more than one application process. The JSON store uses advisory filesystem locking; every writer must honor the same lock. For high write concurrency, multiple hosts, or untrusted multi-user access, migrate to a transactional database and centralized identity provider.
