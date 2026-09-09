<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { untrack } from 'svelte';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { narrativeApi, workspaceApi } from '$lib/features/narrative/api';
	import { rememberGraph } from '$lib/features/narrative/recent-graphs';
	import type {
		AgentRun,
		CharacterPresence,
		IntelligenceMetrics,
		NarrativeHistoryEvent,
		NarrativeGraph,
		RelationTimelineItem,
		StoryChapter,
		StoryHealth
	} from '$lib/features/narrative/types';
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
	let intelligenceOpen = $state(false);
	let intelligenceLoading = $state(false);
	let indexingCanon = $state(false);
	let health = $state<StoryHealth | null>(null);
	let presence = $state<CharacterPresence[]>([]);
	let relationTimeline = $state<RelationTimelineItem[]>([]);
	let metrics = $state<IntelligenceMetrics | null>(null);
	let recentEvents = $state<NarrativeHistoryEvent[]>([]);
	let semanticQuery = $state('');
	let semanticResults = $state<
		Array<{
			source_type: string;
			source_id: string;
			chapter_id: string | null;
			content: string;
			metadata: Record<string, unknown>;
			distance: number;
			destination?: {
				kind: 'chapter' | 'node';
				chapter_id: string | null;
				node_id?: string;
				node_type?: string;
			};
		}>
	>([]);
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
				workspaceApi.chapters.list(graphId)
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
		const chapter = await workspaceApi.chapters.create(params.graphId, title.trim());
		title = '';
		await goto(resolve(`/stories/${params.graphId}/chapters/${chapter.id}`));
	}
	async function reorderChapters(chapterIds: string[]) {
		const previous = chapters;
		const byId = new Map(previous.map((chapter) => [chapter.id, chapter]));
		chapters = chapterIds.map((id, index) => ({ ...byId.get(id)!, sequence: index + 1 }));
		try {
			chapters = await workspaceApi.chapters.reorder(params.graphId, chapterIds);
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
			let run = await workspaceApi.agents.startRun(params.graphId, {
				agent_group: 'produce',
				scope: 'story'
			});
			const deadline = Date.now() + 5 * 60_000;
			while ((run.status === 'queued' || run.status === 'running') && Date.now() < deadline) {
				await new Promise((resolve) => setTimeout(resolve, 750));
				run = await workspaceApi.agents.getRun(params.graphId, run.id);
			}
			productionResult = run;
			if (run.status === 'failed') throw new Error(run.error || 'Story production failed.');
			if (run.status !== 'completed' && run.status !== 'reviewed') {
				throw new Error(
					'Story production is taking longer than expected. You can check the run again shortly.'
				);
			}
			error = `Produced your authored story from ${run.result.chapters?.length ?? 0} chapter(s).`;
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not start story production.';
		} finally {
			producingStory = false;
		}
	}
	async function loadIntelligence() {
		intelligenceOpen = true;
		intelligenceLoading = true;
		try {
			const [loadedHealth, loadedPresence, loadedTimeline, loadedMetrics, loadedEvents] =
				await Promise.all([
					workspaceApi.intelligence.storyHealth(params.graphId),
					workspaceApi.intelligence.characterPresence(params.graphId),
					workspaceApi.intelligence.relationTimeline(params.graphId),
					workspaceApi.intelligence.metrics(params.graphId),
					workspaceApi.intelligence.events(params.graphId)
				]);
			health = loadedHealth;
			presence = loadedPresence;
			relationTimeline = loadedTimeline;
			metrics = loadedMetrics;
			recentEvents = loadedEvents;
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not load story intelligence.';
		} finally {
			intelligenceLoading = false;
		}
	}
	async function indexCanon() {
		indexingCanon = true;
		try {
			const result = await workspaceApi.search.backfillSemanticIndex(params.graphId);
			error = result.message;
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not start canon indexing.';
		} finally {
			indexingCanon = false;
		}
	}
	async function searchCanon() {
		if (!semanticQuery.trim()) return;
		try {
			semanticResults = await workspaceApi.search.semanticSearch(params.graphId, semanticQuery);
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not search story canon.';
		}
	}
	function openSemanticResult(result: (typeof semanticResults)[number]) {
		const destination = result.destination;
		const chapterId = destination?.chapter_id ?? result.chapter_id;
		if (!chapterId) {
			error = 'This canon record is global and is not linked to a chapter yet.';
			return;
		}
		const node =
			destination?.kind === 'node' && destination.node_id
				? `?node=${encodeURIComponent(destination.node_id)}`
				: '';
		void goto(resolve(`/stories/${params.graphId}/chapters/${chapterId}${node}`));
	}
