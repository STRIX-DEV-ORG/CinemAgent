import type {
	AnalysisProposal,
	AnalysisRun,
	NarrativeGraph,
	OperationBatch,
	StoryChapter,
	Subgraph,
	TextProposal,
	AgentGroup,
	AgentRun,
	TipTapDocument
} from './types';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const response = await fetch(path, init);
	if (!response.ok)
		throw new Error((await response.text()) || `Request failed with status ${response.status}`);
	if (response.status === 204) return undefined as T;
	return response.json() as Promise<T>;
}

export const narrativeApi = {
	createGraph: (name: string) =>
		request<NarrativeGraph>('/api/graphs', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ name })
		}),
	getGraph: (graphId: string) => request<NarrativeGraph>(`/api/graphs/${graphId}`),
	updateGraph: (graphId: string, name: string) =>
		request<NarrativeGraph>(`/api/graphs/${graphId}`, {
			method: 'PATCH',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ name })
		}),
	deleteGraph: (graphId: string) => request<void>(`/api/graphs/${graphId}`, { method: 'DELETE' }),
	createEntity: (graphId: string, entity: { name: string; type: string; status: string }) =>
		request<OperationBatch>(`/api/graphs/${graphId}/operations`, {
			method: 'POST',
			headers: { 'content-type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
			body: JSON.stringify({
				operations: [
					{
						id: crypto.randomUUID(),
						operation_type: 'create_entity',
						origin: 'writer',
						payload: { id: crypto.randomUUID(), ...entity, metadata: {} },
						provenance: { source: 'writer-ui' }
					}
				]
			})
		}),
	querySubgraph: (
		graphId: string,
		includeEvidence: boolean,
		entityIds: string[] = [],
		chapterId?: string
	) =>
		request<Subgraph>(`/api/graphs/${graphId}/subgraph`, {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({
				include_evidence: includeEvidence,
				entity_ids: entityIds,
				chapter_id: chapterId,
				limit: 100
			})
		}),
	createNode: (
		graphId: string,
		kind: 'entity' | 'event' | 'context' | 'assumption',
		values: Record<string, unknown>,
		chapterId: string
	) => {
		const id = crypto.randomUUID();
		const metadata = {
			...(values.metadata as Record<string, unknown> | undefined),
			chapter_id: chapterId
		};
		const payload =
			kind === 'entity'
				? {
						id,
						name: String(values.name),
						type: String(values.type),
						status: String(values.status ?? 'active'),
						description: String(values.description ?? ''),
						content: String(values.content ?? ''),
						confidence: Number(values.confidence ?? 1),
						aliases: values.aliases ?? [],
						metadata
					}
				: kind === 'event'
					? {
							id,
							name: String(values.name),
							type: String(values.type),
							status: String(values.status ?? 'active'),
							description: String(values.description ?? ''),
							content: String(values.content ?? ''),
							confidence: Number(values.confidence ?? 1),
							metadata
						}
					: kind === 'context'
						? {
								id,
								name: String(values.name),
								type: String(values.type),
								description: String(values.description ?? ''),
								content: String(values.content ?? ''),
								holder_entity_id: values.holder_entity_id || null,
								confidence: Number(values.confidence ?? 1),
								metadata
							}
						: {
							id,
							element_type: String(values.element_type),
							name: String(values.name),
							description: String(values.description ?? ''),
							content: String(values.content ?? ''),
								origin: String(values.origin ?? 'writer'),
								status: String(values.status ?? 'active'),
								confidence: Number(values.confidence ?? 1),
								metadata
							};
		const operationType = kind === 'assumption' ? 'create_knowledge_element' : `create_${kind}`;
		return request<OperationBatch>(`/api/graphs/${graphId}/operations`, {
			method: 'POST',
			headers: { 'content-type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
			body: JSON.stringify({
				operations: [
					{
						id: crypto.randomUUID(),
						operation_type: operationType,
						origin: 'writer',
						payload,
						provenance: { source: 'writer-ui', chapter_id: chapterId }
					},
					{
						id: crypto.randomUUID(),
						operation_type: 'link_node_to_chapter',
						origin: 'writer',
						payload: {
							chapter_id: chapterId,
							node_id: id,
							node_type: kind === 'assumption' ? 'knowledge_element' : kind
						},
						provenance: { source: 'writer-ui' }
					}
				]
			})
		});
	},
	deleteNode: (
		graphId: string,
		id: string,
		nodeType: 'entity' | 'event' | 'context' | 'knowledge_element'
	) =>
		request<OperationBatch>(`/api/graphs/${graphId}/operations`, {
			method: 'POST',
			headers: { 'content-type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
			body: JSON.stringify({
				operations: [
					{
						id: crypto.randomUUID(),
						operation_type: 'delete_node',
						origin: 'writer',
						payload: { id, node_type: nodeType },
						provenance: { source: 'writer-ui' }
					}
				]
			})
		}),
	linkNodeToChapter: (
		graphId: string,
		chapterId: string,
		nodeId: string,
		nodeType: 'entity' | 'event' | 'context' | 'knowledge_element'
	) =>
		request<OperationBatch>(`/api/graphs/${graphId}/operations`, {
			method: 'POST',
			headers: { 'content-type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
			body: JSON.stringify({
				operations: [
					{
						id: crypto.randomUUID(),
						operation_type: 'link_node_to_chapter',
						origin: 'writer',
						payload: { chapter_id: chapterId, node_id: nodeId, node_type: nodeType },
						provenance: { source: 'writer-ui' }
					}
				]
			})
		}),
	createRelation: (
		graphId: string,
		chapterId: string,
		sourceId: string,
		targetId: string,
		values: {
			relationType: 'statement' | 'context';
			label: string;
			description?: string;
			confidence?: number;
		}
	) => {
		const relationId = crypto.randomUUID();
		const isStatement = values.relationType === 'statement';
		const description = values.description?.trim() ?? '';
		const confidence = values.confidence ?? 1;
		const operations: Array<Record<string, unknown>> = [
			{
				id: crypto.randomUUID(),
				operation_type: 'create_relation',
				origin: 'writer',
				payload: {
					id: relationId,
					source_node_id: sourceId,
					target_node_id: targetId,
					relation_type: values.relationType,
					label: values.label.trim(),
					description,
					status: 'active',
					confidence,
					metadata: { chapter_id: chapterId }
				},
				provenance: { source: 'writer-ui' }
			},
			{
				id: crypto.randomUUID(),
				operation_type: 'link_node_to_chapter',
				origin: 'writer',
				payload: { chapter_id: chapterId, node_id: relationId, node_type: 'relation' },
				provenance: { source: 'writer-ui' }
			}
		];
		if (isStatement) {
			operations.splice(
				1,
				0,
				{
					id: crypto.randomUUID(),
					operation_type: 'create_knowledge_element',
					origin: 'writer',
					payload: {
						id: relationId,
						element_type: 'statement',
						description,
						origin: 'writer',
						status: 'active',
						confidence,
						metadata: { chapter_id: chapterId }
					},
					provenance: { source: 'writer-ui' }
				},
				{
					id: crypto.randomUUID(),
					operation_type: 'create_statement',
					origin: 'writer',
					payload: {
						id: relationId,
						subject_entity_id: sourceId,
						predicate: values.label.trim(),
						object_entity_id: targetId,
						description,
						status: 'active',
						confidence,
						metadata: { chapter_id: chapterId }
					},
					provenance: { source: 'writer-ui' }
				},
				{
					id: crypto.randomUUID(),
					operation_type: 'link_node_to_chapter',
					origin: 'writer',
					payload: { chapter_id: chapterId, node_id: relationId, node_type: 'knowledge_element' },
					provenance: { source: 'writer-ui' }
				}
			);
		}
		return request<OperationBatch>(`/api/graphs/${graphId}/operations`, {
			method: 'POST',
			headers: { 'content-type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
			body: JSON.stringify({
				operations
			})
		});
	},
	updateRelation: (graphId: string, relationId: string, changes: Record<string, unknown>) =>
		request<OperationBatch>(`/api/graphs/${graphId}/operations`, {
			method: 'POST',
			headers: { 'content-type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
			body: JSON.stringify({
				operations: [{
					id: crypto.randomUUID(),
					operation_type: 'update_relation',
					origin: 'writer',
					payload: { id: relationId, changes },
					provenance: { source: 'writer-ui' }
				}]
			})
		}),
	deleteRelation: (graphId: string, relationId: string) =>
		request<OperationBatch>(`/api/graphs/${graphId}/operations`, {
			method: 'POST',
			headers: { 'content-type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
			body: JSON.stringify({
				operations: [{
					id: crypto.randomUUID(),
					operation_type: 'delete_relation',
					origin: 'writer',
					payload: { id: relationId },
					provenance: { source: 'writer-ui' }
				}]
			})
		}),
	updateNode: (
		graphId: string,
		id: string,
		nodeType: 'entity' | 'event' | 'context' | 'knowledge_element',
		changes: Record<string, unknown>
	) =>
		request<OperationBatch>(`/api/graphs/${graphId}/operations`, {
			method: 'POST',
			headers: { 'content-type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
			body: JSON.stringify({
				operations: [
					{
						id: crypto.randomUUID(),
						operation_type: 'update_node',
						origin: 'writer',
						payload: { id, node_type: nodeType, changes },
						provenance: { source: 'writer-ui' }
					}
				]
			})
		}),
	getBatch: (graphId: string, batchId: string) =>
		request<OperationBatch>(`/api/graphs/${graphId}/batches/${batchId}`)
};

const workspacePath = (graphId: string, path = '') => `/api/workspace/${graphId}${path}`;
export const workspaceApi = {
	startAgentRun: (
		graphId: string,
		runRequest: {
			agent_group: AgentGroup;
			chapter_id?: string;
			scope?: 'chapter' | 'story';
			instruction?: string;
		}
	) =>
		request<AgentRun>(workspacePath(graphId, '/agent-runs'), {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify(runRequest)
		}),
	getAgentRun: (graphId: string, runId: string) =>
		request<AgentRun>(workspacePath(graphId, `/agent-runs/${runId}`)),
	listAgentRuns: (graphId: string, chapterId?: string) =>
		request<AgentRun[]>(
			workspacePath(graphId, `/agent-runs${chapterId ? `?chapter_id=${chapterId}` : ''}`)
		),
	reviewAgentRun: (graphId: string, runId: string, accepted_text_ids: string[]) =>
		request<AgentRun>(workspacePath(graphId, `/agent-runs/${runId}/review`), {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ accepted_text_ids })
		}),
	saveStoryboards: (graphId: string, runId: string, selected_scene_ids: string[]) =>
		request<AgentRun>(workspacePath(graphId, `/agent-runs/${runId}/storyboards`), {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ selected_scene_ids })
		}),
	listChapters: (graphId: string) => request<StoryChapter[]>(workspacePath(graphId, '/chapters')),
	getChapter: (graphId: string, chapterId: string) =>
		request<StoryChapter>(workspacePath(graphId, `/chapters/${chapterId}`)),
	createChapter: (graphId: string, title: string) =>
		request<StoryChapter>(workspacePath(graphId, '/chapters'), {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ title })
		}),
	deleteChapter: (graphId: string, chapterId: string) =>
		request<void>(workspacePath(graphId, `/chapters/${chapterId}`), { method: 'DELETE' }),
	updateChapter: (
		graphId: string,
		chapterId: string,
		update: { title?: string; sequence?: number }
	) =>
		request<StoryChapter>(workspacePath(graphId, `/chapters/${chapterId}`), {
			method: 'PATCH',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify(update)
		}),
	reorderChapters: (graphId: string, chapterIds: string[]) =>
		request<StoryChapter[]>(workspacePath(graphId, '/chapters/order'), {
			method: 'PUT',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ chapter_ids: chapterIds })
		}),
	saveDocument: (
		graphId: string,
		chapterId: string,
		document: TipTapDocument,
		plain_text: string,
		revision: number
	) =>
		request<StoryChapter>(workspacePath(graphId, `/chapters/${chapterId}/document`), {
			method: 'PUT',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ document, plain_text, revision })
		}),
	startAnalysis: (graphId: string, chapterId: string) =>
		request<AnalysisRun>(workspacePath(graphId, `/chapters/${chapterId}/analysis-runs`), {
			method: 'POST'
		}),
	suggestText: (graphId: string, chapterId: string) =>
		request<TextProposal[]>(workspacePath(graphId, `/chapters/${chapterId}/text-proposals`), {
			method: 'POST'
		}),
	getProposals: (graphId: string, chapterId: string, runId: string) =>
		request<AnalysisProposal[]>(
			workspacePath(graphId, `/chapters/${chapterId}/analysis-runs/${runId}/proposals`)
		),
	applyProposals: (graphId: string, chapterId: string, runId: string, accepted_ids: string[]) =>
		request<OperationBatch>(
			workspacePath(graphId, `/chapters/${chapterId}/analysis-runs/${runId}:apply`),
			{
				method: 'POST',
				headers: { 'content-type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
				body: JSON.stringify({ accepted_ids })
			}
		)
};
