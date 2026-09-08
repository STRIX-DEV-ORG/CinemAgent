<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { untrack } from 'svelte';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { narrativeApi, workspaceApi } from '$lib/features/narrative/api';
	import { rememberGraph } from '$lib/features/narrative/recent-graphs';
	import type { AgentRun, NarrativeGraph, StoryChapter } from '$lib/features/narrative/types';
	import ChapterTimeline from '$lib/components/workspace/chapter-timeline.svelte';
	import StoryMenu from '$lib/components/workspace/story-menu.svelte';

	let { params } = $props();
	let graph = $state<NarrativeGraph | null>(null);
	let chapters = $state<StoryChapter[]>([]);
	let title = $state('');
	let storyTitleDraft = $state('');
	let editingStoryTitle = $state(false);
	let savingStoryTitle = $state(false);
	let producingStory = $state(false);
	let productionResult = $state<AgentRun | null>(null);
	let loading = $state(true);
	let error = $state('');
	let loadVersion = 0;
	async function load(graphId: string) {
		const version = ++loadVersion;
		loading = true;
		error = '';
		try {
			const [loadedGraph, loadedChapters] = await Promise.all([
				narrativeApi.getGraph(graphId),
				workspaceApi.listChapters(graphId)
			]);
			if (version !== loadVersion) return;
			graph = loadedGraph;
			chapters = loadedChapters;
			storyTitleDraft = graph.name;
			rememberGraph(graph);
		} catch (cause) {
			if (version !== loadVersion) return;
			error = cause instanceof Error ? cause.message : 'Could not load story.';
		} finally {
			if (version === loadVersion) loading = false;
		}
	}
	$effect(() => {
		const graphId = params.graphId;
		untrack(() => void load(graphId));
	});
	$effect(() => {
		const visibleError = error;
		if (!visibleError) return;
		const timer = setTimeout(() => {
			if (error === visibleError) error = '';
		}, 7000);
		return () => clearTimeout(timer);
	});
	async function addChapter() {
		if (!title.trim()) return;
		const chapter = await workspaceApi.createChapter(params.graphId, title.trim());
		title = '';
		await goto(resolve(`/stories/${params.graphId}/chapters/${chapter.id}`));
	}
	async function reorderChapters(chapterIds: string[]) {
		const previous = chapters;
		const byId = new Map(previous.map((chapter) => [chapter.id, chapter]));
		chapters = chapterIds.map((id, index) => ({ ...byId.get(id)!, sequence: index + 1 }));
		try {
			chapters = await workspaceApi.reorderChapters(params.graphId, chapterIds);
		} catch (cause) {
			chapters = previous;
			error = cause instanceof Error ? cause.message : 'Could not reorder chapters.';
		}
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
	async function produceStory() {
		producingStory = true;
		productionResult = null;
		try {
			let run = await workspaceApi.startAgentRun(params.graphId, {
				agent_group: 'produce',
				scope: 'story'
			});
			const deadline = Date.now() + 5 * 60_000;
			while ((run.status === 'queued' || run.status === 'running') && Date.now() < deadline) {
				await new Promise((resolve) => setTimeout(resolve, 750));
				run = await workspaceApi.getAgentRun(params.graphId, run.id);
			}
			productionResult = run;
			if (run.status === 'failed') throw new Error(run.error || 'Story production failed.');
			if (run.status !== 'completed' && run.status !== 'reviewed') {
				throw new Error('Story production is taking longer than expected. You can check the run again shortly.');
			}
			error = `Produced your authored story from ${run.result.chapters?.length ?? 0} chapter(s).`;
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not start story production.';
		} finally {
			producingStory = false;
		}
	}
</script>

<main class="relative grid min-h-screen grid-cols-[3.5rem_minmax(0,1fr)_minmax(0,1fr)] bg-background">
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
		{#if productionResult?.result.story_text}<aside class="max-h-72 overflow-y-auto border-b bg-primary/5 px-6 py-4">
				<div class="flex items-start justify-between gap-3">
					<div>
						<p class="text-xs font-semibold tracking-wide text-primary uppercase">Story production</p>
						<p class="mt-1 text-sm text-muted-foreground">
							Assembled from {productionResult.result.chapters?.length ?? 0} authored chapter(s), with no template prose.
						</p>
					</div>
					<Button size="sm" variant="ghost" onclick={() => (productionResult = null)}>Close results</Button>
				</div>
				<details class="mt-3 rounded-md border bg-background p-3">
					<summary class="cursor-pointer text-sm font-medium">View produced story</summary>
					<pre class="mt-3 whitespace-pre-wrap text-sm font-sans">{productionResult.result.story_text}</pre>
				</details>
			</aside>{/if}
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
			<Button
				size="sm"
				variant="outline"
				disabled={producingStory}
				onclick={() => void produceStory()}>{producingStory ? 'Starting…' : 'Produce story'}</Button
			>
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
				onreorder={reorderChapters}
			/>
		</div>
	</section>
	{#if loading}
		<div class="absolute inset-0 z-30 grid place-items-center bg-background/70 backdrop-blur-sm">
			<p class="rounded-lg border bg-card px-4 py-3 text-sm text-muted-foreground">Loading story…</p>
		</div>
	{/if}
</main>
{#if error}<p class="fixed bottom-4 left-4 rounded bg-destructive p-3 text-sm text-white">
		{error}
	</p>{/if}
