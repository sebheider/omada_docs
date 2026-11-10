"""Collects raw data from the controller using only registered GET endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .client import OmadaClient, OmadaError, OmadaUnsupportedError
from .endpoints import BY_NAME

log = logging.getLogger(__name__)


class Collector:
    def __init__(self, client: OmadaClient, site_ids: list[str] | None = None):
        self.client = client
        self.site_filter = set(site_ids or [])
        self.results: list[dict[str, Any]] = []

    async def _call(self, name: str, site: str | None = None, **path_args: str) -> Any:
        ep = BY_NAME[name]
        path = ep.path.format(siteId=site or "", **path_args)
        started = datetime.now(timezone.utc)
        entry = {"endpoint": name, "path": ep.path, "site_id": site, "status": "ok", "count": 0, "error": None,
                 "at": started.isoformat()}
        try:
            if ep.mode == "paged":
                data = await self.client.get_all(path)
            else:
                data = await self.client.get(path)
            entry["count"] = len(data) if isinstance(data, list) else (1 if data else 0)
            return data
        except OmadaUnsupportedError as exc:
            entry.update(status="unsupported", error=str(exc))
            return None
        except OmadaError as exc:
            entry.update(status="error", error=str(exc))
            if not ep.optional:
                log.warning("Omada endpoint %s failed: %s", name, exc)
            return None
        finally:
            if path_args:
                entry["args"] = path_args
            self.results.append(entry)

    async def collect(self) -> dict[str, Any]:
        info = await self.client.get_info()
        await self.client.authenticate()
        raw: dict[str, Any] = {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "controller_info": info.raw,
            "controller_status": await self._call("controller_status"),
            "sites": [],
        }
        sites = await self._call("sites") or []
        if self.site_filter:
            sites = [s for s in sites if s.get("siteId") in self.site_filter]
        for site in sites:
            raw["sites"].append(await self._collect_site(site))
        raw["endpoint_results"] = self.results
        raw["request_count"] = self.client.request_count
        return raw

    async def _collect_site(self, site: dict[str, Any]) -> dict[str, Any]:
        sid = site["siteId"]
        out: dict[str, Any] = {"site": site}
        for name in ("devices", "clients", "lan_networks", "lan_profiles", "gateway_acls", "switch_acls",
                     "eap_acls", "groups", "port_forwardings", "one_to_one_nat", "static_routes",
                     "dhcp_reservations", "internet", "vpns", "site_to_site_vpns", "switch_ports", "switch_poe"):
            out[name] = await self._call(name, sid)

        wlan_groups = await self._call("wlan_groups", sid) or []
        out["wlan_groups"] = []
        for wg in wlan_groups:
            wlan_id = wg.get("id") or wg.get("wlanId")
            ssids = await self._call("ssids", sid, wlanId=wlan_id) or []
            details = []
            for ssid in ssids:
                ssid_id = ssid.get("id") or ssid.get("ssidId")
                detail = await self._call("ssid_detail", sid, wlanId=wlan_id, ssidId=ssid_id)
                details.append({"summary": ssid, "detail": detail})
            out["wlan_groups"].append({"group": wg, "ssids": details})

        devices = out.get("devices") or []
        out["wan_status"] = {}
        out["switch_detail"] = {}
        for dev in devices:
            mac = dev.get("mac")
            if not mac:
                continue
            if dev.get("type") == "gateway":
                out["wan_status"][mac] = await self._call("wan_status", sid, gatewayMac=mac)
            elif dev.get("type") == "switch":
                out["switch_detail"][mac] = await self._call("switch_detail", sid, switchMac=mac)
        return out
