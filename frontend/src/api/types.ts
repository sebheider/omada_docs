export type Role = 'admin' | 'viewer';

export interface User {
  id: number;
  username: string;
  role: Role;
  auth_source: string;
  is_active: boolean;
  created_at: string | null;
  last_login: string | null;
}

export interface AuthState {
  setup_required: boolean;
  user: User | null;
  csrf_token: string | null;
  demo_mode: boolean;
  version: string;
  auth_mode: string | null;
}

export interface Meta {
  source: string;
  collected_at: string | null;
  updated_at: string | null;
  site_id: string | null;
  controller_id: string | null;
  validation_status: string | null;
}

export interface ManualDescription {
  id: number;
  object_type: string;
  object_key: string;
  site_id: string | null;
  display_name: string | null;
  description: string | null;
  location: string | null;
  responsible: string | null;
  notes: string | null;
  tags: string[];
  created_at: string | null;
  updated_at: string | null;
  updated_by: string | null;
  source: 'manual';
}

export interface BaseEntity {
  kind: string;
  key: string;
  site_id: string | null;
  name: string | null;
  controller_id?: string | null;
  validation_status?: string | null;
  _meta?: Meta;
  manual?: ManualDescription | null;
  [k: string]: unknown;
}

export interface Device extends BaseEntity {
  mac?: string | null;
  type?: string | null;
  model?: string | null;
  model_name?: string | null;
  ip?: string | null;
  serial?: string | null;
  firmware?: string | null;
  status?: string | null;
  uptime?: string | null;
  uptime_seconds?: number | null;
  cpu_percent?: number | null;
  memory_percent?: number | null;
  uplink_device_mac?: string | null;
  uplink_device_name?: string | null;
  uplink_port?: string | null;
  uplink_speed?: string | null;
  client_count?: number | null;
}

export interface Dhcp {
  enabled?: boolean | null;
  range_start?: string | null;
  range_end?: string | null;
  lease_minutes?: number | null;
  dns_mode?: string | null;
  dns_servers?: string[] | null;
  gateway?: string | null;
  reservations?: { mac?: string; ip?: string; name?: string; description?: string | null; [k: string]: unknown }[] | null;
}

export interface Network extends BaseEntity {
  purpose?: string | null;
  vlan_id?: number | null;
  vlans?: unknown;
  subnet?: string | null;
  gateway?: string | null;
  netmask?: string | null;
  domain?: string | null;
  dhcp?: Dhcp | null;
  guest?: boolean | null;
  application?: string | null;
}

export interface Poe {
  supported?: boolean | null;
  enabled?: boolean | null;
  active?: boolean | null;
  power_w?: number | null;
  pd_class?: string | null;
}

export interface ConnectedRef {
  mac?: string | null;
  name?: string | null;
  type?: string | null;
  source?: string | null;
  relation?: string | null;
}

export interface SwitchPort extends BaseEntity {
  switch_mac?: string;
  switch_name?: string | null;
  port?: number;
  port_type?: string | null;
  link_status?: string | null;
  speed?: string | null;
  duplex?: string | null;
  poe?: Poe | null;
  profile_id?: string | null;
  profile_name?: string | null;
  network_mode?: string | null;
  native_network_id?: string | null;
  native_network?: string | null;
  native_vlan_id?: number | null;
  tagged_networks?: string[] | null;
  untagged_networks?: string[] | null;
  lag?: boolean | null;
  link_role?: string | null;
  connected?: ConnectedRef[] | null;
  warning?: string | null;
}

export interface Wlan extends BaseEntity {
  ssid?: string | null;
  enabled?: boolean | null;
  broadcast?: boolean | null;
  bands?: string[] | null;
  security?: string | null;
  security_version?: string | null;
  guest?: boolean | null;
  vlan_enabled?: boolean | null;
  vlan_id?: number | null;
  network_id?: string | null;
  network_name?: string | null;
  ap_assignment?: string | null;
  ap_group_ids?: string[] | null;
  client_count?: number | null;
  wlan_group?: string | null;
}

export interface Client extends BaseEntity {
  mac?: string | null;
  ip?: string | null;
  hostname?: string | null;
  vendor?: string | null;
  vlan_id?: number | null;
  network_name?: string | null;
  network_id?: string | null;
  wireless?: boolean | null;
  guest?: boolean | null;
  connection_type?: string | null;
  connected_device_mac?: string | null;
  connected_device_name?: string | null;
  connected_device_type?: string | null;
  port?: number | null;
  ssid?: string | null;
  radio?: string | null;
  active?: boolean | null;
  signal_percent?: number | null;
  last_seen?: number | string | null;
}

export interface AclRef {
  id?: string | null;
  name?: string | null;
  resolved?: boolean;
}

export interface AclSide {
  type?: string | null;
  negate?: boolean | null;
  refs?: AclRef[] | null;
  ports?: string[] | null;
}