</script>

<main
	class="relative grid min-h-screen grid-cols-[3.5rem_minmax(0,1fr)_minmax(0,1fr)] bg-background"
>
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
		{#if productionResult?.result.story_text}<aside
				class="max-h-72 overflow-y-auto border-b bg-primary/5 px-6 py-4"
			>
				<div class="flex items-start justify-between gap-3">
					<div>
						<p class="text-xs font-semibold tracking-wide text-primary uppercase">
							Story production
						</p>
						<p class="mt-1 text-sm text-muted-foreground">
							Assembled from {productionResult.result.chapters?.length ?? 0} authored chapter(s), with
							no template prose.
						</p>
					</div>
					<Button size="sm" variant="ghost" onclick={() => (productionResult = null)}
						>Close results</Button
					>
				</div>
				<details class="mt-3 rounded-md border bg-background p-3">
					<summary class="cursor-pointer text-sm font-medium">View produced story</summary>
					<pre class="mt-3 font-sans text-sm whitespace-pre-wrap">{productionResult.result
							.story_text}</pre>
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
				disabled={intelligenceLoading}
				onclick={() => void loadIntelligence()}>Story intelligence</Button
			>
			<Button
				size="sm"
				variant="outline"
				disabled={producingStory}
				onclick={() => void produceStory()}>{producingStory ? 'Starting…' : 'Produce story'}</Button
			>
		</header>
		{#if intelligenceOpen}<aside class="max-h-[46vh] overflow-y-auto border-b bg-muted/30 p-4">
				<div class="mb-4 flex items-center justify-between gap-3">
					<div>
						<p class="text-xs font-semibold tracking-wide text-primary uppercase">
							Story intelligence
						</p>
						<p class="text-sm text-muted-foreground">
							Live ClickHouse insight models for this narrative.
						</p>
					</div>
					<Button size="sm" variant="ghost" onclick={() => (intelligenceOpen = false)}
						>Close results</Button
					>
				</div>
				{#if intelligenceLoading}<p class="text-sm text-muted-foreground">
						Refreshing narrative intelligence…
					</p>{:else}<div class="grid gap-4 lg:grid-cols-2">
						<section class="rounded-md border bg-background p-3">
							<div class="flex items-center justify-between">
								<h3 class="font-semibold">Story health</h3>
								<Button
									size="sm"
									variant="ghost"
									disabled={indexingCanon}
									onclick={() => void indexCanon()}
									>{indexingCanon ? 'Indexing…' : 'Index canon'}</Button
								>
							</div>
							{#if health}<dl class="mt-3 grid grid-cols-3 gap-3 text-sm">
									<div>
										<dt class="text-muted-foreground">Chapters</dt>
										<dd class="font-semibold">{health.chapters}</dd>
									</div>
									<div>
										<dt class="text-muted-foreground">Nodes</dt>
										<dd class="font-semibold">{health.nodes}</dd>
									</div>
									<div>
										<dt class="text-muted-foreground">Relations</dt>
										<dd class="font-semibold">{health.relations}</dd>
									</div>
									<div>
										<dt class="text-muted-foreground">Open assumptions</dt>
										<dd class="font-semibold">{health.unresolved_assumptions}</dd>
									</div>
									<div>
										<dt class="text-muted-foreground">Evidence</dt>
										<dd class="font-semibold">{health.evidence_count}</dd>
									</div>
									<div>
										<dt class="text-muted-foreground">Coverage</dt>
										<dd class="font-semibold">{Math.round(health.evidence_coverage * 100)}%</dd>
									</div>
								</dl>{/if}
						</section>
						<section class="rounded-md border bg-background p-3">
							<h3 class="font-semibold">Semantic canon</h3>
							<form
								class="mt-3 flex gap-2"
								onsubmit={(event) => {
									event.preventDefault();
									void searchCanon();
								}}
							>
								<Input bind:value={semanticQuery} placeholder="Find prior canon…" /><Button
									size="sm"
									type="submit">Search</Button
								>
							</form>
							{#if semanticResults.length}<div class="mt-3 grid gap-2">
									{#each semanticResults as result (result.source_type + result.source_id)}<button
											class="cursor-pointer rounded border p-2 text-left text-sm transition-colors hover:border-primary hover:bg-muted"
											onclick={() => openSemanticResult(result)}
											><p class="font-medium">
												{result.source_type} · {Math.round((1 - result.distance) * 100)}% match
											</p>
											<p class="mt-1 line-clamp-3 text-muted-foreground">{result.content}</p>
											<p class="mt-2 text-xs text-primary">
												Open {result.destination?.kind === 'node' ? 'node' : 'chapter'} →
											</p></button
										>{/each}
								</div>{/if}
						</section>
						<section class="rounded-md border bg-background p-3">
							<h3 class="font-semibold">Character presence</h3>
							{#if presence.length}<div class="mt-2 grid gap-1 text-sm">
									{#each presence.slice(0, 12) as item (item.chapter_id + item.entity_id)}<button
											class="cursor-pointer rounded px-1 py-1 text-left hover:bg-muted"
											onclick={() =>
												goto(resolve(`/stories/${params.graphId}/chapters/${item.chapter_id}`))}
											>{item.name}
											<span class="text-muted-foreground"
												>in {item.chapter_sequence}. {item.chapter_title}</span
											></button
										>{/each}
								</div>{:else}<p class="mt-2 text-sm text-muted-foreground">
									Link character entities to chapters to see their presence.
								</p>{/if}
						</section>
						<section class="rounded-md border bg-background p-3">
							<h3 class="font-semibold">Relationship evolution</h3>
							{#if relationTimeline.length}<div class="mt-2 grid gap-1 text-sm">
									{#each relationTimeline.slice(0, 12) as relation (relation.id + relation.chapter_id)}<button
											class="cursor-pointer rounded px-1 py-1 text-left hover:bg-muted"
											onclick={() =>
												goto(resolve(`/stories/${params.graphId}/chapters/${relation.chapter_id}`))}
											>{relation.label.replaceAll('_', ' ')}
											<span class="text-muted-foreground"
												>· {relation.chapter_sequence}. {relation.chapter_title}</span
											></button
										>{/each}
								</div>{:else}<p class="mt-2 text-sm text-muted-foreground">
									Create chapter relations to see their evolution.
								</p>{/if}
						</section>
						<section class="rounded-md border bg-background p-3 lg:col-span-2">
							<h3 class="font-semibold">ClickHouse activity</h3>
							<p class="mt-1 text-sm text-muted-foreground">
								{metrics?.activity.reduce((total, item) => total + item.event_count, 0) ?? 0} immutable
								narrative events · {metrics?.embeddings.reduce(
									(total, item) => total + item.count,
									0
								) ?? 0} indexed canon records
							</p>
							{#if metrics?.agent_runs.length}<p class="mt-2 text-xs text-muted-foreground">
									Agent runs: {metrics.agent_runs
										.map((item) => `${item.count} ${item.agent_group} ${item.status}`)
										.join(' · ')}
								</p>{/if}
						</section>
						<section class="rounded-md border bg-background p-3 lg:col-span-2">
							<h3 class="font-semibold">Narrative history</h3>
							{#if recentEvents.length}<div class="mt-2 grid gap-1 text-xs text-muted-foreground">
									{#each recentEvents.slice(0, 8) as event (event.event_id)}<p>
											<span class="font-medium text-foreground"
												>{event.event_type.replaceAll('_', ' ')}</span
											>
											· {event.actor_type} · {new Date(event.occurred_at).toLocaleString()}
										</p>{/each}
								</div>{:else}<p class="mt-2 text-sm text-muted-foreground">
									No immutable history has been recorded for this story yet.
								</p>{/if}
						</section>
					</div>{/if}
			</aside>{/if}
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
			<p class="rounded-lg border bg-card px-4 py-3 text-sm text-muted-foreground">
				Loading story…
			</p>
		</div>
	{/if}
</main>
{#if error}<p class="fixed bottom-4 left-4 rounded bg-destructive p-3 text-sm text-white">
		{error}
	</p>{/if}
