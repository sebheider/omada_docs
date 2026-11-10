"""Normalisation of raw Omada Open API payloads into the platform's entity format.

All enum mappings below are taken from the controller-exported OpenAPI specification.
Unknown values are kept as ``"unknown (<value>)"`` instead of being guessed.
Secrets (PSKs, VPN keys, passwords, ...) are removed recursively before anything is stored.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any

# ----------------------------------------------------------------------------- helpers

_SECRET_EXACT = {"psk", "key", "pwd", "passphrase", "hidepwd"}
_SECRET_PARTS = ("password", "secret", "token", "presharedkey", "privatekey", "securitykey", "passwd")


def is_secret_key(name: str) -> bool:
    low = name.lower()
    return low in _SECRET_EXACT or any(p in low for p in _SECRET_PARTS)


def sanitize(value: Any) -> Any:
    """Recursively drop secret fields from API payloads."""
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items() if not is_secret_key(str(k))}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    return value


def norm_mac(mac: Any) -> str | None:
    if not mac:
        return None
    hexdigits = re.sub(r"[^0-9A-Fa-f]", "", str(mac))
    if len(hexdigits) != 12:
        return str(mac).upper()
    return "-".join(hexdigits[i:i + 2] for i in range(0, 12, 2)).upper()


def _enum(mapping: dict[Any, str], value: Any) -> str | None:
    if value is None:
        return None
    return mapping.get(value, f"unknown ({value})")


_UPTIME_RE = re.compile(r"(\d+)\s*(day|d|h|hour|m|min|s|sec)", re.I)


def parse_uptime(value: Any) -> int | None:
    """Omada device uptime is a string such as ``"3day(s) 2h 5m 10s"``; controller uptime is seconds."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if str(value).isdigit():
        return int(value)
    total = 0
    found = False
    for num, unit in _UPTIME_RE.findall(str(value)):
        found = True
        u = unit.lower()
        mult = 86400 if u.startswith("d") else 3600 if u.startswith("h") else 60 if u.startswith("m") else 1
        total += int(num) * mult
    return total if found else None


def _split_gateway_subnet(value: str | None) -> tuple[str | None, str | None, str | None]:
    """``"192.168.10.1/24"`` -> (gateway, network cidr, netmask)."""
    if not value:
        return None, None, None
    try:
        iface = ipaddress.ip_interface(value)
    except ValueError:
        return None, None, None
    return str(iface.ip), str(iface.network), str(iface.network.netmask)


# ----------------------------------------------------------------------------- enum maps (from spec)

DEVICE_STATUS = {0: "offline", 1: "online", 2: "pending", 3: "heartbeat_missed", 4: "isolated"}
DEVICE_TYPES = {"gateway": "gateway", "switch": "switch", "ap": "ap"}
LINK_SPEED_DEVICE = {0: "Auto", 1: "10 Mbps", 2: "100 Mbps", 3: "1 Gbps", 4: "2.5 Gbps", 5: "10 Gbps", 6: "5 Gbps",
                     7: "25 Gbps", 8: "100 Gbps"}
PORT_SPEED = {1: "10 Mbps", 2: "100 Mbps", 3: "1 Gbps", 4: "10 Gbps"}
DUPLEX = {0: "Auto", 1: "Half", 2: "Full"}
NETWORK_PURPOSE = {0: "vlan", 1: "interface"}
IPV6_PROTO = {0: "none", 1: "DHCPv6", 2: "SLAAC + stateless DHCP", 3: "SLAAC + RDNSS", 4: "passthrough"}
SSID_SECURITY = {0: "None (open)", 2: "WPA-Enterprise", 3: "WPA-Personal", 4: "PPSK without RADIUS",
                 5: "PPSK with RADIUS"}
PSK_VERSION = {1: "WPA-PSK", 2: "WPA2-PSK", 3: "WPA/WPA2-PSK", 4: "WPA2-PSK/WPA3-SAE"}
PSK_ENCRYPTION = {1: "Auto", 3: "AES"}
ENT_VERSION = {1: "WPA-Enterprise", 2: "WPA2-Enterprise", 3: "WPA/WPA2-Enterprise", 4: "WPA3-Enterprise"}
ENT_ENCRYPTION = {1: "Auto", 3: "AES", 4: "AES-GCM 256", 5: "AES-CNSA", 6: "CCMP-128"}
PMF_MODE = {1: "Mandatory", 2: "Capable", 3: "Disabled"}
CONNECT_TYPE = {0: "wireless_guest", 1: "wireless", 2: "wired"}
RADIO = {0: "2.4 GHz", 1: "5 GHz", 2: "5 GHz-2", 3: "6 GHz"}
ACL_POLICY = {0: "deny", 1: "allow"}
ACL_SIDE_TYPE = {
    0: ("network", False), 1: ("ip_group", False), 2: ("ip_port_group", False), 4: ("ssid", False),
    6: ("ip_group", False), 7: ("ip_port_group", False), 8: ("country", False), 9: ("country_group", False),
    10: ("domain_group", False), 11: ("network", True), 12: ("ip_group", True), 13: ("ip_port_group", True),
    14: ("ip_group", True), 15: ("ip_port_group", True),
}
GROUP_TYPE = {0: "ip_group", 1: "ip_port_group", 2: "mac_group", 3: "ipv6_group", 4: "ipv6_port_group",
              5: "country_group", 7: "domain_group"}
