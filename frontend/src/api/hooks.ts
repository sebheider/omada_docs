import { useEffect, useRef } from 'react';
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, get } from './client';
import type {
  AclData,
  BaseEntity,
  Dashboard,
  EntityDetail,
  EntityList,
  ManualMeta,
  SyncStatus,
  Topology,
} from './types';
import { useSite } from '../context/SiteContext';

export function useEntities<T extends BaseEntity = BaseEntity>(kind: string, opts: { siteScoped?: boolean } = {}) {
  const { siteId, ready } = useSite();
  const scoped = opts.siteScoped ?? !['controller', 'site'].includes(kind);
  return useQuery({
    queryKey: ['entities', kind, scoped ? siteId : null],
    queryFn: ({ signal }) => get<EntityList<T>>(`entities/${kind}`, scoped ? { site_id: siteId } : undefined, signal),
    enabled: ready,
  });
}

/** Load an entity detail; tries the selected site first and falls back to any site. */
export function useEntity<T extends BaseEntity = BaseEntity>(kind: string, key: string | undefined) {
  const { siteId, ready } = useSite();
  return useQuery({
    queryKey: ['entity', kind, key, siteId],
    queryFn: async ({ signal }) => {
      const path = `entities/${kind}/${encodeURIComponent(key ?? '')}`;
      if (siteId && !['controller', 'site'].includes(kind)) {
        try {
          return await get<EntityDetail<T>>(path, { site_id: siteId }, signal);
        } catch (e) {
          if (!(e instanceof ApiError && e.status === 404)) throw e;
        }
      }
      return get<EntityDetail<T>>(path, undefined, signal);
    },
    enabled: ready && !!key,
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 2,
  });
}

export function useDashboard() {
  const { siteId, ready } = useSite();
  return useQuery({
    queryKey: ['dashboard', siteId],
    queryFn: ({ signal }) => get<Dashboard>('dashboard', { site_id: siteId }, signal),
    enabled: ready,
  });
}

export function useAcl() {
  const { siteId, ready } = useSite();
  return useQuery({
    queryKey: ['acl', siteId],
    queryFn: ({ signal }) => get<AclData>('acl', { site_id: siteId }, signal),
    enabled: ready,
  });
}

export function useTopology(clients: 'none' | 'important' | 'all') {
  const { siteId, ready } = useSite();
  return useQuery({
    queryKey: ['topology', siteId, clients],
    queryFn: ({ signal }) => get<Topology>('topology', { site_id: siteId, clients }, signal),
    enabled: ready,
    placeholderData: keepPreviousData,
  });
}

export function useManualMeta() {
  return useQuery({
    queryKey: ['manual-meta'],
    queryFn: () => get<ManualMeta>('manual/meta'),
    staleTime: Infinity,
  });
}

/**
 * Sync status; polls every 2 s while a synchronisation is running and invalidates all data queries
 * once it has finished.
 */
export function useSyncStatus() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['sync-status'],
    queryFn: () => get<SyncStatus>('sync/status'),
    refetchInterval: (query) => (query.state.data?.running ? 2000 : 60_000),
  });
  const wasRunning = useRef(false);
  const running = q.data?.running ?? false;
  useEffect(() => {
    if (wasRunning.current && !running) {
      void qc.invalidateQueries({ predicate: (query) => !['auth-state', 'sync-status', 'manual-meta'].includes(String(query.queryKey[0])) });
    }
    wasRunning.current = running;
  }, [running, qc]);
  return q;
}
