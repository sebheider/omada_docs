# Backup import

Backup import is an **additional, untrusted data source**. Imported data is validated, sanitised (secrets
removed) and stored as a separate snapshot with source `backup`. It never overwrites data collected through the
API; differences are reported as conflicts (*only in backup*, *only in API*, *different values*).

Upload files under **Sync & Import → Backup import** (administrators only, default limit 20 MB,
`OMADA_DOCS_MAX_UPLOAD_MB`).

## Native Omada controller backups (`.cfg`)

Controller backups created via *Settings → Maintenance → Backup* (`.cfg`) can be imported directly. The
decryption is ported from [Omada_Backup_Decryptor](https://github.com/jgrimard/Omada_Backup_Decryptor)
by jgrimard (MIT License, see [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)):

```
.cfg = RC4( GZIP( JSON ) )
```

The RC4 key is static and embedded in the controller software (a 256-byte array whose first 8-byte block is
TEA-decrypted), so no password is needed. The decryptor was verified by its author against controller
versions 5.15, 6.1 and 6.2. Detection works by file extension or by content (the first bytes decrypt to a
gzip header).

Processing (`backend/app/omada/cfg_crypto.py`, `backend/app/omada/native_backup.py`):

1. The file is decrypted **in memory**; decompression is capped at 128 MB (protection against
   decompression bombs). Neither the `.cfg` file nor the decrypted JSON is ever written to disk or stored.
2. The decrypted "SDN backup" document (`mainInfo`, `systemSetting`, `sites`, `deviceBriefInfo`, …) is
   validated (nesting depth, element count, string length).
3. Secrets are removed by field name, individually encrypted `v2#…` values are discarded (they are not
   decrypted), and every secret value found in the backup is redacted from the result should it appear
   under an unexpected field name.
4. Sites and the lists stored below them are mapped **best effort** to the regular data model: the internal
   format is undocumented and changes between controller versions, so lists are classified by their section
   name (e.g. `lanNetworks`, `wlans`/`ssids`, `devices`/`deviceBriefInfo`, `portForwardings`, `gatewayAcls`,
   `staticRoutes`, `vpns`, `ipGroups`, `lanProfiles`) and objects are read with the Open API field names.
   Objects without the minimum fields for their type are skipped and counted in a warning; all other
   sections are listed as *not interpreted*.
5. Controller version, backup version and backup time are read from `mainInfo` where present.

A backup that was already decrypted with the original tool (JSON containing `mainInfo` / `systemSetting`) is
accepted as well and reported as `omada-native-backup-json`.

Omada Docs only **reads** backups. It never creates or re-encrypts `.cfg` files, because the application is
strictly read-only towards the controller.

> Native backups contain plaintext credentials (Wi-Fi keys, device and RADIUS passwords). Treat the files
> accordingly; Omada Docs discards these values during import.

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

* Only JSON and native `.cfg` backups are parsed; decompressed size, nesting depth, item count and string
  length are limited.
* Secrets (fields such as `psk`, `password`, `securityKey`, `*Pwd`, `token`, private keys) are removed
  recursively before anything is stored.
* The import result shows the detected format and version, controller version, object counts, unsupported
  areas, warnings/errors and the comparison with current API data.
* Every import is written to the audit log; the file's SHA-256 is stored, the file itself is not kept.