ACL_PROTOCOLS = {1: "icmp", 2: "igmp", 6: "tcp", 17: "udp", 47: "gre", 50: "esp", 51: "ah", 89: "ospf",
                 112: "vrrp", 115: "l2tp", 132: "sctp", 256: "all"}
NAT_PROTOCOL = {0: "all", 1: "tcp", 2: "udp"}
WAN_IPV4_PROTO = {0: "Static IP", 1: "DHCP", 2: "PPPoE", 3: "L2TP", 4: "PPTP", 5: "DS-Lite", 6: "MAP-E"}
WAN_IPV6_PROTO = {0: "Static", 1: "Dynamic", 2: "PPPoE", 3: "6to4 tunnel", 4: "Bridge"}
ROUTE_TYPE = {0: "next_hop", 1: "interface"}
ROUTE_IFACE = {0: "WAN", 1: "LAN network", 2: "L2TP", 3: "PPTP", 5: "Virtual WAN"}
PROFILE_POE = {0: "off", 1: "on", 2: "unchanged"}
NETWORK_MODE = {0: "trunk", 1: "access"}
SITE_VPN_TYPE = {0: "Auto IPsec", 1: "Manual IPsec"}
CLIENT_VPN_TYPE = {0: "L2TP", 1: "PPTP", 2: "IPsec", 3: "OpenVPN"}
CONTROLLER_TYPE = {0: "Software (Windows)", 1: "Software (Linux)", 10: "OC200", 11: "OC300", 12: "ER7212PC",
                   13: "OC400", 20: "Cloud-Based Controller"}


def bands_from_mask(mask: Any) -> list[str]:
    if not isinstance(mask, int):
        return []
    out = []
    if mask & 1:
        out.append("2.4 GHz")
    if mask & 2:
        out.append("5 GHz")
    if mask & 4:
        out.append("6 GHz")
    return out


def protocol_names(codes: list[Any] | None) -> list[str]:
    if not codes:
        return ["all"]
    names = [ACL_PROTOCOLS.get(c, f"proto-{c}") if isinstance(c, int) else str(c).lower() for c in codes]
    return ["all"] if "all" in names else names


def _entity(kind: str, key: Any, site_id: str | None, name: Any, controller_id: Any = None, **fields) -> dict:
    return {"kind": kind, "key": str(key), "site_id": site_id, "name": name,
            "controller_id": str(controller_id) if controller_id is not None else None, **fields}


# ----------------------------------------------------------------------------- per-kind parsers


def parse_controller(info: dict | None, status: dict | None, host: str | None) -> dict:
    info, status = info or {}, status or {}
    ctype = status.get("controllerType")
    return _entity(
        "controller", "controller", None, status.get("name") or "Omada Controller", info.get("omadacId"),
        model=status.get("model") or _enum(CONTROLLER_TYPE, ctype),
        controller_type=_enum(CONTROLLER_TYPE, ctype),
        version=status.get("controllerVersion") or info.get("controllerVer"),
        firmware=status.get("firmwareVersion"),
        api_version=info.get("apiVer"),
        mac=norm_mac(status.get("macAddress")),
        serial=status.get("sn"),
        host=host,
        uptime_seconds=parse_uptime(status.get("upTime")),
        timezone=status.get("timeZone"),
        status="online",
        capacity=status.get("deviceCapacity"),
        validation_status="valid" if status else "partial",
    )


def parse_site(site: dict) -> dict:
    return _entity(
        "site", site.get("siteId"), site.get("siteId"), site.get("name"), site.get("siteId"),
        region=site.get("region"), timezone=site.get("timeZone"), scenario=site.get("scenario"),
        address=site.get("address"), primary=site.get("primary"),
        site_type={0: "basic", 1: "pro"}.get(site.get("type")) if site.get("type") is not None else None,
    )


