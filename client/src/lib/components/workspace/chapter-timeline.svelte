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
	import type { StoryChapter } from '$lib/features/narrative/types';

	let {
		chapters,
		onselect,
		onreorder
	}: {
		chapters: StoryChapter[];
		onselect: (chapter: StoryChapter) => void;
		onreorder: (chapterIds: string[]) => void;
	} = $props();
	const nodeTypes = { narrative: GraphNode };
	let nodes = $state.raw<Node[]>([]);
	let edges = $state.raw<Edge[]>([]);
	function rebuild() {
		nodes = chapters.map((chapter, index) => ({
			id: chapter.id,
			type: 'narrative',
			position: { x: index * 240, y: 120 },
			data: { label: `${chapter.sequence}. ${chapter.title}`, kind: 'chapter', record: chapter, connectable: false }
		}));
		edges = chapters.slice(1).map((chapter, index) => ({
			id: `${chapters[index].id}-${chapter.id}`,
			source: chapters[index].id,
			target: chapter.id,
			type: 'smoothstep'
		}));
	}
	$effect(rebuild);
	function reorderFromCanvas() {
		const order = [...nodes].sort((left, right) => left.position.x - right.position.x).map((node) => node.id);
		if (order.some((id, index) => id !== chapters[index]?.id)) onreorder(order);
	}
</script>

<div class="h-full min-h-96 overflow-hidden rounded-xl border bg-muted/20">
	<SvelteFlow
		bind:nodes
		bind:edges
		{nodeTypes}
		fitView
		nodesConnectable={false}
		onnodedragstop={reorderFromCanvas}
		onnodeclick={(event) => onselect(event.node.data.record as StoryChapter)}
	>
		<Controls />
		<Background variant={BackgroundVariant.Dots} gap={16} size={1} />
	</SvelteFlow>
</div>
