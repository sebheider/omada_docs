# Omada Docs

Self-hosted, **read-only** documentation platform for TP-Link Omada networks. Omada Docs collects the
configuration of an Omada controller through the official Open API, stores it in a local SQLite database and
turns it into up-to-date, searchable network documentation – including topology diagrams, an explained ACL /
firewall communication matrix, change history and PDF/Word/HTML/CSV exports. Technical data can be enriched
with manual descriptions, documents and attachments that survive every synchronisation.

Designed to run as a single Docker container on a Synology NAS (or any Docker host).

> The controller is never modified: Omada Docs only sends `GET` requests (plus the token request) and
> never stores WLAN passwords, VPN keys or other secrets.

## Features

* **Synchronisation** – manual or scheduled, per-endpoint status, partial failures keep previous data,
  sync history, demo mode with realistic example data.
* **Inventory** – controller, sites, gateways, switches, access points, switch ports (VLANs, PoE, profiles,
  connected devices), networks/VLANs, DHCP, WAN, WLANs/SSIDs, clients, NAT/port forwarding, routes, VPN,
  IP groups, with sortable/filterable tables and detail pages with cross-references.
* **ACL / firewall analysis** – rules in evaluation order, plain-language explanation, confidence level,
  shadowed/redundant rule detection and a network-to-network communication matrix and graph.
* **Topology** – interactive, zoomable network diagram (gateway → switches → APs → optionally clients).
* **Manual documentation** – descriptions, location, responsible person, tags, notes, Markdown documents,
  attachments and manual relationships; credentials in free text are rejected.
* **Search** – global search over all objects and manual documentation, IP addresses are matched to their
  networks.
* **Change tracking** – field-level change log per sync and for manual edits, snapshot comparison.
* **Export** – complete documentation as PDF, DOCX, HTML or CSV with selectable chapters, optional
  anonymisation; dataset export (JSON).
* **Backup import** – native Omada controller backups (`.cfg`, decrypted in memory) and JSON dataset/raw API
  dumps as an additional, untrusted source with conflict report – see
  [docs/backup-import.md](docs/backup-import.md).
* **Security** – local users with *admin* and *viewer* roles, encrypted credentials, CSRF protection,
  network allow-list, login rate limiting, audit log, application backup/restore.

## Quick start (demo)

```bash
docker compose build
OMADA_DOCS_DEMO_MODE=true docker compose up -d
```

Open <http://localhost:8080>, create the first administrator and explore the generated example network.
Demo mode never contacts a controller.

## Installation on a Synology NAS

Requirements: DSM 7.2+ with **Container Manager**, an x86-64 or ARM64 model, and an Omada controller
version 5.12 or newer reachable from the NAS.

1. **Prepare folders** – in File Station create `docker/omada-docs` and `docker/omada-docs/data`.
2. **Copy the project** – copy this repository (at least `Dockerfile`, `docker-compose.yml`, `docker/`,
   `backend/`, `frontend/`) into `docker/omada-docs`.
3. **Configure** – copy `.env.example` to `.env` and adjust it. Set `PUID`/`PGID` to the owner of the data
   folder (via SSH: `id <your-user>`, typically `1026` / `100`).
4. **Create the project** – Container Manager → *Project* → *Create*, path `docker/omada-docs`, source
   *Use existing docker-compose.yml*. Container Manager builds the image and starts the container
   (or via SSH: `cd /volume1/docker/omada-docs && sudo docker compose up -d --build`).
5. **First start** – open `http://<nas-ip>:8080`, create the administrator account (or set
   `OMADA_DOCS_ADMIN_USERNAME`/`OMADA_DOCS_ADMIN_PASSWORD` in `.env`).
6. **Connect the controller** – create an Open API client with a read-only role on the controller
   (see [docs/omada-api.md](docs/omada-api.md)), then enter host, port, client id and secret under
   **Settings**, test the connection and start the first synchronisation. Choose an automatic sync interval
   if desired.

### Update

```bash
cd /volume1/docker/omada-docs
# replace the project files with the new version, then:
sudo docker compose up -d --build
```

Database migrations run automatically on start. Create an application backup before updating.

