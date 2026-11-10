# Architecture

Omada Docs is a single self-hosted container. It collects configuration data **read-only** from a TP-Link
Omada controller through the official Open API, stores it in SQLite, enriches it with manual documentation
and turns it into browsable, searchable and exportable network documentation.

```
┌──────────────────────── Docker container ─────────────────────────┐
│                                                                    │
│  React SPA (static files)  ──HTTP/JSON──►  FastAPI (uvicorn)       │
│                                              │                     │
│              ┌───────────────────────────────┼──────────────────┐  │
│              │ api/routes   auth · data · manual · changes ·    │  │
│              │              admin (settings, sync, backup, audit)│ │
│              ├──────────────────────────────────────────────────┤  │
│              │ services     sync · acl_analysis · topology ·     │  │
│              │              search · quality · related · manual ·│  │
│              │              changes · backup_import · app_backup │  │
│              │              · export (HTML/PDF/DOCX/CSV) ·       │  │
│              │              scheduler (APScheduler)              │  │
│              ├──────────────────────────────────────────────────┤  │
│              │ omada        client (GET only) · collector ·      │  │
│              │              endpoints · parsers · mock (demo)    │  │
│              ├──────────────────────────────────────────────────┤  │
│              │ db/models    SQLAlchemy 2 + Alembic migrations    │  │
│              └──────────────────────────────────────────────────┘  │
│                                   │                                │
│        /data: omada_docs.db · attachments/ · logs/ · secret.key    │
└───────────────────────────────────┼────────────────────────────────┘
                                    │ HTTPS, read-only (GET + token request)
                                    ▼
                        Omada Software/Hardware Controller
```

## Repository layout

| Path | Content |
|------|---------|
| `backend/app/core` | Settings (`OMADA_DOCS_*` environment variables), logging with secret redaction, encryption, password hashing |
| `backend/app/db`, `backend/alembic` | Engine/session handling, declarative base, migrations (run automatically on start) |
| `backend/app/models` | Technical tables (one per object type), manual documentation, users/sessions, sync history, snapshots, change log, audit log, search index |
| `backend/app/omada` | Open API client, endpoint catalogue, collector, normalising parsers, native `.cfg` backup decryption and mapping, simulated controller for demo mode and tests |
| `backend/app/services` | Domain logic (see below) |
| `backend/app/api` | REST API (`/api/...`), authentication and CSRF dependencies |
| `backend/app/templates` | Jinja2 template for the HTML/PDF report |
| `backend/tests` | pytest suite |
| `frontend/` | React + TypeScript + Vite + Tailwind single page application, React Flow diagrams |
| `docker/`, `Dockerfile`, `docker-compose.yml` | Container build and deployment |

## Data model

* **Technical data** (`omada_*` tables) – one table per object type (`controller`, `site`, `device`, `network`,
  `wan`, `wlan`, `switch_port`, `client`, `acl_rule`, `nat_rule`, `route`, `vpn`, `ip_group`, `port_profile`).
  Each row stores the normalised object as JSON plus metadata: `site_id`, `object_key` (stable key such as the
  MAC address or controller id), `controller_id`, `source` (`api`/`backup`/`demo`), `collected_at`, `updated_at`
  (last real change) and `validation_status` (`valid`/`stale`). A synchronisation replaces these tables.
* **Manual documentation** (`manual_*` tables) – descriptions (display name, description, location, responsible,
  notes, tags) keyed by `(object_type, object_key)`, free documents (Markdown), attachments and manual
  relationships. These tables are never touched by a synchronisation, so manual content survives every
  re-sync. Descriptions of objects that disappear from the controller are kept.
* **History** – `sync_history`, `config_snapshots` (complete normalised dataset, stored whenever the
  configuration checksum changed and for every backup import; retention configurable), `change_log` (field-level changes from syncs and manual edits) and
  `audit_log` (logins, settings, edits, exports, backups).
* **Search** – `search_entries` is rebuilt after every sync and manual edit; IP searches are additionally
  matched against network subnets.

## Synchronisation

1. `OmadaClient` requests a client-credentials token and then only issues `GET` requests
   (rate limited, retries with backoff, automatic token refresh, paging).
2. `Collector` calls every endpoint of the catalogue per site. Each endpoint result (`ok`, `error`,
   `unsupported`, `skipped`) is recorded; a failing endpoint never aborts the whole run.
3. `parsers.normalize` converts raw responses into stable entities and removes secrets (PSKs, passwords,
   keys, tokens) recursively before anything is stored.
4. For endpoints that failed, the previous data of that object type/site is carried forward and marked
   `stale` instead of being reported as deleted. The run is then marked `partial`.
5. The new dataset is compared with the previous one (`changes.diff_datasets`, volatile runtime fields such as
   uptime or link status are ignored, clients are not tracked), changes are written to `change_log`, a snapshot
   is stored and the search index is rebuilt.

Syncs run manually, on a schedule (APScheduler, interval from the settings page) or once at start in demo
mode. Only one sync runs at a time.

## Analysis services

* `acl_analysis` – evaluates gateway/switch/EAP ACLs in order, resolves networks, IP groups and IPs, handles
  negation, disabled rules and protocols/ports, detects shadowed and redundant rules, produces explanations in
  plain language with a confidence level and computes a network-to-network communication matrix
  (`allowed` / `blocked` / `restricted` / `unknown`, default policy: LAN-to-LAN allowed).
* `topology` – builds the device graph from uplink information reported by the controller (gateway → switch
  → AP, switch ports, optional clients). Missing information is never guessed.
* `quality` – data quality checks (unassigned devices/clients, unknown port connections, VLANs without
  description, unreliable ACL rules, devices without location, unresolved references, conflicts between API
  and backup data, stale data, unsupported endpoints).
* `related` – cross-references for detail pages (network ↔ ports, ACLs, NAT, clients, …).
* `export` – builds a document model once and renders it as HTML, PDF (WeasyPrint), DOCX (python-docx) or CSV.
  Diagrams are generated as SVG server-side.

## Security

* The controller is never modified: the client has no method for write requests except the token request.
* Controller credentials are encrypted at rest (Fernet; key from `OMADA_DOCS_SECRET_KEY` or generated
  `/data/secret.key`) and never returned by the API.
* Users with roles `admin` (full access) and `viewer` (read-only). Passwords are hashed with scrypt. Sessions
  are random tokens stored hashed; cookies are `HttpOnly` and `SameSite=Strict`.
* CSRF protection with a double-submit token header plus Origin/`Sec-Fetch-Site` checks for unsafe requests.
* Access restricted to configurable networks (`OMADA_DOCS_ALLOWED_NETWORKS`), login rate limiting, strict
  Content Security Policy and security headers.
* Manual text is checked for credentials (e.g. `password: …`), Markdown is sanitised (bleach on export,
  DOMPurify in the UI), uploads are restricted by type and size, and CSV exports neutralise formulas.
* Logs and error messages pass through a redaction filter.