def parse_device(dev: dict, site_id: str) -> dict:
    mac = norm_mac(dev.get("mac"))
    status = _enum(DEVICE_STATUS, dev.get("status")) or "unknown"
    return _entity(
        "device", mac, site_id, dev.get("name") or mac, mac,
        mac=mac,
        type=DEVICE_TYPES.get(str(dev.get("type") or "").lower(), "unknown"),
        model=dev.get("model") or dev.get("modelName"),
        model_name=dev.get("modelName"),
        hw_version=dev.get("modelVersion"),
        ip=dev.get("ip"),
        ipv6=dev.get("ipv6") or [],
        public_ip=dev.get("publicIp"),
        serial=dev.get("sn"),
        firmware=dev.get("firmwareVersion"),
        status=status,
        adopted=None if dev.get("status") is None else dev.get("status") != 2,
        uptime=dev.get("uptime"),
        uptime_seconds=parse_uptime(dev.get("uptime")),
        cpu_percent=dev.get("cpuUtil"),
        memory_percent=dev.get("memUtil"),
        uplink_device_mac=norm_mac(dev.get("uplinkDeviceMac")),
        uplink_device_name=dev.get("uplinkDeviceName"),
        uplink_port=str(dev.get("uplinkDevicePort")) if dev.get("uplinkDevicePort") not in (None, "") else None,
        uplink_speed=_enum(LINK_SPEED_DEVICE, dev.get("linkSpeed")),
        tag=dev.get("tagName"),
        last_seen=dev.get("lastSeen"),
        validation_status="valid" if mac and dev.get("type") else "partial",
    )


def parse_network(net: dict, site_id: str, reservations: list[dict]) -> dict:
    gateway, subnet, netmask = _split_gateway_subnet(net.get("gatewaySubnet"))
    dhcp = net.get("dhcpSettingsVO") or {}
    dns_mode = dhcp.get("dhcpns")
    dns = [d for d in (dhcp.get("priDns"), dhcp.get("sndDns")) if d] if dns_mode == "manual" else []
    ipv6 = net.get("lanNeworkIpv6Config") or {}
    nid = net.get("id")
    return _entity(
        "network", nid, site_id, net.get("name"), nid,
        purpose=_enum(NETWORK_PURPOSE, net.get("purpose")),
        vlan_id=net.get("vlan"),
        vlans=net.get("vlans"),
        subnet=subnet,
        gateway=gateway,
        netmask=netmask,
        domain=net.get("domain"),
        primary=net.get("primary"),
        application={0: "gateway_and_switch", 1: "switch_only"}.get(net.get("application")),
        dhcp={
            "enabled": dhcp.get("enable"),
            "range_start": dhcp.get("ipaddrStart"),
            "range_end": dhcp.get("ipaddrEnd"),
            "lease_minutes": dhcp.get("leasetime"),
            "dns_mode": dns_mode,
            "dns_servers": dns,
            "gateway": dhcp.get("gateway"),
            "reservations": sorted(
                ({"mac": norm_mac(r.get("mac")), "ip": r.get("ip"), "name": r.get("clientName") or r.get("name"),
                  "description": r.get("description"), "enabled": r.get("status")} for r in reservations),
                key=lambda r: str(r.get("ip")),
            ),
        },
        dhcp_guard=(net.get("dhcpGuard") or {}).get("enable"),
        igmp_snooping=net.get("igmpSnoopEnable"),
        ipv6={"enabled": ipv6.get("enable") == 1 if ipv6.get("enable") is not None else None,
              "mode": _enum(IPV6_PROTO, ipv6.get("proto"))},
        portal=net.get("portal"),
        validation_status="valid" if (subnet or net.get("purpose") == 0) else "partial",
    )


def parse_ip_group(group: dict, site_id: str) -> dict:
    entries = []
    for e in group.get("ipList") or []:
        if e.get("ip"):
            entries.append({"ip": f"{e['ip']}/{e.get('mask') or 32}", "description": e.get("description")})
    for e in group.get("ipv6List") or []:
        if e.get("ip"):
            entries.append({"ip": f"{e['ip']}/{e.get('prefix') or 128}", "description": e.get("description")})
    gid = group.get("groupId")
    return _entity(
        "ip_group", gid, site_id, group.get("name"), gid,
        type=_enum(GROUP_TYPE, group.get("type")),
        entries=entries,
        ports=group.get("portList") or [],
        macs=[{"mac": norm_mac(m.get("macAddress")), "name": m.get("name")} for m in group.get("macAddressList") or []],
        domains=group.get("domainName") or [],
        countries=group.get("countryList") or [],
        built_in=group.get("buildIn"),
        description=group.get("description"),
    )


