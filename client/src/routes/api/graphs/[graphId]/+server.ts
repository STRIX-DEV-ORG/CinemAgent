import type { RequestHandler } from './$types';
import { forwardResponse, proxyNarrativeRequest } from '$lib/server/backend';

export const GET: RequestHandler = async ({ fetch, params }) =>
	forwardResponse(
		await proxyNarrativeRequest(fetch, `/v1/narrative-graphs/${encodeURIComponent(params.graphId)}`)
	);

export const PATCH: RequestHandler = async ({ request, fetch, params }) =>
	forwardResponse(
		await proxyNarrativeRequest(
			fetch,
			`/v1/narrative-graphs/${encodeURIComponent(params.graphId)}`,
			{
				method: 'PATCH',
				headers: { 'content-type': 'application/json' },
				body: await request.text()
			}
		)
	);

export const DELETE: RequestHandler = async ({ fetch, params }) =>
	forwardResponse(
		await proxyNarrativeRequest(fetch, `/v1/narrative-graphs/${encodeURIComponent(params.graphId)}`, {
			method: 'DELETE'
		})
	);
