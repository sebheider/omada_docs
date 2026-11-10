# Omada Open API usage

Omada Docs uses the official **Omada Open API** (northbound API) of the Omada Software Controller,
Hardware Controller (OC200/OC300/OC400) or Omada Cloud-Based Controller. It works with controller
versions **5.12 and newer**; some switch port details require **6.0 or newer** (older versions fall back to
the switch detail endpoint).

## Create API credentials on the controller

1. Open the controller as an administrator: **Global View → Settings → Platform Integration → Open API**.
2. **Add New App**, mode **Client** (client credentials).
3. Assign a role with **read-only (viewer) permissions** for the sites to be documented.
4. Copy the **Client ID** and **Client Secret** and enter them in Omada Docs under
   **Settings → Controller** together with the controller host/IP and port (default: 443 for hardware
   controllers, 8043 for the software controller). The Omada ID (`omadacId`) is detected automatically.

Self-signed certificates are common on controllers; disable *Verify TLS certificate* only if the
controller uses one and the network path is trusted.

## Read-only guarantee

| Request | Purpose |
|---------|---------|
| `GET /api/info` | Controller id (`omadacId`), version (no authentication) |
| `POST /openapi/authorize/token?grant_type=client_credentials` | Obtain an access token (the only non-GET request) |
| `GET /openapi/v1/{omadacId}/…` | All data endpoints below |

`backend/app/omada/client.py` has no method for `POST`/`PUT`/`PATCH`/`DELETE` data requests. The test
suite asserts that collecting data only issues `GET` requests.

## Endpoints

| Name | Path (below `/openapi/v1/{omadacId}`) | Data |
|------|---------------------------------------|------|
| controller_status | `/system/setting/controller-status` | Controller model, version, uptime |
| sites | `/sites` | Sites |
| devices | `/sites/{siteId}/devices` | Gateways, switches, access points, uplinks |
| clients | `/sites/{siteId}/clients` | Online clients (IP, MAC, VLAN, switch port / AP) |
| lan_networks | `/sites/{siteId}/lan-networks` | Networks / VLANs, subnets, DHCP |
| lan_profiles | `/sites/{siteId}/lan-profiles` | Switch port profiles |
| wlan_groups, ssids, ssid_detail | `/sites/{siteId}/wireless-network/wlans[/{wlanId}/ssids[/{ssidId}]]` | WLAN groups and SSIDs (security mode, VLAN, band, guest) |
| gateway_acls, switch_acls, eap_acls | `/sites/{siteId}/acls/{osg,osw,eap}-acls` | ACL rules in controller order |
| groups | `/sites/{siteId}/profiles/groups` | IP, IP-port and MAC groups |
| port_forwardings, one_to_one_nat | `/sites/{siteId}/nat/…` | NAT rules |
| static_routes | `/sites/{siteId}/routing/static-routings` | Static routes |
| dhcp_reservations | `/sites/{siteId}/setting/service/dhcp` | DHCP reservations |
| internet, wan_status | `/sites/{siteId}/internet`, `/sites/{siteId}/gateways/{mac}/wan-status` | WAN configuration and status |
| vpns, site_to_site_vpns | `/sites/{siteId}/vpn[/site-to-site-vpns]` | VPN configuration (without secrets) |
| switch_ports, switch_poe | `/sites/{siteId}/switches/ports/{overview,poe-info}` | Port status, VLANs, PoE (≥ 6.0) |
| switch_detail | `/sites/{siteId}/switches/{mac}` | Port list fallback for older controllers |

The authoritative list is `backend/app/omada/endpoints.py`.

## Behaviour and error handling

* Requests carry `Authorization: AccessToken=<token>`. Responses use the envelope
  `{"errorCode": 0, "msg": "…", "result": …}`; paged endpoints are read completely (`page`, `pageSize`).
* Expired tokens (`-44112`, `-44113`) are renewed transparently. Invalid credentials fail the sync with a
  clear message (secrets are never logged).
* HTTP 429/5xx and transport errors are retried with exponential backoff (honouring `Retry-After`). The request
  rate is limited (default 5 requests/s, configurable).
* Endpoints the controller does not support (HTTP 404 or error `-1600`) are recorded as `unsupported`;
  permission errors and other failures as `error`. Neither aborts the sync: data of a failed endpoint is
  carried forward from the previous sync and marked stale.
* The per-endpoint result of every sync is visible under **Sync & Import → Sync history**.

## Information not available through the Open API

| Area | Reason |
|------|--------|
| Per-port LLDP neighbours | No per-switch-port LLDP endpoint |
| Learned MAC address table | No MAC table endpoint; clients report switch MAC/port instead |
| Physical cabling | Only uplinks reported by devices are known – cabling is never guessed; document it manually |
| DHCP leases | Only reservations are available |
| WLAN passwords / PSKs, VPN secrets | Deliberately never collected or stored |

These gaps can be closed with manual documentation (descriptions, relationships, documents, attachments).
