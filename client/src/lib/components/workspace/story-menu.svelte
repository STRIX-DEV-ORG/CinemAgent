<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { narrativeApi, workspaceApi } from '$lib/features/narrative/api';
	import { loadRecentGraphs, rememberGraph } from '$lib/features/narrative/recent-graphs';
	import type { NarrativeGraph, StoryChapter } from '$lib/features/narrative/types';

	let { graphId, compact = false }: { graphId?: string; compact?: boolean } = $props();
	let open = $state(false);
	let title = $state('');
	let busy = $state(false);
	let error = $state('');
	let recent = $state<NarrativeGraph[]>([]);
	let fileInput = $state<HTMLInputElement>();

	onMount(() => {
		recent = loadRecentGraphs();
	});

	async function createStory() {
		if (!title.trim()) return;
		busy = true;
		try {
			const graph = await narrativeApi.createGraph(title.trim());
			rememberGraph(graph);
			await goto(resolve(`/stories/${graph.id}`));
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not create story.';
		} finally {
			busy = false;
		}
	}

	async function exportStory() {
		if (!graphId) return;
		busy = true;
		try {
			const [story, chapters, graph] = await Promise.all([
				narrativeApi.getGraph(graphId),
				workspaceApi.listChapters(graphId),
				narrativeApi.querySubgraph(graphId, false)
			]);
			const chapterNodes = await Promise.all(
				chapters.map(async (chapter) => ({
					id: chapter.id,
					graph: await narrativeApi.querySubgraph(graphId, false, [], chapter.id)
				}))
			);
			const blob = new Blob(
				[JSON.stringify({ version: 1, story, chapters, graph, chapterNodes }, null, 2)],
				{
					type: 'application/json'
				}
			);
			const url = URL.createObjectURL(blob);
			const link = document.createElement('a');
			link.href = url;
			link.download = `${story.name.replaceAll(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '') || 'story'}.json`;
			link.click();
			URL.revokeObjectURL(url);
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not export story.';
		} finally {
			busy = false;
		}
	}

	async function importStory(event: Event) {
		const file = (event.currentTarget as HTMLInputElement).files?.[0];
		if (!file) return;
		busy = true;
		try {
			const snapshot = JSON.parse(await file.text()) as {
				story?: { name?: string };
				chapters?: StoryChapter[];
			};
			if (!snapshot.story?.name || !Array.isArray(snapshot.chapters) || !snapshot.chapters.length) {
				throw new Error('Choose a CinemAgent story export file.');
			}
			const graph = await narrativeApi.createGraph(snapshot.story.name);
			const importedChapters = await workspaceApi.listChapters(graph.id);
			const first = snapshot.chapters[0];
			await workspaceApi.updateChapter(graph.id, importedChapters[0].id, { title: first.title });
			await workspaceApi.saveDocument(
				graph.id,
				importedChapters[0].id,
				first.document,
				first.plain_text,
				importedChapters[0].revision + 1
			);
			for (const chapter of snapshot.chapters.slice(1)) {
				const created = await workspaceApi.createChapter(graph.id, chapter.title);
				await workspaceApi.saveDocument(
					graph.id,
					created.id,
					chapter.document,
					chapter.plain_text,
					created.revision
				);
			}
			rememberGraph(graph);
			await goto(resolve(`/stories/${graph.id}`));
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not import story.';
		} finally {
			busy = false;
			if (fileInput) fileInput.value = '';
		}
	}
</script>

<div class="relative flex justify-center">
	<Button
		size={compact ? 'icon' : 'sm'}
		variant="outline"
		aria-label="Stories"
		aria-expanded={open}
		onclick={() => (open = !open)}>{compact ? '☰' : 'Stories'}</Button
	>
	{#if open}<section
			class="absolute top-full left-0 z-40 mt-2 w-72 rounded-lg border bg-popover p-3 shadow-lg"
		>
			<p class="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
				Your stories
			</p>
			<form
				class="mt-2 flex gap-2"
				onsubmit={(event) => {
					event.preventDefault();
					void createStory();
				}}
			>
				<Input bind:value={title} placeholder="New story title" />
				<Button size="sm" type="submit" disabled={busy || !title.trim()}>New</Button>
			</form>
			<div class="mt-3 grid gap-1">
				<p class="text-xs text-muted-foreground">Continue</p>
				{#each recent as story (story.id)}<Button
						size="sm"
						variant="ghost"
						class="justify-start"
						onclick={() => goto(resolve(`/stories/${story.id}`))}>{story.name}</Button
					>{:else}<p class="text-xs text-muted-foreground">
						Stories you open will appear here.
					</p>{/each}
			</div>
			<div class="mt-3 grid grid-cols-2 gap-2 border-t pt-3">
				<Button
					size="sm"
					variant="outline"
					disabled={busy || !graphId}
					onclick={() => void exportStory()}>Export</Button
				>
				<Button size="sm" variant="outline" disabled={busy} onclick={() => fileInput?.click()}
					>Import</Button
				>
				<input
					class="hidden"
					bind:this={fileInput}
					type="file"
					accept="application/json"
					onchange={(event) => void importStory(event)}
				/>
			</div>
			{#if error}<p class="mt-2 text-xs text-destructive">{error}</p>{/if}
		</section>{/if}
</div>