def parse_port_profile(p: dict, site_id: str, nets: dict[str, dict]) -> dict:
    def names(ids):
        return [nets[i]["name"] if i in nets else i for i in ids or []]

    pid = p.get("id")
    return _entity(
        "port_profile", pid, site_id, p.get("name"), pid,
        native_network_id=p.get("nativeNetworkId"),
        native_network=names([p.get("nativeNetworkId")])[0] if p.get("nativeNetworkId") else None,
        tagged_network_ids=p.get("tagNetworkIds") or [],
        tagged_networks=names(p.get("tagNetworkIds")),
        untagged_network_ids=p.get("untagNetworkIds") or [],
        untagged_networks=names(p.get("untagNetworkIds")),
        voice_network_id=p.get("voiceNetworkId"),
        poe=_enum(PROFILE_POE, p.get("poe")),
        port_isolation=p.get("portIsolationEnable"),
        dot1x={0: "force_unauthorized", 1: "force_authorized", 2: "auto"}.get(p.get("dot1x")),
        spanning_tree=p.get("spanningTreeEnable"),
        lldp_med=p.get("lldpMedEnable"),
        loopback_detect=p.get("loopbackDetectEnable"),
        profile_type={0: "all", 1: "disable", 2: "custom"}.get(p.get("type")),
    )


def parse_ssid(group: dict, summary: dict, detail: dict | None, site_id: str, nets: dict[str, dict]) -> dict:
    d = {**summary, **(detail or {})}
    sid = d.get("id") or d.get("ssidId")
    security = _enum(SSID_SECURITY, d.get("security"))
    psk = d.get("pskSetting") or {}
    ent = d.get("entSetting") or {}
    if d.get("security") == 3:
        version, encryption = _enum(PSK_VERSION, psk.get("versionPsk")), _enum(PSK_ENCRYPTION, psk.get("encryptionPsk"))
    elif d.get("security") == 2:
        version, encryption = _enum(ENT_VERSION, ent.get("versionEnt")), _enum(ENT_ENCRYPTION, ent.get("encryptionEnt"))
    elif d.get("security") == 0:
        version, encryption = ("OWE (Enhanced Open)" if d.get("oweEnable") else None), ("OWE" if d.get("oweEnable") else "None")
    else:
        version, encryption = None, None
    vlan_enabled = d.get("vlanEnable")
    vlan_id = d.get("vlanId") if vlan_enabled else None
    custom = ((d.get("vlanSetting") or {}).get("customConfig") or {})
    network_id = custom.get("lanNetworkId")
    network_source = "api" if network_id else None
    if not network_id and vlan_id is not None:
        match = [n for n in nets.values() if n.get("vlan_id") == vlan_id]
        if len(match) == 1:
            network_id, network_source = match[0]["key"], "derived"
    if network_id and vlan_id is None and network_id in nets:
        vlan_id = nets[network_id].get("vlan_id")
    schedule = d.get("wlanSchedule") or {}
    return _entity(
        "wlan", sid, site_id, d.get("name"), sid,
        ssid=d.get("name"),
        wlan_group=group.get("name"),
        wlan_group_id=group.get("id") or group.get("wlanId"),
        enabled=d.get("ssidEnable") if d.get("ssidEnable") is not None else None,
        broadcast=d.get("broadcast"),
        bands=bands_from_mask(d.get("band")),
        security=security,
        security_version=version,
        encryption=encryption,
        pmf=_enum(PMF_MODE, d.get("pmfMode")),
        fast_roaming_11r=d.get("enable11r"),
        mlo=d.get("mloEnable"),
        guest=bool(d.get("guestNetEnable")),
        vlan_enabled=vlan_enabled,
        vlan_id=vlan_id,
        network_id=network_id,
        network_name=nets.get(network_id, {}).get("name") if network_id else None,
        network_source=network_source,
        schedule={"enabled": schedule.get("wlanScheduleEnable"), "profile_id": schedule.get("scheduleId"),
                  "action": {0: "radio_off", 1: "radio_on"}.get(schedule.get("action"))},
        ap_assignment="all" if d.get("chooseDevices") == 0 else ("selected" if d.get("chooseDevices") == 1 else None),
        ap_group_ids=d.get("apGroupIds") or [],
        mac_filter=(d.get("macFilter") or {}).get("macFilterEnable"),
        validation_status="valid" if detail else "partial",
    )


