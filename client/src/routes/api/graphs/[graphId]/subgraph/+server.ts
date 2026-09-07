import type { RequestHandler } from './$types';
import { forwardResponse, proxyNarrativeRequest } from '$lib/server/backend';

export const POST: RequestHandler = async ({ request, fetch, params }) =>
	forwardResponse(
		await proxyNarrativeRequest(
			fetch,
			`/v1/narrative-graphs/${encodeURIComponent(params.graphId)}/subgraph:query`,
			{
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: await request.text()
			}
		)
	);
