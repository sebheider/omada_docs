"""Registry of verified, read-only Omada Open API endpoints used by the collector.

Every path below was verified against controller-exported OpenAPI specifications
(controller 5.x pre-6.0 snapshot, 6.0.0.25 and 6.3.0.45) – see docs/omada-api.md.
Add new endpoints here; the collector picks them up by ``name``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Endpoint:
    name: str
    path: str
    mode: str  # "single" | "paged" | "list"
    scope: str  # "controller" | "site" | "wlan" | "ssid" | "gateway" | "switch"
    description: str
    since: str = "5.12"  # controller version introducing Open API support for the path
    optional: bool = False  # failure does not mark the data area as failed (fallback exists)


ENDPOINTS: tuple[Endpoint, ...] = (
    Endpoint("controller_status", "/system/setting/controller-status", "single", "controller",
             "Controller model, version, uptime"),
    Endpoint("sites", "/sites", "paged", "controller", "Sites"),
    Endpoint("devices", "/sites/{siteId}/devices", "paged", "site", "Adopted devices (gateway, switch, AP)"),
    Endpoint("clients", "/sites/{siteId}/clients", "paged", "site", "Online clients"),
    Endpoint("lan_networks", "/sites/{siteId}/lan-networks", "paged", "site", "LAN networks / VLANs incl. DHCP"),
    Endpoint("lan_profiles", "/sites/{siteId}/lan-profiles", "paged", "site", "Switch port profiles"),
    Endpoint("wlan_groups", "/sites/{siteId}/wireless-network/wlans", "list", "site", "WLAN groups"),
    Endpoint("ssids", "/sites/{siteId}/wireless-network/wlans/{wlanId}/ssids", "paged", "wlan", "SSIDs per WLAN group"),
    Endpoint("ssid_detail", "/sites/{siteId}/wireless-network/wlans/{wlanId}/ssids/{ssidId}", "single", "ssid",
             "SSID details (security, schedule, VLAN)"),
    Endpoint("gateway_acls", "/sites/{siteId}/acls/osg-acls", "paged", "site", "Gateway ACL rules"),
    Endpoint("switch_acls", "/sites/{siteId}/acls/osw-acls", "paged", "site", "Switch ACL rules"),
    Endpoint("eap_acls", "/sites/{siteId}/acls/eap-acls", "paged", "site", "EAP (access point) ACL rules"),
    Endpoint("groups", "/sites/{siteId}/profiles/groups", "list", "site", "IP / IP-port / MAC group profiles"),
    Endpoint("port_forwardings", "/sites/{siteId}/nat/port-forwardings", "paged", "site", "Port forwarding rules"),
    Endpoint("one_to_one_nat", "/sites/{siteId}/nat/one-to-one-nat", "paged", "site", "One-to-one NAT rules"),
    Endpoint("static_routes", "/sites/{siteId}/routing/static-routings", "paged", "site", "Static routes"),
    Endpoint("dhcp_reservations", "/sites/{siteId}/setting/service/dhcp", "paged", "site", "DHCP reservations"),
    Endpoint("internet", "/sites/{siteId}/internet", "single", "site", "WAN port configuration"),
    Endpoint("wan_status", "/sites/{siteId}/gateways/{gatewayMac}/wan-status", "list", "gateway", "Live WAN status"),
    Endpoint("vpns", "/sites/{siteId}/vpn", "paged", "site", "VPN configurations"),
    Endpoint("site_to_site_vpns", "/sites/{siteId}/vpn/site-to-site-vpns", "list", "site", "Site-to-site VPNs",
             optional=True),
    Endpoint("switch_ports", "/sites/{siteId}/switches/ports/overview", "paged", "site",
             "Switch port status/configuration", since="6.0", optional=True),
    Endpoint("switch_poe", "/sites/{siteId}/switches/ports/poe-info", "paged", "site", "Switch PoE details",
             since="6.0", optional=True),
    Endpoint("switch_detail", "/sites/{siteId}/switches/{switchMac}", "single", "switch",
             "Switch details incl. port list (fallback for < 6.0)"),
)

BY_NAME = {e.name: e for e in ENDPOINTS}

#: Information requested in the requirements that the Open API does not expose (documented gap).
UNSUPPORTED_AREAS = [
    ("Per-port LLDP neighbours", "No per-switch-port LLDP neighbour endpoint exists in the Open API."),
    ("Learned MAC address table", "No switch MAC address table endpoint exists; clients list switchMac/port instead."),
    ("Physical cabling", "Only uplink relationships reported by devices are known; cabling is never guessed."),
    ("DHCP leases", "Only DHCP reservations are available, not the dynamic lease table."),
    ("WLAN passwords / PSKs", "Deliberately never collected or stored."),
    ("VPN secrets", "Pre-shared keys, passwords and private keys are removed before storage."),
]
