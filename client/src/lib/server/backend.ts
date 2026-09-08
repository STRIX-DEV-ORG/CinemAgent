import { env } from '$env/dynamic/private';
import { error } from '@sveltejs/kit';

function backendUrl(path: string): string {
	const baseUrl = env.FASTAPI_URL?.replace(/\/$/, '');
	if (!baseUrl) error(500, 'FASTAPI_URL is not configured');
	return `${baseUrl}${path}`;
}

export async function proxyNarrativeRequest(
	fetcher: typeof fetch,
	path: string,
	init: RequestInit = {}
): Promise<Response> {
	if (!env.NARRATIVE_API_KEY) error(500, 'NARRATIVE_API_KEY is not configured');
	const headers = new Headers(init.headers);
	headers.set('Authorization', `Bearer ${env.NARRATIVE_API_KEY}`);
	headers.set('Accept', 'application/json');
	try {
		return await fetcher(backendUrl(path), { ...init, headers });
	} catch {
		error(502, 'The narrative API is unavailable');
	}
}

/** Proxy generated media without requiring the narrative API key in the browser. */
export async function proxyMediaRequest(
	fetcher: typeof fetch,
	path: string,
	init: RequestInit = {}
): Promise<Response> {
	try {
		return await fetcher(backendUrl(path), {
			...init,
			headers: { Accept: '*/*', ...init.headers }
		});
	} catch {
		error(502, 'The media server is unavailable');
	}
}

export function forwardResponse(response: Response): Response {
	const headers = new Headers();
	for (const name of ['content-type', 'content-length', 'content-range', 'accept-ranges']) {
		const value = response.headers.get(name);
		if (value) headers.set(name, value);
	}
	return new Response(response.body, { status: response.status, headers });
}
