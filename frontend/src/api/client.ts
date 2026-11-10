/** Minimal fetch wrapper: base-relative URLs, cookies, CSRF header and FastAPI error parsing. */

let csrfToken: string | null = null;
let unauthorizedHandler: (() => void) | null = null;

export function setCsrfToken(token: string | null | undefined): void {
  csrfToken = token ?? null;
}

export function onUnauthorized(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

function readCookie(name: string): string | null {
  for (const part of document.cookie.split(';')) {
    const [k, ...v] = part.trim().split('=');
    if (k === name) return decodeURIComponent(v.join('='));
  }
  return null;
}

function getCsrf(): string | null {
  return csrfToken ?? readCookie('omada_docs_csrf');
}

export type Query = Record<string, string | number | boolean | null | undefined>;

/** Build an absolute URL for an API path (without leading slash), relative to <base href>. */
export function apiUrl(path: string, query?: Query): string {
  const url = new URL(`api/${path.replace(/^\/+/, '')}`, document.baseURI);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d) => {
          if (d && typeof d === 'object') {
            const o = d as { msg?: string; loc?: unknown[] };
            const field = Array.isArray(o.loc) ? o.loc.filter((x) => x !== 'body').join('.') : '';
            return field ? `${field}: ${o.msg ?? ''}` : (o.msg ?? '');
          }
          return String(d);
        })
        .join('; ');
    }
  }
  return fallback;
}

export interface RequestOptions {
  method?: string;
  query?: Query;
  body?: unknown;
  form?: FormData;
  signal?: AbortSignal;
}

async function rawRequest(path: string, opts: RequestOptions = {}): Promise<Response> {
  const method = (opts.method ?? 'GET').toUpperCase();
  const headers: Record<string, string> = { Accept: 'application/json' };
  let body: BodyInit | undefined;
  if (opts.form) {
    body = opts.form;
  } else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(opts.body);
  }
  if (method !== 'GET' && method !== 'HEAD') {
    const token = getCsrf();
    if (token) headers['X-CSRF-Token'] = token;
  }
  let res: Response;
  try {
    res = await fetch(apiUrl(path, opts.query), {
      method,
      headers,
      body,
      credentials: 'same-origin',
      signal: opts.signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e;
    throw new ApiError(0, 'The server could not be reached. Please check your connection.');
  }
  if (!res.ok) {
    let parsed: unknown = null;
    try {
      parsed = await res.json();
    } catch {
      /* not JSON */
    }
    const msg = errorMessage(parsed, `Request failed (${res.status} ${res.statusText})`);
    if (res.status === 401 && !path.startsWith('auth/')) unauthorizedHandler?.();
    throw new ApiError(res.status, msg);
  }
  return res;
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await rawRequest(path, opts);
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get('content-type') ?? '';
  if (ct.includes('application/json')) return (await res.json()) as T;
  return (await res.text()) as unknown as T;
}

/** Download a file through fetch (keeps auth/CSRF handling) and save it via an object URL. */
export async function downloadFile(path: string, query?: Query, fallbackName = 'download'): Promise<void> {
  const res = await rawRequest(path, { query });
  const blob = await res.blob();
  const cd = res.headers.get('content-disposition') ?? '';
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
  const name = match ? decodeURIComponent(match[1]) : fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export const get = <T>(path: string, query?: Query, signal?: AbortSignal) => api<T>(path, { query, signal });
export const post = <T>(path: string, body?: unknown) => api<T>(path, { method: 'POST', body });
export const put = <T>(path: string, body?: unknown) => api<T>(path, { method: 'PUT', body });
export const patch = <T>(path: string, body?: unknown) => api<T>(path, { method: 'PATCH', body });
export const del = <T>(path: string) => api<T>(path, { method: 'DELETE' });
export const upload = <T>(path: string, file: File) => {
  const form = new FormData();
  form.append('file', file);
  return api<T>(path, { method: 'POST', form });
};
