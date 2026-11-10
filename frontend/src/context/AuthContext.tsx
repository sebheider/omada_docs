import { createContext, useCallback, useContext, useEffect, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { get, onUnauthorized, post, setCsrfToken } from '../api/client';
import type { AuthState, User } from '../api/types';

interface AuthCtx {
  state: AuthState | undefined;
  user: User | null;
  isAdmin: boolean;
  loading: boolean;
  error: unknown;
  login: (username: string, password: string) => Promise<void>;
  setup: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<unknown>;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['auth-state'],
    queryFn: async () => {
      const s = await get<AuthState>('auth/state');
      setCsrfToken(s.csrf_token);
      return s;
    },
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const refresh = useCallback(() => qc.invalidateQueries({ queryKey: ['auth-state'] }), [qc]);

  useEffect(() => {
    onUnauthorized(() => {
      setCsrfToken(null);
      qc.setQueryData<AuthState | undefined>(['auth-state'], (s) => (s ? { ...s, user: null, csrf_token: null } : s));
    });
    return () => onUnauthorized(null);
  }, [qc]);

  const afterLogin = useCallback(
    async (res: { user: User; csrf_token: string }) => {
      setCsrfToken(res.csrf_token);
      qc.removeQueries({ predicate: (query) => query.queryKey[0] !== 'auth-state' });
      qc.setQueryData<AuthState | undefined>(['auth-state'], (s) =>
        s ? { ...s, user: res.user, csrf_token: res.csrf_token, setup_required: false } : s,
      );
      await refresh();
    },
    [qc, refresh],
  );

  const login = useCallback(
    async (username: string, password: string) =>
      afterLogin(await post<{ user: User; csrf_token: string }>('auth/login', { username, password })),
    [afterLogin],
  );
  const setup = useCallback(
    async (username: string, password: string) =>
      afterLogin(await post<{ user: User; csrf_token: string }>('auth/setup', { username, password })),
    [afterLogin],
  );
  const logout = useCallback(async () => {
    try {
      await post('auth/logout');
    } finally {
      setCsrfToken(null);
      // Keep the auth-state query (its observer must stay attached); drop all cached data otherwise.
      qc.setQueryData<AuthState | undefined>(['auth-state'], (s) => (s ? { ...s, user: null, csrf_token: null } : s));
      qc.removeQueries({ predicate: (query) => query.queryKey[0] !== 'auth-state' });
      await refresh();
    }
  }, [qc, refresh]);

  const user = q.data?.user ?? null;
  return (
    <Ctx.Provider
      value={{
        state: q.data,
        user,
        isAdmin: user?.role === 'admin',
        loading: q.isLoading,
        error: q.error,
        login,
        setup,
        logout,
        refresh,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useAuth(): AuthCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error('AuthProvider missing');
  return c;
}