export interface AclAnalysis {
  key: string;
  technical: string;
  explanation: string;
  confidence: 'high' | 'medium' | 'low';
  confidence_reasons: string[];
  shadowed_by: string | string[] | null;
  related_rules: string[];
  data_source: string;
}

export interface AclRule extends BaseEntity {
  acl_type?: string;
  index?: number | null;
  enabled?: boolean | null;
  action?: string | null;
  protocols?: string[] | null;
  direction?: string | null;
  directions?: string[] | null;
  source?: AclSide | null;
  destination?: AclSide | null;
  description?: string | null;
  analysis?: AclAnalysis | null;
}

export interface NatRule extends BaseEntity {
  nat_type?: string | null;
  enabled?: boolean | null;
  protocol?: string | null;
  external_port?: string | null;
  internal_ip?: string | null;
  internal_port?: string | null;
  source?: string | null;
  source_addresses?: string[] | null;
  dmz?: boolean | null;
  wan_port_ids?: string[] | null;
}

export interface EntityList<T extends BaseEntity = BaseEntity> {
  kind: string;
  site_id: string | null;
  items: T[];
}

export interface RelatedRef {
  object_type: string;
  object_key: string;
  name: string | null;
  detail: string | null;
}

export interface Relationship {
  id: number;
  source_type: string;
  source_key: string;
  target_type: string;
  target_key: string;
  relation: string;
  description: string | null;
  created_at: string | null;
  created_by: string | null;
  source: 'manual';
}

export interface Change {
  id?: number;
  ts?: string;
  kind?: 'config' | 'manual';
  sync_id?: number | null;
  site_id: string | null;
  object_type: string;
  object_key: string;
  object_name: string | null;
  change_type: 'added' | 'removed' | 'modified';
  field: string | null;
  before: string | null;
  after: string | null;
  username?: string | null;
}

export interface EntityDetail<T extends BaseEntity = BaseEntity> {
  kind: string;
  entity: T;
  manual: ManualDescription | null;
  relationships: Relationship[];
  related: Record<string, RelatedRef[]>;
  analysis: AclAnalysis | null;
  changes: Change[];
}

export interface SyncRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: 'running' | 'success' | 'partial' | 'failed';
  trigger: string;
  duration_ms: number | null;
  new_objects: number | null;
  changed_objects: number | null;
  removed_objects: number | null;
  total_objects: number | null;
  error: string | null;
  snapshot_id: number | null;
}

export interface SyncEndpoint {
  endpoint: string;
  path: string;
  site_id: string | null;
  status: 'ok' | 'error' | 'unsupported' | string;
  count: number | null;
  error: string | null;
  at?: string;
  [k: string]: unknown;
}

export interface SyncRunDetail extends SyncRun {
  details: {
    endpoints?: SyncEndpoint[];
    request_count?: number;
    carried_forward?: number;
    unsupported?: string[];
    controller_version?: string | null;
    first_sync?: boolean;
    [k: string]: unknown;
  } | null;
}

export interface SyncStatus {
  running: boolean;
  last: SyncRun | null;
  last_success: SyncRun | null;
  last_failure: SyncRun | null;
  total_runs: number;
  next_run: string | null;
  interval: string;
}

export interface Site extends BaseEntity {
  region?: string | null;
  timezone?: string | null;
  scenario?: string | null;
  primary?: boolean | null;
}

export interface Dashboard {
  site_id: string | null;
  controller: BaseEntity | null;
  configured: boolean;
  demo_mode: boolean;
  version: string;
  sync: SyncStatus;
  counts: Record<string, number>;
  devices_by_type: Record<string, { total: number; online: number }>;
  devices_offline: { key: string; name: string | null; type: string | null }[];
  clients: { total: number; wireless: number; wired: number };
  acl: { total: number; low_confidence: number; shadowed: number };
  changes_7d: { config: number; manual: number };
  recent_changes: Change[];
  quality: { total: number; sections: Record<string, number> };
  syncs_total: number;
}

export interface Segment {
  id: string;
  type: string;
  name: string;
  vlan_id: number | null;
  guest: boolean;
  cidrs: string[];
  ref_id: string | null;
  has_rules?: boolean;
}

export type CellStatus = 'allowed' | 'blocked' | 'restricted' | 'unknown';

export interface MatrixCell {
  source: string;
  destination: string;
  status: CellStatus;
  computed_status: string;
  confidence: string;
  basis: 'rule' | 'default' | 'derived';
  rules: string[];
  notes: string[];
}

export interface AclGraphEdge {
  id: string;
  source: string;
  target: string;
  rules: string[];
  disabled_rules: string[];
  status: CellStatus;
  dashed: boolean;
  confidence: string;
}

