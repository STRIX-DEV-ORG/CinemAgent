<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
	import { Button } from '$lib/components/ui/button';
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle
	} from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { narrativeApi } from '$lib/features/narrative/api';
	import { loadRecentGraphs, rememberGraph } from '$lib/features/narrative/recent-graphs';

	let title = $state('');
	let error = $state('');
	let pending = $state(false);
	let checkingForStory = $state(true);

	onMount(async () => {
		const mostRecentStory = loadRecentGraphs()[0];
		if (mostRecentStory) {
			await goto(resolve(`/stories/${mostRecentStory.id}`), { replaceState: true });
			return;
		}
		checkingForStory = false;
	});
	async function createStory() {
		if (!title.trim()) return;
		pending = true;
		try {
			const graph = await narrativeApi.createGraph(title.trim());
			rememberGraph(graph);
			await goto(resolve(`/stories/${graph.id}`));
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not create the story.';
		} finally {
			pending = false;
		}
	}
</script>

<main class="grid min-h-screen place-items-center bg-background p-6">
	{#if checkingForStory}
		<p class="text-sm text-muted-foreground">Loading your workspace…</p>
	{:else}<div class="w-full max-w-lg">
		<Card class="w-full max-w-lg"
			><CardHeader
				><p class="text-sm font-semibold tracking-[0.18em] text-primary uppercase">CinemAgent</p>
				<CardTitle class="text-3xl">Begin a story</CardTitle>
				<CardDescription>
					Create the story and its first chapter. Your prose and narrative graph will grow together.
				</CardDescription>
			</CardHeader>
			<CardContent>
				<div class="mb-4 rounded-md text-sm text-blue-800 ">
					<strong>Note:</strong> Insert Title Only for your new story.
				</div>
				<form
					class="grid gap-4"
					onsubmit={(event) => {
						event.preventDefault();
						void createStory();
					}}
				>
					<Input bind:value={title} placeholder="Insert Title Only..." autofocus />
					<Button
						type="submit"
						disabled={pending || !title.trim()}>Create story</Button
					>{#if error}<p class="text-sm text-destructive">{error}</p>{/if}
				</form></CardContent
			></Card
		>
	</div>{/if}
</main>
