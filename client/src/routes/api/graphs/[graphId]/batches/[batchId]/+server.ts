import type { RequestHandler } from './$types';
import { forwardResponse, proxyNarrativeRequest } from '$lib/server/backend';

export const GET: RequestHandler = async ({ fetch, params }) =>
	forwardResponse(
		await proxyNarrativeRequest(
			fetch,
			`/v1/narrative-graphs/${encodeURIComponent(params.graphId)}/operation-batches/${encodeURIComponent(params.batchId)}`
		)
	);