export interface IpGroup extends BaseEntity {
  type?: string | null;
  entries?: { ip?: string; description?: string | null }[] | null;
  ports?: string[] | null;
  macs?: unknown[] | null;
  domains?: unknown[] | null;
  countries?: unknown[] | null;
  built_in?: boolean | null;
  description?: string | null;
}

export interface AclData {
  site_id: string | null;
  rules: AclRule[];
  matrix: { segments: Segment[]; cells: MatrixCell[] };
  graph: { nodes: Segment[]; edges: AclGraphEdge[] };
  ip_groups: IpGroup[];
}

export interface TopoNode {
  id: string;
  type: string;
  label: string;
  data: Record<string, unknown>;
}

export interface TopoEdge {
  id: string;
  source: string;
  target: string;
  evidence: 'api' | 'lldp' | 'manual' | 'derived' | string;
  label: string | null;
  data: Record<string, unknown> | null;
}

export interface SegmentationEntry {
  id: string;
  name: string;
  vlan_id: number | null;
  subnet: string | null;
  gateway: string | null;
  guest: boolean;
  ssids: string[];
  client_count: number;
  description: string | null;
}

export interface Topology {
  site_id: string | null;
  nodes: TopoNode[];
  edges: TopoEdge[];
  unresolved: { name?: string; reason?: string; [k: string]: unknown }[];
  notes: string[];
  segmentation: SegmentationEntry[];
}

export interface SearchHit {
  category: string;
  object_type: string;
  object_key: string;
  site_id: string | null;
  title: string;
  subtitle: string | null;
  reason: string | null;
}

export interface SearchResult {
  query: string;
  total: number;
  groups: { category: string; items: SearchHit[] }[];
}

export interface QualityItem {
  object_type: string;
  object_key: string;
  name: string | null;
  detail: string | null;
  site_id: string | null;
}

export interface QualityReport {
  site_id: string | null;
  summary: Record<string, number>;
  sections: Record<string, QualityItem[]>;
}

export interface ManualMeta {
  object_types: string[];
  document_categories: string[];
  relations: string[];
  attachment_types: string[];
}

export interface Attachment {
  id: number;
  document_id: number;
  filename: string;
  content_type: string;
  size: number;
  sha256: string;
  uploaded_at: string | null;
  uploaded_by: string | null;
}

export interface ManualDocument {
  id: number;
  title: string;
  category: string;
  tags: string[];
  created_at: string | null;
  updated_at: string | null;
  created_by: string | null;
  updated_by: string | null;
  body?: string;
  relationships?: Relationship[];
  attachments?: Attachment[];
}

export interface Snapshot {
  id: number;
  created_at: string;
  source: string;
  label: string | null;
  controller_version: string | null;
  checksum: string;
  object_count: number;
}

export interface SnapshotCompare {
  a: Snapshot;
  b: Snapshot;
  changes: Change[];
  summary: { added: number; removed: number; modified: number };
}

export interface ControllerSettings {
  host: string;
  port: number;
  scheme: 'https' | 'http';
  client_id: string;
  client_secret_set: boolean;
  omadac_id: string;
  api_version: 'v1';
  verify_ssl: boolean;
  site_ids: string[];
  sync_interval: string;
  request_timeout: number;
  max_requests_per_second: number;
  snapshot_retention: number;
  configured: boolean;
  sync_intervals?: string[];
  demo_mode?: boolean;
  next_run: string | null;
}

export interface ExportOptions {
  formats: string[];
  chapters: Record<string, string>;
  default_chapters: string[];
  csv_tables: string[];
}

export interface BackupConflict {
  object_type: string;
  site_id: string | null;
  object_key: string;
  object_name: string | null;
  field: string;
  api_value: unknown;
  backup_value: unknown;
  api_source: string;
  api_collected_at: string | null;
}

export interface BackupObjectRef {
  object_type: string;
  site_id: string | null;
  object_key: string;
  object_name: string | null;
}

export interface BackupImport {
  id: number;
  imported_at: string;
  filename: string;
  sha256: string;
  detected_format: string | null;
  controller_version: string | null;
  backup_version: string | null;
  status: 'imported' | 'rejected' | string;
  unsupported: unknown[];
  errors: unknown[];
  snapshot_id: number | null;
  imported_by: string | null;
  counts: Record<string, number> | null;
  comparison_counts: { only_in_backup: number; only_in_api: number; conflicts: number } | null;
  comparison?: {
    only_in_backup: BackupObjectRef[];
    only_in_api: BackupObjectRef[];
    conflicts: BackupConflict[];
    counts: Record<string, number>;
    api_has_data?: boolean;
  } | null;
}

export interface AuditEntry {
  id: number;
  ts: string;
  username: string | null;
  action: string;
  object_type: string | null;
  object_key: string | null;
  details: unknown;
  ip: string | null;
}

export interface Paged<T> {
  total: number;
  items: T[];
}