def parse_acl(rule: dict, acl_type: str, site_id: str, nets: dict, groups: dict, ssids: dict) -> dict:
    def side(type_code: Any, ids: list | None) -> dict:
        stype, negate = ACL_SIDE_TYPE.get(type_code, ("unknown", False))
        refs = []
        ports: list[str] = []
        for rid in ids or []:
            rid = str(rid)
            if stype == "network":
                name = nets.get(rid, {}).get("name")
            elif stype in ("ip_group", "ip_port_group", "country_group", "domain_group"):
                g = groups.get(rid, {})
                name = g.get("name")
                ports.extend(g.get("ports") or [])
            elif stype == "ssid":
                name = ssids.get(rid, {}).get("name")
            else:
                name = None
            refs.append({"id": rid, "name": name or rid, "resolved": name is not None})
        out = {"type": stype, "negate": negate, "refs": refs}
        if ports:
            out["ports"] = sorted(set(ports))
        if not ids and stype != "unknown" and not negate:
            # The controller sends an empty ID list when "Any" is selected for a side.
            out["type"] = "any"
        return out

    direction = rule.get("direction") or {}
    directions = []
    if acl_type == "gateway":
        if direction.get("lanToLan"):
            directions.append("lan_to_lan")
        if direction.get("lanToWan"):
            directions.append("lan_to_wan")
        if direction.get("wanInIds"):
            directions.append("wan_in")
        if direction.get("vpnInIds"):
            directions.append("vpn_in")
    rid = rule.get("id")
    return _entity(
        "acl_rule", f"{acl_type}:{rid}", site_id, rule.get("name") or rule.get("description") or f"{acl_type} rule {rule.get('index')}",
        rid,
        acl_type=acl_type,
        index=rule.get("index"),
        enabled=bool(rule.get("status")),
        action=_enum(ACL_POLICY, rule.get("policy")) or "unknown",
        protocols=protocol_names(rule.get("protocols")),
        direction=directions[0] if len(directions) == 1 else ("unknown" if not directions else directions[0]),
        directions=directions,
        source=side(rule.get("sourceType"), rule.get("sourceIds")),
        destination=side(rule.get("destinationType"), rule.get("destinationIds")),
        description=rule.get("description"),
        time_range_id=rule.get("timeRangeId"),
        state_mode={0: "auto", 1: "manual"}.get(rule.get("stateMode")),
        binding={0: "all_ports", 1: "custom_ports", 2: "all_switch_vlans", 3: "custom_switch_vlans"}.get(
            rule.get("bindingType")) if acl_type == "switch" else None,
        validation_status="valid" if rule.get("policy") in (0, 1) else "partial",
    )


def parse_port_forward(pf: dict, site_id: str) -> dict:
    pid = pf.get("id")
    return _entity(
        "nat_rule", f"pf:{pid}", site_id, pf.get("name"), pid,
        nat_type="port_forwarding",
        enabled=bool(pf.get("status")),
        protocol=_enum(NAT_PROTOCOL, pf.get("protocol")),
        external_port=pf.get("externalPort"),
        internal_ip=pf.get("forwardIp"),
        internal_port=pf.get("forwardPort"),
        source="any" if pf.get("from") == 0 else ("limited" if pf.get("from") == 1 else None),
        source_addresses=pf.get("limitedAddresses") or [],
        dmz=pf.get("dMZ"),
        wan_port_ids=pf.get("interfaceWanPortId") or [],
    )


def parse_one_to_one(n: dict, site_id: str) -> dict:
    nid = n.get("id")
    return _entity(
        "nat_rule", f"121:{nid}", site_id, n.get("name"), nid,
        nat_type="one_to_one", enabled=bool(n.get("status")), external_ip=n.get("externalIp"),
        internal_ip=n.get("internalIp"), dmz=n.get("dmz"), description=n.get("description"),
        wan_port_ids=n.get("interfaceIds") or [],
    )


def parse_route(r: dict, site_id: str, nets: dict) -> dict:
    rid = r.get("id")
    iface = r.get("interfaceId")
    return _entity(
        "route", rid, site_id, r.get("name"), rid,
        enabled=bool(r.get("status")), destinations=r.get("destinations") or [],
        route_type=_enum(ROUTE_TYPE, r.get("routeType")), next_hop=r.get("nextHopIp"),
        interface_type=_enum(ROUTE_IFACE, r.get("interfaceType")),
        interface=nets.get(iface, {}).get("name", iface) if iface else None, metric=r.get("metric"),
    )


def parse_vpn(v: dict, site_id: str, nets: dict, kind_hint: str | None = None) -> dict:
    vid = v.get("id")
    if v.get("siteVpnType") is not None:
        vtype = "Site-to-site " + (_enum(SITE_VPN_TYPE, v.get("siteVpnType")) or "")
    elif v.get("clientVpnType2") is not None:
        role = {0: "server", 1: "client"}.get(v.get("clientVpnType1"), "")
        vtype = f"Client-to-site {_enum(CLIENT_VPN_TYPE, v.get('clientVpnType2'))} {role}".strip()
    else:
        vtype = kind_hint or "VPN"
    subnets = []
    for s in v.get("remoteSubnet") or []:
        if isinstance(s, dict) and s.get("ip"):
            subnets.append(f"{s['ip']}/{s.get('mask', 32)}")
        elif isinstance(s, str):
            subnets.append(s)
    return _entity(
        "vpn", vid, site_id, v.get("name"), vid,
        type=vtype, enabled=bool(v.get("status")), remote_ip=v.get("remoteIp"), remote_site=v.get("remoteSite"),
        local_networks=[nets.get(n, {}).get("name", n) for n in v.get("networkList") or []],
        remote_subnets=subnets,
        working_mode={0: "NAT", 1: "Routing"}.get(v.get("workingMode")),
        settings=sanitize({k: v.get(k) for k in ("advancedSetting", "servicePort", "encryption", "openVpnTunnelMode")
                           if v.get(k) is not None}),
    )


