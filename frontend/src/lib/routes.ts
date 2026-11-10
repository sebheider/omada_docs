const enc = encodeURIComponent;

/** Map an object type/key to the frontend route of its detail page. */
export function objectPath(type: string, key: string | number, extra?: { deviceType?: string | null }): string | null {
  const k = enc(String(key));
  switch (type) {
    case 'device':
      return extra?.deviceType === 'switch' ? `/switches/${k}` : `/devices/${k}`;
    case 'switch':
      return `/switches/${k}`;
    case 'network':
      return `/networks/${k}`;
    case 'wan':
      return `/networks/wan/${k}`;
    case 'route':
      return `/networks/routes/${k}`;
    case 'vpn':
      return `/networks/vpn/${k}`;
    case 'port_profile':
      return `/switches/profiles/${k}`;
    case 'switch_port':
      return `/ports/${k}`;
    case 'wlan':
      return `/wlans/${k}`;
    case 'client':
      return `/clients/${k}`;
    case 'acl_rule':
      return `/acl/rules/${k}`;
    case 'ip_group':
      return `/acl/groups/${k}`;
    case 'nat_rule':
      return `/nat/${k}`;
    case 'document':
      return `/documentation/${k}`;
    case 'site':
      return `/sites/${k}`;
    case 'controller':
      return `/controller`;
    default:
      return null;
  }
}
