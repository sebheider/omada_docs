import type { AclSide } from '../api/types';

export function describeSide(side: AclSide | null | undefined): string {
  if (!side) return 'Unknown';
  const type = side.type ?? '';
  let text: string;
  if (type === 'any' || (!side.refs?.length && !type)) {
    text = 'Any';
  } else if (side.refs && side.refs.length) {
    text = side.refs.map((r) => r.name || r.id || '?').join(', ');
  } else {
    text = type ? type.replace(/_/g, ' ') : 'Unknown';
  }
  if (side.negate) text = `NOT ${text}`;
  if (side.ports && side.ports.length) text += ` : ${side.ports.join(', ')}`;
  return text;
}

export const ACL_TYPE_LABELS: Record<string, string> = {
  gateway: 'Gateway ACL',
  switch: 'Switch ACL',
  eap: 'EAP (Access Point) ACL',
};
