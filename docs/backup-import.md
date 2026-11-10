# Backup import

Backup import is an **additional, untrusted data source**. Imported data is validated, sanitised (secrets
removed) and stored as a separate snapshot with source `backup`. It never overwrites data collected through the
API; differences are reported as conflicts (*only in backup*, *only in API*, *different values*).

Upload files under **Sync & Import → Backup import** (administrators only, default limit 20 MB,
`OMADA_DOCS_MAX_UPLOAD_MB`).

## Native Omada controller backups (`.cfg`) – not supported

Controller backups created via *Settings → Maintenance → Backup* are encrypted, proprietary binary files. Their
format is undocumented and they contain credentials. Omada Docs detects such files and rejects them with an
explanation instead of guessing their content. Use the Open API synchronisation, or one of the JSON formats
below.

## Supported formats (JSON)

### 1. `omada-docs-dataset` – dataset export of this application

Created with **Export → Dataset (JSON)** (`GET /api/dataset/export`). Useful for moving documentation
data between installations or archiving a state.

```json
{
  "format": "omada-docs-dataset",
  "format_version": 1,
  "app_version": "0.1.0",
  "exported_at": "2025-01-01T12:00:00+00:00",
  "entities": {
    "device":  [{"key": "40-ED-00-00-01-01", "site_id": "…", "name": "Core Switch", "…": "…"}],
    "network": [{"key": "…", "site_id": "…", "name": "Servers", "vlan_id": 20, "subnet": "192.168.20.0/24"}]
  }
}
```

### 2. `omada-docs-raw` / raw Open API responses

Raw responses of the Open API endpoints (the `result` part of each response; for paged endpoints the `data`
list), grouped per site. Useful when the controller cannot be reached from the NAS but responses can be
collected elsewhere, e.g. with `curl`. The `format` field is optional (without it the format is reported as
`api-responses`).

```json
{
  "format": "omada-docs-raw",
  "format_version": 1,
  "collected_at": "2025-01-01T12:00:00+00:00",
  "controller_info": {"controllerVer": "5.15.20.20", "omadacId": "…"},
  "sites": [
    {
      "site": {"siteId": "…", "name": "Home"},
      "devices": [ … ],
      "clients": [ … ],
      "lan_networks": [ … ],
      "lan_profiles": [ … ],
      "wlan_groups": [ … ],
      "gateway_acls": [ … ], "switch_acls": [ … ], "eap_acls": [ … ],
      "groups": [ … ],
      "port_forwardings": [ … ], "one_to_one_nat": [ … ],
      "static_routes": [ … ],
      "dhcp_reservations": [ … ],
      "internet": { … },
      "vpns": [ … ], "site_to_site_vpns": [ … ],
      "switch_ports": [ … ], "switch_poe": [ … ]
    }
  ]
}
```

All site sections are optional. The section names correspond to the endpoint names in
[omada-api.md](omada-api.md). Unknown sections are listed as *not interpreted*; sections with an invalid type
cause the import to fail with an explanation.

## Validation and safety

* Only JSON is parsed; nesting depth and item count are limited.
* Secrets (fields such as `psk`, `password`, `securityKey`, `*Pwd`, `token`, private keys) are removed
  recursively before anything is stored.
* The import result shows the detected format and version, controller version, object counts, unsupported
  areas, warnings/errors and the comparison with current API data.
* Every import is written to the audit log; the file's SHA-256 is stored, the file itself is not kept.