def parse_wans(internet: dict | None, wan_status: dict[str, list], site_id: str) -> list[dict]:
    out = []
    status_by_name: dict[str, dict] = {}
    for ports in (wan_status or {}).values():
        for p in ports or []:
            if p.get("mode", 0) == 0 and p.get("name"):
                status_by_name[p["name"]] = p
    for w in (internet or {}).get("wanPortSettings") or []:
        v4 = w.get("wanPortIpv4Setting") or {}
        v6 = w.get("wanPortIpv6Setting") or {}
        proto = v4.get("protoType")
        proto_key = {0: "ipv4Static", 1: "ipv4Dhcp", 2: "ipv4Pppoe", 3: "ipv4L2tp", 4: "ipv4Pptp", 5: "ipv4Dslite",
                     6: "ipv4Mape"}.get(proto)
        live = status_by_name.get(w.get("portName") or "", {})
        cfg4 = live.get("wanPortIpv4Config") or {}
        cfg6 = live.get("wanPortIpv6Config") or {}
        key = w.get("portUuid") or w.get("portId") or w.get("portName")
        out.append(_entity(
            "wan", key, site_id, w.get("portName"), w.get("portId") or w.get("portUuid"),
            description=w.get("portDescription"),
            ipv4={"type": _enum(WAN_IPV4_PROTO, proto), "vlan_id": v4.get("vlanId") or None,
                  "settings": sanitize(v4.get(proto_key) or {}) if proto_key else {},
                  "address": cfg4.get("ip") or live.get("ip"), "netmask": cfg4.get("netmask"),
                  "gateway": cfg4.get("gateway"),
                  "dns": [d for d in (cfg4.get("priDns"), cfg4.get("sndDns")) if d]},
            ipv6={"enabled": v6.get("enable"), "type": _enum(WAN_IPV6_PROTO, v6.get("protoType")),
                  "address": cfg6.get("addr"), "gateway": cfg6.get("gateway")},
            type=_enum(WAN_IPV4_PROTO, proto),
            vlan_id=v4.get("vlanId") or None,
            status=("connected" if live.get("internetState") == 1 else "disconnected") if live else "unknown",
            isp=live.get("isp"),
            speed=_enum({1: "10 Mbps", 2: "100 Mbps", 3: "1 Gbps"}, live.get("speed")),
            validation_status="valid" if live else "partial",
        ))
    return out


