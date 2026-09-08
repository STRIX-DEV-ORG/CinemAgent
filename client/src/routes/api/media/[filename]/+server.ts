import type { RequestHandler } from './$types';
import { forwardResponse, proxyMediaRequest } from '$lib/server/backend';

/** Stream generated audio and storyboard files from FastAPI on the client origin. */
export const GET: RequestHandler = async ({ fetch, params, request }) => {
	const headers = new Headers();
	const range = request.headers.get('range');
	if (range) headers.set('range', range);
	return forwardResponse(
		await proxyMediaRequest(
			fetch,
			`/api/v1/pipeline/media/${encodeURIComponent(params.filename)}`,
			{ headers }
		)
	);
};
