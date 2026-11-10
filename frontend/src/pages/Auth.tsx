import { useState, type FormEvent, type ReactNode } from 'react';
import { Loader2, Moon, Server, Sun } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { Badge, ErrorBox, Field } from '../components/ui';

function AuthFrame({ title, subtitle, children }: { title: string; subtitle: ReactNode; children: ReactNode }) {
  const { state } = useAuth();
  const { theme, toggle } = useTheme();
  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-100 to-slate-200 p-4 dark:from-slate-950 dark:to-slate-900">
      <button className="btn-ghost fixed right-4 top-4 p-2" onClick={toggle} aria-label="Toggle theme">
        {theme === 'dark' ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
      </button>
      <div className="card w-full max-w-sm p-6">
        <div className="mb-5 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-600 text-white">
            <Server className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-semibold">{title}</h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">{subtitle}</p>
          </div>
        </div>
        {state?.demo_mode && (
          <div className="mb-4">
            <Badge tone="violet">DEMO MODE</Badge>
          </div>
        )}
        {children}
        <p className="mt-6 text-center text-[11px] text-slate-400">Omada Network Documentation Platform {state?.version ? `v${state.version}` : ''}</p>
      </div>
    </div>
  );
}

export function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthFrame title="Sign in" subtitle="Omada Network Documentation">
      <form className="space-y-4" onSubmit={submit}>
        <Field label="Username">
          <input className="input" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
        </Field>
        <Field label="Password">
          <input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </Field>
        {error !== null && <ErrorBox error={error} title="Sign-in failed" />}
        <button className="btn-primary w-full" type="submit" disabled={busy}>
          {busy && <Loader2 className="h-4 w-4 animate-spin" />} Sign in
        </button>
      </form>
    </AuthFrame>
  );
}

export function SetupPage() {
  const { setup } = useAuth();
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (password.length < 10) return setError('The password must be at least 10 characters long.');
    if (password !== confirm) return setError('The passwords do not match.');
    setBusy(true);
    setError(null);
    try {
      await setup(username.trim(), password);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthFrame title="Initial setup" subtitle="Create the first administrator account">
      <form className="space-y-4" onSubmit={submit}>
        <Field label="Administrator username">
          <input className="input" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required maxLength={64} />
        </Field>
        <Field label="Password" hint="At least 10 characters">
          <input className="input" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={10} />
        </Field>
        <Field label="Confirm password">
          <input className="input" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
        </Field>
        {error !== null && <ErrorBox error={error} title="Setup failed" />}
        <button className="btn-primary w-full" type="submit" disabled={busy}>
          {busy && <Loader2 className="h-4 w-4 animate-spin" />} Create administrator
        </button>
      </form>
    </AuthFrame>
  );
}