def parse_switch_ports(site_id: str, devices: list[dict], overview: list[dict] | None, poe: list[dict] | None,
                       details: dict[str, dict | None], nets: dict, profiles: dict, clients: list[dict]) -> list[dict]:
    dev_by_mac = {d["mac"]: d for d in devices}
    ports: dict[tuple[str, int], dict] = {}

    for mac, det in (details or {}).items():
        smac = norm_mac(mac)
        for p in (det or {}).get("portList") or []:
            ports.setdefault((smac, p.get("port")), {}).update({
                "name": p.get("name"), "profileId": p.get("profileId"), "profileName": p.get("profileName"),
                "poeMode": p.get("poeMode"), "enabledStatus": p.get("status"), "lagPort": p.get("lagPort"),
                "profileOverrideEnable": p.get("profileOverrideEnable"),
            })
    for p in overview or []:
        smac = norm_mac(p.get("switchMac"))
        ports.setdefault((smac, p.get("port")), {}).update({"overview": p})
    for p in poe or []:
        smac = norm_mac(p.get("switchMac"))
        ports.setdefault((smac, p.get("port")), {}).update({"poeinfo": p})

    # Device-to-device links reported by the controller (child.uplinkDeviceMac / uplinkDevicePort)
    downlinks: dict[tuple[str, str], dict] = {}
    for d in devices:
        if d.get("uplink_device_mac") and d.get("uplink_port"):
            downlinks[(d["uplink_device_mac"], str(d["uplink_port"]))] = d
    wired_clients: dict[tuple[str, str], list[dict]] = {}
    for c in clients:
        if c.get("connected_device_type") == "switch" and c.get("port") is not None:
            wired_clients.setdefault((c["connected_device_mac"], str(c["port"])), []).append(c)

    out = []
    for (smac, port), p in sorted(ports.items(), key=lambda kv: (kv[0][0] or "", kv[0][1] or 0)):
        if port is None or smac is None:
            continue
        ov = p.get("overview") or {}
        st = ov.get("portStatus") or {}
        pi = p.get("poeinfo") or {}
        switch = dev_by_mac.get(smac, {})
        if st.get("linkStatus") is not None:
            link = "up" if st.get("linkStatus") == 1 else "down"
        elif ov.get("connectedStatus") is not None:
            link = {0: "up", 1: "down", 2: "disabled"}.get(ov.get("connectedStatus"), "unknown")
        else:
            link = "unknown"
        if ov.get("disable") or p.get("enabledStatus") == 0:
            link = "disabled"
        profile_id = ov.get("profileId") or p.get("profileId")
        profile = profiles.get(profile_id, {})
        native_id = ov.get("nativeNetworkId") or profile.get("native_network_id")
        poe_cfg = ov.get("poe") if ov.get("poe") is not None else (pi.get("poe") if pi else p.get("poeMode"))
        poe_power = st.get("poePower") if st.get("poePower") is not None else pi.get("power")
        poe_active = st.get("poe") if st.get("poe") is not None else (bool(poe_power) if poe_power is not None else None)

        child = downlinks.get((smac, str(port)))
        connected = []
        if child:
            connected.append({"mac": child["mac"], "name": child["name"], "type": child["type"], "source": "api",
                              "relation": "downlink"})
        for c in wired_clients.get((smac, str(port)), []):
            connected.append({"mac": c["mac"], "name": c["name"], "type": "client", "source": "api",
                              "ip": c.get("ip")})
        # Uplink is only asserted when LLDP chassis id of the neighbour equals this switch's uplink device MAC.
        role = None
        chassis = norm_mac(st.get("chassisId")) if st.get("chassisId") else None
        if chassis and switch.get("uplink_device_mac") and chassis == switch["uplink_device_mac"]:
            role = "uplink"
        elif child and child.get("type") in ("switch", "gateway", "ap"):
            role = "downlink"
        lldp = None
        if st.get("chassisId") or st.get("portId"):
            lldp = {"chassis_id": st.get("chassisId"), "port_id": st.get("portId")}
        warning = None
        if ov.get("networkTagsSetting") is None and profile.get("profile_type") is None and not profile_id:
            warning = None
        if st.get("stpDiscarding"):
            warning = "STP discarding"
        if st.get("blockedType"):
            warning = f"Port blocked (type {st.get('blockedType')})"
        out.append(_entity(
            "switch_port", f"{smac}:{port}", site_id, ov.get("portName") or p.get("name") or f"Port {port}",
            f"{smac}:{port}",
            switch_mac=smac,
            switch_name=switch.get("name") or ov.get("switchName"),
            port=port,
            port_type={1: "copper", 2: "combo", 3: "sfp"}.get(ov.get("type")),
            link_status=link,
            speed=_enum(PORT_SPEED, st.get("linkSpeed")) if link == "up" else None,
            duplex=_enum(DUPLEX, st.get("duplex")) if link == "up" else None,
            configured_speed=_enum({0: "Auto", 1: "10 Mbps", 2: "100 Mbps", 3: "1 Gbps", 4: "10 Gbps"}, ov.get("linkSpeed")),
            poe={"supported": ov.get("supportPoe", pi.get("supportPoe") if pi else None),
                 "enabled": None if poe_cfg is None else poe_cfg == 1,
                 "active": poe_active, "power_w": poe_power, "pd_class": pi.get("pdClass") if pi else None},
            profile_id=profile_id,
            profile_name=ov.get("profileName") or p.get("profileName") or profile.get("name"),
            profile_override=ov.get("profileOverrideEnable", p.get("profileOverrideEnable")),
            network_mode=_enum(NETWORK_MODE, ov.get("networkMode")),
            native_network_id=native_id,
            native_network=nets.get(native_id, {}).get("name") if native_id else None,
            native_vlan_id=nets.get(native_id, {}).get("vlan_id") if native_id else None,
            tagged_networks=profile.get("tagged_networks") or [],
            untagged_networks=profile.get("untagged_networks") or [],
            port_isolation=profile.get("port_isolation"),
            lag=bool(p.get("lagPort") or ov.get("lagSetting")),
            link_role=role,
            connected=connected,
            lldp=lldp,
            stp=st.get("stp"),
            rx_bytes=st.get("rx"),
            tx_bytes=st.get("tx"),
            warning=warning,
            validation_status="valid" if ov else "partial",
        ))
    return out


