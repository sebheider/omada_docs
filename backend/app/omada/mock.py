"""Demo mode: a simulated Omada controller speaking the Open API wire format.

Used ONLY when demo mode is explicitly enabled (``OMADA_DOCS_DEMO_MODE=true``) and by tests.
The data is served through an ``httpx.MockTransport`` so the complete production pipeline
(client -> collector -> parsers) is exercised.  ``revision`` lets successive demo
synchronisations introduce configuration changes so change tracking can be demonstrated.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

OMADAC_ID = "demo0000000000000000000000000000"
SITE_ID = "demo-site-home"
SITE2_ID = "demo-site-office"

GW = "40-ED-00-00-00-01"
SW1 = "40-ED-00-00-01-01"
SW2 = "40-ED-00-00-01-02"
AP1 = "40-ED-00-00-02-01"
AP2 = "40-ED-00-00-02-02"
AP3 = "40-ED-00-00-02-03"
AP4 = "40-ED-00-00-02-04"

NETS = [
    # id, name, vlan, gatewaySubnet, dhcp start/end
    ("net-mgmt", "Management", 1, "10.10.10.1/24", "10.10.10.100", "10.10.10.199"),
    ("net-home", "Home", 10, "192.168.10.1/24", "192.168.10.100", "192.168.10.250"),
    ("net-server", "Servers", 20, "192.168.20.1/24", "192.168.20.100", "192.168.20.199"),
    ("net-iot", "IoT", 30, "192.168.30.1/24", "192.168.30.50", "192.168.30.250"),
    ("net-cam", "Cameras", 40, "192.168.40.1/24", "192.168.40.100", "192.168.40.199"),
    ("net-guest", "Guest", 50, "192.168.50.1/24", "192.168.50.10", "192.168.50.250"),
    ("net-dmz", "DMZ", 60, "192.168.60.1/24", "192.168.60.100", "192.168.60.150"),
]


def _site_data(revision: int) -> dict[str, Any]:
    lan_networks = []
    for nid, name, vlan, gs, start, end in NETS:
        lan_networks.append({
            "id": nid, "name": name, "purpose": 1, "vlan": vlan, "vlanType": 0, "gatewaySubnet": gs,
            "primary": nid == "net-mgmt", "application": 0, "domain": "home.lan" if nid == "net-home" else None,
            "igmpSnoopEnable": nid == "net-iot",
            "dhcpSettingsVO": {"enable": nid != "net-dmz", "ipaddrStart": start, "ipaddrEnd": end, "leasetime": 120,
                               "dhcpns": "manual" if nid in ("net-home", "net-iot") else "auto",
                               "priDns": "192.168.20.53", "sndDns": "1.1.1.1"},
            "dhcpGuard": {"enable": False},
            "lanNeworkIpv6Config": {"enable": 1 if nid == "net-home" else 0, "proto": 2 if nid == "net-home" else 0},
        })

    groups = [
        {"groupId": "grp-iobroker", "name": "ioBroker", "type": 0, "buildIn": False,
         "ipList": [{"ip": "192.168.20.10", "mask": 32, "description": "ioBroker master"}]},
        {"groupId": "grp-nas", "name": "NAS", "type": 0, "buildIn": False,
         "ipList": [{"ip": "192.168.20.5", "mask": 32, "description": "Synology NAS"}]},
        {"groupId": "grp-mgmt-ui", "name": "Management UI", "type": 1, "buildIn": False, "portType": 0,
         "ipList": [{"ip": "10.10.10.0", "mask": 24}], "portList": ["22", "443", "8043"]},
        {"groupId": "grp-dns", "name": "DNS Server", "type": 1, "buildIn": False, "portType": 0,
         "ipList": [{"ip": "192.168.20.53", "mask": 32}], "portList": ["53"]},
    ]

    def acl(idx, rid, name, policy, st, sids, dt, dids, protos=(256,), lan2lan=True, lan2wan=False, status=True,
            wan_in=None):
        return {"id": rid, "name": name, "index": idx, "policy": policy, "status": status,
                "sourceType": st, "sourceIds": sids, "destinationType": dt, "destinationIds": dids,
                "protocols": list(protos), "description": name,
                "direction": {"lanToLan": lan2lan, "lanToWan": lan2wan, "wanInIds": wan_in or [], "vpnInIds": []},
                "stateMode": 0}

    gateway_acls = [
        acl(1, "acl-iot-iobroker", "IoT to ioBroker", 1, 0, ["net-iot"], 1, ["grp-iobroker"]),
        acl(2, "acl-iot-dns", "IoT to DNS", 1, 0, ["net-iot"], 2, ["grp-dns"], protos=(6, 17)),
        acl(3, "acl-iot-home", "Block IoT to Home", 0, 0, ["net-iot"], 0, ["net-home"]),
        acl(4, "acl-iot-servers", "Block IoT to Servers", 0, 0, ["net-iot"], 0, ["net-server"]),
        acl(5, "acl-iot-mgmt", "Block IoT to Management", 0, 0, ["net-iot"], 0, ["net-mgmt"]),
        acl(6, "acl-guest-lan", "Block Guest to internal", 0, 0, ["net-guest"], 0,
            ["net-home", "net-server", "net-mgmt", "net-iot", "net-cam"]),
        acl(7, "acl-cam-lan", "Isolate cameras", 0, 0, ["net-cam"], 0, ["net-home", "net-iot", "net-guest"]),
        acl(8, "acl-home-mgmt", "Restrict management UI", 0, 0, ["net-home"], 2, ["grp-mgmt-ui"], protos=(6,)),
        acl(9, "acl-dmz-lan", "Block DMZ to LAN", 0, 0, ["net-dmz"], 11, ["net-dmz"]),
        acl(10, "acl-cam-wan", "Cameras no Internet", 0, 0, ["net-cam"], 0, [], lan2lan=False, lan2wan=True),
        acl(11, "acl-iot-home-tcp", "Block IoT to Home (TCP)", 0, 0, ["net-iot"], 0, ["net-home"], protos=(6,)),
        acl(12, "acl-home-iot", "Block Home to IoT (test)", 0, 0, ["net-home"], 0, ["net-iot"], status=False),
    ]
    if revision >= 1:
        gateway_acls.append(acl(13, "acl-guest-dmz", "Block Guest to DMZ", 0, 0, ["net-guest"], 0, ["net-dmz"]))
    switch_acls = [
        {**acl(1, "sacl-dmz-home", "Switch: DMZ to Home", 0, 0, ["net-dmz"], 0, ["net-home"]), "bindingType": 0},
    ]
    eap_acls = [
        {k: v for k, v in acl(1, "eacl-guest-nas", "WLAN: Guest to NAS", 0, 0, ["net-guest"], 1, ["grp-nas"]).items()
         if k not in ("direction", "stateMode")},
    ]

    devices = [
        {"mac": GW, "name": "Gateway ER7206", "type": "gateway", "model": "ER7206 v2.0", "modelName": "ER7206",
         "ip": "10.10.10.1", "status": 1, "firmwareVersion": "2.1.2 Build 20240911", "uptime": "21day(s) 4h 12m 3s",
         "sn": "Y2400000001", "cpuUtil": 9, "memUtil": 41},
        {"mac": SW1, "name": "Core Switch SG2218P", "type": "switch", "model": "SG2218P v1.0", "modelName": "SG2218P",
         "ip": "10.10.10.2", "status": 1, "firmwareVersion": "1.20.4 Build 20240411", "uptime": "21day(s) 4h 2m 3s",
         "uplinkDeviceMac": GW, "uplinkDeviceName": "Gateway ER7206", "uplinkDevicePort": "2", "linkSpeed": 3,
         "sn": "Y2400000002", "cpuUtil": 12, "memUtil": 55},
        {"mac": SW2, "name": "Office Switch SG2008P", "type": "switch", "model": "SG2008P v3.0",
         "modelName": "SG2008P", "ip": "10.10.10.3", "status": 1, "firmwareVersion": "3.20.1 Build 20240205",
         "uptime": "9day(s) 1h 2m 3s", "uplinkDeviceMac": SW1, "uplinkDeviceName": "Core Switch SG2218P",
         "uplinkDevicePort": "16", "linkSpeed": 3, "sn": "Y2400000003"},
        {"mac": AP1, "name": "AP Living Room", "type": "ap", "model": "EAP653 v1.0", "modelName": "EAP653",
         "ip": "10.10.10.11", "status": 1, "firmwareVersion": "1.1.3 Build 20240520", "uptime": "21day(s) 3h",
         "uplinkDeviceMac": SW1, "uplinkDeviceName": "Core Switch SG2218P", "uplinkDevicePort": "1", "linkSpeed": 3},
        {"mac": AP2, "name": "AP Upstairs", "type": "ap", "model": "EAP653 v1.0", "modelName": "EAP653",
         "ip": "10.10.10.12", "status": 1, "firmwareVersion": "1.1.3 Build 20240520", "uptime": "21day(s) 3h",
         "uplinkDeviceMac": SW1, "uplinkDeviceName": "Core Switch SG2218P", "uplinkDevicePort": "2", "linkSpeed": 3},
        {"mac": AP3, "name": "AP Office", "type": "ap", "model": "EAP615-Wall v1.0", "modelName": "EAP615-Wall",
         "ip": "10.10.10.13", "status": 0, "firmwareVersion": "1.4.2 Build 20231201", "uptime": None,
         "uplinkDeviceMac": SW2, "uplinkDeviceName": "Office Switch SG2008P", "uplinkDevicePort": "1"},
    ]
    if revision >= 2:
        devices.append({"mac": AP4, "name": "AP Garden", "type": "ap", "model": "EAP610-Outdoor v1.0",
                        "modelName": "EAP610-Outdoor", "ip": "10.10.10.14", "status": 1,
                        "firmwareVersion": "1.3.0 Build 20240101", "uptime": "0day(s) 2h 1m",
                        "uplinkDeviceMac": SW1, "uplinkDeviceName": "Core Switch SG2218P", "uplinkDevicePort": "9"})

    clients_spec = [
        # mac suffix, name, ip, vlan/network, wired switch+port or ssid/ap, vendor
        ("01", "Synology NAS", "192.168.20.5", 20, "Servers", SW1, 5, None, "Synology"),
        ("02", "ioBroker Master", "192.168.20.10", 20, "Servers", SW1, 6, None, "Raspberry Pi"),
        ("03", "Pi-hole DNS", "192.168.20.53", 20, "Servers", SW1, 7, None, "Raspberry Pi"),
        ("04", "ioBroker Slave", "192.168.30.9", 30, "IoT", SW1, 8, None, "Raspberry Pi"),
        ("05", "Living Room TV", "192.168.10.120", 10, "Home", SW1, 10, None, "LG Electronics"),
        ("06", "Office PC", "192.168.10.101", 10, "Home", SW2, 3, None, "Dell"),
        ("07", "Printer", "192.168.10.30", 10, "Home", SW2, 4, None, "Brother"),
        ("08", "Camera Entrance", "192.168.40.101", 40, "Cameras", SW1, 11, None, "Reolink"),
        ("09", "Camera Garden", "192.168.40.102", 40, "Cameras", SW1, 12, None, "Reolink"),
        ("10", "Web Server", "192.168.60.10", 60, "DMZ", SW1, 14, None, "Intel"),
        ("11", "iPhone Anna", "192.168.10.140", 10, "Home", None, None, ("Home WiFi", AP1, "AP Living Room"), "Apple"),
        ("12", "MacBook Ben", "192.168.10.141", 10, "Home", None, None, ("Home WiFi", AP2, "AP Upstairs"), "Apple"),
        ("13", "Shelly Plug Kitchen", "192.168.30.60", 30, "IoT", None, None, ("IoT", AP1, "AP Living Room"), "Shelly"),
        ("14", "Shelly Dimmer Hall", "192.168.30.61", 30, "IoT", None, None, ("IoT", AP1, "AP Living Room"), "Shelly"),
        ("15", "Robot Vacuum", "192.168.30.70", 30, "IoT", None, None, ("IoT", AP2, "AP Upstairs"), "Roborock"),
        ("16", "Guest Phone", "192.168.50.23", 50, "Guest", None, None, ("Guest", AP1, "AP Living Room"), "Samsung"),
        ("17", "Thermostat", "192.168.30.80", 30, "IoT", None, None, ("IoT", AP2, "AP Upstairs"), "tado"),
    ]
    clients = []
    for i, (suffix, name, ip, vid, netname, sw, port, wl, vendor) in enumerate(clients_spec):
        c: dict[str, Any] = {"mac": f"AA-BB-CC-00-00-{suffix}", "name": name, "ip": ip, "vendor": vendor,
                             "active": True, "uptime": 3600 * (i + 1), "lastSeen": 1731230000000,
                             "ipSetting": {"netId": next(n[0] for n in NETS if n[2] == vid)}}
        if sw:
            c.update(wireless=False, connectType=2, connectDevType="switch", switchMac=sw,
                     switchName="Core Switch SG2218P" if sw == SW1 else "Office Switch SG2008P", port=port,
                     vid=vid, networkName=netname)
        else:
            ssid, apmac, apname = wl
            c.update(wireless=True, connectType=0 if ssid == "Guest" else 1, connectDevType="ap", ssid=ssid,
                     apMac=apmac, apName=apname, radioId=1 if i % 2 else 0, signalLevel=55 + (i * 7) % 40,
                     rssi=-45 - (i * 3) % 30, guest=ssid == "Guest")
        clients.append(c)

    profiles = [
        {"id": "prof-all", "name": "All", "type": 0, "flag": 0, "nativeNetworkId": "net-mgmt",
         "tagNetworkIds": [n[0] for n in NETS if n[0] != "net-mgmt"], "untagNetworkIds": [], "poe": 2},
        {"id": "prof-disable", "name": "Disable", "type": 1, "flag": 0, "poe": 2},
    ] + [
        {"id": f"prof-{n[0][4:]}", "name": n[1], "type": 2, "flag": 1, "nativeNetworkId": n[0], "tagNetworkIds": [],
         "untagNetworkIds": [], "poe": 2, "portIsolationEnable": n[0] == "net-cam"}
        for n in NETS
    ]
    prof_by_id = {p["id"]: p for p in profiles}

    def ports_for(sw_mac, sw_name, count, poe_ports, assignment, sfp_from):
        overview, poe = [], []
        for port in range(1, count + 1):
            prof = assignment.get(port, "prof-all")
            if sw_mac == SW1 and port == 10 and revision >= 1:
                prof = "prof-iot"
            connected = port in assignment or port in uplinks.get(sw_mac, {})
            ptype = 3 if port >= sfp_from else 1
            poe_active = connected and port in poe_ports and port in ap_ports.get(sw_mac, set()) | cam_ports.get(sw_mac, set())
            status = {"port": port, "linkStatus": 1 if connected else 0, "linkSpeed": 3 if connected else None,
                      "duplex": 2 if connected else None, "poe": poe_active, "poePower": 6.4 if poe_active else 0.0,
                      "rx": 123456789 * port if connected else 0, "tx": 98765432 * port if connected else 0}
            if port in uplinks.get(sw_mac, {}):
                status.update(chassisId=uplinks[sw_mac][port], portId=f"port {port}")
            overview.append({"switchMac": sw_mac, "switchName": sw_name, "port": port, "portName": f"Port{port}",
                             "type": ptype, "profileId": prof, "profileName": prof_by_id[prof]["name"],
                             "nativeNetworkId": prof_by_id[prof].get("nativeNetworkId"), "networkMode": 0,
                             "supportPoe": port in poe_ports, "poe": 1 if port in poe_ports else 0,
                             "linkSpeed": 0, "duplex": 0, "disable": False, "portStatus": status,
                             "connectedStatus": 0 if connected else 1})
            if port in poe_ports:
                poe.append({"switchMac": sw_mac, "port": port, "poe": 1, "supportPoe": True,
                            "power": status["poePower"], "pdClass": "Class 4" if poe_active else None})
        return overview, poe

    uplinks = {SW1: {17: GW}, SW2: {8: SW1}}
    ap_ports = {SW1: {1, 2, 9} if revision >= 2 else {1, 2}, SW2: {1}}
    cam_ports = {SW1: {11, 12}}
    sw1_assign = {1: "prof-all", 2: "prof-all", 5: "prof-server", 6: "prof-server", 7: "prof-server",
                  8: "prof-iot", 10: "prof-home", 11: "prof-cam", 12: "prof-cam", 14: "prof-dmz", 16: "prof-all"}
    if revision >= 2:
        sw1_assign[9] = "prof-all"
    sw2_assign = {1: "prof-all", 3: "prof-home", 4: "prof-home"}
    ov1, poe1 = ports_for(SW1, "Core Switch SG2218P", 18, set(range(1, 17)), sw1_assign, 17)
    ov2, poe2 = ports_for(SW2, "Office Switch SG2008P", 8, set(range(1, 5)), sw2_assign, 9)
    # SW2 uplink port 8 -> SW1 port 16
    for p in ov2:
        if p["port"] == 8:
            p["portStatus"].update(linkStatus=1, linkSpeed=3, duplex=2)
            p["connectedStatus"] = 0

    ssids_home = [
        {"id": "ssid-home", "name": "Home WiFi", "band": 3, "broadcast": True, "security": 3, "guestNetEnable": False,
         "vlanEnable": True, "vlanId": 10, "ssidEnable": True, "chooseDevices": 0, "pmfMode": 2, "enable11r": True,
         "pskSetting": {"versionPsk": 4, "encryptionPsk": 3, "securityKey": "never-store-this-psk"},
         "vlanSetting": {"mode": 1, "customConfig": {"customMode": 0, "lanNetworkId": "net-home"}},
         "wlanSchedule": {"wlanScheduleEnable": False}},
        {"id": "ssid-iot", "name": "IoT", "band": 1, "broadcast": False, "security": 3, "guestNetEnable": False,
         "vlanEnable": True, "vlanId": 30, "ssidEnable": True, "chooseDevices": 0, "pmfMode": 3,
         "pskSetting": {"versionPsk": 2, "encryptionPsk": 3, "securityKey": "iot-secret-psk"},
         "wlanSchedule": {"wlanScheduleEnable": False}},
        {"id": "ssid-guest", "name": "Guest", "band": 3, "broadcast": True, "security": 3,
         "guestNetEnable": True, "vlanEnable": True, "vlanId": 50, "ssidEnable": True, "chooseDevices": 1,
         "apGroupIds": ["apg-living"], "pmfMode": 2,
         "pskSetting": {"versionPsk": 3, "encryptionPsk": 1, "securityKey": "guest-psk"},
         "wlanSchedule": {"wlanScheduleEnable": True, "scheduleId": "tr-daytime", "action": 1}},
    ]
    if revision >= 1:
        ssids_home[2]["band"] = 7 if False else 3
        ssids_home[1]["band"] = 3

    port_forwardings = [
        {"id": "pf-web", "name": "Web Server HTTPS", "status": True, "protocol": 1, "externalPort": "443",
         "forwardIp": "192.168.60.10", "forwardPort": "443", "from": 0, "dMZ": False, "interfaceWanPortId": ["wan1"]},
        {"id": "pf-vpn", "name": "WireGuard (NAS)", "status": False, "protocol": 2, "externalPort": "51820",
         "forwardIp": "192.168.20.5", "forwardPort": "51820", "from": 0, "dMZ": False,
         "interfaceWanPortId": ["wan1"]},
    ]
    if revision >= 1:
        port_forwardings.append({"id": "pf-ha", "name": "Home Assistant", "status": True, "protocol": 1,
                                 "externalPort": "8123", "forwardIp": "192.168.20.10", "forwardPort": "8123",
                                 "from": 1, "limitedAddresses": ["203.0.113.0/24"], "interfaceWanPortId": ["wan1"]})

    return {
        "site": {"siteId": SITE_ID, "name": "Home", "region": "Germany", "timeZone": "Europe/Berlin",
                 "scenario": "Home", "type": 0, "primary": True},
        "devices": devices,
        "clients": clients,
        "lan-networks": lan_networks,
        "lan-profiles": profiles,
        "wlans": [{"id": "wlan-default", "wlanId": "wlan-default", "name": "Default", "primary": True}],
        "ssids": {"wlan-default": ssids_home},
        "osg-acls": gateway_acls,
        "osw-acls": switch_acls,
        "eap-acls": eap_acls,
        "groups": groups,
        "port-forwardings": port_forwardings,
        "one-to-one-nat": [],
        "static-routings": [
            {"id": "rt-lab", "name": "Lab network", "status": True, "destinations": ["172.20.0.0/16"],
             "routeType": 0, "nextHopIp": "192.168.20.254", "metric": 1},
        ],
        "dhcp": [
            {"id": "res-nas", "mac": "AA-BB-CC-00-00-01", "ip": "192.168.20.5", "clientName": "Synology NAS",
             "netId": "net-server", "netName": "Servers", "status": True},
            {"id": "res-iob", "mac": "AA-BB-CC-00-00-04", "ip": "192.168.30.9", "clientName": "ioBroker Slave",
             "netId": "net-iot", "netName": "IoT", "status": True},
        ],
        "internet": {"wanPortSettings": [
            {"portUuid": "wan1", "portId": "wan1", "portName": "WAN1", "portDescription": "Fibre",
             "wanPortIpv4Setting": {"protoType": 2, "vlanId": 7, "ipv4Pppoe": {"username": "user@isp.example",
                                                                               "password": "secret"}},
             "wanPortIpv6Setting": {"enable": True, "protoType": 2}},
            {"portUuid": "wan2", "portId": "wan2", "portName": "WAN2", "portDescription": "LTE backup",
             "wanPortIpv4Setting": {"protoType": 1, "vlanId": 0}, "wanPortIpv6Setting": {"enable": False}},
        ]},
        "wan-status": {GW: [
            {"name": "WAN1", "mode": 0, "status": 1, "internetState": 1, "ip": "198.51.100.23", "proto": "PPPoE",
             "speed": 3, "isp": "Example Fibre", "wanPortIpv4Config": {"ip": "198.51.100.23", "gateway": "198.51.100.1",
                                                                       "netmask": "255.255.255.255",
                                                                       "priDns": "198.51.100.53"}},
            {"name": "WAN2", "mode": 0, "status": 0, "internetState": 0},
        ]},
        "vpn": [
            {"id": "vpn-office", "name": "Office tunnel", "status": True, "siteVpnType": 1, "remoteIp": "203.0.113.10",
             "networkList": ["net-server"], "remoteSubnet": [{"ip": "10.50.0.0", "mask": 16}],
             "preSharedKey": "do-not-store"},
        ],
        "site-to-site-vpns": None,
        "switches": {SW1: ov1, SW2: ov2},
        "poe": poe1 + poe2,
    }


def _office_site() -> dict[str, Any]:
    return {
        "site": {"siteId": SITE2_ID, "name": "Holiday Home", "region": "Germany", "timeZone": "Europe/Berlin",
                 "scenario": "Home", "type": 0},
        "devices": [{"mac": "40-ED-00-00-09-01", "name": "Holiday Router ER605", "type": "gateway",
                     "model": "ER605 v2.0", "ip": "192.168.1.1", "status": 1, "firmwareVersion": "2.2.3",
                     "uptime": "3day(s)"}],
        "clients": [], "lan-networks": [{"id": "hh-lan", "name": "LAN", "purpose": 1, "vlan": 1,
                                          "gatewaySubnet": "192.168.1.1/24",
                                          "dhcpSettingsVO": {"enable": True, "ipaddrStart": "192.168.1.100",
                                                             "ipaddrEnd": "192.168.1.199", "dhcpns": "auto"}}],
        "lan-profiles": [], "wlans": [], "ssids": {}, "osg-acls": [], "osw-acls": [], "eap-acls": [], "groups": [],
        "port-forwardings": [], "one-to-one-nat": [], "static-routings": [], "dhcp": [], "internet": None,
        "wan-status": {}, "vpn": [], "site-to-site-vpns": [], "switches": {}, "poe": [],
    }


def _ok(result: Any) -> httpx.Response:
    return httpx.Response(200, json={"errorCode": 0, "msg": "Success.", "result": result})


def _paged(items: list, request: httpx.Request) -> httpx.Response:
    page = int(request.url.params.get("page", 1))
    size = int(request.url.params.get("pageSize", 100))
    chunk = items[(page - 1) * size: page * size]
    return _ok({"totalRows": len(items), "currentPage": page, "currentSize": size, "data": chunk})


class DemoController:
    """In-memory simulated controller. ``fail_paths`` lets tests inject endpoint failures."""

    def __init__(self, revision: int = 0, fail_paths: tuple[str, ...] = (), client_id: str = "demo",
                 client_secret: str = "demo", pre_60: bool = False):
        self.revision = revision
        self.fail_paths = fail_paths
        self.client_id = client_id
        self.client_secret = client_secret
        self.pre_60 = pre_60
        self.sites = {SITE_ID: _site_data(revision), SITE2_ID: _office_site()}
        self.requests: list[tuple[str, str]] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:  # noqa: C901 - routing table
        path = request.url.path
        self.requests.append((request.method, path))
        if any(f in path for f in self.fail_paths):
            return httpx.Response(500, json={"errorCode": -1, "msg": "Simulated failure"})
        if path == "/api/info":
            return _ok({"omadacId": OMADAC_ID, "controllerVer": "5.15.20.20", "apiVer": "3", "configured": True})
        if path == "/openapi/authorize/token":
            body = json.loads(request.content or b"{}")
            if request.method != "POST" or request.url.params.get("grant_type") != "client_credentials":
                return _ok(None) if False else httpx.Response(200, json={"errorCode": -44111, "msg": "Invalid grant"})
            if body.get("client_id") != self.client_id or body.get("client_secret") != self.client_secret:
                return httpx.Response(200, json={"errorCode": -44106, "msg": "Invalid client credentials"})
            return _ok({"accessToken": "AT-demo-token", "tokenType": "bearer", "expiresIn": 7200,
                        "refreshToken": "RT-demo"})
        if request.method != "GET":
            return httpx.Response(405, json={"errorCode": -1, "msg": "read-only demo"})
        if request.headers.get("Authorization") != "AccessToken=AT-demo-token":
            return httpx.Response(200, json={"errorCode": -44113, "msg": "Invalid access token"})
        prefix = f"/openapi/v1/{OMADAC_ID}"
        if not path.startswith(prefix):
            return httpx.Response(404)
        sub = path[len(prefix):]
        if sub == "/system/setting/controller-status":
            return _ok({"name": "Omada Controller (Demo)", "controllerVersion": "5.15.20.20",
                        "firmwareVersion": None, "model": "OC200", "controllerType": 10,
                        "macAddress": "40-ED-00-00-FF-01", "upTime": 1_234_567, "timeZone": "Europe/Berlin",
                        "deviceCapacity": {"adoptedApNum": 4, "adoptedOsgNum": 1, "adoptedOswNum": 2}})
        if sub == "/sites":
            return _paged([s["site"] for s in self.sites.values()], request)
        m = re.match(r"^/sites/([^/]+)(/.*)$", sub)
        if not m or m.group(1) not in self.sites:
            return httpx.Response(200, json={"errorCode": -1505, "msg": "No permission for site"})
        s, rest = self.sites[m.group(1)], m.group(2)
        simple_paged = {
            "/devices": "devices", "/clients": "clients", "/lan-networks": "lan-networks",
            "/lan-profiles": "lan-profiles", "/acls/osg-acls": "osg-acls", "/acls/osw-acls": "osw-acls",
            "/acls/eap-acls": "eap-acls", "/nat/port-forwardings": "port-forwardings",
            "/nat/one-to-one-nat": "one-to-one-nat", "/routing/static-routings": "static-routings",
            "/setting/service/dhcp": "dhcp", "/vpn": "vpn",
        }
        if rest in simple_paged:
            return _paged(s[simple_paged[rest]], request)
        if rest == "/profiles/groups":
            return _ok(s["groups"])
        if rest == "/wireless-network/wlans":
            return _ok(s["wlans"])
        if rest == "/internet":
            return _ok(s["internet"])
        if rest == "/vpn/site-to-site-vpns":
            return _ok(s["site-to-site-vpns"]) if s["site-to-site-vpns"] is not None else httpx.Response(
                200, json={"errorCode": -1600, "msg": "Unsupported request path."})
        if rest in ("/switches/ports/overview", "/switches/ports/poe-info"):
            if self.pre_60:
                return httpx.Response(200, json={"errorCode": -1600, "msg": "Unsupported request path."})
            if rest.endswith("overview"):
                return _paged([p for ports in s["switches"].values() for p in ports], request)
            return _paged(s["poe"], request)
        m2 = re.match(r"^/wireless-network/wlans/([^/]+)/ssids(?:/([^/]+))?$", rest)
        if m2:
            ssids = s["ssids"].get(m2.group(1), [])
            if m2.group(2):
                found = next((x for x in ssids if x["id"] == m2.group(2)), None)
                return _ok(found) if found else httpx.Response(404)
            summary = [{k: v for k, v in x.items() if k in ("id", "name", "band", "broadcast", "security",
                                                              "guestNetEnable", "vlanEnable", "vlanId")} for x in ssids]
            return _paged(summary, request)
        m3 = re.match(r"^/gateways/([^/]+)/wan-status$", rest)
        if m3:
            return _ok(s["wan-status"].get(m3.group(1), []))
        m4 = re.match(r"^/switches/([^/]+)$", rest)
        if m4 and m4.group(1) in s["switches"]:
            dev = next(d for d in s["devices"] if d["mac"] == m4.group(1))
            return _ok({"mac": dev["mac"], "model": dev["model"], "ip": dev["ip"],
                        "firmwareVersion": dev["firmwareVersion"],
                        "portList": [{"port": p["port"], "name": p["portName"], "status": 1, "poeMode": p["poe"],
                                      "profileId": p["profileId"], "profileName": p["profileName"], "lagPort": False}
                                     for p in s["switches"][m4.group(1)]]})
        return httpx.Response(200, json={"errorCode": -1600, "msg": "Unsupported request path."})
