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

export function forwardResponse(response: Response): Response {
	const headers = new Headers();
	const contentType = response.headers.get('content-type');
	if (contentType) headers.set('content-type', contentType);
	return new Response(response.body, { status: response.status, headers });
}
