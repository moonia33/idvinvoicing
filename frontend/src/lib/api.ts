const BASE = '/api/v1';

export class ApiError extends Error {
	status: number;
	constructor(status: number, message: string) {
		super(message);
		this.status = status;
	}
}

function csrfToken(): string {
	const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
	return m ? decodeURIComponent(m[1]) : '';
}

export async function ensureCsrf(): Promise<void> {
	await fetch(`${BASE}/auth/csrf`, { credentials: 'include' });
}

export async function api<T = unknown>(
	path: string,
	options: { method?: string; body?: unknown } = {}
): Promise<T> {
	const isForm = options.body instanceof FormData;
	const resp = await fetch(`${BASE}${path}`, {
		method: options.method ?? 'GET',
		credentials: 'include',
		headers: {
			...(options.body !== undefined && !isForm ? { 'Content-Type': 'application/json' } : {}),
			...(options.method && options.method !== 'GET' ? { 'X-CSRFToken': csrfToken() } : {})
		},
		body:
			options.body !== undefined
				? ((isForm ? options.body : JSON.stringify(options.body)) as BodyInit)
				: undefined
	});
	if (!resp.ok) {
		let detail = `Klaida ${resp.status}`;
		try {
			const data = await resp.json();
			if (typeof data.detail === 'string') detail = data.detail;
		} catch {
			// ignore
		}
		throw new ApiError(resp.status, detail);
	}
	if (resp.status === 204) return undefined as T;
	const ct = resp.headers.get('content-type') ?? '';
	return (ct.includes('json') ? resp.json() : resp.blob()) as Promise<T>;
}
