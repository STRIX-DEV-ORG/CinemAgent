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
		onselect
	}: { chapters: StoryChapter[]; onselect: (chapter: StoryChapter) => void } = $props();
	const nodeTypes = { narrative: GraphNode };
	let nodes = $derived<Node[]>(
		chapters.map((chapter, index) => ({
			id: chapter.id,
			type: 'narrative',
			position: { x: index * 240, y: 120 },
			data: { label: `${chapter.sequence}. ${chapter.title}`, kind: 'chapter', record: chapter }
		}))
	);
	let edges = $derived<Edge[]>(
		chapters.slice(1).map((chapter, index) => ({
			id: `${chapters[index].id}-${chapter.id}`,
			source: chapters[index].id,
			target: chapter.id,
			type: 'smoothstep'
		}))
	);
</script>

<div class="h-full min-h-96 overflow-hidden rounded-xl border bg-muted/20">
	<SvelteFlow
		{nodes}
		{edges}
		{nodeTypes}
		fitView
		onnodeclick={(event) => onselect(event.node.data.record as StoryChapter)}
	>
		<Controls />
		<Background variant={BackgroundVariant.Dots} gap={16} size={1} />
	</SvelteFlow>
</div>
