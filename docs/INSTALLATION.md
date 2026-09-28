# Installing and operating Kellmarks

**Recommended: [install the prebuilt GHCR image with docker-compose.yml](GHCR_INSTALLATION.md).**
That option needs no Git checkout, host Python, or local image build. The guide
below retains the source-build installation and shared operational reference.

Choose **Docker Compose** for a complete, persistent server, **local Python** for
loopback-only personal use/development, or the **static demonstration** for a
browser-local preview. Docker includes the dashboard, Flask API, pinned Python
runtime dependencies and a production Gunicorn WSGI server. It is not a static
site container. No separate database, Node.js installation, or host Python is
required for Docker deployment.

## Contents

- [Requirements and obtaining the source](#requirements-and-obtaining-the-source)
- [Docker Compose: full server](#docker-compose-full-server)
- [HTTPS: full server with Caddy](#https-full-server-with-caddy)
- [Using an existing reverse proxy](#using-an-existing-reverse-proxy)
- [Docker without Compose](#docker-without-compose)
- [Configuration and storage](#configuration-and-storage)
- [Operations, upgrades and rollback](#operations-upgrades-and-rollback)
- [Backup, restore and migration](#backup-restore-and-migration)
- [Local Python installation](#local-python-installation)
- [Static demonstration](#static-demonstration)
- [Troubleshooting and removal](#troubleshooting-and-removal)

## Requirements and obtaining the source

For a Linux server, install a maintained Docker Engine and the current
`docker compose` plugin using Docker's official
[Engine installation guide](https://docs.docker.com/engine/install/) and
[Compose plugin guide](https://docs.docker.com/compose/install/linux/).
For macOS or Windows, install [Docker Desktop](https://docs.docker.com/desktop/)
and use Linux containers. The examples require Compose 2.20 or newer, including
newer major versions. Do not use the obsolete `docker-compose` command.

Install Git using your operating system's package manager, then run:

```bash
git clone https://github.com/paulkakell/kellmarks.git
cd kellmarks
docker version
docker compose version
```

Both Docker client and server must be available. Linux installations that require
administrator access should use `sudo docker` consistently. Membership in the
Docker group grants extensive host control; do not grant it to untrusted users.
The first build needs network access to the Python image registry and PyPI.
Use a local disk for the data volume, not an unverified NFS/SMB mount.

Docker and GHCR installation files ship with `v02.02.00` and newer releases.
Older release archives, including `v02.01.02`, predate the complete Docker option.
This page uses a **locally built image** via `compose.yaml`; the separate
[GHCR guide](GHCR_INSTALLATION.md) uses the pull-only `docker-compose.yml`.
When both files are present, always specify `-f docker-compose.yml` for GHCR.
Do not combine the two base files, since Compose merges build settings.

## Docker Compose: full server

Run commands from the repository root. The default listener is
`http://127.0.0.1:8787` on the Docker host. It is deliberately not exposed to your
LAN or the Internet. For another computer, use HTTPS as described below or an SSH
tunnel; do not publish the bearer-token API over untrusted plaintext HTTP.

### 1. Build and create private configuration

Linux/macOS shell:

```bash
(
  set -eu
  if [ -e .env ]; then
    echo '.env already exists; preserve the existing configuration.' >&2
    exit 1
  fi
  docker build --pull -t kellmarks:02.02.00 .
  umask 077
  cp .env.docker.example .env
  docker run --rm --entrypoint python kellmarks:02.02.00 \
    -c "import secrets; print('KELLMARKS_AUTH_TOKEN=' + secrets.token_urlsafe(32))" >> .env
)
```

Check whether `.env` already exists before following first-install commands. When
it does, retain the existing file and token, and proceed to validation instead of
appending another credential. `.env.docker.example` contains no working token;
Compose refuses to start without one. The generated token is stored in `.env`,
not baked into the image or placed in a command-line argument.

Windows PowerShell (new installation only):

```powershell
docker build --pull -t kellmarks:02.02.00 .
if ($LASTEXITCODE -ne 0) { throw 'Image build failed.' }
if (Test-Path .env) { throw '.env already exists; preserve the existing configuration.' }
Copy-Item .env.docker.example .env
$token = docker run --rm --entrypoint python kellmarks:02.02.00 -c "import secrets; print(secrets.token_urlsafe(32))"
if ($LASTEXITCODE -ne 0) { throw 'Token generation failed.' }
Add-Content -Path .env -Value "KELLMARKS_AUTH_TOKEN=$token" -Encoding ascii
Remove-Variable token
```

On Windows, restrict the `.env` file's NTFS permissions to the operator account
and administrators. Do not place it in a shared or publicly synchronized folder.

### 2. Start and verify

```bash
docker compose config --quiet
docker compose up -d --wait
docker compose ps
docker compose exec -T kellmarks python /app/docker/healthcheck.py
```

`config --quiet` validates without displaying the token. An unqualified
`docker compose config` or `docker inspect` can reveal environment credentials;
do not paste their output into issues. The health command returns exit code 0
on success and never prints the token. It authenticates against the live API
without making external requests; it is a liveness check, not a disk-integrity
check or a backup.

Open `http://127.0.0.1:8787` on the Docker host and enter the token when prompted.
Read `KELLMARKS_AUTH_TOKEN` privately from `.env`. The browser retains it only for
the current session. On first launch, the sample library seeds the private
persistent store. Add or import your bookmarks through the dashboard.

The UI shell and bundled assets are public; API data and all API operations,
including health, require authentication. There is one shared library and one
operator-managed token, not separate user accounts or per-user permissions.

### 3. Confirm persistence

Create a test bookmark, then run:

```bash
docker compose up -d --force-recreate --wait
```

Reload the dashboard: the bookmark must remain. The default Compose project name
is `kellmarks`; its named volume is `kellmarks_data`. Keep the same project name
and volume when upgrading. A different `-p`/`COMPOSE_PROJECT_NAME` creates a
separate library. Container recreation does not copy an existing host-Python
library automatically; see migration below.

## HTTPS: full server with Caddy

The included `compose.https.yaml` adds Caddy with automatic certificate management
and persistent certificate/configuration volumes. Complete Docker steps 1–2
first. Then set the existing `KELLMARKS_DOMAIN` line in `.env` to a domain you
control, for example:

```dotenv
KELLMARKS_DOMAIN=bookmarks.example.com
```

Use a hostname only: no scheme, path, wildcard, or port. Configure its public DNS
A record (and AAAA only when IPv6 routing works) to reach the server. Allow inbound
TCP **80 and 443** through your router and host/cloud firewall. Caddy must be able
to reach certificate authorities. Do not open 8787 publicly. Another process must
not already own ports 80/443.

```bash
docker compose -f compose.yaml -f compose.https.yaml config --quiet
docker compose -f compose.yaml -f compose.https.yaml up -d --wait
docker compose -f compose.yaml -f compose.https.yaml logs --tail=100 caddy
```

Open `https://bookmarks.example.com`, confirm a valid certificate, and log in with
the same token. The overlay sets the exact trusted hostname and HTTPS public
origin automatically; leave additional CORS origins empty for this deployment.
The proxy forwards the original Host and removes client-supplied forwarding
identity. API authorization remains enforced by Kellmarks.

**Use both `-f` arguments for every subsequent Compose command for this HTTPS
installation**, including rebuilds, backups, restores, stops, and removals. In the
remaining examples, replace `docker compose` with
`docker compose -f compose.yaml -f compose.https.yaml`.

After verifying HTTPS works consistently, set `KELLMARKS_ENABLE_HSTS=1` in `.env`
and run the same `up -d --wait` command. HSTS lasts one year and includes
subdomains; enable it only when that policy is appropriate for the hostname.
Do not test HSTS on an HTTP-only hostname.

Caddy's `caddy_data` volume contains certificate private keys; treat it as a
secret and preserve it across upgrades. The supplied configuration does not
enable access logging, which could expose bookmark search queries. See Caddy's
[automatic HTTPS requirements](https://caddyserver.com/docs/automatic-https).
A private hostname without public certificate validation needs an operator-managed
internal CA/certificate setup or an existing HTTPS proxy instead of this public
DNS example. Actual certificate issuance depends on your DNS and network; a
container health status alone does not verify public HTTPS.

## Using an existing reverse proxy

Use the base `compose.yaml` without the Caddy overlay when a host-level proxy
already terminates HTTPS. Set `.env`:

```dotenv
KELLMARKS_TRUSTED_HOSTS=bookmarks.example.com,localhost,127.0.0.1
KELLMARKS_PUBLIC_ORIGIN=https://bookmarks.example.com
KELLMARKS_ENABLE_HSTS=1
```

Configure the proxy to forward to `http://127.0.0.1:8787`, preserve the original
Host, forward Authorization, discard incoming Forwarded/X-Forwarded-* values
before setting its own, and never log credentials or URL query strings. Serve
Kellmarks at the hostname root, not under a URL path prefix. Apply changes with
`docker compose up -d --wait`. Do not use Flask's development server for this
production deployment.

For a proxy in another container, its own `127.0.0.1` is not the Docker host.
Attach it to the same private Docker network and use `kellmarks:8787`, as the
included Caddy overlay does. Do not solve connectivity by exposing an
unauthenticated service or using wildcard trusted hosts/CORS.

For temporary remote administration without a domain, keep the default base
configuration and create an SSH tunnel from your workstation:

```bash
ssh -N -L 8787:127.0.0.1:8787 your-user@your-server
```

Then browse to `http://127.0.0.1:8787` locally. The remote hop is encrypted by SSH.

## Docker without Compose

Build the image and generate the private `.env` as above. This equivalent Linux
shell example uses a **different volume** from the default Compose installation:

```bash
docker volume create kellmarks_standalone_data
docker run -d --name kellmarks --restart unless-stopped --init \
  --env-file .env \
  -e KELLMARKS_DATA_FILE=/data/data.json \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m,mode=1777 \
  --cap-drop ALL --security-opt no-new-privileges:true --pids-limit 128 \
  --stop-timeout 40 --log-opt max-size=10m --log-opt max-file=3 \
  -p 127.0.0.1:8787:8787 \
  -v kellmarks_standalone_data:/data \
  kellmarks:02.02.00
docker exec kellmarks python /app/docker/healthcheck.py
```

Do not run this beside Compose on the same host port. Docker `--env-file` does not
perform Compose interpolation; retain plain `KEY=value` lines without shell
expansions or quotes. `KELLMARKS_HTTP_PORT` only controls Compose; change `-p`
manually for standalone Docker. To upgrade standalone Docker, back up the named
volume, build a new image, stop/remove only the container, and recreate it with
the same volume and settings. `docker rm` does not delete that named volume.

## Configuration and storage

`.env` is read by Compose for the explicitly mapped settings. The Python app
does not automatically load `.env`. Docker always requires a token of at least 32
printable ASCII characters with no whitespace, even when `REQUIRE_AUTH=0` is
supplied. Keep the token private: Docker/host administrators can inspect
container environment variables. Do not commit `.env` or send it in support logs.
The build context is deny-by-default and does not include local data or secrets.

| Docker setting | Default / behavior |
| --- | --- |
| `KELLMARKS_AUTH_TOKEN` | Required; securely generated at installation. |
| `KELLMARKS_HTTP_PORT` | Host loopback port `8787`; container port stays `8787`. |
| `KELLMARKS_IMAGE` | Local image tag `kellmarks:02.02.00`; may be overridden for controlled builds/rollback. |
| `KELLMARKS_DOMAIN` | Required only for the HTTPS overlay. |
| `KELLMARKS_TRUSTED_HOSTS` | Exact hostnames without ports; the HTTPS overlay supplies its own value. |
| `KELLMARKS_PUBLIC_ORIGIN` | Exact external origin; automatically HTTPS in the overlay. |
| `KELLMARKS_ALLOWED_ORIGINS` | Empty; extra exact origins only when separately required. |
| `KELLMARKS_ENABLE_HSTS` | `0`; enable after verifying HTTPS. |
| `KELLMARKS_EXTERNAL_REQUESTS` | `1`; set `0` to disable app-owned external lookups/remote icons. |
| `KELLMARKS_LOG_LEVEL` | `INFO` for the application's structured logs. |
| Data location | Fixed at `/data/data.json` by Compose, on the named volume. |

All request/data/import/rate-limit environment settings are mapped in
`compose.yaml`; their defaults and allowed ranges are in the
[server configuration reference](server/README.md#configuration).
`KELLMARKS_BIND_HOST` and `KELLMARKS_PORT` configure only the development server,
not Gunicorn. The container runs one Gunicorn worker with four threads: rate
limits and release caches are process-local. Do not scale to multiple workers,
replicas, or hosts without redesigning these controls and validating storage
locking. Clients behind a reverse proxy share its source-address rate limits.

The application runs as UID/GID **10001:10001**. Its code is read-only under
Compose; `/tmp` is temporary and `/data` is persistent. Prefer the named volume,
whose ownership is initialized from the image. For a Linux bind mount, create a
private directory owned by 10001:10001 and replace `data:/data` with its absolute
path. Example preparation: `sudo install -d -m 0700 -o 10001 -g 10001
/srv/kellmarks/data`. Rootless Docker uses mapped host UIDs; check those mappings
before preparing bind mounts. SELinux hosts may also require an appropriate
container label. Never use `chmod 777` or run the application as root to avoid a
permissions error.

Mount the **whole data directory**, not just `data.json`: atomic writes, locks,
`.bak` files and migration backups must live beside it. Never store this directory
under public web assets. Full-volume backups and exports contain private URLs.
Browser-local theme settings, remote-icon consent and session credentials are not
server-volume data and are not included in server backups.

## Operations, upgrades and rollback

```bash
docker compose ps
docker compose logs --tail=100 kellmarks
docker compose stop                 # Stop; retain containers and volumes.
docker compose up -d --wait         # Start or apply configuration changes.
```

`restart: unless-stopped` restarts the service after a process crash or daemon
restart, unless it was deliberately stopped. An `unhealthy` status alone does
not cause Docker to restart a still-running process; inspect the logs and fix the
underlying issue. Enable/start the Docker service at boot on your Linux host.
Docker Desktop must be running on a desktop host.

### Upgrade

First take a backup as below. Retain the old source revision and image:

```bash
git rev-parse HEAD
docker image tag kellmarks:02.02.00 kellmarks:rollback
git pull --ff-only
docker compose build --pull
docker compose up -d --wait
docker compose exec -T kellmarks python /app/docker/healthcheck.py
```

For HTTPS, use both Compose files and also run `docker compose ... pull caddy`
before `up`. After an upgrade, verify your bookmarks and the dashboard version.
Python packages are pinned; base-image tags receive upstream patches, so rebuild
with `--pull` regularly rather than only restarting an old image. This setup does
not silently auto-update application images. For strict reproducibility, retain
the built image ID/digest and source revision; a moving base-image tag alone is
not an immutable build.

To roll back, retain the current data backup, restore the matching old source
revision (so Compose/config files match), and tag the saved image back:

```bash
docker image tag kellmarks:rollback kellmarks:02.02.00
docker compose up -d --no-build --force-recreate --wait
```

This Docker addition does not change data schema 2. For future schema changes,
follow that release's migration notes and restore a compatible backup before a
downgrade; do not assume all future releases can read newer data.

To rotate the token, securely generate a replacement, replace the single
`KELLMARKS_AUTH_TOKEN` line in `.env`, and run `up -d --force-recreate --wait`.
A simple `docker compose restart` does **not** apply changed environment values.
Existing browser sessions must reauthenticate with the new token.

## Backup, restore and migration

The dashboard's JSON Export is convenient for a portable library copy. A full
server backup also preserves import/migration backups. Stop writers for a
consistent full-volume archive. The following commands are for Linux/macOS;
run them through a suitable shell on the Docker host. Windows PowerShell versions
with text-based native redirection must not be used for binary archive streams.

### Full-volume backup

```bash
mkdir -p backups
chmod 700 backups
docker compose stop kellmarks
# Select a new filename each time; protect the archive from other users.
(umask 077; docker compose run --rm --no-deps -T --entrypoint tar \
  kellmarks -C /data -czf - . > "backups/kellmarks-$(date +%Y%m%d-%H%M%S).tar.gz")
# Check the command succeeded and verify the archive before relying on it.
docker compose up -d --wait
```

Run `tar -tzf backups/YOUR-BACKUP.tar.gz` and confirm it includes `./data.json`.
Copy verified backups off-host and encrypt them. Keep a separate protected copy
of `.env`; do not include it in a publicly shared archive. Test restoration into a
separate instance periodically. For HTTPS, also preserve the `caddy_data` volume
(certificate/account keys) with your host's stopped-volume backup process.

### Restore

This replaces library files. Preserve the current volume first and use only your
own trusted backup archive, not an arbitrary downloaded tar file. The restored
files must be writable by UID 10001.

```bash
docker compose stop kellmarks
tar -tzf backups/YOUR-BACKUP.tar.gz
docker compose run --rm --no-deps -T --entrypoint tar \
  kellmarks -C /data -xzf - < backups/YOUR-BACKUP.tar.gz
docker compose up -d --wait
docker compose exec -T kellmarks python /app/docker/healthcheck.py
```

Confirm the expected entries through the dashboard. Restoring into a fresh volume
requires building the image and configuring `.env` first, but do not start the
application until the restore is complete. If startup rejects the data, preserve
it, check schema/size/permissions and use a matching application version. Never
delete the data file merely to make the health check pass.

### Migrate an existing Python/server installation

The easiest path is to export JSON from the old server and import it into Docker.
The reviewed import dialog defaults to merge; choose replacement explicitly only
when the destination sample/previous library should be replaced. Review duplicates
and keep the original export until verification is complete.

For a byte-preserving schema-2 migration, stop the old server, create a tar archive
of the contents of its private `docs/server/instance/` directory (or the directory
containing its configured data file), and restore it using the procedure above.
When the old filename is not `data.json`, make a staging copy named `data.json`
and include its associated backups before archiving. Restore as UID 10001 and
keep the original installation untouched until you verify the new library.

For 01.xx.xx data, follow the
[02.00.00 migration procedure](releases/02.00.00.md) in a local Python installation
first, then export or transfer the validated schema-2 library. Legacy runtime
`docs/assets/data.json` is deliberately excluded from Docker builds and is never
copied into a published image. Do not rebuild an image containing your bookmarks.

## Local Python installation

This alternative needs Python **3.10 or newer** and Git. Node.js is needed only
for development checks, not normal runtime. Clone the repository as above.

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r docs/server/requirements.txt
python docs/server/app.py
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r docs/server/requirements.txt
.\.venv\Scripts\python.exe docs/server/app.py
```

Open `http://127.0.0.1:8787`. Data is stored under `docs/server/instance/` unless
`KELLMARKS_DATA_FILE` is set to a private file path. Back up this directory before
upgrades. On Debian/Ubuntu, a missing `venv` module can be installed with the
appropriate `python3-venv` package for your Python installation.

For protected local mode on Linux/macOS, set before starting:

```bash
export KELLMARKS_AUTH_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export KELLMARKS_REQUIRE_AUTH=1
python docs/server/app.py
```

PowerShell equivalents are `$env:KELLMARKS_AUTH_TOKEN = (&
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))")`
and `$env:KELLMARKS_REQUIRE_AUTH = '1'`. Save the token privately to retain it
across shell sessions. `.env.example` documents environment names but is not
automatically loaded. Do not export empty data/legacy file path values.

The built-in Flask server is for local use/development only and intentionally
refuses non-loopback binds. Use the Docker production deployment for a full
server. Existing local API behavior is unchanged by the Docker option.

## Static demonstration

To preview without Flask or shared server persistence:

```bash
python3 -m http.server 8080 --bind 127.0.0.1 --directory docs
```

Open `http://127.0.0.1:8080`. Only sample data and browser-local fallback storage
are used; this is not the Docker/server installation, has no authenticated shared
API, and does not provide the server's reviewed imports. Do not publish a `docs`
directory containing private files or an old `assets/data.json`.

## Troubleshooting and removal

| Symptom | Check / corrective action |
| --- | --- |
| Cannot connect to Docker daemon | Start Docker Engine/Desktop; verify CLI permissions and Linux-container mode. |
| Compose says token is required | Use `.env.docker.example`, generate a token, and run from the repository root. Shell environment values override `.env`; remove unintended overrides. |
| Container exits with token error | Token must be at least 32 printable ASCII characters without whitespace; no example credential is supplied. |
| `401` from `/api/health` | Expected without a token. Use the packaged healthcheck or authenticated API request. |
| `400` / invalid Host | Add the exact hostname to trusted hosts, without scheme or port; do not use `*`. |
| `403` on browser API writes | Check exact public HTTPS origin, scheme and port, and that the proxy preserves Host. Do not broadly enable CORS. |
| Permission denied / read-only store | Mount all of `/data` and check UID/GID 10001, rootless mappings, SELinux labels and disk space. |
| Port already allocated | Stop the conflicting service or change `KELLMARKS_HTTP_PORT` for loopback access. For Caddy, ports 80/443 must be free. |
| Caddy certificate error | Verify public DNS, inbound 80/443, outbound certificate-authority access, and Caddy logs. Do not repeatedly recreate its certificate volume. |
| Data appears reset | Check Compose project name and volume; do not delete the old volume. Docker does not automatically mount an existing Python library. |
| New `.env` setting has no effect | Recreate with `up -d`; `restart` alone does not reload environment configuration. |
| External search/icons/version unavailable | Check `KELLMARKS_EXTERNAL_REQUESTS`, session icon consent and outbound network policy. |
| `429` after repeated actions | Respect rate limits; clients behind one proxy share its address. Avoid adding workers to bypass limits. |
| Container is `unhealthy` | Inspect logs and run the packaged check. Authentication, Host or store-startup errors can prevent readiness. |

`docker compose down` removes containers and the project network but retains named
volumes. **Do not use `docker compose down --volumes` / `down -v` unless you intend
to permanently delete the library and, in HTTPS mode, certificate volumes.**
Back up and verify restoration first. Uninstalling Docker or pruning volumes may
also destroy data. Keep backups separately from Docker's own storage.

For developers, `python scripts/docker_smoke.py` expects an image built with
`docker build -t kellmarks:ci .`. It uses a randomized Compose project and only
removes its own disposable volumes. CI builds the actual image and checks
unauthenticated denial, real API/asset serving, non-root/read-only settings,
health, persistence after recreation, backup and restore. It validates the Caddy
configuration without requesting a public certificate.
