<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { narrativeApi, workspaceApi } from '$lib/features/narrative/api';
	import { rememberGraph } from '$lib/features/narrative/recent-graphs';
	import type { NarrativeGraph, StoryChapter } from '$lib/features/narrative/types';
	import ChapterTimeline from '$lib/components/workspace/chapter-timeline.svelte';
	import StoryMenu from '$lib/components/workspace/story-menu.svelte';

	let { params } = $props();
	let graph = $state<NarrativeGraph | null>(null);
	let chapters = $state<StoryChapter[]>([]);
	let title = $state('');
	let storyTitleDraft = $state('');
	let editingStoryTitle = $state(false);
	let savingStoryTitle = $state(false);
	let error = $state('');
	async function load() {
		try {
			[graph, chapters] = await Promise.all([
				narrativeApi.getGraph(params.graphId),
				workspaceApi.listChapters(params.graphId)
			]);
			storyTitleDraft = graph.name;
			rememberGraph(graph);
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not load story.';
		}
	}
	onMount(() => void load());
	async function addChapter() {
		if (!title.trim()) return;
		const chapter = await workspaceApi.createChapter(params.graphId, title.trim());
		title = '';
		await goto(resolve(`/stories/${params.graphId}/chapters/${chapter.id}`));
	}
	function startEditingStoryTitle() {
		storyTitleDraft = graph?.name ?? '';
		editingStoryTitle = true;
	}
	async function saveStoryTitle() {
		if (!storyTitleDraft.trim()) return;
		savingStoryTitle = true;
		try {
			graph = await narrativeApi.updateGraph(params.graphId, storyTitleDraft.trim());
			storyTitleDraft = graph.name;
			editingStoryTitle = false;
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not update story title.';
		} finally {
			savingStoryTitle = false;
		}
	}
</script>

<main class="grid min-h-screen grid-cols-[3.5rem_minmax(0,1fr)_minmax(0,1fr)] bg-background">
	<aside class="flex flex-col items-center gap-3 border-r py-4">
		<StoryMenu graphId={params.graphId} compact />
	</aside>
	<section class="flex min-h-0 flex-col border-r">
		<header class="border-b px-6 py-4">
			<p class="text-sm text-muted-foreground">Story</p>
			{#if editingStoryTitle}<form
					class="mt-1 flex max-w-md gap-2"
					onsubmit={(event) => {
						event.preventDefault();
						void saveStoryTitle();
					}}
				>
					<Input bind:value={storyTitleDraft} aria-label="Story title" autofocus />
					<Button size="sm" type="submit" disabled={savingStoryTitle || !storyTitleDraft.trim()}
						>{savingStoryTitle ? 'Saving…' : 'Save'}</Button
					>
					<Button
						size="sm"
						variant="outline"
						type="button"
						disabled={savingStoryTitle}
						onclick={() => (editingStoryTitle = false)}>Cancel</Button
					>
				</form>{:else}<div class="flex items-center gap-2">
					<h1 class="text-xl font-semibold">{graph?.name ?? 'Loading…'}</h1>
					<Button size="sm" variant="ghost" onclick={startEditingStoryTitle}>Edit</Button>
				</div>{/if}
		</header>
		<div class="min-h-0 flex-1 overflow-y-auto p-6">
			<div class="prose max-w-none">
				{#each chapters as chapter (chapter.id)}<article class="mb-8">
						<h2>{chapter.title}</h2>
						<p class="whitespace-pre-wrap">
							{chapter.plain_text || 'This chapter is ready for your first words.'}
						</p>
					</article>{/each}
			</div>
		</div>
	</section>
	<section class="flex min-h-0 flex-col">
		<header class="flex items-center justify-between border-b px-6 py-4">
			<div>
				<p class="text-sm text-muted-foreground">Narrative map</p>
				<h2 class="text-xl font-semibold">Chapters</h2>
			</div>
			<form
				class="flex gap-2"
				onsubmit={(event) => {
					event.preventDefault();
					void addChapter();
				}}
			>
				<Input class="w-40" bind:value={title} placeholder="Chapter title" /><Button
					size="sm"
					type="submit">Add</Button
				>
			</form>
		</header>
		<nav class="flex flex-wrap gap-2 border-b p-4">
			{#each chapters as chapter (chapter.id)}<Button
					variant="outline"
					onclick={() => goto(resolve(`/stories/${params.graphId}/chapters/${chapter.id}`))}
					>{chapter.sequence}. {chapter.title}</Button
				>{/each}
		</nav>
		<div class="min-h-0 flex-1 p-4">
			<ChapterTimeline
				{chapters}
				onselect={(chapter) => goto(resolve(`/stories/${params.graphId}/chapters/${chapter.id}`))}
			/>
		</div>
	</section>
</main>
{#if error}<p class="fixed bottom-4 left-4 rounded bg-destructive p-3 text-sm text-white">
		{error}
	</p>{/if}
