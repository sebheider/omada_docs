import { useEffect, useState, type FormEvent } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  ArrowLeftRight,
  BookOpen,
  Cable,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  Network,
  RefreshCw,
  Router,
  Search,
  Server,
  Settings,
  Shield,
  Sun,
  Users,
  Waypoints,
  Wifi,
  X,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { useSite } from '../context/SiteContext';
import { useSyncStatus } from '../api/hooks';
import { Badge, cx, Spinner } from './ui';

export const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/topology', label: 'Network Overview', icon: Waypoints },
  { to: '/devices', label: 'Devices', icon: Router },
  { to: '/switches', label: 'Switches and Ports', icon: Cable },
  { to: '/networks', label: 'VLANs and Networks', icon: Network },
  { to: '/wlans', label: 'WLAN', icon: Wifi },
  { to: '/acl', label: 'ACL / Firewall', icon: Shield },
  { to: '/nat', label: 'NAT / Port Forwarding', icon: ArrowLeftRight },
  { to: '/clients', label: 'Clients', icon: Users },
  { to: '/documentation', label: 'Documentation', icon: BookOpen },
  { to: '/search', label: 'Search', icon: Search },
  { to: '/changes', label: 'Change History', icon: History },
  { to: '/sync', label: 'Synchronization', icon: RefreshCw },
  { to: '/settings', label: 'Settings', icon: Settings },
];

function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { state } = useAuth();
  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-slate-900/40 lg:hidden" onClick={onClose} />}
      <aside
        className={cx(
          'fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-slate-800 bg-slate-900 text-slate-300 transition-transform lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex h-14 items-center gap-2 border-b border-slate-800 px-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-brand-600 text-white">
            <Server className="h-4 w-4" />
          </div>
          <div className="min-w-0 leading-tight">
            <div className="truncate text-sm font-semibold text-white">Omada Docs</div>
            <div className="truncate text-[11px] text-slate-400">Network Documentation</div>
          </div>
          <button className="ml-auto text-slate-400 hover:text-white lg:hidden" onClick={onClose} aria-label="Close menu">
            <X className="h-5 w-5" />
          </button>
        </div>
        <nav className="flex-1 overflow-y-auto px-2 py-3" aria-label="Main">
          <ul className="space-y-0.5">
            {NAV.map((n) => (
              <li key={n.to}>
                <NavLink
                  to={n.to}
                  end={n.end}
                  onClick={onClose}
                  className={({ isActive }) =>
                    cx(
                      'flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors',
                      isActive ? 'bg-brand-600/20 font-medium text-white ring-1 ring-inset ring-brand-500/40' : 'hover:bg-slate-800 hover:text-white',
                    )
                  }
                >
                  <n.icon className="h-4 w-4 shrink-0" />
                  {n.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="border-t border-slate-800 px-4 py-2 text-[11px] text-slate-500">Version {state?.version ?? '—'}</div>
      </aside>
    </>
  );
}

function SyncIndicator() {
  const { data } = useSyncStatus();
  const navigate = useNavigate();
  if (!data) return null;
  if (data.running)
    return (
      <button className="hidden sm:inline-flex" onClick={() => navigate('/sync')} title="Synchronization running">
        <Badge tone="blue">
          <RefreshCw className="h-3 w-3 animate-spin" /> Syncing…
        </Badge>
      </button>
    );
  const last = data.last;
  if (last && last.status !== 'success')
    return (
      <button className="hidden sm:inline-flex" onClick={() => navigate('/sync')} title={last.error ?? undefined}>
        <Badge tone={last.status === 'partial' ? 'amber' : 'red'}>Last sync {last.status}</Badge>
      </button>
    );
  return null;
}

function TopBar({ onMenu }: { onMenu: () => void }) {
  const { user, state, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const { sites, siteId, setSiteId } = useSite();
  const navigate = useNavigate();
  const location = useLocation();
  const [q, setQ] = useState('');

  useEffect(() => {
    if (location.pathname === '/search') setQ(new URLSearchParams(location.search).get('q') ?? '');
  }, [location]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (q.trim()) navigate(`/search?q=${encodeURIComponent(q.trim())}`);
  };

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-slate-200 bg-white/90 px-3 backdrop-blur dark:border-slate-800 dark:bg-slate-900/90 sm:px-4">
      <button className="btn-ghost p-1.5 lg:hidden" onClick={onMenu} aria-label="Open menu">
        <Menu className="h-5 w-5" />
      </button>
      <form onSubmit={submit} className="relative max-w-md flex-1" role="search">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input
          className="input pl-8"
          placeholder="Search devices, IPs, MACs, VLANs, rules…"
          aria-label="Global search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </form>
      <div className="ml-auto flex items-center gap-2">
        {state?.demo_mode && (
          <Badge tone="violet" title="Demo mode: generated example data, no controller is contacted">
            DEMO MODE
          </Badge>
        )}
        <SyncIndicator />
        {sites.length > 1 && (
          <select
            className="input hidden w-auto max-w-[12rem] sm:block"
            value={siteId ?? ''}
            onChange={(e) => setSiteId(e.target.value)}
            aria-label="Site"
            title="Site"
          >
            {sites.map((s) => (
              <option key={s.key} value={s.key}>
                {s.manual?.display_name || s.name || s.key}
              </option>
            ))}
          </select>
        )}
        <button className="btn-ghost p-1.5" onClick={toggle} aria-label="Toggle theme" title={theme === 'dark' ? 'Light theme' : 'Dark theme'}>
          {theme === 'dark' ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </button>
        <div className="hidden text-right leading-tight md:block">
          <div className="text-sm font-medium">{user?.username}</div>
          <div className="text-[11px] text-slate-500 dark:text-slate-400">{user?.role === 'admin' ? 'Administrator' : 'Read-only'}</div>
        </div>
        {state?.auth_mode !== 'proxy' && (
          <button className="btn-ghost p-1.5" onClick={() => void logout()} aria-label="Log out" title="Log out">
            <LogOut className="h-5 w-5" />
          </button>
        )}
      </div>
    </header>
  );
}

export function Layout() {
  const [open, setOpen] = useState(false);
  const { ready, sites, siteId, setSiteId } = useSite();
  return (
    <div className="min-h-screen">
      <Sidebar open={open} onClose={() => setOpen(false)} />
      <div className="lg:pl-60">
        <TopBar onMenu={() => setOpen(true)} />
        {sites.length > 1 && (
          <div className="border-b border-slate-200 bg-white px-3 py-2 dark:border-slate-800 dark:bg-slate-900 sm:hidden">
            <select className="input" value={siteId ?? ''} onChange={(e) => setSiteId(e.target.value)} aria-label="Site">
              {sites.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.manual?.display_name || s.name || s.key}
                </option>
              ))}
            </select>
          </div>
        )}
        <main className="mx-auto max-w-[1600px] p-3 sm:p-5">{ready ? <Outlet /> : <Spinner />}</main>
      </div>
    </div>
  );
}
