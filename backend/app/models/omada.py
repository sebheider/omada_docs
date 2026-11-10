"""Technical data collected from the Omada controller (or imported backups).

Every technical table shares the same metadata columns (data source, collection timestamp,
site, controller object id, validation status). The normalised object itself is stored in
``data`` so new API fields can be added without schema migrations. These tables are fully
replaced on every successful synchronisation and are never referenced by manual data.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class OmadaRecord:
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[str | None] = mapped_column(String(64), index=True)
    object_key: Mapped[str] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(255))
    controller_id: Mapped[str | None] = mapped_column(String(128))
    source: Mapped[str] = mapped_column(String(16), default="api")  # api | backup | demo | derived
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    validation_status: Mapped[str] = mapped_column(String(16), default="valid")  # valid|partial|invalid
    data: Mapped[dict] = mapped_column(JSON)


def _table(class_name: str, table: str, kind: str):
    cls = type(
        class_name,
        (OmadaRecord, Base),
        {
            "__tablename__": table,
            "__table_args__": (Index(f"ix_{table}_site_key", "site_id", "object_key", unique=True),),
            "kind": kind,
        },
    )
    return cls


OmadaController = _table("OmadaController", "omada_controller", "controller")
OmadaSite = _table("OmadaSite", "omada_sites", "site")
OmadaDevice = _table("OmadaDevice", "omada_devices", "device")
OmadaNetwork = _table("OmadaNetwork", "omada_networks", "network")
OmadaWan = _table("OmadaWan", "omada_wans", "wan")
OmadaWlan = _table("OmadaWlan", "omada_wlans", "wlan")
OmadaSwitchPort = _table("OmadaSwitchPort", "omada_switch_ports", "switch_port")
OmadaClient = _table("OmadaClient", "omada_clients", "client")
OmadaAclRule = _table("OmadaAclRule", "omada_acl_rules", "acl_rule")
OmadaNatRule = _table("OmadaNatRule", "omada_nat_rules", "nat_rule")
OmadaRoute = _table("OmadaRoute", "omada_routes", "route")
OmadaVpn = _table("OmadaVpn", "omada_vpns", "vpn")
OmadaIpGroup = _table("OmadaIpGroup", "omada_ip_groups", "ip_group")
OmadaPortProfile = _table("OmadaPortProfile", "omada_port_profiles", "port_profile")

#: entity kind -> ORM model
ENTITY_MODELS = {
    m.kind: m
    for m in (
        OmadaController,
        OmadaSite,
        OmadaDevice,
        OmadaNetwork,
        OmadaWan,
        OmadaWlan,
        OmadaSwitchPort,
        OmadaClient,
        OmadaAclRule,
        OmadaNatRule,
        OmadaRoute,
        OmadaVpn,
        OmadaIpGroup,
        OmadaPortProfile,
    )
}
