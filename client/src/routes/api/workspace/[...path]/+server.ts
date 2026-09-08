import type { RequestHandler } from './$types';
import { forwardResponse, proxyNarrativeRequest } from '$lib/server/backend';

const methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] as const;

function handler(method: string): RequestHandler {
	return async ({ request, fetch, params }) => {
		const headers = new Headers();
		const contentType = request.headers.get('content-type');
		if (contentType) headers.set('content-type', contentType);
		const idempotencyKey = request.headers.get('Idempotency-Key');
		if (idempotencyKey) headers.set('Idempotency-Key', idempotencyKey);
		return forwardResponse(
			await proxyNarrativeRequest(fetch, `/v1/narrative-graphs/${params.path}`, {
				method,
				headers,
				body: method === 'GET' ? undefined : await request.text()
			})
		);
	};
}

export const GET = handler(methods[0]);
export const POST = handler(methods[1]);
export const PUT = handler(methods[2]);
export const PATCH = handler(methods[3]);
export const DELETE = handler(methods[4]);
