<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle
	} from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Separator } from '$lib/components/ui/separator';
	import { Tabs, TabsContent, TabsList, TabsTrigger } from '$lib/components/ui/tabs';
	import { narrativeApi } from '$lib/features/narrative/api';
	import { loadRecentGraphs, rememberGraph } from '$lib/features/narrative/recent-graphs';
	import type {
		NarrativeGraph,
		NarrativeRecord,
		OperationBatch,
		Subgraph
	} from '$lib/features/narrative/types';

	let graph = $state<NarrativeGraph | null>(null);
	let recentGraphs = $state<NarrativeGraph[]>([]);
	let graphName = $state('');
	let openGraphId = $state('');
	let entityName = $state('');
	let entityType = $state('character');
	let entityStatus = $state('active');
	let batch = $state<OperationBatch | null>(null);
	let subgraph = $state<Subgraph | null>(null);
	let includeEvidence = $state(false);
	let busy = $state(false);
	let message = $state('Create a story graph or open one by UUID to begin.');
	let pollTimer: ReturnType<typeof setTimeout> | undefined;

	onMount(() => {
		recentGraphs = loadRecentGraphs();
	});
	onDestroy(() => {
		if (pollTimer) clearTimeout(pollTimer);
	});

	function errorMessage(error: unknown) {
		return error instanceof Error ? error.message : 'An unexpected error occurred.';
	}
	function remember(graphToRemember: NarrativeGraph) {
		recentGraphs = rememberGraph(graphToRemember);
	}
	function statusVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
		return status === 'applied'
			? 'default'
			: status === 'failed' || status === 'rejected'
				? 'destructive'
				: status === 'accepted' || status === 'applying'
					? 'secondary'
					: 'outline';
	}
	function recordLabel(record: NarrativeRecord) {
		return String(record.name ?? record.predicate ?? record.id ?? 'Untitled record');
	}

	async function createGraph() {
		if (!graphName.trim()) return;
		busy = true;
		try {
			graph = await narrativeApi.createGraph(graphName.trim());
			remember(graph);
			graphName = '';
			batch = null;
			subgraph = null;
			message = `Opened ${graph.name}. Add the first entity when you are ready.`;
		} catch (error) {
			message = errorMessage(error);
		} finally {
			busy = false;
		}
	}
	async function openGraph(id = openGraphId) {
		if (!id.trim()) return;
		busy = true;
		try {
			graph = await narrativeApi.getGraph(id.trim());
			remember(graph);
			openGraphId = graph.id;
			batch = null;
			subgraph = null;
			message = `Opened ${graph.name}.`;
		} catch (error) {
			message = errorMessage(error);
		} finally {
			busy = false;
		}
	}
	async function refreshSubgraph() {
		if (!graph) return;
		try {
			subgraph = await narrativeApi.querySubgraph(graph.id, includeEvidence);
			message = 'The focused graph context is up to date.';
		} catch (error) {
			message = errorMessage(error);
		}
	}
	async function pollBatch(batchId: string) {
		if (!graph) return;
		try {
			batch = await narrativeApi.getBatch(graph.id, batchId);
			if (batch.status === 'accepted' || batch.status === 'applying') {
				pollTimer = setTimeout(() => void pollBatch(batchId), 1000);
				return;
			}
			message =
				batch.status === 'applied'
					? 'Entity written to the narrative graph.'
					: (batch.error ?? `Batch ${batch.status}.`);
			if (batch.status === 'applied') await refreshSubgraph();
		} catch (error) {
			message = errorMessage(error);
		}
	}
	async function createEntity() {
		if (!graph || !entityName.trim()) return;
		busy = true;
		try {
			batch = await narrativeApi.createEntity(graph.id, {
				name: entityName.trim(),
				type: entityType.trim() || 'character',
				status: entityStatus.trim() || 'active'
			});
			entityName = '';
			message = 'Write accepted. Waiting for ClickHouse materialization…';
			if (pollTimer) clearTimeout(pollTimer);
			void pollBatch(batch.id);
		} catch (error) {
			message = errorMessage(error);
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head>
	<title>CinemAgent · Narrative Graph Workspace</title>
	<meta
		name="description"
		content="A writer workspace for turning story ideas into a narrative knowledge graph."
	/>
</svelte:head>

<main class="mx-auto min-h-screen max-w-6xl px-5 py-10 sm:px-8">
	<header class="mb-10 max-w-2xl">
		<p class="mb-2 text-sm font-semibold tracking-[0.2em] text-primary uppercase">CinemAgent</p>
		<h1 class="text-3xl font-semibold tracking-tight sm:text-4xl">Narrative graph workspace</h1>
		<p class="mt-3 text-muted-foreground">
			Capture story ideas as durable graph knowledge that writers and agents can build on together.
		</p>
	</header>

	<div class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
		<section class="grid gap-6">
			<Card>
				<CardHeader
					><CardTitle>{graph ? graph.name : 'Start a story graph'}</CardTitle><CardDescription
						>{graph
							? `Graph ${graph.id} · version ${graph.version}`
							: 'Graphs are the durable workspace for a story and its ideas.'}</CardDescription
					></CardHeader
				>
				<CardContent class="grid gap-4">
					<form
						class="flex flex-col gap-3 sm:flex-row"
						onsubmit={(event) => {
							event.preventDefault();
							void createGraph();
						}}
					>
						<Input bind:value={graphName} placeholder="The Silent Throne" disabled={busy} />
						<Button type="submit" disabled={busy || !graphName.trim()}>Create story graph</Button>
					</form>
					{#if graph}<Button
							class="w-fit"
							variant="outline"
							onclick={() => void refreshSubgraph()}
							disabled={busy}>Refresh graph context</Button
						>{/if}
					<p class="text-sm text-muted-foreground">{message}</p>
				</CardContent>
			</Card>

			<Card>
				<CardHeader
					><CardTitle>Add an entity</CardTitle><CardDescription
						>Writer input becomes a validated operation batch, then materializes into ClickHouse.</CardDescription
					></CardHeader
				>
				<CardContent>
					<form
						class="grid gap-4 sm:grid-cols-3"
						onsubmit={(event) => {
							event.preventDefault();
							void createEntity();
						}}
					>
						<div class="grid gap-2 sm:col-span-3">
							<Label for="entity-name">Name</Label><Input
								id="entity-name"
								bind:value={entityName}
								placeholder="Elena Maren"
								disabled={!graph || busy}
							/>
						</div>
						<div class="grid gap-2">
							<Label for="entity-type">Type</Label><Input
								id="entity-type"
								bind:value={entityType}
								disabled={!graph || busy}
							/>
						</div>
						<div class="grid gap-2">
							<Label for="entity-status">Status</Label><Input
								id="entity-status"
								bind:value={entityStatus}
								disabled={!graph || busy}
							/>
						</div>
						<div class="flex items-end">
							<Button class="w-full" type="submit" disabled={!graph || busy || !entityName.trim()}
								>Write entity</Button
							>
						</div>
					</form>
					{#if batch}
						<Separator class="my-6" />
						<div class="flex flex-wrap items-center gap-3 text-sm">
							<span>Operation batch</span><Badge variant={statusVariant(batch.status)}
								>{batch.status}</Badge
							><span class="font-mono text-xs text-muted-foreground">{batch.id}</span>
						</div>
					{/if}
				</CardContent>
			</Card>

			<Card>
				<CardHeader
					><CardTitle>Focused graph context</CardTitle><CardDescription
						>What agents can retrieve for grounded story work.</CardDescription
					></CardHeader
				>
				<CardContent>
					<label class="mb-4 flex items-center gap-2 text-sm text-muted-foreground"
						><input
							type="checkbox"
							bind:checked={includeEvidence}
							onchange={() => void refreshSubgraph()}
							disabled={!graph}
						/> Include source evidence</label
					>
					{#if subgraph}
						<Tabs value="entities"
							><TabsList
								><TabsTrigger value="entities">Entities ({subgraph.entities.length})</TabsTrigger
								><TabsTrigger value="events">Events ({subgraph.events.length})</TabsTrigger
								><TabsTrigger value="statements"
									>Statements ({subgraph.statements.length})</TabsTrigger
								></TabsList
							>
							<TabsContent value="entities" class="mt-4"
								>{#if subgraph.entities.length}<ul class="grid gap-2">
										{#each subgraph.entities as record (recordLabel(record))}<li
												class="rounded-md border bg-muted/30 px-3 py-2 text-sm"
											>
												{recordLabel(record)}
											</li>{/each}
									</ul>{:else}<p class="text-sm text-muted-foreground">
										Nothing has been retrieved yet.
									</p>{/if}</TabsContent
							>
							<TabsContent value="events" class="mt-4"
								>{#if subgraph.events.length}<ul class="grid gap-2">
										{#each subgraph.events as record (recordLabel(record))}<li
												class="rounded-md border bg-muted/30 px-3 py-2 text-sm"
											>
												{recordLabel(record)}
											</li>{/each}
									</ul>{:else}<p class="text-sm text-muted-foreground">
										Nothing has been retrieved yet.
									</p>{/if}</TabsContent
							>
							<TabsContent value="statements" class="mt-4"
								>{#if subgraph.statements.length}<ul class="grid gap-2">
										{#each subgraph.statements as record (recordLabel(record))}<li
												class="rounded-md border bg-muted/30 px-3 py-2 text-sm"
											>
												{recordLabel(record)}
											</li>{/each}
									</ul>{:else}<p class="text-sm text-muted-foreground">
										Nothing has been retrieved yet.
									</p>{/if}</TabsContent
							>
						</Tabs>
					{:else}<p class="text-sm text-muted-foreground">
							Refresh this panel after opening a graph to inspect its stored narrative context.
						</p>{/if}
				</CardContent>
			</Card>
		</section>

		<aside class="grid content-start gap-6">
			<Card
				><CardHeader
					><CardTitle>Open graph</CardTitle><CardDescription
						>Paste an existing graph UUID.</CardDescription
					></CardHeader
				><CardContent
					><form
						class="grid gap-3"
						onsubmit={(event) => {
							event.preventDefault();
							void openGraph();
						}}
					>
						<Input bind:value={openGraphId} placeholder="Graph UUID" disabled={busy} /><Button
							type="submit"
							variant="outline"
							disabled={busy || !openGraphId.trim()}>Open graph</Button
						>
					</form></CardContent
				></Card
			>
			<Card
				><CardHeader
					><CardTitle>Recent graphs</CardTitle><CardDescription
						>Stored only in this browser.</CardDescription
					></CardHeader
				><CardContent
					>{#if recentGraphs.length}<ul class="grid gap-2">
							{#each recentGraphs as recent (recent.id)}<li>
									<Button
										class="h-auto w-full justify-start py-2 text-left whitespace-normal"
										variant="ghost"
										onclick={() => void openGraph(recent.id)}>{recent.name}</Button
									>
								</li>{/each}
						</ul>{:else}<p class="text-sm text-muted-foreground">
							Graphs you create or open will appear here.
						</p>{/if}</CardContent
				></Card
			>
		</aside>
	</div>
</main>
