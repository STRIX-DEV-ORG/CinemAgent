<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
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
	import { rememberGraph } from '$lib/features/narrative/recent-graphs';
	import StoryMenu from '$lib/components/workspace/story-menu.svelte';

	let title = $state('');
	let error = $state('');
	let pending = $state(false);
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

<main class="grid min-h-screen grid-cols-[3.5rem_minmax(0,1fr)] bg-background">
	<aside class="flex flex-col items-center gap-3 border-r py-4">
		<StoryMenu compact />
	</aside>
	<div class="grid place-items-center p-6">
		<Card class="w-full max-w-lg"
			><CardHeader
				><p class="text-sm font-semibold tracking-[0.18em] text-primary uppercase">CinemAgent</p>
				<CardTitle class="text-3xl">Begin a story</CardTitle><CardDescription
					>Create the story and its first chapter. Your prose and narrative graph will grow
					together.</CardDescription
				></CardHeader
			><CardContent
				><form
					class="grid gap-4"
					onsubmit={(event) => {
						event.preventDefault();
						void createStory();
					}}
				>
					<Input bind:value={title} placeholder="The Silent Throne" autofocus /><Button
						type="submit"
						disabled={pending || !title.trim()}>Create story</Button
					>{#if error}<p class="text-sm text-destructive">{error}</p>{/if}
				</form></CardContent
			></Card
		>
	</div>
</main>
