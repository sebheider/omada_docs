import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { get } from '../api/client';
import type { Site } from '../api/types';

const STORAGE_KEY = 'omada-docs-site';

interface SiteCtx {
  siteId: string | undefined;
  sites: Site[];
  setSiteId: (id: string) => void;
  currentSite: Site | undefined;
  ready: boolean;
}

const Ctx = createContext<SiteCtx | null>(null);

export function SiteProvider({ children }: { children: ReactNode }) {
  const q = useQuery({
    queryKey: ['sites'],
    queryFn: () => get<{ items: Site[]; default: string | null }>('sites'),
  });
  const [selected, setSelected] = useState<string | null>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch {
      return null;
    }
  });
  const sites = q.data?.items ?? [];
  const valid = selected && sites.some((s) => s.key === selected) ? selected : null;
  const siteId = valid ?? q.data?.default ?? undefined;

  useEffect(() => {
    if (q.data && selected && !valid) setSelected(null);
  }, [q.data, selected, valid]);

  const setSiteId = (id: string) => {
    setSelected(id);
    try {
      localStorage.setItem(STORAGE_KEY, id);
    } catch {
      /* ignore */
    }
  };

  return (
    <Ctx.Provider value={{ siteId, sites, setSiteId, currentSite: sites.find((s) => s.key === siteId), ready: !q.isLoading }}>
      {children}
    </Ctx.Provider>
  );
}

export function useSite(): SiteCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error('SiteProvider missing');
  return c;
}
