export function fmtDate(v: string | number | null | undefined, withSeconds = false): string {
  if (v === null || v === undefined || v === '') return '—';
  const d = typeof v === 'number' ? new Date(v > 1e12 ? v : v * 1000) : new Date(v);
  if (Number.isNaN(d.getTime())) return String(v);
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    ...(withSeconds ? { second: '2-digit' } : {}),
  });
}

export function fmtRelative(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === '') return '—';
  const d = typeof v === 'number' ? new Date(v > 1e12 ? v : v * 1000) : new Date(v);
  const t = d.getTime();
  if (Number.isNaN(t)) return String(v);
  const diff = (Date.now() - t) / 1000;
  const abs = Math.abs(diff);
  const fmt = (n: number, unit: string) => {
    const r = Math.round(n);
    const s = `${r} ${unit}${r === 1 ? '' : 's'}`;
    return diff >= 0 ? `${s} ago` : `in ${s}`;
  };
  if (abs < 45) return diff >= 0 ? 'just now' : 'in a few seconds';
  if (abs < 3600) return fmt(abs / 60, 'minute');
  if (abs < 86400) return fmt(abs / 3600, 'hour');
  if (abs < 86400 * 30) return fmt(abs / 86400, 'day');
  return fmtDate(v);
}

export function fmtDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—';
  if (ms < 1000) return `${ms} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)} s`;
  return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
}

export function fmtSeconds(sec: number | null | undefined): string {
  if (sec === null || sec === undefined) return '—';
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  return [d ? `${d}d` : '', h ? `${h}h` : '', `${m}m`].filter(Boolean).join(' ');
}

export function fmtBytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

/** Humanise snake_case identifiers ("switch_port" → "Switch port"). */
export function humanize(s: string | null | undefined): string {
  if (!s) return '';
  const t = s
    .replace(/[_-]+/g, ' ')
    .trim()
    .replace(/\b(ip|ssid|vlan|poe|mac|dhcp|dns|lan|wan|acl|nat|vpn|ap|eap|ipsec|lldp|ntp|cidr)(s?)\b/gi, (_w, a: string, s: string) =>
      a.toUpperCase() + s.toLowerCase(),
    );
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export function isEmpty(v: unknown): boolean {
  return (
    v === null ||
    v === undefined ||
    v === '' ||
    (Array.isArray(v) && v.length === 0) ||
    (typeof v === 'object' && !Array.isArray(v) && Object.keys(v as object).length === 0)
  );
}

/** Render any JSON value as a short human readable string. */
export function fmtValue(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (Array.isArray(v)) {
    if (v.length === 0) return '—';
    return v.map((x) => (typeof x === 'object' && x !== null ? fmtObject(x as Record<string, unknown>) : String(x))).join(', ');
  }
  if (typeof v === 'object') return fmtObject(v as Record<string, unknown>);
  return String(v);
}

function fmtObject(o: Record<string, unknown>): string {
  if ('name' in o && o.name) return String(o.name);
  const parts = Object.entries(o)
    .filter(([, x]) => !isEmpty(x))
    .map(([k, x]) => `${humanize(k)}: ${typeof x === 'object' ? JSON.stringify(x) : String(x)}`);
  return parts.length ? parts.join('; ') : '—';
}

export function str(v: unknown): string {
  return v === null || v === undefined ? '' : String(v);
}

export const KIND_LABELS: Record<string, string> = {
  controller: 'Controller',
  site: 'Site',
  device: 'Device',
  network: 'Network / VLAN',
  wan: 'WAN',
  wlan: 'WLAN',
  switch_port: 'Switch port',
  client: 'Client',
  acl_rule: 'ACL rule',
  nat_rule: 'NAT rule',
  route: 'Static route',
  vpn: 'VPN',
  ip_group: 'IP / port group',
  port_profile: 'Port profile',
  document: 'Document',
  connection: 'Connection',
  location: 'Location',
};

export const kindLabel = (k: string) => KIND_LABELS[k] ?? humanize(k);
