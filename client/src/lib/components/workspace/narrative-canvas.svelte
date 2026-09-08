<script lang="ts">
	import {
		Background,
		BackgroundVariant,
		Controls,
		SvelteFlow,
		type Edge,
		type Node
	} from '@xyflow/svelte';
	import '@xyflow/svelte/dist/style.css';
	import GraphNode from './graph-node.svelte';
	import type { Subgraph } from '$lib/features/narrative/types';

	let {
		subgraph,
		onselect,
		onconnect
	}: {
		subgraph: Subgraph | null;
		onselect: (id: string, label: string, kind: string, record: Record<string, unknown>) => void;
		onconnect: (sourceId: string, targetId: string) => void;
	} = $props();
	let nodes = $state.raw<Node[]>([]);
	let edges = $state.raw<Edge[]>([]);
	const nodeTypes = { narrative: GraphNode };

	function rebuild() {
		if (!subgraph) {
			nodes = [];
			edges = [];
			return;
		}
		const records = [
			...subgraph.entities.map((item) => ({ item, kind: 'entity' })),
			...subgraph.events.map((item) => ({ item, kind: 'event' })),
			...subgraph.contexts.map((item) => ({ item, kind: 'context' })),
			...subgraph.knowledge_elements
				.filter((item) => item.element_type !== 'statement')
				.map((item) => ({ item, kind: 'knowledge' }))
		];
		const relations = subgraph.relations ?? [];
		nodes = records.map(({ item, kind }, index) => ({
			id: String(item.id),
			type: 'narrative',
			position: { x: (index % 3) * 220, y: Math.floor(index / 3) * 150 },
			data: { label: item.name ?? item.element_type ?? item.type ?? item.id, kind, record: item }
		}));
		const relationIds = new Set(relations.map((relation) => String(relation.id)));
		const legacyStatementEdges = subgraph.statements
			.filter((statement) => !relationIds.has(String(statement.id)))
			.map((statement) => ({
				id: String(statement.id),
				source: String(statement.subject_entity_id),
				target: String(statement.object_entity_id),
				label: String(statement.predicate ?? '').replaceAll('_', ' ')
			}));
		edges = [
			...legacyStatementEdges,
			...relations.map((relation) => ({
				id: String(relation.id),
				source: String(relation.source_node_id),
				target: String(relation.target_node_id),
				label: String(relation.label).replaceAll('_', ' '),
				style: String(relation.relation_type) === 'context' ? { strokeDasharray: '5 4' } : undefined
			}))
		];
	}
	$effect(rebuild);
</script>

<div class="h-full min-h-96 overflow-hidden rounded-xl border bg-muted/20">
	<SvelteFlow
		bind:nodes
		bind:edges
		{nodeTypes}
		fitView
		onconnect={(connection) => {
			if (connection.source && connection.target) onconnect(connection.source, connection.target);
		}}
		onnodeclick={(event) =>
			onselect(
				event.node.id,
				String(event.node.data.label),
				String(event.node.data.kind),
				event.node.data.record as Record<string, unknown>
			)}
	>
		<Controls />
		<Background variant={BackgroundVariant.Dots} gap={16} size={1} />
	</SvelteFlow>
</div>
