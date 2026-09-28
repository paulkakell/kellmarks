# Install Kellmarks from GHCR

The prebuilt image `ghcr.io/paulkakell/kellmarks:02.02.01` runs the full dashboard,
authenticated Flask API and Gunicorn server. It supports Linux **AMD64 and ARM64**,
including Linux containers on Docker Desktop. No Git checkout, host Python,
Node.js or local image build is required. Bookmark data stays in a private named
volume; there is no separate database service.

## Requirements

Install a maintained [Docker Engine](https://docs.docker.com/engine/install/)
and [Compose plugin](https://docs.docker.com/compose/install/linux/) on Linux,
or [Docker Desktop](https://docs.docker.com/desktop/) on Windows/macOS. These
examples require Compose 2.20 or newer, including newer major versions. Verify
`docker version` and `docker compose version`. Use `docker compose`, not the
obsolete standalone `docker-compose` executable. On Linux, use `sudo docker`
consistently when required by your installation. Docker access grants extensive
host control; restrict it to trusted operators.

The host needs outbound HTTPS access to GHCR for image pulls. The optional Caddy
proxy also needs DNS and certificate-authority access. Use local storage for the
data volume. These instructions target a single instance, not a replicated cluster.

## 1. Download the installation files

Start in a new private directory. Linux/macOS:

```bash
mkdir kellmarks && cd kellmarks
curl --fail --location --remote-name https://github.com/paulkakell/kellmarks/releases/download/v02.02.01/docker-compose.yml
curl --fail --location --output .env.docker.example https://github.com/paulkakell/kellmarks/releases/download/v02.02.01/env.docker.example
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory kellmarks -ErrorAction Stop
Set-Location kellmarks
Invoke-WebRequest 'https://github.com/paulkakell/kellmarks/releases/download/v02.02.01/docker-compose.yml' -OutFile docker-compose.yml
Invoke-WebRequest 'https://github.com/paulkakell/kellmarks/releases/download/v02.02.01/env.docker.example' -OutFile .env.docker.example
```

The release also supplies `kellmarks-02.02.01-docker.tar.gz` containing both Compose
options for GHCR/HTTPS, the Caddyfile, environment example, installation guides
and `container.json`. It contains no credentials or bookmark data. `SHA256SUMS`
covers the downloadable assets; compare hashes of the files you downloaded
against this file. `container.json` records the source commit, image digest,
platforms and whether anonymous registry access was verified at publication.

The standalone environment asset is named `env.docker.example` to avoid GitHub's
renaming of leading-dot filenames. The commands above save it locally as
`.env.docker.example`, matching the source checkout and the tar bundle. When
checking `SHA256SUMS`, compare the local environment example against the
`env.docker.example` checksum entry. Do not rename your private `.env`.

Release 02.02.00 remains available for rollback. Its standalone environment
asset was renamed by GitHub to `default.env.docker.example`; the tar bundle
retains `.env.docker.example`. Prefer the corrected 02.02.01 installation files.

In a source checkout, these same files are already present. **Always use
`-f docker-compose.yml` for the prebuilt installation.** Docker prefers
`compose.yaml` when both filenames exist; Kellmarks keeps that file as the
separate source-build option. Do not merge the two base files. The downloaded
`docker-compose.yml` has no `build`, `extends`, or source-file dependency.

## 2. Pull the image and create a private token

Linux/macOS, first installation only:

```bash
(
  set -eu
  if [ -e .env ]; then
    echo '.env already exists; preserve the existing configuration.' >&2
    exit 1
  fi
  docker pull ghcr.io/paulkakell/kellmarks:02.02.01
  umask 077
  cp .env.docker.example .env
  docker run --rm --entrypoint python ghcr.io/paulkakell/kellmarks:02.02.01 \
    -c "import secrets; print('KELLMARKS_AUTH_TOKEN=' + secrets.token_urlsafe(32))" >> .env
)
```

Windows PowerShell:

```powershell
if (Test-Path .env) { throw '.env already exists; preserve the existing configuration.' }
docker pull ghcr.io/paulkakell/kellmarks:02.02.01
if ($LASTEXITCODE -ne 0) { throw 'Image pull failed; check registry access below.' }
Copy-Item .env.docker.example .env
$token = docker run --rm --entrypoint python ghcr.io/paulkakell/kellmarks:02.02.01 -c "import secrets; print(secrets.token_urlsafe(32))"
if ($LASTEXITCODE -ne 0) { throw 'Token generation failed.' }
Add-Content -Path .env -Value "KELLMARKS_AUTH_TOKEN=$token" -Encoding ascii
Remove-Variable token
```

Restrict `.env` NTFS permissions to the operator and administrators on Windows.
Never commit this file, put it in a public share, or paste its contents into an
issue. The image refuses startup without a sufficiently strong token even when
someone tries to disable authentication. Existing installations must keep their
current `.env` rather than regenerate it during every upgrade.

### Registry access and initial package visibility

GitHub initially creates GHCR packages as **private**, even for a public source
repository. The package owner must open the repository's **Packages > kellmarks >
Package settings > Change visibility** and choose **Public** to allow anonymous
installation. This setting is separate from repository visibility. Publishing
through Actions links the package to the repository using the OCI source label.
The release workflow reports whether anonymous manifest access succeeded; it
does not claim to change package visibility automatically.

For an intentionally private package, an authorized user can log in with a
GitHub personal access token **(classic)** with `read:packages`, supplied through
standard input. GitHub organization SSO authorization may also be required:

```bash
# Set GHCR_READ_TOKEN privately using your secret manager, not a literal in shell history.
printf '%s' "$GHCR_READ_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
unset GHCR_READ_TOKEN
docker pull ghcr.io/paulkakell/kellmarks:02.02.01
```

Use Docker's credential helper and `docker logout ghcr.io` when credentials are
no longer needed. The GitHub registry token is **not** the Kellmarks API token;
never put it in `KELLMARKS_AUTH_TOKEN`. Public packages require no registry login.
A `denied` error requires checking package access/visibility. A missing tag or
404 release asset can instead mean publication has not completed. Do not replace
a failed versioned pull with an unverified third-party image.

## 3. Start and verify

```bash
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.yml pull
docker compose -f docker-compose.yml up -d --wait
docker compose -f docker-compose.yml ps
docker compose -f docker-compose.yml exec -T kellmarks python /app/docker/healthcheck.py
```

Open `http://127.0.0.1:8787` on the Docker host and enter the token stored privately
in `.env`. The shell/assets are public; bookmark data and every API operation
require authentication. This is one shared library and token, not multi-user
accounts. The healthcheck authenticates without printing the token.

The default listener is deliberately loopback-only. For another computer, use
HTTPS below or an SSH tunnel, for example `ssh -N -L 8787:127.0.0.1:8787
USER@SERVER`. Never send the bearer token across an untrusted plaintext network.
A remote browser's `127.0.0.1` refers to that browser's computer, not your server.

The process runs as UID/GID 10001, with a read-only root filesystem, a private
`/tmp` tmpfs, dropped capabilities, bounded logs and a restart policy. Its
`/data/data.json` is on `kellmarks_data` by default. Keep the project name
`kellmarks` and the same volume when changing image versions or installation
methods. A different `-p` or `COMPOSE_PROJECT_NAME` selects a different library.

## HTTPS with Caddy

Download/extract the complete Docker release bundle, or download
`compose.https.yaml` and save the release's `Caddyfile` at `docker/Caddyfile` beside
the base Compose file. Set the existing domain line in `.env`:

```dotenv
KELLMARKS_DOMAIN=bookmarks.example.com
```

Use your own DNS hostname without scheme/path/port. Point its DNS records at the
server, open TCP 80/443, and ensure no other service owns these ports. Do not open
8787 publicly. Start with both files:

```bash
docker compose -f docker-compose.yml -f compose.https.yaml config --quiet
docker compose -f docker-compose.yml -f compose.https.yaml pull
docker compose -f docker-compose.yml -f compose.https.yaml up -d --wait
```

Browse to your HTTPS hostname, verify its certificate, then log in. Preserve the
Caddy certificate volume. Use **both `-f` arguments in every subsequent command**
for this deployment, including backups, restores and upgrades. Enable
`KELLMARKS_ENABLE_HSTS=1` only after confirming HTTPS works and its one-year,
include-subdomains policy is appropriate. See the [full proxy and TLS guide](INSTALLATION.md#https-full-server-with-caddy)
for DNS, certificate, existing-proxy and trusted-origin requirements; substitute
`docker-compose.yml` for its source-build base file. An actual public certificate
still depends on your domain and network, not just container health.

## Configuration and image selection

The environment mappings, limits, data permissions, authentication, logging and
external-request controls are identical to the [source deployment reference](INSTALLATION.md#configuration-and-storage).
Examples: change `KELLMARKS_HTTP_PORT=8788` for another loopback host port, set
`KELLMARKS_EXTERNAL_REQUESTS=0` to disable application-owned external requests,
or set `KELLMARKS_IMAGE` to a complete image reference:

```dotenv
# Explicit release version, recommended:
KELLMARKS_IMAGE=ghcr.io/paulkakell/kellmarks:02.02.01
```

For immutable deployment, use `ghcr.io/paulkakell/kellmarks@sha256:...` with the
**complete digest from that release's `container.json`**, not a literal ellipsis.
The `sha-<full-commit>` tag provides source traceability. `latest` is an optional
moving alias for the newest successful stable publication; it is not the default
and is unsuitable as a precise rollback reference. The workflow does not
republish an existing version tag from a different source commit.

The default `pull_policy: missing` permits restarts from a cached version. Run
`pull` explicitly for installation/upgrades. There is no automatic updater.
For source changes, use `compose.yaml` and its build procedure instead.

## Upgrade, rollback, token rotation and removal

Before an upgrade, export the library or take a stopped-volume backup using the
[backup/restore procedure](INSTALLATION.md#backup-restore-and-migration), replacing
every base command with `docker compose -f docker-compose.yml` and including the
HTTPS overlay when used. Preserve `.env`, the old release files, old image digest
and a tested backup. Do not change project names or volume names.

Download the new release's Compose/configuration files, review its migration
notes, and update the single `KELLMARKS_IMAGE` override in `.env` when one is set.
An existing override wins over the new Compose file's default. Then:

```bash
docker compose -f docker-compose.yml pull
docker compose -f docker-compose.yml up -d --no-build --wait
docker compose -f docker-compose.yml exec -T kellmarks python /app/docker/healthcheck.py
```

Confirm the dashboard version and your bookmarks. To roll back, restore the
previous deployment files and set `KELLMARKS_IMAGE` to the recorded prior digest,
then run `up -d --no-build --force-recreate --wait` with the same file arguments.
Release 02.02.01 retains schema 2, so no database migration or data rewrite is
needed. This is the first GHCR release: do not invent a `02.01.02` registry tag.
For a pre-GHCR rollback, use the retained local image or previous Python source.
Future schema changes require the corresponding release's rollback instructions.

To rotate authentication, replace the token once in `.env` and recreate the
container; `restart` alone does not apply environment changes. To stop without
deleting data, run `docker compose -f docker-compose.yml stop`. `down` also keeps
named volumes. **Never use `down -v` or prune volumes unless intentionally deleting
the library and any certificate data.**

For standalone Docker, substitute the GHCR reference for the local image in the
[standalone instructions](INSTALLATION.md#docker-without-compose); keep its
security options and named volume. Existing Python libraries must be exported
or migrated explicitly; image pulls never contain or migrate personal bookmarks.

## Troubleshooting

A build prompt or `kellmarks:local` pull indicates the wrong Compose file or an
old `.env` image override. Use `-f docker-compose.yml` explicitly and check the
override privately. A platform error means the host is not AMD64/ARM64 Linux,
Linux-container mode is disabled, or the requested tag has not finished publishing.

For token errors, unhealthy status, Host/origin rejection, storage permissions,
port conflicts, certificate errors and apparently reset libraries, use the
[operational troubleshooting table](INSTALLATION.md#troubleshooting-and-removal).
Use `config --quiet`; plain `config` and `docker inspect` may disclose credentials.
Container `unhealthy` does not itself trigger an automatic restart.

## Publishing and verification

The release workflow waits for the Python, browser, lint, security, dependency,
CodeQL and both Docker architecture checks on the exact main commit. It uses the
short-lived `GITHUB_TOKEN` with `packages: write`, not a stored registry password.
It builds a multi-platform image with provenance/SBOM attestations, then pulls and
exercises its exact registry digest on both architectures before promoting the
version tag. Re-runs reuse the matching digest and reject a mismatched revision.
The GitHub release includes install assets, checksums and `container.json`;
`latest` is promoted only after that release exists and main still matches.
No workflow runs privileged pull-request code through `pull_request_target`.

Reference: [GitHub Container registry authentication and visibility](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry),
[GitHub image publishing](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images),
and [Compose filename selection](https://docs.docker.com/compose/intro/compose-application-model/).