### Backup

All state is stored in the data folder (`omada_docs.db`, `attachments/`, `secret.key`, `logs/`).

* Include the data folder in **Hyper Backup**, or
* download an application backup (database + attachments) under **Settings → Backup** and restore it there.

Keep `secret.key` (or `OMADA_DOCS_SECRET_KEY`): without it, the stored controller secret cannot be decrypted
and must be re-entered. Application backups do not contain the key.

### Reverse proxy / HTTPS

The container serves plain HTTP on port 8080. For HTTPS use the DSM reverse proxy
(*Control Panel → Login Portal → Advanced → Reverse Proxy*) or any other proxy:

* Set `OMADA_DOCS_TRUSTED_PROXIES` to the proxy address(es) so that client IPs and the original host are
  taken from `X-Forwarded-*` headers. Forward the `Host` header unchanged (or send `X-Forwarded-Host`).
* Set `OMADA_DOCS_COOKIE_SECURE=true` when the UI is only used via HTTPS.
* For a sub path (e.g. `https://nas.lan/omada-docs`) set `OMADA_DOCS_BASE_PATH=/omada-docs` and let the proxy
  forward the full path.
* Optional single sign-on: an authenticating proxy can pass the user name in a header configured with
  `OMADA_DOCS_PROXY_AUTH_HEADER` (only accepted from trusted proxies).

## Configuration

Application settings are environment variables with the prefix `OMADA_DOCS_` (see
[.env.example](.env.example)). The controller connection and sync schedule are configured in the web UI and
stored in the database (secret encrypted).

| Variable | Default | Description |
|----------|---------|-------------|
| `OMADA_DOCS_DATA_DIR` | `/data` | Data directory (database, attachments, logs, key) |
| `OMADA_DOCS_DEMO_MODE` | `false` | Use the built-in simulated controller |
| `OMADA_DOCS_ALLOWED_NETWORKS` | loopback + private ranges | Networks allowed to access the UI |
| `OMADA_DOCS_TRUSTED_PROXIES` | – | Proxies whose `X-Forwarded-*` headers are trusted |
| `OMADA_DOCS_BASE_PATH` | – | URL sub path behind a reverse proxy |
| `OMADA_DOCS_COOKIE_SECURE` | `false` | Mark cookies as HTTPS-only |
| `OMADA_DOCS_SESSION_HOURS` | `12` | Session lifetime |
| `OMADA_DOCS_ADMIN_USERNAME` / `_PASSWORD` | – | Create an administrator on start |
| `OMADA_DOCS_PROXY_AUTH_HEADER` / `_DEFAULT_ROLE` | – / `viewer` | Header-based SSO from trusted proxies |
| `OMADA_DOCS_MAX_UPLOAD_MB` | `20` | Upload limit for attachments and imports |
| `OMADA_DOCS_SECRET_KEY` | generated | Key for encryption at rest (otherwise `/data/secret.key`) |
| `OMADA_DOCS_DATABASE_URL` | SQLite in data dir | SQLAlchemy URL (SQLite is the supported default) |
| `OMADA_DOCS_LOG_LEVEL` | `INFO` | Log level |
| `PUID` / `PGID` | `1000` | Owner of the data directory; the app runs as this user |

## Development

Backend (Python 3.12):

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
OMADA_DOCS_DATA_DIR=./data OMADA_DOCS_DEMO_MODE=true uvicorn app.main:app --reload --port 8000
pytest -q          # tests
ruff check app tests
```

Frontend (Node 20+):

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to http://localhost:8000
npm run build      # production build in frontend/dist
```

To serve the built frontend from the backend, copy `frontend/dist` to `backend/static` (done automatically in
the Docker image).

## Documentation

* [docs/requirements.md](docs/requirements.md) – requirements specification
* [docs/architecture.md](docs/architecture.md) – architecture, data model, security
* [docs/omada-api.md](docs/omada-api.md) – Open API setup, endpoints used, limitations
* [docs/backup-import.md](docs/backup-import.md) – supported import formats

## License

No license has been chosen yet; all rights reserved by the repository owner.

Third-party code is listed with its license in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