def parse_client(c: dict, site_id: str) -> dict:
    mac = norm_mac(c.get("mac"))
    ctype = c.get("connectType")
    wireless = bool(c.get("wireless"))
    if wireless:
        dev_mac, dev_name, dev_type = norm_mac(c.get("apMac")), c.get("apName"), "ap"
    elif c.get("switchMac"):
        dev_mac, dev_name, dev_type = norm_mac(c.get("switchMac")), c.get("switchName"), "switch"
    elif c.get("gatewayMac"):
        dev_mac, dev_name, dev_type = norm_mac(c.get("gatewayMac")), c.get("gatewayName"), "gateway"
    else:
        dev_mac, dev_name, dev_type = None, None, c.get("connectDevType")
    return _entity(
        "client", mac, site_id, c.get("name") or c.get("hostName") or mac, c.get("id") or mac,
        mac=mac, ip=c.get("ip"), ipv6=c.get("ipv6List") or [], hostname=c.get("hostName"), vendor=c.get("vendor"),
        device_type=c.get("deviceType"), device_category=c.get("deviceCategory"), os=c.get("osName"),
        model=c.get("model"),
        vlan_id=c.get("vid"), network_name=c.get("networkName"), network_id=(c.get("ipSetting") or {}).get("netId"),
        wireless=wireless, guest=bool(c.get("guest")) or ctype == 0,
        connection_type=_enum(CONNECT_TYPE, ctype) or ("wireless" if wireless else "wired"),
        connected_device_mac=dev_mac, connected_device_name=dev_name, connected_device_type=dev_type,
        port=c.get("port"), port_name=c.get("portName"), ssid=c.get("ssid"),
        radio=_enum(RADIO, c.get("radioId")), active=c.get("active"),
        signal_percent=c.get("signalLevel"), rssi=c.get("rssi"), snr=c.get("snr"),
        fixed_ip=(c.get("ipSetting") or {}).get("useFixedAddr"),
        last_seen=c.get("lastSeen"), uptime_seconds=c.get("uptime"), health_score=c.get("healthScore"),
    )


# ----------------------------------------------------------------------------- dataset


def normalize(raw: dict[str, Any], host: str | None = None) -> dict[str, list[dict]]:
    """Convert the collector output into ``{kind: [entity, ...]}``."""
    entities: dict[str, list[dict]] = {k: [] for k in (
        "controller", "site", "device", "network", "wan", "wlan", "switch_port", "client", "acl_rule",
        "nat_rule", "route", "vpn", "ip_group", "port_profile")}
    entities["controller"].append(parse_controller(raw.get("controller_info"), raw.get("controller_status"), host))

    for s in raw.get("sites") or []:
        site = s.get("site") or {}
        sid = site.get("siteId")
        entities["site"].append(parse_site(site))

        reservations: dict[str, list[dict]] = {}
        for r in s.get("dhcp_reservations") or []:
            reservations.setdefault(r.get("netId"), []).append(r)
        networks = [parse_network(n, sid, reservations.get(n.get("id"), [])) for n in s.get("lan_networks") or []]
        nets = {n["key"]: n for n in networks}
        entities["network"] += networks

        groups = [parse_ip_group(g, sid) for g in s.get("groups") or [] if g.get("groupId")]
        groups_by_id = {g["key"]: g for g in groups}
        entities["ip_group"] += groups

        profiles = [parse_port_profile(p, sid, nets) for p in s.get("lan_profiles") or []]
        profiles_by_id = {p["key"]: p for p in profiles}
        entities["port_profile"] += profiles

        devices = [parse_device(d, sid) for d in s.get("devices") or []]
        entities["device"] += devices
        clients = [parse_client(c, sid) for c in s.get("clients") or []]
        entities["client"] += clients

        wlans = []
        for wg in s.get("wlan_groups") or []:
            for item in wg.get("ssids") or []:
                wlans.append(parse_ssid(wg.get("group") or {}, item.get("summary") or {}, item.get("detail"), sid, nets))
        for w in wlans:
            w["client_count"] = sum(1 for c in clients if c.get("wireless") and c.get("ssid") == w["ssid"])
        entities["wlan"] += wlans
        ssids_by_id = {w["key"]: w for w in wlans}

        for acl_type, field in (("gateway", "gateway_acls"), ("switch", "switch_acls"), ("eap", "eap_acls")):
            entities["acl_rule"] += [parse_acl(r, acl_type, sid, nets, groups_by_id, ssids_by_id)
                                     for r in s.get(field) or []]
        entities["nat_rule"] += [parse_port_forward(p, sid) for p in s.get("port_forwardings") or []]
        entities["nat_rule"] += [parse_one_to_one(n, sid) for n in s.get("one_to_one_nat") or []]
        entities["route"] += [parse_route(r, sid, nets) for r in s.get("static_routes") or []]
        vpns: dict[str, dict] = {}
        for v in s.get("vpns") or []:
            vpns[str(v.get("id"))] = parse_vpn(v, sid, nets)
        for v in s.get("site_to_site_vpns") or []:
            vpns.setdefault(str(v.get("id")), parse_vpn(v, sid, nets, "Site-to-site VPN"))
        entities["vpn"] += list(vpns.values())
        entities["wan"] += parse_wans(s.get("internet"), s.get("wan_status") or {}, sid)
        entities["switch_port"] += parse_switch_ports(
            sid, devices, s.get("switch_ports"), s.get("switch_poe"), s.get("switch_detail") or {}, nets,
            profiles_by_id, clients)
        for d in devices:
            d["client_count"] = sum(1 for c in clients if c.get("connected_device_mac") == d["mac"])
    return entities
