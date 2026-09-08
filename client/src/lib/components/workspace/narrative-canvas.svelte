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
		onconnect,
		oneditrelation
	}: {
		subgraph: Subgraph | null;
		onselect: (id: string, label: string, kind: string, record: Record<string, unknown>) => void;
		onconnect: (sourceId: string, targetId: string) => void;
		oneditrelation: (relation: Record<string, unknown>) => void;
	} = $props();
	let nodes = $state.raw<Node[]>([]);
	let edges = $state.raw<Edge[]>([]);
	const nodeTypes = { narrative: GraphNode };
	const nodeWidth = 240;
	const nodeHeight = 104;
	const horizontalGap = 96;
	const verticalGap = 76;

	function gridPosition(index: number, total: number) {
		// Fixed node dimensions plus generous gutters guarantee that every
		// rebuilt view is collision-free, including long labels that wrap.
		const columns = Math.max(1, Math.ceil(Math.sqrt(total)));
		return {
			x: (index % columns) * (nodeWidth + horizontalGap),
			y: Math.floor(index / columns) * (nodeHeight + verticalGap)
		};
	}

	function overlaps(position: { x: number; y: number }, other: Node) {
		return (
			position.x < other.position.x + nodeWidth &&
			position.x + nodeWidth > other.position.x &&
			position.y < other.position.y + nodeHeight &&
			position.y + nodeHeight > other.position.y
		);
	}

	function resolveDrop(node: Node) {
		const otherNodes = nodes.filter((candidate) => candidate.id !== node.id);
		if (!otherNodes.some((candidate) => overlaps(node.position, candidate))) return;

		const stepX = nodeWidth + horizontalGap;
		const stepY = nodeHeight + verticalGap;
		const originColumn = Math.round(node.position.x / stepX);
		const originRow = Math.round(node.position.y / stepY);
		let freePosition: { x: number; y: number } | undefined;

		// Search outward from the dropped slot so the node settles in the closest
		// available place instead of sitting on top of another card.
		for (let radius = 0; radius < 50 && !freePosition; radius += 1) {
			for (let rowOffset = -radius; rowOffset <= radius && !freePosition; rowOffset += 1) {
				for (let columnOffset = -radius; columnOffset <= radius; columnOffset += 1) {
					if (Math.max(Math.abs(rowOffset), Math.abs(columnOffset)) !== radius) continue;
					const position = {
						x: (originColumn + columnOffset) * stepX,
						y: (originRow + rowOffset) * stepY
					};
					if (!otherNodes.some((candidate) => overlaps(position, candidate))) {
						freePosition = position;
						break;
					}
				}
			}
		}

		if (freePosition) {
			nodes = nodes.map((candidate) =>
				candidate.id === node.id ? { ...candidate, position: freePosition } : candidate
			);
		}
	}

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
			position: gridPosition(index, records.length),
			style: `width: ${nodeWidth}px; height: ${nodeHeight}px;`,
			data: {
				label: item.name || item.description || item.content || item.element_type || item.type || item.id,
				kind,
				record: item
			}
		}));
		const nodeIds = new Set(records.map(({ item }) => String(item.id)));
		// A visible connector represents an explicit relation only. Statements
		// describe relation meaning, but must not create a line by themselves.
		edges = relations
			.filter(
				(relation) =>
					nodeIds.has(String(relation.source_node_id)) &&
					nodeIds.has(String(relation.target_node_id))
			)
			.map((relation) => ({
				id: String(relation.id),
				source: String(relation.source_node_id),
				target: String(relation.target_node_id),
				label: String(relation.label).replaceAll('_', ' '),
				data: { relation },
				style: String(relation.relation_type) === 'context' ? 'stroke-dasharray: 5 4' : undefined
			}));
	}
	$effect(rebuild);
</script>

<div class="h-full min-h-96 overflow-hidden rounded-xl border bg-muted/20">
	<SvelteFlow
		bind:nodes
		bind:edges
		{nodeTypes}
		fitView
		nodesDraggable
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
		onedgeclick={(event) => oneditrelation(event.edge.data?.relation as Record<string, unknown>)}
		onnodedragstop={({ targetNode }) => {
			if (targetNode) resolveDrop(targetNode);
		}}
	>
		<Controls />
		<Background variant={BackgroundVariant.Dots} gap={16} size={1} />
	</SvelteFlow>
</div>
